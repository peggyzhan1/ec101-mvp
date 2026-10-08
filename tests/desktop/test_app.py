from pathlib import Path

import pytest

from desktop.app import build_request, run_conversion


def test_build_request_selects_platform_and_maps_source_roles(tmp_path):
    customer = tmp_path / "customers.xlsx"
    customer.touch()
    request = build_request({
        "platform": "kuaima", "dealer_name": "经销商", "output_dir": str(tmp_path / "out"),
        "customer": str(customer), "order": "", "activity_inputs": [], "coupon_inputs": [],
    })

    assert request.platform == "快马"
    assert request.source_paths == {"customer": [customer]}


def test_build_request_rejects_missing_essential_fields(tmp_path):
    with pytest.raises(ValueError, match="经销商"):
        build_request({"platform": "zhoupu", "dealer_name": "", "output_dir": str(tmp_path)})
    with pytest.raises(ValueError, match="至少"):
        build_request({"platform": "zhoupu", "dealer_name": "经销商", "output_dir": str(tmp_path)})


def test_run_conversion_delegates_by_platform(monkeypatch, tmp_path):
    source = tmp_path / "source.xlsx"
    source.touch()
    request = build_request({"platform": "kuaima", "dealer_name": "经销商", "output_dir": str(tmp_path / "out"), "order": str(source)})
    called = []
    monkeypatch.setattr("desktop.app.convert_kuaima", lambda value: called.append(value) or "done")

    assert run_conversion(request) == "done"
    assert called == [request]
