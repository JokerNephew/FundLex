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

function exceptionLocation(item: Record<string, unknown>): string {
  return field(item.location || item.address || item.paragraph || item.block_id, '未定位')
}

function exceptionKey(item: Record<string, unknown>, index: number): string {
  const source = JSON.stringify(Object.keys(item).sort().map((key) => [key, item[key]]))
  let hash = 2166136261
  for (let offset = 0; offset < source.length; offset += 1) hash = Math.imul(hash ^ source.charCodeAt(offset), 16777619)
  return field(item.issue_id || item.exception_id, `EX-${(hash >>> 0).toString(16).slice(0, 8) || String(index + 1).padStart(2, '0')}`)
}

function EditRows({ edit }: { edit: Record<string, unknown> }) {
  const components = objectList(edit.components)
  const rows = components.length ? components : [edit]
  return <>{rows.map((row, rowIndex) => <div className="fundlex-edit-row" key={rowIndex}><div><small>修改前</small><p>{field(row.expected_old_text || row.old_text || row.original_text, '（新增内容）')}</p></div><div><small>修改后</small><p>{field(row.new_text || row.replacement || row.after, edit.operation === 'delete' ? '（删除）' : '（未提供新文）')}</p></div></div>)}</>
}

function counts(document: TaskDocument, report?: Record<string, unknown>) {
  const targets = reportList(report, 'targets')
  const total = document.target_counts?.total ?? targets.length
  const completed = document.target_counts?.completed ?? targets.filter((target) => ['modified_verified', 'planned', 'satisfied', 'not_applicable', 'superseded'].includes(text(target.status || target.state)) || target.out_of_scope).length
  const unresolved = document.target_counts?.unresolved ?? targets.filter((target) => !target.out_of_scope && ['unresolved', 'unsupported', 'needs_edit'].includes(text(target.status || target.state))).length
  return { total, completed, unresolved }
}

/** L0 结论带：一句结构话结论 + 单徽章 + 主行动（下载最终合同 / 逐条审阅）。 */
function ConclusionBand({ taskId, document, report }: { taskId: string; document: TaskDocument; report?: Record<string, unknown> }) {
  const { total, completed, unresolved } = counts(document, report)
  const blocked = report?.verification_status === 'verification_blocked'
  const canReview = Boolean(document.downloads?.working_redline || document.downloads?.redline)
  const finalKind = ['final', 'selected_final', 'working_final'].find((kind) => Boolean(document.downloads?.[kind]))
  const headline = total
    ? `改完 ${completed}/${total} 处 · 待人工核 ${unresolved} 处`
    : detailStatus(document)
  return <header className="page-heading"><div>
    <p><Link to={`/tasks/${taskId}`}>← 返回任务</Link></p>
    <h1>{document.name}</h1>
    <p>{headline}</p>
    {blocked && <p className="fundlex-detail-warning" role="status">验证暂未完成，恢复任务后将继续校验；当前文件尚未通过最终交付核验。</p>}
    {(document.delivery_status === 'incomplete' || document.delivery_status === 'not_generated') && <p className="fundlex-detail-warning">带“未完成”标记的文件不能直接当最终合同用。</p>}
  </div>
    <div className="action-row">
      {finalKind && <DownloadOne taskId={taskId} document={document} kind={finalKind} variant="primary" />}
      <Link to={`/tasks/${taskId}/documents/${document.document_id}/review`}><Button disabled={!canReview}>逐条审阅修改</Button></Link>
      <StatusBadge value={document.delivery_status} />
    </div>
  </header>
}

