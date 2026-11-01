import { useMemo, useState } from 'react'
import { api } from '../../api/endpoints'
import { useGuideDiff, useGuideTextDiff } from '../../api/hooks'
import { Button, Card, Spinner } from '../../components/ui'
import { ErrorState } from '../Tasks'
import type { GuideDiffResult, GuideSummary, GuideTextDiffResult } from '../../types'

const FIELD_LABELS: Record<string, string> = {
  title: '标题',
  requirement: '要求',
  operations: '修改操作',
  old_text_variants: '原文线索',
  slot_tokens: '槽位',
  class_substitution: '类别替换',
  references: '依据',
  section_hint: '章节提示',
}

const META_LABELS: Record<string, string> = {
  parser_version: '解析器版本',
  schema_version: '结构版本',
  source_sha256: '原件摘要',
  prompt_versions: '提示词版本',
}

const OP_LABELS: Record<string, string> = {
  append: '追加', replace: '替换为', delete: '删除', noop: '不改',
}

function formatTime(value?: string): string {
  const stamp = Number(value || 0)
  if (!stamp) return ''
  const date = new Date(stamp * 1000)
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}`
}

function fieldLabel(name: string) {
  return FIELD_LABELS[name] || META_LABELS[name] || name
}

function fieldValue(name: string, value: unknown): React.ReactNode {
  if (value === null || value === undefined) return '—'
  if (name === 'operations' && Array.isArray(value)) {
    if (!value.length) return '（无操作）'
    return <ul className="guide-diff-ops">{value.map((op, index) => {
      const item = (op || {}) as { op?: string; new_text?: string }
      const label = OP_LABELS[item.op || ''] || '调整'
      return <li key={index}>{label}{item.new_text ? `「${item.new_text}」` : ''}</li>
    })}</ul>
  }
  if (typeof value === 'string') return value || '—'
  if (Array.isArray(value)) {
    return value.length
      ? value.map((entry) => (typeof entry === 'string' ? entry : JSON.stringify(entry))).join('；')
      : '—'
  }
  return JSON.stringify(value)
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

function RulesDiffView({ result }: { result: GuideDiffResult }) {
  const { diff } = result
  const [enabledNote, setEnabledNote] = useState<string>('')
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
  const summary = diff.summary
  return <>
    <p className="muted" data-testid="guide-diff-summary">
      规则 {summary.rules_before} 条 → {summary.rules_after} 条；新增 {summary.added} · 删除 {summary.removed} · 修改 {summary.changed}
      {summary.identical ? '：两个版本的规则内容完全一致。' : ''}
    </p>
    <p className="muted">
      分组变化：新增 {summary.groups_added} / 删除 {summary.groups_removed}{summary.groups_order_changed ? ' / 顺序有变化' : ''}；
      元信息变化 {summary.meta_fields_changed} 项{summary.meta_fields_changed ? `（${Object.keys(diff.meta).map(fieldLabel).join('、')}）` : ''}；
      校验：{diff.validation.before.clean ? '干净' : '有遗留'}→{diff.validation.after.clean ? '干净' : '有遗留'}（发现 {diff.validation.before.findings}→{diff.validation.after.findings}）。
    </p>
    <div className="guide-diff-grid">
      <section className="guide-diff-group">
        <h3>新增规则 · {diff.rules.added.length} 条</h3>
        {diff.rules.added.length ? <ul className="guide-diff-rules">
          {diff.rules.added.map((item) => <li key={item.rule_id}>
            <strong>{item.rule_id}</strong>{typeof item.rule?.title === 'string' ? ` ${item.rule.title}` : ''}
          </li>)}
        </ul> : <p className="muted">无</p>}
      </section>
      <section className="guide-diff-group">
        <h3>删除规则 · {diff.rules.removed.length} 条</h3>
        {diff.rules.removed.length ? <ul className="guide-diff-rules">
          {diff.rules.removed.map((item) => <li key={item.rule_id}>
            <strong>{item.rule_id}</strong>{typeof item.rule?.title === 'string' ? ` ${item.rule.title}` : ''}
          </li>)}
        </ul> : <p className="muted">无</p>}
      </section>
      <section className="guide-diff-group">
        <h3>修改规则 · {diff.rules.changed.length} 条</h3>
        {diff.rules.changed.length ? diff.rules.changed.map((item) => {
          const fields = Object.entries(item.fields)
          return <details key={item.rule_id} className="guide-diff-change">
            <summary><strong>{item.rule_id}</strong> · {fields.length} 个字段有变化</summary>
            <dl className="guide-diff-fields">
              {fields.map(([name, change]) => <div key={name} className="guide-diff-field">
                <dt>{fieldLabel(name)}</dt>
                <dd>
                  <span className="guide-diff-old">{fieldValue(name, change.old)}</span>
                  <span className="guide-diff-arrow">→</span>
                  <span className="guide-diff-new">{fieldValue(name, change.new)}</span>
                </dd>
              </div>)}
            </dl>
          </details>
        }) : <p className="muted">无</p>}
      </section>
    </div>
    <div className="action-row">
      <Button variant="quiet" onClick={() => void loadEnabledDiff()}>对比规则启停</Button>
      {enabledNote && <span className="muted">{enabledNote}</span>}
    </div>
  </>
}

function TextDiffView({ target, against }: { target: string; against: string }) {
  const [view, setView] = useState<'merged' | 'side'>('merged')
  const diff = useGuideTextDiff(target, against)
  const builtinBlocked = ((diff.error as Error | null)?.message || '').includes('BUILTIN_SOURCE_UNAVAILABLE')
  if (builtinBlocked) {
    return <p className="muted">内置指引没有上传的原文文件，无法做原文比对；可查看「规则差异」，或改用两个自己上传的版本。</p>
  }
  if (diff.error) return <ErrorState error={diff.error} onRetry={() => void diff.refetch()} />
  if (diff.loading && !diff.data) return <Spinner />
  if (!diff.data) return null
  const textDiff = (diff.data as GuideTextDiffResult).text_diff
  const summary = textDiff.summary
  return <>
    <p className="muted">
      {textDiff.identical ? '两个版本的原文完全一致。'
        : `共 ${summary.diffs} 处差异：修改 ${summary.modify} · 新增 ${summary.insert} · 删除 ${summary.delete}`}
      <span className="guide-diff-viewbtns">
        <Button variant={view === 'merged' ? 'primary' : 'quiet'} disabled={view === 'merged'}
          onClick={() => setView('merged')}>合并稿</Button>
        <Button variant={view === 'side' ? 'primary' : 'quiet'} disabled={view === 'side'}
          onClick={() => setView('side')}>并排对照</Button>
      </span>
    </p>
    {view === 'side'
      ? <div className="guide-diff-panes">
        <div className="guide-diff-pane" aria-label="基准版本原文"
          dangerouslySetInnerHTML={{ __html: textDiff.left_html }} />
        <div className="guide-diff-pane" aria-label="对比版本原文"
          dangerouslySetInnerHTML={{ __html: textDiff.right_html }} />
      </div>
      : <div className="guide-diff-merged"
        dangerouslySetInnerHTML={{ __html: textDiff.merged_html }} />}
  </>
}

export function defaultCompareTargets(items: GuideSummary[], currentId?: string): { target: string; against: string } {
  const parsed = items.filter((item) => ['parsed', 'released', 'validated'].includes(item.status))
  // 默认对比「当前自定义版 vs 其来源版」，否则按创建时间取最近两个自定义版；
  // 内置指引只在自定义版本不足或用户主动选择时参与默认对比。
  const customs = parsed.filter((item) => !item.built_in)
    .sort((a, b) => Number(b.created_at || 0) - Number(a.created_at || 0))
  const byId = new Map(parsed.map((item) => [item.id, item]))
  const current = (currentId && byId.get(currentId)) || customs.find((item) => item.current)
  if (current && !current.built_in) {
    const against = (current.parent_version_id && byId.get(current.parent_version_id)?.id)
      || customs.find((item) => item.id !== current.id)?.id
      || parsed.find((item) => item.id !== current.id)?.id || ''
    return { target: current.id, against }
  }
  if (customs.length) {
    const target = customs[0].id
    const against = (customs.find((item) => item.id !== target)
      || parsed.find((item) => item.id !== target))?.id || ''
    return { target, against }
  }
  return { target: parsed[0]?.id || '', against: parsed.find((item) => item.id !== parsed[0]?.id)?.id || '' }
}

export function CompareCard({ items, currentId }: { items: GuideSummary[]; currentId?: string }) {
  const candidates = useMemo(
    () => items.filter((item) => ['parsed', 'released', 'validated'].includes(item.status)),
    [items])
  const defaults = useMemo(() => defaultCompareTargets(items, currentId), [items, currentId])
  const [target, setTarget] = useState('')
  const [against, setAgainst] = useState('')
  const [tab, setTab] = useState<'rules' | 'text'>('rules')
  const effectiveTarget = target || defaults.target
  const effectiveAgainst = against || defaults.against
  const diff = useGuideDiff(effectiveTarget, effectiveAgainst)

  if (candidates.length < 2) return null
  const label = (item: GuideSummary) =>
    `${item.filename}${formatTime(item.created_at as string | undefined) ? ` · ${formatTime(item.created_at as string | undefined)}` : ''}${item.built_in ? '（内置）' : ''}${item.current ? '（当前）' : ''}`
  return <Card>
    <div className="page-heading">
      <div>
        <h2>版本对比</h2>
        <p className="muted">默认对比当前版本与上一版本；选任意两版看规则改动与原文差异，全部在服务器本地计算，不调用模型。</p>
      </div>
    </div>
    <div className="action-row">
      <label>基准版本（旧）
        <select aria-label="基准版本" value={effectiveAgainst} onChange={(event) => setAgainst(event.target.value)}>
          {candidates.filter((item) => item.id !== effectiveTarget).map((item) =>
            <option key={item.id} value={item.id}>{label(item)}</option>)}
        </select>
      </label>
      <label>对比版本（新）
        <select aria-label="对比版本" value={effectiveTarget} onChange={(event) => setTarget(event.target.value)}>
          {candidates.filter((item) => item.id !== effectiveAgainst).map((item) =>
            <option key={item.id} value={item.id}>{label(item)}</option>)}
        </select>
      </label>
    </div>
    {effectiveTarget && effectiveAgainst && effectiveTarget !== effectiveAgainst ? <>
      <div className="guide-diff-tabs" role="tablist" aria-label="对比内容">
        <button type="button" role="tab" aria-selected={tab === 'rules'}
          className={tab === 'rules' ? 'is-active' : ''} onClick={() => setTab('rules')}>规则差异</button>
        <button type="button" role="tab" aria-selected={tab === 'text'}
          className={tab === 'text' ? 'is-active' : ''} onClick={() => setTab('text')}>原文比对</button>
      </div>
      {tab === 'rules'
        ? diff.error ? <ErrorState error={diff.error} onRetry={() => void diff.refetch()} />
          : diff.loading && !diff.data ? <Spinner />
            : diff.data ? <RulesDiffView result={diff.data} /> : null
        : <TextDiffView target={effectiveTarget} against={effectiveAgainst} />}
    </> : <p className="muted">选择两个版本后自动加载对比结果。</p>}
  </Card>
}
