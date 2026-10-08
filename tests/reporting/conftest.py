import pytest

from ec101.calculation.engine import calculate_batch
from ec101.db import connect_database, create_database


@pytest.fixture
def reporting_db(tmp_path):
    path = tmp_path / "reporting.db"
    create_database(path)
    db = connect_database(path)
    batch_id = db.execute(
        "INSERT INTO import_batch "
        "(snapshot_key, dealer_name, platform_name, template_version, converter_version, imported_at, status, is_current) "
        "VALUES ('r', '经销商', '平台', '1', '1', '2026-10-08', 'imported', 1)"
    ).lastrowid
    dealer_id = db.execute(
        "INSERT INTO dealer_platform (dealer_name, platform_name) VALUES ('经销商', '平台')"
    ).lastrowid
    db.execute(
        "INSERT INTO customer (import_batch_id, dealer_platform_id, customer_no, customer_name) VALUES (?, ?, 'C1', '客户一')",
        (batch_id, dealer_id),
    )
    products = [
        ("P1", "可口可乐瓶装", "可口可乐", "瓶", None, "1"),
        ("P2", "可口可乐箱装", "可口可乐", "箱", "12瓶/箱", None),
        ("P3", "其他品牌", "其他", "瓶", None, "1"),
    ]
    for no, name, brand, unit, conversion, base in products:
        db.execute(
            "INSERT INTO product (import_batch_id, dealer_platform_id, product_no, product_name, brand, base_unit, box_conversion, base_qty_per_box) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (batch_id, dealer_id, no, name, brand, unit, conversion, base),
        )
    orders = [("O1", "已完成", "2026-09-01 00:00:00"), ("O2", "处理中", "2026-09-01 00:00:00")]
    order_ids = {}
    for no, status, when in orders:
        order_ids[no] = db.execute(
            "INSERT INTO order_header (import_batch_id, dealer_platform_id, order_no, order_time, customer_no, order_status) "
            "VALUES (?, ?, ?, ?, 'C1', ?)",
            (batch_id, dealer_id, no, when, status),
        ).lastrowid
    for order_no, product_no, quantity, amount in [
        ("O1", "P1", 6, 120), ("O1", "P2", 2, 180), ("O1", "P3", 100, 100), ("O2", "P1", 100, 1000),
    ]:
        db.execute(
            "INSERT INTO order_line (order_id, product_no, quantity, pre_discount_amount, unit) VALUES (?, ?, ?, ?, ?)",
            (order_ids[order_no], product_no, quantity, amount, "箱" if product_no == "P2" else "瓶"),
        )
    activity_id = db.execute(
        "INSERT INTO activity (import_batch_id, activity_no, activity_name, activity_type, start_time, end_time) "
        "VALUES (?, 'A1', '可乐满减', '满减', '2026-09-01', '2026-09-30')",
        (batch_id,),
    ).lastrowid
    gift_activity_id = db.execute(
        "INSERT INTO activity (import_batch_id, activity_no, activity_name, activity_type) "
        "VALUES (?, 'A2', '可乐满赠', '满赠')", (batch_id,)
    ).lastrowid
    for activity, order_no, amount in [(activity_id, "O1", 10), (activity_id, "O2", 2), (gift_activity_id, "O1", 0)]:
        db.execute(
            "INSERT INTO activity_execution (activity_id, order_id, discount_amount) VALUES (?, ?, ?)",
            (activity, order_ids[order_no], amount),
        )
    config_id = db.execute(
        "INSERT INTO coupon_config (import_batch_id, config_no, coupon_name, config_status) "
        "VALUES (?, 'CC1', '可乐券', '启用')", (batch_id,)
    ).lastrowid
    db.execute(
        "INSERT INTO coupon_use_rule (coupon_config_id, coupon_type, validity_mode, use_start_at, use_end_at, max_use_per_coupon, rule_status) "
        "VALUES (?, '返券', '固定期限', '2026-09-01', '2026-09-30', 1, '启用')", (config_id,)
    )
    for order_no, amount in [("O1", 5), ("O2", 5), (None, 3)]:
        db.execute(
            "INSERT INTO coupon_redemption (import_batch_id, order_id, coupon_no, customer_no, status, discount_amount) "
            "VALUES (?, ?, ?, 'C1', '已使用', ?)",
            (batch_id, order_ids.get(order_no), f"CP-{order_no or 'UNLINKED'}", amount),
        )
    db.commit()
    run_id = calculate_batch(db, batch_id, "2026-09-22")
    yield db, {"batch_id": batch_id, "run_id": run_id, "activity_id": activity_id, "gift_activity_id": gift_activity_id, "config_id": config_id}
    db.close()
