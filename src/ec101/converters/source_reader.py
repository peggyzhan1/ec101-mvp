from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import re
from typing import Literal, Optional
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import xlrd


Format = Literal["OOXML", "BIFF", "HTML"]
_BIFF_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def detect(path: Path) -> Format:
    prefix = path.read_bytes()[:4096]
    if prefix.startswith(b"PK\x03\x04"):
        return "OOXML"
    if prefix.startswith(_BIFF_SIGNATURE):
        return "BIFF"
    sample = prefix.lstrip(b"\xef\xbb\xbf\x00\t\r\n ").lower()
    if b"<html" in sample or b"<table" in sample:
        return "HTML"
    raise ValueError(f"无法识别源文件格式：{path.name}")


def read_table(
    path: Path,
    header_row: int = 1,
) -> tuple[str, Optional[str], list[str], list[list[str]]]:
    if header_row < 1:
        raise ValueError("header_row 必须从 1 开始")
    kind = detect(path)
    if kind == "OOXML":
        sheet_name, matrix = _read_ooxml(path)
    elif kind == "BIFF":
        sheet_name, matrix = _read_biff(path)
    else:
        sheet_name, matrix = None, _read_html(path)
    if len(matrix) < header_row:
        raise ValueError(f"{path.name} 不包含第 {header_row} 行表头")
    headers = matrix[header_row - 1]
    width = len(headers)
    rows = []
    for row in matrix[header_row:]:
        normalized = (row + [""] * width)[:width]
        if any(value.strip() for value in normalized):
            rows.append(normalized)
    return kind, sheet_name, headers, rows


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Za-z]+", reference)
    if not letters:
        return 0
    index = 0
    for letter in letters.group(0).upper():
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


def _read_ooxml(path: Path) -> tuple[str, list[list[str]]]:
    with ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheet = workbook.find(f".//{{{_MAIN_NS}}}sheet")
        if sheet is None:
            raise ValueError(f"{path.name} 没有工作表")
        sheet_name = sheet.attrib.get("name", "")
        relation_id = sheet.attrib.get(f"{{{_DOC_REL_NS}}}id")
        relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = None
        for relation in relations.findall(f"{{{_PKG_REL_NS}}}Relationship"):
            if relation.attrib.get("Id") == relation_id:
                target = relation.attrib.get("Target")
                break
        if not target:
            raise ValueError(f"{path.name} 的首个工作表关系缺失")
        target_path = PurePosixPath(target.lstrip("/"))
        if not str(target_path).startswith("xl/"):
            target_path = PurePosixPath("xl") / target_path

        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in shared_root.findall(f"{{{_MAIN_NS}}}si"):
                shared_strings.append("".join(
                    node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")
                ))

        worksheet = ET.fromstring(archive.read(str(target_path)))
        matrix: list[list[str]] = []
        for row_node in worksheet.findall(f".//{{{_MAIN_NS}}}row"):
            values: dict[int, str] = {}
            for cell in row_node.findall(f"{{{_MAIN_NS}}}c"):
                index = _column_index(cell.attrib.get("r", "A1"))
                cell_type = cell.attrib.get("t")
                value_node = cell.find(f"{{{_MAIN_NS}}}v")
                value = "" if value_node is None or value_node.text is None else value_node.text
                if cell_type == "s" and value:
                    value = shared_strings[int(value)]
                elif cell_type == "inlineStr":
                    value = "".join(
                        node.text or "" for node in cell.iter(f"{{{_MAIN_NS}}}t")
                    )
                values[index] = value
            width = max(values, default=-1) + 1
            matrix.append([values.get(index, "") for index in range(width)])
    return sheet_name, _pad_matrix(matrix)


def _read_biff(path: Path) -> tuple[str, list[list[str]]]:
    workbook = xlrd.open_workbook(str(path))
    sheet = workbook.sheet_by_index(0)
    matrix = []
    for row_index in range(sheet.nrows):
        row = []
        for column_index in range(sheet.ncols):
            cell = sheet.cell(row_index, column_index)
            if cell.ctype == xlrd.XL_CELL_DATE:
                value = xlrd.xldate_as_datetime(cell.value, workbook.datemode).strftime("%Y-%m-%d %H:%M:%S")
            elif cell.ctype == xlrd.XL_CELL_NUMBER:
                value = _number_text(cell.value)
            elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                value = ""
            elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                value = "TRUE" if cell.value else "FALSE"
            else:
                value = str(cell.value)
            row.append(value)
        matrix.append(row)
    return sheet.name, matrix


def _number_text(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return format(value, ".15g")


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table" and self._table is None:
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None


def _read_html(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"无法解码 HTML 文件：{path.name}")
    parser = _TableParser()
    parser.feed(text)
    if not parser.tables:
        raise ValueError(f"{path.name} 中没有表格")
    return _pad_matrix(parser.tables[0])


def _pad_matrix(matrix: list[list[str]]) -> list[list[str]]:
    width = max((len(row) for row in matrix), default=0)
    return [row + [""] * (width - len(row)) for row in matrix]
