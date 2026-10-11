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
