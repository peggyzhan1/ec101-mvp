# EC101 Clean-Room Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从空仓库重建 EC101 的快马/舟谱转换、标准数据导入、唯一实际费用核算、优惠券汇总、查询 API、费用运营台和 Windows 转换入口。

**Architecture:** Python 包按 `contract → importing → calculation → api/reporting` 单向依赖，平台差异只存在于 `converters`。SQLite 保存 CORE 与 RESULT；React 前端只消费 API。现行 `calculation_engine` 的实际路径是核算基线，理论重算支线完全排除，唯一新增行为是生成 `coupon_fee_summary` 并展示未关联券。

**Tech Stack:** Python 3.9+、SQLite、openpyxl、xlrd、pytest、stdlib `http.server`、Tkinter/PyInstaller、Node.js 22.13+、React 19、TypeScript、Vite、Vitest、Testing Library。

**Spec:** `docs/superpowers/specs/2026-10-08-ec101-clean-room-rebuild-design.md`

## Global Constraints

- 不复制旧仓库工作树或 Git 历史；只迁移规格允许的契约、现行行为和脱敏测试断言。
- 不提交 `.db`、备份、真实业务文件、`sources.zip`、构建缓存或生成输出；允许提交 `tests/fixtures/` 下的脱敏最小 Excel 测试样本。
- `src/ec101/calculation` 是唯一核算入口；不得出现快马/舟谱分支、理论权益重算或第二核算器。
- 实际核算必须复现现行 `calculation_engine`：批次金额、参与订单、T-2、逐单候选、活动汇总和状态更新保持一致。
- 唯一扩展是每次核算写 `coupon_fee_summary`，并让未关联券数量、金额和明细可查询、可展示、不可释放。
- 无法唯一归属券配置时使用 `coupon_config_id = NULL`；不得按券号、名称或活动编号猜测。
- 活动汇总继续使用现行 `COUNT(*)` 行为，不改成去重订单数。
- 导入服务不写 RESULT；API 和前端不重复计算金额、参与订单或 T-2。
- 第一期为本地单机工具，不实现认证、RBAC、财经云、异常协同、支付、ERP 或生产数据库迁移。
- 每个任务遵循 TDD，任务完成时提交一次范围单一的 commit。

## Review Focus

- 核算日边界：订单时间恰好等于 T-2 零点时必须不可释放；由 Task 4 的 `test_release_cutoff_is_strict` 固定。
- 未关联券：必须计入券总额和未关联汇总，但不得进入参与订单或可释放金额；由 Task 4 的 `test_unlinked_coupon_is_visible_but_not_releasable` 固定。
- 多券配置：无法唯一归属时必须进入 `coupon_config_id=NULL` 汇总桶；由 Task 4 的 `test_multiple_coupon_configs_use_null_bucket` 固定。
- 覆盖区间替换：重复导入只能关闭相同经销商、平台、开始日期、结束日期的旧批次；由 Task 3 的 `test_current_batch_switch_is_scoped_to_same_snapshot_window` 固定。
- 大编号和稀疏表格：订单号、券号不得被科学计数或移位；由 Task 2 和 Task 5 的长编号/稀疏 OOXML 测试固定。

## File Structure

```text
pyproject.toml                         Python 包、依赖和 pytest 配置
.gitignore                             运行库、业务数据、归档和构建产物规则
db/ec101_standard_sqlite.sql           现行标准库 DDL 基线
src/ec101/db.py                        SQLite 创建和连接
src/ec101/contract/schema.py           15 个标准工作表契约与行校验
src/ec101/contract/workbook.py         标准工作簿读写
src/ec101/importing/service.py         跨表校验、批次和 CORE 入库
src/ec101/calculation/engine.py        唯一实际核算与 RESULT 写入
src/ec101/converters/source_reader.py  OOXML/BIFF/HTML 源表读取
src/ec101/converters/common.py         转换请求、结果和归档
src/ec101/converters/kuaima.py         快马映射
src/ec101/converters/zhoupu.py         舟谱映射
src/ec101/converters/cli.py            命令行入口
src/ec101/reporting/roi.py             ROI 查询
src/ec101/reporting/verification.py    核验导出
src/ec101/api/queries.py               只读业务和 RESULT 查询
src/ec101/api/server.py                HTTP 路由、上传和响应
desktop/app.py                         Tkinter 薄客户端
web/src/                               React 页面、API 客户端和类型
tests/                                 Python 单元、集成和端到端测试
web/src/**/*.test.tsx                  前端组件和页面测试
docs/                                  数据字典、核算口径和运行说明
```

