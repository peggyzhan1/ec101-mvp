from urllib.error import HTTPError

import pytest

from ec101.api.queries import get_fee_overview, list_activity_summaries

from .conftest import get_json


def test_current_overview_uses_latest_run_for_every_current_batch(api_db, api_seed):
    overview = get_fee_overview(api_db, None)

    assert overview["calculationRunIds"] == [api_seed["latest_a"], api_seed["latest_b"]]
    assert overview["activityBenefit"] == 20
    assert overview["couponBenefit"] == 16
    assert overview["totalBenefit"] == 36
    assert overview["releasedActivityBenefit"] == 20
    assert overview["releasedCouponBenefit"] == 10


def test_historical_overview_and_activity_pagination_are_exact(api_db, api_seed):
    overview = get_fee_overview(api_db, api_seed["old_run"])
    activities = list_activity_summaries(api_db, api_seed["old_run"], limit=1, offset=0)

    assert overview["calculationRunIds"] == [api_seed["old_run"]]
    assert overview["totalBenefit"] == 18
    assert activities["total"] == 1
    assert len(activities["items"]) == 1
    with pytest.raises(LookupError):
        get_fee_overview(api_db, 99999)


def test_fee_http_routes_and_missing_history_never_falls_back(api_server, api_seed):
    for path in ("overview", "activities", "issues", "settlements"):
        status, payload = get_json(f"{api_server}/api/fee-tpm/{path}")
        assert status == 200
        assert payload is not None

    with pytest.raises(HTTPError) as error:
        get_json(f"{api_server}/api/fee-tpm/overview?calculationRunId=99999")
    assert error.value.code == 404
