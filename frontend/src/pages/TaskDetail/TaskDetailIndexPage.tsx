import { Link } from 'react-router-dom'
import { useTasks } from '../../api/hooks'
import { Button, Card, Spinner, StatusBadge } from '../../components/ui'
import { ErrorState, formatDate, Pagination } from '../Tasks'
import { useState } from 'react'

export function TaskDetailIndexPage() {
  const [page, setPage] = useState(1)
  const tasks = useTasks({ page, page_size: 20, sort: 'newest' })
  const items = tasks.data?.items || []
  return <>
    <div className="page-heading"><div><p>工作区 / 任务详情</p><h1>任务详情</h1><p>选择任务查看处理阶段、合同交付状态、异常原因和下载入口。</p></div><Link to="/tasks/new"><Button variant="primary">新建任务</Button></Link></div>
    <Card>
      {tasks.error ? <ErrorState error={tasks.error} onRetry={() => void tasks.refetch()} /> : tasks.loading && !tasks.data ? <Spinner label="正在读取任务" /> : !items.length ? <div className="empty-state">当前没有可查看的任务。<br /><Link to="/tasks/new">创建第一个任务</Link></div> : <>
        <div className="table-scroll"><table className="data-table"><thead><tr><th>任务</th><th>状态</th><th>合同进度</th><th>指引快照</th><th>创建时间</th></tr></thead><tbody>{items.map((task) => <tr key={task.id}><td><Link to={`/tasks/${task.id}`}>{task.name}</Link><div className="muted">{task.id}</div></td><td><StatusBadge value={task.status} /></td><td>{task.completed ?? 0}/{task.total ?? '—'}<div className="muted">异常 {task.exceptions ?? 0} · 待补传 {task.pending_upload ?? 0}</div></td><td>{task.guide_snapshot?.version_id || task.ruleset_version || '—'}</td><td>{formatDate(task.created_at)}</td></tr>)}</tbody></table></div>
        <Pagination page={tasks.data?.page ?? page} pageSize={tasks.data?.page_size ?? 20} total={tasks.data?.total ?? 0} onChange={setPage} />
      </>}
    </Card>
  </>
}
