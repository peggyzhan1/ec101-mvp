import argparse
from pathlib import Path

from .common import ConversionRequest
from .kuaima import convert_kuaima


def _source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("源文件参数必须使用 role=path")
    role, path = value.split("=", 1)
    return role, Path(path)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ec101-convert")
    parser.add_argument("platform", choices=("kuaima",))
    parser.add_argument("--dealer", required=True)
    parser.add_argument("--source", action="append", type=_source, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--coverage-start", default="")
    parser.add_argument("--coverage-end", default="")
    args = parser.parse_args(argv)
    sources = {}
    for role, path in args.source:
        sources.setdefault(role, []).append(path)
    request = ConversionRequest(
        platform="快马",
        dealer_name=args.dealer,
        source_paths=sources,
        activity_inputs=[],
        coupon_inputs=[],
        output_dir=args.output,
        coverage_start=args.coverage_start,
        coverage_end=args.coverage_end,
    )
    result = convert_kuaima(request)
    print(result.workbook_path)
    print(result.sources_zip_path)
    print(result.report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
