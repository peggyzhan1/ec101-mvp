from __future__ import annotations

import sqlite3
from typing import Any


_CONFIRMATION_STATUSES = {
    "未提交",
    "答卷冲突",
    "已确认收到",
    "确认未收到",
    "答卷无效",
}
_EXCEPTION_KINDS = {
    "outside_list",
    "conflict",
    "unmatched_mapping",
    "ambiguous_mapping",
    "invalid_response",
}


def _page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), 500)), max(0, int(offset))


def _cycle_id(db: sqlite3.Connection, fee_cycle_code: str) -> int:
    row = db.execute(
        "SELECT fee_cycle_id FROM fee_cycle WHERE fee_cycle_code = ?", (fee_cycle_code,)
    ).fetchone()
    if row is None:
        raise LookupError(f"费用周期 {fee_cycle_code} 不存在")
    return int(row[0])


def _metric(row) -> dict[str, Any]:
    return {
        "customerCount": int(row[0]),
        "expectedAmount": round(float(row[1] or 0), 2),
    }


def get_confirmation_overview(
    db: sqlite3.Connection,
    fee_cycle_code: str,
) -> dict[str, Any]:
    fee_cycle_id = _cycle_id(db, fee_cycle_code)

    def reconciliation_metric(condition: str, params=()):
        return _metric(db.execute(
            "SELECT COUNT(*), COALESCE(SUM(expected_amount), 0) "
            "FROM v_fee_confirmation_reconciliation WHERE fee_cycle_id = ? AND " + condition,
            (fee_cycle_id, *params),
        ).fetchone())

    recipient = _metric(db.execute(
        "SELECT COUNT(*), COALESCE(SUM(expected_amount), 0) "
        "FROM fee_recipient WHERE fee_cycle_id = ?",
        (fee_cycle_id,),
    ).fetchone())
    return {
        "feeCycleCode": fee_cycle_code,
        "recipient": recipient,
        "submitted": reconciliation_metric("survey_response_id IS NOT NULL"),
        "notSubmitted": reconciliation_metric("survey_response_id IS NULL"),
        "received": reconciliation_metric("confirmation_status = ?", ("已确认收到",)),
        "notReceived": reconciliation_metric("confirmation_status = ?", ("确认未收到",)),
        "conflict": reconciliation_metric("confirmation_status = ?", ("答卷冲突",)),
        "outsideListResponseCount": db.execute(
            "SELECT COUNT(*) FROM survey_response "
            "WHERE fee_cycle_id = ? AND match_status = 'not_in_recipient_list'",
            (fee_cycle_id,),
        ).fetchone()[0],
        "unmatchedMapping": reconciliation_metric("mapping_status = 'unmatched'"),
        "ambiguousMapping": reconciliation_metric("mapping_status = 'ambiguous'"),
    }


