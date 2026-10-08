from ec101.calculation.engine import calculate_batch


def coupon_seed(seed_batch, config_count=1):
    return seed_batch(
        orders=[
            {"order_no": "O_RELEASE", "status": "已完成", "order_time": "2026-09-19 23:59:59"},
            {"order_no": "O_PENDING", "status": "已完成", "order_time": "2026-09-20 00:00:00"},
        ],
        coupons=[("O_RELEASE", 5), ("O_PENDING", 4), (None, 3)],
        config_count=config_count,
    )


def test_unlinked_coupon_is_visible_but_not_releasable(db, seed_batch):
    seeded = coupon_seed(seed_batch)
    run_id = calculate_batch(db, seeded["batch_id"], "2026-09-22")

    summary = db.execute(
        "SELECT used_count, used_amount, linked_amount, releasable_count, releasable_amount, "
        "unlinked_count, unlinked_amount, settle_status FROM coupon_fee_summary "
        "WHERE calculation_run_id = ?",
        (run_id,),
    ).fetchone()

    assert tuple(summary) == (3, 12, 9, 1, 5, 1, 3, None)


def test_single_coupon_config_is_attached(db, seed_batch):
    seeded = coupon_seed(seed_batch, config_count=1)
    run_id = calculate_batch(db, seeded["batch_id"], "2026-09-22")

    config_id = db.execute(
        "SELECT coupon_config_id FROM coupon_fee_summary WHERE calculation_run_id = ?", (run_id,)
    ).fetchone()[0]
    assert config_id == seeded["config_ids"][0]


def test_multiple_coupon_configs_use_null_bucket(db, seed_batch):
    seeded = coupon_seed(seed_batch, config_count=2)
    run_id = calculate_batch(db, seeded["batch_id"], "2026-09-22")

    config_id = db.execute(
        "SELECT coupon_config_id FROM coupon_fee_summary WHERE calculation_run_id = ?", (run_id,)
    ).fetchone()[0]
    assert config_id is None