---

### Task 1: Project Foundation and Standard Database

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `db/ec101_standard_sqlite.sql`
- Create: `src/ec101/__init__.py`
- Create: `src/ec101/db.py`
- Create: `tests/conftest.py`
- Create: `tests/test_schema.py`

**Interfaces:**
- Consumes: approved spec and the current `mvp/ddl/ec101_standard_sqlite.sql` contract.
- Produces: `connect_database(path: Path) -> sqlite3.Connection`; `create_database(path: Path) -> None`; `empty_db: sqlite3.Connection` pytest fixture.

- [ ] **Step 1: Write failing schema tests**

Add `test_create_database_builds_current_standard_schema`, `test_foreign_keys_are_enabled`, `test_coupon_summary_accepts_null_config`, and `test_runtime_artifacts_are_ignored`. Assert the current 25-table set, current foreign keys/unique constraints, nullable `coupon_fee_summary.coupon_config_id`, and ignored `*.db`, `sources.zip`, archives, raw Excel and web build directories.

- [ ] **Step 2: Run schema tests and verify failure**

Run: `python -m pytest tests/test_schema.py -v`  
Expected: FAIL because `ec101.db` and DDL do not exist.

- [ ] **Step 3: Implement the minimum database foundation**

Create the package and DDL from the current standard schema. `connect_database` must set `row_factory=sqlite3.Row` and `PRAGMA foreign_keys=ON`; `create_database` must execute the repository DDL against a new file. Configure Python 3.9+, `openpyxl`, `xlrd`, and pytest in `pyproject.toml`.

- [ ] **Step 4: Run schema tests**

Run: `python -m pytest tests/test_schema.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .gitignore pyproject.toml db src/ec101 tests/conftest.py tests/test_schema.py
git commit -m "feat: establish EC101 standard database"
```

### Task 2: Standard Workbook Contract

**Files:**
- Create: `src/ec101/contract/__init__.py`
- Create: `src/ec101/contract/schema.py`
- Create: `src/ec101/contract/workbook.py`
- Create: `tests/contract/test_schema.py`
- Create: `tests/contract/test_workbook.py`

**Interfaces:**
- Consumes: current reviewed 15-sheet contract from `mvp/standard_schema.py` and `mvp/standard_workbook.py`.
- Produces: `Issue`; `STANDARD_SHEETS`; `SHEET_COLUMNS`; `REQUIRED_COLUMNS`; `validate_rows(sheet, rows) -> list[Issue]`; `StandardWorkbook`; `read_standard_workbook(path) -> StandardWorkbook`; `write_standard_workbook(path, tables, manifest) -> None`.

- [ ] **Step 1: Write failing contract tests**

Assert the exact ordered sheet tuple beginning with `导入清单` and ending with `标准履约`; unknown columns and empty required values produce `Issue`; a workbook with reordered sheets or mismatched headers raises `ValueError`; blank rows are skipped; manifest must contain exactly one row; a 20-digit order/coupon identifier round-trips as text.

- [ ] **Step 2: Run contract tests and verify failure**

Run: `python -m pytest tests/contract -v`  
Expected: FAIL because contract modules do not exist.

- [ ] **Step 3: Implement the workbook contract**

Migrate only the reviewed constants and validation behavior. Use openpyxl read-only/write-only modes, write every cell as text, preserve fixed sheet order, and close workbooks after reading.

