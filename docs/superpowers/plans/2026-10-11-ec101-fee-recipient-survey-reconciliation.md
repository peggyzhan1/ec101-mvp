# EC101 应发客户与问卷确认实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改动现有费用核算引擎和 RESULT 结果层的前提下，建立“应发客户 → 第三方客户映射 → 客户周期应发额 → 问卷确认 → 对账”的可追溯 MVP 链路。

**Architecture:** 新增独立的 `ec101.confirmation` 领域模块，负责主数据快照、应发名单、问卷答卷和客户周期对账；现有第三方标准工作簿导入仅补写稳定客户身份。业务关联键固定为 `fee_cycle_id + sap_customer_code`，问卷不持有订单、销售凭证、活动或优惠券外键。本计划在现有 SQLite 基线上交付数据库、文件导入、查询 API 和最小运营页面；云数据库迁移和数采通直连另立项。

**Tech Stack:** Python 3.9+、SQLite 3（窗口函数）、`sqlite3`、`openpyxl 3.1`、pytest 8、TypeScript、React、Vite、Vitest、Testing Library

**Spec:** `docs/superpowers/specs/2026-10-11-ec101-fee-recipient-survey-reconciliation-design.md`

## Global Constraints

- 问卷与应发表只按“费用周期 + 太古客户编号”对账。
- 同一周期、同一太古客户在 `fee_recipient` 中只能有一条汇总记录，且 `expected_amount > 0`。
- 客户确认的是“本费用周期全部协议费用是否收到”，不逐项确认。
- `survey_response` 不得包含 `fee_recipient_id`、问卷令牌、应发金额快照、第三方订单号、销售凭证号、订单金额、订单箱数、主券号、副券号或优惠券核销标识。
- 重复答卷全部保留；当前结果取最新有效答卷，排序为 `submitted_at DESC, survey_response_id DESC`。
- 问卷对账以 `fee_recipient` 为主表使用 `LEFT JOIN`，不得遗漏未提交问卷的应发客户。
- 只有 `match_status IN ('匹配成功', '已确认')` 且两端客户编号均非空的客资映射可用于自动转换；不用名称、电话或地址兜底。
- 太古客户编号、第三方客户编号、线路号、办事处代码和合作伙伴编号全部按字符串保存，保留前导零。
- 现有 `ec101.calculation.engine`、RESULT 结果表及其核算口径不变。
- 本期不实现预设线路表、未收到自动转下期、云数据库迁移、认证权限或数采通网络直连。
- 手机号在 API 和页面默认不返回；源文件不提交代码仓库，仅保存文件名和 SHA-256。

## Review Focus

- 编号被 Excel 读成数字、科学计数法或含前后空格时：输入应被明确规范化或拒绝，不得生成不可逆的错误客户编号（Task 3、Task 5）。
- 金额为空、零、负数、非数字或超过两位小数时：整批应在写库前失败，不允许部分导入（Task 3）。
- 同一答卷文件重复上传，或不同文件包含同一原始答卷时：应拒绝重复批次或指纹，不得复制历史（Task 5）。
- 两份答卷的提交时间相同且答案相反时：使用更大的 `survey_response_id` 作为当前答案，同时标记冲突（Task 6）。
- 可用客资映射指向多个第三方客户或平台时：应标记 `ambiguous`，不得任选一条（Task 3）。

---

### Task 1: 建立客户周期确认数据库基线

**Files:**
- Modify: `db/ec101_standard_sqlite.sql`
- Create: `db/migrations/001_fee_confirmation.sql`
- Modify: `src/ec101/db.py`
- Modify: `tests/test_schema.py`

**Interfaces:**
- Consumes: 现有 `dealer_platform(dealer_platform_id)` 和 `activity(activity_id)`。
- Produces: 规格中的 9 张新表 `master_sync_batch`、`taikoo_customer_snapshot`、`customer_mapping_snapshot`、`platform_customer_identity`、`fee_cycle`、`fee_recipient`、`fee_cycle_activity`、`survey_import_batch`、`survey_response`，以及 `v_effective_survey_response`、`v_fee_confirmation_reconciliation` 两个视图；`upgrade_database(path: Path) -> None` 为旧库幂等应用未执行迁移。

