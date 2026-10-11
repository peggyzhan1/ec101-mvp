import pytest

from ec101.confirmation.surveys import (
    SurveyValidationError,
    import_survey_responses,
)
from ec101.db import connect_database, create_database


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "surveys.db"
    create_database(path)
    connection = connect_database(path)
    cycle_id = connection.execute(
        "INSERT INTO fee_cycle "
        "(fee_cycle_code, cycle_name, period_start, period_end, status, created_at) "
        "VALUES ('2026-09', '2026年9月', '2026-09-01', '2026-09-30', 'confirming', '2026-10-01')"
    ).lastrowid
    connection.execute(
        "INSERT INTO fee_recipient "
        "(fee_cycle_id, sap_customer_code, sap_customer_name, expected_amount, "
        "mapping_status, handoff_status, created_at) "
        "VALUES (?, '0570502563', '佳源食品商行', 500, 'matched', 'configured', '2026-10-01')",
        (cycle_id,),
    )
    connection.commit()
    yield connection
    connection.close()


def response(sequence="1", code="0570502563", answer="已收到", reason="", cycle="2026-09"):
    return {
        "费用周期": cycle,
        "太古客户编号": code,
        "太古客户名称": "佳源食品商行",
        "是否收到本期全部协议费用": answer,
        "未收到原因": reason,
        "补充说明": "",
        "答卷手机号": "13800000000",
        "提交时间": "2026-10-09 16:15:00",
        "问卷星原始序号": sequence,
    }


def test_import_survey_responses_maps_answers_and_keeps_outside_list_rows(db):
    result = import_survey_responses(
        db,
        "2026-09",
        "survey.xlsx",
        "hash-1",
        [
            response("1", answer="已收到"),
            response("2", answer="尚未收到", reason="尚未到账"),
            response("3", code="0570502999", answer="已收到"),
        ],
        "2026-10-11 12:00:00",
    )

    assert (result.row_count, result.matched_count, result.unmatched_count, result.invalid_count) == (3, 2, 1, 0)
    assert [tuple(row) for row in db.execute(
        "SELECT received_answer, match_status FROM survey_response ORDER BY survey_response_id"
    )] == [
        ("received", "matched"),
        ("not_received", "matched"),
        ("received", "not_in_recipient_list"),
    ]


def test_import_survey_responses_preserves_invalid_business_rows(db):
    result = import_survey_responses(
        db,
        "2026-09",
        "invalid.xlsx",
        "hash-invalid",
        [
            response("1", answer="尚未收到", reason=""),
            response("2", cycle="2026-08"),
            response("3", answer="不确定"),
        ],
        "2026-10-11 12:00:00",
    )

    assert result.invalid_count == 3
    rows = db.execute(
        "SELECT match_status, match_reason FROM survey_response ORDER BY survey_response_id"
    ).fetchall()
    assert all(row["match_status"] == "invalid" for row in rows)
    assert "未收到原因" in rows[0]["match_reason"]
    assert "费用周期" in rows[1]["match_reason"]
    assert "答案" in rows[2]["match_reason"]


def test_import_survey_responses_rejects_duplicate_file_hash_without_new_batch(db):
    import_survey_responses(
        db, "2026-09", "survey.xlsx", "same-hash", [response()], "2026-10-11 12:00:00"
    )

    with pytest.raises(SurveyValidationError, match="重复导入"):
        import_survey_responses(
            db, "2026-09", "copy.xlsx", "same-hash", [response("2")], "2026-10-11 12:01:00"
        )

    assert db.execute("SELECT COUNT(*) FROM survey_import_batch").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM survey_response").fetchone()[0] == 1


def test_import_survey_responses_rejects_duplicate_fingerprint_atomically(db):
    import_survey_responses(
        db, "2026-09", "survey.xlsx", "hash-1", [response()], "2026-10-11 12:00:00"
    )

    with pytest.raises(SurveyValidationError, match="重复答卷"):
        import_survey_responses(
            db,
            "2026-09",
            "survey-2.xlsx",
            "hash-2",
            [response(), response("2", code="0570502999")],
            "2026-10-11 12:01:00",
        )

    assert db.execute("SELECT COUNT(*) FROM survey_import_batch").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM survey_response").fetchone()[0] == 1