- [ ] **Step 4: Run contract and schema tests**

Run: `python -m pytest tests/contract tests/test_schema.py -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ec101/contract tests/contract
git commit -m "feat: add standard workbook contract"
```

### Task 3: Atomic Import Service

**Files:**
- Create: `src/ec101/importing/__init__.py`
- Create: `src/ec101/importing/service.py`
- Create: `tests/importing/test_validation.py`
- Create: `tests/importing/test_import_service.py`

**Interfaces:**
- Consumes: `StandardWorkbook`, `Issue`, and `sqlite3.Connection` from Tasks 1-2.
- Produces: `ArchiveMetadata(file_path: str, sha256: str, file_size: int)`; `ImportResult(import_batch_id: int, status: str)`; `ImportValidationError`; `validate_import(workbook, db) -> list[Issue]`; `import_snapshot(db, workbook, archive) -> ImportResult`.

- [ ] **Step 1: Write failing import validation tests**

Cover missing customer/product/activity/order references; allow coupon redemptions with an empty order number; reject a non-empty unknown coupon order; assert validation does not modify the database.

- [ ] **Step 2: Write failing atomic import tests**

Cover all CORE table mappings, order header deduplication with multiple lines, source archive metadata, status `imported`, zero RESULT rows after import, rollback on an invalid child row, and `test_current_batch_switch_is_scoped_to_same_snapshot_window` with two dealers and two coverage windows.

- [ ] **Step 3: Run import tests and verify failure**

Run: `python -m pytest tests/importing -v`  
Expected: FAIL because import service does not exist.

- [ ] **Step 4: Implement `validate_import` and `import_snapshot`**

Port the current cross-sheet validation and CORE inserts into one transaction. Remove the legacy `calc_date` parameter and any import of `actual_result_calculator`; result tables must remain empty until Task 4 calls the engine.

- [ ] **Step 5: Run import tests and the existing suite**

Run: `python -m pytest tests/importing tests/contract tests/test_schema.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ec101/importing tests/importing
git commit -m "feat: import standard workbook atomically"
```

### Task 4: Unique Calculation Engine and Coupon Summary

**Files:**
- Create: `src/ec101/calculation/__init__.py`
- Create: `src/ec101/calculation/engine.py`
- Create: `tests/calculation/test_dates.py`
- Create: `tests/calculation/test_engine.py`
- Create: `tests/calculation/test_coupon_summary.py`
- Create: `tests/calculation/test_boundaries.py`

**Interfaces:**
- Consumes: current standard tables and imported batches from Task 3.
- Produces: `parse_calc_date(calc_date: Optional[str]) -> str`; `release_cutoff(calc_date: str) -> str`; `release_reason(order_status: str, order_time: Optional[str], cutoff: str) -> tuple[bool, str]`; `calculate_batch(db: sqlite3.Connection, batch_id: int, calc_date: Optional[str] = None) -> int`; `run_calculation(db: sqlite3.Connection, import_batch_id: int) -> dict[str, Any]` with keys `calculation_run_id`, `calc_date`, `release_cutoff`, `activity_benefit`, `coupon_benefit`, `total_benefit`, `released_activity_benefit`, `released_coupon_benefit`, `participating_orders`, `released_orders`, and `status`.

- [ ] **Step 1: Write failing date and release tests**

Pin missing date, invalid `2026/09/22`, cutoff `2026-09-20 00:00:00`, non-completed status, missing time, equality at cutoff, and one second before cutoff. `test_release_cutoff_is_strict` must assert equality is not releasable.

- [ ] **Step 2: Write failing current-engine regression tests**

Seed minimal batches directly or through Task 3. Assert batch activity/coupon totals, participating-order selection, per-order candidate amounts/reasons, released totals, `COUNT(*)` activity summary behavior, noncandidate quality prompts, latest-run reads, and final batch status. Assert no import or symbol containing `promotion_calculator`, `standard_promotion`, `TemplateResult`, `theoretical`, `consistency`, or `entitlement_check` occurs in the engine source.

