from ec101.contract.workbook import read_standard_workbook
from ec101.converters.kuaima import (
    convert_kuaima,
    infer_activity_type,
    parse_policy_activity_name,
)
from tests.fixtures.kuaima_builder import build_kuaima_request


def test_policy_activity_name_and_type_inference():
    policy = "参与[可口可乐满减]组合金额满¥300，立减¥15活动"
    assert parse_policy_activity_name(policy) == "可口可乐满减"
    assert parse_policy_activity_name("参与【满赠优惠】送赠品活动") == "满赠优惠"
    assert infer_activity_type(policy, "可口可乐满减") == "满减"
    assert infer_activity_type("组合金额满¥100，送赠品活动", "满赠优惠") == "满赠"
    assert infer_activity_type("消费后返券", "返券") == "返券"


def test_kuaima_maps_and_aggregates_source_rows(tmp_path):
    result = convert_kuaima(build_kuaima_request(tmp_path, duplicate_order_file=True))
    workbook = read_standard_workbook(result.workbook_path)

    assert result.workbook_path.name == "standard.xlsx"
    assert result.sources_zip_path.name == "sources.zip"
    assert result.report_path.name == "conversion_report.txt"
    assert len(workbook.tables["标准客户"]) == 1
    assert len(workbook.tables["标准商品"]) == 1
    assert len(workbook.tables["标准订单明细"]) == 1
    assert len(workbook.tables["标准活动"]) == 1
    assert len(workbook.tables["标准活动核销明细"]) == 1
    execution = workbook.tables["标准活动核销明细"][0]
    assert execution["订单号"] == "O1"
    assert execution["优惠金额"] == "10"
    order = workbook.tables["标准订单明细"][0]
    assert order["活动编号"] == workbook.tables["标准活动"][0]["活动编号"]
    assert order["优惠券编号"] == "CP1"
    assert workbook.tables["标准履约"][0]["履约订单状态"] == "已完成"
    redemptions = workbook.tables["标准优惠券核销明细"]
    assert [(row["优惠券编号"], row["订单号"]) for row in redemptions] == [
        ("CP1", "O1"), ("CP2", "")
    ]


def test_kuaima_creates_fallback_master_rows(tmp_path):
    result = convert_kuaima(build_kuaima_request(tmp_path, fallback=True))
    workbook = read_standard_workbook(result.workbook_path)

    assert workbook.tables["标准客户"] == [{
        **{column: "" for column in workbook.tables["标准客户"][0]},
        "客户编号": "C-MISSING",
        "客户名称": "客户一",
    }]
    assert workbook.tables["标准商品"][0]["商品编号"] == "P-MISSING"
    assert workbook.tables["标准商品"][0]["商品名称"] == "商品一"
