from datetime import date, datetime
from hashlib import sha256
from zipfile import ZipFile

from ec101.contract.schema import STANDARD_SHEETS
from ec101.contract.workbook import read_standard_workbook
from ec101.converters.common import (
    ConversionRequest,
    finish_conversion,
    to_datetime_text,
    to_num,
)


def test_value_normalizers():
    assert to_datetime_text(datetime(2026, 9, 22, 8, 30, 1)) == "2026-09-22 08:30:01"
    assert to_datetime_text(date(2026, 9, 22)) == "2026-09-22"
    assert to_datetime_text(None) == ""
    assert to_num("1,234.50") == 1234.5
    assert to_num(3) == 3.0
    assert to_num("") is None
    assert to_num("不是数字") is None


def test_finish_conversion_writes_standard_package_and_report(tmp_path):
    first = tmp_path / "orders.xls"
    second = tmp_path / "coupons.xlsx"
    first.write_bytes(b"orders-source")
    second.write_bytes(b"coupons-source")
    output_dir = tmp_path / "output"
    request = ConversionRequest(
        platform="测试平台",
        dealer_name="测试经销商",
        source_paths={"订单": [first], "优惠券": [second]},
        activity_inputs=[],
        coupon_inputs=[],
        output_dir=output_dir,
    )
    tables = {sheet: [] for sheet in STANDARD_SHEETS[1:]}
    tables["标准订单明细"] = [
        {"单据编号": "O2", "下单时间": "2026-09-30 23:59:59"},
        {"单据编号": "O1", "下单时间": "2026-09-01 00:00:00"},
    ]

    result = finish_conversion(request, tables, ["转换完成"])

    assert result.workbook_path == output_dir / "standard.xlsx"
    assert result.sources_zip_path == output_dir / "sources.zip"
    assert result.report_path == output_dir / "conversion_report.txt"
    assert result.counts["标准订单明细"] == 2
    with ZipFile(result.sources_zip_path) as archive:
        assert sorted(archive.namelist()) == ["coupons.xlsx", "orders.xls"]
        assert archive.read("orders.xls") == b"orders-source"
    report = result.report_path.read_text(encoding="utf-8")
    assert sha256(b"orders-source").hexdigest() in report
    assert sha256(b"coupons-source").hexdigest() in report
    restored = read_standard_workbook(result.workbook_path)
    assert restored.manifest["数据开始日期"] == "2026-09-01"
    assert restored.manifest["数据结束日期"] == "2026-09-30"
    assert restored.manifest["经销商名称"] == "测试经销商"
    assert restored.manifest["平台名称"] == "测试平台"


def test_explicit_coverage_dates_are_preserved(tmp_path):
    source = tmp_path / "source.xls"
    source.write_bytes(b"source")
    request = ConversionRequest(
        platform="平台",
        dealer_name="经销商",
        source_paths={"订单": [source]},
        activity_inputs=[],
        coupon_inputs=[],
        output_dir=tmp_path / "output",
        coverage_start="2026-08-01",
        coverage_end="2026-08-31",
    )
    tables = {sheet: [] for sheet in STANDARD_SHEETS[1:]}

    result = finish_conversion(request, tables, [])

    manifest = read_standard_workbook(result.workbook_path).manifest
    assert (manifest["数据开始日期"], manifest["数据结束日期"]) == (
        "2026-08-01", "2026-08-31"
    )
