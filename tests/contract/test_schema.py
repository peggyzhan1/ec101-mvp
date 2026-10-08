from ec101.contract.schema import (
    REQUIRED_COLUMNS,
    SHEET_COLUMNS,
    STANDARD_SHEETS,
    Issue,
    validate_rows,
)


EXPECTED_SHEETS = (
    "导入清单",
    "标准客户",
    "标准商品",
    "标准订单明细",
    "标准活动",
    "标准活动规则",
    "标准活动权益",
    "标准活动范围",
    "标准活动核销明细",
    "标准优惠券配置",
    "标准优惠券发放规则",
    "标准优惠券使用规则",
    "标准优惠券适用范围",
    "标准优惠券核销明细",
    "标准履约",
)


def test_standard_sheet_order_is_fixed():
    assert STANDARD_SHEETS == EXPECTED_SHEETS
    assert tuple(SHEET_COLUMNS) == EXPECTED_SHEETS


def test_validate_rows_reports_unknown_columns_and_empty_required_values():
    issues = validate_rows("标准订单明细", [{"单据编号": "", "未知字段": "x"}])

    assert all(isinstance(issue, Issue) for issue in issues)
    assert {(issue.code, issue.column) for issue in issues} >= {
        ("UNKNOWN_COLUMN", "未知字段"),
        ("REQUIRED_VALUE", "单据编号"),
    }
    assert "单据编号" in REQUIRED_COLUMNS["标准订单明细"]


def test_validate_rows_rejects_unknown_sheet():
    issues = validate_rows("不存在", [{}])

    assert [(issue.code, issue.sheet) for issue in issues] == [
        ("UNKNOWN_SHEET", "不存在")
    ]
