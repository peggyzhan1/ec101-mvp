from __future__ import annotations

from pathlib import Path

import pytest

from ec101.db import connect_database, create_database


EXPECTED_TABLES = {
    "import_batch",
    "import_file",
    "import_validation_issue",
    "dealer_platform",
    "customer",
    "product",
    "order_header",
    "order_line",
    "activity",
    "activity_rule",
    "activity_benefit",
    "activity_scope",
    "activity_execution",
    "fulfillment",
    "coupon_config",
    "coupon_issue_rule",
    "coupon_use_rule",
    "coupon_scope",
    "coupon_redemption",
    "calculation_run",
    "entitlement_check",
    "release_candidate",
    "activity_fee_summary",
    "coupon_fee_summary",
    "calculation_quality_issue",
}


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "ec101.db"


def test_create_database_builds_current_standard_schema(database_path: Path) -> None:
    create_database(database_path)
    db = connect_database(database_path)
    try:
        tables = {
            row["name"]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert tables == EXPECTED_TABLES

        indexes = {
            row["name"]
            for row in db.execute("PRAGMA index_list(import_batch)")
        }
        assert indexes
        with pytest.raises(Exception):
            db.execute(
                "INSERT INTO import_batch(snapshot_key,dealer_name,platform_name,template_version,converter_version,imported_at,status) "
                "VALUES('same','d','p','v1','v1','2026-10-08','imported')"
            )
            db.execute(
                "INSERT INTO import_batch(snapshot_key,dealer_name,platform_name,template_version,converter_version,imported_at,status) "
                "VALUES('same','d','p','v1','v1','2026-10-08','imported')"
            )
    finally:
        db.close()


def test_foreign_keys_are_enabled(database_path: Path) -> None:
    create_database(database_path)
    db = connect_database(database_path)
    try:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(Exception):
            db.execute(
                "INSERT INTO import_file(import_batch_id,file_role,file_path,sha256,file_size) "
                "VALUES(999,'sources','sources.zip','hash',1)"
            )
    finally:
        db.close()


def test_coupon_summary_accepts_null_config(database_path: Path) -> None:
    create_database(database_path)
    db = connect_database(database_path)
    try:
        columns = {
            row["name"]: row
            for row in db.execute("PRAGMA table_info(coupon_fee_summary)")
        }
        assert columns["coupon_config_id"]["notnull"] == 0
    finally:
        db.close()


def test_runtime_artifacts_are_ignored() -> None:
    ignore = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    for pattern in (
        "*.db",
        "*.db.bak-*",
        "sources.zip",
        "archives/",
        "*.xls",
        "*.xlsx",
        "!tests/fixtures/**/*.xls",
        "!tests/fixtures/**/*.xlsx",
        "web/node_modules/",
        "web/dist/",
        "__pycache__/",
    ):
        assert pattern in ignore
