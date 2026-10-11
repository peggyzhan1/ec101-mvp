# EC101 应发客户与问卷确认数据库设计规格

日期：2026-10-11

状态：待书面评审（设计方向已确认）

适用范围：EC101 MVP 的应发客户识别、第三方客户转换和客户确认数据链路

## 1. 目标

在现有第三方平台订单、活动、优惠券、履约和费用核算数据库基础上，补充两段数据链路：

1. 核算前：将太古应发客户名单转换为第三方平台客户名单。
2. 核算后：将问卷星答卷与本期应发客户名单进行客户周期级对账。

系统需要回答：

- 本费用周期有哪些客户应发费用；
- 每个客户本期合计应发多少钱；
- 每个太古客户对应哪个第三方平台客户；
- 客户是否确认收到本期全部协议费用；
- 哪些应发客户尚未提交问卷。

## 2. 已确认的关键决策

1. 问卷与应发表只按“费用周期 + 太古客户编号”对账。
2. 同一费用周期、同一太古客户在应发表中只能有一条汇总记录。
3. 同一客户一个周期内存在多个费用项目时，必须先汇总为客户周期应发总额，再发放问卷。
4. 客户确认的是“本费用周期全部协议费用是否收到”，不逐项目确认。
5. 问卷不关联第三方订单、销售凭证、活动、优惠券或费用明细。
6. 问卷不依赖 `fee_recipient_id`、问卷令牌或应发金额快照完成关联。
7. `fee_recipient_id` 可以作为数据库内部主键，但不进入问卷，也不参与答卷匹配。
8. 应发表是客户确认对账的主表，使用 `LEFT JOIN` 保留未提交问卷的应发客户。
9. 客户名称、手机号和地址只用于展示或人工核对，不作为自动关联键。
10. 现有第三方实际费用核算逻辑及 RESULT 表不因本设计发生变化。

## 3. 范围

### 3.1 本期包含

- 太古客资和客资映射的同步快照；
- 第三方平台稳定客户身份；
- 费用周期；
- 客户周期应发总额；
- 应发客户到第三方平台客户的映射结果；
- 问卷星答卷导入批次；
- 原始答卷历史；
- 最新有效答卷和客户周期对账视图；
- 未提交、名单外答卷、重复答卷和冲突答卷识别。

### 3.2 本期不包含

- 按单个费用项目确认；
- 问卷与第三方订单关联；
- 问卷与销售凭证关联；
- 问卷与主券、副券或优惠券核销关联；
- 客户在问卷中确认某张订单、某张券或某个活动；
- 自动将“未收到”客户转入下一周期不予发放；
- 按预设线路组织问卷发送或催收；
- 对现有第三方费用核算引擎进行口径调整。

## 4. 核心业务键

客户确认对账的自然键为：

```text
fee_cycle_code + sap_customer_code
```

数据库内部使用 `fee_cycle_id` 外键后，对应约束为：

```sql
UNIQUE (fee_cycle_id, sap_customer_code)
```

太古客户编号、第三方客户编号、线路号、办事处代码和合作伙伴编号全部按字符串保存，保留前导零。

## 5. 数据分层

| 数据域 | 职责 |
| --- | --- |
| 太古客资 | 保存太古客户标准身份快照 |
| 客资映射 | 保存太古客户与第三方平台客户的映射快照 |
| 应发费用 | 保存每个周期、每个太古客户的应发总额 |
| 第三方执行 | 继续使用现有活动、订单、优惠券、履约和费用 RESULT |
| 客户确认 | 保存问卷答卷并完成客户周期级对账 |

## 6. 表结构

### 6.1 `master_sync_batch`

记录从数采通同步太古客资和客资映射的批次。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `master_sync_batch_id` | BIGINT | 主键 |
| `source_system` | VARCHAR(50) | 来源系统，固定为数采通 |
| `source_database` | VARCHAR(100) | 来源数据库标识 |
| `started_at` | DATETIME | 同步开始时间 |
| `completed_at` | DATETIME | 同步完成时间 |
| `status` | VARCHAR(20) | `running`、`success`、`failed` |
| `customer_count` | INT | 太古客资数量 |
| `mapping_count` | INT | 客资映射数量 |
| `error_message` | VARCHAR(1000) | 失败原因 |

### 6.2 `taikoo_customer_snapshot`

保存同步取得的太古客资快照，主要字段包括：

```text
master_sync_batch_id
sap_customer_primary_key
sap_customer_code
sap_customer_name
region_code
region_name
sales_office_code
office_name
presale_route
storefront_address
ship_to_address
contact_name
phone_no
mobile_no
channel_group
sub_channel_code
customer_status
partner_code
partner_name
self_sale_flag
source_imported_at
```

