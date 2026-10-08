import re
import sqlite3
from typing import Any, Optional


def box_factor(box_conversion: object = None, base_qty_per_box: object = None) -> Optional[float]:
    for value in (base_qty_per_box, box_conversion):
        if value is None or str(value).strip() == "":
            continue
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        if match:
            factor = float(match.group(0))
            if factor > 0:
                return factor
    return None


def base_qty(
    quantity: object,
    unit: object,
    box_conversion: object = None,
    base_qty_per_box: object = None,
) -> Optional[float]:
    try:
        amount = float(quantity)
    except (TypeError, ValueError):
        return None
    text = str(unit or "")
    if "箱" in text:
        factor = box_factor(box_conversion, base_qty_per_box)
        return amount * factor if factor is not None else None
    if "瓶" in text or "罐" in text:
        return amount
    return None


def _period(start: object, end: object):
    if start and end:
        return {"start": str(start), "end": str(end)}
    return None


def _coca_cola_order_metrics(db: sqlite3.Connection, order_sql: str, params: list[Any]):
    rows = db.execute(
        "SELECT ol.quantity, ol.unit, ol.pre_discount_amount, p.box_conversion, p.base_qty_per_box "
        "FROM order_line ol JOIN order_header oh ON oh.order_id = ol.order_id "
        "JOIN product p ON p.import_batch_id = oh.import_batch_id AND p.product_no = ol.product_no "
        f"WHERE oh.order_status = '已完成' AND p.brand LIKE '%可口可乐%' AND ({order_sql})",
        params,
    ).fetchall()
    quantity = 0.0
    sales = 0.0
    for row in rows:
        value = base_qty(row["quantity"], row["unit"], row["box_conversion"], row["base_qty_per_box"])
        if value is not None:
            quantity += value
        sales += float(row["pre_discount_amount"] or 0)
    return quantity, sales


def activity_roi(db: sqlite3.Connection, activity_id: int) -> dict[str, Any]:
    activity = db.execute(
        "SELECT activity_id, activity_no, activity_name, activity_type, start_time, end_time "
        "FROM activity WHERE activity_id = ?", (activity_id,)
    ).fetchone()
    if activity is None:
        raise LookupError(f"活动 {activity_id} 不存在")
    actual = db.execute(
        "SELECT COALESCE(SUM(ae.discount_amount), 0) FROM activity_execution ae "
        "JOIN order_header oh ON oh.order_id = ae.order_id "
        "WHERE ae.activity_id = ? AND oh.order_status = '已完成'",
        (activity_id,),
    ).fetchone()[0]
    quantity, sales = _coca_cola_order_metrics(
        db,
        "EXISTS (SELECT 1 FROM activity_execution ae WHERE ae.order_id = oh.order_id AND ae.activity_id = ?)",
        [activity_id],
    )
    gift = "赠" in (activity["activity_type"] or "")
    return {
        "kind": "activity",
        "id": activity_id,
        "code": activity["activity_no"],
        "name": activity["activity_name"],
        "activityType": activity["activity_type"],
        "period": _period(activity["start_time"], activity["end_time"]),
        "baseQuantity": quantity,
        "salesAmount": sales,
        "actualAmount": actual,
        "roi": None if gift or not actual else sales / actual,
    }


def coupon_roi(db: sqlite3.Connection, coupon_config_id: int) -> dict[str, Any]:
    config = db.execute(
        "SELECT cc.coupon_config_id, cc.config_no, cc.coupon_name, cc.import_batch_id, "
        "cur.use_start_at, cur.use_end_at FROM coupon_config cc "
        "LEFT JOIN coupon_use_rule cur ON cur.coupon_config_id = cc.coupon_config_id "
        "WHERE cc.coupon_config_id = ?", (coupon_config_id,)
    ).fetchone()
    if config is None:
        raise LookupError(f"优惠券配置 {coupon_config_id} 不存在")
    actual = db.execute(
        "SELECT COALESCE(SUM(cr.discount_amount), 0) FROM coupon_redemption cr "
        "JOIN order_header oh ON oh.order_id = cr.order_id "
        "WHERE cr.import_batch_id = ? AND oh.order_status = '已完成'",
        (config["import_batch_id"],),
    ).fetchone()[0]
    quantity, sales = _coca_cola_order_metrics(
        db,
        "EXISTS (SELECT 1 FROM coupon_redemption cr "
        "        WHERE cr.order_id = oh.order_id AND cr.import_batch_id = ?)",
        [config["import_batch_id"]],
    )
    return {
        "kind": "coupon",
        "id": coupon_config_id,
        "code": config["config_no"],
        "name": config["coupon_name"],
        "period": _period(config["use_start_at"], config["use_end_at"]),
        "baseQuantity": quantity,
        "salesAmount": sales,
        "actualAmount": actual,
        "roi": None if not actual else sales / actual,
    }


def query_roi(db: sqlite3.Connection, calculation_run_id: Optional[int] = None) -> list[dict[str, Any]]:
    if calculation_run_id is None:
        runs = db.execute(
            "SELECT cr.calculation_run_id FROM calculation_run cr JOIN import_batch ib "
            "ON ib.import_batch_id = cr.import_batch_id WHERE ib.is_current = 1 "
            "AND cr.calculation_run_id = (SELECT MAX(inner_run.calculation_run_id) "
            "FROM calculation_run inner_run WHERE inner_run.import_batch_id = cr.import_batch_id)"
        ).fetchall()
        run_ids = [row[0] for row in runs]
    else:
        exists = db.execute("SELECT 1 FROM calculation_run WHERE calculation_run_id = ?", (calculation_run_id,)).fetchone()
        if exists is None:
            raise LookupError(f"核算结果 {calculation_run_id} 不存在")
        run_ids = [calculation_run_id]
    result = []
    for run_id in run_ids:
        for row in db.execute(
            "SELECT activity_id FROM activity_fee_summary WHERE calculation_run_id = ? ORDER BY activity_fee_summary_id",
            (run_id,),
        ).fetchall():
            item = activity_roi(db, row[0])
            item["calculationRunId"] = run_id
            result.append(item)
        for row in db.execute(
            "SELECT coupon_config_id FROM coupon_fee_summary WHERE calculation_run_id = ? "
            "AND coupon_config_id IS NOT NULL ORDER BY coupon_fee_summary_id",
            (run_id,),
        ).fetchall():
            item = coupon_roi(db, row[0])
            item["calculationRunId"] = run_id
            result.append(item)
    return result
