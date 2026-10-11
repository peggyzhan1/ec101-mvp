import pytest

from ec101.confirmation.legacy_coupon import aggregate_legacy_coupon_rows
from ec101.confirmation.workbook import FeeRecipientValidationError


def row(main_coupon, amount, sub_coupon, month=202609):
    return {
        "客户编号": 576567577,
        "客户名称": "佳源食品商行",
        "主券号": main_coupon,
        "费用发放月": month,
        "金额": amount,
        "副券号": sub_coupon,
    }


def test_aggregate_legacy_coupon_rows_deduplicates_main_coupon_before_cycle_sum():
    rows = [
        row("M-001", "200.00", "S-001"),
        row("M-001", "200.00", "S-002"),
        row("M-002", "300.00", "S-003"),
    ]

    result = aggregate_legacy_coupon_rows(rows)

    assert result == [{
        "费用周期": "2026-09",
        "太古客户编号": "576567577",
        "太古客户名称": "佳源食品商行",
        "应发金额": "500.00",
        "备注": "历史乐客通发券明细汇总",
    }]


def test_aggregate_legacy_coupon_rows_rejects_conflicting_amount_for_same_main_coupon():
    rows = [
        row("M-001", "200.00", "S-001"),
        row("M-001", "220.00", "S-002"),
    ]

    with pytest.raises(FeeRecipientValidationError, match="主券.*金额不一致"):
        aggregate_legacy_coupon_rows(rows)


@pytest.mark.parametrize("month", [None, "2026-13", "26年9月"])
def test_aggregate_legacy_coupon_rows_rejects_invalid_fee_month(month):
    with pytest.raises(FeeRecipientValidationError, match="费用发放月"):
        aggregate_legacy_coupon_rows([row("M-001", "200.00", "S-001", month)])
