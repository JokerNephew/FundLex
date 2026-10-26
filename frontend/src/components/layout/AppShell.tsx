import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useAuthStore } from '../../stores/auth'
import { assetPath } from '../../api/client'
import { useTasks } from '../../api/hooks'
import { Button } from '../ui'

const workspaceLinks = [
  ['/tasks', '任务总览', 'grid'],
  ['/tasks/new', '新建任务', 'upload'],
  ['/tasks/detail', '任务详情', 'detail'],
] as const

const configLinks = [
  ['/guides', '指引配置', 'book'],
  ['/settings', '设置', 'settings'],
] as const

function NavIcon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    grid: <><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>,
    upload: <><path d="M12 16V3m0 0L7 8m5-5 5 5" /><path d="M4 16v4h16v-4" /></>,
    book: <><path d="M5 4h6a2 2 0 0 1 2 2v14a2 2 0 0 0-2-2H5z" /><path d="M19 4h-6a2 2 0 0 0-2 2v14a2 2 0 0 1 2-2h6z" /></>,
    settings: <><path d="M4 6h16M4 12h16M4 18h16" /><path d="M8 3v6M16 9v6M10 15v6" /></>,
    compare: <><path d="M8 6h13M8 12h13M8 18h13" /><path d="M3 6h1M3 12h1M3 18h1" /></>,
    detail: <><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
  }
  return <svg viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

