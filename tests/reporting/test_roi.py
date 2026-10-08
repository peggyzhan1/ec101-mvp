from ec101.reporting.roi import activity_roi, base_qty, box_factor, coupon_roi, query_roi


def test_quantity_helpers_cover_bottle_can_box_and_missing_conversion():
    assert box_factor("12瓶/箱") == 12
    assert box_factor(None, "24") == 24
    assert box_factor("无") is None
    assert base_qty(6, "瓶") == 6
    assert base_qty(8, "罐") == 8
    assert base_qty(2, "箱", "12瓶/箱") == 24
    assert base_qty(2, "箱") is None
    assert base_qty(2, "件") is None


def test_activity_roi_uses_completed_participating_coca_cola_orders_only(reporting_db):
    db, ids = reporting_db

    result = activity_roi(db, ids["activity_id"])

    assert result["period"] == {"start": "2026-09-01", "end": "2026-09-30"}
    assert result["baseQuantity"] == 30
    assert result["salesAmount"] == 300
    assert result["actualAmount"] == 10
    assert result["roi"] == 30


def test_coupon_roi_uses_coupon_period_and_completed_coca_cola_orders(reporting_db):
    db, ids = reporting_db

    result = coupon_roi(db, ids["config_id"])

    assert result["period"] == {"start": "2026-09-01", "end": "2026-09-30"}
    assert result["baseQuantity"] == 30
    assert result["salesAmount"] == 300
    assert result["actualAmount"] == 5
    assert result["roi"] == 60


def test_gift_activity_has_amount_without_monetary_roi_and_missing_period_is_explicit(reporting_db):
    db, ids = reporting_db

    gift = activity_roi(db, ids["gift_activity_id"])
    all_rows = query_roi(db, ids["run_id"])

    assert gift["period"] is None
    assert gift["actualAmount"] == 0
    assert gift["roi"] is None
    assert any(row["kind"] == "activity" and row["id"] == ids["gift_activity_id"] for row in all_rows)
