from __future__ import annotations

from pathlib import Path

import pytest

from ec101.db import connect_database, create_database, upgrade_database


EXPECTED_CONFIRMATION_TABLES = {
    "schema_migration",
    "master_sync_batch",
    "taikoo_customer_snapshot",
    "customer_mapping_snapshot",
    "platform_customer_identity",
    "fee_cycle",
    "fee_recipient",
    "fee_cycle_activity",
    "survey_import_batch",
    "survey_response",
}


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
} | EXPECTED_CONFIRMATION_TABLES


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


def test_create_database_builds_confirmation_schema_and_views(database_path: Path) -> None:
    create_database(database_path)
    db = connect_database(database_path)
    try:
        tables = {
            row["name"]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        views = {
            row["name"]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='view'")
        }
        assert EXPECTED_CONFIRMATION_TABLES <= tables
        assert {"v_effective_survey_response", "v_fee_confirmation_reconciliation"} <= views
    finally:
        db.close()


def test_fee_recipient_enforces_one_customer_per_cycle_and_positive_amount(
    database_path: Path,
) -> None:
    create_database(database_path)
    db = connect_database(database_path)
    try:
        cycle_id = db.execute(
            "INSERT INTO fee_cycle "
            "(fee_cycle_code, cycle_name, period_start, period_end, status, created_at) "
            "VALUES ('2026-09', '2026年9月', '2026-09-01', '2026-09-30', 'draft', '2026-10-11')"
        ).lastrowid
        db.execute(
            "INSERT INTO fee_recipient "
            "(fee_cycle_id, sap_customer_code, sap_customer_name, expected_amount, "
            "mapping_status, handoff_status, created_at) "
            "VALUES (?, '0570502563', '佳源食品商行', 500, 'pending', 'pending', '2026-10-11')",
            (cycle_id,),
        )
        with pytest.raises(Exception):
            db.execute(
                "INSERT INTO fee_recipient "
                "(fee_cycle_id, sap_customer_code, sap_customer_name, expected_amount, "
                "mapping_status, handoff_status, created_at) "
                "VALUES (?, '0570502563', '佳源食品商行', 100, 'pending', 'pending', '2026-10-11')",
                (cycle_id,),
            )
        with pytest.raises(Exception):
            db.execute(
                "INSERT INTO fee_recipient "
                "(fee_cycle_id, sap_customer_code, sap_customer_name, expected_amount, "
                "mapping_status, handoff_status, created_at) "
                "VALUES (?, '0570502564', '无效金额客户', 0, 'pending', 'pending', '2026-10-11')",
                (cycle_id,),
            )
    finally:
        db.close()


def test_survey_response_has_no_order_coupon_or_recipient_foreign_keys(
    database_path: Path,
) -> None:
    create_database(database_path)
    db = connect_database(database_path)
    try:
        columns = {row["name"] for row in db.execute("PRAGMA table_info(survey_response)")}
        forbidden = {
            "fee_recipient_id",
            "recipient_token",
            "expected_amount_snapshot",
            "order_id",
            "third_party_order_no",
            "sales_voucher_no",
            "order_amount",
            "order_case_qty",
            "coupon_no",
            "main_coupon_no",
            "sub_coupon_no",
        }
        assert columns.isdisjoint(forbidden)
        foreign_tables = {
            row["table"] for row in db.execute("PRAGMA foreign_key_list(survey_response)")
        }
        assert foreign_tables == {"survey_import_batch", "fee_cycle"}
    finally:
        db.close()


def test_upgrade_database_adds_confirmation_schema_to_existing_database_once(
    database_path: Path,
) -> None:
    db = connect_database(database_path)
    try:
        db.executescript(
            """
            CREATE TABLE import_batch (
              import_batch_id INTEGER PRIMARY KEY,
              snapshot_key TEXT NOT NULL UNIQUE,
              dealer_name TEXT NOT NULL,
              platform_name TEXT NOT NULL,
              template_version TEXT NOT NULL,
              converter_version TEXT NOT NULL,
              imported_at TEXT NOT NULL,
              status TEXT NOT NULL
            );
            CREATE TABLE dealer_platform (
              dealer_platform_id INTEGER PRIMARY KEY,
              dealer_name TEXT NOT NULL,
              platform_name TEXT NOT NULL
            );
            CREATE TABLE activity (
              activity_id INTEGER PRIMARY KEY,
              import_batch_id INTEGER NOT NULL REFERENCES import_batch(import_batch_id)
            );
            INSERT INTO dealer_platform VALUES (1, '兴路强', '兴路强平台');
            """
        )
        db.commit()
    finally:
        db.close()

    upgrade_database(database_path)
    upgrade_database(database_path)

    db = connect_database(database_path)
    try:
        assert db.execute("SELECT dealer_name FROM dealer_platform WHERE dealer_platform_id = 1").fetchone()[0] == "兴路强"
        assert db.execute(
            "SELECT COUNT(*) FROM schema_migration WHERE version = '001_fee_confirmation'"
        ).fetchone()[0] == 1
        assert db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='fee_recipient'"
        ).fetchone()[0] == 1
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
