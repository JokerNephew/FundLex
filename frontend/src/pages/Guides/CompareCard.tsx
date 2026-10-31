import { useMemo, useState } from 'react'
import { api } from '../../api/endpoints'
import { useGuideDiff } from '../../api/hooks'
import { Button, Card, Spinner } from '../../components/ui'
import { ErrorState } from '../Tasks'
import type { GuideDiffResult, GuideSummary } from '../../types'

const FIELD_LABELS: Record<string, string> = {
  title: '标题',
  requirement: '要求',
  operations: '操作',
  old_text_variants: '旧文变体',
  slot_tokens: '槽位',
  class_substitution: '类别替换',
  references: '依据',
}

const META_LABELS: Record<string, string> = {
  parser_version: '解析器版本',
  schema_version: '结构版本',
  source_sha256: '原件摘要',
  prompt_versions: '提示词版本',
}

function clip(value: unknown, limit = 160): string {
  const text = value === null || value === undefined ? '—'
    : typeof value === 'string' ? value : JSON.stringify(value, null, 0)
  return text.length > limit ? `${text.slice(0, limit)}…` : text
}

/** Rule ids whose owner-level enable switch differs between two versions. */
export function enabledChanges(before: Record<string, boolean>, after: Record<string, boolean>) {
  const disabledNow: string[] = []
  const enabledNow: string[] = []
  for (const ruleId of Object.keys({ ...before, ...after }).sort()) {
    const oldEnabled = before[ruleId]
    const newEnabled = after[ruleId]
    if (oldEnabled === undefined || newEnabled === undefined || oldEnabled === newEnabled) continue
    if (newEnabled) enabledNow.push(ruleId)
    else disabledNow.push(ruleId)
  }
  return { disabledNow, enabledNow }
}

function fieldLabel(name: string) {
  return FIELD_LABELS[name] || META_LABELS[name] || name
}

function DiffView({ result }: { result: GuideDiffResult }) {
  const { diff } = result
  const [enabledNote, setEnabledNote] = useState<string>('')
  const rows: { kind: string; ruleId: string; detail: string }[] = []
  diff.rules.added.forEach((item) => rows.push({ kind: '新增', ruleId: item.rule_id, detail: clip(item.rule.title) }))
  diff.rules.removed.forEach((item) => rows.push({ kind: '删除', ruleId: item.rule_id, detail: clip(item.rule.title) }))
  diff.rules.changed.forEach((item) => rows.push({
    kind: '修改', ruleId: item.rule_id,
    detail: Object.entries(item.fields).map(([field, change]) =>
      `${fieldLabel(field)}：${clip(change.old)} → ${clip(change.new)}`).join('；'),
  }))
  const loadEnabledDiff = async () => {
    setEnabledNote('读取中…')
    try {
      const [before, after] = await Promise.all([
        api.guideRuleSettings(result.against), api.guideRuleSettings(result.version_id)])
      const map = (rules: { rule_id: string; enabled: boolean }[]) =>
        Object.fromEntries(rules.map((rule) => [rule.rule_id, rule.enabled]))
      const change = enabledChanges(map(before.rules), map(after.rules))
      const parts: string[] = []
      if (change.disabledNow.length) parts.push(`停用 ${change.disabledNow.length} 条（${change.disabledNow.join('、')}）`)
      if (change.enabledNow.length) parts.push(`启用 ${change.enabledNow.length} 条（${change.enabledNow.join('、')}）`)
      setEnabledNote(parts.length ? parts.join('；') : '两个版本的规则启停一致。')
    } catch {
      setEnabledNote('启停对比不可用（两版本均需处于可启用状态）。')
    }
  }
  return <>
    <div className="stats-grid" data-testid="guide-diff-summary">
      <div><span className="muted">规则数</span><strong className="stat-value">{diff.summary.rules_before} → {diff.summary.rules_after}</strong></div>
      <div><span className="muted">新增规则</span><strong className="stat-value">{diff.summary.added}</strong></div>
      <div><span className="muted">删除规则</span><strong className="stat-value">{diff.summary.removed}</strong></div>
      <div><span className="muted">修改规则</span><strong className="stat-value">{diff.summary.changed}</strong></div>
    </div>
    {diff.summary.identical && <p className="muted">两个版本的规则内容完全一致。</p>}
    <p className="muted">
      分组变化：新增 {diff.summary.groups_added} / 删除 {diff.summary.groups_removed}{diff.summary.groups_order_changed ? ' / 顺序有变化' : ''}；
      元信息变化 {diff.summary.meta_fields_changed} 项{diff.summary.meta_fields_changed ? `（${Object.keys(diff.meta).map(fieldLabel).join('、')}）` : ''}；
      校验：{diff.validation.before.clean ? '干净' : '有遗留'}→{diff.validation.after.clean ? '干净' : '有遗留'}（发现 {diff.validation.before.findings}→{diff.validation.after.findings}）。
    </p>
    <div className="action-row">
      <Button variant="quiet" onClick={() => void loadEnabledDiff()}>对比规则启停</Button>
      {enabledNote && <span className="muted">{enabledNote}</span>}
    </div>
    {rows.length > 0 && <div className="table-scroll">
      <table className="data-table">
        <thead><tr><th>变化</th><th>规则</th><th>详情</th></tr></thead>
        <tbody>{rows.map((row, index) => <tr key={`${row.kind}-${row.ruleId}-${index}`}>
          <td>{row.kind}</td><td><strong>{row.ruleId}</strong></td><td>{row.detail || '—'}</td>
        </tr>)}</tbody>
      </table>
    </div>}
  </>
}

