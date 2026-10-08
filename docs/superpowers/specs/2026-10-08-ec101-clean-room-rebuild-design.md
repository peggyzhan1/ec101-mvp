# EC101 净室重建设计规格

日期：2026-10-08  
状态：待评审  
基准来源：`peggyzhan1/ec101-mvp-db_new` 的 `main` 分支与《EC101 项目现状梳理》  
目标仓库：当前空仓库 `ec101-mvp`

## 1. 目标

在不复制旧仓库历史和杂项资产的前提下，重建一个可运行、可测试、可追溯的 EC101 数据底座与费用运营台。

第一期必须打通以下纵向链路：

```text
快马 / 舟谱源文件
→ 平台转换器
→ standard.xlsx + sources.zip
→ 标准数据校验与批次入库
→ 唯一实际核算引擎
→ RESULT
→ API
→ 费用运营台只读展示
```

成功标准：业务人员能把两类平台文件转换并上传，系统能复现现行 `calculation_engine` 的逐单释放候选、活动费用汇总、核算提示及 ROI 查询；所有核心数字可由自动化测试复现。

## 2. 已确认的关键决策

1. 采用净室重建，不清理或继承旧仓库的完整工作树和 Git 历史。
2. 保留现行的导入、主数据、订单、活动、优惠券和 RESULT 分层。
3. `calculation` 只有一个费用核算引擎，不存在平台分支或第二套费用口径。
4. 费用 RESULT 的唯一权威实现是现行 `calculation_engine`；重建必须复现其实际核算行为，不另行概括、扩充或优化费用口径。
5. 可释放条件只有：订单状态为“已完成”，且下单时间严格早于核算日 T-2 的 `00:00:00`。
6. 不加入理论权益重算支线，不根据活动规则反推理论优惠或理论赠品。
7. 活动规则和活动权益仍作为业务配置事实保存、查询和追溯，但不参与费用 RESULT 计算。
8. 满赠不在无确认单价时折算费用，只保留实际核销事实及数量展示能力。
9. 第一期是本地单机业务工具；认证、权限和生产数据库迁移不在本期范围。

## 3. 范围

### 3.1 保留

- 快马和舟谱源文件转换。
- 固定标准工作簿契约与版本号。
- CLI 转换核心和 Windows Tkinter 薄客户端。
- `standard.xlsx` 校验、事务入库和 `sources.zip` 元数据归档。
- 导入批次历史和 `is_current` 切换。
- 客户、商品、订单、订单行、履约、活动、活动核销、优惠券配置和券核销事实。
- 唯一费用核算、逐单释放候选、活动费用汇总和现行核算质量提示。
- 业务数据查询、筛选、详情和 CSV 导出。
- 费用总览、活动、实际费用核算、异常、可释放清单、结算候选和 ROI。
- 快马与舟谱的脱敏黄金样本和端到端回归。

### 3.2 明确排除

- 理论优惠金额、理论应赠数量和实际/理论一致性判断。
- `promotion_calculator`、`standard_promotion`、`recacl_activity_execution`、`recacl_coupon_redemption`、`consistency_of`。
- 旧库 `ec101_mvp.db`、旧 DDL、数据库备份和旧四层直灌脚本。
- `raw_*`、`std_*`、`tpm_*` 旧表。
- 原始真实业务文件、历史试点目录、截图、PPT、临时输出、探查脚本、缓存和构建残留。
- 财经云接入、用户认证、RBAC、异常协同、支付、ERP 上账和生产多租户部署。
- 没有后端事实支撑的静态指标、假状态和假操作。

## 4. 架构

```text
src/ec101/contract      标准工作簿契约、类型和基础校验
src/ec101/converters    快马、舟谱平台适配
src/ec101/importing     批次、事务、事实入库、归档元数据
src/ec101/calculation   唯一实际费用核算引擎
src/ec101/reporting     ROI、核验报告和导出
src/ec101/api           HTTP 路由、请求校验和查询
db                      SQLite DDL 与迁移
desktop                 Windows 转换器薄客户端
web                     React 费用运营台
tests                   单元、集成、端到端和脱敏样本
docs                    数据契约、核算口径和运行说明
```

