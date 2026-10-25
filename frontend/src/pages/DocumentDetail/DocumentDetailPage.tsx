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

function downloadLabel(kind: string): string {
  return ({
    report_md: 'Markdown 报告', report_json: 'JSON 报告', final: '最终版合同',
    redline: '修订版合同（全量痕迹）', selected_final: '选择版合同', selected_redline: '选择版修订痕迹',
    working_final: '工作文件（未完成）', working_redline: '工作文件修订痕迹（未完成）',
    evaluation_final: '评测修改版合同', evaluation_redline: '评测修订痕迹',
  } as Record<string, string>)[kind] || kind
}

function downloadExtension(kind: string): string {
  return kind.startsWith('report_') ? (kind === 'report_json' ? 'json' : 'md') : 'docx'
}

function detailStatus(document: TaskDocument): string {
  if (document.delivery_status === 'complete') return '交付完成'
  if (document.delivery_status === 'incomplete') return '结果不完整，需人工核对'
  if (document.delivery_status === 'not_generated') return '未生成可交付文件'
  return field(document.delivery_status, '未确认')
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
  const completed = document.target_counts?.completed ?? targets.filter((target) => ['modified_verified', 'satisfied', 'not_applicable'].includes(text(target.state))).length
  const unresolved = document.target_counts?.unresolved ?? targets.filter((target) => ['unresolved', 'unsupported', 'needs_edit'].includes(text(target.state))).length
  return <Card><h2>交付概览</h2><dl className="fundlex-detail-grid"><dt>资格</dt><dd><StatusBadge value={document.eligibility} /></dd><dt>处理状态</dt><dd><StatusBadge value={document.job_status} /></dd><dt>交付</dt><dd><StatusBadge value={document.delivery_status} /></dd><dt>交付说明</dt><dd>{detailStatus(document)}</dd><dt>目标完成</dt><dd>{total ? `${completed} / ${total}` : '—'}</dd><dt>仍需核对</dt><dd>{unresolved || '0'}</dd><dt>原件 SHA-256</dt><dd><code>{field(document.source_sha256)}</code></dd><dt>指引版本</dt><dd>{field(document.guide_snapshot?.version_id)}</dd></dl></Card>
}

function EvidenceSection({ report }: { report: Record<string, unknown> }) {
  const qualification = (report.qualification || report.eligibility || {}) as Record<string, unknown>
  const evidence = objectList(qualification.evidence || report.qualification_evidence)
  return <Card><h2>资格与业务依据</h2><p>{field(qualification.basis || qualification.reason || report.qualification_reason, '报告未提供资格说明。')}</p>{Boolean(qualification.fund_type_quote) && <Evidence value={qualification.fund_type_quote} />}{evidence.length ? <div className="fundlex-evidence-list">{evidence.map((item, index) => <Evidence key={index} value={item} />)}</div> : <p className="fundlex-muted">暂无独立证据引文。</p>}</Card>
}

function TargetSection({ report }: { report: Record<string, unknown> }) {
  const targets = reportList(report, 'targets')
  return <Card><h2>修改目标 · {targets.length} 项</h2>{targets.length ? <div className="fundlex-target-list">{targets.map((target, index) => <details key={String(target.target_id || index)} className="fundlex-target"><summary><strong>{field(target.title || target.rule_id, `目标 ${index + 1}`)}</strong><StatusBadge value={text(target.state)} /></summary><dl className="fundlex-detail-grid"><dt>规则</dt><dd>{field(target.rule_id)}</dd><dt>位置</dt><dd>{field(target.location)}</dd><dt>目标原文</dt><dd><Evidence value={target.quote || target.original_text} /></dd><dt>依据</dt><dd>{field(target.reason || target.requirement)}</dd></dl></details>)}</div> : <p className="fundlex-muted">报告没有返回目标清单。</p>}</Card>
}

function CompareSection({ report }: { report: Record<string, unknown> }) {
  const edits = reportList((report.plan || {}) as Record<string, unknown>, 'edits')
  return <Card><h2>原文与新文 · {edits.length} 处</h2>{edits.length ? <div className="fundlex-edit-list">{edits.map((edit, index) => { const components = objectList(edit.components); const rows = components.length ? components : [edit]; return <details key={String(edit.edit_id || index)} className="fundlex-edit"><summary>{field(edit.rule_id || edit.operation, `修改 ${index + 1}`)} · {field(edit.location)}</summary>{rows.map((row, rowIndex) => <div className="fundlex-edit-row" key={rowIndex}><div><small>原文</small><p>{field(row.expected_old_text || row.old_text || row.original_text, '（新增内容）')}</p></div><div><small>新文</small><p>{field(row.new_text || row.replacement || row.after, edit.operation === 'delete' ? '（删除）' : '（未提供新文）')}</p></div></div>)}</details> })}</div> : <p className="fundlex-muted">暂无实际修改对照。已满足或不适用目标仍会显示在目标清单中。</p>}</Card>
}

