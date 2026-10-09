from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import sqlite3
from typing import Any, Iterable, Mapping
from uuid import uuid4

from ec101.contract.schema import Issue, validate_rows
from ec101.contract.workbook import StandardWorkbook


@dataclass(frozen=True)
class ArchiveMetadata:
    file_path: str
    sha256: str
    file_size: int


@dataclass(frozen=True)
class ImportResult:
    import_batch_id: int
    status: str


class ImportValidationError(ValueError):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        super().__init__(f"标准工作簿校验失败：{len(issues)} 个问题")


def _value(row: Mapping[str, Any], column: str) -> str:
    value = row.get(column)
    return "" if value is None else str(value).strip()


def _nullable(row: Mapping[str, Any], column: str) -> str | None:
    value = _value(row, column)
    return value or None


def _references(
    sheet: str,
    rows: Iterable[Mapping[str, Any]],
    column: str,
    known: set[str],
    code: str,
    label: str,
    *,
    allow_empty: bool = False,
) -> list[Issue]:
    issues = []
    for row_number, row in enumerate(rows, start=2):
        value = _value(row, column)
        if (not value and allow_empty) or not value:
            continue
        if value not in known:
            issues.append(Issue(
                sheet, row_number, column, code,
                f"{sheet} 第 {row_number} 行引用了不存在的{label}：{value}",
            ))
    return issues


def validate_import(workbook: StandardWorkbook, db: sqlite3.Connection) -> list[Issue]:
    del db  # Validation is deliberately read-only and snapshot-local.
    issues = validate_rows("导入清单", [workbook.manifest])
    for sheet, rows in workbook.tables.items():
        issues.extend(validate_rows(sheet, rows))

    customers = {_value(row, "客户编号") for row in workbook.tables.get("标准客户", ())}
    products = {_value(row, "商品编号") for row in workbook.tables.get("标准商品", ())}
    orders = {_value(row, "单据编号") for row in workbook.tables.get("标准订单明细", ())}
    activities = {_value(row, "活动编号") for row in workbook.tables.get("标准活动", ())}
    rules = {
        (_value(row, "活动编号"), _value(row, "规则编号"))
        for row in workbook.tables.get("标准活动规则", ())
    }
    coupon_configs = {
        _value(row, "优惠券配置编号")
        for row in workbook.tables.get("标准优惠券配置", ())
    }

    order_rows = workbook.tables.get("标准订单明细", ())
    issues.extend(_references("标准订单明细", order_rows, "客户编号", customers, "MISSING_CUSTOMER", "客户"))
    issues.extend(_references("标准订单明细", order_rows, "商品编号", products, "MISSING_PRODUCT", "商品"))

    activity_children = (
        "标准活动规则", "标准活动权益", "标准活动范围", "标准活动核销明细",
    )
    for sheet in activity_children:
        issues.extend(_references(
            sheet, workbook.tables.get(sheet, ()), "活动编号", activities,
            "MISSING_ACTIVITY", "活动",
        ))
    for row_number, row in enumerate(workbook.tables.get("标准活动权益", ()), start=2):
        key = (_value(row, "活动编号"), _value(row, "规则编号"))
        if all(key) and key not in rules:
            issues.append(Issue(
                "标准活动权益", row_number, "规则编号", "MISSING_ACTIVITY_RULE",
                f"标准活动权益 第 {row_number} 行引用了不存在的活动规则：{key[1]}",
            ))
    issues.extend(_references(
        "标准活动核销明细", workbook.tables.get("标准活动核销明细", ()), "订单号", orders,
        "MISSING_ACTIVITY_ORDER", "订单",
    ))

    for sheet in ("标准优惠券发放规则", "标准优惠券使用规则", "标准优惠券适用范围"):
        issues.extend(_references(
            sheet, workbook.tables.get(sheet, ()), "优惠券配置编号", coupon_configs,
            "MISSING_COUPON_CONFIG", "优惠券配置",
        ))

    redemption_rows = workbook.tables.get("标准优惠券核销明细", ())
    issues.extend(_references(
        "标准优惠券核销明细", redemption_rows, "客户编号", customers,
        "MISSING_CUSTOMER", "客户",
    ))
    issues.extend(_references(
        "标准优惠券核销明细", redemption_rows, "订单号", orders,
        "MISSING_COUPON_ORDER", "订单", allow_empty=True,
    ))
    issues.extend(_references(
        "标准履约", workbook.tables.get("标准履约", ()), "单据编号", orders,
        "MISSING_FULFILLMENT_ORDER", "订单",
    ))
    return issues