- [ ] **Step 1: 为新表、键和禁止字段写失败测试**

  在 `tests/test_schema.py` 新增 `EXPECTED_CONFIRMATION_TABLES` 和三个测试：
  - `test_create_database_builds_confirmation_schema_and_views`：断言 9 张表和 2 个视图存在。
  - `test_fee_recipient_enforces_one_customer_per_cycle_and_positive_amount`：重复 `(fee_cycle_id, '0570502563')` 和 `expected_amount <= 0` 均失败。
  - `test_survey_response_has_no_order_coupon_or_recipient_foreign_keys`：断言列集中不存在规格禁止字段，外键仅指向 `survey_import_batch` 和 `fee_cycle`。
  - `test_upgrade_database_adds_confirmation_schema_to_existing_database_once`：从只含现有核心表的旧库开始，连续执行两次 `upgrade_database` 均成功，原数据不变，迁移版本 `001_fee_confirmation` 只记录一次。

- [ ] **Step 2: 运行定向测试并确认因缺表失败**

  Run: `pytest tests/test_schema.py -v`

  Expected: FAIL，原因是新表或视图不存在。

- [ ] **Step 3: 按规格实现 DDL**

  使用 SQLite 类型映射：`BIGINT` 主键用 `INTEGER PRIMARY KEY`，`DECIMAL(18,2)` 用 `NUMERIC NOT NULL`，布尔快照用 `INTEGER NOT NULL DEFAULT 0 CHECK (... IN (0,1))`。状态字段使用规格中的 `CHECK` 枚举；建立所有唯一约束、外键和查询索引。视图的选取顺序与状态文案必须与规格第 10、11 节一致。同一套对象同时写入全量 DDL 和 `001_fee_confirmation.sql`；`schema_migration(version, applied_at)` 记录迁移，`upgrade_database` 在单个事务中应用尚未记录的脚本。

- [ ] **Step 4: 运行 schema 测试**

  Run: `pytest tests/test_schema.py -v`

  Expected: PASS。

- [ ] **Step 5: 提交数据库基线**

  ```bash
  git add db/ec101_standard_sqlite.sql db/migrations/001_fee_confirmation.sql src/ec101/db.py tests/test_schema.py
  git commit -m "feat: add fee confirmation schema"
  ```

### Task 2: 稳定第三方客户身份与主数据快照

**Files:**
- Create: `src/ec101/confirmation/__init__.py`
- Create: `src/ec101/confirmation/master_data.py`
- Create: `tests/confirmation/__init__.py`
- Create: `tests/confirmation/test_master_data.py`
- Modify: `src/ec101/importing/service.py`
- Modify: `tests/importing/test_import_service.py`

**Interfaces:**
- Consumes: Task 1 的 `master_sync_batch`、`taikoo_customer_snapshot`、`customer_mapping_snapshot`、`platform_customer_identity`。
- Produces: `MasterSyncResult(master_sync_batch_id: int, customer_count: int, mapping_count: int)`；`sync_master_data(db: sqlite3.Connection, source_database: str, customers: Sequence[Mapping[str, Any]], mappings: Sequence[Mapping[str, Any]], synced_at: str | None = None) -> MasterSyncResult`；`upsert_platform_customer_identity(db, dealer_platform_id: int, platform_customer_no: str, customer_name: str | None, seen_at: str) -> int`。

- [ ] **Step 1: 写主数据快照与稳定身份失败测试**

  测试以太古编号 `0570502563` 和第三方编号 `00081` 证明：
  - `sync_master_data` 原子写入一个成功批次、客户快照和映射快照，前导零保留。
  - 缺少主键或客户编号时整批回滚，批次状态记为 `failed`。
  - 同平台再次导入 `00081` 只更新 `latest_customer_name` 和 `last_seen_at`，不新建身份。

- [ ] **Step 2: 运行定向测试并确认接口尚不存在**

  Run: `pytest tests/confirmation/test_master_data.py tests/importing/test_import_service.py -v`

  Expected: FAIL，原因是 `ec101.confirmation.master_data` 或稳定身份数据尚不存在。

