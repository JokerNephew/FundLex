import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card } from '../../components/ui'
import { useAuthStore } from '../../stores/auth'
import { assetPath } from '../../api/client'

/** 开发身份模式下的 /login：明确告知无需登录，并给「以开发身份继续」入口（项9 批3，FL-D740）。 */
export function DevIdentityLogin() {
  const user = useAuthStore((state) => state.user)
  return <div className="login-layout"><Card className="login-card">
    <div className="login-brand"><img src={assetPath('/static/assets/gf-logo-mark.png')} alt="广发基金" /><strong>FundLex</strong></div>
    <div className="page-heading"><div><h1>登录工作台</h1><p>合同修订工作台</p></div></div>
    <p className="muted">当前环境为开发身份模式，无需账号密码{user?.display_name || user?.username ? `；已使用身份 ${user.display_name || user.username}` : ''}。</p>
    <Link to="/tasks"><Button variant="primary">以开发身份继续</Button></Link>
  </Card></div>
}

export function LoginPage() {
  const login = useAuthStore((state) => state.login); const register = useAuthStore((state) => state.register); const registrationOpen = useAuthStore((state) => state.capabilities?.registration_open)
  const [mode, setMode] = useState<'login' | 'register'>('login'); const [username, setUsername] = useState(''); const [password, setPassword] = useState(''); const [displayName, setDisplayName] = useState(''); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setBusy(true); setError(''); try { if (mode === 'login') await login(username, password); else await register(username, password, displayName) } catch (nextError) { setError(nextError instanceof Error ? nextError.message : '操作未完成') } finally { setBusy(false) } }
   return <div className="login-layout"><Card className="login-card"><div className="login-brand"><img src={assetPath('/static/assets/gf-logo-mark.png')} alt="广发基金" /><strong>FundLex</strong></div><div className="page-heading"><div><h1>{mode === 'login' ? '登录工作台' : '创建工作台账号'}</h1><p>合同修订工作台</p></div></div><form className="form-stack" onSubmit={submit}><label>用户名<input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required /></label>{mode === 'register' && <label>显示名称<input value={displayName} onChange={(event) => setDisplayName(event.target.value)} autoComplete="name" /></label>}<label>密码<input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength={8} required /></label>{error && <p className="form-error">{error}</p>}<Button variant="primary" type="submit" disabled={busy}>{busy ? '处理中…' : mode === 'login' ? '登录' : '注册并登录'}</Button>{registrationOpen && <Button type="button" variant="quiet" onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError('') }}>{mode === 'login' ? '注册新账号' : '返回登录'}</Button>}</form></Card></div>
}