- [ ] **Step 3: Write failing coupon summary tests**

`test_unlinked_coupon_is_visible_but_not_releasable` must seed one released linked coupon, one pending linked coupon, and one unlinked coupon; assert `used_count=3`, totals include all three, only the eligible linked coupon contributes to releasable fields, and the unlinked coupon contributes only to unlinked fields. `test_single_coupon_config_is_attached` asserts its ID; `test_multiple_coupon_configs_use_null_bucket` asserts `coupon_config_id is None`; assert `settle_status is None`.

- [ ] **Step 4: Run calculation tests and verify failure**

Run: `python -m pytest tests/calculation -v`  
Expected: FAIL because engine functions do not exist.

- [ ] **Step 5: Implement the unique engine**

Port the current actual path in execution order. Add private `_write_coupon_summary(db, calculation_run_id, import_batch_id) -> None` after candidates exist. Do not import or reproduce any theoretical recalculation helper. Use the caller's transaction boundary consistently so one failed run leaves no partial RESULT.

- [ ] **Step 6: Run calculation and import tests**

Run: `python -m pytest tests/calculation tests/importing -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/ec101/calculation tests/calculation
git commit -m "feat: add unique actual calculation engine"
```

### Task 5: Source Reader and Conversion Contract

**Files:**
- Create: `src/ec101/converters/__init__.py`
- Create: `src/ec101/converters/source_reader.py`
- Create: `src/ec101/converters/common.py`
- Create: `tests/converters/test_source_reader.py`
- Create: `tests/converters/test_common.py`
- Create: `tests/fixtures/source/`

**Interfaces:**
- Consumes: workbook writer and schema from Task 2.
- Produces: `detect(path: Path) -> Literal['OOXML','BIFF','HTML']`; `read_table(path: Path, header_row: int = 1) -> tuple[str, Optional[str], list[str], list[list[str]]]`; `to_datetime_text(value: object) -> str`; `to_num(value: object) -> Optional[float]`; `ConversionRequest(platform: str, dealer_name: str, source_paths: Mapping[str, Sequence[Path]], activity_inputs: Sequence[Mapping[str, Any]], coupon_inputs: Sequence[Mapping[str, Any]], output_dir: Path, coverage_start: str = '', coverage_end: str = '')`; `ConversionResult(workbook_path: Path, sources_zip_path: Path, report_path: Path, counts: Mapping[str, int])`; `finish_conversion(request: ConversionRequest, tables: dict[str, list[dict[str, str]]], report_lines: Sequence[str]) -> ConversionResult`.

- [ ] **Step 1: Write failing source reader tests**

Create synthetic OOXML, BIFF and HTML fixtures. Cover sparse OOXML cells, relation attribute order, shared strings, a 20-digit identifier, BIFF dates/numbers, GBK HTML, and Zhoupu `header_row=4`.

- [ ] **Step 2: Write failing conversion contract tests**

Assert `sources.zip` contains only supplied files by basename, SHA-256 is reported, `standard.xlsx` follows Task 2, coverage dates derive from order dates when omitted, and counts/report paths are returned.

- [ ] **Step 3: Run converter foundation tests and verify failure**

Run: `python -m pytest tests/converters/test_source_reader.py tests/converters/test_common.py -v`  
Expected: FAIL because converter modules do not exist.

- [ ] **Step 4: Implement the minimal reader and common conversion layer**

Migrate the format-signature behavior; use xlrd only for BIFF. Keep all identifiers as strings and preserve sparse column positions. Common conversion code may create output files but must never connect to SQLite.

- [ ] **Step 5: Run converter foundation tests**

Run: `python -m pytest tests/converters/test_source_reader.py tests/converters/test_common.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ec101/converters tests/converters tests/fixtures/source
git commit -m "feat: add source file conversion foundation"
```

### Task 6: Kuaima Converter Vertical Slice