约束和索引：

```sql
UNIQUE (master_sync_batch_id, sap_customer_primary_key)
INDEX (master_sync_batch_id, sap_customer_code)
```

### 6.3 `customer_mapping_snapshot`

保存太古客户与第三方客户之间的映射快照，主要字段包括：

```text
master_sync_batch_id
source_mapping_id
area_partner_dealer_id
dealer_platform_id
source_customer_primary_key
source_customer_code
source_customer_name
sap_customer_primary_key
sap_customer_code
sap_customer_name
match_status
hit_field
mapping_source
manual_override
confirmed_at
source_last_seen_at
```

只有以下映射可以用于应发名单转换：

```text
match_status IN ('匹配成功', '已确认')
AND sap_customer_code IS NOT NULL
AND source_customer_code IS NOT NULL
```

“待确认”和“匹配失败”必须保留为异常，不得自动选择客户。

### 6.4 `platform_customer_identity`

保存第三方平台客户的稳定身份，解决现有 `customer` 表按导入批次重复保存客户的问题。

| 字段 | 说明 |
| --- | --- |
| `platform_customer_identity_id` | 主键 |
| `dealer_platform_id` | 经销商及平台 |
| `platform_customer_no` | 第三方客户编号 |
| `latest_customer_name` | 最新客户名称 |
| `first_seen_at` | 首次出现时间 |
| `last_seen_at` | 最近出现时间 |
| `status` | `active` 或 `inactive` |

约束：

```sql
UNIQUE (dealer_platform_id, platform_customer_no)
```

现有 `customer` 表继续保存导入批次客户快照，不承担跨批次稳定身份。

### 6.5 `fee_cycle`

定义一个客户确认和费用对账周期。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `fee_cycle_id` | BIGINT | 主键 |
| `fee_cycle_code` | VARCHAR(20) | 周期代码，第一阶段采用 `YYYY-MM` |
| `cycle_name` | VARCHAR(100) | 展示名称 |
| `period_start` | DATE | 周期开始日期 |
| `period_end` | DATE | 周期结束日期 |
| `status` | VARCHAR(20) | `draft`、`imported`、`executing`、`confirming`、`closed` |
| `created_at` | DATETIME | 创建时间 |
| `closed_at` | DATETIME | 关闭时间 |

约束：

```sql
UNIQUE (fee_cycle_code)
```

### 6.6 `fee_recipient`

保存每个费用周期的客户级应发总额。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `fee_recipient_id` | BIGINT | 数据库内部主键 |
| `fee_cycle_id` | BIGINT | 费用周期 |
| `sap_customer_code` | VARCHAR(50) | 太古客户编号 |
| `sap_customer_name` | VARCHAR(255) | 导入时客户名称 |
| `expected_amount` | DECIMAL(18,2) | 本期全部协议费用应发总额 |
| `dealer_platform_id` | BIGINT NULL | 确定的第三方平台 |
| `platform_customer_identity_id` | BIGINT NULL | 映射后的第三方客户 |
| `platform_customer_no` | VARCHAR(100) NULL | 第三方客户编号快照 |
| `mapping_snapshot_id` | BIGINT NULL | 使用的客资映射快照 |
| `mapping_status` | VARCHAR(20) | `pending`、`matched`、`unmatched`、`ambiguous` |
| `mapping_reason` | VARCHAR(500) NULL | 未匹配或多义原因 |
| `handoff_status` | VARCHAR(20) | `pending`、`exported`、`configured` |
| `source_row_no` | INT NULL | 应发名单来源行 |
| `remark` | VARCHAR(500) NULL | 备注 |
| `created_at` | DATETIME | 创建时间 |

核心约束：

```sql
UNIQUE (fee_cycle_id, sap_customer_code)
CHECK (expected_amount > 0)
```

本表不保存 `confirmation_status`。客户确认状态由答卷对账视图计算，避免重复状态发生漂移。

### 6.7 `fee_cycle_activity`

关联费用周期和第三方平台活动，用于按周期汇总第三方执行结果。

| 字段 | 说明 |
| --- | --- |
| `fee_cycle_activity_id` | 主键 |
| `fee_cycle_id` | 费用周期 |
| `activity_id` | 现有 EC101 活动 |
| `dealer_platform_id` | 经销商平台 |
| `created_at` | 创建时间 |

该表不用于关联问卷和订单。

### 6.8 `survey_import_batch`