export function defaultCompareTargets(items: GuideSummary[], currentId?: string): { target: string; against: string } {
  const parsed = items.filter((item) => ['parsed', 'released', 'validated'].includes(item.status))
  const current = parsed.find((item) => item.id === currentId) || parsed[0]
  if (!current) return { target: '', against: '' }
  const parent = current.parent_version_id && parsed.find((item) => item.id === current.parent_version_id)
  const index = parsed.findIndex((item) => item.id === current.id)
  const previous = parsed[index + 1] || parsed.find((item) => item.id !== current.id)
  return { target: current.id, against: (parent || previous || { id: '' }).id }
}

export function CompareCard({ items, currentId }: { items: GuideSummary[]; currentId?: string }) {
  const candidates = useMemo(
    () => items.filter((item) => ['parsed', 'released', 'validated'].includes(item.status)),
    [items])
  const defaults = useMemo(() => defaultCompareTargets(items, currentId), [items, currentId])
  const [target, setTarget] = useState('')
  const [against, setAgainst] = useState('')
  const effectiveTarget = target || defaults.target
  const effectiveAgainst = against || defaults.against
  const diff = useGuideDiff(effectiveTarget, effectiveAgainst)

  if (candidates.length < 2) return null
  const label = (item: GuideSummary) =>
    `${item.filename} · ${item.built_in ? '内置' : '自定义'}${item.current ? '（当前）' : ''}`
  return <Card>
    <div className="page-heading">
      <div>
        <h2>版本对比</h2>
        <p className="muted">任选两个已解析版本查看规则差异。</p>
      </div>
    </div>
    <div className="action-row">
      <label>基准版本
        <select aria-label="基准版本" value={effectiveAgainst} onChange={(event) => setAgainst(event.target.value)}>
          {candidates.filter((item) => item.id !== effectiveTarget).map((item) =>
            <option key={item.id} value={item.id}>{label(item)}</option>)}
        </select>
      </label>
      <label>对比版本
        <select aria-label="对比版本" value={effectiveTarget} onChange={(event) => setTarget(event.target.value)}>
          {candidates.filter((item) => item.id !== effectiveAgainst).map((item) =>
            <option key={item.id} value={item.id}>{label(item)}</option>)}
        </select>
      </label>
    </div>
    {effectiveTarget && effectiveAgainst && effectiveTarget !== effectiveAgainst
      ? diff.error ? <ErrorState error={diff.error} onRetry={() => void diff.refetch()} />
        : diff.loading && !diff.data ? <Spinner />
          : diff.data ? <DiffView result={diff.data} /> : null
      : <p className="muted">选择两个版本后自动加载对比结果。</p>}
  </Card>
}