**Files:**
- Create: `src/ec101/converters/kuaima.py`
- Create: `src/ec101/converters/cli.py`
- Create: `tests/converters/test_kuaima.py`
- Create: `tests/e2e/test_kuaima_pipeline.py`
- Create: `tests/fixtures/kuaima/`

**Interfaces:**
- Consumes: `ConversionRequest`, `read_table`, workbook contract, import service, and calculation engine.
- Produces: `parse_policy_activity_name(text: str) -> str`; `infer_activity_type(policy_text: str, activity_name: str) -> str`; `convert_kuaima(request: ConversionRequest) -> ConversionResult`; CLI platform `kuaima`.

- [ ] **Step 1: Write failing Kuaima mapping tests**

Cover customer/product/order mapping, fallback master rows, duplicate order-detail file suppression, policy activity-name extraction, order × activity aggregation, coupon redemptions with linked and unlinked orders, order-line trace fields, fulfillment rows, and fixed output artifacts.

- [ ] **Step 2: Write a failing miniature Kuaima end-to-end test**

Convert synthetic source files, read the generated workbook, import it, run calculation for `2026-09-22`, and assert one releasable activity, one linked releasable coupon, one unlinked coupon, and matching `coupon_fee_summary`.

- [ ] **Step 3: Run Kuaima tests and verify failure**

Run: `python -m pytest tests/converters/test_kuaima.py tests/e2e/test_kuaima_pipeline.py -v`  
Expected: FAIL because Kuaima conversion does not exist.

- [ ] **Step 4: Implement the minimum Kuaima adapter and CLI route**

Migrate only the reviewed mappings and aggregation behavior. Do not move platform rules into import or calculation modules.

- [ ] **Step 5: Run Kuaima and core regression tests**

Run: `python -m pytest tests/converters/test_kuaima.py tests/e2e/test_kuaima_pipeline.py tests/calculation -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ec101/converters/kuaima.py src/ec101/converters/cli.py tests/converters/test_kuaima.py tests/e2e/test_kuaima_pipeline.py tests/fixtures/kuaima
git commit -m "feat: add Kuaima standard pipeline"
```

### Task 7: Zhoupu Converter Vertical Slice

**Files:**
- Create: `src/ec101/converters/zhoupu.py`
- Modify: `src/ec101/converters/cli.py`
- Create: `tests/converters/test_zhoupu.py`
- Create: `tests/e2e/test_zhoupu_pipeline.py`
- Create: `tests/fixtures/zhoupu/`

**Interfaces:**
- Consumes: the same platform-neutral interfaces as Task 6.
- Produces: `convert_zhoupu(request: ConversionRequest) -> ConversionResult`; CLI platform `zhoupu`.

- [ ] **Step 1: Write failing Zhoupu mapping tests**

Cover row-4 headers, customer/product alternative column names, SXD order facts, XD fulfillment/downstream identifiers, multiple order files, activity/coupon inputs, and preservation of “返券” semantics.

- [ ] **Step 2: Write a failing miniature Zhoupu end-to-end test**

Convert synthetic SXD/XD files, import, calculate, and assert the batch is visible without any platform branch in the engine. Include an unlinked coupon and assert its summary/detail behavior matches Kuaima.

- [ ] **Step 3: Run Zhoupu tests and verify failure**

Run: `python -m pytest tests/converters/test_zhoupu.py tests/e2e/test_zhoupu_pipeline.py -v`  
Expected: FAIL because Zhoupu conversion does not exist.

- [ ] **Step 4: Implement the Zhoupu adapter and CLI route**

Migrate only current reviewed field mapping. Keep XD/SXD handling in this adapter; do not add “满减” interpretation to the calculation engine.

- [ ] **Step 5: Run both platform pipelines**

Run: `python -m pytest tests/converters tests/e2e/test_kuaima_pipeline.py tests/e2e/test_zhoupu_pipeline.py -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ec101/converters/zhoupu.py src/ec101/converters/cli.py tests/converters/test_zhoupu.py tests/e2e/test_zhoupu_pipeline.py tests/fixtures/zhoupu
git commit -m "feat: add Zhoupu standard pipeline"
```

