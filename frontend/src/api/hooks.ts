import { useMutation, useQuery as useTanStackQuery } from '@tanstack/react-query'
import { useCallback } from 'react'
import { api } from './endpoints'
import { queryClient } from './queryClient'
import type { Capabilities, CompareTask, CompareUploadResult, Decision, GuideDetail, GuideSettings, GuideSummary, Paginated, Report, RevisionView, TaskDetail, TaskDocument, TaskStats, TaskSummary, UploadResult } from '../types'

type QueryState<T> = {
  data: T | undefined
  error: unknown
  loading: boolean
  refreshing: boolean
  refetch: () => Promise<T | undefined>
}

type QueryOptions = { enabled?: boolean; pollMs?: number }

const queryKeys = {
  capabilities: ['capabilities'] as const,
  tasks: (params: Record<string, string | number | undefined>) => ['tasks', params] as const,
  taskStats: (month?: string) => ['task-stats', month || 'current'] as const,
  task: (id: string) => ['task', id] as const,
  documents: (id: string, params: Record<string, string | number | undefined>) => ['documents', id, params] as const,
  documentsAll: (id: string) => ['documents-all', id] as const,
  document: (taskId: string, documentId: string) => ['document', taskId, documentId] as const,
  guides: ['guides'] as const,
  guideSettings: ['guide-settings'] as const,
  guide: (id: string) => ['guide', id] as const,
  taskReport: (id: string) => ['task-report', id] as const,
  documentReport: (taskId: string, documentId: string) => ['document-report', taskId, documentId] as const,
  revisions: (taskId: string, documentId: string) => ['revisions', taskId, documentId] as const,
  compareTasks: ['compare-tasks'] as const,
  compareTask: (id: string) => ['compare-task', id] as const,
  compareView: (pairId: string) => ['compare-view', pairId] as const,
}

function useServerQuery<T>(key: readonly unknown[], loader: () => Promise<T>, options: QueryOptions = {}): QueryState<T> {
  const query = useTanStackQuery({
    queryKey: key,
    queryFn: loader,
    enabled: options.enabled ?? true,
    refetchInterval: options.pollMs,
  })
  const refetch = useCallback(async () => {
    const result = await query.refetch()
    return result.data
  }, [query])
  return {
    data: query.data,
    error: query.error,
    loading: query.isPending,
    refreshing: query.isFetching && !query.isPending,
    refetch,
  }
}

export function useQuery<T>(key: string, loader: () => Promise<T>, options: QueryOptions = {}): QueryState<T> {
  return useServerQuery([key], loader, options)
}

export function invalidateQuery(keyPrefix: string): void {
  const normalized = keyPrefix.replace(/:$/, '')
  void queryClient.invalidateQueries({
    predicate: ({ queryKey }) => {
      const key = String(queryKey[0] || '')
      if (normalized === 'tasks') return key === 'tasks'
      if (normalized === 'guides') return key === 'guides'
      if (normalized === 'guide-settings') return key === 'guide-settings'
      if (normalized === 'documents-all') return key === 'documents-all'
      if (normalized.startsWith('task:')) return key === 'task' && queryKey[1] === normalized.slice(5)
      if (normalized.startsWith('documents-all:')) return key === 'documents-all' && queryKey[1] === normalized.slice(14)
      if (normalized.startsWith('document-report:')) {
        const [, taskId, documentId] = normalized.split(':')
        return key === 'document-report' && queryKey[1] === taskId && queryKey[2] === documentId
      }
      if (normalized.startsWith('task-report:')) return key === 'task-report' && queryKey[1] === normalized.slice(12)
      if (normalized.startsWith('revisions:')) {
        const [, taskId, documentId] = normalized.split(':')
        return key === 'revisions' && queryKey[1] === taskId && queryKey[2] === documentId
      }
      if (normalized === 'compare-tasks') return key === 'compare-tasks'
      if (normalized.startsWith('document:')) {
        const [, taskId, documentId] = normalized.split(':')
        return key === 'document' && queryKey[1] === taskId && queryKey[2] === documentId
      }
      return key === normalized
    },
  })
}

export function clearQueryCache(): void { void queryClient.clear() }

export function useApiMutation<TData, TVariables>(mutationFn: (variables: TVariables) => Promise<TData>, invalidate: string[] = []) {
  return useMutation({
    mutationFn,
    onSuccess: () => invalidate.forEach((key) => invalidateQuery(key)),
  })
}