def _snapshot_key(manifest: Mapping[str, Any], archive: ArchiveMetadata | None) -> str:
    identity = "|".join((
        _value(manifest, "经销商名称"),
        _value(manifest, "平台名称"),
        _value(manifest, "数据开始日期"),
        _value(manifest, "数据结束日期"),
        archive.sha256 if archive else "no-source-archive",
        uuid4().hex,
    ))
    return sha256(identity.encode("utf-8")).hexdigest()


def import_snapshot(
    db: sqlite3.Connection,
    workbook: StandardWorkbook,
    archive: ArchiveMetadata | None = None,
) -> ImportResult:
    manifest = workbook.manifest
    dealer = _value(manifest, "经销商名称")
    platform = _value(manifest, "平台名称")
    coverage_start = _nullable(manifest, "数据开始日期")
    coverage_end = _nullable(manifest, "数据结束日期")
    imported_at = _nullable(manifest, "生成时间") or datetime.now().isoformat(timespec="seconds")

    with db:
        db.execute(
            "UPDATE import_batch SET is_current = 0 "
            "WHERE dealer_name = ? AND platform_name = ? "
            "AND coverage_start IS ? AND coverage_end IS ?",
            (dealer, platform, coverage_start, coverage_end),
        )
        cursor = db.execute(
            "INSERT INTO import_batch "
            "(snapshot_key, dealer_name, platform_name, coverage_start, coverage_end, "
            "template_version, converter_version, imported_at, status, is_current) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'imported', 1)",
            (
                _snapshot_key(manifest, archive), dealer, platform, coverage_start, coverage_end,
                _value(manifest, "模板版本"), _value(manifest, "转换工具版本"), imported_at,
            ),
        )
        batch_id = int(cursor.lastrowid)
        if archive is not None:
            db.execute(
                "INSERT INTO import_file "
                "(import_batch_id, file_role, file_path, sha256, file_size) VALUES (?, 'sources', ?, ?, ?)",
                (batch_id, archive.file_path, archive.sha256, archive.file_size),
            )
        db.execute(
            "INSERT INTO dealer_platform (dealer_name, platform_name) VALUES (?, ?) "
            "ON CONFLICT(dealer_name, platform_name) DO NOTHING",
            (dealer, platform),
        )
        dealer_platform_id = db.execute(
            "SELECT dealer_platform_id FROM dealer_platform WHERE dealer_name = ? AND platform_name = ?",
            (dealer, platform),
        ).fetchone()[0]

        _insert_customers(db, workbook, batch_id, dealer_platform_id)
        _insert_products(db, workbook, batch_id, dealer_platform_id)
        order_ids = _insert_orders(db, workbook, batch_id, dealer_platform_id)
        activity_ids = _insert_activities(db, workbook, batch_id, order_ids)
        _insert_fulfillment(db, workbook, batch_id)
        coupon_config_ids = _insert_coupon_configs(db, workbook, batch_id)
        _insert_coupon_details(db, workbook, batch_id, coupon_config_ids, order_ids)

    return ImportResult(import_batch_id=batch_id, status="imported")


