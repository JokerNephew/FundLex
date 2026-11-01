import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/endpoints'
import { Button, Card } from '../../components/ui'
import type { FeishuBinding, FeishuOAuthStart } from '../../types'
import { useAuthStore } from '../../stores/auth'

// FL-D989：飞书绑定独立成页，账户修改区不再混入飞书内容。
export function FeishuBindingPage() {
  const user = useAuthStore((state) => state.user)
  const [binding, setBinding] = useState<FeishuBinding>()
  const [bindingCode, setBindingCode] = useState('')
  const [bindingError, setBindingError] = useState('')
  const [bindingBusy, setBindingBusy] = useState(false)
  const [oauth, setOauth] = useState<FeishuOAuthStart>()
  const [oauthMessage, setOauthMessage] = useState('')

  const loadBinding = async () => {
    try {
      setBinding(await api.feishuBinding())
      setBindingError('')
    } catch (nextError) {
      setBindingError(nextError instanceof Error ? nextError.message : '飞书绑定状态暂无法读取')
    }
  }
  useEffect(() => { void loadBinding() }, [])
  useEffect(() => {
    if (!oauth) return
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const next = await api.feishuBinding()
          if (next.bound) {
            setBinding(next)
            setOauth(undefined)
            setOauthMessage('飞书账号已绑定。')
            setBindingCode('')
          }
        } catch { /* keep the QR visible until expiry or success */ }
      })()
    }, 2500)
    return () => window.clearInterval(timer)
  }, [oauth])

  const createBindingCode = async () => {
    setBindingBusy(true)
    setBindingError('')
    try {
      const result = await api.createFeishuBindingCode()
      setBindingCode(result.code)
    } catch (nextError) {
      setBindingError(nextError instanceof Error ? nextError.message : '绑定码生成失败')
    } finally {
      setBindingBusy(false)
    }
  }
  const startOAuth = async () => {
    setBindingBusy(true)
    setBindingError('')
    setOauthMessage('正在生成扫码绑定二维码…')
    try {
      const result = await api.startFeishuOAuth()
      setOauth(result)
      const minutes = Math.max(1, Math.round((result.expires_at - Date.now() / 1000) / 60))
      setOauthMessage(`请用飞书扫描二维码并确认授权，二维码 ${minutes} 分钟内有效。`)
    } catch (nextError) {
      setOauthMessage(nextError instanceof Error ? nextError.message : '二维码生成失败')
    } finally {
      setBindingBusy(false)
    }
  }
  const revokeBinding = async () => {
    setBindingBusy(true)
    setBindingError('')
    try {
      await api.revokeFeishuBinding()
      setBinding(undefined)
      setBindingCode('')
      setOauth(undefined)
      setOauthMessage('')
    } catch (nextError) {
      setBindingError(nextError instanceof Error ? nextError.message : '解绑失败')
    } finally {
      setBindingBusy(false)
    }
  }

  return <>
    <div className="page-heading">
      <div><p><Link to="/settings">设置</Link> / 飞书绑定</p><h1>飞书绑定</h1><p>在飞书私聊里发送绑定码或扫码授权，仅绑定当前账号{user ? `（${user.display_name || user.username}）` : ''}。</p></div>
    </div>

    <Card>
      <h2>飞书私聊绑定</h2>
      <p>绑定后可直接在飞书私聊机器人发送合同、提交任务。</p>
      {bindingError && <p className="form-error">{bindingError}</p>}
      {binding?.bound ? <><p>已绑定飞书账号 <code>{binding.subject_id?.slice(0, 12)}…</code></p><Button variant="danger" onClick={() => void revokeBinding()} disabled={bindingBusy}>解除绑定</Button></> : <>
        <div className="action-row">
          <Button variant="primary" onClick={() => void createBindingCode()} disabled={bindingBusy}>{bindingBusy ? '处理中…' : '生成绑定码'}</Button>
          <Button onClick={() => void startOAuth()} disabled={bindingBusy}>{bindingBusy ? '处理中…' : '生成扫码绑定二维码'}</Button>
          {bindingCode && <code aria-label="飞书绑定码">{bindingCode}</code>}
        </div>
        {oauth && <div className="settings-oauth"><div className="settings-qr-frame">{oauth.qr_svg ? <div dangerouslySetInnerHTML={{ __html: oauth.qr_svg }} /> : oauth.qr_png ? <img src={oauth.qr_png} alt="飞书绑定二维码" /> : null}</div><p>{oauthMessage}</p><a href={oauth.authorization_url} target="_blank" rel="noreferrer">在飞书中打开授权页</a></div>}
        {!oauth && oauthMessage && <p>{oauthMessage}</p>}
      </>}
    </Card>
  </>
}
