from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import xlwt

from ec101.converters.source_reader import detect, read_table


def write_sparse_ooxml(path: Path):
    workbook = """<?xml version="1.0" encoding="UTF-8"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
      xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
      <sheets><sheet name="数据" sheetId="1" r:id="rId1"/></sheets>
    </workbook>"""
    relations = """<?xml version="1.0" encoding="UTF-8"?>
    <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
      <Relationship Target="worksheets/sheet1.xml" Type="worksheet" Id="rId1"/>
    </Relationships>"""
    shared = """<?xml version="1.0" encoding="UTF-8"?>
    <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <si><t>订单号</t></si><si><t>金额</t></si><si><t>12345678901234567890</t></si>
    </sst>"""
    sheet = """<?xml version="1.0" encoding="UTF-8"?>
    <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
      <sheetData>
        <row r="1"><c r="A1" t="s"><v>0</v></c><c r="C1" t="s"><v>1</v></c></row>
        <row r="2"><c r="A2" t="s"><v>2</v></c><c r="C2"><v>12.5</v></c></row>
      </sheetData>
    </worksheet>"""
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relations)
        archive.writestr("xl/sharedStrings.xml", shared)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


def test_ooxml_reader_preserves_sparse_positions_shared_strings_and_long_ids(tmp_path):
    path = tmp_path / "sparse.xlsx"
    write_sparse_ooxml(path)

    kind, sheet_name, headers, rows = read_table(path)

    assert detect(path) == "OOXML"
    assert (kind, sheet_name) == ("OOXML", "数据")
    assert headers == ["订单号", "", "金额"]
    assert rows == [["12345678901234567890", "", "12.5"]]


def test_biff_reader_formats_dates_and_numbers(tmp_path):
    path = tmp_path / "legacy.xls"
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("旧表")
    sheet.write(0, 0, "日期")
    sheet.write(0, 1, "数量")
    date_style = xlwt.easyxf(num_format_str="YYYY-MM-DD")
    sheet.write(1, 0, datetime(2026, 9, 22), date_style)
    sheet.write(1, 1, 12.5)
    workbook.save(str(path))

    kind, sheet_name, headers, rows = read_table(path)

    assert detect(path) == "BIFF"
    assert (kind, sheet_name) == ("BIFF", "旧表")
    assert headers == ["日期", "数量"]
    assert rows == [["2026-09-22 00:00:00", "12.5"]]


def test_gbk_html_reader_supports_zhoupu_header_row_four(tmp_path):
    path = tmp_path / "zhoupu.xls"
    html = """<html><head><meta charset="gbk"></head><body><table>
    <tr><td>报表名称</td></tr><tr><td>导出人</td></tr><tr><td>导出时间</td></tr>
    <tr><td>订单号</td><td>客户</td></tr>
    <tr><td>12345678901234567890</td><td>门店甲</td></tr>
    </table></body></html>"""
    path.write_bytes(html.encode("gbk"))

    kind, sheet_name, headers, rows = read_table(path, header_row=4)

    assert detect(path) == "HTML"
    assert (kind, sheet_name) == ("HTML", None)
    assert headers == ["订单号", "客户"]
    assert rows == [["12345678901234567890", "门店甲"]]
