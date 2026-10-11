import pytest

from ec101.confirmation.master_data import (
    MasterDataValidationError,
    sync_master_data,
    upsert_platform_customer_identity,
)
from ec101.db import connect_database, create_database


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "confirmation.db"
    create_database(path)
    connection = connect_database(path)
    yield connection
    connection.close()


def customer(**overrides):
    row = {
        "sap_customer_primary_key": "sap-pk-1",
        "sap_customer_code": "0570502563",
        "sap_customer_name": "佳源食品商行",
        "sales_office_code": "0010",
        "presale_route": "0007",
        "partner_code": "000012",
    }
    row.update(overrides)
    return row


def mapping(dealer_platform_id, **overrides):
    row = {
        "source_mapping_id": "mapping-1",
        "area_partner_dealer_id": "dealer-1",
        "dealer_platform_id": dealer_platform_id,
        "source_customer_primary_key": "source-pk-1",
        "source_customer_code": "00081",
        "source_customer_name": "佳源食品商行",
        "sap_customer_primary_key": "sap-pk-1",
        "sap_customer_code": "0570502563",
        "sap_customer_name": "佳源食品商行",
        "match_status": "匹配成功",
        "manual_override": False,
    }
    row.update(overrides)
    return row


def dealer_platform(db):
    return db.execute(
        "INSERT INTO dealer_platform (dealer_name, platform_name) VALUES ('兴路强', '兴路强平台')"
    ).lastrowid


def test_sync_master_data_writes_successful_snapshot_and_preserves_leading_zeroes(db):
    platform_id = dealer_platform(db)

    result = sync_master_data(
        db,
        "areapartner",
        [customer()],
        [mapping(platform_id)],
        synced_at="2026-10-11 10:00:00",
    )

    assert result.customer_count == 1
    assert result.mapping_count == 1
    assert tuple(db.execute(
        "SELECT source_system, source_database, status, customer_count, mapping_count "
        "FROM master_sync_batch WHERE master_sync_batch_id = ?",
        (result.master_sync_batch_id,),
    ).fetchone()) == ("数采通", "areapartner", "success", 1, 1)
    assert tuple(db.execute(
        "SELECT sap_customer_code, sales_office_code, presale_route, partner_code "
        "FROM taikoo_customer_snapshot"
    ).fetchone()) == ("0570502563", "0010", "0007", "000012")
    assert tuple(db.execute(
        "SELECT source_customer_code, sap_customer_code FROM customer_mapping_snapshot"
    ).fetchone()) == ("00081", "0570502563")


@pytest.mark.parametrize(
    ("customers", "mappings"),
    [
        ([customer(sap_customer_primary_key="")], []),
        ([customer(sap_customer_code="")], []),
        ([customer()], [mapping(1, source_mapping_id="")]),
        ([customer()], [mapping(1, source_customer_code="")]),
    ],
)
def test_sync_master_data_rejects_invalid_rows_without_partial_snapshots(
    db, customers, mappings
):
    dealer_platform(db)

    with pytest.raises(MasterDataValidationError):
        sync_master_data(
            db, "areapartner", customers, mappings, synced_at="2026-10-11 10:00:00"
        )

    assert db.execute("SELECT COUNT(*) FROM taikoo_customer_snapshot").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM customer_mapping_snapshot").fetchone()[0] == 0
    assert tuple(db.execute(
        "SELECT status, customer_count, mapping_count FROM master_sync_batch"
    ).fetchone()) == ("failed", 0, 0)


def test_upsert_platform_customer_identity_updates_one_stable_identity(db):
    platform_id = dealer_platform(db)

    first_id = upsert_platform_customer_identity(
        db, platform_id, "00081", "旧名称", "2026-09-01 09:00:00"
    )
    second_id = upsert_platform_customer_identity(
        db, platform_id, "00081", "新名称", "2026-10-01 09:00:00"
    )

    assert first_id == second_id
    assert tuple(db.execute(
        "SELECT platform_customer_no, latest_customer_name, first_seen_at, last_seen_at "
        "FROM platform_customer_identity"
    ).fetchone()) == ("00081", "新名称", "2026-09-01 09:00:00", "2026-10-01 09:00:00")