- [ ] **Step 3: 实现主数据快照服务**

  输入字段名与规格 6.2、6.3 一致。先完整校验，再在一个事务中写入；不得在此模块建立数采通网络连接或保存凭据。

- [ ] **Step 4: 把稳定客户身份补写到现有导入流程**

  修改 `_insert_customers(...)`，每次写入现有 `customer` 快照后调用 `upsert_platform_customer_identity(...)`。`seen_at` 使用导入批次的 `imported_at`；不改变 `customer` 表和原导入返回值。

- [ ] **Step 5: 运行主数据和现有导入回归**

  Run: `pytest tests/confirmation/test_master_data.py tests/importing -v`

  Expected: PASS。

- [ ] **Step 6: 提交快照和稳定身份**

  ```bash
  git add src/ec101/confirmation tests/confirmation src/ec101/importing/service.py tests/importing/test_import_service.py
  git commit -m "feat: add customer master snapshots"
  ```

### Task 3: 导入客户周期应发名单并解析客资映射

**Files:**
- Create: `src/ec101/confirmation/workbook.py`
- Create: `src/ec101/confirmation/recipients.py`
- Create: `tests/confirmation/test_recipient_workbook.py`
- Create: `tests/confirmation/test_recipients.py`

**Interfaces:**
- Consumes: Task 1 的 `fee_cycle`、`fee_recipient` 和 Task 2 的快照/稳定身份。
- Produces: `FeeCycleInput(fee_cycle_code: str, cycle_name: str, period_start: str, period_end: str)`；`FeeRecipientImportResult(fee_cycle_id: int, input_row_count: int, recipient_count: int, matched_count: int, unmatched_count: int, ambiguous_count: int)`；`read_fee_recipient_workbook(path: str | Path) -> list[dict[str, str]]`；`import_fee_recipients(db: sqlite3.Connection, cycle: FeeCycleInput, rows: Sequence[Mapping[str, Any]], master_sync_batch_id: int, imported_at: str | None = None) -> FeeRecipientImportResult`；`replace_fee_cycle_activities(db: sqlite3.Connection, fee_cycle_id: int, activity_ids: Sequence[int], created_at: str | None = None) -> None`。

- [ ] **Step 1: 写工作簿合同和金额校验失败测试**

  `read_fee_recipient_workbook` 仅接受单工作表表头 `费用周期、太古客户编号、太古客户名称、应发金额、备注`，其中备注可空。测试覆盖：
  - 文本编号 `0570502563` 原样保留。
  - Excel 数字编号仅在能无损转为整数字符串时接受；科学计数法文本拒绝并提示改为文本。
  - 空、零、负数、非数字、三位小数金额均抛出 `FeeRecipientValidationError`。

- [ ] **Step 2: 写应发汇总和映射决策失败测试**

  以两行 `200.00 + 300.00` 断言最终仅有一条 `expected_amount = 500.00` 的 `fee_recipient`。分别断言：唯一有效映射为 `matched`；没有为 `unmatched`；两个不同目标为 `ambiguous` 且所有平台字段为 `NULL`；名称相同不得兜底。再断言重复导入同一周期整批失败且不覆盖原数据。`replace_fee_cycle_activities` 只接受已存在的活动，重复活动去重，且不建立问卷到活动的关联。

- [ ] **Step 3: 运行定向测试并确认接口尚不存在**

  Run: `pytest tests/confirmation/test_recipient_workbook.py tests/confirmation/test_recipients.py -v`

  Expected: FAIL，原因是工作簿解析器和导入服务尚不存在。

- [ ] **Step 4: 实现应发工作簿解析和导入服务**

  用 `Decimal` 解析金额，只接受正数且最多两位小数；按 `(fee_cycle_code, sap_customer_code)` 显式分组求和。先校验整份文件的周期都等于 `cycle.fee_cycle_code`，再开启写库事务。映射只查指定 `master_sync_batch_id` 内的可用记录，并要求稳定平台客户身份已存在。周期活动替换函数只写 `fee_cycle_activity`，不反向改动活动或订单数据。

