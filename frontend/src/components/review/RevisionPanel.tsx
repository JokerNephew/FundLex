import { useEffect, useMemo } from 'react'
import { Button } from '../ui'
import { RevisionCard } from './RevisionCard'
import type { RevisionDecisions, RevisionItem } from './RevisionTypes'
import type { MarkerDecision } from '../document'

export function RevisionPanel({
  revisions,
  decisions,
  activeRevisionId,
  busy = false,
  onFocus,
  onDecision,
  onBulkDecision,
  onPrevious,
  onNext,
  previousDisabled = false,
  nextDisabled = false,
}: {
  revisions: RevisionItem[]
  decisions: RevisionDecisions
  activeRevisionId: string | null
  busy?: boolean
  onFocus: (revisionId: string) => void
  onDecision: (revisionId: string, decision: MarkerDecision) => void
  onBulkDecision: (decision: MarkerDecision) => void
  onPrevious?: () => void
  onNext?: () => void
  previousDisabled?: boolean
  nextDisabled?: boolean
}) {
  const counts = useMemo(() => revisions.reduce((result, revision) => {
    const value = decisions[String(revision.del_id)] || 'pending'
    result[value] += 1
    return result
  }, { pending: 0, accept: 0, reject: 0 } as Record<MarkerDecision, number>), [decisions, revisions])
  useEffect(() => {
    if (!activeRevisionId) return
    document.querySelector(`[data-revision-card="${CSS.escape(activeRevisionId)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [activeRevisionId])
  return <div className="fundlex-revision-panel">
    <div className="fundlex-revision-panel__heading">
      <div><h2>修订清单</h2><p className="fundlex-muted">共 {revisions.length} 条 · 待处理 {counts.pending} · 接受 {counts.accept} · 拒绝 {counts.reject}</p></div>
      <div className="fundlex-revision-panel__bulk">
        <Button type="button" disabled={busy || previousDisabled} onClick={onPrevious}>上一条</Button>
        <Button type="button" disabled={busy || nextDisabled} onClick={onNext}>下一条</Button>
        <Button type="button" disabled={busy || !revisions.length} onClick={() => onBulkDecision('accept')}>全部接受</Button>
        <Button type="button" variant="danger" disabled={busy || !revisions.length} onClick={() => onBulkDecision('reject')}>全部拒绝</Button>
        <Button type="button" variant="quiet" disabled={busy || !revisions.length} onClick={() => onBulkDecision('pending')}>全部待处理</Button>
      </div>
    </div>
    {revisions.length ? <div className="fundlex-revision-list">{revisions.map((revision) => <RevisionCard
      key={revision.del_id}
      revision={revision}
      decision={decisions[String(revision.del_id)] || 'pending'}
      active={String(activeRevisionId) === String(revision.del_id)}
      disabled={busy}
      onFocus={() => onFocus(String(revision.del_id))}
      onDecision={(decision) => onDecision(String(revision.del_id), decision)}
    />)}</div> : <p className="fundlex-empty">这份合同没有可供复核的修订。</p>}
  </div>
}
