# EC101 数据底座与费用运营台

## Purpose

将快马、舟谱等经销商平台导出的业务数据转换为统一标准工作簿，导入 SQLite，并以现行 `calculation_engine` 的实际核算行为生成可追溯的费用 RESULT。

## Current capabilities

已完成净室重建的最小可运行链路：平台转换、标准数据导入、唯一实际费用核算、业务/API 查询、费用运营页面与 ROI。导入时标准工作簿为必填；来源文件包为可选，上传时会归档并记录 SHA-256，未上传时仍可完成导入和核算。

## How to run

运行方式见 `README.md`。转换器、API 与 Web 管理端均可在本地启动。

## Main flow

平台源文件 → 平台转换器 → `standard.xlsx` + `sources.zip` → 校验入库 → 唯一实际核算引擎 → RESULT → API → 费用运营台。

## Important files

- `src/ec101/calculation/engine.py`：唯一实际费用核算引擎。
- `desktop/app.py`：本地转换桌面入口。
- `web/`：费用运营管理端。
- `docs/实际费用核算口径.md`：核算边界与未关联券处理。

## Current limits and next step

第一期定位为本地单机工具，不包含认证、权限、ERP 支付或理论权益重算。下一步可使用真实金标数据执行可选验收，并根据运营使用情况补充权限与部署方案。
