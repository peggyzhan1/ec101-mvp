from ec101.api.queries import list_business_rows, list_release_candidates
from urllib.parse import urlencode

from .conftest import get_json


def test_business_rows_support_filter_search_and_pagination(api_db):
    result = list_business_rows(
        api_db, "customers", dealer="测试经销商", platform="快马",
        query="客户一", limit=1, offset=0,
    )

    assert result["total"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0]["customerNo"] == "C1"


def test_release_candidates_use_latest_run_and_candidate_filter(api_db, api_seed):
    result = list_release_candidates(
        api_db, api_seed["batch_a"], candidate=True, query="O1", limit=10, offset=0
    )

    assert result["total"] == 1
    assert result["items"][0]["orderNo"] == "O1"
    assert result["items"][0]["isCandidate"] is True


def test_business_and_release_http_routes(api_server, api_seed):
    query = urlencode({"dealer": "测试经销商", "limit": 1})
    status, business = get_json(f"{api_server}/api/business/customers?{query}")
    assert status == 200
    assert business["total"] == 1
    status, release = get_json(
        f"{api_server}/api/imports/{api_seed['batch_a']}/release?candidate=true"
    )
    assert status == 200
    assert release["items"][0]["isCandidate"] is True
