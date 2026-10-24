import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './endpoints'
import { useAuthStore } from '../stores/auth'
import type { Capabilities, GuideDetail, GuideSettings, GuideSummary, Paginated, Report, RevisionView, TaskDetail, TaskDocument, TaskStats, TaskSummary } from '../types'

type Loader<T> = () => Promise<T>
type QueryState<T> = { data: T | undefined; error: unknown; loading: boolean; refreshing: boolean; refetch: () => Promise<T | undefined> }

const cache = new Map<string, unknown>()
const inflight = new Map<string, Promise<unknown>>()
let authEpoch = 0

function clearQueryState(): void {
  authEpoch += 1
  cache.clear()
  inflight.clear()
}

if (typeof window !== 'undefined') {
  window.addEventListener('fundlex:auth-cleared', clearQueryState)
  window.addEventListener('fundlex:auth-changed', clearQueryState)
}

export function useQuery<T>(key: string, loader: Loader<T>, options: { enabled?: boolean; pollMs?: number } = {}): QueryState<T> {
  const enabled = options.enabled ?? true
  const [data, setData] = useState<T | undefined>(() => cache.get(key) as T | undefined)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(enabled && data === undefined)
  const [refreshing, setRefreshing] = useState(false)
  const loaderRef = useRef(loader)
  const requestSequence = useRef(0)
  loaderRef.current = loader
  useEffect(() => {
    requestSequence.current += 1
    const cached = cache.get(key) as T | undefined
    setData(cached)
    setError(null)
    setLoading(enabled && cached === undefined)
    setRefreshing(false)
  }, [key, enabled])
  const refetch = useCallback(async () => {
    if (!enabled) return undefined
    setRefreshing(data !== undefined)
    setLoading(data === undefined)
    setError(null)
    const requestEpoch = authEpoch
    const requestId = ++requestSequence.current
    let promise = inflight.get(key) as Promise<T> | undefined
    if (!promise) {
      promise = loaderRef.current()
      inflight.set(key, promise)
      promise.finally(() => { if (inflight.get(key) === promise) inflight.delete(key) }).catch(() => undefined)
    }
    try {
      const next = await promise
      if (requestEpoch !== authEpoch || requestId !== requestSequence.current) return undefined
      cache.set(key, next)
      setData(next)
      return next
    } catch (nextError) {
      if (requestEpoch === authEpoch && requestId === requestSequence.current) {
        setError(nextError)
        useAuthStore.getState().handleError(nextError)
      }
      return undefined
    } finally {
      if (requestEpoch === authEpoch && requestId === requestSequence.current) {
        setLoading(false)
        setRefreshing(false)
      }
    }
  }, [data, enabled, key])
  useEffect(() => { void refetch() }, [key, enabled]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const clear = () => { cache.clear(); setData(undefined); setError(null) }
    window.addEventListener('fundlex:auth-cleared', clear)
    window.addEventListener('fundlex:auth-changed', clear)
    return () => {
      window.removeEventListener('fundlex:auth-cleared', clear)
      window.removeEventListener('fundlex:auth-changed', clear)
    }
  }, [])
  useEffect(() => {
    if (!enabled || !options.pollMs) return
    const timer = window.setInterval(() => void refetch(), options.pollMs)
    return () => window.clearInterval(timer)
  }, [enabled, options.pollMs, refetch])
  return { data, error, loading, refreshing, refetch }
}

export function invalidateQuery(keyPrefix: string): void {
  for (const key of cache.keys()) if (key.startsWith(keyPrefix)) cache.delete(key)
}

export function clearQueryCache(): void { clearQueryState() }

export function useCapabilities(): QueryState<Capabilities> { return useQuery('capabilities', api.capabilities) }
export function useTasks(params: Record<string, string | number | undefined> = {}, options?: { pollMs?: number }) { const key = `tasks:${JSON.stringify(params)}`; return useQuery<Paginated<TaskSummary>>(key, () => api.tasks(params), options) }
export function useTaskStats(month?: string) { return useQuery<TaskStats>(`task-stats:${month || 'current'}`, () => api.taskStats(month)) }
export function useTask(id: string | undefined, options?: { pollMs?: number }) { return useQuery<TaskDetail>(`task:${id || ''}`, () => api.task(id as string), { ...options, enabled: Boolean(id) }) }
export function useTaskDocuments(id: string | undefined, params: Record<string, string | number | undefined> = {}, options?: { pollMs?: number }) { return useQuery<Paginated<TaskDocument>>(`documents:${id || ''}:${JSON.stringify(params)}`, () => api.documents(id as string, params), { ...options, enabled: Boolean(id) }) }
export function useAllTaskDocuments(id: string | undefined) {
  return useQuery<TaskDocument[]>(`documents-all:${id || ''}`, async () => {
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
export function useTaskDocument(taskId: string | undefined, documentId: string | undefined) { return useQuery<TaskDocument>(`document:${taskId || ''}:${documentId || ''}`, () => api.document(taskId as string, documentId as string), { enabled: Boolean(taskId && documentId) }) }
export function useGuides(options?: { pollMs?: number }) { return useQuery<{ items: GuideSummary[] }>('guides', api.guides, options) }
export function useGuideSettings(options?: { pollMs?: number }) { return useQuery<GuideSettings>('guide-settings', api.guideSettings, options) }
export function useGuide(id: string | undefined) { return useQuery<GuideDetail>(`guide:${id || ''}`, () => api.guide(id as string), { enabled: Boolean(id) }) }
export function useTaskReport(id: string | undefined) { return useQuery<string>(`task-report:${id || ''}`, () => api.taskReport(id as string), { enabled: Boolean(id) }) }
export function useDocumentReport(taskId: string | undefined, documentId: string | undefined) { return useQuery<Report>(`document-report:${taskId || ''}:${documentId || ''}`, () => api.documentReport(taskId as string, documentId as string), { enabled: Boolean(taskId && documentId) }) }
export function useRevisions(taskId: string | undefined, documentId: string | undefined) { return useQuery<RevisionView>(`revisions:${taskId || ''}:${documentId || ''}`, () => api.revisions(taskId as string, documentId as string), { enabled: Boolean(taskId && documentId) }) }