记录一次问卷星答卷文件导入。

| 字段 | 说明 |
| --- | --- |
| `survey_import_batch_id` | 主键 |
| `fee_cycle_id` | 所属费用周期 |
| `source_file_name` | 文件名 |
| `source_file_sha256` | 文件哈希 |
| `imported_at` | 导入时间 |
| `row_count` | 原始记录数 |
| `matched_count` | 匹配到应发表的记录数 |
| `unmatched_count` | 未匹配记录数 |
| `status` | `imported` 或 `failed` |
| `error_message` | 失败原因 |

相同文件哈希不得重复导入同一费用周期。

### 6.9 `survey_response`

保存问卷星原始答卷历史。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `survey_response_id` | BIGINT | 主键 |
| `survey_import_batch_id` | BIGINT | 导入批次 |
| `fee_cycle_id` | BIGINT | 费用周期 |
| `sap_customer_code` | VARCHAR(50) | 太古客户编号 |
| `sap_customer_name` | VARCHAR(255) | 答卷中的客户名称 |
| `received_answer` | VARCHAR(20) | `received` 或 `not_received` |
| `not_received_reason` | VARCHAR(500) NULL | 未收到原因 |
| `customer_comment` | VARCHAR(1000) NULL | 补充说明 |
| `respondent_mobile` | VARCHAR(50) NULL | 答卷手机号，仅用于核对 |
| `submitted_at` | DATETIME | 提交时间 |
| `raw_sequence_no` | VARCHAR(50) | 问卷星原始序号 |
| `match_status` | VARCHAR(30) | `matched`、`not_in_recipient_list`、`invalid` |
| `match_reason` | VARCHAR(500) NULL | 未匹配原因 |
| `response_fingerprint` | VARCHAR(64) | 答卷指纹 |
| `imported_at` | DATETIME | 导入时间 |

约束和索引：

```sql
UNIQUE (survey_import_batch_id, raw_sequence_no)
UNIQUE (response_fingerprint)
INDEX (fee_cycle_id, sap_customer_code, submitted_at)
```

不得对 `(fee_cycle_id, sap_customer_code)` 设置唯一约束，因为同一客户可能重复提交问卷，全部答卷历史都必须保留。

`survey_response` 不得包含：

- `fee_recipient_id`；
- 问卷令牌；
- 应发金额快照；
- 第三方订单号或 `order_id`；
- 销售凭证号；
- 订单金额或订单箱数；
- 主券号、副券号或优惠券核销标识。

## 7. 应发名单标准字段

第一阶段标准应发名单只要求：

```text
费用周期
太古客户编号
太古客户名称
应发金额
备注（可选）
```

导入前必须完成费用项目汇总。数据库不保存一条客户周期记录下的项目确认明细。

如来源是历史乐客通发券明细，应先按以下键去重：

```text
太古客户编号 + 费用发放月 + 主券号
```

每张主券金额取唯一主券金额，再汇总为客户周期应发总额。不得直接对重复出现在副券或生动化明细行中的“金额”列求和。

## 8. 问卷标准字段

问卷只需带回：

```text
费用周期
太古客户编号
太古客户名称
是否收到本期全部协议费用
未收到原因
补充说明
答卷手机号
提交时间
问卷星原始序号
```

推荐问题：

> 您是否已经收到本费用周期应发的全部协议费用？

答案为“已收到”或“尚未收到”。选择“尚未收到”时要求填写原因。

## 9. 导入规则

### 9.1 应发名单

1. 明确费用周期。
2. 客户编号按字符串读取。
3. 应发金额转换为两位小数并要求大于零。
4. 多费用项目先在导入前汇总。
5. 汇总后，同周期、同客户只能产生一条记录。
6. 重复自然键不得静默覆盖。

### 9.2 客资映射

系统按太古客户编号查询当前有效客资映射：

- 唯一有效映射：`matched`；
- 无有效映射：`unmatched`；
- 多个有效映射且无法确定目标平台：`ambiguous`。

### 9.3 问卷答卷

导入文件或导入界面必须明确指定费用周期。答卷匹配条件固定为：

```text
survey_response.fee_cycle_id = fee_recipient.fee_cycle_id
AND survey_response.sap_customer_code = fee_recipient.sap_customer_code
```

匹配结果：

- 找到应发客户：`matched`；
- 找不到应发客户：`not_in_recipient_list`；
- 周期、客户编号或答案无效：`invalid`。

未匹配答卷必须保留，不能丢弃。

## 10. 重复答卷

系统保存全部答卷，但客户周期对账只使用最新一条有效答卷。

