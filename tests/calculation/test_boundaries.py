import sqlite3

import pytest

from ec101.calculation.engine import calculate_batch


def test_failed_calculation_leaves_no_partial_result(db, seed_batch):
    seeded = seed_batch(
        orders=[
            {"order_no": "O1", "status": "已完成", "order_time": "2026-09-01 00:00:00"},
        ],
        activity_amounts=[("O1", 10)],
        coupons=[],
    )
    db.execute(
        "CREATE TRIGGER stop_activity_summary BEFORE INSERT ON activity_fee_summary "
        "BEGIN SELECT RAISE(ABORT, 'stop'); END"
    )
    db.commit()

    with pytest.raises(sqlite3.IntegrityError, match="stop"):
        calculate_batch(db, seeded["batch_id"], "2026-09-22")

    for table in (
        "calculation_run", "release_candidate", "activity_fee_summary",
        "coupon_fee_summary", "calculation_quality_issue",
    ):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
