import pytest

from ec101.db import connect_database, create_database


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "calculation.db"
    create_database(path)
    connection = connect_database(path)
    yield connection
    connection.close()


@pytest.fixture
def seed_batch(db):
    def seed(*, orders, activity_amounts=(), coupons=(), config_count=1):
        batch_id = db.execute(
            "INSERT INTO import_batch "
            "(snapshot_key, dealer_name, platform_name, coverage_start, coverage_end, "
            "template_version, converter_version, imported_at, status, is_current) "
            "VALUES ('snapshot', '经销商', '平台', '2026-09-01', '2026-09-30', "
            "'1.0', 'test', '2026-10-08', 'imported', 1)"
        ).lastrowid
        dealer_platform_id = db.execute(
            "INSERT INTO dealer_platform (dealer_name, platform_name) VALUES ('经销商', '平台')"
        ).lastrowid
        order_ids = {}
        for order in orders:
            order_id = db.execute(
                "INSERT INTO order_header "
                "(import_batch_id, dealer_platform_id, order_no, order_time, customer_no, order_status) "
                "VALUES (?, ?, ?, ?, 'C1', ?)",
                (batch_id, dealer_platform_id, order["order_no"], order.get("order_time"), order["status"]),
            ).lastrowid
            order_ids[order["order_no"]] = order_id

        activity_id = None
        if activity_amounts:
            activity_id = db.execute(
                "INSERT INTO activity "
                "(import_batch_id, activity_no, activity_name, activity_type) "
                "VALUES (?, 'A1', '活动一', '满减')",
                (batch_id,),
            ).lastrowid
            for order_no, amount in activity_amounts:
                db.execute(
                    "INSERT INTO activity_execution "
                    "(activity_id, order_id, activity_name, discount_amount) VALUES (?, ?, '活动一', ?)",
                    (activity_id, order_ids[order_no], amount),
                )

        config_ids = []
        for index in range(config_count):
            config_ids.append(db.execute(
                "INSERT INTO coupon_config "
                "(import_batch_id, config_no, coupon_name, config_status) VALUES (?, ?, ?, '启用')",
                (batch_id, f"CC{index + 1}", f"券配置{index + 1}"),
            ).lastrowid)
        for index, (order_no, amount) in enumerate(coupons, start=1):
            db.execute(
                "INSERT INTO coupon_redemption "
                "(import_batch_id, order_id, coupon_no, customer_no, status, discount_amount) "
                "VALUES (?, ?, ?, 'C1', '已使用', ?)",
                (batch_id, order_ids.get(order_no), f"CP{index}", amount),
            )
        db.commit()
        return {
            "batch_id": batch_id,
            "order_ids": order_ids,
            "activity_id": activity_id,
            "config_ids": config_ids,
        }
    return seed