有效答卷选择顺序：

```text
submitted_at DESC
survey_response_id DESC
```

如果同一客户同一周期既回答“已收到”又回答“未收到”：

- 保留全部答卷；
- 当前展示仍使用最新答卷；
- 同时标记 `has_conflict = 1`；
- 进入人工核查列表。

## 11. 对账视图

### 11.1 `v_effective_survey_response`

按费用周期和太古客户编号选择最新有效答卷：

```sql
ROW_NUMBER() OVER (
  PARTITION BY fee_cycle_id, sap_customer_code
  ORDER BY submitted_at DESC, survey_response_id DESC
)
```

只取 `row_number = 1`，同时计算同一客户周期是否存在相互冲突的答案。

### 11.2 `v_fee_confirmation_reconciliation`

应发表为主表，通过 `LEFT JOIN` 关联最新有效答卷：

```sql
SELECT
  c.fee_cycle_code,
  f.sap_customer_code,
  f.sap_customer_name,
  f.expected_amount,
  s.received_answer,
  s.not_received_reason,
  s.customer_comment,
  s.submitted_at,
  CASE
    WHEN s.survey_response_id IS NULL THEN '未提交'
    WHEN s.has_conflict = 1 THEN '答卷冲突'
    WHEN s.received_answer = 'received' THEN '已确认收到'
    WHEN s.received_answer = 'not_received' THEN '确认未收到'
    ELSE '答卷无效'
  END AS confirmation_status
FROM fee_recipient f
JOIN fee_cycle c
  ON c.fee_cycle_id = f.fee_cycle_id
LEFT JOIN v_effective_survey_response s
  ON s.fee_cycle_id = f.fee_cycle_id
 AND s.sap_customer_code = f.sap_customer_code;
```

`LEFT JOIN` 确保未提交问卷的应发客户仍出现在结果中。

## 12. 核心指标

基于对账视图计算：

- 应发客户数和应发总金额；
- 已提交、未提交问卷的客户数和应发金额；
- 确认已收到的客户数和对应应发金额；
- 确认未收到的客户数和对应应发金额；
- 答卷冲突客户数和对应应发金额；
- 名单外答卷数；
- 客资未匹配、映射多义的客户数和应发金额。

“确认已收到金额”是确认已收到客户在应发表中的 `expected_amount` 合计，不是客户在问卷中填写或确认的具体金额。

## 13. 与第三方执行数据的边界

第三方执行继续使用现有活动、订单、优惠券、履约和 RESULT 表。

第三方执行路径：

```text
fee_cycle
→ fee_cycle_activity
→ activity / activity_execution
→ 第三方平台客户
→ 客资映射
→ 太古客户
```

客户确认路径：

```text
fee_cycle
→ fee_recipient
← survey_response
```

两条路径只在“费用周期 + 太古客户编号”层面并列展示。问卷答卷不与订单、活动或优惠券建立外键。

## 14. 预设线路

第一阶段不新增预设线路表。应发名单对账只依赖费用周期、太古客户编号和应发金额，客资映射已有线路字段。

后续只有在以下场景出现时再同步线路源表：

- 按线路分配问卷催收；
- 按线路统计问卷回收率；
- 乐客通发送必须按线路组织客户。

## 15. 数据安全

- 手机号、联系人、地址和问卷原始文件按敏感数据管理；
- 导出默认隐藏手机号；
- 问卷导入文件记录哈希，不提交代码仓库；
- 云端数据库账号按最小权限配置；
- EC101 读取数采通客资和映射时使用只读权限；
- 不在数据库、源码或日志中保存明文凭据。

## 16. 验收标准

1. 同一费用周期、同一太古客户只能有一条应发记录。
2. 多费用项目可正确汇总为客户周期应发总额。
3. 历史副券或生动化明细不会造成应发金额重复累计。
4. 问卷答卷只按费用周期和太古客户编号匹配。
5. 答卷表不存在订单、券或销售凭证关联字段。
6. 未提交问卷的应发客户可通过 `LEFT JOIN` 查出。
7. 名单外答卷得到保留并进入异常列表。
8. 重复答卷全部保留，最新有效答卷用于当前展示。
9. 相互冲突的答卷能够识别并进入人工核查。
10. 客资未匹配或多义不会通过名称、电话或地址自动兜底。
11. 第三方实际费用和客户确认结果只在客户周期层面汇总对照。
12. 客户确认语义始终是“本费用周期全部协议费用是否收到”。
13. 现有费用核算逻辑和 RESULT 表保持不变。
