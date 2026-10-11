from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import sqlite3
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class MasterSyncResult:
    master_sync_batch_id: int
    customer_count: int
    mapping_count: int


class MasterDataValidationError(ValueError):
    pass


_CUSTOMER_COLUMNS = (
    "sap_customer_primary_key",
    "sap_customer_code",
    "sap_customer_name",
    "region_code",
    "region_name",
    "sales_office_code",
    "office_name",
    "presale_route",
    "storefront_address",
    "ship_to_address",
    "contact_name",
    "phone_no",
    "mobile_no",
    "channel_group",
    "sub_channel_code",
    "customer_status",
    "partner_code",
    "partner_name",
    "self_sale_flag",
    "source_imported_at",
)

_MAPPING_COLUMNS = (
    "source_mapping_id",
    "area_partner_dealer_id",
    "dealer_platform_id",
    "source_customer_primary_key",
    "source_customer_code",
    "source_customer_name",
    "sap_customer_primary_key",
    "sap_customer_code",
    "sap_customer_name",
    "match_status",
    "hit_field",
    "mapping_source",
    "manual_override",
    "confirmed_at",
    "source_last_seen_at",
)


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    return "" if value is None else str(value).strip()


def _nullable(row: Mapping[str, Any], key: str) -> str | None:
    value = _text(row, key)
    return value or None


def _validate(customers: Sequence[Mapping[str, Any]], mappings: Sequence[Mapping[str, Any]]) -> None:
    issues = []
    for index, row in enumerate(customers, start=1):
        for key in ("sap_customer_primary_key", "sap_customer_code", "sap_customer_name"):
            if not _text(row, key):
                issues.append(f"太古客资第 {index} 行缺少 {key}")
    for index, row in enumerate(mappings, start=1):
        for key in ("source_mapping_id", "source_customer_code", "sap_customer_code", "match_status"):
            if not _text(row, key):
                issues.append(f"客资映射第 {index} 行缺少 {key}")
    if issues:
        raise MasterDataValidationError("；".join(issues))


def _record_failed_batch(
    db: sqlite3.Connection,
    source_database: str,
    synced_at: str,
    message: str,
) -> None:
    with db:
        db.execute(
            "INSERT INTO master_sync_batch "
            "(source_system, source_database, started_at, completed_at, status, error_message) "
            "VALUES ('数采通', ?, ?, ?, 'failed', ?)",
            (source_database, synced_at, synced_at, message),
        )


def sync_master_data(
    db: sqlite3.Connection,
    source_database: str,
    customers: Sequence[Mapping[str, Any]],
    mappings: Sequence[Mapping[str, Any]],
    synced_at: str | None = None,
) -> MasterSyncResult:
    timestamp = synced_at or datetime.now().isoformat(timespec="seconds")
    try:
        _validate(customers, mappings)
    except MasterDataValidationError as exc:
        _record_failed_batch(db, source_database, timestamp, str(exc))
        raise

    with db:
        cursor = db.execute(
            "INSERT INTO master_sync_batch "
            "(source_system, source_database, started_at, status) "
            "VALUES ('数采通', ?, ?, 'running')",
            (source_database, timestamp),
        )
        batch_id = int(cursor.lastrowid)
        for row in customers:
            values = [
                _text(row, key) if key in {
                    "sap_customer_primary_key", "sap_customer_code", "sap_customer_name"
                } else _nullable(row, key)
                for key in _CUSTOMER_COLUMNS
            ]
            db.execute(
                "INSERT INTO taikoo_customer_snapshot "
                f"(master_sync_batch_id, {', '.join(_CUSTOMER_COLUMNS)}) "
                f"VALUES (?, {', '.join('?' for _ in _CUSTOMER_COLUMNS)})",
                (batch_id, *values),
            )
        for row in mappings:
            values = []
            for key in _MAPPING_COLUMNS:
                if key == "manual_override":
                    values.append(1 if row.get(key) in (True, 1, "1", "true", "True", "是") else 0)
                elif key == "dealer_platform_id":
                    values.append(row.get(key))
                elif key in {"source_mapping_id", "source_customer_code", "sap_customer_code", "match_status"}:
                    values.append(_text(row, key))
                else:
                    values.append(_nullable(row, key))
            db.execute(
                "INSERT INTO customer_mapping_snapshot "
                f"(master_sync_batch_id, {', '.join(_MAPPING_COLUMNS)}) "
                f"VALUES (?, {', '.join('?' for _ in _MAPPING_COLUMNS)})",
                (batch_id, *values),
            )
        db.execute(
            "UPDATE master_sync_batch SET completed_at = ?, status = 'success', "
            "customer_count = ?, mapping_count = ? WHERE master_sync_batch_id = ?",
            (timestamp, len(customers), len(mappings), batch_id),
        )
    return MasterSyncResult(batch_id, len(customers), len(mappings))


def upsert_platform_customer_identity(
    db: sqlite3.Connection,
    dealer_platform_id: int,
    platform_customer_no: str,
    customer_name: str | None,
    seen_at: str,
) -> int:
    customer_no = str(platform_customer_no).strip()
    if not customer_no:
        raise ValueError("第三方客户编号不能为空")
    name = None if customer_name is None else str(customer_name).strip() or None
    db.execute(
        "INSERT INTO platform_customer_identity "
        "(dealer_platform_id, platform_customer_no, latest_customer_name, first_seen_at, last_seen_at, status) "
        "VALUES (?, ?, ?, ?, ?, 'active') "
        "ON CONFLICT(dealer_platform_id, platform_customer_no) DO UPDATE SET "
        "latest_customer_name = excluded.latest_customer_name, "
        "last_seen_at = excluded.last_seen_at, status = 'active'",
        (dealer_platform_id, customer_no, name, seen_at, seen_at),
    )
    row = db.execute(
        "SELECT platform_customer_identity_id FROM platform_customer_identity "
        "WHERE dealer_platform_id = ? AND platform_customer_no = ?",
        (dealer_platform_id, customer_no),
    ).fetchone()
    return int(row[0])
