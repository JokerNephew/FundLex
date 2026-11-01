import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useGuideSettings, useTaskStats, useTasks } from '../../api/hooks'
import { Button, Card, Select, Spinner, StatusBadge } from '../../components/ui'
import type { TaskStatus } from '../../types'

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return <div className="error-state"><span>{error instanceof Error ? error.message : '请求未完成，请稍后重试。'}</span>{onRetry && <Button type="button" variant="quiet" onClick={onRetry}>重试</Button>}</div>
}

export function LoadingCard() {
  return <Card><Spinner label="加载中" /></Card>
}

export function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString('zh-CN') : '—'
}

function taskSummary(task: { status: string; total?: number; completed?: number; exceptions?: number; pending_upload?: number }) {
  if (task.status === 'failed') return '处理失败，点进去看哪份出了问题。'
  if (task.status === 'paused') return '已暂停，点进去恢复。'
  if (task.pending_upload) return `${task.pending_upload} 份合同仍待上传。`
  if (task.status === 'completed_with_exceptions') return `还有 ${task.exceptions ?? 0} 份没改完，要人工核一眼。`
  if (task.status === 'completed' && task.exceptions) return `还有 ${task.exceptions} 份没改完，要人工核一眼。`
  if (task.status === 'completed') return `已完成 ${task.completed ?? 0}/${task.total ?? 0} 份合同。`
  return `正在处理 ${task.completed ?? 0}/${task.total ?? 0} 份合同。`
}

/** 全站唯一分页规格（FL-D806）：左「共 N 条 · 第 x / y 页」，右 每页 select+翻页；句式与 V1 app.js pagination() 一致 */
export function Pagination({ page, pageSize, total, onChange, onPageSizeChange }: { page: number; pageSize: number; total: number; onChange: (page: number) => void; onPageSizeChange?: (size: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return <div className="pagination" aria-label="分页"><span>共 {total} 条 · 第 {page} / {pages} 页</span><div className="controls">{onPageSizeChange && <label className="muted">每页<Select className="control-select" value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))} aria-label="每页条数">{[20, 50, 100].map((n) => <option key={n} value={n}>{n}</option>)}</Select></label>}<Button disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</Button><Button disabled={page >= pages} onClick={() => onChange(page + 1)}>下一页</Button></div></div>
}

export function TasksPage() {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<TaskStatus | ''>('')
  const [guideVersionId, setGuideVersionId] = useState('')
  const [sort, setSort] = useState('newest')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const tasks = useTasks({ q: search, status, guide_version_id: guideVersionId, sort, page, page_size: pageSize }, { pollMs: 20_000 })
  const stats = useTaskStats()
  const guides = useGuideSettings()
  const items = tasks.data?.items ?? []
   const connectionText = useMemo(() => stats.error ? '统计读取失败' : stats.loading && !stats.data ? '读取中…' : '', [stats.data, stats.error, stats.loading])
  const submitSearch = (event: React.FormEvent) => { event.preventDefault(); setPage(1); setSearch(query.trim()) }
  const statValues = useMemo(() => {
    const s = stats.data
    return [
      { label: '处理中', value: s?.active_tasks, note: '个任务进行中' },
      { label: '待处理合同', value: s?.pending_contracts, note: '等前面的任务处理完' },
      { label: '异常合同', value: s?.exception_contracts, note: `需人工处理 · 失败 ${s?.failed_contracts ?? '—'}` },
      { label: '本月处理合同', value: s?.processed_contracts, note: `完成率 ${typeof s?.completion_rate === 'number' ? `${Math.round(s.completion_rate * 100)}%` : '—'}` },
    ]
  }, [stats.data])
  const statsEmpty = Boolean(stats.data) && !stats.loading && statValues.every((item) => !item.value)
  return <>
    <div className="page-heading"><div><h1>任务</h1><p>跟踪每个任务的上传、处理与交付进度。</p></div><div className="action-row"><Link to="/tasks/new"><Button variant="primary">新建任务</Button></Link></div></div>
      {statsEmpty ? (
        <p className="muted stats-empty" data-testid="stats-empty">还没有处理中的任务。</p>
      ) : (
      <div className="stats-grid">{statValues.map((item) => <Card key={item.label}><span className="muted">{item.label}</span><strong className="stat-value">{item.value ?? '—'}</strong><small>{item.note}</small></Card>)}</div>
      )}
      {Boolean(connectionText || stats.error) && <p className="muted stats-connection" data-testid="stats-connection">{connectionText}{Boolean(stats.error) && <> · <Button type="button" variant="quiet" onClick={() => void stats.refetch()}>重试统计</Button></>}</p>}
      <Card><form className="action-row" onSubmit={submitSearch} role="search"><label className="muted">搜索任务<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="按任务名称搜索" /></label><label className="muted">状态<Select value={status} onChange={(event) => { setStatus(event.target.value as TaskStatus | ''); setPage(1) }}><option value="">全部状态</option><option value="queued">排队中</option><option value="running">处理中</option><option value="paused">已暂停</option><option value="completed">已完成</option><option value="completed_with_exceptions">已完成（部分需核对）</option><option value="failed">处理失败</option></Select></label><label className="muted">指引<Select value={guideVersionId} onChange={(event) => { setGuideVersionId(event.target.value); setPage(1) }}><option value="">全部指引</option>{guides.data?.available?.map((guide) => <option key={guide.id} value={guide.id}>{guide.filename}</option>)}</Select></label><label className="muted">排序<Select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1) }}><option value="newest">最新创建</option><option value="oldest">最早创建</option><option value="name">名称 A-Z</option><option value="name_desc">名称 Z-A</option></Select></label><Button type="submit" variant="primary">搜索</Button></form></Card>
      <Card><div className="page-heading"><div><h2>任务清单</h2></div><Button onClick={() => void tasks.refetch()} disabled={tasks.refreshing}>{tasks.refreshing ? '刷新中…' : '刷新'}</Button></div>{tasks.error ? <ErrorState error={tasks.error} onRetry={() => void tasks.refetch()} /> : tasks.loading && !tasks.data ? <Spinner /> : !items.length ? <div className="empty-state">{search || status || guideVersionId ? '没有符合筛选条件的任务。' : <>还没有任务。<br /><Link to="/tasks/new">创建第一个合同任务</Link></>}</div> : <><div className="table-scroll"><table className="data-table"><thead><tr><th>任务</th><th>状态</th><th>行动提示</th><th>合同</th><th>创建时间</th></tr></thead><tbody>{items.map((task) => <tr key={task.id}><td><Link to={`/tasks/${task.id}`}>{task.name}</Link></td><td><StatusBadge value={task.status} /></td><td>{taskSummary(task)}</td><td>{task.completed ?? 0}/{task.total ?? '—'}<div className="muted">异常 {task.exceptions ?? 0}</div></td><td>{formatDate(task.created_at)}</td></tr>)}</tbody></table></div><Pagination page={tasks.data?.page ?? page} pageSize={tasks.data?.page_size ?? pageSize} total={tasks.data?.total ?? 0} onChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1) }} /></>}</Card>
  </>
}
