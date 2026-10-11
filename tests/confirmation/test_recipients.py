from decimal import Decimal

import pytest

from ec101.confirmation.master_data import (
    sync_master_data,
    upsert_platform_customer_identity,
)
from ec101.confirmation.recipients import (
    FeeCycleInput,
    FeeRecipientValidationError,
    import_fee_recipients,
    replace_fee_cycle_activities,
)
from ec101.db import connect_database, create_database


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "recipients.db"
    create_database(path)
    connection = connect_database(path)
    yield connection
    connection.close()


def cycle():
    return FeeCycleInput("2026-09", "2026年9月", "2026-09-01", "2026-09-30")


def recipient_row(amount="500.00", code="0570502563", name="佳源食品商行"):
    return {
        "费用周期": "2026-09",
        "太古客户编号": code,
        "太古客户名称": name,
        "应发金额": amount,
        "备注": "协议费用",
    }


def add_platform(db):
    platform_id = db.execute(
        "INSERT INTO dealer_platform (dealer_name, platform_name) VALUES ('兴路强', '兴路强平台')"
    ).lastrowid
    return int(platform_id)


def sync_mapping(db, platform_id, mapping_rows):
    return sync_master_data(
        db,
        "areapartner",
        [{
            "sap_customer_primary_key": "sap-pk-1",
            "sap_customer_code": "0570502563",
            "sap_customer_name": "佳源食品商行",
        }],
        mapping_rows,
        "2026-10-11 10:00:00",
    )


def mapping(platform_id, source_code="00081", source_mapping_id="mapping-1", status="匹配成功"):
    return {
        "source_mapping_id": source_mapping_id,
        "dealer_platform_id": platform_id,
        "source_customer_code": source_code,
        "source_customer_name": "佳源食品商行",
        "sap_customer_code": "0570502563",
        "sap_customer_name": "佳源食品商行",
        "match_status": status,
    }


def test_import_fee_recipients_aggregates_rows_and_uses_unique_valid_mapping(db):
    platform_id = add_platform(db)
    identity_id = upsert_platform_customer_identity(
        db, platform_id, "00081", "佳源食品商行", "2026-10-01 09:00:00"
    )
    sync = sync_mapping(db, platform_id, [mapping(platform_id)])

    result = import_fee_recipients(
        db,
        cycle(),
        [recipient_row("200.00"), recipient_row("300.00")],
        sync.master_sync_batch_id,
        "2026-10-11 11:00:00",
    )

    assert (result.input_row_count, result.recipient_count, result.matched_count) == (2, 1, 1)
    row = db.execute(
        "SELECT expected_amount, mapping_status, dealer_platform_id, "
        "platform_customer_identity_id, platform_customer_no FROM fee_recipient"
    ).fetchone()
    assert Decimal(str(row["expected_amount"])) == Decimal("500.00")
    assert tuple(row)[1:] == ("matched", platform_id, identity_id, "00081")


def test_import_fee_recipients_marks_missing_mapping_without_name_fallback(db):
    platform_id = add_platform(db)
    upsert_platform_customer_identity(
        db, platform_id, "00081", "佳源食品商行", "2026-10-01 09:00:00"
    )
    sync = sync_mapping(db, platform_id, [])

    result = import_fee_recipients(
        db, cycle(), [recipient_row()], sync.master_sync_batch_id, "2026-10-11 11:00:00"
    )

    assert result.unmatched_count == 1
    assert tuple(db.execute(
        "SELECT mapping_status, dealer_platform_id, platform_customer_identity_id, platform_customer_no "
        "FROM fee_recipient"
    ).fetchone()) == ("unmatched", None, None, None)


def test_import_fee_recipients_marks_different_valid_targets_ambiguous(db):
    platform_id = add_platform(db)
    upsert_platform_customer_identity(db, platform_id, "00081", "客户甲", "2026-10-01")
    upsert_platform_customer_identity(db, platform_id, "00082", "客户乙", "2026-10-01")
    sync = sync_mapping(db, platform_id, [
        mapping(platform_id, "00081", "mapping-1"),
        mapping(platform_id, "00082", "mapping-2", status="已确认"),
    ])

    result = import_fee_recipients(
        db, cycle(), [recipient_row()], sync.master_sync_batch_id, "2026-10-11 11:00:00"
    )

    assert result.ambiguous_count == 1
    assert tuple(db.execute(
        "SELECT mapping_status, dealer_platform_id, platform_customer_identity_id, "
        "platform_customer_no, mapping_snapshot_id FROM fee_recipient"
    ).fetchone()) == ("ambiguous", None, None, None, None)


def test_import_fee_recipients_rejects_duplicate_cycle_without_overwrite(db):
    platform_id = add_platform(db)
    sync = sync_mapping(db, platform_id, [])
    import_fee_recipients(
        db, cycle(), [recipient_row("500.00")], sync.master_sync_batch_id, "2026-10-11"
    )

    with pytest.raises(FeeRecipientValidationError, match="已存在"):
        import_fee_recipients(
            db, cycle(), [recipient_row("999.00")], sync.master_sync_batch_id, "2026-10-12"
        )

    amount = db.execute("SELECT expected_amount FROM fee_recipient").fetchone()[0]
    assert Decimal(str(amount)) == Decimal("500.00")


def test_replace_fee_cycle_activities_deduplicates_and_rejects_unknown_activity(db):
    platform_id = add_platform(db)
    batch_id = db.execute(
        "INSERT INTO import_batch "
        "(snapshot_key, dealer_name, platform_name, template_version, converter_version, imported_at, status) "
        "VALUES ('snapshot', '兴路强', '兴路强平台', '1', '1', '2026-10-11', 'imported')"
    ).lastrowid
    activity_id = db.execute(
        "INSERT INTO activity "
        "(import_batch_id, activity_no, activity_name, activity_type) "
        "VALUES (?, 'A1', '协议费用', '满减')",
        (batch_id,),
    ).lastrowid
    cycle_id = db.execute(
        "INSERT INTO fee_cycle "
        "(fee_cycle_code, cycle_name, period_start, period_end, status, created_at) "
        "VALUES ('2026-09', '2026年9月', '2026-09-01', '2026-09-30', 'imported', '2026-10-11')"
    ).lastrowid

    replace_fee_cycle_activities(db, int(cycle_id), [int(activity_id), int(activity_id)])

    assert tuple(db.execute(
        "SELECT activity_id, dealer_platform_id FROM fee_cycle_activity"
    ).fetchone()) == (activity_id, platform_id)
    with pytest.raises(FeeRecipientValidationError, match="不存在"):
        replace_fee_cycle_activities(db, int(cycle_id), [999])


@pytest.mark.parametrize(
    "invalid_cycle",
    [
        FeeCycleInput("2026-9", "九月", "2026-09-01", "2026-09-30"),
        FeeCycleInput("2026-09", "九月", "2026-09-30", "2026-09-01"),
        FeeCycleInput("2026-09", "九月", "2026-08-01", "2026-09-30"),
        FeeCycleInput("2026-09", "九月", "bad-date", "2026-09-30"),
    ],
)
def test_import_fee_recipients_rejects_invalid_or_incoherent_cycle(db, invalid_cycle):
    platform_id = add_platform(db)
    sync = sync_mapping(db, platform_id, [])
    row = recipient_row()
    row["费用周期"] = invalid_cycle.fee_cycle_code

    with pytest.raises(FeeRecipientValidationError, match="周期"):
        import_fee_recipients(
            db, invalid_cycle, [row], sync.master_sync_batch_id, "2026-10-11"
        )