模块边界：

- 转换器只产生标准工作簿和归档，不连接数据库。
- 导入服务只校验和写入事实，不写 RESULT。
- 核算引擎只读取已入库事实，不读取 Excel、不识别平台。
- API 不重新计算费用，只调用核算服务或读取已保存 RESULT。
- 前端不计算 T-2、优惠金额或 ROI，只展示 API 结果。

## 5. 数据流

1. 平台转换器把快马或舟谱源文件转换为统一的 `standard.xlsx`，并生成 `sources.zip`。
2. 导入服务校验标准工作簿并写入导入批次和 CORE 业务事实；导入服务不得写 RESULT。
3. 导入成功后，API 调用 `calculation.calculate_batch(connection, import_batch_id, calc_date)`。
4. `calculate_batch` 只读取标准库事实，不读取 Excel，也不判断平台名称。
5. 引擎追加一条 `calculation_run`，再写逐单释放候选、活动费用汇总和核算质量提示。
6. 引擎完成后把 `calculation_run.status` 和 `import_batch.status` 更新为 `calculated`。
7. API 和前端只读取已保存的 RESULT，不重新计算费用和 T-2。

同一经销商、平台、覆盖区间再次导入时，仍沿用现行导入逻辑切换 `is_current`；该行为属于导入服务，不属于费用核算引擎。

## 6. 唯一费用核算引擎

本节按现行 `mvp/calculation_engine.py` 的实际执行顺序定义。除移除理论重算支线外，不改变现有核算口径。

### 6.1 入口

```text
calculate_batch(db: sqlite3.Connection, batch_id: int, calc_date: str | None = None) -> int
```

- `calc_date` 为空时使用运行当天。
- 非 `YYYY-MM-DD` 格式抛出错误。
- 返回新建的 `calculation_run_id`。
- `run_calculation` 只读取该导入批次最新一次核算结果，不执行核算。

### 6.2 T-2

```text
release_cutoff = 核算日 00:00:00 - 2 天
```

订单必须严格满足 `order_time < release_cutoff`。等于截止时间时仍为“未达 T-2”。

### 6.3 建立核算批次

引擎先按现行查询得到批次级金额：

```text
activity_benefit =
  SUM(activity_execution.discount_amount)
  WHERE activity 属于当前 import_batch

coupon_benefit =
  SUM(coupon_redemption.discount_amount)
  WHERE coupon_redemption.import_batch_id = 当前批次

total_benefit = activity_benefit + coupon_benefit
```

随后插入状态为 `calculating` 的 `calculation_run`。这些查询是现行引擎行为的组成部分，不在重建时替换为其他金额字段或新的业务推导。

### 6.4 参与订单查询

现行引擎从当前批次的 `order_header` 中选择满足以下任一条件的订单：

- 存在关联到该订单的 `activity_execution`；
- 存在关联到该订单的 `coupon_redemption`。

每个参与订单的活动金额为该订单全部 `activity_execution.discount_amount` 之和，券金额为该订单全部已关联 `coupon_redemption.discount_amount` 之和。

未关联到订单的券金额会进入批次级 `coupon_benefit`，但不会出现在参与订单、释放候选或 `released_coupon_benefit` 中。净室重建保持这一现行行为，不新增未关联券告警或新的汇总规则。

### 6.5 逐单释放判断

现行判断顺序：

1. `order_status` 不是“已完成”时，不可释放，原因记录订单状态。
2. `order_time` 缺失时，不可释放，原因记录“下单时间缺失”。
3. `order_time >= release_cutoff` 时，不可释放，原因记录“未达 T-2”。
4. 其他情况可释放，原因记录“已完成且达到 T-2”。

每个参与订单写一条 `release_candidate`，保存：