function ExceptionSection({ report }: { report: Record<string, unknown> }) {
  const issues = reportList(report, 'exceptions')
  const summary = (report.user_summary || {}) as Record<string, unknown>
  const summaryIssues = objectList(summary.issues)
  const all = [...issues, ...summaryIssues]
  return <Card><h2>例外与人工核对 · {all.length} 项</h2><p className="fundlex-muted">此处展示报告的交付核验事项；“仍需核对”还包含目标盘点中的未决目标，两者统计口径不同。</p>{all.length ? <div className="fundlex-exception-list">{all.map((item, index) => <details key={`${exceptionKey(item, index)}-${index}`} className="fundlex-exception"><summary><span><strong>{exceptionKey(item, index)}</strong> · {field(item.title || item.rule_id || item.description, `例外 ${index + 1}`)}</span><small>{exceptionLocation(item)}</small></summary><dl className="fundlex-exception-meta"><dt>规则</dt><dd>{field(item.rule_id)}</dd><dt>位置</dt><dd>{exceptionLocation(item)}</dd><dt>诊断来源</dt><dd>{exceptionSource(item)}</dd></dl><p>{field(item.business_reason || item.reason || item.review_note || item.description, '请结合原文与指引人工核对。')}</p><Evidence value={item.quote || item.evidence_quote} /></details>)}</div> : <p className="fundlex-muted">报告没有登记例外事项。</p>}</Card>
}

function DownloadSection({ taskId, document }: { taskId: string; document: TaskDocument }) {
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState('')
  const downloads = document.downloads || {}
  const kinds = Object.entries(downloads).filter(([kind, url]) => Boolean(url && !kind.startsWith('evaluation_') || url && kind.startsWith('evaluation_')))
  const download = async (kind: string, url: string) => {
    if (busy) return
    setBusy(kind)
    try { const blob = await api.downloadDocument(taskId, document.document_id || '', kind); saveBlob(blob, `${document.name.replace(/\.docx$/i, '')}_${downloadLabel(kind)}.${downloadExtension(kind)}`) }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : '下载失败，请稍后重试。') }
    finally { setBusy(null) }
    void url
  }
  return <Card><h2>报告与合同下载</h2>{error && <p className="fundlex-detail-warning" role="alert">{error}</p>}{kinds.length ? <div className="fundlex-download-list">{kinds.map(([kind, url]) => <Button key={kind} type="button" variant={kind === 'final' || kind === 'selected_final' ? 'primary' : 'secondary'} disabled={busy !== null} onClick={() => void download(kind, url)}>{busy === kind ? '下载中…' : `↓ ${downloadLabel(kind)}`}</Button>)}</div> : <div className="fundlex-download-empty"><p>当前没有可下载文件。</p><p className="fundlex-muted">文件会在 Worker 完成并通过实际复核后开放；不完整结果请先查看例外。</p></div>}{(document.delivery_status === 'incomplete' || document.delivery_status === 'not_generated') && <p className="fundlex-detail-warning">当前交付状态为“{detailStatus(document)}”，工作文件不能直接视为最终合同。</p>}</Card>
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
    <header className="page-heading"><div><p><Link to={`/tasks/${taskId}`}>← 返回任务</Link></p><h1>{document.name}</h1><p>合同详情、业务依据、实际修改和授权下载</p></div><div className="action-row"><Link to={`/tasks/${taskId}/documents/${document.document_id}/review`}><Button variant="primary" disabled={!document.downloads?.working_redline && !document.downloads?.redline}>打开修订复核</Button></Link><StatusBadge value={document.delivery_status} /></div></header>
    <Summary document={document} report={reportData} />
    {reportData ? <><EvidenceSection report={reportData} /><TargetSection report={reportData} /><CompareSection report={reportData} /><ExceptionSection report={reportData} /></> : <Card><h2>报告</h2><p className="fundlex-muted">报告尚未生成。请等待任务完成后刷新。</p></Card>}
     <DownloadSection taskId={taskId || ''} document={document} />
  </div>
}
