export type Id = string

export interface User {
  id: Id
  username: string
  display_name: string
  role: string
  disabled?: boolean
}

export interface AuthSession {
  token: string
  user: User
}

export interface Capabilities {
  auth_mode?: 'dev' | 'password' | string
  login_required?: boolean
  registration_open?: boolean
  task_api?: boolean
  app_version?: string
  upload_limits?: { max_file_bytes?: number; max_request_bytes?: number }
  engine?: {
    id?: string
    rule_source?: string
    guide?: GuideSummary | null
    delivery_mode?: string
    auto_write_enabled?: boolean
    actions_total?: number
  }
}

export interface FeishuBinding {
  provider: 'feishu' | string
  bound: boolean
  tenant_key?: string
  subject_id?: string
  created_at?: number
  updated_at?: number
}

export interface FeishuBindingCode {
  provider: 'feishu' | string
  code: string
  expires_at: number
}

export interface FeishuOAuthStart {
  provider: 'feishu' | string
  authorization_url: string
  expires_at: number
  qr_svg?: string | null
  qr_png?: string | null
}

export type GuideStatus = 'uploaded' | 'parsing' | 'parsed' | 'validated' | 'released' | 'archived' | 'parse_failed' | string

export interface GuideSummary {
  id: Id
  built_in: boolean
  parent_version_id?: Id
  filename: string
  status: GuideStatus
  qualification_status?: string
  certified?: boolean
  /** Machine-readable reason the version cannot be enabled (null = enableable). */
  enable_block_reason?: 'GUIDE_NOT_PARSED' | 'GUIDE_NOT_CERTIFIED' | null
  review?: { status?: string; dimensions?: Record<string, unknown>; evaluated_at?: string } | null
  document_sha256?: string
  rules_sha256?: string
  groups?: number
  issues?: number
  current?: boolean
  created_at?: string
  updated_at?: string
}

export interface GuideDiffFieldChange { old: unknown; new: unknown }

export interface GuideDiff {
  algorithm: string
  summary: {
    rules_before: number
    rules_after: number
    added: number
    removed: number
    changed: number
    groups_added: number
    groups_removed: number
    groups_order_changed: boolean
    meta_fields_changed: number
    identical: boolean
  }
  rules: {
    added: { rule_id: string; rule: Record<string, unknown> }[]
    removed: { rule_id: string; rule: Record<string, unknown> }[]
    changed: { rule_id: string; fields: Record<string, GuideDiffFieldChange> }[]
  }
  groups: { added: string[]; removed: string[]; order_changed: boolean }
  meta: Record<string, GuideDiffFieldChange>
  validation: { before: GuideValidationSummary; after: GuideValidationSummary }
}

export interface GuideValidationSummary {
  clean: boolean
  errors: number
  warnings: number
  coverage_gaps: number
  findings: number
  invalid_findings: number
  rounds: number
}

export interface GuideDiffResult { version_id: string; against: string; diff: GuideDiff }

export interface GuideDetail extends GuideSummary {
  issues_detail?: Record<string, unknown>
  rules_overview?: RuleOverview[]
  prompt_versions?: Record<string, unknown>
}

export interface RuleOverview {
  rule_id?: string
  title?: string
  section_hint?: string
  operations?: { append?: number; replace?: number; delete?: number; noop?: number }
}

export interface GuideSettings {
  current: GuideSummary | null
  available: GuideSummary[]
  engine_id?: string
}

export interface ModelRoleSettings {
  role: 'primary' | 'review'
  provider?: string
  model?: string
  api_key_set?: boolean
  source?: 'system' | 'personal'
  base_url?: string
  connection_id?: string
  system_model?: string
  legacy_model?: string
}

export interface ModelSettings {
  editable: boolean
  source: 'personal' | 'deployment' | string
  config_error?: string
  primary: ModelRoleSettings
  review: ModelRoleSettings
  review_inherits: boolean
  task_roles?: Record<string, string>
  legacy_preferences?: boolean
  providers: Array<{ id: string; label: string; base_url: string; models: string[] }>
}

export type TaskStatus = 'uploading' | 'queued' | 'running' | 'paused' | 'completed' | 'completed_with_exceptions' | 'failed' | string

export interface GuideSnapshot {
  version_id?: Id
  rules_sha256?: string
}

export interface TaskSummary {
  id: Id
  name: string
  status: TaskStatus
  legacy?: boolean
  engine_id?: string
  ruleset_version?: string
  ruleset_sha256?: string
  guide_snapshot?: GuideSnapshot
  disabled_rule_ids?: string[]
  upload_status?: string
  total?: number
  uploaded?: number
  pending_upload?: number
  rejected?: number
  queued?: number
  processing?: number
  completed?: number
  failed?: number
  successful?: number
  exceptions?: number
  qualification_counts?: Record<string, number>
  delivery_counts?: Record<string, number>
  created_at?: string
  updated_at?: string
  pause_reason?: string | null
  summary_url?: string
  phase?: string
  downloadable_count?: number
}

