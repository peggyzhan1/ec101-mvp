from decimal import Decimal

import pytest

from ec101.confirmation.queries import (
    get_confirmation_overview,
    list_confirmation_exceptions,
    list_confirmation_reconciliation,
)
from ec101.db import connect_database, create_database


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "queries.db"
    create_database(path)
    connection = connect_database(path)
    cycle_id = connection.execute(
        "INSERT INTO fee_cycle "
        "(fee_cycle_code, cycle_name, period_start, period_end, status, created_at) "
        "VALUES ('2026-09', '2026年9月', '2026-09-01', '2026-09-30', 'confirming', '2026-10-01')"
    ).lastrowid
    recipients = [
        ("A", "客户A", 100, "matched"),
        ("B", "客户B", 200, "unmatched"),
        ("C", "客户C", 300, "ambiguous"),
        ("D", "客户D", 400, "matched"),
        ("E", "客户E", 500, "matched"),
    ]
    for code, name, amount, mapping_status in recipients:
        connection.execute(
            "INSERT INTO fee_recipient "
            "(fee_cycle_id, sap_customer_code, sap_customer_name, expected_amount, "
            "mapping_status, mapping_reason, handoff_status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'pending', '2026-10-01')",
            (cycle_id, code, name, amount, mapping_status, None if mapping_status == "matched" else "测试异常"),
        )
    batch_id = connection.execute(
        "INSERT INTO survey_import_batch "
        "(fee_cycle_id, source_file_name, source_file_sha256, imported_at, row_count, "
        "matched_count, unmatched_count, status) "
        "VALUES (?, 'survey.xlsx', 'hash', '2026-10-10', 8, 6, 2, 'imported')",
        (cycle_id,),
    ).lastrowid

    def add(sequence, code, answer, submitted_at, status="matched", reason=None):
        connection.execute(
            "INSERT INTO survey_response "
            "(survey_import_batch_id, fee_cycle_id, sap_customer_code, sap_customer_name, "
            "received_answer, submitted_at, raw_sequence_no, match_status, match_reason, "
            "response_fingerprint, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-10-10')",
            (batch_id, cycle_id, code, f"客户{code}", answer, submitted_at, sequence, status, reason, f"fp-{sequence}"),
        )

    add("1", "A", "not_received", "2026-10-01 10:00:00")
    add("2", "A", "received", "2026-10-02 10:00:00")
    add("3", "C", "not_received", "2026-10-03 10:00:00")
    add("4", "C", "received", "2026-10-03 10:00:00")
    add("5", "D", "received", "2026-10-04 10:00:00")
    add("6", "E", "not_received", "2026-10-05 10:00:00")
    add("7", "X", "received", "2026-10-06 10:00:00", "not_in_recipient_list", "名单外")
    add("8", "E", None, None, "invalid", "答案无效")
    connection.commit()
    yield connection
    connection.close()


def metric(overview, name):
    return overview[name]["customerCount"], Decimal(str(overview[name]["expectedAmount"]))


def test_reconciliation_uses_latest_response_flags_conflicts_and_keeps_missing(db):
    result = list_confirmation_reconciliation(db, "2026-09", None, "", 100, 0)
    items = {item["sapCustomerCode"]: item for item in result["items"]}

    assert result["total"] == 5
    assert items["A"]["receivedAnswer"] == "received"
    assert items["A"]["hasConflict"] is True
    assert items["A"]["confirmationStatus"] == "答卷冲突"
    assert items["B"]["surveyResponseId"] is None
    assert items["B"]["confirmationStatus"] == "未提交"
    assert items["C"]["receivedAnswer"] == "received"
    assert items["C"]["hasConflict"] is True
    assert items["C"]["rawSequenceNo"] == "4"
    assert all("respondentMobile" not in item for item in result["items"])


def test_confirmation_overview_counts_customers_and_recipient_amounts(db):
    overview = get_confirmation_overview(db, "2026-09")

    assert metric(overview, "recipient") == (5, Decimal("1500"))
    assert metric(overview, "submitted") == (4, Decimal("1300"))
    assert metric(overview, "notSubmitted") == (1, Decimal("200"))
    assert metric(overview, "received") == (1, Decimal("400"))
    assert metric(overview, "notReceived") == (1, Decimal("500"))
    assert metric(overview, "conflict") == (2, Decimal("400"))
    assert overview["outsideListResponseCount"] == 1
    assert metric(overview, "unmatchedMapping") == (1, Decimal("200"))
    assert metric(overview, "ambiguousMapping") == (1, Decimal("300"))


@pytest.mark.parametrize(
    "kind",
    ["outside_list", "conflict", "unmatched_mapping", "ambiguous_mapping", "invalid_response"],
)
def test_confirmation_exceptions_can_filter_each_supported_kind(db, kind):
    result = list_confirmation_exceptions(db, "2026-09", kind, 100, 0)

    assert result["total"] >= 1
    assert {item["kind"] for item in result["items"]} == {kind}
    assert all("respondentMobile" not in item for item in result["items"])


def test_confirmation_queries_validate_cycle_filters_and_pagination(db):
    with pytest.raises(LookupError):
        get_confirmation_overview(db, "2099-01")
    with pytest.raises(ValueError):
        list_confirmation_reconciliation(db, "2026-09", "未知", "", 100, 0)
    with pytest.raises(ValueError):
        list_confirmation_exceptions(db, "2026-09", "unknown", 100, 0)

    page = list_confirmation_reconciliation(db, "2026-09", None, "客户", 999, -10)
    assert page["limit"] == 500
    assert page["offset"] == 0
