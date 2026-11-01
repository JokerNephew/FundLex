import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../../api/endpoints'
import { saveBlob } from '../../api/client'
import { useDocumentReport, useTaskDocument } from '../../api/hooks'
import { Button, Card, Spinner, StatusBadge } from '../../components/ui'
import type { TaskDocument } from '../../types'

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div className="fundlex-detail-error" role="alert"><strong>合同详情暂时无法加载</strong><p>{message}</p>{onRetry && <Button type="button" onClick={onRetry}>重试</Button>}</div>
}

function text(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  return ''
}

function field(value: unknown, fallback = '—'): string {
  const result = text(value).trim()
  return result || fallback
}

function objectList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object')) : []
}

function reportList(report: Record<string, unknown> | undefined, key: string): Record<string, unknown>[] {
  return objectList(report?.[key])
}

function Evidence({ value }: { value: unknown }) {
  if (typeof value === 'string') return value ? <blockquote className="fundlex-evidence">{value}</blockquote> : null
  if (!value || typeof value !== 'object') return null
  const item = value as Record<string, unknown>
  const quote = item.quote || item.text || item.evidence_quote || item.original_text
  const location = item.location || item.address || item.paragraph
  return <div className="fundlex-evidence"><p>{field(quote, '未提供引文')}</p>{Boolean(location) && <small>位置：{field(location)}</small>}</div>
}

function downloadLabel(kind: string, delivery?: string): string {
  if (delivery === 'incomplete' && kind === 'selected_final') return '选择版（未完成）'
  if (delivery === 'incomplete' && kind === 'selected_redline') return '选择版-带修改标记（未完成）'
  return ({
    report_md: '文本报告', report_json: '原始数据（JSON）', final: '最终版',
    redline: '带修改标记版', selected_final: '选择版', selected_redline: '选择版-带修改标记',
    working_final: '修改版（未完成）', working_redline: '修改版-带修改标记（未完成）',
    evaluation_final: '评测版（非正式）', evaluation_redline: '评测版-带修改标记',
  } as Record<string, string>)[kind] || kind
}

function downloadExtension(kind: string): string {
  return kind.startsWith('report_') ? (kind === 'report_json' ? 'json' : 'md') : 'docx'
}

function detailStatus(document: TaskDocument): string {
  if (document.delivery_status === 'complete') return '文件已完整交付'
  if (document.delivery_status === 'incomplete') return '没改完，需要人工核对'
  if (document.delivery_status === 'diagnosed') return '只生成了报告，没有改后的合同'
  if (document.delivery_status?.startsWith('evaluation_')) return '这是评测产物，不是正式合同'
  if (document.delivery_status === 'not_generated') return '未生成可交付文件'
  return field(document.delivery_status, '未确认')
}

function operationLabel(value: unknown): string {
  return ({ replace: '修改', delete: '删除', insert: '新增', append: '新增' } as Record<string, string>)[text(value)] || '修改'
}

function exceptionSource(item: Record<string, unknown>): string {
  if (item.obligation_id) return '规则义务核对'
  if (item.quote_exact_site === true) return '覆盖检查'
  if (item.review_note) return '人工复核提示'
  return '交付核验'
}

function exceptionLocation(item: Record<string, unknown>): string {
  return field(item.location || item.address || item.paragraph || item.block_id, '未定位')
}

function exceptionKey(item: Record<string, unknown>, index: number): string {
  const source = JSON.stringify(Object.keys(item).sort().map((key) => [key, item[key]]))
  let hash = 2166136261
  for (let offset = 0; offset < source.length; offset += 1) hash = Math.imul(hash ^ source.charCodeAt(offset), 16777619)
  return field(item.issue_id || item.exception_id, `EX-${(hash >>> 0).toString(16).slice(0, 8) || String(index + 1).padStart(2, '0')}`)
}

function Summary({ document, report }: { document: TaskDocument; report?: Record<string, unknown> }) {
  const targets = reportList(report, 'targets')
  const total = document.target_counts?.total ?? targets.length
  const completed = document.target_counts?.completed ?? targets.filter((target) => ['modified_verified', 'planned', 'satisfied', 'not_applicable', 'superseded'].includes(text(target.status || target.state)) || target.out_of_scope).length
  const unresolved = document.target_counts?.unresolved ?? targets.filter((target) => !target.out_of_scope && ['unresolved', 'unsupported', 'needs_edit'].includes(text(target.status || target.state))).length
  return <Card><h2>交付概览</h2><dl className="fundlex-detail-grid"><dt>资格</dt><dd><StatusBadge value={document.eligibility} /></dd><dt>处理状态</dt><dd><StatusBadge value={document.job_status} /></dd><dt>交付</dt><dd><StatusBadge value={document.delivery_status} /></dd><dt>说明</dt><dd>{detailStatus(document)}</dd><dt>已改完</dt><dd>{total ? `${completed} / ${total}` : '—'}</dd><dt>待人工核对</dt><dd>{unresolved || '0'}</dd></dl></Card>
}