def list_confirmation_reconciliation(
    db: sqlite3.Connection,
    fee_cycle_code: str,
    status: str | None,
    query: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    _cycle_id(db, fee_cycle_code)
    if status is not None and status not in _CONFIRMATION_STATUSES:
        raise ValueError(f"未知确认状态：{status}")
    limit, offset = _page(limit, offset)
    where = ["r.fee_cycle_code = ?"]
    params: list[Any] = [fee_cycle_code]
    if status is not None:
        where.append("r.confirmation_status = ?")
        params.append(status)
    if query:
        where.append("(r.sap_customer_code LIKE ? OR r.sap_customer_name LIKE ?)")
        params.extend((f"%{query}%", f"%{query}%"))
    condition = " AND ".join(where)
    total = db.execute(
        "SELECT COUNT(*) FROM v_fee_confirmation_reconciliation r WHERE " + condition,
        params,
    ).fetchone()[0]
    rows = db.execute(
        "SELECT r.fee_recipient_id AS feeRecipientId, r.fee_cycle_code AS feeCycleCode, "
        "r.sap_customer_code AS sapCustomerCode, r.sap_customer_name AS sapCustomerName, "
        "r.expected_amount AS expectedAmount, r.mapping_status AS mappingStatus, "
        "r.mapping_reason AS mappingReason, r.platform_customer_no AS platformCustomerNo, "
        "r.survey_response_id AS surveyResponseId, r.received_answer AS receivedAnswer, "
        "r.not_received_reason AS notReceivedReason, r.customer_comment AS customerComment, "
        "r.submitted_at AS submittedAt, r.has_conflict AS hasConflict, "
        "r.confirmation_status AS confirmationStatus, e.raw_sequence_no AS rawSequenceNo "
        "FROM v_fee_confirmation_reconciliation r "
        "LEFT JOIN v_effective_survey_response e ON e.survey_response_id = r.survey_response_id "
        "WHERE " + condition + " ORDER BY r.sap_customer_code LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    items = [dict(row) for row in rows]
    for item in items:
        item["hasConflict"] = bool(item["hasConflict"])
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def list_confirmation_exceptions(
    db: sqlite3.Connection,
    fee_cycle_code: str,
    kind: str | None,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    fee_cycle_id = _cycle_id(db, fee_cycle_code)
    if kind is not None and kind not in _EXCEPTION_KINDS:
        raise ValueError(f"未知异常类型：{kind}")
    limit, offset = _page(limit, offset)
    cte = (
        "WITH exceptions AS ("
        "SELECT 'outside_list' AS kind, sap_customer_code, sap_customer_name, NULL AS expected_amount, "
        "received_answer, submitted_at, raw_sequence_no, match_reason FROM survey_response "
        "WHERE fee_cycle_id = ? AND match_status = 'not_in_recipient_list' UNION ALL "
        "SELECT 'invalid_response', sap_customer_code, sap_customer_name, NULL, received_answer, "
        "submitted_at, raw_sequence_no, match_reason FROM survey_response "
        "WHERE fee_cycle_id = ? AND match_status = 'invalid' UNION ALL "
        "SELECT 'conflict', sap_customer_code, sap_customer_name, expected_amount, received_answer, "
        "submitted_at, NULL, '同一客户周期存在相互冲突的有效答卷' "
        "FROM v_fee_confirmation_reconciliation WHERE fee_cycle_id = ? AND has_conflict = 1 UNION ALL "
        "SELECT 'unmatched_mapping', sap_customer_code, sap_customer_name, expected_amount, NULL, "
        "NULL, NULL, mapping_reason FROM fee_recipient "
        "WHERE fee_cycle_id = ? AND mapping_status = 'unmatched' UNION ALL "
        "SELECT 'ambiguous_mapping', sap_customer_code, sap_customer_name, expected_amount, NULL, "
        "NULL, NULL, mapping_reason FROM fee_recipient "
        "WHERE fee_cycle_id = ? AND mapping_status = 'ambiguous') "
    )
    params: list[Any] = [fee_cycle_id] * 5
    where = "WHERE kind = ?" if kind is not None else ""
    if kind is not None:
        params.append(kind)
    total = db.execute(cte + f"SELECT COUNT(*) FROM exceptions {where}", params).fetchone()[0]
    rows = db.execute(
        cte
        + "SELECT kind, sap_customer_code AS sapCustomerCode, "
        "sap_customer_name AS sapCustomerName, expected_amount AS expectedAmount, "
        "received_answer AS receivedAnswer, submitted_at AS submittedAt, "
        "raw_sequence_no AS rawSequenceNo, match_reason AS matchReason "
        f"FROM exceptions {where} ORDER BY kind, sap_customer_code, raw_sequence_no "
        "LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    items = [dict(row) for row in rows]
    for item in items:
        if item["expectedAmount"] is not None:
            item["expectedAmount"] = round(float(item["expectedAmount"]), 2)
    return {"items": items, "total": total, "limit": limit, "offset": offset}