### Task 8: Local API and Read Models

**Files:**
- Create: `src/ec101/api/__init__.py`
- Create: `src/ec101/api/queries.py`
- Create: `src/ec101/api/server.py`
- Create: `tests/api/test_import_api.py`
- Create: `tests/api/test_business_api.py`
- Create: `tests/api/test_fee_api.py`
- Create: `tests/api/test_coupon_api.py`

**Interfaces:**
- Consumes: workbook reader, import service, calculation engine, standard DB.
- Produces: `list_imports(db: sqlite3.Connection) -> list[dict[str, Any]]`; `get_import(db, import_batch_id: int) -> dict[str, Any]`; `list_release_candidates(db, import_batch_id: int, candidate: Optional[bool], query: str, limit: int, offset: int) -> dict[str, Any]`; `list_business_rows(db, resource: str, dealer: Optional[str], platform: Optional[str], query: str, limit: int, offset: int) -> dict[str, Any]`; `get_fee_overview(db, calculation_run_id: Optional[int]) -> dict[str, Any]`; `list_activity_summaries(db, calculation_run_id: Optional[int], limit: int, offset: int) -> dict[str, Any]`; `list_coupon_summaries(db, calculation_run_id: Optional[int], limit: int, offset: int) -> dict[str, Any]`; `list_unlinked_coupons(db, calculation_run_id: Optional[int], limit: int, offset: int) -> dict[str, Any]`; `create_handler(db_path: Path, archive_dir: Path) -> type[BaseHTTPRequestHandler]`; `serve(host: str, port: int, db_path: Path, archive_dir: Path) -> None`.

- [ ] **Step 1: Write failing query tests**

Cover current mode (latest run for every current import batch), fixed historical `calculation_run_id`, pagination limits, business search/filter, release candidate filtering, activity summaries, coupon summary metrics, and unlinked coupon rows including coupon number/customer/amount/status. API `linkedCount` is derived as `used_count - unlinked_count`; no extra database column is added.

- [ ] **Step 2: Write failing HTTP contract tests**

Cover `/health`, multipart `POST /api/imports`, import list/detail/issues/release, business objects, fee overview/activities/issues/settlements, `GET /api/fee-tpm/coupons`, and `GET /api/fee-tpm/coupons/unlinked`. Assert nonexistent historical runs return 404 and never fall back.

- [ ] **Step 3: Run API tests and verify failure**

Run: `python -m pytest tests/api -v`  
Expected: FAIL because API modules do not exist.

- [ ] **Step 4: Implement read models and local HTTP server**

Keep routing, multipart parsing, serialization and SQL queries in focused functions. `POST /api/imports` must archive metadata, call `import_snapshot`, then call `calculate_batch` once. API query code reads RESULT; it must not reproduce calculation formulas.

- [ ] **Step 5: Run API and end-to-end tests**

Run: `python -m pytest tests/api tests/e2e -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ec101/api tests/api
git commit -m "feat: expose EC101 local API"
```

### Task 9: ROI and Verification Reporting

**Files:**
- Create: `src/ec101/reporting/__init__.py`
- Create: `src/ec101/reporting/roi.py`
- Create: `src/ec101/reporting/verification.py`
- Modify: `src/ec101/api/queries.py`
- Modify: `src/ec101/api/server.py`
- Create: `tests/reporting/test_roi.py`
- Create: `tests/reporting/test_verification.py`
- Create: `tests/api/test_reporting_api.py`

**Interfaces:**
- Consumes: current CORE/RESULT and API routing.
- Produces: `box_factor(box_conversion: object = None, base_qty_per_box: object = None) -> Optional[float]`; `base_qty(quantity: object, unit: object, box_conversion: object = None, base_qty_per_box: object = None) -> Optional[float]`; `activity_roi(db: sqlite3.Connection, activity_id: int) -> dict[str, Any]`; `coupon_roi(db: sqlite3.Connection, coupon_config_id: int) -> dict[str, Any]`; `query_roi(db: sqlite3.Connection, calculation_run_id: Optional[int] = None) -> list[dict[str, Any]]`; `build_verification_workbook(db: sqlite3.Connection, calculation_run_id: int, output_path: Path) -> Path`.

