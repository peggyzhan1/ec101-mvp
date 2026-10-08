from datetime import date, datetime, timedelta
import sqlite3
from typing import Any, Optional


def parse_calc_date(calc_date: Optional[str]) -> str:
    if calc_date is None:
        return date.today().isoformat()
    try:
        parsed = datetime.strptime(calc_date, "%Y-%m-%d")
    except (TypeError, ValueError) as exc:
        raise ValueError("核算日期必须使用 YYYY-MM-DD 格式") from exc
    if parsed.strftime("%Y-%m-%d") != calc_date:
        raise ValueError("核算日期必须使用 YYYY-MM-DD 格式")
    return calc_date


def release_cutoff(calc_date: str) -> str:
    value = datetime.strptime(parse_calc_date(calc_date), "%Y-%m-%d") - timedelta(days=2)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def release_reason(
    order_status: str,
    order_time: Optional[str],
    cutoff: str,
) -> tuple[bool, str]:
    if order_status != "已完成":
        return False, f"订单状态：{order_status}"
    if not order_time:
        return False, "下单时间缺失"
    if datetime.fromisoformat(order_time) >= datetime.fromisoformat(cutoff):
        return False, "未达 T-2"
    return True, "已完成且达到 T-2"


def calculate_batch(
    db: sqlite3.Connection,
    batch_id: int,
    calc_date: Optional[str] = None,
) -> int:
    normalized_date = parse_calc_date(calc_date)
    cutoff = release_cutoff(normalized_date)

    with db:
        activity_total = db.execute(
            "SELECT COALESCE(SUM(ae.discount_amount), 0) "
            "FROM activity_execution ae "
            "JOIN activity a ON a.activity_id = ae.activity_id "
            "WHERE a.import_batch_id = ?",
            (batch_id,),
        ).fetchone()[0]
        coupon_total = db.execute(
            "SELECT COALESCE(SUM(discount_amount), 0) FROM coupon_redemption "
            "WHERE import_batch_id = ?",
            (batch_id,),
        ).fetchone()[0]
        run_id = int(db.execute(
            "INSERT INTO calculation_run "
            "(import_batch_id, calc_date, release_cutoff, activity_benefit, coupon_benefit, "
            "total_benefit, status) VALUES (?, ?, ?, ?, ?, ?, 'calculating')",
            (batch_id, normalized_date, cutoff, activity_total, coupon_total, activity_total + coupon_total),
        ).lastrowid)

        participating = db.execute(
            "SELECT oh.order_id, oh.order_no, oh.order_status, oh.order_time, "
            "COALESCE((SELECT SUM(ae.discount_amount) FROM activity_execution ae "
            "          WHERE ae.order_id = oh.order_id), 0) AS activity_amount, "
            "COALESCE((SELECT SUM(cr.discount_amount) FROM coupon_redemption cr "
            "          WHERE cr.order_id = oh.order_id AND cr.import_batch_id = ?), 0) AS coupon_amount "
            "FROM order_header oh WHERE oh.import_batch_id = ? AND ("
            "EXISTS (SELECT 1 FROM activity_execution ae WHERE ae.order_id = oh.order_id) OR "
            "EXISTS (SELECT 1 FROM coupon_redemption cr "
            "        WHERE cr.order_id = oh.order_id AND cr.import_batch_id = ?)) "
            "ORDER BY oh.order_id",
            (batch_id, batch_id, batch_id),
        ).fetchall()

        released_orders = 0
        released_activity = 0
        released_coupon = 0
        for row in participating:
            candidate, reason = release_reason(row["order_status"], row["order_time"], cutoff)
            db.execute(
                "INSERT INTO release_candidate "
                "(calculation_run_id, order_id, is_candidate, reason, activity_benefit, coupon_benefit) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, row["order_id"], int(candidate), reason, row["activity_amount"], row["coupon_amount"]),
            )
            if candidate:
                released_orders += 1
                released_activity += row["activity_amount"]
                released_coupon += row["coupon_amount"]
            else:
                db.execute(
                    "INSERT INTO calculation_quality_issue "
                    "(calculation_run_id, order_no, issue_type, level, reason) "
                    "VALUES (?, ?, '未达释放节点', '提示', ?)",
                    (run_id, row["order_no"], reason),
                )

        _write_activity_summaries(db, run_id, batch_id)
        _write_coupon_summary(db, run_id, batch_id)
        db.execute(
            "UPDATE calculation_run SET released_activity_benefit = ?, "
            "released_coupon_benefit = ?, participating_orders = ?, released_orders = ?, "
            "status = 'calculated' WHERE calculation_run_id = ?",
            (released_activity, released_coupon, len(participating), released_orders, run_id),
        )
        db.execute(
            "UPDATE import_batch SET status = 'calculated' WHERE import_batch_id = ?",
            (batch_id,),
        )
    return run_id