- [ ] **Step 5: 运行应发导入测试**

  Run: `pytest tests/confirmation/test_recipient_workbook.py tests/confirmation/test_recipients.py -v`

  Expected: PASS。

- [ ] **Step 6: 提交应发名单导入**

  ```bash
  git add src/ec101/confirmation/workbook.py src/ec101/confirmation/recipients.py tests/confirmation
  git commit -m "feat: import cycle fee recipients"
  ```

### Task 4: 转换历史乐客通发券明细

**Files:**
- Create: `src/ec101/confirmation/legacy_coupon.py`
- Create: `tests/confirmation/test_legacy_coupon.py`

**Interfaces:**
- Consumes: 历史行的 `客户编号`、`客户名称`、`主券号`、`费用发放月`、`金额`。
- Produces: `aggregate_legacy_coupon_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]`，返回 Task 3 工作簿对应的标准行。

- [ ] **Step 1: 写主券去重和客户周期汇总失败测试**

  构造同一主券 `M-001` 因两张副券重复两行、金额均为 `200.00`，再加一张主券 `M-002 = 300.00`。断言按 `客户编号 + 费用发放月 + 主券号` 去重后，客户周期总额为 `500.00` 而非 `700.00`。同一主券出现不同金额时必须失败。

- [ ] **Step 2: 运行测试并确认转换器尚不存在**

  Run: `pytest tests/confirmation/test_legacy_coupon.py -v`

  Expected: FAIL with `ModuleNotFoundError` or missing function。

- [ ] **Step 3: 实现最小历史转换器**

  先以主券键去重并校验金额一致，再按 `费用发放月 + 客户编号` 汇总。输出只包含 `费用周期、太古客户编号、太古客户名称、应发金额、备注`，不携带券号进入最终应发表。

- [ ] **Step 4: 运行历史转换测试**

  Run: `pytest tests/confirmation/test_legacy_coupon.py -v`

  Expected: PASS。

- [ ] **Step 5: 提交历史转换器**

  ```bash
  git add src/ec101/confirmation/legacy_coupon.py tests/confirmation/test_legacy_coupon.py
  git commit -m "feat: aggregate legacy coupon recipients"
  ```

### Task 5: 导入问卷星原始答卷历史

**Files:**
- Create: `src/ec101/confirmation/surveys.py`
- Create: `tests/confirmation/test_survey_workbook.py`
- Create: `tests/confirmation/test_surveys.py`
- Modify: `src/ec101/confirmation/workbook.py`

**Interfaces:**
- Consumes: Task 1 的 `fee_cycle`、`fee_recipient`、`survey_import_batch`、`survey_response`。
- Produces: `SurveyImportResult(survey_import_batch_id: int, row_count: int, matched_count: int, unmatched_count: int, invalid_count: int)`；`read_survey_workbook(path: str | Path) -> list[dict[str, str]]`；`import_survey_responses(db: sqlite3.Connection, fee_cycle_code: str, source_file_name: str, source_file_sha256: str, rows: Sequence[Mapping[str, Any]], imported_at: str | None = None) -> SurveyImportResult`。

- [ ] **Step 1: 写问卷工作簿和敏感字段失败测试**

  固定表头为 `费用周期、太古客户编号、太古客户名称、是否收到本期全部协议费用、未收到原因、补充说明、答卷手机号、提交时间、问卷星原始序号`。断言不允许多出第三方订单号、销售凭证号、主券号或应发金额列；客户编号的规范化规则与 Task 3 一致。

- [ ] **Step 2: 写答卷匹配、保留和去重失败测试**

  断言：
  - `已收到` / `尚未收到` 分别存为 `received` / `not_received`；选“尚未收到”但原因为空时存为 `invalid`。
  - 同周期和客户找到应发记录为 `matched`，找不到为 `not_in_recipient_list` 且原行仍保留。
  - 文件周期与指定周期不符的行保留为 `invalid`，不跨周期匹配。
  - 同一周期内重复文件 SHA-256 整批拒绝；不同文件中的同一指纹拒绝新批次并不留部分数据。

