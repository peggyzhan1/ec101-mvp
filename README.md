# EC101 数据底座与费用运营台

本项目将快马、舟谱源文件转换为统一工作簿，导入 SQLite 后由唯一的实际费用核算引擎生成费用结果。

## 本地运行

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
ec101-convert kuaima --dealer 经销商 --source order=订单.xlsx --output output
ec101-api --db ec101.db --archive-dir archives
npm --prefix web install
npm --prefix web run dev
```

桌面转换入口为 `python desktop/app.py`。Windows 打包可执行 `desktop/build_windows.ps1`。

转换输出包含 `standard.xlsx`、`sources.zip` 与 `conversion_report.txt`。运行导入 API 时，来源归档路径应由部署方纳入备份；SQLite 数据库和归档文件均不应提交到仓库。

## 范围

费用结果只来自实际活动核销与优惠券核销，由后端唯一引擎计算。未关联订单的券会展示在券汇总和未关联券清单中，但绝不进入释放候选。