function EditRows({ edit }: { edit: Record<string, unknown> }) {
  const components = objectList(edit.components)
  const rows = components.length ? components : [edit]
  return <>{rows.map((row, rowIndex) => <div className="fundlex-edit-row" key={rowIndex}><div><small>修改前</small><p>{field(row.expected_old_text || row.old_text || row.original_text, '（新增内容）')}</p></div><div><small>修改后</small><p>{field(row.new_text || row.replacement || row.after, edit.operation === 'delete' ? '（删除）' : '（未提供新文）')}</p></div></div>)}</>
}

function ClauseChangeSection({ report }: { report: Record<string, unknown> }) {
  const targets = reportList(report, 'targets')
  const edits = reportList((report.plan || {}) as Record<string, unknown>, 'edits')
  const usedEdits = new Set<number>()
  const blocks = targets.map((target, index) => {
    const ruleId = text(target.rule_id)
    const matched: Record<string, unknown>[] = []
    if (ruleId) {
      edits.forEach((edit, editIndex) => {
        if (!usedEdits.has(editIndex) && text(edit.rule_id) === ruleId) { usedEdits.add(editIndex); matched.push(edit) }
      })
    }
    return { target, index, matched }
  })
  const restEdits = edits.filter((_, editIndex) => !usedEdits.has(editIndex))
  const total = targets.length + restEdits.length
  return <Card><h2>改了哪些条款{total ? ` · ${total} 处` : ''}</h2>{total ? <div className="fundlex-target-list">
    {blocks.map(({ target, index, matched }) => { const status = text(target.status || target.state); return <details key={String(target.target_id || index)} className="fundlex-target"><summary><strong>{field(target.title || target.rule_id, `条款 ${index + 1}`)}</strong><StatusBadge value={status} /></summary><dl className="fundlex-detail-grid"><dt>位置</dt><dd>{field(target.location)}</dd><dt>合同原文</dt><dd><Evidence value={target.quote || target.original_text} /></dd></dl>{matched.length ? matched.map((edit, editIndex) => <EditRows key={String(edit.edit_id || editIndex)} edit={edit} />) : <p className="meta-line">这条没有前后对照，状态见标签。</p>}</details> })}
    {restEdits.map((edit, index) => <details key={String(edit.edit_id || `edit-${index}`)} className="fundlex-target"><summary><strong>修改 {index + 1} · {field(edit.location)}</strong><span className="ui-tag">{operationLabel(edit.operation)}</span></summary><EditRows edit={edit} /></details>)}
  </div> : <p className="fundlex-muted">报告没有返回逐条修改明细。</p>}</Card>
}

function ExceptionSection({ report }: { report: Record<string, unknown> }) {
  const issues = [...reportList(report, 'exceptions'), ...reportList(report, 'unresolved')]
  const summary = (report.user_summary || {}) as Record<string, unknown>
  const summaryIssues = objectList(summary.issues)
  const all = [...issues, ...summaryIssues]
  return <Card><h2>还要人工核 · {all.length} 处</h2>{all.length ? <div className="fundlex-exception-list">{all.map((item, index) => <details key={`${exceptionKey(item, index)}-${index}`} className="fundlex-exception"><summary><span><strong>第 {index + 1} 处</strong> · {field(item.title || item.rule_id || item.description, '需人工核对')}</span><small>{exceptionLocation(item)}</small></summary><dl className="fundlex-exception-meta"><dt>位置</dt><dd>{exceptionLocation(item)}</dd><dt>诊断来源</dt><dd>{exceptionSource(item)}</dd></dl><p>{field(item.business_reason || item.reason || item.review_note || item.description, '请结合原文与指引人工核对。')}</p><Evidence value={item.quote || item.evidence_quote} /></details>)}</div> : <p className="fundlex-muted">都改完了，没有待核对项。</p>}</Card>
}

function DownloadButtons({ taskId, document, kinds }: { taskId: string; document: TaskDocument; kinds: Array<[string, string]> }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')
  const download = async (kind: string, url: string) => {
    if (busy) return
    setBusy(kind)
    try { const blob = await api.downloadDocument(taskId, document.document_id || '', kind); saveBlob(blob, `${document.name.replace(/\.docx$/i, '')}_${downloadLabel(kind, document.delivery_status)}.${downloadExtension(kind)}`) }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : '下载失败，请稍后重试。') }
    finally { setBusy(null) }
    void url
  }
  return <>{error && <p className="fundlex-detail-warning" role="alert">{error}</p>}<div className="fundlex-download-list">{kinds.map(([kind, url]) => <Button key={kind} type="button" variant={kind === 'final' || kind === 'selected_final' ? 'primary' : 'secondary'} disabled={busy !== null} onClick={() => void download(kind, url)}>{busy === kind ? '下载中…' : `↓ ${downloadLabel(kind, document.delivery_status)}`}</Button>)}</div></>
}