- [ ] **Step 3: 运行定向测试并确认接口尚不存在**

  Run: `pytest tests/confirmation/test_survey_workbook.py tests/confirmation/test_surveys.py -v`

  Expected: FAIL，原因是答卷解析和导入服务尚不存在。

- [ ] **Step 4: 实现答卷导入和稳定指纹**

  `response_fingerprint` 使用 `SHA-256(fee_cycle_code + "|" + raw_sequence_no + "|" + sap_customer_code + "|" + submitted_at + "|" + received_answer)`。所有原行在一个事务中写入，同时回写批次计数；数据库连接和异常日志不输出手机号。

- [ ] **Step 5: 运行问卷导入测试**

  Run: `pytest tests/confirmation/test_survey_workbook.py tests/confirmation/test_surveys.py -v`

  Expected: PASS。

- [ ] **Step 6: 提交答卷历史导入**

  ```bash
  git add src/ec101/confirmation/workbook.py src/ec101/confirmation/surveys.py tests/confirmation
  git commit -m "feat: import survey response history"
  ```

### Task 6: 查询客户周期对账和异常

**Files:**
- Create: `src/ec101/confirmation/queries.py`
- Create: `tests/confirmation/test_queries.py`

**Interfaces:**
- Consumes: Task 1 的两个视图，Task 3 的映射状态，Task 5 的答卷历史。
- Produces: `get_confirmation_overview(db: sqlite3.Connection, fee_cycle_code: str) -> dict[str, Any]`；`list_confirmation_reconciliation(db: sqlite3.Connection, fee_cycle_code: str, status: str | None, query: str, limit: int, offset: int) -> dict[str, Any]`；`list_confirmation_exceptions(db: sqlite3.Connection, fee_cycle_code: str, kind: str | None, limit: int, offset: int) -> dict[str, Any]`。

- [ ] **Step 1: 写最新答卷、冲突和未提交失败测试**

  构造三个应发客户：A 从“未收到”更新为“已收到”，B 未提交，C 两份相反答卷拥有相同 `submitted_at`。断言 A 取最新答卷且 `has_conflict = 1`，B 状态为 `未提交`，C 取更大 `survey_response_id` 且为 `答卷冲突`。

- [ ] **Step 2: 写指标和异常分类失败测试**

  断言 overview 同时返回客户数和 `expected_amount` 合计：`recipient`、`submitted`、`notSubmitted`、`received`、`notReceived`、`conflict`；另返回 `outsideListResponseCount`、`unmatchedMapping`、`ambiguousMapping`。异常列表能单独筛选 `outside_list`、`conflict`、`unmatched_mapping`、`ambiguous_mapping`、`invalid_response`。

- [ ] **Step 3: 运行定向测试并确认查询尚不存在**

  Run: `pytest tests/confirmation/test_queries.py -v`

  Expected: FAIL with missing query functions。

- [ ] **Step 4: 实现三个只读查询**

  复用现有 API 的分页边界：`limit` 限制为 1–500，`offset >= 0`。名称和编号用参数化 `LIKE` 查询；手机号不进入返回字段。未知周期抛 `LookupError`，未知状态或异常类型抛 `ValueError`。

- [ ] **Step 5: 运行对账查询测试**

  Run: `pytest tests/confirmation/test_queries.py -v`

  Expected: PASS。

- [ ] **Step 6: 提交对账查询**

  ```bash
  git add src/ec101/confirmation/queries.py tests/confirmation/test_queries.py
  git commit -m "feat: query fee confirmation reconciliation"
  ```

### Task 7: 暴露应发、问卷和对账 API

**Files:**
- Modify: `src/ec101/api/server.py`
- Create: `tests/api/test_confirmation_api.py`
- Modify: `tests/api/conftest.py`

**Interfaces:**
- Consumes: Task 3 的应发工作簿导入、Task 5 的问卷工作簿导入、Task 6 的三个查询。
- Produces: `POST /api/fee-confirmation/recipients`、`POST /api/fee-confirmation/surveys`、`GET /api/fee-confirmation/overview`、`GET /api/fee-confirmation/recipients`、`GET /api/fee-confirmation/exceptions`。