def _insert_customers(db, workbook, batch_id, dealer_platform_id):
    for row in workbook.tables.get("标准客户", ()):
        db.execute(
            "INSERT INTO customer VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (batch_id, dealer_platform_id, _value(row, "客户编号"), _value(row, "客户名称"),
             _nullable(row, "客户类型"), _nullable(row, "客户区域"), _nullable(row, "详细地址"),
             _nullable(row, "联系电话"), _nullable(row, "添加时间"), _nullable(row, "所属业务员")),
        )


def _insert_products(db, workbook, batch_id, dealer_platform_id):
    for row in workbook.tables.get("标准商品", ()):
        db.execute(
            "INSERT INTO product VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (batch_id, dealer_platform_id, _value(row, "商品编号"), _value(row, "商品名称"),
             _nullable(row, "商品品牌"), _nullable(row, "商品目录"), _nullable(row, "商品条码"),
             _nullable(row, "商品规格"), _nullable(row, "基本单位"), _nullable(row, "箱规"),
             _nullable(row, "每箱基本单位数量")),
        )


def _insert_orders(db, workbook, batch_id, dealer_platform_id):
    order_ids = {}
    for row in workbook.tables.get("标准订单明细", ()):
        order_no = _value(row, "单据编号")
        if order_no not in order_ids:
            cursor = db.execute(
                "INSERT INTO order_header VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (batch_id, dealer_platform_id, order_no, _nullable(row, "下单时间"),
                 _value(row, "客户编号"), _nullable(row, "客户名称"), _nullable(row, "业务员"),
                 _nullable(row, "订单来源"), _nullable(row, "订单类型"), _value(row, "订单状态"),
                 _nullable(row, "支付方式"), _nullable(row, "下游订单编号")),
            )
            order_ids[order_no] = int(cursor.lastrowid)
        db.execute(
            "INSERT INTO order_line VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (order_ids[order_no], _value(row, "商品编号"), _nullable(row, "商品名称"),
             _nullable(row, "商品目录"), _nullable(row, "规格"), _nullable(row, "商品条码"),
             _nullable(row, "单位"), _nullable(row, "数量"), _nullable(row, "优惠前金额"),
             _nullable(row, "活动编号"), _nullable(row, "优惠券编号"), _nullable(row, "优惠金额"),
             _nullable(row, "实付金额"), _nullable(row, "单价"), _nullable(row, "退货数量")),
        )
    return order_ids


def _insert_activities(db, workbook, batch_id, order_ids):
    activity_ids = {}
    for row in workbook.tables.get("标准活动", ()):
        cursor = db.execute(
            "INSERT INTO activity VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (batch_id, _value(row, "活动编号"), _value(row, "活动名称"), _value(row, "活动类型"),
             _nullable(row, "促销方式"), _nullable(row, "开始时间"), _nullable(row, "结束时间"),
             _nullable(row, "是否允许叠加活动"), _nullable(row, "是否允许叠加优惠券"),
             _nullable(row, "活动状态")),
        )
        activity_ids[_value(row, "活动编号")] = int(cursor.lastrowid)
    for row in workbook.tables.get("标准活动规则", ()):
        db.execute(
            "INSERT INTO activity_rule VALUES (NULL, ?, ?, ?, ?, ?, ?)",
            (activity_ids[_value(row, "活动编号")], _value(row, "规则编号"),
             _value(row, "门槛类型"), _nullable(row, "门槛值"), _nullable(row, "立减金额"),
             1 if _value(row, "是否免邮") in {"是", "1", "true", "True"} else 0),
        )
    for row in workbook.tables.get("标准活动权益", ()):
        db.execute(
            "INSERT INTO activity_benefit VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            (activity_ids[_value(row, "活动编号")], _value(row, "规则编号"),
             _value(row, "权益编号"), _value(row, "权益类型"), _nullable(row, "赠品商品编号"),
             _nullable(row, "赠品商品名称"), _nullable(row, "赠品数量"), _nullable(row, "赠品单位")),
        )
    for row in workbook.tables.get("标准活动范围", ()):
        db.execute(
            "INSERT INTO activity_scope VALUES (NULL, ?, ?, ?, ?, ?)",
            (activity_ids[_value(row, "活动编号")], _value(row, "范围编号"),
             _value(row, "范围类别"), _value(row, "范围维度"), _value(row, "范围值")),
        )
    for row in workbook.tables.get("标准活动核销明细", ()):
        db.execute(
            "INSERT INTO activity_execution VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            (activity_ids[_value(row, "活动编号")], order_ids[_value(row, "订单号")],
             _nullable(row, "活动名称"), _nullable(row, "客户编号"), _nullable(row, "客户"),
             _nullable(row, "所属业务员"), _nullable(row, "商品总金额"), _nullable(row, "优惠金额")),
        )
    return activity_ids


