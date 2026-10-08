from pathlib import Path
from typing import Mapping

from ec101.converters.common import ConversionRequest, ConversionResult
from ec101.converters.kuaima import convert_kuaima
from ec101.converters.zhoupu import convert_zhoupu


_PLATFORMS = {"kuaima": "快马", "zhoupu": "舟谱", "快马": "快马", "舟谱": "舟谱"}
_RESERVED = {"platform", "dealer_name", "output_dir", "coverage_start", "coverage_end", "activity_inputs", "coupon_inputs"}


def build_request(form_values: Mapping[str, object]) -> ConversionRequest:
    platform_key = str(form_values.get("platform", "")).strip()
    if platform_key not in _PLATFORMS:
        raise ValueError("请选择快马或舟谱平台")
    dealer_name = str(form_values.get("dealer_name", "")).strip()
    if not dealer_name:
        raise ValueError("请填写经销商名称")
    output_dir = Path(str(form_values.get("output_dir", "")).strip())
    if not str(output_dir):
        raise ValueError("请选择输出目录")
    source_paths = {}
    for role, value in form_values.items():
        if role in _RESERVED or not value:
            continue
        paths = [Path(item.strip()) for item in str(value).split(";") if item.strip()]
        if paths:
            source_paths[role] = paths
    if not source_paths:
        raise ValueError("至少选择一个源文件")
    return ConversionRequest(
        platform=_PLATFORMS[platform_key], dealer_name=dealer_name, source_paths=source_paths,
        activity_inputs=form_values.get("activity_inputs", []), coupon_inputs=form_values.get("coupon_inputs", []),
        output_dir=output_dir, coverage_start=str(form_values.get("coverage_start", "")),
        coverage_end=str(form_values.get("coverage_end", "")),
    )


def run_conversion(request: ConversionRequest) -> ConversionResult:
    return convert_kuaima(request) if request.platform == "快马" else convert_zhoupu(request)


def main() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title("EC101 数据转换")
    values = {name: tk.StringVar() for name in ("platform", "dealer_name", "output_dir", "customer", "product", "order", "sales", "activity", "coupon")}
    values["platform"].set("kuaima")
    for row, (name, variable) in enumerate(values.items()):
        tk.Label(root, text=name).grid(row=row, column=0, sticky="w", padx=8, pady=4)
        tk.Entry(root, textvariable=variable, width=54).grid(row=row, column=1, padx=8, pady=4)
        if name not in {"platform", "dealer_name"}:
            tk.Button(root, text="选择", command=lambda key=name: values[key].set(filedialog.askopenfilename() if key != "output_dir" else filedialog.askdirectory())).grid(row=row, column=2)
    def submit():
        try:
            result = run_conversion(build_request({key: value.get() for key, value in values.items()}))
            messagebox.showinfo("完成", f"标准工作簿：{result.workbook_path}\n来源归档：{result.sources_zip_path}")
        except Exception as exc:
            messagebox.showerror("无法转换", str(exc))
    tk.Button(root, text="转换", command=submit).grid(row=len(values), column=1, pady=12)
    root.mainloop()


if __name__ == "__main__":
    main()