- [ ] **Step 1: 写 HTTP 合同失败测试**

  固定请求合同：
  - 应发 POST 为 multipart，文件字段 `recipients`，文本字段 `feeCycle`、`cycleName`、`periodStart`、`periodEnd`、`masterSyncBatchId`。
  - 问卷 POST 为 multipart，文件字段 `survey`，文本字段 `feeCycle`。服务端从原始上传内容计算 SHA-256，只将临时文件用于解析。
  - 三个 GET 都必须提供 `feeCycle`；列表接受 `status`/`kind`、`query`、`limit`、`offset`。
  - 成功 POST 返回 201 和导入计数；格式/业务错误返回 400，未知周期返回 404，临时文件总是删除。

- [ ] **Step 2: 运行 API 测试并确认路由返回 404**

  Run: `pytest tests/api/test_confirmation_api.py -v`

  Expected: FAIL，新路由不存在。

- [ ] **Step 3: 扩展 GET 路由分发**

  从 `ec101.confirmation.queries` 导入三个查询，严格区分 `LookupError -> 404` 和 `ValueError -> 400`，不将手机号放入 JSON。

- [ ] **Step 4: 扩展 POST 路由分发**

  把现有单一 `/api/imports` 分支改为明确的路由分支，复用 `_multipart()` 和 `NamedTemporaryFile`。不改变原 `/api/imports` 的行为和返回结构。`serve(...)` 在库不存在时调用 `create_database`，已存在时调用 Task 1 的 `upgrade_database`。

- [ ] **Step 5: 运行 API 及原导入回归**

  Run: `pytest tests/api/test_confirmation_api.py tests/api/test_import_api.py tests/api/test_fee_api.py -v`

  Expected: PASS。

- [ ] **Step 6: 提交客户确认 API**

  ```bash
  git add src/ec101/api/server.py tests/api/conftest.py tests/api/test_confirmation_api.py
  git commit -m "feat: expose fee confirmation api"
  ```

### Task 8: 增加最小客户确认运营页

**Files:**
- Create: `web/src/views/FeeConfirmationView.tsx`
- Create: `web/src/views/FeeConfirmationView.test.tsx`
- Modify: `web/src/App.tsx`
- Modify: `web/src/api/types.ts`
- Modify: `web/src/api/client.ts`
- Modify: `web/src/api/client.test.ts`
- Modify: `web/src/styles.css`

**Interfaces:**
- Consumes: Task 7 的 5 个 HTTP 端点。
- Produces: `ConfirmationOverview`、`ConfirmationRecipient`、`ConfirmationException`；`ApiClient.uploadRecipients(...)`、`uploadSurveys(...)`、`confirmationOverview(...)`、`confirmationRecipients(...)`、`confirmationExceptions(...)`；导航项“客户确认”。

- [ ] **Step 1: 写 API 客户端路径和 multipart 合同失败测试**

  断言两个上传方法使用 Task 7 固定的字段名，三个查询方法始终传送 `feeCycle`，并正确编码状态、关键字和分页参数。

- [ ] **Step 2: 写页面业务语义失败测试**

  断言页面：
  - 显示“本月全部协议费用是否收到”，不出现“订单确认”或“逐项确认”。
  - 提供费用周期输入、应发名单上传、问卷上传、确认状态筛选。
  - 展示应发、已提交、未提交、已确认收到、确认未收到、答卷冲突的客户数与金额。
  - 对账表保留未提交客户，异常区显示名单外答卷、客资未匹配/多义和冲突答卷；页面不显示手机号。

- [ ] **Step 3: 运行 Web 定向测试并确认组件和方法尚不存在**

  Run: `cd web && npm test -- --run src/api/client.test.ts src/views/FeeConfirmationView.test.tsx`

  Expected: FAIL with missing client methods or component。

- [ ] **Step 4: 实现类型和 API 客户端**

  使用明确的 camelCase 返回类型，金额类型保持现有 `number` 惯例。上传成功后返回服务端导入计数，由视图重新拉取 overview 和列表。

