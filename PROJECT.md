# EC101 数据底座与费用运营台

## Purpose

将快马、舟谱等经销商平台导出的业务数据转换为统一标准工作簿，导入 SQLite，并以现行 `calculation_engine` 的实际核算行为生成可追溯的费用 RESULT。

## Current capabilities

当前仓库处于净室重建的规格阶段，尚无运行代码。已确认的目标能力包括平台转换、标准数据导入、实际费用核算、业务查询、费用运营展示和 ROI。

## How to run

尚未实现。运行方式将在第一个可用纵向切片完成后补充。

## Main flow

平台源文件 → 平台转换器 → `standard.xlsx` + `sources.zip` → 校验入库 → 唯一实际核算引擎 → RESULT → API → 费用运营台。

## Important files

- `docs/superpowers/specs/2026-10-08-ec101-clean-room-rebuild-design.md`：净室重建的范围、架构、核算口径和验收标准。

## Current limits and next step

第一期定位为本地单机业务工具，不包含认证、权限、ERP 支付或理论权益重算。下一步是评审重建规格，确认后生成逐文件实施计划。