export interface Paginated<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface TaskDocument {
  task_id?: Id | null
  batch_id?: Id | null
  document_id?: Id | null
  client_id?: string
  name: string
  size?: number
  job_status?: string
  upload_status?: string
  eligibility?: string | null
  delivery_status?: string
  execution_mode?: string
  error_code?: string | null
  reason_codes?: string[]
  report_url?: string | null
  downloads?: Record<string, string>
  source_sha256?: string | null
  phase?: string
  target_counts?: { total?: number; completed?: number; unresolved?: number }
  guide_snapshot?: GuideSnapshot
}

export interface TaskDetail extends TaskSummary {
  documents?: TaskDocument[]
}

export interface TaskStats {
  processed_contracts?: number
  completed_contracts?: number
  pending_contracts?: number
  average_seconds?: number
  exception_contracts?: number
  failed_contracts?: number
  completion_rate?: number
  month_over_month?: number
  active_tasks?: number
  [key: string]: unknown
}

export interface CreateTaskInput {
  name: string
  files: Array<{ client_id: string; name: string; size: number }>
  engine_id: 'recall_first'
  guide_version_id?: string
}

export interface UploadResult {
  receipts?: UploadReceipt[]
  task?: TaskSummary
  items?: TaskDocument[]
  [key: string]: unknown
}

export interface UploadReceipt {
  client_id: string
  status: string
  document_id?: Id | null
  batch_id?: Id | null
  error_code?: string | null
}

export interface Report {
  [key: string]: unknown
}

export interface RevisionView {
  document_id: Id
  html: string
  revisions: Array<Record<string, unknown>>
  meta?: Record<string, unknown>
  download_url?: string
  selection_epoch?: number
  manifest_hash?: string
  decision_hash?: string
}

export interface Decision {
  del_id: number
  decision: 'accept' | 'reject'
}

export interface DecisionResult {
  document_id: Id
  accepted?: number[]
  rejected?: number[]
  sha256?: string
  download_url?: string
  selection_epoch?: number
  manifest_hash?: string
  decision_hash?: string
}

export interface CompareFileManifest {
  client_id: string
  name: string
  size: number
}

export interface ComparePairManifest {
  client_pair_id: string
  label?: string
  left: CompareFileManifest
  right: CompareFileManifest
}

export interface CompareTask {
  id: Id
  name: string
  status: string
  total?: number
  pairs?: ComparePair[]
  counts?: Record<string, number>
  created_at?: string
  updated_at?: string
}

export interface ComparePairSide {
  name: string
  upload_status?: string
  error_code?: string | null
}

export interface ComparePair {
  id: Id
  label?: string
  ordinal?: number
  status: string
  left: ComparePairSide
  right: ComparePairSide
  summary?: { total?: number; modify?: number; insert?: number; delete?: number }
  error_code?: string | null
  diagnostics?: { failure?: { error_code?: string; stage?: string; retryable?: boolean } | null } | null
}

export interface CompareUploadResult {
  receipts?: Array<{ client_id: string; status: string; error_code?: string | null }>
}

export interface CompareSpan {
  block_id: string
  start: number
  end: number
  text: string
}

export interface CompareDiff {
  id: string
  type: 'modify' | 'insert' | 'delete' | string
  section?: string
  left?: CompareSpan
  right?: CompareSpan
  left_spans?: CompareSpan[]
  right_spans?: CompareSpan[]
  left_anchor?: CompareSpan
  right_anchor?: CompareSpan
}

export interface CompareView {
  pair: { id: Id; label?: string; ordinal?: number; status: string }
  left: { name: string; html: string }
  right: { name: string; html: string }
  merged?: { name: string; html: string }
  summary?: { total?: number; modify?: number; insert?: number; delete?: number }
  coverage?: { status?: string; warnings?: string[] }
  diffs: CompareDiff[]
  result_sha256?: string
}

export interface ApiErrorBody {
  detail?: unknown
}

export interface GuideTextDiffRow {
  id: string
  type: 'modify' | 'insert' | 'delete' | string
  type_label: string
  section?: string
  location?: string
  old_text?: string
  new_text?: string
}

export interface GuideTextDiff {
  algorithm: string
  identical: boolean
  summary: { diffs: number; modify: number; insert: number; delete: number }
  diffs: GuideTextDiffRow[]
  left_html: string
  right_html: string
  merged_html: string
}

export interface GuideTextDiffResult { version_id: string; against: string; text_diff: GuideTextDiff }
