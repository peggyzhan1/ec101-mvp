from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence
from zipfile import ZIP_DEFLATED, ZipFile

from ec101.contract.schema import STANDARD_SHEETS
from ec101.contract.workbook import write_standard_workbook


@dataclass(frozen=True)
class ConversionRequest:
    platform: str
    dealer_name: str
    source_paths: Mapping[str, Sequence[Path]]
    activity_inputs: Sequence[Mapping[str, Any]]
    coupon_inputs: Sequence[Mapping[str, Any]]
    output_dir: Path
    coverage_start: str = ""
    coverage_end: str = ""


@dataclass(frozen=True)
class ConversionResult:
    workbook_path: Path
    sources_zip_path: Path
    report_path: Path
    counts: Mapping[str, int]


def to_datetime_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def to_num(value: object) -> Optional[float]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def finish_conversion(
    request: ConversionRequest,
    tables: dict[str, list[dict[str, str]]],
    report_lines: Sequence[str],
) -> ConversionResult:
    request.output_dir.mkdir(parents=True, exist_ok=True)
    workbook_path = request.output_dir / "standard.xlsx"
    sources_zip_path = request.output_dir / "sources.zip"
    report_path = request.output_dir / "conversion_report.txt"

    normalized_tables = {
        sheet: list(tables.get(sheet, ())) for sheet in STANDARD_SHEETS[1:]
    }
    start, end = _coverage_dates(normalized_tables["标准订单明细"])
    manifest = {
        "模板版本": "1.0",
        "转换工具版本": "ec101-clean-room",
        "经销商名称": request.dealer_name,
        "平台名称": request.platform,
        "数据开始日期": request.coverage_start or start,
        "数据结束日期": request.coverage_end or end,
        "生成时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_standard_workbook(workbook_path, normalized_tables, manifest)

    source_records = []
    seen_names = set()
    with ZipFile(sources_zip_path, "w", ZIP_DEFLATED) as archive:
        for role, paths in request.source_paths.items():
            for path in paths:
                if path.name in seen_names:
                    raise ValueError(f"源文件 basename 重复：{path.name}")
                seen_names.add(path.name)
                content = path.read_bytes()
                archive.writestr(path.name, content)
                source_records.append((role, path.name, len(content), sha256(content).hexdigest()))

    lines = list(report_lines)
    lines.append("")
    lines.append("源文件 SHA-256")
    for role, name, size, digest in source_records:
        lines.append(f"{role}\t{name}\t{size}\t{digest}")
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    counts = {sheet: len(rows) for sheet, rows in normalized_tables.items()}
    return ConversionResult(workbook_path, sources_zip_path, report_path, counts)


def _coverage_dates(order_rows: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    dates = []
    for row in order_rows:
        value = to_datetime_text(row.get("下单时间"))
        if len(value) >= 10:
            try:
                dates.append(datetime.strptime(value[:10], "%Y-%m-%d").date().isoformat())
            except ValueError:
                continue
    return (min(dates), max(dates)) if dates else ("", "")
