import { useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { api } from '../../api/endpoints'
import { saveBlob } from '../../api/client'
import { useTask, useTaskControlMutation, useTaskDocuments } from '../../api/hooks'
import { Button, Card, Select, Spinner, StatusBadge } from '../../components/ui'
import type { TaskDocument } from '../../types'
import { ErrorState, formatDate, LoadingCard, Pagination } from '../Tasks'

const phases = ['结构读取', '事实理解', '范围映射', '目标盘点', '规划', '写入', '复核', '交付']

function phaseLabel(phase?: string) {
  if (!phase) return '等待 Worker 更新'
  const known = phases.find((item) => phase.includes(item))
  return known || phase
}

function phaseIndex(phase?: string) {
  if (!phase) return -1
  const index = phases.findIndex((item) => phase.includes(item))
  return index
}

function DownloadButton({ action, label, disabled }: { action: () => Promise<void>; label: string; disabled?: boolean }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  const run = async () => { setBusy(true); setError(''); try { await action() } catch (nextError) { setError(nextError instanceof Error ? nextError.message : '下载失败') } finally { setBusy(false) } }
  return <span><Button type="button" variant="quiet" disabled={disabled || busy} onClick={() => void run()}>{busy ? '准备中…' : label}</Button>{error && <span className="form-error">{error}</span>}</span>
}

function artifactExtension(kind: string) { return kind === 'report_json' ? 'json' : kind === 'report_md' ? 'md' : 'docx' }

function taskDeliveryStatus(task: { delivery_counts?: Record<string, number> }) {
  const counts = task.delivery_counts || {}
  if ((counts.incomplete || 0) > 0) return 'incomplete'
  if ((counts.complete_with_exceptions || 0) > 0) return 'complete_with_exceptions'
  if ((counts.complete || 0) > 0) return 'complete'
  return 'not_generated'
}

function primaryArtifact(document: TaskDocument): { kind: string; label: string } | null {
  const downloads = document.downloads || {}
  const incomplete = document.delivery_status === 'incomplete'
  if (downloads.selected_final) {
    return { kind: 'selected_final', label: incomplete ? '工作文件（选择版）' : '选择版' }
  }
  if (downloads.final) {
    return { kind: 'final', label: document.delivery_status === 'complete_with_exceptions' ? '最终版（含例外）' : '最终版' }
  }
  if (downloads.working_final) return { kind: 'working_final', label: '工作文件（未完成）' }
  return null
}

function DocumentRow({ taskId, document }: { taskId: string; document: TaskDocument }) {
  const documentId = document.document_id
  if (!documentId) return <tr><td>{document.name}</td><td><StatusBadge value={document.upload_status || document.job_status} /></td><td>—</td><td>{document.error_code || '等待接收'}</td></tr>
  const download = (kind: string) => async () => { const blob = await api.downloadDocument(taskId, documentId, kind); saveBlob(blob, `${document.name.replace(/\.docx$/i, '')}_${kind}.${artifactExtension(kind)}`) }
  const primary = primaryArtifact(document)
  return <tr><td><Link to={`/tasks/${taskId}/documents/${documentId}/detail`}>{document.name}</Link><div className="muted">阶段：{phaseLabel(document.phase)}</div></td><td><StatusBadge value={document.job_status} />{document.error_code && <div className="form-error">{document.error_code}</div>}</td><td><StatusBadge value={document.eligibility || 'pending'} /><div className="muted">{document.reason_codes?.join('；') || '—'}</div></td><td><StatusBadge value={document.delivery_status} /><div className="muted">目标 {document.target_counts?.completed ?? 0}/{document.target_counts?.total ?? '—'}，未完成 {document.target_counts?.unresolved ?? 0}</div>{document.delivery_status === 'incomplete' && <div className="form-error">部分条款未完成，按例外清单人工核对</div>}</td><td className="action-row"><Link to={`/tasks/${taskId}/documents/${documentId}/review`}>修订</Link>{primary && <DownloadButton action={download(primary.kind)} label={primary.label} />}{<DownloadButton action={download('report_json')} label="报告" disabled={!document.downloads?.report_json} />}</td></tr>
}

function StatusDimension({ title, value, detail }: { title: string; value?: string; detail: string }) {
  return <div><span className="muted">{title}</span><p><StatusBadge value={value} /></p><small>{detail}</small></div>
}

export function TaskDetailPage() {
  const { taskId } = useParams(); const navigate = useNavigate(); const task = useTask(taskId, { pollMs: 5_000 }); const [query, setQuery] = useState(''); const [search, setSearch] = useState(''); const [tab, setTab] = useState(''); const [page, setPage] = useState(1); const [sort, setSort] = useState('oldest'); const [jobStatus, setJobStatus] = useState(''); const [deliveryStatus, setDeliveryStatus] = useState(''); const [uploadStatus, setUploadStatus] = useState(''); const [errorCode, setErrorCode] = useState(''); const [advancedOpen, setAdvancedOpen] = useState(false); const [controlError, setControlError] = useState(''); const [controlBusy, setControlBusy] = useState(false); const [downloadBusy, setDownloadBusy] = useState(false)
  const docs = useTaskDocuments(taskId, { q: search, job_status: tab === 'processing' ? 'running' : jobStatus || undefined, delivery_status: tab === 'delivered' ? 'complete' : tab === 'incomplete' ? 'incomplete' : tab === 'not_generated' ? 'not_generated' : deliveryStatus || undefined, eligibility: tab === 'eligible' ? 'eligible' : undefined, upload_status: uploadStatus || undefined, error_code: errorCode || undefined, page, page_size: 20, sort }, { pollMs: 5_000 })
  const controlMutation = useTaskControlMutation()
  if (task.error) return <ErrorState error={task.error} onRetry={() => void task.refetch()} />
  if (task.loading && !task.data) return <LoadingCard />
  if (!task.data || !taskId) return <div className="empty-state">任务不存在。</div>
   const current = task.data; const isPaused = current.status === 'paused'; const terminal = ['completed', 'completed_with_exceptions', 'failed'].includes(current.status); const currentPhase = current.phase; const control = async () => { setControlBusy(true); setControlError(''); try { await controlMutation.mutateAsync({ id: taskId, action: isPaused ? 'resume' : 'pause' }); await task.refetch() } catch (error) { setControlError(error instanceof Error ? error.message : '操作未完成') } finally { setControlBusy(false) } }
  const downloadAll = async () => { const blob = await api.downloadTask(taskId); saveBlob(blob, `${current.name}_结果.zip`) }
  const downloadSummary = async () => { const text = await api.taskReport(taskId); saveBlob(new Blob([text], { type: 'text/markdown;charset=utf-8' }), `${current.name}_汇总.md`) }
   const exportResults = async () => { setDownloadBusy(true); try { const rows: Array<Array<string | number>> = [['序号', '文件名', '资格', '处理状态', '交付完整性', '业务提示', '原始原因码']]; let all: TaskDocument[] = []; let nextPage = 1; let total = Infinity; const documentParams = { q: search || undefined, job_status: tab === 'processing' ? 'running' : jobStatus || undefined, delivery_status: tab === 'delivered' ? 'complete' : tab === 'incomplete' ? 'incomplete' : tab === 'not_generated' ? 'not_generated' : deliveryStatus || undefined, eligibility: tab === 'eligible' ? 'eligible' : undefined, upload_status: uploadStatus || undefined, error_code: errorCode || undefined, sort }; while (all.length < total && nextPage <= 100) { const result = await api.documents(taskId, { ...documentParams, page: nextPage, page_size: 200 }); all = [...all, ...result.items]; total = result.total; if (!result.items.length) break; nextPage += 1 } all.forEach((document, index) => rows.push([index + 1, document.name, document.eligibility || '未判定', document.job_status || '—', document.delivery_status || '—', document.error_code || document.reason_codes?.join('；') || '—', document.error_code || ''])); const escape = (value: string | number) => { const text = String(value); return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text }; const csv = `\ufeff${rows.map((row) => row.map(escape).join(',')).join('\r\n')}`; saveBlob(new Blob([csv], { type: 'text/csv;charset=utf-8' }), `${current.name}_结果清单.csv`) } finally { setDownloadBusy(false) } }
  const submitSearch = (event: React.FormEvent) => { event.preventDefault(); setPage(1); setSearch(query.trim()) }
  const done = current.completed ?? 0; const total = current.total ?? 0
  return <>
    <div className="page-heading"><div><p><Link to="/tasks">任务</Link> / 详情</p><h1>{current.name}</h1><p>创建于 {formatDate(current.created_at)} · 指引快照 {current.guide_snapshot?.version_id || '—'}</p></div><div className="action-row"><StatusBadge value={current.status} /><Button onClick={() => void control()} disabled={controlBusy || terminal}>{controlBusy ? '处理中…' : isPaused ? '恢复处理' : '暂停处理'}</Button><Button onClick={() => void task.refetch()} disabled={task.refreshing}>刷新</Button></div></div>
    {controlError && <ErrorState error={controlError} />}
       <Card><h2>任务状态</h2><div className="stats-grid"><StatusDimension title="任务" value={current.status} detail={current.pause_reason || '任务调度状态'} /><StatusDimension title="处理阶段" value={terminal ? 'completed' : 'running'} detail={phaseLabel(currentPhase)} /><StatusDimension title="交付" value={taskDeliveryStatus(current)} detail={`已完成 ${done}/${total}，异常 ${current.exceptions ?? 0}`} /><StatusDimension title="上传" value={current.upload_status} detail={`已接收 ${current.uploaded ?? 0}/${total}`} /></div><div className="task-phase-rail" aria-label="任务处理阶段"><ol>{phases.map((phase, index) => { const active = terminal || index <= phaseIndex(currentPhase); return <li key={phase} className={active ? 'is-active' : ''}><span>{index + 1}</span><small>{phase}</small></li> })}</ol></div><div className="task-status-legend"><span><i className="is-active" />已完成阶段</span><span><i />待处理阶段</span><span>当前 Worker：{phaseLabel(currentPhase)}</span></div><p className="muted">阶段来自合同处理结果中的服务端 phase 字段；任务总进度以合同计数和交付状态为准。</p></Card>
      <Card><div className="page-heading"><div><h2>结果与交付</h2><p>汇总和 ZIP 是清单与产物入口，合同本身请从下方列表进入。</p></div><div className="action-row"><DownloadButton action={downloadSummary} label="下载汇总" /><DownloadButton action={exportResults} label={downloadBusy ? '导出中…' : '导出结果 CSV'} disabled={downloadBusy} /><DownloadButton action={downloadAll} label="下载全部 ZIP" disabled={!current.downloadable_count} /><Button type="button" onClick={() => navigate(`/tasks/new?taskId=${encodeURIComponent(taskId || '')}`)} disabled={!current.pending_upload}>补传未接收文件</Button></div></div><div className="action-row">{[['', '全部'], ['processing', '处理中'], ['eligible', '资格通过'], ['delivered', '交付完成'], ['incomplete', '结果不完整'], ['not_generated', '未生成']].map(([value, label]) => <Button key={value} variant={tab === value ? 'primary' : 'secondary'} onClick={() => { setTab(value); setPage(1) }}>{label}</Button>)}</div></Card>
    <Card><div className="page-heading"><div><h2>合同列表</h2><p>资格、处理和交付状态分开查看；点击合同名称进入报告。</p></div></div><form className="action-row" onSubmit={submitSearch}><label className="muted">搜索合同<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="合同名称" /></label><label className="muted">排序<Select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1) }}><option value="oldest">最早加入</option><option value="newest">最新加入</option><option value="exceptions">异常优先</option><option value="status">状态</option></Select></label><Button type="submit" variant="primary">筛选</Button><Button type="button" onClick={() => setAdvancedOpen((open) => !open)}>{advancedOpen ? '收起高级筛选' : '高级筛选'}</Button></form>{advancedOpen && <form className="action-row" onSubmit={(event) => { event.preventDefault(); setPage(1) }}><label className="muted">处理<Select value={jobStatus} onChange={(event) => setJobStatus(event.target.value)}><option value="">全部处理</option><option value="not_started">未开始</option><option value="queued">排队中</option><option value="running">处理中</option><option value="failed">失败</option><option value="succeeded">已完成</option></Select></label><label className="muted">交付<Select value={deliveryStatus} onChange={(event) => setDeliveryStatus(event.target.value)}><option value="">全部交付</option><option value="complete">交付完成</option><option value="incomplete">结果不完整</option><option value="not_generated">未生成</option></Select></label><label className="muted">上传<Select value={uploadStatus} onChange={(event) => setUploadStatus(event.target.value)}><option value="">全部上传</option><option value="pending">待上传</option><option value="accepted">已接收</option><option value="rejected">接收失败</option></Select></label><label className="muted">异常代码<input value={errorCode} onChange={(event) => setErrorCode(event.target.value)} placeholder="例如 UPLOAD_SIZE_LIMIT" /></label><Button type="submit">应用高级筛选</Button><Button type="button" variant="quiet" onClick={() => { setJobStatus(''); setDeliveryStatus(''); setUploadStatus(''); setErrorCode(''); setPage(1) }}>清除</Button></form>}{docs.error ? <ErrorState error={docs.error} /> : docs.loading && !docs.data ? <Spinner /> : !docs.data?.items.length ? <div className="empty-state">没有符合条件的合同。</div> : <><div style={{ overflowX: 'auto' }}><table className="data-table"><thead><tr><th>合同</th><th>处理</th><th>资格</th><th>交付/目标</th><th>操作</th></tr></thead><tbody>{docs.data.items.map((document) => <DocumentRow key={document.document_id || document.client_id || document.name} taskId={taskId} document={document} />)}</tbody></table></div><Pagination page={docs.data.page} pageSize={docs.data.page_size} total={docs.data.total} onChange={setPage} /></>}</Card>
  </>
}
