from ec101.contract.workbook import StandardWorkbook
from ec101.importing.service import validate_import


def test_validation_reports_missing_master_and_execution_references(db, workbook_factory):
    workbook = workbook_factory()
    workbook.tables["标准客户"] = []
    workbook.tables["标准商品"] = []
    workbook.tables["标准活动"] = []

    issues = validate_import(workbook, db)
    codes = {issue.code for issue in issues}

    assert {"MISSING_CUSTOMER", "MISSING_PRODUCT", "MISSING_ACTIVITY"} <= codes


def test_coupon_redemption_allows_empty_order_but_rejects_unknown_nonempty_order(db, workbook_factory):
    workbook = workbook_factory()
    workbook.tables["标准优惠券核销明细"][0]["订单号"] = "UNKNOWN"
    workbook.tables["标准优惠券核销明细"][1]["订单号"] = ""

    issues = validate_import(workbook, db)

    coupon_order_issues = [issue for issue in issues if issue.code == "MISSING_COUPON_ORDER"]
    assert len(coupon_order_issues) == 1
    assert coupon_order_issues[0].row == 2


def test_validation_does_not_modify_database(db, workbook_factory):
    before = db.total_changes

    validate_import(workbook_factory(), db)

    assert db.total_changes == before
    assert db.execute("SELECT COUNT(*) FROM import_batch").fetchone()[0] == 0
