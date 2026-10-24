import { Button } from '../ui'
import type { MarkerDecision } from '../document'
import type { RevisionItem } from './RevisionTypes'

const operationLabels: Record<string, string> = { insert: '新增', delete: '删除', replace: '替换' }
const decisionLabels: Record<MarkerDecision, string> = { pending: '待处理', accept: '接受', reject: '拒绝' }

export function RevisionCard({
  revision,
  decision,
  active,
  disabled = false,
  onFocus,
  onDecision,
}: {
  revision: RevisionItem
  decision: MarkerDecision
  active: boolean
  disabled?: boolean
  onFocus: () => void
  onDecision: (decision: MarkerDecision) => void
}) {
  return <article className={`fundlex-revision-card${active ? ' is-active' : ''}${decision === 'reject' ? ' is-rejected' : ''}`} data-revision-card={revision.del_id}>
    <button type="button" className="fundlex-revision-card__focus" onClick={onFocus} aria-label={`定位第 ${revision.index || 0} 条修订`}>
      <span className="fundlex-revision-card__number">#{revision.index || '—'}</span>
      <span>{operationLabels[revision.operation || ''] || revision.operation || '修改'}</span>
      {revision.rule_id && <code>{revision.rule_id}</code>}
      {revision.section && <span className="fundlex-muted">{revision.section}</span>}
    </button>
    <div className="fundlex-revision-card__comparison">
      <div><small>原文</small><p>{revision.before?.trim() || '（无原文，新增内容）'}</p></div>
      <div><small>新文</small><p>{revision.after?.trim() || '（删除该段）'}</p></div>
    </div>
    <div className="fundlex-revision-card__actions" aria-label={`第 ${revision.index || 0} 条修订状态`}>
      {(Object.keys(decisionLabels) as MarkerDecision[]).map((value) => <Button
        key={value}
        type="button"
        variant={decision === value ? (value === 'reject' ? 'danger' : value === 'accept' ? 'primary' : 'secondary') : 'quiet'}
        disabled={disabled}
        aria-pressed={decision === value}
        onClick={() => onDecision(value)}
      >{decisionLabels[value]}</Button>)}
    </div>
  </article>
}
