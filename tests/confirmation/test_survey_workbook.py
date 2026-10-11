from openpyxl import Workbook
import pytest

from ec101.confirmation.surveys import SurveyValidationError
from ec101.confirmation.workbook import read_survey_workbook


HEADERS = (
    "费用周期", "太古客户编号", "太古客户名称", "是否收到本期全部协议费用",
    "未收到原因", "补充说明", "答卷手机号", "提交时间", "问卷星原始序号",
)


def write_survey(path, headers=HEADERS, customer_code="0570502563"):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "问卷答卷"
    sheet.append(headers)
    sheet.append((
        "2026-09", customer_code, "佳源食品商行", "已收到", "", "", "13800000000",
        "2026-10-09 16:15:00", "1",
    ))
    workbook.save(path)
    workbook.close()


def test_survey_workbook_reads_exact_contract_and_preserves_customer_code(tmp_path):
    path = tmp_path / "survey.xlsx"
    write_survey(path)

    rows = read_survey_workbook(path)

    assert rows[0]["太古客户编号"] == "0570502563"
    assert rows[0]["是否收到本期全部协议费用"] == "已收到"
    assert rows[0]["答卷手机号"] == "13800000000"


@pytest.mark.parametrize("forbidden", ["第三方订单号", "销售凭证号", "主券号", "应发金额"])
def test_survey_workbook_rejects_forbidden_or_extra_columns(tmp_path, forbidden):
    path = tmp_path / "survey.xlsx"
    write_survey(path, headers=(*HEADERS, forbidden))

    with pytest.raises(SurveyValidationError, match="表头"):
        read_survey_workbook(path)


def test_survey_workbook_rejects_scientific_notation_customer_code(tmp_path):
    path = tmp_path / "survey.xlsx"
    write_survey(path, customer_code="5.70502563E+08")

    with pytest.raises(SurveyValidationError, match="文本"):
        read_survey_workbook(path)
