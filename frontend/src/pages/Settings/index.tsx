import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/endpoints'
import { useCapabilities, useModelSettings, useModelSettingsMutation } from '../../api/hooks'
import { Button, Card, Spinner } from '../../components/ui'
import type { FeishuBinding, FeishuOAuthStart, ModelRoleSettings } from '../../types'
import { useAuthStore } from '../../stores/auth'
import { ErrorState } from '../Tasks'

function capabilityLabel(value: unknown, labels: Record<string, string>): string {
  const key = String(value || '')
  return labels[key] || key || '—'
}

type RoleForm = {
  provider: string
  model: string
  timeout_s: string
  max_tokens: string
  retries: string
  max_context_chars: string
  request_options: string
}

function roleForm(role?: ModelRoleSettings): RoleForm {
  return {
    provider: role?.provider || '',
    model: role?.model || '',
    timeout_s: String(role?.timeout_s ?? 45),
    max_tokens: String(role?.max_tokens ?? 1500),
    retries: String(role?.retries ?? 1),
    max_context_chars: String(role?.max_context_chars ?? 12000),
    request_options: JSON.stringify(role?.request_options || {}, null, 2),
  }
}

function RoleFields({ role, value, onChange, disabled }: { role: 'primary' | 'review'; value: RoleForm; onChange: (next: RoleForm) => void; disabled: boolean }) {
  const update = (field: keyof RoleForm, next: string) => onChange({ ...value, [field]: next })
  const prefix = role === 'primary' ? '主模型' : '复核模型'
  return <div className="form-stack">
    <div className="action-row">
      <label>服务商（系统提供）<input value={value.provider} disabled /></label>
      <label>{prefix} Model<input value={value.model} disabled={disabled} onChange={(event) => update('model', event.target.value)} required /></label>
    </div>
    <div className="action-row">
      <label>超时（秒）<input type="number" min="1" max="600" value={value.timeout_s} disabled={disabled} onChange={(event) => update('timeout_s', event.target.value)} /></label>
      <label>最大输出 tokens<input type="number" min="1" value={value.max_tokens} disabled={disabled} onChange={(event) => update('max_tokens', event.target.value)} /></label>
      <label>重试次数<input type="number" min="0" max="10" value={value.retries} disabled={disabled} onChange={(event) => update('retries', event.target.value)} /></label>
    </div>
    <div className="action-row">
      <label>上下文字符上限<input type="number" min="1000" value={value.max_context_chars} disabled={disabled} onChange={(event) => update('max_context_chars', event.target.value)} /></label>
    </div>
    <label>请求选项 JSON<textarea rows={3} value={value.request_options} disabled={disabled} onChange={(event) => update('request_options', event.target.value)} /><span className="muted">例如 {`{"thinking":{"type":"disabled"}}`}；只允许供应商支持的普通请求选项。</span></label>
  </div>
}

