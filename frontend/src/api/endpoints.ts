import { download, jsonBody, request, requestText, upload, type UploadProgress } from './client'
import type {
  AuthSession, Capabilities, CreateTaskInput, Decision, DecisionResult,
  GuideDetail, GuideSettings, GuideSummary, Paginated, Report, RevisionView, TaskDetail,
  TaskDocument, TaskStats, TaskSummary, User, UploadResult, CompareTask,
  ComparePairManifest, CompareUploadResult, CompareView,
  FeishuBinding, FeishuBindingCode, FeishuOAuthStart,
} from '../types'

// The API returns JSON objects from the running FastAPI service. Optional fields in
// the shared types intentionally preserve compatibility with historical records.
export const api = {
  capabilities: () => request<Capabilities>('/api/capabilities'),
  login: (username: string, password: string) => request<AuthSession>('/api/auth/login', { method: 'POST', body: jsonBody({ username, password }) }),
  register: (username: string, password: string, display_name = '') => request<AuthSession>('/api/auth/register', { method: 'POST', body: jsonBody({ username, password, display_name }) }),
  logout: () => request<{ ok: boolean }>('/api/auth/logout', { method: 'POST' }),
  me: () => request<User>('/api/auth/me'),
  changePassword: (old_password: string, new_password: string) => request<{ ok: boolean }>('/api/auth/password', { method: 'POST', body: jsonBody({ old_password, new_password }) }),
  feishuBinding: () => request<FeishuBinding>('/api/integrations/feishu/binding'),
  createFeishuBindingCode: (ttl_seconds = 600) => request<FeishuBindingCode>('/api/integrations/feishu/binding-code', { method: 'POST', body: jsonBody({ ttl_seconds }) }),
  startFeishuOAuth: () => request<FeishuOAuthStart>('/api/integrations/feishu/oauth/start', { method: 'POST' }),
  revokeFeishuBinding: () => request<FeishuBinding>('/api/integrations/feishu/binding', { method: 'DELETE' }),

  tasks: (params: Record<string, string | number | undefined> = {}) => request<Paginated<TaskSummary>>(`/api/tasks?${new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== '').map(([key, value]) => [key, String(value)]))}`),
  taskStats: (month?: string) => request<TaskStats>(`/api/tasks/stats${month ? `?month=${encodeURIComponent(month)}` : ''}`),
  task: (id: string) => request<TaskDetail>(`/api/tasks/${encodeURIComponent(id)}`),
  documents: (id: string, params: Record<string, string | number | undefined> = {}) => request<Paginated<TaskDocument>>(`/api/tasks/${encodeURIComponent(id)}/documents?${new URLSearchParams(Object.entries(params).filter(([, value]) => value !== undefined && value !== '').map(([key, value]) => [key, String(value)]))}`),
  document: (taskId: string, documentId: string) => request<TaskDocument>(`/api/tasks/${encodeURIComponent(taskId)}/documents/${encodeURIComponent(documentId)}`),
  createTask: (input: CreateTaskInput, idempotencyKey?: string) => request<TaskSummary>('/api/tasks', { method: 'POST', headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined, body: jsonBody(input) }),
  uploadTask: (id: string, files: File[], clientIds: string[], onProgress?: UploadProgress) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file, file.name))
    form.append('client_ids', JSON.stringify(clientIds))
    return upload<UploadResult>(`/api/tasks/${encodeURIComponent(id)}/uploads`, form, onProgress)
  },
  sealTask: (id: string) => request<TaskSummary>(`/api/tasks/${encodeURIComponent(id)}/seal`, { method: 'POST' }),
  pauseTask: (id: string) => request<TaskSummary>(`/api/tasks/${encodeURIComponent(id)}/pause`, { method: 'POST' }),
  resumeTask: (id: string) => request<TaskSummary>(`/api/tasks/${encodeURIComponent(id)}/resume`, { method: 'POST' }),
  taskReport: (id: string) => requestText(`/api/tasks/${encodeURIComponent(id)}/report`),
  downloadTask: (id: string) => download(`/api/tasks/${encodeURIComponent(id)}/download/all`),

  guides: () => request<{ items: GuideSummary[] }>('/api/guides'),
  guide: (id: string) => request<GuideDetail>(`/api/guides/${encodeURIComponent(id)}`),
  guideSource: (id: string) => download(`/api/guides/${encodeURIComponent(id)}/source`),
  guideRules: (id: string) => request<Record<string, unknown>>(`/api/guides/${encodeURIComponent(id)}/rules`),
  guideSettings: () => request<GuideSettings>('/api/settings/guide'),
  setGuide: (version_id: string | null) => request<GuideSettings>('/api/settings/guide', { method: 'PUT', body: jsonBody({ version_id }) }),
  uploadGuide: (file: File, onProgress?: UploadProgress) => { const form = new FormData(); form.append('file', file, file.name); return upload<{ version: GuideSummary }>('/api/guides', form, onProgress) },
  parseGuide: (id: string) => request<{ version: GuideSummary }>(`/api/guides/${encodeURIComponent(id)}/parse`, { method: 'POST' }),

  documentReport: (taskId: string, documentId: string) => request<Report>(`/api/tasks/${encodeURIComponent(taskId)}/documents/${encodeURIComponent(documentId)}/report`),
  revisions: (taskId: string, documentId: string) => request<RevisionView>(`/api/tasks/${encodeURIComponent(taskId)}/documents/${encodeURIComponent(documentId)}/revisions`),
  decisions: (taskId: string, documentId: string, decisions: Decision[]) => request<DecisionResult>(`/api/tasks/${encodeURIComponent(taskId)}/documents/${encodeURIComponent(documentId)}/decisions`, { method: 'POST', body: jsonBody({ decisions }) }),
  acceptAll: (taskId: string, documentId: string) => request<DecisionResult>(`/api/tasks/${encodeURIComponent(taskId)}/documents/${encodeURIComponent(documentId)}/accept-all`, { method: 'POST' }),
  downloadDocument: (taskId: string, documentId: string, kind: string) => download(`/api/tasks/${encodeURIComponent(taskId)}/documents/${encodeURIComponent(documentId)}/download/${encodeURIComponent(kind)}`),

  compareTasks: () => request<{ items: CompareTask[]; total: number }>('/api/compare/tasks'),
  compareTask: (id: string) => request<CompareTask>(`/api/compare/tasks/${encodeURIComponent(id)}`),
  createCompareTask: (name: string, pairs: ComparePairManifest[], idempotencyKey?: string) => request<CompareTask>('/api/compare/tasks', { method: 'POST', headers: idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : undefined, body: jsonBody({ name, pairs }) }),
  uploadCompareTask: (id: string, files: File[], clientIds: string[]) => { const form = new FormData(); files.forEach((file) => form.append('files', file, file.name)); form.append('client_ids', JSON.stringify(clientIds)); return upload<CompareUploadResult>(`/api/compare/tasks/${encodeURIComponent(id)}/uploads`, form) },
  sealCompareTask: (id: string) => request<CompareTask>(`/api/compare/tasks/${encodeURIComponent(id)}/seal`, { method: 'POST' }),
  compareView: (pairId: string) => request<CompareView>(`/api/compare/pairs/${encodeURIComponent(pairId)}/view`),
}

export type Api = typeof api
