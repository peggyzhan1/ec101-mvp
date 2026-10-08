from ec101.api.queries import list_coupon_summaries, list_unlinked_coupons

from .conftest import get_json


def test_coupon_summary_derives_linked_count_and_exposes_all_metrics(api_db, api_seed):
    result = list_coupon_summaries(api_db, api_seed["latest_a"], limit=10, offset=0)

    assert result["total"] == 1
    assert result["items"][0] == {
        "calculationRunId": api_seed["latest_a"],
        "couponConfigId": result["items"][0]["couponConfigId"],
        "usedCount": 2,
        "usedAmount": 8,
        "linkedCount": 1,
        "linkedAmount": 5,
        "releasableCount": 1,
        "releasableAmount": 5,
        "unlinkedCount": 1,
        "unlinkedAmount": 3,
        "settleStatus": None,
    }


def test_unlinked_coupon_rows_include_business_visible_fields(api_db, api_seed):
    result = list_unlinked_coupons(api_db, api_seed["latest_a"], limit=1, offset=0)

    assert result["total"] == 1
    assert result["items"] == [{
        "couponRedemptionId": result["items"][0]["couponRedemptionId"],
        "couponNo": "CP2",
        "customerNo": "C1",
        "customerName": "客户一",
        "status": "已使用",
        "discountAmount": 3,
    }]


def test_coupon_http_routes(api_server):
    status, summaries = get_json(f"{api_server}/api/fee-tpm/coupons?limit=1")
    assert status == 200
    assert summaries["total"] == 2
    assert summaries["items"][0]["linkedCount"] == 1
    status, unlinked = get_json(f"{api_server}/api/fee-tpm/coupons/unlinked?limit=1")
    assert status == 200
    assert unlinked["total"] == 2
    assert unlinked["items"][0]["couponNo"] == "CP2"
