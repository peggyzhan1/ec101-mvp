from urllib.error import HTTPError

import pytest

from .conftest import get_json


def test_roi_api_uses_saved_data(api_server):
    status, payload = get_json(f"{api_server}/api/roi")

    assert status == 200
    assert isinstance(payload["items"], list)


def test_verification_api_returns_workbook_and_missing_run_is_404(api_server, api_seed):
    from urllib.request import urlopen

    with urlopen(f"{api_server}/api/verification/{api_seed['latest_a']}") as response:
        assert response.status == 200
        assert response.headers["Content-Type"].startswith("application/vnd.openxmlformats")
        assert response.read()[:2] == b"PK"

    with pytest.raises(HTTPError) as error:
        get_json(f"{api_server}/api/verification/99999")
    assert error.value.code == 404