export function AppShell() {
  const { user, capabilities, logout } = useAuthStore()
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const helpTriggerRef = useRef<HTMLButtonElement>(null)
  const helpCloseRef = useRef<HTMLButtonElement>(null)
  const helpDialogRef = useRef<HTMLElement>(null)
  const previousFocusRef = useRef<HTMLElement | null>(null)
  const openHelp = () => {
    previousFocusRef.current = document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : helpTriggerRef.current
    setHelpOpen(true)
  }
  const closeHelp = () => {
    setHelpOpen(false)
  }
  const taskQuery = useTasks({ page: 1, page_size: 50, sort: 'newest' }, { pollMs: 10_000 })
  const previous = useRef<Record<string, string>>({})
  const [notifications, setNotifications] = useState<Array<{ id: string; taskId: string; title: string; detail: string }>>([])
  useEffect(() => {
    const next = Object.fromEntries((taskQuery.data?.items || []).map((task) => [task.id, task.status]))
    if (Object.keys(previous.current).length) {
      const changes = (taskQuery.data?.items || []).flatMap((task) => {
        const old = previous.current[task.id]
        if (!old || old === task.status || !['completed', 'paused', 'failed'].includes(task.status)) return []
        return [{ id: `${task.id}:${task.status}`, taskId: task.id, title: task.status === 'completed' ? '任务处理完成' : task.status === 'paused' ? '任务已暂停' : '任务处理失败', detail: task.name }]
      })
      if (changes.length) setNotifications((current) => [...changes, ...current].slice(0, 8))
    }
    previous.current = next
  }, [taskQuery.data])
  useEffect(() => {
    if (!helpOpen) {
      return
    }
    previousFocusRef.current ||= document.activeElement instanceof HTMLElement && document.activeElement !== document.body ? document.activeElement : helpTriggerRef.current
    const frame = requestAnimationFrame(() => helpCloseRef.current?.focus())
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeHelp()
        return
      }
      if (event.key !== 'Tab') return
      const dialog = helpDialogRef.current
      if (!dialog) return
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter((element) => element.getAttribute('aria-hidden') !== 'true')
      if (!focusable.length) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    const background = Array.from(document.querySelectorAll<HTMLElement>('.app-shell > :not(.help-backdrop)'))
    const previousInert = background.map((element) => element.inert)
    const restoreFocusTarget = previousFocusRef.current || helpTriggerRef.current
    background.forEach((element) => { element.inert = true })
    document.addEventListener('keydown', onKeyDown)
    return () => {
      cancelAnimationFrame(frame)
      document.removeEventListener('keydown', onKeyDown)
      background.forEach((element, index) => { element.inert = previousInert[index] })
      restoreFocusTarget?.focus()
    }
  }, [helpOpen])
  return <div className="app-shell">
       <header className="topbar">
        <NavLink className="brand" to="/workspace"><img src={assetPath('/static/assets/gf-logo-mark.png')} alt="广发基金" /><span>FundLex</span></NavLink>
      <div className="topbar-actions">
        <span className="identity">{user?.display_name || user?.username || (capabilities?.auth_mode === 'dev' ? '本地开发身份' : '')}</span>
        <div className="notification-center">
           <Button type="button" variant="quiet" aria-label="消息" aria-expanded={notificationsOpen} onClick={() => setNotificationsOpen((open) => !open)}>消息{notifications.length ? <span className="notification-count">{notifications.length}</span> : null}</Button>
           {notificationsOpen && <div className="notification-panel" role="status"><strong>消息</strong>{notifications.length ? <ul>{notifications.map((notice) => <li key={notice.id}><Link to={`/tasks/${notice.taskId}`} onClick={() => setNotificationsOpen(false)}><strong>{notice.title}</strong><span>{notice.detail}</span></Link></li>)}</ul> : <p className="muted">暂无任务状态消息</p>}</div>}
        </div>
        {user && <Link className="topbar-link" to="/settings">修改密码</Link>}
        {user && <Button variant="quiet" onClick={() => void logout()}>退出登录</Button>}
      </div>
    </header>
    <div className="shell-body">
      <aside className="sidebar" aria-label="工作区导航">
        <nav>
          <div className="nav-group">工作区</div>
          {workspaceLinks.map(([to, label, icon]) => <NavLink end={to === '/tasks'} key={to} to={to} className={({ isActive }) => isActive ? 'nav-link is-active' : 'nav-link'}><NavIcon name={icon} /><span>{label}</span></NavLink>)}
           <NavLink to="/compare" className={({ isActive }) => isActive ? 'nav-link is-active' : 'nav-link'}><NavIcon name="compare" /><span>合同对比</span></NavLink>
          <div className="nav-group">配置</div>
          {configLinks.map(([to, label, icon]) => <NavLink key={to} to={to} className={({ isActive }) => isActive ? 'nav-link is-active' : 'nav-link'}><NavIcon name={icon} /><span>{label}</span></NavLink>)}
          {user?.role === 'admin' && <NavLink to="/users" className={({ isActive }) => isActive ? 'nav-link is-active' : 'nav-link'}><NavIcon name="settings" /><span>用户管理</span></NavLink>}
          <div className="sidebar-note">报告与诊断文件不作为最终合同</div>
        </nav>
      </aside>
      <main className="main-content"><Outlet /></main>
    </div>
     <footer className="app-footer"><span>© 2026 广发基金</span><span aria-hidden="true">·</span><span>FundLex {capabilities?.app_version || '—'}</span><span aria-hidden="true">·</span><button ref={helpTriggerRef} type="button" className="footer-link" onClick={openHelp}>帮助中心</button><span aria-hidden="true">·</span><span className="footer-link is-disabled">隐私政策</span><span aria-hidden="true">·</span><span className="footer-link is-disabled">服务条款</span></footer>
       {helpOpen && <div className="help-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) closeHelp() }}><section ref={helpDialogRef} className="help-dialog" role="dialog" aria-modal="true" aria-labelledby="help-title" tabIndex={-1}><div className="help-dialog__head"><div><small>使用说明 · FundLex</small><h2 id="help-title">帮助中心</h2></div><Button ref={helpCloseRef} type="button" variant="quiet" aria-label="关闭帮助中心" onClick={closeHelp}>关闭</Button></div><ol className="help-steps"><li><strong>准备文件</strong><span>仅接收可编辑 DOCX，可多选文件或选择整个文件夹；原文件会按账号隔离保存。</span></li><li><strong>创建任务</strong><span>上传完成后逐合同处理，单份失败不会影响其它合同；中断的任务可从任务详情继续补传。</span></li><li><strong>查看结果</strong><span>在任务详情分别查看资格、处理和交付状态，打开合同报告并下载最终版、修订版和报告。</span></li><li><strong>状态说明</strong><span>“结果不完整”表示仍有人工核对事项；工作文件和评测文件不能直接视为最终合同。</span></li><li><strong>安全与权限</strong><span>只能访问当前账号的任务、合同、指引和授权下载文件；会话失效后需要重新登录。</span></li></ol><div className="help-dialog__actions"><Button type="button" variant="primary" onClick={closeHelp}>知道了</Button></div></section></div>}
  </div>
}