export function SettingsPage() {
  const capabilities = useCapabilities()
  const user = useAuthStore((state) => state.user)
  const model = useModelSettings()
  const modelMutation = useModelSettingsMutation()
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [binding, setBinding] = useState<FeishuBinding>()
  const [bindingCode, setBindingCode] = useState('')
  const [bindingError, setBindingError] = useState('')
  const [bindingBusy, setBindingBusy] = useState(false)
  const [oauth, setOauth] = useState<FeishuOAuthStart>()
  const [oauthMessage, setOauthMessage] = useState('')
  const [primaryForm, setPrimaryForm] = useState<RoleForm>(roleForm())
  const [reviewForm, setReviewForm] = useState<RoleForm>(roleForm())
  const [reviewInherits, setReviewInherits] = useState(true)
  const [modelMessage, setModelMessage] = useState('')
  const [modelError, setModelError] = useState('')
  const [modelBusy, setModelBusy] = useState(false)

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
  useEffect(() => {
    if (!model.data) return
    setPrimaryForm(roleForm(model.data.primary))
    setReviewForm(roleForm(model.data.review))
    setReviewInherits(Boolean(model.data.review_inherits))
  }, [model.data])

  const changePassword = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setMessage('')
    setError('')
    try {
      await api.changePassword(oldPassword, newPassword)
      setOldPassword('')
      setNewPassword('')
      setMessage('密码已修改，其他会话已失效。')
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '密码修改未完成')
    } finally {
      setBusy(false)
    }
  }
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
  const saveModel = async (event: React.FormEvent) => {
    event.preventDefault()
    setModelBusy(true)
    setModelMessage('')
    setModelError('')
    try {
      const parsedOptions = (raw: string) => {
        const value = JSON.parse(raw || '{}')
        if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('请求选项必须是 JSON 对象')
        return value as Record<string, unknown>
      }
      const toPayload = (form: RoleForm) => ({
        model: form.model.trim(),
        timeout_s: Number(form.timeout_s),
        max_tokens: Number(form.max_tokens),
        retries: Number(form.retries),
        max_context_chars: Number(form.max_context_chars),
        request_options: parsedOptions(form.request_options),
      })
      const payload = {
        primary: toPayload(primaryForm),
        review: reviewInherits ? null : toPayload(reviewForm),
      }
      const saved = await modelMutation.mutateAsync(payload)
      setModelMessage(saved.editable ? '我的模型配置已保存；仅用于之后新建的合同修改任务。' : '模型配置已保存。')
      await model.refetch()
    } catch (nextError) {
      setModelError(nextError instanceof Error ? nextError.message : '模型配置保存失败')
    } finally {
      setModelBusy(false)
    }
  }

  return <>
    <div className="page-heading">
      <div><h1>设置</h1><p>管理个人偏好、账号安全、飞书接入和模型配置。</p></div>
      <div className="action-row"><Link to="/guides"><Button>我的指引</Button></Link>{user?.role === 'admin' && <Link to="/users"><Button>用户管理</Button></Link>}</div>
    </div>

    <Card>
      <h2>运行能力</h2>
      {capabilities.error ? <ErrorState error={capabilities.error} /> : capabilities.loading && !capabilities.data ? <Spinner /> : <dl className="settings-capability-list">
        <dt>认证模式</dt><dd>{capabilityLabel(capabilities.data?.auth_mode, { password: '账号密码登录', dev: '开发身份登录' })}</dd>
        <dt>引擎</dt><dd>{capabilityLabel(capabilities.data?.engine?.id, { recall_first: '召回优先修订引擎' })}</dd>
        <dt>交付模式</dt><dd>{capabilityLabel(capabilities.data?.engine?.delivery_mode, { formal: '正式交付模式', evaluation: '评测模式' })}</dd>
        <dt>正式写入</dt><dd>{capabilities.data?.engine?.auto_write_enabled ? '已启用' : '当前不可用'}</dd>
        <dt>单文件限制</dt><dd>{capabilities.data?.upload_limits?.max_file_bytes ? `${Math.round(capabilities.data.upload_limits.max_file_bytes / 1024 / 1024)} MB` : '—'}</dd>
      </dl>}
    </Card>

    <Card>
      <div className="page-heading">
        <div>
          <h2>模型配置</h2>
          <p className="muted">配置自己使用的主模型和复核模型；仅影响你的新建合同修改任务。地址与密钥由系统管理，不影响其他用户。</p>
        </div>
        {model.data?.editable && <span className="muted">可编辑</span>}
      </div>
      {model.error ? <ErrorState error={model.error} onRetry={() => void model.refetch()} /> : model.loading && !model.data ? <Spinner /> : model.data ? <>
        <p className="muted">来源：{model.data.source === 'personal' ? '我的配置' : '系统默认'} · 模型名称需由当前服务商支持 · 主模型 {model.data.primary.model || '未配置'}</p>
        {model.data.config_error && <p className="form-error">当前配置有问题：{model.data.config_error}</p>}
        <form className="form-stack" onSubmit={saveModel}>
          <h3>主模型</h3>
          <RoleFields role="primary" value={primaryForm} onChange={setPrimaryForm} disabled={!model.data.editable || modelBusy} />
          <label className="settings-check"><input type="checkbox" checked={reviewInherits} disabled={!model.data.editable || modelBusy} onChange={(event) => setReviewInherits(event.target.checked)} /> 复核模型继承主模型</label>
          {!reviewInherits && <>
            <h3>复核模型</h3>
            <RoleFields role="review" value={reviewForm} onChange={setReviewForm} disabled={!model.data.editable || modelBusy} />
          </>}
          {model.data.editable && <div className="action-row"><Button variant="primary" type="submit" disabled={modelBusy}>{modelBusy ? '保存中…' : '保存模型配置'}</Button>{model.data.primary.api_key_set ? <span className="muted">主模型密钥已配置</span> : <span className="form-error">主模型密钥未配置</span>}{model.data.review.api_key_set && !model.data.review_inherits ? <span className="muted">复核模型密钥已配置</span> : null}</div>}
          {modelMessage && <p role="status">{modelMessage}</p>}
          {modelError && <p className="form-error">{modelError}</p>}
        </form>
        <p className="muted">仅影响你的新建合同修改任务；已创建任务保留自己的选择快照。服务地址与密钥仍由系统提供。指引解析和法规生成暂使用系统模型。</p>
        <Button disabled={modelBusy} onClick={() => { void api.resetModelSettings().then(() => model.refetch()).catch((nextError) => setModelError(nextError instanceof Error ? nextError.message : '恢复默认失败')) }}>恢复系统模型默认值</Button>
      </> : null}
    </Card>

    <Card>
      <h2>飞书私聊绑定</h2>
      <p>生成一次性绑定码后，在飞书与 FundLex 机器人私聊发送“绑定 绑定码”。绑定只关联当前账号，绑定码 10 分钟后失效。</p>
      {bindingError && <p className="form-error">{bindingError}</p>}
      {binding?.bound ? <><p>已绑定飞书账号 <code>{binding.subject_id?.slice(0, 12)}…</code></p><Button variant="danger" onClick={() => void revokeBinding()} disabled={bindingBusy}>解除绑定</Button></> : <>
        <div className="action-row">
          <Button variant="primary" onClick={() => void createBindingCode()} disabled={bindingBusy}>{bindingBusy ? '处理中…' : '生成绑定码'}</Button>
          <Button onClick={() => void startOAuth()} disabled={bindingBusy}>{bindingBusy ? '处理中…' : '生成扫码绑定二维码'}</Button>
          {bindingCode && <code aria-label="飞书绑定码">{bindingCode}</code>}
        </div>
        {oauth && <div style={{ marginTop: 12, maxWidth: 351 }}><div style={{ background: '#fff', border: '1px solid #d9d9d9', borderRadius: 8, padding: 10 }}>{oauth.qr_svg ? <div dangerouslySetInnerHTML={{ __html: oauth.qr_svg }} /> : oauth.qr_png ? <img src={oauth.qr_png} alt="飞书绑定二维码" style={{ display: 'block', width: '100%', height: 'auto' }} /> : null}</div><p>{oauthMessage}</p><a href={oauth.authorization_url} target="_blank" rel="noreferrer">在飞书中打开授权页</a></div>}
        {!oauth && oauthMessage && <p>{oauthMessage}</p>}
      </>}
    </Card>

    <Card>
      <h2>修改密码</h2>
      <form className="form-stack" onSubmit={changePassword}>
        <label>当前密码<input type="password" value={oldPassword} onChange={(event) => setOldPassword(event.target.value)} autoComplete="current-password" minLength={8} required /></label>
        <label>新密码<input type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} autoComplete="new-password" minLength={8} required /></label>
        {message && <p>{message}</p>}
        {error && <p className="form-error">{error}</p>}
        <Button variant="primary" type="submit" disabled={busy}>{busy ? '保存中…' : '修改密码'}</Button>
      </form>
    </Card>

    {user?.role === 'admin' && <Card><h2>管理员</h2><p>账号管理与业务指引配置分开控制。</p><Link to="/users"><Button>打开用户管理</Button></Link></Card>}
  </>
}
