import { useNavigate } from 'react-router-dom'
import { Button, Card, Spinner, StatusBadge } from '../../components/ui'
import { useCompareTasks } from '../../api/hooks'
import { taskDescription } from './shared'

// P1 比对任务列表（FL-D846：/compare）：只放任务检索入口与状态、差异概览，
// 新建与比对工作台分别迁至 /compare/new 与 /compare/:taskId。
export function CompareListPage() {
  const tasks = useCompareTasks()
  const navigate = useNavigate()
  return <div className="fundlex-compare-page">
    <div className="page-heading"><div><h1>合同对比</h1></div><div className="action-row"><Button type="button" onClick={() => void tasks.refetch()}>刷新</Button><Button type="button" variant="primary" onClick={() => navigate('/compare/new')}>＋ 新建对比任务</Button></div></div>
    <Card className="compare-task-card"><div className="page-heading"><div><h2>我的对比任务</h2></div></div>{tasks.error ? <div className="error-state">读取对比任务失败：{tasks.error instanceof Error ? tasks.error.message : '服务暂时不可用'}</div> : tasks.loading && !tasks.data ? <Spinner /> : tasks.data?.items.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>任务</th><th>分组</th><th>状态</th><th>结果</th><th /></tr></thead><tbody>{tasks.data.items.map((item) => <tr key={item.id}><td><button type="button" className="table-link compare-task-name-cell" title={item.name} onClick={() => navigate(`/compare/${item.id}`)}>{item.name}</button></td><td>{item.total || item.pairs?.length || 0}</td><td><StatusBadge value={item.status} /></td><td className="compare-task-result-cell">{taskDescription(item)}</td><td><Button type="button" variant="primary" onClick={() => navigate(`/compare/${item.id}`)}>查看</Button></td></tr>)}</tbody></table></div> : <div className="empty-state"><strong>还没有合同对比任务</strong><p>创建一组或多组左右合同开始比较。</p></div>}</Card>
  </div>
}
