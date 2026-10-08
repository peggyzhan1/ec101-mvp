from pathlib import Path

from ec101.calculation.engine import calculate_batch, run_calculation


def engine_seed(seed_batch):
    return seed_batch(
        orders=[
            {"order_no": "O_RELEASE", "status": "已完成", "order_time": "2026-09-19 23:59:59"},
            {"order_no": "O_PENDING", "status": "已完成", "order_time": "2026-09-20 00:00:00"},
            {"order_no": "O_STATUS", "status": "处理中", "order_time": "2026-09-01 00:00:00"},
            {"order_no": "O_IDLE", "status": "已完成", "order_time": "2026-09-01 00:00:00"},
        ],
        activity_amounts=[("O_RELEASE", 10), ("O_PENDING", 7)],
        coupons=[("O_RELEASE", 5), ("O_PENDING", 4), ("O_STATUS", 6), (None, 3)],
    )


def test_engine_reproduces_actual_amount_and_release_path(db, seed_batch):
    seeded = engine_seed(seed_batch)

    run_id = calculate_batch(db, seeded["batch_id"], "2026-09-22")
    result = run_calculation(db, seeded["batch_id"])

    assert result == {
        "calculation_run_id": run_id,
        "calc_date": "2026-09-22",
        "release_cutoff": "2026-09-20 00:00:00",
        "activity_benefit": 17,
        "coupon_benefit": 18,
        "total_benefit": 35,
        "released_activity_benefit": 10,
        "released_coupon_benefit": 5,
        "participating_orders": 3,
        "released_orders": 1,
        "status": "calculated",
    }
    assert db.execute(
        "SELECT status FROM import_batch WHERE import_batch_id = ?", (seeded["batch_id"],)
    ).fetchone()[0] == "calculated"


def test_candidates_activity_summary_and_quality_prompts(db, seed_batch):
    seeded = engine_seed(seed_batch)
    run_id = calculate_batch(db, seeded["batch_id"], "2026-09-22")

    candidates = db.execute(
        "SELECT oh.order_no, rc.is_candidate, rc.reason, rc.activity_benefit, rc.coupon_benefit "
        "FROM release_candidate rc JOIN order_header oh ON oh.order_id = rc.order_id "
        "WHERE rc.calculation_run_id = ? ORDER BY oh.order_no",
        (run_id,),
    ).fetchall()
    assert [tuple(row) for row in candidates] == [
        ("O_PENDING", 0, "未达 T-2", 7, 4),
        ("O_RELEASE", 1, "已完成且达到 T-2", 10, 5),
        ("O_STATUS", 0, "订单状态：处理中", 0, 6),
    ]
    summary = db.execute(
        "SELECT actual_discount_total, participating_orders, released_orders, released_amount, "
        "pending_orders, pending_amount FROM activity_fee_summary WHERE calculation_run_id = ?",
        (run_id,),
    ).fetchone()
    assert tuple(summary) == (17, 2, 1, 10, 1, 7)
    issues = db.execute(
        "SELECT issue_type, level FROM calculation_quality_issue "
        "WHERE calculation_run_id = ? ORDER BY calculation_quality_issue_id",
        (run_id,),
    ).fetchall()
    assert [tuple(row) for row in issues] == [("未达释放节点", "提示"), ("未达释放节点", "提示")]


def test_run_calculation_reads_latest_without_creating_a_run(db, seed_batch):
    seeded = engine_seed(seed_batch)
    first = calculate_batch(db, seeded["batch_id"], "2026-09-21")
    second = calculate_batch(db, seeded["batch_id"], "2026-09-22")

    result = run_calculation(db, seeded["batch_id"])

    assert result["calculation_run_id"] == second
    assert second != first
    assert db.execute("SELECT COUNT(*) FROM calculation_run").fetchone()[0] == 2


def test_engine_source_has_no_parallel_recalculation_branch():
    source = Path(__file__).parents[2].joinpath("src/ec101/calculation/engine.py").read_text()
    forbidden = (
        "promotion_calculator", "standard_promotion", "TemplateResult",
        "theoretical", "consistency", "entitlement_check",
    )

    assert all(symbol not in source for symbol in forbidden)
