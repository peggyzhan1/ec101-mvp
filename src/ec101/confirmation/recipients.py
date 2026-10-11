from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import sqlite3
import re
from typing import Any, Mapping, Sequence

from .workbook import (
    FeeRecipientValidationError,
    normalize_customer_code,
    parse_positive_amount,
)


@dataclass(frozen=True)
class FeeCycleInput:
    fee_cycle_code: str
    cycle_name: str
    period_start: str
    period_end: str


@dataclass(frozen=True)
class FeeRecipientImportResult:
    fee_cycle_id: int
    input_row_count: int
    recipient_count: int
    matched_count: int
    unmatched_count: int
    ambiguous_count: int


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    return "" if value is None else str(value).strip()


def _validate_cycle(cycle: FeeCycleInput) -> None:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", cycle.fee_cycle_code):
        raise FeeRecipientValidationError("费用周期必须为 YYYY-MM")
    if not cycle.cycle_name.strip():
        raise FeeRecipientValidationError("周期名称不能为空")
    try:
        period_start = datetime.strptime(cycle.period_start, "%Y-%m-%d").date()
        period_end = datetime.strptime(cycle.period_end, "%Y-%m-%d").date()
    except ValueError as exc:
        raise FeeRecipientValidationError("周期开始和结束日期必须为 YYYY-MM-DD") from exc
    if period_start > period_end:
        raise FeeRecipientValidationError("周期开始日期不能晚于结束日期")
    if (
        period_start.strftime("%Y-%m") != cycle.fee_cycle_code
        or period_end.strftime("%Y-%m") != cycle.fee_cycle_code
    ):
        raise FeeRecipientValidationError("周期开始和结束日期必须属于费用周期")


