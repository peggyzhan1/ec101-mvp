from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import re
from typing import Any, Mapping, Sequence

from .workbook import (
    FeeRecipientValidationError,
    normalize_customer_code,
    parse_positive_amount,
)


def _month(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m")
    text = "" if value is None else str(value).strip()
    match = re.fullmatch(r"(\d{4})-?(\d{2})", text)
    if match is None:
        raise FeeRecipientValidationError("费用发放月必须是 YYYYMM 或 YYYY-MM")
    month = int(match.group(2))
    if month < 1 or month > 12:
        raise FeeRecipientValidationError("费用发放月不是有效月份")
    return f"{match.group(1)}-{month:02d}"


def aggregate_legacy_coupon_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    coupons: dict[tuple[str, str, str], tuple[Decimal, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        try:
            customer_code = normalize_customer_code(row.get("客户编号"))
            fee_cycle = _month(row.get("费用发放月"))
            amount = parse_positive_amount(row.get("金额"))
        except FeeRecipientValidationError as exc:
            raise FeeRecipientValidationError(f"第 {row_number} 行：{exc}") from exc
        main_coupon = "" if row.get("主券号") is None else str(row.get("主券号")).strip()
        if not main_coupon:
            raise FeeRecipientValidationError(f"第 {row_number} 行：主券号不能为空")
        customer_name = "" if row.get("客户名称") is None else str(row.get("客户名称")).strip()
        key = (customer_code, fee_cycle, main_coupon)
        previous = coupons.get(key)
        if previous is not None and previous[0] != amount:
            raise FeeRecipientValidationError(
                f"第 {row_number} 行：同一主券 {main_coupon} 的金额不一致"
            )
        coupons.setdefault(key, (amount, customer_name))

    totals: dict[tuple[str, str], dict[str, Any]] = {}
    for (customer_code, fee_cycle, _), (amount, customer_name) in coupons.items():
        group = totals.setdefault((fee_cycle, customer_code), {
            "name": customer_name,
            "amount": Decimal("0.00"),
        })
        group["amount"] += amount

    return [
        {
            "费用周期": fee_cycle,
            "太古客户编号": customer_code,
            "太古客户名称": group["name"],
            "应发金额": format(group["amount"], ".2f"),
            "备注": "历史乐客通发券明细汇总",
        }
        for (fee_cycle, customer_code), group in sorted(totals.items())
    ]
