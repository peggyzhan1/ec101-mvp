from ec101.contract.workbook import read_standard_workbook
from ec101.converters.zhoupu import convert_zhoupu
from tests.fixtures.zhoupu_builder import build_zhoupu_request


def test_zhoupu_maps_row_four_reports_sxd_and_xd(tmp_path):
    result = convert_zhoupu(build_zhoupu_request(tmp_path, multiple_orders=True))
    workbook = read_standard_workbook(result.workbook_path)

    assert workbook.tables["标准客户"][0]["客户编号"] == "C1"
    assert workbook.tables["标准客户"][0]["客户区域"] == "华东"
    assert workbook.tables["标准商品"][0]["商品编号"] == "P1"
    assert {row["单据编号"] for row in workbook.tables["标准订单明细"]} == {"SXD1", "SXD2"}
    first = next(row for row in workbook.tables["标准订单明细"] if row["单据编号"] == "SXD1")
    assert first["下游订单编号"] == "XD1"
    assert first["商品编号"] == "P1"
    fulfillment = next(row for row in workbook.tables["标准履约"] if row["单据编号"] == "SXD1")
    assert fulfillment["下游订单编号"] == "XD1"
    assert fulfillment["出库时间"] == "2026-09-21"
    assert fulfillment["结款状态"] == "已结款"


def test_zhoupu_uses_activity_and_coupon_inputs_without_changing_return_coupon_semantics(tmp_path):
    result = convert_zhoupu(build_zhoupu_request(tmp_path))
    workbook = read_standard_workbook(result.workbook_path)

    assert workbook.tables["标准活动"][0]["活动类型"] == "满赠"
    assert workbook.tables["标准活动核销明细"][0]["优惠金额"] == "10"
    assert workbook.tables["标准优惠券配置"][0]["券类型"] == "返券"
    redemptions = workbook.tables["标准优惠券核销明细"]
    assert [(row["订单号"], row["优惠金额"]) for row in redemptions] == [
        ("SXD1", "5"), ("", "5")
    ]