def _validated_groups(
    cycle: FeeCycleInput,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not rows:
        raise FeeRecipientValidationError("应发名单不能为空")
    groups: dict[str, dict[str, Any]] = {}
    for row_number, row in enumerate(rows, start=2):
        row_cycle = _text(row, "费用周期")
        if row_cycle != cycle.fee_cycle_code:
            raise FeeRecipientValidationError(
                f"第 {row_number} 行费用周期 {row_cycle or '为空'} 与指定周期 {cycle.fee_cycle_code} 不一致"
            )
        try:
            code = normalize_customer_code(row.get("太古客户编号"))
            amount = parse_positive_amount(row.get("应发金额"))
        except FeeRecipientValidationError as exc:
            raise FeeRecipientValidationError(f"第 {row_number} 行：{exc}") from exc
        name = _text(row, "太古客户名称")
        if not name:
            raise FeeRecipientValidationError(f"第 {row_number} 行：太古客户名称不能为空")
        group = groups.setdefault(code, {
            "sap_customer_name": name,
            "expected_amount": Decimal("0.00"),
            "source_row_no": row_number,
            "remarks": [],
        })
        group["expected_amount"] += amount
        remark = _text(row, "备注")
        if remark and remark not in group["remarks"]:
            group["remarks"].append(remark)
    return groups


def _mapping_for(
    db: sqlite3.Connection,
    master_sync_batch_id: int,
    sap_customer_code: str,
) -> dict[str, Any]:
    rows = db.execute(
        "SELECT cms.customer_mapping_snapshot_id, cms.dealer_platform_id, "
        "cms.source_customer_code, pci.platform_customer_identity_id "
        "FROM customer_mapping_snapshot cms "
        "JOIN platform_customer_identity pci "
        "  ON pci.dealer_platform_id = cms.dealer_platform_id "
        " AND pci.platform_customer_no = cms.source_customer_code "
        "WHERE cms.master_sync_batch_id = ? AND cms.sap_customer_code = ? "
        "AND cms.match_status IN ('匹配成功', '已确认') "
        "AND cms.sap_customer_code IS NOT NULL AND cms.sap_customer_code <> '' "
        "AND cms.source_customer_code IS NOT NULL AND cms.source_customer_code <> ''",
        (master_sync_batch_id, sap_customer_code),
    ).fetchall()
    targets: dict[tuple[int, int, str], int] = {}
    for row in rows:
        key = (int(row["dealer_platform_id"]), int(row["platform_customer_identity_id"]), row["source_customer_code"])
        targets.setdefault(key, int(row["customer_mapping_snapshot_id"]))
    if not targets:
        return {
            "status": "unmatched",
            "reason": "当前客资快照中没有唯一可用且已出现于平台数据的映射",
        }
    if len(targets) > 1:
        return {
            "status": "ambiguous",
            "reason": f"当前客资快照中存在 {len(targets)} 个不同的平台客户目标",
        }
    (dealer_platform_id, identity_id, platform_no), snapshot_id = next(iter(targets.items()))
    return {
        "status": "matched",
        "reason": None,
        "dealer_platform_id": dealer_platform_id,
        "platform_customer_identity_id": identity_id,
        "platform_customer_no": platform_no,
        "mapping_snapshot_id": snapshot_id,
    }


def import_fee_recipients(
    db: sqlite3.Connection,
    cycle: FeeCycleInput,
    rows: Sequence[Mapping[str, Any]],
    master_sync_batch_id: int,
    imported_at: str | None = None,
) -> FeeRecipientImportResult:
    timestamp = imported_at or datetime.now().isoformat(timespec="seconds")
    _validate_cycle(cycle)
    if db.execute(
        "SELECT 1 FROM fee_cycle WHERE fee_cycle_code = ?", (cycle.fee_cycle_code,)
    ).fetchone():
        raise FeeRecipientValidationError(f"费用周期 {cycle.fee_cycle_code} 已存在，不能重复导入")
    batch = db.execute(
        "SELECT status FROM master_sync_batch WHERE master_sync_batch_id = ?",
        (master_sync_batch_id,),
    ).fetchone()
    if batch is None or batch["status"] != "success":
        raise FeeRecipientValidationError("指定的客资同步批次不存在或未成功")
    groups = _validated_groups(cycle, rows)

    counts = {"matched": 0, "unmatched": 0, "ambiguous": 0}
    with db:
        cursor = db.execute(
            "INSERT INTO fee_cycle "
            "(fee_cycle_code, cycle_name, period_start, period_end, status, created_at) "
            "VALUES (?, ?, ?, ?, 'imported', ?)",
            (cycle.fee_cycle_code, cycle.cycle_name, cycle.period_start, cycle.period_end, timestamp),
        )
        fee_cycle_id = int(cursor.lastrowid)
        for code, group in groups.items():
            mapped = _mapping_for(db, master_sync_batch_id, code)
            counts[mapped["status"]] += 1
            db.execute(
                "INSERT INTO fee_recipient "
                "(fee_cycle_id, sap_customer_code, sap_customer_name, expected_amount, "
                "dealer_platform_id, platform_customer_identity_id, platform_customer_no, "
                "mapping_snapshot_id, mapping_status, mapping_reason, handoff_status, "
                "source_row_no, remark, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
                (
                    fee_cycle_id,
                    code,
                    group["sap_customer_name"],
                    format(group["expected_amount"], ".2f"),
                    mapped.get("dealer_platform_id"),
                    mapped.get("platform_customer_identity_id"),
                    mapped.get("platform_customer_no"),
                    mapped.get("mapping_snapshot_id"),
                    mapped["status"],
                    mapped["reason"],
                    group["source_row_no"],
                    "；".join(group["remarks"]) or None,
                    timestamp,
                ),
            )
    return FeeRecipientImportResult(
        fee_cycle_id,
        len(rows),
        len(groups),
        counts["matched"],
        counts["unmatched"],
        counts["ambiguous"],
    )


def replace_fee_cycle_activities(
    db: sqlite3.Connection,
    fee_cycle_id: int,
    activity_ids: Sequence[int],
    created_at: str | None = None,
) -> None:
    unique_ids = list(dict.fromkeys(int(value) for value in activity_ids))
    timestamp = created_at or datetime.now().isoformat(timespec="seconds")
    resolved = {}
    if unique_ids:
        placeholders = ",".join("?" for _ in unique_ids)
        rows = db.execute(
            "SELECT a.activity_id, dp.dealer_platform_id "
            "FROM activity a "
            "JOIN import_batch ib ON ib.import_batch_id = a.import_batch_id "
            "JOIN dealer_platform dp ON dp.dealer_name = ib.dealer_name "
            " AND dp.platform_name = ib.platform_name "
            f"WHERE a.activity_id IN ({placeholders})",
            unique_ids,
        ).fetchall()
        resolved = {int(row["activity_id"]): int(row["dealer_platform_id"]) for row in rows}
    missing = [activity_id for activity_id in unique_ids if activity_id not in resolved]
    if missing:
        raise FeeRecipientValidationError(f"活动不存在或缺少经销商平台：{missing[0]}")
    if db.execute(
        "SELECT 1 FROM fee_cycle WHERE fee_cycle_id = ?", (fee_cycle_id,)
    ).fetchone() is None:
        raise FeeRecipientValidationError(f"费用周期不存在：{fee_cycle_id}")
    with db:
        db.execute("DELETE FROM fee_cycle_activity WHERE fee_cycle_id = ?", (fee_cycle_id,))
        for activity_id in unique_ids:
            db.execute(
                "INSERT INTO fee_cycle_activity "
                "(fee_cycle_id, activity_id, dealer_platform_id, created_at) VALUES (?, ?, ?, ?)",
                (fee_cycle_id, activity_id, resolved[activity_id], timestamp),
            )
