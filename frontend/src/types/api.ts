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
  upload_limits?: { max_file_bytes?: number; max_request_files?: number; max_request_bytes?: number }
  engine?: {
    id?: string
    rule_source?: string
    guide?: GuideSummary | null
    delivery_mode?: string
    auto_write_enabled?: boolean
    actions_total?: number
  }
}

export type GuideStatus = 'uploaded' | 'parsing' | 'parsed' | 'validated' | 'released' | 'archived' | 'parse_failed' | string

export interface GuideSummary {
  id: Id
  built_in: boolean
  filename: string
  status: GuideStatus
  qualification_status?: string
  document_sha256?: string
  rules_sha256?: string
  groups?: number
  issues?: number
  current?: boolean
  created_at?: string
  updated_at?: string
}

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

export type TaskStatus = 'uploading' | 'queued' | 'running' | 'paused' | 'completed' | string

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

export interface ComparePair {
  id: Id
  label?: string
  ordinal?: number
  status: string
  left: { name: string }
  right: { name: string }
  summary?: { total?: number; modify?: number; insert?: number; delete?: number }
  error_code?: string | null
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
  summary?: { total?: number; modify?: number; insert?: number; delete?: number }
  coverage?: { status?: string; warnings?: string[] }
  diffs: CompareDiff[]
  result_sha256?: string
}

export interface ApiErrorBody {
  detail?: unknown
}