- [ ] **Step 5: 实现页面和导航**

  用现有表单、卡片、表格样式完成单页；不引入新 UI 库或图表库。周期默认为当前月的 `YYYY-MM`，但只有用户点击查询或导入时才调用 API。

- [ ] **Step 6: 运行 Web 测试**

  Run: `cd web && npm test -- --run`

  Expected: PASS。

- [ ] **Step 7: 提交客户确认页**

  ```bash
  git add web/src
  git commit -m "feat: add fee confirmation workspace"
  ```

### Task 9: 更新数据字典并完成端到端验收

**Files:**
- Modify: `docs/数据库字典.md`
- Modify: `docs/标准数据契约.md`
- Modify: `README.md`
- Create: `tests/e2e/test_fee_confirmation_pipeline.py`

**Interfaces:**
- Consumes: Tasks 1–8 的完整链路。
- Produces: 从主数据快照、第三方客户身份、应发名单到问卷对账的自动化验收，以及运营人员可使用的字段文档。

- [ ] **Step 1: 写端到端失败测试**

  测试建立 `2026-09` 周期，覆盖五个客户：已确认收到、确认未收到、未提交、客资未匹配、客资多义；另导入一条名单外答卷和一组冲突答卷。断言对账总客户数始终等于 5，金额只来自 `fee_recipient.expected_amount`，且问卷表没有任何订单/券/销售凭证关联。

- [ ] **Step 2: 运行端到端测试并确认尚缺文档或链路组装**

  Run: `pytest tests/e2e/test_fee_confirmation_pipeline.py -v`

  Expected: FAIL 直至完整链路和断言都就绪。

- [ ] **Step 3: 补齐数据字典、文件合同和运行说明**

  `docs/数据库字典.md` 记录 9 张表、2 个视图、键和状态枚举；`docs/标准数据契约.md` 记录两种新工作簿的精确表头与编号/金额格式；`README.md` 记录操作顺序“客资快照→应发名单→问卷答卷→对账”和隐私注意事项。

- [ ] **Step 4: 完成端到端组装并运行全部 Python 测试**

  Run: `pytest -v`

  Expected: PASS，包含新的客户确认 E2E 和原有核算回归。

- [ ] **Step 5: 运行全部 Web 测试和生产构建**

  Run: `cd web && npm test -- --run && npm run build`

  Expected: 测试全部 PASS，Vite build 成功。

- [ ] **Step 6: 检查变更卫生和敏感文件**

  Run: `git diff --check && git status --short && git ls-files '*.xlsx' '*.xls' '*.db'`

  Expected: `git diff --check` 无输出；状态只包含 Task 9 当前尚未提交的文档和 E2E 测试；不存在新增的真实问卷、客资或数据库文件。

- [ ] **Step 7: 提交文档和端到端验收**

  ```bash
  git add README.md docs tests/e2e/test_fee_confirmation_pipeline.py
  git commit -m "docs: document fee confirmation workflow"
  ```

### Task 10: 最终回归与分支审查

**Files:**
- Review only: all files changed by Tasks 1–9

**Interfaces:**
- Consumes: Tasks 1–9 的所有交付。
- Produces: 可合并、无未解决高优问题的分支。

- [ ] **Step 1: 执行完整验证**

  Run: `pytest -v`

  Expected: PASS。

  Run: `cd web && npm test -- --run && npm run build`

  Expected: PASS and successful build。

  Run: `git diff --check origin/main...HEAD`

  Expected: no output。

- [ ] **Step 2: 对照规格做整体审查**

  逐项核对规格第 16 节的 13 条验收标准，特别检查问卷表无订单/券/销售凭证字段、未提交客户仍可见、冲突答卷保留，以及原有核算回归未改变。

- [ ] **Step 3: 修复审查发现的本范围问题并重跑完整验证**

  只修改可追溯到本规格的问题，不顺带重构现有费用核算、转换器或页面。

- [ ] **Step 4: 如审查产生修复，提交最终修复**

  ```bash
  git add <review-fix-files>
  git commit -m "fix: address fee confirmation review"
  ```
