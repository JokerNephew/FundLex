import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Button, Spinner } from '../components/ui'
import { AppShell } from '../components/layout'
import { useAuthStore } from '../stores/auth'
import { LoginPage } from '../pages/Auth'
import { DocumentDetailPage } from '../pages/DocumentDetail/DocumentDetailPage'
import { GuidesPage, GuideDetailPage } from '../pages/Guides'
import { NewTaskPage } from '../pages/NewTask'
import { SettingsPage } from '../pages/Settings'
import { TaskDetailPage } from '../pages/TaskDetail'
import { TaskDetailIndexPage } from '../pages/TaskDetail/TaskDetailIndexPage'
import { ReviewPage } from '../pages/Review/ReviewPage'
import { TasksPage } from '../pages/Tasks'
import { UsersPage } from '../pages/Users'
import { ComparePage } from '../pages/Compare/ComparePage'
import { getBasePath } from '../api/client'

function AppRoutes() {
  const auth = useAuthStore()
  if (!auth.ready) return <div className="login-layout"><Spinner label="连接服务" /></div>
  if (auth.error) return <div className="login-layout"><div className="fundlex-error" role="alert"><strong>暂时无法连接服务</strong><p>{auth.error instanceof Error ? auth.error.message : '服务初始化失败，请稍后重试。'}</p><Button type="button" onClick={() => void auth.load()}>重试</Button></div></div>
  if (auth.capabilities?.login_required && !auth.user) return <LoginPage />
  return <Routes><Route element={<AppShell />}>
    <Route path="/" element={<Navigate to="/tasks" replace />} />
    <Route path="/workspace" element={<Navigate to="/tasks" replace />} />
    <Route path="/tasks" element={<TasksPage />} />
     <Route path="/tasks/new" element={<NewTaskPage />} />
     <Route path="/tasks/detail" element={<TaskDetailIndexPage />} />
    <Route path="/tasks/:taskId" element={<TaskDetailPage />} />
     <Route path="/tasks/:taskId/documents/:documentId/report" element={<DocumentDetailPage />} />
    <Route path="/tasks/:taskId/documents/:documentId/detail" element={<DocumentDetailPage />} />
    <Route path="/tasks/:taskId/documents/:documentId/revisions" element={<ReviewPage />} />
    <Route path="/tasks/:taskId/documents/:documentId/review" element={<ReviewPage />} />
    <Route path="/guides" element={<GuidesPage />} />
    <Route path="/guides/:guideId" element={<GuideDetailPage />} />
    <Route path="/settings" element={<SettingsPage />} />
     <Route path="/users" element={<UsersPage />} />
     <Route path="/compare" element={<ComparePage />} />
    <Route path="*" element={<Navigate to="/tasks" replace />} />
  </Route></Routes>
}

export function App() {
  const load = useAuthStore((state) => state.load)
  useEffect(() => { void load() }, [load])
  return <BrowserRouter basename={getBasePath() || undefined}><AppRoutes /></BrowserRouter>
}
