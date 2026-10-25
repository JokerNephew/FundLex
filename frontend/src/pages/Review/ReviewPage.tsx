import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { DocumentNavigator, DocumentViewer, type DocumentViewerHandle, SplitPane, type MarkerDecision } from '../../components/document'
import { RevisionPanel, type RevisionDecisions, type RevisionItem } from '../../components/review'
import { Button, Card, Spinner, StatusBadge } from '../../components/ui'
import { useAllTaskDocuments, useReviewMutation, useRevisions, useTaskDocument } from '../../api/hooks'
import { useAuthStore } from '../../stores/auth'
import type { TaskDocument } from '../../types'

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="fundlex-error"><strong>页面暂时无法加载</strong><p>{message}</p>{onRetry && <Button type="button" onClick={onRetry}>重试</Button>}</div>
}

function revisionItems(value: unknown): RevisionItem[] {
  return Array.isArray(value) ? value.filter((item): item is RevisionItem => Boolean(item && typeof item === 'object' && 'del_id' in item)) : []
}

function documentWithId(items: TaskDocument[] | undefined, id: string | undefined): TaskDocument | undefined {
  return items?.find((item) => String(item.document_id || '') === String(id || ''))
}

function revisionFingerprint(items: RevisionItem[], html: string, meta: Record<string, unknown> | undefined): string {
  const payload = JSON.stringify({ html, meta: meta || {}, revisions: items })
  let hash = 2166136261
  for (let index = 0; index < payload.length; index += 1) {
    hash ^= payload.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return (hash >>> 0).toString(16)
}

export function ReviewPage() {
  const { taskId, documentId } = useParams()
  const navigate = useNavigate()
  const documents = useAllTaskDocuments(taskId)
  const documentQuery = useTaskDocument(taskId, documentId)
  const document = documentQuery.data || documentWithId(documents.data, documentId)
  const revisions = useRevisions(taskId, document?.document_id || documentId)
  const user = useAuthStore((state) => state.user)
  const viewerRef = useRef<DocumentViewerHandle>(null)
  const [decisionsByDocument, setDecisionsByDocument] = useState<Record<string, RevisionDecisions>>({})
  const [activeRevisionId, setActiveRevisionId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [mobilePane, setMobilePane] = useState<'left' | 'right'>('left')
  const reviewMutation = useReviewMutation()
  const hydratedDraftKey = useRef<string | null>(null)
  const documentKey = `${taskId || ''}:${document?.document_id || documentId || ''}`
  const items = useMemo(() => revisionItems(revisions.data?.revisions), [revisions.data?.revisions])
  const draftFingerprint = useMemo(() => revisionFingerprint(items, revisions.data?.html || '', revisions.data?.meta), [items, revisions.data?.html, revisions.data?.meta])
  const draftKey = `fundlex-review-draft:${user?.id || user?.username || 'anonymous'}:${documentKey}:${draftFingerprint}`
  const decisions = useMemo(() => decisionsByDocument[documentKey] || {}, [decisionsByDocument, documentKey])
  const updateDecisions = useCallback((next: RevisionDecisions | ((current: RevisionDecisions) => RevisionDecisions)) => {
    setDecisionsByDocument((current) => ({
      ...current,
      [documentKey]: typeof next === 'function' ? next(current[documentKey] || {}) : next,
    }))
  }, [documentKey])

  const usableDocuments = useMemo(() => (documents.data || []).filter((item) => Boolean(item.document_id && (item.downloads?.working_redline || item.downloads?.redline))), [documents.data])
  const currentIndex = Math.max(0, usableDocuments.findIndex((item) => String(item.document_id) === String(document?.document_id)))
  const resolvedCount = items.filter((item) => decisions[String(item.del_id)] && decisions[String(item.del_id)] !== 'pending').length
  const pendingCount = items.length - resolvedCount
  const markerDecisions = useMemo(() => Object.fromEntries(items.flatMap((item) => {
    const decision = decisions[String(item.del_id)] || 'pending'
    return [item.del_id, item.ins_id, ...(item.revision_ids || [])]
      .filter((id): id is number => typeof id === 'number')
      .map((id) => [String(id), decision])
  })) as RevisionDecisions, [decisions, items])
  const activeRevisionIds = useMemo(() => {
    const item = items.find((candidate) => String(candidate.del_id) === String(activeRevisionId))
    return item ? [item.del_id, item.ins_id, ...(item.revision_ids || [])].filter((id): id is number => typeof id === 'number').map(String) : activeRevisionId ? [activeRevisionId] : []
  }, [activeRevisionId, items])

  useEffect(() => {
    const first = items[0]
    setActiveRevisionId((current) => current && items.some((item) => String(item.del_id) === current) ? current : first ? String(first.del_id) : null)
    updateDecisions((current) => Object.fromEntries(items.map((item) => [String(item.del_id), current[String(item.del_id)] || 'pending'])))
  }, [documentKey, items, updateDecisions])

  useEffect(() => {
    if (!items.length || revisions.loading) return
    let stored: RevisionDecisions = {}
    try {
      const raw = localStorage.getItem(draftKey)
      const parsed = raw ? JSON.parse(raw) as { decisions?: RevisionDecisions } : {}
      if (parsed.decisions && typeof parsed.decisions === 'object') stored = parsed.decisions
    } catch {
      stored = {}
    }
    hydratedDraftKey.current = draftKey
    updateDecisions(Object.fromEntries(items.map((item) => [String(item.del_id), stored[String(item.del_id)] || 'pending'])))
  }, [draftKey, items, revisions.loading, updateDecisions])

  useEffect(() => {
    if (!items.length || revisions.loading || hydratedDraftKey.current !== draftKey) return
    try {
      localStorage.setItem(draftKey, JSON.stringify({ version: 1, taskId, documentId: document?.document_id || documentId, revisionFingerprint: draftFingerprint, decisions }))
    } catch {
      // Local draft persistence is best effort; the server remains authoritative.
    }
  }, [decisions, document?.document_id, documentId, draftFingerprint, draftKey, items.length, revisions.loading, taskId])

  const revisionKey = useCallback((revisionId: string) => {
    const item = items.find((candidate) => [candidate.del_id, candidate.ins_id, ...(candidate.revision_ids || [])].some((id) => String(id) === revisionId))
    return item ? String(item.del_id) : revisionId
  }, [items])

  const setRevisionDecision = useCallback((revisionId: string, decision: MarkerDecision) => {
    const primaryId = revisionKey(revisionId)
    setActiveRevisionId(primaryId)
    updateDecisions((current) => ({ ...current, [primaryId]: decision }))
    setMobilePane('right')
  }, [revisionKey, updateDecisions])

  const selectRevision = useCallback((revisionId: string) => {
    const primaryId = revisionKey(revisionId)
    setActiveRevisionId(primaryId)
    viewerRef.current?.scrollToRevision(revisionId)
  }, [revisionKey])

  const moveRevision = (direction: -1 | 1) => {
    const index = items.findIndex((item) => String(item.del_id) === String(activeRevisionId))
    const next = items[index + direction]
    if (next) selectRevision(String(next.del_id))
  }
  const activeRevisionIndex = items.findIndex((item) => String(item.del_id) === String(activeRevisionId))

  const moveDocument = (direction: -1 | 1) => {
    const next = usableDocuments[currentIndex + direction]
    if (next?.document_id) {
      navigate(`/tasks/${taskId}/documents/${next.document_id}/review`, { replace: true })
    }
  }

  const generate = async () => {
    if (!taskId || !document?.document_id || busy) return
    if (pendingCount) {
      setError(`还有 ${pendingCount} 条修订处于“待处理”，请逐条决定或使用批量接受/拒绝。`)
      return
    }
    setBusy(true); setError(''); setMessage('正在生成选择版合同…')
    try {
      const allAccepted = items.every((item) => decisions[String(item.del_id)] === 'accept')
      const result = await reviewMutation.mutateAsync({ taskId, documentId: document.document_id, allAccepted, decisions: items.map((item) => ({
          del_id: item.del_id,
          decision: decisions[String(item.del_id)] === 'reject' ? 'reject' : 'accept',
        })) })
      setMessage(`已生成选择版合同：接受 ${result.accepted?.length || 0} 条，拒绝 ${result.rejected?.length || 0} 条。`)
      await documents.refetch()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '生成选择版合同失败，请稍后重试。')
      setMessage('')
    } finally { setBusy(false) }
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (busy || event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return
      const target = event.target as HTMLElement | null
      if (target && ['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(target.tagName)) return
      const current = activeRevisionId || (items[0] && String(items[0].del_id))
      if (!current) return
      const index = items.findIndex((item) => String(item.del_id) === current)
      if (event.key.toLowerCase() === 'a') { event.preventDefault(); setRevisionDecision(current, 'accept'); return }
      if (event.key.toLowerCase() === 'r') { event.preventDefault(); setRevisionDecision(current, 'reject'); return }
      if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
        event.preventDefault(); const next = items[index + (event.key === 'ArrowUp' ? -1 : 1)]
        if (next) selectRevision(String(next.del_id))
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [activeRevisionId, busy, items, selectRevision, setRevisionDecision])

  if (documents.error || documentQuery.error) return <ErrorState message="合同读取失败。" onRetry={() => { void documents.refetch(); void documentQuery.refetch() }} />
  if ((documents.loading || documentQuery.loading) && !documents.data && !documentQuery.data) return <Card><Spinner label="正在读取合同" /></Card>
  if (!document) return <Card><div className="fundlex-empty">找不到这份合同，或当前账号没有访问权限。</div></Card>
  if (revisions.error) return <ErrorState message="修订呈现读取失败，合同报告仍可返回查看。" onRetry={() => void revisions.refetch()} />
  if (revisions.loading && !revisions.data) return <Card><Spinner label="正在生成合同呈现" /></Card>
  const html = revisions.data?.html || ''
  const revisionData = revisions.data?.revisions || []
  return <div className="fundlex-review-page">
    
    <header className="fundlex-review-header">
      <div><div className="fundlex-review-meta"><Link to={`/tasks/${taskId}/documents/${document.document_id}/report`}>← 返回合同详情</Link><StatusBadge value={document.delivery_status} /></div><h1>修订复核</h1><p className="muted">{document.name} · 已处理 {resolvedCount} / {items.length} 条</p></div>
       <div className="fundlex-review-actions"><DocumentNavigator index={currentIndex} total={usableDocuments.length} disabled={busy} onPrevious={() => moveDocument(-1)} onNext={() => moveDocument(1)} /><Button variant="primary" type="button" disabled={busy || !items.length || pendingCount > 0} onClick={() => void generate()}>生成选择版合同</Button></div>
    </header>
    {(error || message) && <div className={`fundlex-message${error ? ' error' : ''}`} role={error ? 'alert' : 'status'}>{error || message}</div>}
    <div className="fundlex-review-toolbar"><span className="fundlex-review-toolbar__keys">快捷键：A 接受 · R 拒绝 · ↑ / ↓ 定位上一条或下一条</span><span className="fundlex-muted">进度：{resolvedCount} / {items.length} · 待处理 {pendingCount}</span></div>
    <SplitPane
       left={<><div className="fundlex-review-toolbar"><strong>合同原文与修订</strong><span className="fundlex-muted">点击高亮内容可定位右侧修订</span></div><DocumentViewer ref={viewerRef} html={html} activeRevisionId={activeRevisionId} activeRevisionIds={activeRevisionIds} decisions={markerDecisions} onRevisionClick={(id) => { setMobilePane('right'); selectRevision(id) }} /></>}
        right={<RevisionPanel revisions={revisionData as RevisionItem[]} decisions={decisions} activeRevisionId={activeRevisionId} busy={busy} onFocus={(id) => { setMobilePane('left'); selectRevision(id) }} onDecision={setRevisionDecision} onPrevious={() => moveRevision(-1)} onNext={() => moveRevision(1)} previousDisabled={activeRevisionIndex <= 0} nextDisabled={activeRevisionIndex < 0 || activeRevisionIndex >= items.length - 1} onBulkDecision={(decision) => updateDecisions(Object.fromEntries(items.map((item) => [String(item.del_id), decision])))} />}
       leftLabel="合同呈现"
       rightLabel="修订清单"
       mobilePane={mobilePane}
       onMobilePaneChange={setMobilePane}
     />
     <footer className="fundlex-review-actions"><Button type="button" disabled={busy || !items.length} onClick={() => updateDecisions(Object.fromEntries(items.map((item) => [String(item.del_id), 'accept'])))}>批量接受</Button><Button type="button" variant="danger" disabled={busy || !items.length} onClick={() => updateDecisions(Object.fromEntries(items.map((item) => [String(item.del_id), 'reject'])))}>批量拒绝</Button><span className="fundlex-muted">选择版会按每条修订的接受/拒绝结果生成；待处理项不会被默认为接受。</span></footer>
  </div>
}
