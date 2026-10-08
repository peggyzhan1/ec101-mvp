import sqlite3

import pytest

from ec101.contract.workbook import StandardWorkbook
from ec101.importing.service import ArchiveMetadata, import_snapshot

from .conftest import full_tables, manifest


CORE_COUNTS = {
    "import_batch": 1,
    "import_file": 1,
    "import_validation_issue": 0,
    "dealer_platform": 1,
    "customer": 1,
    "product": 1,
    "order_header": 1,
    "order_line": 2,
    "activity": 1,
    "activity_rule": 1,
    "activity_benefit": 1,
    "activity_scope": 1,
    "activity_execution": 1,
    "fulfillment": 1,
    "coupon_config": 1,
    "coupon_issue_rule": 1,
    "coupon_use_rule": 1,
    "coupon_scope": 1,
    "coupon_redemption": 2,
}

RESULT_TABLES = (
    "calculation_run", "entitlement_check", "release_candidate",
    "activity_fee_summary", "coupon_fee_summary", "calculation_quality_issue",
)


def archive(number=1):
    return ArchiveMetadata(f"archives/source-{number}.zip", f"sha-{number}", 100 + number)


def test_import_maps_all_core_tables_and_leaves_result_empty(db, workbook_factory):
    result = import_snapshot(db, workbook_factory(), archive())

    assert result.status == "imported"
    assert result.import_batch_id > 0
    for table, expected in CORE_COUNTS.items():
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == expected
    assert tuple(db.execute(
        "SELECT file_path, sha256, file_size FROM import_file"
    ).fetchone()) == ("archives/source-1.zip", "sha-1", 101)
    assert db.execute("SELECT status FROM import_batch").fetchone()[0] == "imported"
    for table in RESULT_TABLES:
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_import_rolls_back_everything_on_invalid_child_row(db, workbook_factory):
    workbook = workbook_factory()
    workbook.tables["标准优惠券发放规则"].append(
        dict(workbook.tables["标准优惠券发放规则"][0])
    )

    with pytest.raises(sqlite3.IntegrityError):
        import_snapshot(db, workbook, archive())

    for table in CORE_COUNTS:
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_current_batch_switch_is_scoped_to_same_snapshot_window(db):
    snapshots = [
        (manifest("经销商甲", "平台甲", "2026-09-01", "2026-09-30"), 1),
        (manifest("经销商乙", "平台甲", "2026-09-01", "2026-09-30"), 2),
        (manifest("经销商甲", "平台甲", "2026-10-01", "2026-10-31"), 3),
        (manifest("经销商甲", "平台甲", "2026-09-01", "2026-09-30"), 4),
    ]
    batch_ids = []
    for manifest_row, number in snapshots:
        workbook = StandardWorkbook(tables={key: [] for key in full_tables()}, manifest=manifest_row)
        batch_ids.append(import_snapshot(db, workbook, archive(number)).import_batch_id)

    current = db.execute(
        "SELECT import_batch_id, dealer_name, coverage_start, is_current "
        "FROM import_batch ORDER BY import_batch_id"
    ).fetchall()
    assert [tuple(row) for row in current] == [
        (batch_ids[0], "经销商甲", "2026-09-01", 0),
        (batch_ids[1], "经销商乙", "2026-09-01", 1),
        (batch_ids[2], "经销商甲", "2026-10-01", 1),
        (batch_ids[3], "经销商甲", "2026-09-01", 1),
    ]
