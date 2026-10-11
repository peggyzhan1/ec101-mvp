PRAGMA foreign_keys = ON;

CREATE TABLE import_batch (
  import_batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_key TEXT NOT NULL UNIQUE,
  dealer_name TEXT NOT NULL,
  platform_name TEXT NOT NULL,
  coverage_start TEXT,
  coverage_end TEXT,
  template_version TEXT NOT NULL,
  converter_version TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  status TEXT NOT NULL,
  is_current INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE import_file (
  import_file_id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id INTEGER NOT NULL REFERENCES import_batch(import_batch_id),
  file_role TEXT NOT NULL,
  file_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  file_size INTEGER NOT NULL
);
CREATE TABLE import_validation_issue (
  issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id INTEGER REFERENCES import_batch(import_batch_id),
  code TEXT NOT NULL,
  sheet_name TEXT,
  row_number INTEGER,
  column_name TEXT,
  message TEXT NOT NULL
);

CREATE TABLE dealer_platform (
  dealer_platform_id INTEGER PRIMARY KEY AUTOINCREMENT,
  dealer_name TEXT NOT NULL,
  platform_name TEXT NOT NULL,
  UNIQUE(dealer_name, platform_name)
);
CREATE TABLE customer (
  customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id INTEGER NOT NULL REFERENCES import_batch(import_batch_id),
  dealer_platform_id INTEGER NOT NULL REFERENCES dealer_platform(dealer_platform_id),
  customer_no TEXT NOT NULL,
  customer_name TEXT NOT NULL,
  customer_type TEXT,
  customer_region TEXT,
  address TEXT,
  phone TEXT,
  added_at TEXT,
  salesperson TEXT,
  UNIQUE(import_batch_id, customer_no)
);
CREATE TABLE product (
  product_id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id INTEGER NOT NULL REFERENCES import_batch(import_batch_id),
  dealer_platform_id INTEGER NOT NULL REFERENCES dealer_platform(dealer_platform_id),
  product_no TEXT NOT NULL,
  product_name TEXT NOT NULL,
  brand TEXT,
  category TEXT,
  barcode TEXT,
  spec TEXT,
  base_unit TEXT,
  box_conversion TEXT,
  base_qty_per_box NUMERIC,
  UNIQUE(import_batch_id, product_no)
);
CREATE TABLE order_header (
  order_id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id INTEGER NOT NULL REFERENCES import_batch(import_batch_id),
  dealer_platform_id INTEGER NOT NULL REFERENCES dealer_platform(dealer_platform_id),
  order_no TEXT NOT NULL,
  order_time TEXT,
  customer_no TEXT NOT NULL,
  customer_name TEXT,
  salesperson TEXT,
  order_source TEXT,
  order_type TEXT,
  order_status TEXT NOT NULL,
  payment_method TEXT,
  downstream_order_no TEXT,
  UNIQUE(import_batch_id, order_no)
);
CREATE TABLE order_line (
  order_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id INTEGER NOT NULL REFERENCES order_header(order_id),
  product_no TEXT NOT NULL,
  product_name TEXT,
  category TEXT,
  spec TEXT,
  barcode TEXT,
  unit TEXT,
  quantity NUMERIC,
  pre_discount_amount NUMERIC,
  activity_numbers TEXT,
  coupon_numbers TEXT,
  discount_amount NUMERIC,
  paid_amount NUMERIC,
  unit_price NUMERIC,
  return_qty NUMERIC
);

CREATE TABLE activity (
  activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id INTEGER NOT NULL REFERENCES import_batch(import_batch_id),
  activity_no TEXT NOT NULL,
  activity_name TEXT NOT NULL,
  activity_type TEXT NOT NULL,
  promo_method TEXT,
  start_time TEXT,
  end_time TEXT,
  allow_activity_stack TEXT,
  allow_coupon_stack TEXT,
  activity_status TEXT,
  UNIQUE(import_batch_id, activity_no)
);
CREATE TABLE activity_rule (
  activity_rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_id INTEGER NOT NULL REFERENCES activity(activity_id),
  rule_no TEXT NOT NULL,
  threshold_type TEXT NOT NULL,
  threshold_value NUMERIC,
  reduce_amount NUMERIC,
  free_shipping INTEGER DEFAULT 0,
  UNIQUE(activity_id, rule_no)
);
CREATE TABLE activity_benefit (
  activity_benefit_id INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_id INTEGER NOT NULL REFERENCES activity(activity_id),
  rule_no TEXT NOT NULL,
  benefit_no TEXT NOT NULL,
  benefit_type TEXT NOT NULL,
  gift_product_no TEXT,
  gift_product_name TEXT,
  gift_qty NUMERIC,
  gift_unit TEXT,
  UNIQUE(activity_id, rule_no, benefit_no)
);
CREATE TABLE activity_scope (
  activity_scope_id INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_id INTEGER NOT NULL REFERENCES activity(activity_id),
  scope_no TEXT NOT NULL,
  scope_category TEXT NOT NULL,
  scope_dimension TEXT NOT NULL,
  scope_value TEXT NOT NULL
);
CREATE TABLE activity_execution (
  activity_execution_id INTEGER PRIMARY KEY AUTOINCREMENT,
  activity_id INTEGER NOT NULL REFERENCES activity(activity_id),
  order_id INTEGER NOT NULL REFERENCES order_header(order_id),
  activity_name TEXT,
  customer_no TEXT,
  customer_name TEXT,
  salesperson TEXT,
  product_amount NUMERIC,
  discount_amount NUMERIC,
  UNIQUE(activity_id, order_id)
);
CREATE TABLE fulfillment (
  fulfillment_id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id INTEGER NOT NULL REFERENCES import_batch(import_batch_id),
  order_no TEXT NOT NULL,
  downstream_order_no TEXT,
  fulfillment_status TEXT NOT NULL,
  outbound_at TEXT,
  completed_at TEXT,
  settlement_status TEXT,
  return_qty NUMERIC
);

CREATE TABLE coupon_config (
  coupon_config_id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id INTEGER NOT NULL REFERENCES import_batch(import_batch_id),
  config_no TEXT NOT NULL,
  coupon_name TEXT NOT NULL,
  coupon_type TEXT,
  config_status TEXT NOT NULL,
  UNIQUE(import_batch_id, config_no)
);
CREATE TABLE coupon_issue_rule (
  coupon_issue_rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
  coupon_config_id INTEGER NOT NULL UNIQUE REFERENCES coupon_config(coupon_config_id),
  issue_mode TEXT NOT NULL,
  issue_start_at TEXT NOT NULL,
  issue_end_at TEXT,
  auto_issue_at TEXT,
  qty_per_issue NUMERIC NOT NULL,
  max_claim_per_customer NUMERIC,
  daily_claim_limit NUMERIC,
  rule_status TEXT NOT NULL
);
CREATE TABLE coupon_use_rule (
  coupon_use_rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
  coupon_config_id INTEGER NOT NULL UNIQUE REFERENCES coupon_config(coupon_config_id),
  coupon_type TEXT NOT NULL,
  validity_mode TEXT NOT NULL,
  use_start_at TEXT,
  use_end_at TEXT,
  valid_days_after_receive INTEGER,
  max_use_per_coupon NUMERIC NOT NULL,
  rule_status TEXT NOT NULL
);
CREATE TABLE coupon_scope (
  coupon_scope_id INTEGER PRIMARY KEY AUTOINCREMENT,
  coupon_config_id INTEGER NOT NULL REFERENCES coupon_config(coupon_config_id),
  scope_no TEXT NOT NULL,
  scope_category TEXT NOT NULL,
  scope_dimension TEXT NOT NULL,
  scope_value TEXT NOT NULL
);
CREATE TABLE coupon_redemption (
  coupon_redemption_id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id INTEGER NOT NULL REFERENCES import_batch(import_batch_id),
  order_id INTEGER REFERENCES order_header(order_id),
  coupon_no TEXT NOT NULL,
  customer_no TEXT NOT NULL,
  customer_name TEXT,
  salesperson TEXT,
  receive_time TEXT,
  use_period TEXT,
  status TEXT NOT NULL,
  used_at TEXT,
  discount_amount NUMERIC
);

CREATE TABLE calculation_run (
  calculation_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  import_batch_id INTEGER NOT NULL REFERENCES import_batch(import_batch_id),
  calc_date TEXT NOT NULL DEFAULT '',
  release_cutoff TEXT NOT NULL DEFAULT '',
  activity_benefit NUMERIC NOT NULL DEFAULT 0,
  coupon_benefit NUMERIC NOT NULL DEFAULT 0,
  total_benefit NUMERIC NOT NULL DEFAULT 0,
  released_activity_benefit NUMERIC NOT NULL DEFAULT 0,
  released_coupon_benefit NUMERIC NOT NULL DEFAULT 0,
  theoretical_activity_benefit NUMERIC NOT NULL DEFAULT 0,
  theoretical_coupon_benefit NUMERIC NOT NULL DEFAULT 0,
  consistent_orders INTEGER NOT NULL DEFAULT 0,
  participating_orders INTEGER NOT NULL DEFAULT 0,
  released_orders INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL
);
CREATE TABLE entitlement_check (
  entitlement_check_id INTEGER PRIMARY KEY AUTOINCREMENT,
  calculation_run_id INTEGER NOT NULL REFERENCES calculation_run(calculation_run_id),
  order_id INTEGER REFERENCES order_header(order_id),
  activity_id INTEGER REFERENCES activity(activity_id),
  activity_benefit NUMERIC,
  coupon_benefit NUMERIC,
  total_benefit NUMERIC,
  consistency TEXT,
  theoretical_activity_benefit NUMERIC,
  theoretical_coupon_benefit NUMERIC,
  gift_qty_entitled NUMERIC,
  gift_qty_actual NUMERIC,
  formula_ref TEXT
);
CREATE TABLE release_candidate (
  release_candidate_id INTEGER PRIMARY KEY AUTOINCREMENT,
  calculation_run_id INTEGER NOT NULL REFERENCES calculation_run(calculation_run_id),
  order_id INTEGER NOT NULL REFERENCES order_header(order_id),
  is_candidate INTEGER NOT NULL,
  reason TEXT,
  activity_benefit NUMERIC NOT NULL DEFAULT 0,
  coupon_benefit NUMERIC NOT NULL DEFAULT 0,
  UNIQUE(calculation_run_id, order_id)
);
CREATE TABLE activity_fee_summary (
  activity_fee_summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
  calculation_run_id INTEGER NOT NULL REFERENCES calculation_run(calculation_run_id),
  activity_id INTEGER NOT NULL REFERENCES activity(activity_id),
  actual_discount_total NUMERIC NOT NULL DEFAULT 0,
  gift_cost_total NUMERIC NOT NULL DEFAULT 0,
  participating_orders INTEGER NOT NULL DEFAULT 0,
  released_orders INTEGER NOT NULL DEFAULT 0,
  released_amount NUMERIC NOT NULL DEFAULT 0,
  pending_orders INTEGER NOT NULL DEFAULT 0,
  pending_amount NUMERIC NOT NULL DEFAULT 0,
  gift_qty_entitled NUMERIC,
  gift_qty_actual NUMERIC,
  releasable_discount_total NUMERIC,
  releasable_gift_qty NUMERIC,
  release_order_count INTEGER,
  settle_status TEXT
);
CREATE TABLE coupon_fee_summary (
  coupon_fee_summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
  calculation_run_id INTEGER NOT NULL REFERENCES calculation_run(calculation_run_id),
  coupon_config_id INTEGER REFERENCES coupon_config(coupon_config_id),
  used_count INTEGER NOT NULL DEFAULT 0,
  used_amount NUMERIC NOT NULL DEFAULT 0,
  linked_amount NUMERIC NOT NULL DEFAULT 0,
  releasable_count INTEGER NOT NULL DEFAULT 0,
  releasable_amount NUMERIC NOT NULL DEFAULT 0,
  unlinked_count INTEGER NOT NULL DEFAULT 0,
  unlinked_amount NUMERIC NOT NULL DEFAULT 0,
  settle_status TEXT
);
CREATE TABLE calculation_quality_issue (
  calculation_quality_issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
  calculation_run_id INTEGER NOT NULL REFERENCES calculation_run(calculation_run_id),
  order_no TEXT,
  issue_type TEXT NOT NULL,
  level TEXT NOT NULL,
  reason TEXT NOT NULL
);

CREATE TABLE schema_migration (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE master_sync_batch (
  master_sync_batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_system TEXT NOT NULL DEFAULT '数采通',
  source_database TEXT NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
  customer_count INTEGER NOT NULL DEFAULT 0,
  mapping_count INTEGER NOT NULL DEFAULT 0,
  error_message TEXT
);
CREATE TABLE taikoo_customer_snapshot (
  taikoo_customer_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
  master_sync_batch_id INTEGER NOT NULL REFERENCES master_sync_batch(master_sync_batch_id),
  sap_customer_primary_key TEXT NOT NULL,
  sap_customer_code TEXT NOT NULL,
  sap_customer_name TEXT NOT NULL,
  region_code TEXT,
  region_name TEXT,
  sales_office_code TEXT,
  office_name TEXT,
  presale_route TEXT,
  storefront_address TEXT,
  ship_to_address TEXT,
  contact_name TEXT,
  phone_no TEXT,
  mobile_no TEXT,
  channel_group TEXT,
  sub_channel_code TEXT,
  customer_status TEXT,
  partner_code TEXT,
  partner_name TEXT,
  self_sale_flag TEXT,
  source_imported_at TEXT,
  UNIQUE(master_sync_batch_id, sap_customer_primary_key)
);
CREATE INDEX idx_taikoo_customer_snapshot_code
  ON taikoo_customer_snapshot(master_sync_batch_id, sap_customer_code);

CREATE TABLE platform_customer_identity (
  platform_customer_identity_id INTEGER PRIMARY KEY AUTOINCREMENT,
  dealer_platform_id INTEGER NOT NULL REFERENCES dealer_platform(dealer_platform_id),
  platform_customer_no TEXT NOT NULL,
  latest_customer_name TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  UNIQUE(dealer_platform_id, platform_customer_no)
);
CREATE TABLE customer_mapping_snapshot (
  customer_mapping_snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
  master_sync_batch_id INTEGER NOT NULL REFERENCES master_sync_batch(master_sync_batch_id),
  source_mapping_id TEXT NOT NULL,
  area_partner_dealer_id TEXT,
  dealer_platform_id INTEGER REFERENCES dealer_platform(dealer_platform_id),
  source_customer_primary_key TEXT,
  source_customer_code TEXT,
  source_customer_name TEXT,
  sap_customer_primary_key TEXT,
  sap_customer_code TEXT,
  sap_customer_name TEXT,
  match_status TEXT NOT NULL,
  hit_field TEXT,
  mapping_source TEXT,
  manual_override INTEGER NOT NULL DEFAULT 0 CHECK (manual_override IN (0, 1)),
  confirmed_at TEXT,
  source_last_seen_at TEXT,
  UNIQUE(master_sync_batch_id, source_mapping_id)
);
CREATE INDEX idx_customer_mapping_snapshot_sap
  ON customer_mapping_snapshot(master_sync_batch_id, sap_customer_code, match_status);

CREATE TABLE fee_cycle (
  fee_cycle_id INTEGER PRIMARY KEY AUTOINCREMENT,
  fee_cycle_code TEXT NOT NULL UNIQUE,
  cycle_name TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('draft', 'imported', 'executing', 'confirming', 'closed')),
  created_at TEXT NOT NULL,
  closed_at TEXT
);
CREATE TABLE fee_recipient (
  fee_recipient_id INTEGER PRIMARY KEY AUTOINCREMENT,
  fee_cycle_id INTEGER NOT NULL REFERENCES fee_cycle(fee_cycle_id),
  sap_customer_code TEXT NOT NULL,
  sap_customer_name TEXT NOT NULL,
  expected_amount NUMERIC NOT NULL CHECK (expected_amount > 0),
  dealer_platform_id INTEGER REFERENCES dealer_platform(dealer_platform_id),
  platform_customer_identity_id INTEGER REFERENCES platform_customer_identity(platform_customer_identity_id),
  platform_customer_no TEXT,
  mapping_snapshot_id INTEGER REFERENCES customer_mapping_snapshot(customer_mapping_snapshot_id),
  mapping_status TEXT NOT NULL CHECK (mapping_status IN ('pending', 'matched', 'unmatched', 'ambiguous')),
  mapping_reason TEXT,
  handoff_status TEXT NOT NULL CHECK (handoff_status IN ('pending', 'exported', 'configured')),
  source_row_no INTEGER,
  remark TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(fee_cycle_id, sap_customer_code)
);
CREATE INDEX idx_fee_recipient_mapping_status
  ON fee_recipient(fee_cycle_id, mapping_status);
CREATE TABLE fee_cycle_activity (
  fee_cycle_activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
  fee_cycle_id INTEGER NOT NULL REFERENCES fee_cycle(fee_cycle_id),
  activity_id INTEGER NOT NULL REFERENCES activity(activity_id),
  dealer_platform_id INTEGER NOT NULL REFERENCES dealer_platform(dealer_platform_id),
  created_at TEXT NOT NULL,
  UNIQUE(fee_cycle_id, activity_id)
);

CREATE TABLE survey_import_batch (
  survey_import_batch_id INTEGER PRIMARY KEY AUTOINCREMENT,
  fee_cycle_id INTEGER NOT NULL REFERENCES fee_cycle(fee_cycle_id),
  source_file_name TEXT NOT NULL,
  source_file_sha256 TEXT NOT NULL,
  imported_at TEXT NOT NULL,
  row_count INTEGER NOT NULL DEFAULT 0,
  matched_count INTEGER NOT NULL DEFAULT 0,
  unmatched_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL CHECK (status IN ('imported', 'failed')),
  error_message TEXT,
  UNIQUE(fee_cycle_id, source_file_sha256)
);
CREATE TABLE survey_response (
  survey_response_id INTEGER PRIMARY KEY AUTOINCREMENT,
  survey_import_batch_id INTEGER NOT NULL REFERENCES survey_import_batch(survey_import_batch_id),
  fee_cycle_id INTEGER NOT NULL REFERENCES fee_cycle(fee_cycle_id),
  sap_customer_code TEXT,
  sap_customer_name TEXT,
  received_answer TEXT CHECK (received_answer IN ('received', 'not_received') OR received_answer IS NULL),
  not_received_reason TEXT,
  customer_comment TEXT,
  respondent_mobile TEXT,
  submitted_at TEXT,
  raw_sequence_no TEXT NOT NULL,
  match_status TEXT NOT NULL CHECK (match_status IN ('matched', 'not_in_recipient_list', 'invalid')),
  match_reason TEXT,
  response_fingerprint TEXT NOT NULL UNIQUE,
  imported_at TEXT NOT NULL,
  UNIQUE(survey_import_batch_id, raw_sequence_no)
);
CREATE INDEX idx_survey_response_cycle_customer_submitted
  ON survey_response(fee_cycle_id, sap_customer_code, submitted_at);

CREATE VIEW v_effective_survey_response AS
WITH valid_responses AS (
  SELECT sr.*,
         ROW_NUMBER() OVER (
           PARTITION BY sr.fee_cycle_id, sr.sap_customer_code
           ORDER BY sr.submitted_at DESC, sr.survey_response_id DESC
         ) AS response_rank
  FROM survey_response sr
  WHERE sr.match_status = 'matched'
    AND sr.received_answer IN ('received', 'not_received')
), conflicts AS (
  SELECT fee_cycle_id, sap_customer_code,
         CASE WHEN MIN(received_answer) <> MAX(received_answer) THEN 1 ELSE 0 END AS has_conflict
  FROM valid_responses
  GROUP BY fee_cycle_id, sap_customer_code
)
SELECT v.survey_response_id,
       v.survey_import_batch_id,
       v.fee_cycle_id,
       v.sap_customer_code,
       v.sap_customer_name,
       v.received_answer,
       v.not_received_reason,
       v.customer_comment,
       v.submitted_at,
       v.raw_sequence_no,
       c.has_conflict
FROM valid_responses v
JOIN conflicts c
  ON c.fee_cycle_id = v.fee_cycle_id
 AND c.sap_customer_code = v.sap_customer_code
WHERE v.response_rank = 1;

CREATE VIEW v_fee_confirmation_reconciliation AS
SELECT c.fee_cycle_id,
       c.fee_cycle_code,
       f.fee_recipient_id,
       f.sap_customer_code,
       f.sap_customer_name,
       f.expected_amount,
       f.mapping_status,
       f.mapping_reason,
       f.dealer_platform_id,
       f.platform_customer_identity_id,
       f.platform_customer_no,
       s.survey_response_id,
       s.received_answer,
       s.not_received_reason,
       s.customer_comment,
       s.submitted_at,
       COALESCE(s.has_conflict, 0) AS has_conflict,
       CASE
         WHEN s.survey_response_id IS NULL THEN '未提交'
         WHEN s.has_conflict = 1 THEN '答卷冲突'
         WHEN s.received_answer = 'received' THEN '已确认收到'
         WHEN s.received_answer = 'not_received' THEN '确认未收到'
         ELSE '答卷无效'
       END AS confirmation_status
FROM fee_recipient f
JOIN fee_cycle c ON c.fee_cycle_id = f.fee_cycle_id
LEFT JOIN v_effective_survey_response s
  ON s.fee_cycle_id = f.fee_cycle_id
 AND s.sap_customer_code = f.sap_customer_code;

INSERT INTO schema_migration(version, applied_at)
VALUES ('001_fee_confirmation', CURRENT_TIMESTAMP);
