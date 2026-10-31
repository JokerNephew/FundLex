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
  if (task.status === 'failed') return '处理失败，请打开任务查看原因。'
  if (task.status === 'paused') return '任务已暂停，可从详情页恢复处理。'
  if (task.pending_upload) return `${task.pending_upload} 份合同仍待上传。`
  if (task.status === 'completed_with_exceptions') return `${task.exceptions ?? 0} 份合同需要关注未完成项。`
  if (task.status === 'completed' && task.exceptions) return `${task.exceptions} 份合同需要关注未完成项。`
  if (task.status === 'completed') return `已完成 ${task.completed ?? 0}/${task.total ?? 0} 份合同。`
  return `正在处理 ${task.completed ?? 0}/${task.total ?? 0} 份合同。`
}

export function Pagination({ page, pageSize, total, onChange }: { page: number; pageSize: number; total: number; onChange: (page: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (pages <= 1) return null
  return <div className="action-row" aria-label="分页"><Button disabled={page <= 1} onClick={() => onChange(page - 1)}>上一页</Button><span className="muted">共 {total} 条 · 第 {page} / {pages} 页</span><Button disabled={page >= pages} onClick={() => onChange(page + 1)}>下一页</Button></div>
}

export function TasksPage() {
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<TaskStatus | ''>('')
  const [guideVersionId, setGuideVersionId] = useState('')
  const [sort, setSort] = useState('newest')
  const [page, setPage] = useState(1)
  const pageSize = 20
  const tasks = useTasks({ q: search, status, guide_version_id: guideVersionId, sort, page, page_size: pageSize }, { pollMs: 20_000 })
  const stats = useTaskStats()
  const guides = useGuideSettings()
  const items = tasks.data?.items ?? []
   const connectionText = useMemo(() => stats.error ? '统计读取失败' : stats.data ? '服务已连接' : stats.loading ? '读取中…' : '暂无统计', [stats.data, stats.error, stats.loading])
  const submitSearch = (event: React.FormEvent) => { event.preventDefault(); setPage(1); setSearch(query.trim()) }
  const statValues = useMemo(() => {
    const s = stats.data
    return [
      { label: '处理中', value: s?.active_tasks, note: '个任务进行中' },
      { label: '待处理合同', value: s?.pending_contracts, note: '等待处理服务完成' },
      { label: '异常合同', value: s?.exception_contracts, note: `需人工处理 · 失败 ${s?.failed_contracts ?? '—'}` },
      { label: '本月处理合同', value: s?.processed_contracts, note: `完成率 ${typeof s?.completion_rate === 'number' ? `${Math.round(s.completion_rate * 100)}%` : '—'}` },
    ]
  }, [stats.data])
  const statsEmpty = Boolean(stats.data) && !stats.loading && statValues.every((item) => !item.value)
  return <>
    <div className="page-heading"><div><h1>任务</h1><p>先处理暂停、失败和待交付任务，再查看已完成结果。</p></div><div className="action-row"><Link to="/tasks/new"><Button variant="primary">新建任务</Button></Link></div></div>
      {statsEmpty ? (
        <p className="muted stats-empty" data-testid="stats-empty">暂无处理统计——创建第一个任务后，这里会显示进行中、待处理与异常合同概况。</p>
      ) : (
      <div className="stats-grid">{statValues.map((item) => <Card key={item.label}><span className="muted">{item.label}</span><strong className="stat-value">{item.value ?? '—'}</strong><small>{item.note}</small></Card>)}</div>
      )}
      <p className="muted stats-connection" data-testid="stats-connection">{connectionText}{Boolean(stats.error) && <> · <Button type="button" variant="quiet" onClick={() => void stats.refetch()}>重试统计</Button></>}</p>
      <Card><form className="action-row" onSubmit={submitSearch} role="search"><label className="muted">搜索任务<input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="按任务名称搜索" /></label><label className="muted">状态<Select value={status} onChange={(event) => { setStatus(event.target.value as TaskStatus | ''); setPage(1) }}><option value="">全部状态</option><option value="queued">排队中</option><option value="running">处理中</option><option value="paused">已暂停</option><option value="completed">已完成</option><option value="completed_with_exceptions">已完成（含异常）</option><option value="failed">失败（含失败合同）</option></Select></label><label className="muted">指引<Select value={guideVersionId} onChange={(event) => { setGuideVersionId(event.target.value); setPage(1) }}><option value="">全部指引</option>{guides.data?.available?.map((guide) => <option key={guide.id} value={guide.id}>{guide.filename}</option>)}</Select></label><label className="muted">排序<Select value={sort} onChange={(event) => { setSort(event.target.value); setPage(1) }}><option value="newest">最新创建</option><option value="oldest">最早创建</option><option value="name">名称 A-Z</option><option value="name_desc">名称 Z-A</option></Select></label><Button type="submit" variant="primary">搜索</Button></form></Card>
      <Card><div className="page-heading"><div><h2>任务清单</h2></div><Button onClick={() => void tasks.refetch()} disabled={tasks.refreshing}>{tasks.refreshing ? '刷新中…' : '刷新'}</Button></div>{tasks.error ? <ErrorState error={tasks.error} onRetry={() => void tasks.refetch()} /> : tasks.loading && !tasks.data ? <Spinner /> : !items.length ? <div className="empty-state">{search || status || guideVersionId ? '没有符合筛选条件的任务。' : <>还没有任务。<br /><Link to="/tasks/new">创建第一个合同任务</Link></>}</div> : <><div className="table-scroll"><table className="data-table"><thead><tr><th>任务</th><th>状态</th><th>行动提示</th><th>合同</th><th>指引快照</th><th>创建时间</th></tr></thead><tbody>{items.map((task) => <tr key={task.id}><td><Link to={`/tasks/${task.id}`}>{task.name}</Link></td><td><StatusBadge value={task.status} /></td><td>{taskSummary(task)}</td><td>{task.completed ?? 0}/{task.total ?? '—'}<div className="muted">异常 {task.exceptions ?? 0}</div></td><td>{task.guide_snapshot || task.ruleset_version ? '修改指引已锁定' : '—'}</td><td>{formatDate(task.created_at)}</td></tr>)}</tbody></table></div><Pagination page={tasks.data?.page ?? page} pageSize={tasks.data?.page_size ?? pageSize} total={tasks.data?.total ?? 0} onChange={setPage} /></>}</Card>
  </>
}