function DownloadOne({ taskId, document, kind, variant }: { taskId: string; document: TaskDocument; kind: string; variant?: 'primary' }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = async () => {
    if (busy) return
    setBusy(true)
    try { const blob = await api.downloadDocument(taskId, document.document_id || '', kind); saveBlob(blob, `${document.name.replace(/\.docx$/i, '')}_${downloadLabel(kind, document.delivery_status)}.${downloadExtension(kind)}`) }
    catch (nextError) { setError(nextError instanceof Error ? nextError.message : '下载失败，请稍后重试。') }
    finally { setBusy(false) }
  }
  return <span>{error && <p className="fundlex-detail-warning" role="alert">{error}</p>}<Button type="button" variant={variant} disabled={busy} onClick={() => void run()}>{busy ? '下载中…' : `↓ 下载${downloadLabel(kind, document.delivery_status)}`}</Button></span>
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

/** L1 左：条款名 + 一句改了什么 + 状态徽标；前后对照行内展开，不整页折叠。 */
function ChangeList({ report }: { report: Record<string, unknown> }) {
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
  const total = blocks.length + restEdits.length
  if (!total) return <Card><h2>改了哪些条款</h2><p className="fundlex-muted">报告没有返回逐条修改明细。</p></Card>
  return <Card><h2>改了哪些条款 · {total} 处</h2><div className="fundlex-target-list">
    {blocks.map(({ target, index, matched }) => {
      const status = text(target.status || target.state)
      const preview = matched.length ? text(matched[0].new_text || matched[0].replacement || matched[0].after) : ''
      return <details key={String(target.target_id || index)} className="fundlex-target"><summary><span className="fundlex-target-heading"><strong>{field(target.title || target.rule_id, `条款 ${index + 1}`)}</strong>{preview && <small className="fundlex-target-preview">改为：{preview.slice(0, 40)}{preview.length > 40 ? '…' : ''}</small>}<small className="fundlex-target-location">{field(target.location)}</small></span><StatusBadge value={status} /></summary><dl className="fundlex-detail-grid"><dt>合同原文</dt><dd><Evidence value={target.quote || target.original_text} /></dd></dl>{matched.length ? matched.map((edit, editIndex) => <EditRows key={String(edit.edit_id || editIndex)} edit={edit} />) : <p className="meta-line">这条没有前后对照，状态见标签。</p>}</details>
    })}
    {restEdits.map((edit, index) => {
      const preview = text(edit.new_text || edit.replacement || edit.after)
      return <details key={String(edit.edit_id || `edit-${index}`)} className="fundlex-target"><summary><span className="fundlex-target-heading"><strong>修改 {index + 1} · {field(edit.location)}</strong>{preview && <small className="fundlex-target-preview">改为：{preview.slice(0, 40)}{preview.length > 40 ? '…' : ''}</small>}</span><span className="ui-tag">{operationLabel(edit.operation)}</span></summary><EditRows edit={edit} /></details>
    })}
  </div></Card>
}

/** L1 右：人工核常态条目——标题+位置+原因+引文，移除「诊断来源」等内部行。 */
function ExceptionList({ report }: { report: Record<string, unknown> }) {
  const issues = [...reportList(report, 'exceptions'), ...reportList(report, 'unresolved')]
  const summary = (report.user_summary || {}) as Record<string, unknown>
  const all = [...issues, ...objectList(summary.issues)]
  if (!all.length) return <Card><h2>还要人工核</h2><p className="fundlex-muted">都改完了，没有待核对项。</p></Card>
  return <Card><h2>还要人工核 · {all.length} 处</h2><div className="fundlex-exception-list">{all.map((item, index) => <div key={`${exceptionKey(item, index)}-${index}`} className="fundlex-exception"><p className="fundlex-exception-title"><strong>第 {index + 1} 处</strong> · {field(item.title || item.rule_id || item.description, '需人工核对')} <small>{exceptionLocation(item)}</small></p><p>{field(item.business_reason || item.reason || item.review_note || item.description, '请结合原文与指引人工核对。')}</p><Evidence value={item.quote || item.evidence_quote} /></div>)}</div></Card>
}

/** L2 产物区：按目的三分组（最终用的合同 / 对照与审阅 / 报告与数据）。 */
function ArtifactGroups({ taskId, document }: { taskId: string; document: TaskDocument }) {
  const downloads = document.downloads || {}
  const pick = (names: string[]) => Object.entries(downloads).filter(([kind, url]) => Boolean(url) && names.includes(kind)) as Array<[string, string]>
  const contract = pick(['final', 'selected_final', 'working_final'])
  const compare = pick(['redline', 'selected_redline', 'working_redline'])
  const reports = pick(['report_md', 'report_json', 'evaluation_final', 'evaluation_redline'])
  const empty = !contract.length && !compare.length && !reports.length
  if (empty) return <Card><h2>下载区</h2><div className="fundlex-download-empty"><p>当前没有可下载文件。</p><p className="fundlex-muted">处理完成并复核通过后开放下载。</p></div></Card>
  return <Card><h2>下载区</h2>
    {contract.length ? <div className="fundlex-artifact-group"><h3>最终用的合同</h3><DownloadButtons taskId={taskId} document={document} kinds={contract} /></div> : null}
    {compare.length ? <div className="fundlex-artifact-group"><h3>对照与审阅</h3><DownloadButtons taskId={taskId} document={document} kinds={compare} /></div> : null}
    {reports.length ? <div className="fundlex-artifact-group"><h3>报告与数据</h3><DownloadButtons taskId={taskId} document={document} kinds={reports} /></div> : null}
  </Card>
}

/** L3 依据区：仅资格异常或纯报告合同显示（正常交付无需解释）。 */
function QualificationBasis({ document, report }: { document: TaskDocument; report: Record<string, unknown> }) {
  const show = document.eligibility === 'ineligible' || document.delivery_status === 'diagnosed'
  if (!show) return null
  const qualification = (report.qualification || report.eligibility || {}) as Record<string, unknown>
  const evidence = objectList(qualification.evidence || report.qualification_evidence)
  const reason = field(qualification.basis || qualification.reason || report.qualification_reason, '报告未提供判定说明。')
  return <Card><h2>{document.eligibility === 'ineligible' ? '为什么不能处理' : '判定依据'}</h2><p>{reason}</p>{Boolean(qualification.fund_type_quote) && <Evidence value={qualification.fund_type_quote} />}{evidence.length ? <div className="fundlex-evidence-list">{evidence.map((item, index) => <Evidence key={index} value={item} />)}</div> : <p className="meta-line">没有更多原文依据。</p>}</Card>
}

export function DocumentDetailPage() {
  const { taskId, documentId } = useParams()
  const documentQuery = useTaskDocument(taskId, documentId)
  const document = documentQuery.data
  const report = useDocumentReport(taskId, documentId)
  if (documentQuery.error) return <ErrorState message="合同详情读取失败，请检查登录状态后重试。" onRetry={() => void documentQuery.refetch()} />
  if (documentQuery.loading && !documentQuery.data) return <Card><Spinner label="正在读取合同详情" /></Card>
  if (!document) return <Card><div className="fundlex-empty">合同不存在，或当前账号没有访问权限。</div></Card>
  if (report.error) return <><header className="page-heading"><div><h1>{document.name}</h1><p>报告读取失败，但可以返回任务查看其它合同。</p></div><Link to={`/tasks/${taskId}`}><Button>返回任务</Button></Link></header><ErrorState message="合同报告暂时不可用。" onRetry={() => void report.refetch()} /><ArtifactGroups taskId={taskId || ''} document={document} /></>
  if (report.loading && !report.data) return <Card><Spinner label="正在读取报告" /></Card>
  const reportData = (report.data && typeof report.data === 'object' ? report.data : undefined) as Record<string, unknown> | undefined
  return <div className="fundlex-document-detail">
    <ConclusionBand taskId={taskId || ''} document={document} report={reportData} />
    {reportData ? <>
      <div className="fundlex-detail-columns">
        <ChangeList report={reportData} />
        <ExceptionList report={reportData} />
      </div>
      <ArtifactGroups taskId={taskId || ''} document={document} />
      <QualificationBasis document={document} report={reportData} />
    </> : <>
      <Card><h2>修改情况</h2><p className="fundlex-muted">报告尚未生成。请等待任务完成后刷新。</p></Card>
      <ArtifactGroups taskId={taskId || ''} document={document} />
    </>}
  </div>
}