function DownloadSection({ taskId, document }: { taskId: string; document: TaskDocument }) {
  const downloads = document.downloads || {}
  const kinds = Object.entries(downloads).filter(([kind, url]) => Boolean(url) && !kind.startsWith('report_') && !kind.startsWith('evaluation_'))
  return <Card><h2>交付文件</h2>{kinds.length ? <DownloadButtons taskId={taskId} document={document} kinds={kinds} /> : <div className="fundlex-download-empty"><p>当前没有可下载文件。</p><p className="fundlex-muted">处理完成并复核通过后开放下载。</p></div>}{(document.delivery_status === 'incomplete' || document.delivery_status === 'not_generated') && <p className="fundlex-detail-warning">当前交付状态为“{detailStatus(document)}”，带“未完成”标记的文件不能直接当最终合同用。</p>}</Card>
}

function AdvancedSection({ taskId, document }: { taskId: string; document: TaskDocument }) {
  const downloads = document.downloads || {}
  const kinds = Object.entries(downloads).filter(([kind, url]) => Boolean(url) && (kind.startsWith('report_') || kind.startsWith('evaluation_')))
  return <>{kinds.length ? <DownloadButtons taskId={taskId} document={document} kinds={kinds} /> : null}</>
}

export function DocumentDetailPage() {
  const { taskId, documentId } = useParams()
  const documentQuery = useTaskDocument(taskId, documentId)
  const document = documentQuery.data
  const report = useDocumentReport(taskId, documentId)
  if (documentQuery.error) return <ErrorState message="合同详情读取失败，请检查登录状态后重试。" onRetry={() => void documentQuery.refetch()} />
  if (documentQuery.loading && !documentQuery.data) return <Card><Spinner label="正在读取合同详情" /></Card>
  if (!document) return <Card><div className="fundlex-empty">合同不存在，或当前账号没有访问权限。</div></Card>
  if (report.error) return <><header className="page-heading"><div><h1>{document.name}</h1><p>报告读取失败，但可以返回任务查看其它合同。</p></div><Link to={`/tasks/${taskId}`}><Button>返回任务</Button></Link></header><ErrorState message="合同报告暂时不可用。" onRetry={() => void report.refetch()} /><DownloadSection taskId={taskId || ''} document={document} /></>
  if (report.loading && !report.data) return <Card><Spinner label="正在读取报告" /></Card>
  const reportData = (report.data && typeof report.data === 'object' ? report.data : undefined) as Record<string, unknown> | undefined
  return <div className="fundlex-document-detail">
    <header className="page-heading"><div><p><Link to={`/tasks/${taskId}`}>← 返回任务</Link></p><h1>{document.name}</h1><p>修改与交付结果</p></div><div className="action-row"><Link to={`/tasks/${taskId}/documents/${document.document_id}/review`}><Button variant="primary" disabled={!document.downloads?.working_redline && !document.downloads?.redline}>逐条确认修改</Button></Link><StatusBadge value={document.delivery_status} /></div></header>
    <Summary document={document} report={reportData} />
    <DownloadSection taskId={taskId || ''} document={document} />
    {reportData ? <>
      <ClauseChangeSection report={reportData} />
      {reportData?.verification_status === 'verification_blocked' && <Card><div role="status"><h2>验证暂未完成，等待恢复处理</h2><p>处理所需的验证记录或模型额度暂不可用。恢复任务后将继续验证；当前文件尚未通过最终交付校验。</p></div></Card>}
      <ExceptionSection report={reportData} />
      <EvidenceSection report={reportData} />
    </> : <Card><h2>修改情况</h2><p className="fundlex-muted">报告尚未生成。请等待任务完成后刷新。</p></Card>}
    <AdvancedSection taskId={taskId || ''} document={document} />
  </div>
}

function EvidenceSection({ report }: { report: Record<string, unknown> }) {
  const qualification = (report.qualification || report.eligibility || {}) as Record<string, unknown>
  const evidence = objectList(qualification.evidence || report.qualification_evidence)
  return <Card><h2>为什么判定可处理</h2><p>{field(qualification.basis || qualification.reason || report.qualification_reason, '报告未提供判定说明。')}</p>{Boolean(qualification.fund_type_quote) && <Evidence value={qualification.fund_type_quote} />}{evidence.length ? <div className="fundlex-evidence-list">{evidence.map((item, index) => <Evidence key={index} value={item} />)}</div> : <p className="meta-line">没有更多原文依据。</p>}</Card>
}