def _write_activity_summaries(db: sqlite3.Connection, run_id: int, batch_id: int) -> None:
    rows = db.execute(
        "SELECT a.activity_id, COALESCE(SUM(ae.discount_amount), 0) AS actual_amount, "
        "COUNT(*) AS participating_count, "
        "SUM(CASE WHEN rc.is_candidate = 1 THEN 1 ELSE 0 END) AS released_count, "
        "COALESCE(SUM(CASE WHEN rc.is_candidate = 1 THEN ae.discount_amount ELSE 0 END), 0) AS released_amount, "
        "SUM(CASE WHEN rc.is_candidate = 0 THEN 1 ELSE 0 END) AS pending_count, "
        "COALESCE(SUM(CASE WHEN rc.is_candidate = 0 THEN ae.discount_amount ELSE 0 END), 0) AS pending_amount "
        "FROM activity a "
        "JOIN activity_execution ae ON ae.activity_id = a.activity_id "
        "JOIN release_candidate rc ON rc.order_id = ae.order_id AND rc.calculation_run_id = ? "
        "WHERE a.import_batch_id = ? GROUP BY a.activity_id ORDER BY a.activity_id",
        (run_id, batch_id),
    ).fetchall()
    for row in rows:
        db.execute(
            "INSERT INTO activity_fee_summary "
            "(calculation_run_id, activity_id, actual_discount_total, gift_cost_total, "
            "participating_orders, released_orders, released_amount, pending_orders, pending_amount) "
            "VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)",
            (run_id, row["activity_id"], row["actual_amount"], row["participating_count"],
             row["released_count"], row["released_amount"], row["pending_count"], row["pending_amount"]),
        )


def _write_coupon_summary(db: sqlite3.Connection, run_id: int, batch_id: int) -> None:
    config_ids = db.execute(
        "SELECT coupon_config_id FROM coupon_config WHERE import_batch_id = ? ORDER BY coupon_config_id",
        (batch_id,),
    ).fetchall()
    config_id = config_ids[0][0] if len(config_ids) == 1 else None
    row = db.execute(
        "SELECT COUNT(*) AS used_count, COALESCE(SUM(cr.discount_amount), 0) AS used_amount, "
        "COALESCE(SUM(CASE WHEN cr.order_id IS NOT NULL THEN cr.discount_amount ELSE 0 END), 0) AS linked_amount, "
        "SUM(CASE WHEN rc.is_candidate = 1 THEN 1 ELSE 0 END) AS releasable_count, "
        "COALESCE(SUM(CASE WHEN rc.is_candidate = 1 THEN cr.discount_amount ELSE 0 END), 0) AS releasable_amount, "
        "SUM(CASE WHEN cr.order_id IS NULL THEN 1 ELSE 0 END) AS unlinked_count, "
        "COALESCE(SUM(CASE WHEN cr.order_id IS NULL THEN cr.discount_amount ELSE 0 END), 0) AS unlinked_amount "
        "FROM coupon_redemption cr LEFT JOIN release_candidate rc "
        "ON rc.order_id = cr.order_id AND rc.calculation_run_id = ? "
        "WHERE cr.import_batch_id = ?",
        (run_id, batch_id),
    ).fetchone()
    db.execute(
        "INSERT INTO coupon_fee_summary "
        "(calculation_run_id, coupon_config_id, used_count, used_amount, linked_amount, "
        "releasable_count, releasable_amount, unlinked_count, unlinked_amount, settle_status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
        (run_id, config_id, row["used_count"], row["used_amount"], row["linked_amount"],
         row["releasable_count"], row["releasable_amount"], row["unlinked_count"], row["unlinked_amount"]),
    )


def run_calculation(db: sqlite3.Connection, import_batch_id: int) -> dict[str, Any]:
    row = db.execute(
        "SELECT calculation_run_id, calc_date, release_cutoff, activity_benefit, coupon_benefit, "
        "total_benefit, released_activity_benefit, released_coupon_benefit, participating_orders, "
        "released_orders, status FROM calculation_run WHERE import_batch_id = ? "
        "ORDER BY calculation_run_id DESC LIMIT 1",
        (import_batch_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"导入批次 {import_batch_id} 尚无核算结果")
    return dict(row)