- [ ] **Step 1: Write failing ROI tests**

Cover bottle/can units, box conversion, missing conversion factor, missing activity/coupon period, completed participating orders only, Coca-Cola brand only, monetary activity/coupon ratios, and gift activities returning amount without ROI.

- [ ] **Step 2: Write failing report tests**

Assert the workbook includes run metadata, activity summaries, coupon summaries, release candidates and a dedicated unlinked-coupon sheet with count/amount reconciling to `coupon_fee_summary`.

- [ ] **Step 3: Run reporting tests and verify failure**

Run: `python -m pytest tests/reporting tests/api/test_reporting_api.py -v`  
Expected: FAIL because reporting modules do not exist.

- [ ] **Step 4: Implement reporting and API routes**

Port confirmed ROI rules only. Add JSON ROI and Excel verification endpoints without calculating fees in the API layer.

- [ ] **Step 5: Run reporting, API and calculation tests**

Run: `python -m pytest tests/reporting tests/api tests/calculation -v`  
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/ec101/reporting src/ec101/api tests/reporting tests/api/test_reporting_api.py
git commit -m "feat: add ROI and verification reporting"
```

### Task 10: Fee Operations Web App

**Files:**
- Create: `web/package.json`
- Create: `web/vite.config.ts`
- Create: `web/tsconfig.json`
- Create: `web/src/main.tsx`
- Create: `web/src/App.tsx`
- Create: `web/src/styles.css`
- Create: `web/src/api/client.ts`
- Create: `web/src/api/types.ts`
- Create: `web/src/views/ImportView.tsx`
- Create: `web/src/views/BusinessDataView.tsx`
- Create: `web/src/views/OverviewView.tsx`
- Create: `web/src/views/ActivityFeesView.tsx`
- Create: `web/src/views/CouponFeesView.tsx`
- Create: `web/src/views/IssuesView.tsx`
- Create: `web/src/views/ReleaseView.tsx`
- Create: `web/src/views/RoiView.tsx`
- Create: `web/src/**/*.test.tsx`

**Interfaces:**
- Consumes: Task 8-9 JSON contracts.
- Produces: local React SPA with typed `fetch` client; `CouponSummary { calculationRunId, couponConfigId, usedCount, usedAmount, linkedCount, linkedAmount, releasableCount, releasableAmount, unlinkedCount, unlinkedAmount }`; `UnlinkedCoupon { couponRedemptionId, couponNo, customerNo, customerName, status, discountAmount }`; no business calculation exports.

- [ ] **Step 1: Write failing API client tests**

Assert base URL handling, upload form fields, 404/error messages, pagination parameters, coupon summary parsing and unlinked-coupon detail parsing.

- [ ] **Step 2: Write failing page tests**

Cover loading/error/empty states, import success, business filters, overview values, activity rows, release reasons, ROI missing-period display, and removal of all theoretical/equality copy and fields.

- [ ] **Step 3: Write the failing unlinked-coupon UI test**

Render one coupon summary with nonzero unlinked values; assert visible total/linked/releasable/unlinked metrics, an “未关联订单，不可释放” label, and detail rows with coupon number and amount.

- [ ] **Step 4: Run web tests and verify failure**

Run: `cd web && npm test -- --run`  
Expected: FAIL because the web app does not exist.

- [ ] **Step 5: Implement the smallest responsive operations UI**

Use plain React/Vite and focused view components; do not copy the old monolithic `app/page.tsx` or unused component library. Every displayed metric comes from API responses.

- [ ] **Step 6: Run web checks**

Run: `cd web && npm test -- --run && npm run build`  
Expected: tests PASS and production build succeeds.

- [ ] **Step 7: Commit**

```bash
git add web
git commit -m "feat: add fee operations web app"
```

### Task 11: Desktop Entry, Full Acceptance, CI, and Documentation

**Files:**
- Create: `desktop/__init__.py`
- Create: `desktop/app.py`
- Create: `desktop/build_windows.ps1`
- Create: `desktop/requirements-build.txt`
- Create: `tests/desktop/test_app.py`
- Create: `tests/e2e/test_full_pipeline.py`
- Create: `tests/e2e/test_external_golden.py`
- Create: `.github/workflows/ci.yml`
- Create: `README.md`
- Create: `docs/标准数据契约.md`
- Create: `docs/实际费用核算口径.md`
- Create: `docs/数据库字典.md`
- Modify: `PROJECT.md`

**Interfaces:**
- Consumes: converters, API launch commands, all accepted contracts.
- Produces: `build_request(form_values: Mapping[str, object]) -> ConversionRequest`; `run_conversion(request: ConversionRequest) -> ConversionResult`; optional external acceptance via `EC101_GOLDEN_DATA_DIR`.

- [ ] **Step 1: Write failing desktop tests**

Test platform selection, role-to-path mapping, missing required files, output messages and delegation to `convert_kuaima`/`convert_zhoupu`; do not test Tk rendering details.

- [ ] **Step 2: Write failing full-pipeline tests**

For both synthetic platform fixtures: convert → read workbook → import → calculate → query API read models. Assert current-batch coexistence, activity output, coupon summary, unlinked visibility and absence of theoretical output.

- [ ] **Step 3: Write the optional external golden test**

Skip unless `EC101_GOLDEN_DATA_DIR` is set. When present, assert the confirmed Kuaima numbers `136 / 2040 / 133 / 1995 / 3 / 45 / 98 / 200` and the configured Zhoupu acceptance snapshot without copying source files into the repository.

- [ ] **Step 4: Run desktop and full-pipeline tests and verify failure**

Run: `python -m pytest tests/desktop tests/e2e/test_full_pipeline.py tests/e2e/test_external_golden.py -v`  
Expected: desktop/full-pipeline tests FAIL; external golden test SKIPS without the environment variable.

- [ ] **Step 5: Implement desktop shell and Windows packaging script**

Keep Tkinter as a thin input/result layer. Package the same converter modules used by CLI; do not fork conversion behavior.

- [ ] **Step 6: Add CI and operator documentation**

CI runs the complete Python suite, web tests and web build without external golden data. README documents install, converter CLI/desktop, API, web, runtime archive path and backup. Data docs mark `entitlement_check`/theoretical fields as compatibility-only and document coupon summary/null bucket semantics.

- [ ] **Step 7: Run full verification**

Run: `python -m pytest -q`  
Expected: all repository Python tests PASS; external golden test SKIPS unless configured.

Run: `cd web && npm test -- --run && npm run build`  
Expected: all web tests PASS and build succeeds.

Run: `git diff --check`  
Expected: no whitespace errors.

- [ ] **Step 8: Commit**

```bash
git add desktop tests/desktop tests/e2e .github README.md docs PROJECT.md
git commit -m "feat: complete EC101 clean-room rebuild"
```

## Final Verification

- [ ] Run `python -m pytest -q` and record the passed/skipped counts.
- [ ] Run `cd web && npm test -- --run && npm run build` and record both results.
- [ ] Run the external golden suite when `EC101_GOLDEN_DATA_DIR` is available; otherwise report that full real-data validation remains pending.
- [ ] Search the repository for `promotion_calculator|standard_promotion|TemplateResult|recacl_|theoretical_|consistent_orders|consistency_of` and confirm no runtime dependency exists outside compatibility documentation/DDL.
- [ ] Search for committed `.db`, raw Excel, archives, backups, cache directories and generated output; confirm none are tracked.
- [ ] Update `PROJECT.md` with added capabilities, important files, current limits and the next useful step.
