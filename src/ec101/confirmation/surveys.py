from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import sqlite3
from typing import Any, Mapping, Sequence

from .workbook import SurveyValidationError


@dataclass(frozen=True)
class SurveyImportResult:
    survey_import_batch_id: int
    row_count: int
    matched_count: int
    unmatched_count: int
    invalid_count: int


_ANSWERS = {
    "已收到": "received",
    "received": "received",
    "尚未收到": "not_received",
    "未收到": "not_received",
    "not_received": "not_received",
}


def _text(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    return "" if value is None else str(value).strip()


def _prepared_response(
    db: sqlite3.Connection,
    fee_cycle_id: int,
    fee_cycle_code: str,
    row: Mapping[str, Any],
    row_number: int,
    imported_at: str,
) -> dict[str, Any]:
    row_cycle = _text(row, "费用周期")
    customer_code = _text(row, "太古客户编号")
    answer_text = _text(row, "是否收到本期全部协议费用")
    answer = _ANSWERS.get(answer_text)
    reason = None
    if row_cycle != fee_cycle_code:
        reason = f"费用周期 {row_cycle or '为空'} 与指定周期 {fee_cycle_code} 不一致"
    elif not customer_code:
        reason = "太古客户编号为空"
    elif answer is None:
        reason = f"答案无效：{answer_text or '为空'}"
    elif answer == "not_received" and not _text(row, "未收到原因"):
        reason = "选择尚未收到时必须填写未收到原因"
    submitted_at = _text(row, "提交时间")
    if reason is None and not submitted_at:
        reason = "提交时间为空"
    raw_sequence_no = _text(row, "问卷星原始序号") or f"__missing__{row_number}"

    if reason is not None:
        match_status = "invalid"
    else:
        recipient = db.execute(
            "SELECT 1 FROM fee_recipient WHERE fee_cycle_id = ? AND sap_customer_code = ?",
            (fee_cycle_id, customer_code),
        ).fetchone()
        match_status = "matched" if recipient is not None else "not_in_recipient_list"
        if recipient is None:
            reason = "该客户不在本费用周期应发名单中"

    fingerprint_source = "|".join((
        fee_cycle_code,
        raw_sequence_no,
        customer_code,
        submitted_at,
        answer or "",
    ))
    return {
        "fee_cycle_id": fee_cycle_id,
        "sap_customer_code": customer_code or None,
        "sap_customer_name": _text(row, "太古客户名称") or None,
        "received_answer": answer,
        "not_received_reason": _text(row, "未收到原因") or None,
        "customer_comment": _text(row, "补充说明") or None,
        "respondent_mobile": _text(row, "答卷手机号") or None,
        "submitted_at": submitted_at or None,
        "raw_sequence_no": raw_sequence_no,
        "match_status": match_status,
        "match_reason": reason,
        "response_fingerprint": sha256(fingerprint_source.encode("utf-8")).hexdigest(),
        "imported_at": imported_at,
    }


def import_survey_responses(
    db: sqlite3.Connection,
    fee_cycle_code: str,
    source_file_name: str,
    source_file_sha256: str,
    rows: Sequence[Mapping[str, Any]],
    imported_at: str | None = None,
) -> SurveyImportResult:
    timestamp = imported_at or datetime.now().isoformat(timespec="seconds")
    cycle = db.execute(
        "SELECT fee_cycle_id FROM fee_cycle WHERE fee_cycle_code = ?", (fee_cycle_code,)
    ).fetchone()
    if cycle is None:
        raise SurveyValidationError(f"费用周期 {fee_cycle_code} 不存在")
    fee_cycle_id = int(cycle["fee_cycle_id"])
    if not source_file_sha256.strip():
        raise SurveyValidationError("问卷文件 SHA-256 不能为空")
    if db.execute(
        "SELECT 1 FROM survey_import_batch WHERE fee_cycle_id = ? AND source_file_sha256 = ?",
        (fee_cycle_id, source_file_sha256),
    ).fetchone():
        raise SurveyValidationError("同一费用周期的问卷文件已重复导入")

    prepared = [
        _prepared_response(db, fee_cycle_id, fee_cycle_code, row, index, timestamp)
        for index, row in enumerate(rows, start=2)
    ]
    fingerprints = [row["response_fingerprint"] for row in prepared]
    if len(fingerprints) != len(set(fingerprints)):
        raise SurveyValidationError("导入文件中包含重复答卷")
    if fingerprints:
        placeholders = ",".join("?" for _ in fingerprints)
        if db.execute(
            f"SELECT 1 FROM survey_response WHERE response_fingerprint IN ({placeholders}) LIMIT 1",
            fingerprints,
        ).fetchone():
            raise SurveyValidationError("问卷文件包含已经导入的重复答卷")

    matched_count = sum(row["match_status"] == "matched" for row in prepared)
    unmatched_count = sum(row["match_status"] == "not_in_recipient_list" for row in prepared)
    invalid_count = sum(row["match_status"] == "invalid" for row in prepared)
    with db:
        cursor = db.execute(
            "INSERT INTO survey_import_batch "
            "(fee_cycle_id, source_file_name, source_file_sha256, imported_at, row_count, "
            "matched_count, unmatched_count, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'imported')",
            (
                fee_cycle_id,
                source_file_name,
                source_file_sha256,
                timestamp,
                len(prepared),
                matched_count,
                unmatched_count + invalid_count,
            ),
        )
        batch_id = int(cursor.lastrowid)
        for row in prepared:
            db.execute(
                "INSERT INTO survey_response "
                "(survey_import_batch_id, fee_cycle_id, sap_customer_code, sap_customer_name, "
                "received_answer, not_received_reason, customer_comment, respondent_mobile, "
                "submitted_at, raw_sequence_no, match_status, match_reason, response_fingerprint, imported_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    batch_id,
                    row["fee_cycle_id"],
                    row["sap_customer_code"],
                    row["sap_customer_name"],
                    row["received_answer"],
                    row["not_received_reason"],
                    row["customer_comment"],
                    row["respondent_mobile"],
                    row["submitted_at"],
                    row["raw_sequence_no"],
                    row["match_status"],
                    row["match_reason"],
                    row["response_fingerprint"],
                    row["imported_at"],
                ),
            )
    return SurveyImportResult(
        batch_id, len(prepared), matched_count, unmatched_count, invalid_count
    )