export function useUploadTaskMutation() { return useApiMutation<UploadResult, { id: string; files: File[]; clientIds: string[]; onProgress?: (loaded: number, total: number) => void }>((value) => api.uploadTask(value.id, value.files, value.clientIds, value.onProgress), ['tasks']) }
export function useSealTaskMutation() { return useApiMutation<TaskSummary, string>((id) => api.sealTask(id), ['tasks']) }
export function useTaskControlMutation() { return useApiMutation<TaskSummary, { id: string; action: 'pause' | 'resume' }>((value) => value.action === 'pause' ? api.pauseTask(value.id) : api.resumeTask(value.id), ['tasks']) }
export function useReviewMutation() {
  return useMutation({
    mutationFn: (value: { taskId: string; documentId: string; decisions?: Decision[]; allAccepted?: boolean }) => value.allAccepted ? api.acceptAll(value.taskId, value.documentId) : api.decisions(value.taskId, value.documentId, value.decisions || []),
    onSuccess: (_result, value) => {
      invalidateQuery(`document:${value.taskId}:${value.documentId}`)
      invalidateQuery(`document-report:${value.taskId}:${value.documentId}`)
      invalidateQuery(`documents-all:${value.taskId}`)
      invalidateQuery(`revisions:${value.taskId}:${value.documentId}`)
    },
  })
}
export function useCompareTaskMutation() { return useApiMutation<CompareTask, { name: string; pairs: Parameters<typeof api.createCompareTask>[1]; key: string }>((value) => api.createCompareTask(value.name, value.pairs, value.key), ['compare-tasks']) }
export function useCompareUploadMutation() { return useApiMutation<CompareUploadResult, { id: string; files: File[]; clientIds: string[] }>((value) => api.uploadCompareTask(value.id, value.files, value.clientIds), ['compare-tasks']) }
export function useCompareSealMutation() { return useApiMutation<CompareTask, string>((id) => api.sealCompareTask(id), ['compare-tasks']) }
export function useGuideMutation() { return useApiMutation<GuideSettings, string | null>((id) => api.setGuide(id), ['guides', 'guide-settings']) }
export function useGuideUploadMutation() { return useApiMutation<{ version: GuideSummary }, File>((file) => api.uploadGuide(file), ['guides']) }
export function useGuideParseMutation() { return useApiMutation<{ version: GuideSummary }, string>((id) => api.parseGuide(id), ['guides']) }

export function useCapabilities(): QueryState<Capabilities> { return useServerQuery(queryKeys.capabilities, api.capabilities) }
export function useTasks(params: Record<string, string | number | undefined> = {}, options?: QueryOptions) { return useServerQuery<Paginated<TaskSummary>>(queryKeys.tasks(params), () => api.tasks(params), options) }
export function useTaskStats(month?: string) { return useServerQuery<TaskStats>(queryKeys.taskStats(month), () => api.taskStats(month)) }
export function useTask(id: string | undefined, options?: QueryOptions) { return useServerQuery<TaskDetail>(queryKeys.task(id || ''), () => api.task(id as string), { ...options, enabled: Boolean(id) }) }
export function useTaskDocuments(id: string | undefined, params: Record<string, string | number | undefined> = {}, options?: QueryOptions) { return useServerQuery<Paginated<TaskDocument>>(queryKeys.documents(id || '', params), () => api.documents(id as string, params), { ...options, enabled: Boolean(id) }) }
export function useAllTaskDocuments(id: string | undefined) {
  return useServerQuery<TaskDocument[]>(queryKeys.documentsAll(id || ''), async () => {
    const items: TaskDocument[] = []
    let page = 1
    let total = Infinity
    while (items.length < total && page <= 100) {
      const result = await api.documents(id as string, { page, page_size: 200, sort: 'oldest' })
      items.push(...result.items)
      total = result.total
      if (!result.items.length) break
      page += 1
    }
    return items
  }, { enabled: Boolean(id) })
}
export function useTaskDocument(taskId: string | undefined, documentId: string | undefined) { return useServerQuery<TaskDocument>(queryKeys.document(taskId || '', documentId || ''), () => api.document(taskId as string, documentId as string), { enabled: Boolean(taskId && documentId) }) }
export function useGuides(options?: QueryOptions) { return useServerQuery<{ items: GuideSummary[] }>(queryKeys.guides, api.guides, options) }
export function useGuideSettings(options?: QueryOptions) { return useServerQuery<GuideSettings>(queryKeys.guideSettings, api.guideSettings, options) }
export function useGuide(id: string | undefined) { return useServerQuery<GuideDetail>(queryKeys.guide(id || ''), () => api.guide(id as string), { enabled: Boolean(id) }) }
export function useTaskReport(id: string | undefined) { return useServerQuery<string>(queryKeys.taskReport(id || ''), () => api.taskReport(id as string), { enabled: Boolean(id) }) }
export function useDocumentReport(taskId: string | undefined, documentId: string | undefined) { return useServerQuery<Report>(queryKeys.documentReport(taskId || '', documentId || ''), () => api.documentReport(taskId as string, documentId as string), { enabled: Boolean(taskId && documentId) }) }
export function useRevisions(taskId: string | undefined, documentId: string | undefined) { return useServerQuery<RevisionView>(queryKeys.revisions(taskId || '', documentId || ''), () => api.revisions(taskId as string, documentId as string), { enabled: Boolean(taskId && documentId) }) }
export function useCompareTasks(options?: QueryOptions) { return useServerQuery<{ items: CompareTask[]; total: number }>(queryKeys.compareTasks, api.compareTasks, options) }
export function useCompareTask(id: string | undefined, options?: QueryOptions) { return useServerQuery<CompareTask>(queryKeys.compareTask(id || ''), () => api.compareTask(id as string), { ...options, enabled: Boolean(id) }) }
export function useCompareView(pairId: string | undefined, options?: QueryOptions) { return useServerQuery<import('../types').CompareView>(queryKeys.compareView(pairId || ''), () => api.compareView(pairId as string), { ...options, enabled: Boolean(pairId) }) }
