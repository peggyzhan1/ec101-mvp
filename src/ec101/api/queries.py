import sqlite3
from typing import Any, Optional


def _dicts(rows) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def _page(limit: int, offset: int) -> tuple[int, int]:
    return max(1, min(int(limit), 500)), max(0, int(offset))


def _run_ids(db: sqlite3.Connection, calculation_run_id: Optional[int]) -> list[int]:
    if calculation_run_id is not None:
        row = db.execute(
            "SELECT calculation_run_id FROM calculation_run WHERE calculation_run_id = ?",
            (calculation_run_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"核算结果 {calculation_run_id} 不存在")
        return [int(row[0])]
    return [int(row[0]) for row in db.execute(
        "SELECT cr.calculation_run_id FROM calculation_run cr "
        "JOIN import_batch ib ON ib.import_batch_id = cr.import_batch_id "
        "WHERE ib.is_current = 1 AND cr.calculation_run_id = ("
        "  SELECT MAX(latest.calculation_run_id) FROM calculation_run latest "
        "  WHERE latest.import_batch_id = cr.import_batch_id"
        ") ORDER BY cr.calculation_run_id"
    ).fetchall()]


def _in_clause(values: list[int]) -> tuple[str, list[int]]:
    return ",".join("?" for _ in values) or "NULL", values


def list_imports(db: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT ib.import_batch_id AS importBatchId, ib.dealer_name AS dealerName, "
        "ib.platform_name AS platformName, ib.coverage_start AS coverageStart, "
        "ib.coverage_end AS coverageEnd, ib.imported_at AS importedAt, ib.status, "
        "ib.is_current AS isCurrent, "
        "(SELECT MAX(cr.calculation_run_id) FROM calculation_run cr "
        " WHERE cr.import_batch_id = ib.import_batch_id) AS latestCalculationRunId "
        "FROM import_batch ib ORDER BY ib.import_batch_id DESC"
    ).fetchall()
    result = _dicts(rows)
    for item in result:
        item["isCurrent"] = bool(item["isCurrent"])
    return result


def get_import(db: sqlite3.Connection, import_batch_id: int) -> dict[str, Any]:
    row = db.execute(
        "SELECT ib.import_batch_id AS importBatchId, ib.snapshot_key AS snapshotKey, "
        "ib.dealer_name AS dealerName, ib.platform_name AS platformName, "
        "ib.coverage_start AS coverageStart, ib.coverage_end AS coverageEnd, "
        "ib.template_version AS templateVersion, ib.converter_version AS converterVersion, "
        "ib.imported_at AS importedAt, ib.status, ib.is_current AS isCurrent, "
        "(SELECT MAX(cr.calculation_run_id) FROM calculation_run cr "
        " WHERE cr.import_batch_id = ib.import_batch_id) AS latestCalculationRunId "
        "FROM import_batch ib WHERE ib.import_batch_id = ?",
        (import_batch_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"导入批次 {import_batch_id} 不存在")
    result = dict(row)
    result["isCurrent"] = bool(result["isCurrent"])
    result["files"] = _dicts(db.execute(
        "SELECT file_role AS fileRole, file_path AS filePath, sha256, file_size AS fileSize "
        "FROM import_file WHERE import_batch_id = ? ORDER BY import_file_id",
        (import_batch_id,),
    ).fetchall())
    return result


def list_release_candidates(
    db: sqlite3.Connection,
    import_batch_id: int,
    candidate: Optional[bool],
    query: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    run = db.execute(
        "SELECT MAX(calculation_run_id) FROM calculation_run WHERE import_batch_id = ?",
        (import_batch_id,),
    ).fetchone()[0]
    if run is None:
        raise LookupError(f"导入批次 {import_batch_id} 尚无核算结果")
    limit, offset = _page(limit, offset)
    where = ["rc.calculation_run_id = ?"]
    params: list[Any] = [run]
    if candidate is not None:
        where.append("rc.is_candidate = ?")
        params.append(int(candidate))
    if query:
        where.append("(oh.order_no LIKE ? OR COALESCE(oh.customer_name, '') LIKE ?)")
        params.extend([f"%{query}%", f"%{query}%"])
    condition = " AND ".join(where)
    total = db.execute(
        "SELECT COUNT(*) FROM release_candidate rc JOIN order_header oh ON oh.order_id = rc.order_id "
        f"WHERE {condition}", params,
    ).fetchone()[0]
    rows = db.execute(
        "SELECT rc.calculation_run_id AS calculationRunId, oh.order_no AS orderNo, "
        "oh.customer_no AS customerNo, oh.customer_name AS customerName, "
        "rc.is_candidate AS isCandidate, rc.reason, rc.activity_benefit AS activityBenefit, "
        "rc.coupon_benefit AS couponBenefit FROM release_candidate rc "
        "JOIN order_header oh ON oh.order_id = rc.order_id "
        f"WHERE {condition} ORDER BY oh.order_no LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    items = _dicts(rows)
    for item in items:
        item["isCandidate"] = bool(item["isCandidate"])
    return {"items": items, "total": total, "limit": limit, "offset": offset}


_BUSINESS = {
    "customers": {
        "from": "customer x JOIN import_batch ib ON ib.import_batch_id = x.import_batch_id",
        "select": (
            "x.customer_id AS customerId, x.customer_no AS customerNo, x.customer_name AS customerName, "
            "x.customer_type AS customerType, x.customer_region AS customerRegion, "
            "ib.dealer_name AS dealerName, ib.platform_name AS platformName"
        ),
        "search": ("x.customer_no", "x.customer_name"),
        "order": "x.customer_id",
    },
    "products": {
        "from": "product x JOIN import_batch ib ON ib.import_batch_id = x.import_batch_id",
        "select": (
            "x.product_id AS productId, x.product_no AS productNo, x.product_name AS productName, "
            "x.brand, x.category, ib.dealer_name AS dealerName, ib.platform_name AS platformName"
        ),
        "search": ("x.product_no", "x.product_name"),
        "order": "x.product_id",
    },
    "orders": {
        "from": "order_header x JOIN import_batch ib ON ib.import_batch_id = x.import_batch_id",
        "select": (
            "x.order_id AS orderId, x.order_no AS orderNo, x.order_time AS orderTime, "
            "x.customer_no AS customerNo, x.customer_name AS customerName, x.order_status AS orderStatus, "
            "ib.dealer_name AS dealerName, ib.platform_name AS platformName"
        ),
        "search": ("x.order_no", "x.customer_name"),
        "order": "x.order_id",
    },
    "activities": {
        "from": "activity x JOIN import_batch ib ON ib.import_batch_id = x.import_batch_id",
        "select": (
            "x.activity_id AS activityId, x.activity_no AS activityNo, x.activity_name AS activityName, "
            "x.activity_type AS activityType, ib.dealer_name AS dealerName, ib.platform_name AS platformName"
        ),
        "search": ("x.activity_no", "x.activity_name"),
        "order": "x.activity_id",
    },
    "coupons": {
        "from": "coupon_redemption x JOIN import_batch ib ON ib.import_batch_id = x.import_batch_id",
        "select": (
            "x.coupon_redemption_id AS couponRedemptionId, x.coupon_no AS couponNo, "
            "x.customer_no AS customerNo, x.customer_name AS customerName, x.status, "
            "x.discount_amount AS discountAmount, ib.dealer_name AS dealerName, ib.platform_name AS platformName"
        ),
        "search": ("x.coupon_no", "x.customer_name"),
        "order": "x.coupon_redemption_id",
    },
}


def list_business_rows(
    db: sqlite3.Connection,
    resource: str,
    dealer: Optional[str],
    platform: Optional[str],
    query: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    config = _BUSINESS.get(resource)
    if config is None:
        raise LookupError(f"业务资源 {resource} 不存在")
    limit, offset = _page(limit, offset)
    where = ["ib.is_current = 1"]
    params: list[Any] = []
    if dealer:
        where.append("ib.dealer_name = ?")
        params.append(dealer)
    if platform:
        where.append("ib.platform_name = ?")
        params.append(platform)
    if query:
        search = " OR ".join(f"COALESCE({column}, '') LIKE ?" for column in config["search"])
        where.append(f"({search})")
        params.extend([f"%{query}%"] * len(config["search"]))
    condition = " AND ".join(where)
    total = db.execute(
        f"SELECT COUNT(*) FROM {config['from']} WHERE {condition}", params
    ).fetchone()[0]
    rows = db.execute(
        f"SELECT {config['select']} FROM {config['from']} WHERE {condition} "
        f"ORDER BY {config['order']} LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {"items": _dicts(rows), "total": total, "limit": limit, "offset": offset}


def get_fee_overview(
    db: sqlite3.Connection,
    calculation_run_id: Optional[int],
) -> dict[str, Any]:
    run_ids = _run_ids(db, calculation_run_id)
    clause, params = _in_clause(run_ids)
    row = db.execute(
        "SELECT COALESCE(SUM(activity_benefit), 0), COALESCE(SUM(coupon_benefit), 0), "
        "COALESCE(SUM(total_benefit), 0), COALESCE(SUM(released_activity_benefit), 0), "
        "COALESCE(SUM(released_coupon_benefit), 0), COALESCE(SUM(participating_orders), 0), "
        "COALESCE(SUM(released_orders), 0) FROM calculation_run "
        f"WHERE calculation_run_id IN ({clause})",
        params,
    ).fetchone()
    return {
        "calculationRunIds": run_ids,
        "activityBenefit": row[0],
        "couponBenefit": row[1],
        "totalBenefit": row[2],
        "releasedActivityBenefit": row[3],
        "releasedCouponBenefit": row[4],
        "participatingOrders": row[5],
        "releasedOrders": row[6],
    }


def list_activity_summaries(db, calculation_run_id, limit, offset):
    run_ids = _run_ids(db, calculation_run_id)
    limit, offset = _page(limit, offset)
    clause, params = _in_clause(run_ids)
    total = db.execute(
        f"SELECT COUNT(*) FROM activity_fee_summary WHERE calculation_run_id IN ({clause})", params
    ).fetchone()[0]
    rows = db.execute(
        "SELECT afs.calculation_run_id AS calculationRunId, afs.activity_id AS activityId, "
        "a.activity_no AS activityNo, a.activity_name AS activityName, a.activity_type AS activityType, "
        "afs.actual_discount_total AS actualDiscountTotal, afs.participating_orders AS participatingOrders, "
        "afs.released_orders AS releasedOrders, afs.released_amount AS releasedAmount, "
        "afs.pending_orders AS pendingOrders, afs.pending_amount AS pendingAmount, afs.settle_status AS settleStatus "
        "FROM activity_fee_summary afs JOIN activity a ON a.activity_id = afs.activity_id "
        f"WHERE afs.calculation_run_id IN ({clause}) ORDER BY afs.activity_fee_summary_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {"items": _dicts(rows), "total": total, "limit": limit, "offset": offset}


def list_coupon_summaries(db, calculation_run_id, limit, offset):
    run_ids = _run_ids(db, calculation_run_id)
    limit, offset = _page(limit, offset)
    clause, params = _in_clause(run_ids)
    total = db.execute(
        f"SELECT COUNT(*) FROM coupon_fee_summary WHERE calculation_run_id IN ({clause})", params
    ).fetchone()[0]
    rows = db.execute(
        "SELECT calculation_run_id AS calculationRunId, coupon_config_id AS couponConfigId, "
        "used_count AS usedCount, used_amount AS usedAmount, "
        "used_count - unlinked_count AS linkedCount, linked_amount AS linkedAmount, "
        "releasable_count AS releasableCount, releasable_amount AS releasableAmount, "
        "unlinked_count AS unlinkedCount, unlinked_amount AS unlinkedAmount, "
        "settle_status AS settleStatus FROM coupon_fee_summary "
        f"WHERE calculation_run_id IN ({clause}) ORDER BY coupon_fee_summary_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {"items": _dicts(rows), "total": total, "limit": limit, "offset": offset}


def list_unlinked_coupons(db, calculation_run_id, limit, offset):
    run_ids = _run_ids(db, calculation_run_id)
    limit, offset = _page(limit, offset)
    clause, params = _in_clause(run_ids)
    base = (
        "FROM coupon_redemption cr JOIN calculation_run run "
        "ON run.import_batch_id = cr.import_batch_id "
        f"WHERE run.calculation_run_id IN ({clause}) AND cr.order_id IS NULL"
    )
    total = db.execute(f"SELECT COUNT(*) {base}", params).fetchone()[0]
    rows = db.execute(
        "SELECT cr.coupon_redemption_id AS couponRedemptionId, cr.coupon_no AS couponNo, "
        "cr.customer_no AS customerNo, cr.customer_name AS customerName, cr.status, "
        f"cr.discount_amount AS discountAmount {base} "
        "ORDER BY cr.coupon_redemption_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {"items": _dicts(rows), "total": total, "limit": limit, "offset": offset}


def list_fee_issues(db, calculation_run_id, limit=100, offset=0):
    run_ids = _run_ids(db, calculation_run_id)
    limit, offset = _page(limit, offset)
    clause, params = _in_clause(run_ids)
    total = db.execute(
        f"SELECT COUNT(*) FROM calculation_quality_issue WHERE calculation_run_id IN ({clause})", params
    ).fetchone()[0]
    rows = db.execute(
        "SELECT calculation_run_id AS calculationRunId, order_no AS orderNo, issue_type AS issueType, "
        "level, reason FROM calculation_quality_issue "
        f"WHERE calculation_run_id IN ({clause}) ORDER BY calculation_quality_issue_id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {"items": _dicts(rows), "total": total, "limit": limit, "offset": offset}
