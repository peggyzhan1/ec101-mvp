from openpyxl import Workbook
import pytest

from ec101.confirmation.workbook import (
    FeeRecipientValidationError,
    read_fee_recipient_workbook,
)


HEADERS = ("费用周期", "太古客户编号", "太古客户名称", "应发金额", "备注")


def write_workbook(path, rows, headers=HEADERS, extra_sheet=False):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "应发名单"
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    if extra_sheet:
        workbook.create_sheet("多余工作表")
    workbook.save(path)
    workbook.close()


def test_recipient_workbook_preserves_text_customer_code_and_normalizes_amount(tmp_path):
    path = tmp_path / "recipients.xlsx"
    write_workbook(path, [("2026-09", "0570502563", "佳源食品商行", "500", "首批")])

    rows = read_fee_recipient_workbook(path)

    assert rows == [{
        "费用周期": "2026-09",
        "太古客户编号": "0570502563",
        "太古客户名称": "佳源食品商行",
        "应发金额": "500.00",
        "备注": "首批",
    }]


def test_recipient_workbook_accepts_lossless_integer_customer_code(tmp_path):
    path = tmp_path / "recipients.xlsx"
    write_workbook(path, [("2026-09", 570502563, "佳源食品商行", 500.25, None)])

    rows = read_fee_recipient_workbook(path)

    assert rows[0]["太古客户编号"] == "570502563"
    assert rows[0]["应发金额"] == "500.25"


@pytest.mark.parametrize("customer_code", ["5.70502563E+08", "1e9"])
def test_recipient_workbook_rejects_scientific_notation_customer_code(
    tmp_path, customer_code
):
    path = tmp_path / "recipients.xlsx"
    write_workbook(path, [("2026-09", customer_code, "佳源食品商行", "500", "")])

    with pytest.raises(FeeRecipientValidationError, match="文本"):
        read_fee_recipient_workbook(path)


@pytest.mark.parametrize("amount", [None, "", 0, -1, "abc", "1.234"])
def test_recipient_workbook_rejects_invalid_amounts(tmp_path, amount):
    path = tmp_path / "recipients.xlsx"
    write_workbook(path, [("2026-09", "0570502563", "佳源食品商行", amount, "")])

    with pytest.raises(FeeRecipientValidationError, match="应发金额"):
        read_fee_recipient_workbook(path)


def test_recipient_workbook_requires_exact_headers_and_one_sheet(tmp_path):
    wrong_headers = tmp_path / "wrong.xlsx"
    write_workbook(wrong_headers, [], headers=("费用周期", "客户编号", "客户名称", "金额", "备注"))
    with pytest.raises(FeeRecipientValidationError, match="表头"):
        read_fee_recipient_workbook(wrong_headers)

    extra_sheet = tmp_path / "extra.xlsx"
    write_workbook(extra_sheet, [], extra_sheet=True)
    with pytest.raises(FeeRecipientValidationError, match="一个工作表"):
        read_fee_recipient_workbook(extra_sheet)