def _insert_fulfillment(db, workbook, batch_id):
    for row in workbook.tables.get("标准履约", ()):
        db.execute(
            "INSERT INTO fulfillment VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            (batch_id, _value(row, "单据编号"), _nullable(row, "下游订单编号"),
             _value(row, "履约订单状态"), _nullable(row, "出库时间"), _nullable(row, "完成时间"),
             _nullable(row, "结款状态"), _nullable(row, "退货数量")),
        )


def _insert_coupon_configs(db, workbook, batch_id):
    config_ids = {}
    for row in workbook.tables.get("标准优惠券配置", ()):
        cursor = db.execute(
            "INSERT INTO coupon_config VALUES (NULL, ?, ?, ?, ?, ?)",
            (batch_id, _value(row, "优惠券配置编号"), _value(row, "优惠券名称"),
             _nullable(row, "券类型"), _value(row, "配置状态")),
        )
        config_ids[_value(row, "优惠券配置编号")] = int(cursor.lastrowid)
    return config_ids


def _insert_coupon_details(db, workbook, batch_id, config_ids, order_ids):
    for row in workbook.tables.get("标准优惠券发放规则", ()):
        db.execute(
            "INSERT INTO coupon_issue_rule VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (config_ids[_value(row, "优惠券配置编号")], _value(row, "发放方式"),
             _value(row, "发放开始时间"), _nullable(row, "发放结束时间"),
             _nullable(row, "自动发放时间"), _value(row, "每次发放数量"),
             _nullable(row, "每客户领取上限"), _nullable(row, "每日领取上限"),
             _value(row, "规则状态")),
        )
    for row in workbook.tables.get("标准优惠券使用规则", ()):
        db.execute(
            "INSERT INTO coupon_use_rule VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            (config_ids[_value(row, "优惠券配置编号")], _value(row, "券类型"),
             _value(row, "有效期类型"), _nullable(row, "使用开始时间"), _nullable(row, "使用结束时间"),
             _nullable(row, "领取后有效天数"), _value(row, "每张券最多使用次数"),
             _value(row, "规则状态")),
        )
    for row in workbook.tables.get("标准优惠券适用范围", ()):
        db.execute(
            "INSERT INTO coupon_scope VALUES (NULL, ?, ?, ?, ?, ?)",
            (config_ids[_value(row, "优惠券配置编号")], _value(row, "范围编号"),
             _value(row, "范围类别"), _value(row, "范围维度"), _value(row, "范围值")),
        )
    for row in workbook.tables.get("标准优惠券核销明细", ()):
        order_no = _value(row, "订单号")
        db.execute(
            "INSERT INTO coupon_redemption VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (batch_id, order_ids.get(order_no), _value(row, "优惠券编号"), _value(row, "客户编号"),
             _nullable(row, "客户"), _nullable(row, "所属业务员"), _nullable(row, "领取时间"),
             _nullable(row, "使用期限"), _value(row, "状态"), _nullable(row, "使用时间"),
             _nullable(row, "优惠金额")),
        )