- `calculation_run_id`
- `order_id`
- `is_candidate`
- `reason`
- 该订单的活动核销金额
- 该订单的券核销金额

不可释放订单另外写入一条 `calculation_quality_issue`，类型为“未达释放节点”，级别为“提示”。

### 6.6 活动费用汇总

现行引擎逐个处理当前导入批次中的活动。只有存在 `activity_execution` 且能关联本次 `release_candidate` 的活动才写入 `activity_fee_summary`。

汇总字段保持现行行为：

- `actual_discount_total`
- `gift_cost_total = 0`
- `participating_orders`
- `released_orders`
- `released_amount`
- `pending_orders`
- `pending_amount`

现行 SQL 使用活动核销记录行数进行 `COUNT(*)`。净室重建先复现该行为，不擅自改成 `COUNT(DISTINCT order_id)`；是否改变统计口径必须作为独立需求确认。

### 6.7 完成核算

循环结束后，引擎更新：

```text
calculation_run.released_activity_benefit
calculation_run.released_coupon_benefit
calculation_run.participating_orders
calculation_run.released_orders
calculation_run.status = "calculated"
import_batch.status = "calculated"
```

`released_activity_benefit` 和 `released_coupon_benefit` 只累加满足逐单释放条件的参与订单金额。

### 6.8 移除的理论支线

净室版本不迁移现行文件中的以下支线：

- `TemplateResult`
- `recacl_activity_execution`
- `recacl_coupon_redemption`
- `consistency_of`
- 理论活动金额和理论券金额累计
- 理论应赠/实赠比较
- `entitlement_check` 写入
- “理论权益与实际执行不一致”质量问题
- `theoretical_*`、`consistent_orders` 和 `formula_ref` 返回值

移除这条支线不得改变 6.2 至 6.7 的实际核算结果。

### 6.9 禁止新增行为

重建时不得自行加入：

- 活动订单去重口径变更；
- `coupon_fee_summary` 写入逻辑；
- 未关联券的新告警或自动关联规则；
- 新的结算状态机；
- 活动规则反推费用；
- 平台专属核算分支；
- API 或前端二次核算。

这些能力如需增加，必须在净室重建完成后作为独立需求设计和验收。

## 7. 数据库

标准库仍沿用现行分层和表结构作为重建基线：

- 导入审计：`import_batch`、`import_file`、`import_validation_issue`
- 主数据：`dealer_platform`、`customer`、`product`
- 订单履约：`order_header`、`order_line`、`fulfillment`
- 活动：`activity`、`activity_rule`、`activity_benefit`、`activity_scope`、`activity_execution`
- 优惠券：`coupon_config`、`coupon_issue_rule`、`coupon_use_rule`、`coupon_scope`、`coupon_redemption`
- RESULT：`calculation_run`、`entitlement_check`、`release_candidate`、`activity_fee_summary`、`coupon_fee_summary`、`calculation_quality_issue`

为了不把结构调整混入净室重建，第一期保留现行 RESULT 表名和兼容字段；唯一核算引擎不写 `entitlement_check`，不写理论字段，也不承诺写 `coupon_fee_summary`。这些兼容对象不得被文档或页面描述为已实现能力。

数据库文件不提交到仓库。测试从 DDL 创建空库并开启外键约束；DDL 和运行时结构必须由结构测试保持一致。

## 8. API

API 以现有接口契约为基线，重点保留：

- `POST /api/imports`
- `GET /api/imports`
- `GET /api/imports/{id}`
- `GET /api/imports/{id}/issues`
- `GET /api/imports/{id}/release`
- 现有业务数据查询接口
- 现有费用 TPM 总览、活动、异常和结算候选接口
- 现有 ROI 查询和导出

API 调用唯一核算引擎，但不得复制引擎中的金额查询、参与订单查询或 T-2 判断。不存在的历史核算批次返回错误，不回退到最新结果。

## 9. 前端

费用运营台保留当前真实 API 已支撑的页面和导航。涉及“理论权益”“理论金额”或“一致/差异”的文案和字段全部移除；页面只展示现行实际核算引擎已经写出的 RESULT。

没有 API 支撑的静态批次数字、财经云状态、负责人、P0/P1、关闭状态和结算操作不进入净室版本。

## 10. 测试与验收

### 10.1 核算引擎回归

- 缺省核算日和非法日期格式。
- `release_cutoff` 为核算日减两天的零点。
- 非已完成、缺失时间、未达 T-2 和达到 T-2 的原因文本。
- 批次级活动、券和总金额与现行查询一致。
- 参与订单选择条件与现行引擎一致。
- 逐单活动金额和券金额与现行引擎一致。
- 现行活动汇总 `COUNT(*)` 行为保持不变。
- 未关联券计入批次券总额，但不进入参与订单和可释放券金额。
- 源码不依赖平台名称或理论重算模块。
- 移除理论支线前后，实际核算字段逐项一致。

### 10.2 模块边界

- 导入服务不写 RESULT。
- 核算引擎不读取 Excel。
- API 和前端不实现第二份核算逻辑。
- 多次核算保留历史，结果读取遵循现有最新运行规则。

### 10.3 试点回归

快马兴路强核算日 `2026-09-22` 的已确认数字继续作为回归目标：满减活动订单 136、实际优惠 2040、可释放订单 133、可释放金额 1995、不可释放 3 单/45 元、满赠 98、测试券 200。

舟谱羿柏使用现有标准库投影和已确认结果回归，保留其返券语义，不把文件夹名称“满减”解释成快马式金额满减。

测试样本必须脱敏；真实试点文件不提交到新仓库。

## 11. 净室迁移规则

允许迁移的是现有行为和契约，不是旧仓库目录：标准工作簿字段、导入规则、`calculation_engine` 的实际核算查询和判断、API 响应语义、已确认测试数字及必要 UI 信息架构。

不得迁移旧数据库、真实业务文件、输出物、备份、探查脚本、早期直灌脚本、并行核算器和理论重算模块。

对于现有代码中未实现或未写入的能力，净室项目不得因为 DDL 有对应表或前端有对应区域就自动补齐。

## 12. 实施顺序

1. 建立最小仓库骨架、测试入口和忽略规则。
2. 迁移标准工作簿契约和现行标准库 DDL，建立结构测试。
3. 迁移导入服务并验证导入与 RESULT 的边界。
4. 用回归测试刻画现行 `calculation_engine` 的实际路径。
5. 实现唯一核算引擎，只移除理论重算支线。
6. 迁移快马转换器并完成首个端到端切片。
7. 迁移舟谱转换器并完成第二平台回归。
8. 按现有契约重建 API 和精简前端。
9. 迁移 Windows 转换壳并完成试点验收。

每一阶段先证明与现行行为一致，再进入下一阶段；不在重建中顺手修正统计口径或补做旧代码未实现的 RESULT。

## 13. 完成定义

- 新克隆仓库能够从空库运行。
- 快马和舟谱主链路可运行。
- 只有一个 `calculation` 核算入口。
- 实际核算字段与现行 `calculation_engine` 回归结果一致。
- 理论重算导入、调用、写入、问题和响应字段均不存在于运行路径。
- 导入、核算、API 和前端边界清晰。
- 仓库不含真实业务数据、数据库文件、备份、缓存和历史输出。
- 文档不宣称 `coupon_fee_summary` 等现行引擎未写入的能力已实现。

## 14. 已知风险

- 旧代码的活动汇总使用核销行数而不是去重订单数；本次只复现，不修改。
- 未关联券只进入批次券总额，现行引擎不生成专门告警或券汇总；本次不扩展。
- 保留兼容 RESULT 表而不使用其中理论字段，可能产生理解成本，必须在数据字典中标明“兼容保留、运行时不写”。
- 完整黄金回归依赖外部真实样本；仓库只能保存脱敏样本和期望值。
- SQLite 和本地 HTTP 服务不代表满足多人生产部署要求。
