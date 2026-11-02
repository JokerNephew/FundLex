import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/endpoints'
import { useModelSettings, useModelSettingsMutation } from '../../api/hooks'
import { Button, Card } from '../../components/ui'
import type { ModelRoleSettings, ModelSettings } from '../../types'

type RoleForm = {
  source: 'system' | 'personal'; provider: string; model: string
  api_key: string; base_url: string; connection_id: string
}
type RoleKey = 'primary' | 'review'
function roleForm(value?: ModelRoleSettings): RoleForm {
  return { source: value?.source || 'system', provider: value?.source === 'personal' ? value.provider || 'openai' : 'openai',
    model: value?.source === 'personal' ? value.model || '' : '', api_key: '',
    base_url: value?.base_url || '', connection_id: value?.connection_id || '' }
}
function payload(value: RoleForm) {
  return value.source === 'system' ? { source: 'system' } : { ...value, base_url: value.provider === 'custom' ? value.base_url.trim() : '' }
}
// 后端会为已知供应商回填默认服务地址，已验证徽标只比对使用方式/供应商/模型。
function settingsKey(value?: { source?: string; provider?: string; model?: string }) {
  return value ? `${value.source || 'system'}|${value.provider || ''}|${value.model || ''}` : ''
}

function RoleCard({ name, role, saved, value, editing, verified, busy, providers, systemModel,
  onEdit, onCancel, onChange, onReset, onVerified }: {
  name: string; role: RoleKey; saved?: ModelRoleSettings; value: RoleForm; editing: boolean
  verified: boolean; busy: boolean; providers: ModelSettings['providers']; systemModel: string
  onEdit: () => void; onCancel: () => void; onChange: (value: RoleForm) => void
  onReset: () => void; onVerified: () => void
}) {
  const [status, setStatus] = useState('')
  const [testing, setTesting] = useState(false)
  const generation = useRef(0)
  useEffect(() => { generation.current += 1; setStatus('') }, [value])
  useEffect(() => () => { generation.current += 1 }, [])
  useEffect(() => { if (!editing) setStatus('') }, [editing])
  const update = (key: keyof RoleForm, next: string) => {
    if (key === 'provider' && next !== value.provider) onChange({ ...value, provider: next, base_url: '', connection_id: '', api_key: '' })
    else if (key === 'base_url') onChange({ ...value, base_url: next, connection_id: '', api_key: '' })
    else onChange({ ...value, [key]: next })
  }
  const test = async () => {
    if (!value.model.trim() || (!value.connection_id && !value.api_key.trim()) ||
        (value.provider === 'custom' && !value.base_url.trim())) {
      setStatus('请先填写模型、访问密钥和所需的服务地址。')
      return
    }
    if (!window.confirm('连接测试不会发送合同内容。继续吗？')) return
    const id = ++generation.current
    setTesting(true); setStatus('正在验证连接…')
    try {
      const result = await api.testModelConnection(payload(value))
      if (id !== generation.current) return
      if (result.ok) { setStatus(result.message || '连接验证通过。'); onVerified() }
      else setStatus(`连接验证未通过：${result.message || '请检查密钥与模型名后重试'}`)
    } catch (nextError) {
      if (id === generation.current) {
        const detail = nextError instanceof Error && nextError.message ? nextError.message : '请检查密钥与模型名后重试'
        setStatus(`连接验证未通过：${detail}`)
      }
    } finally { setTesting(false) }
  }
  const suggestions = providers.find(provider => provider.id === value.provider)?.models || []
  const retired = providers.find(provider => provider.id === value.provider)?.deprecated_models || []
  const isPersonal = saved?.source === 'personal'
  const providerLabel = providers.find(provider => provider.id === saved?.provider)?.label || saved?.provider || '—'
  const badge = !isPersonal
    ? <span className="status-badge status-badge--neutral">系统默认</span>
    : verified ? <span className="status-badge status-badge--success">自定义·已验证</span>
      : <span className="status-badge status-badge--warning">自定义·未验证</span>
  return <Card>
    <div className="model-role-head">
      <div><h2>{name}</h2><p className="muted">{role === 'primary' ? '起草合同的修改内容。' : '逐项复查修改是否正确；可以用不同供应商的模型。'}</p></div>
      {badge}
    </div>
    {editing ? <>
      <div className="form-grid">
        <label className="form-grid-full">使用方式<select value={value.source} disabled={busy} onChange={event => update('source', event.target.value)}><option value="system">使用系统默认</option><option value="personal">使用自己的模型</option></select></label>
        {value.source === 'personal' ? <>
          <label>供应商<select value={value.provider} disabled={busy} onChange={event => update('provider', event.target.value)}>{providers.map(provider => <option value={provider.id} key={provider.id}>{provider.label}</option>)}</select></label>
          <label>模型<input value={value.model} list={`model-${role}-suggestions`} required disabled={busy} placeholder="选择建议或填写供应商提供的模型名称" onChange={event => update('model', event.target.value)} /><datalist id={`model-${role}-suggestions`}>{suggestions.map(model => <option key={model} value={model} />)}</datalist></label>
          {retired.length > 0 ? <p className="muted form-grid-full model-deprecated-hint">已停用或拟停用<span aria-hidden>（灰置不可选）</span>：{retired.map(item => <span key={item.id} className="model-deprecated-item"><del>{item.id}</del> — {item.note}</span>)}</p> : null}
          {value.provider === 'custom' ? <label className="form-grid-full">服务地址<input type="url" value={value.base_url} disabled={busy} required placeholder="https://你的服务商地址/v1" onChange={event => update('base_url', event.target.value)} /></label> : null}
          <label className="form-grid-full">访问密钥（API Key）<input type="password" autoComplete="new-password" maxLength={4096} required={!value.connection_id} value={value.api_key} disabled={busy} placeholder={value.connection_id ? '已保存；留空保留，填写可更换' : '粘贴供应商提供的访问密钥'} onChange={event => update('api_key', event.target.value)} /><span className="muted">在供应商控制台获取，仅供你本人使用，加密保存，不回显。</span></label>
        </> : null}
      </div>
      <div className="model-role-actions">
        <div className="model-role-actions-row">
          <Button type="button" disabled={busy || testing || value.source !== 'personal'} onClick={() => void test()}>{testing ? '验证中…' : '验证连接'}</Button>
          <Button type="submit" variant="primary" disabled={busy || testing}>{busy ? '保存中…' : '保存'}</Button>
          <Button type="button" variant="quiet" disabled={busy || testing} onClick={onCancel}>取消</Button>
        </div>
        {status && <p role="status">{status}</p>}
        
      </div>
    </> : <>
      <dl className="fundlex-detail-grid">
        <dt>使用方式</dt><dd>{isPersonal ? '自定义' : '系统默认'}</dd>
        <dt>供应商</dt><dd>{isPersonal ? providerLabel : '由管理员统一配置'}</dd>
        <dt>模型</dt><dd>{isPersonal ? (saved?.model || '—') : '由管理员统一配置'}</dd>
        {isPersonal ? <>
          <dt>访问密钥</dt><dd>{saved?.api_key_set ? '已保存' : '未设置'}</dd>
          <dt>验证状态</dt><dd>{verified ? <span className="status-badge status-badge--success">已验证</span> : '尚未验证'}</dd>
        </> : null}
      </dl>
      {!isPersonal && !systemModel ? <p className="muted">系统模型尚未配置，请联系管理员。</p> : null}
      <div className="model-role-actions">
        <Button type="button" variant="primary" disabled={busy} onClick={onEdit}>修改配置</Button>
        {isPersonal ? <Button type="button" variant="quiet" disabled={busy} onClick={onReset}>恢复系统默认</Button> : null}
      </div>
    </>}
  </Card>
}

export function ModelSettingsPage() {
  const model = useModelSettings()
  const mutation = useModelSettingsMutation()
  const [primary, setPrimary] = useState<RoleForm>(roleForm())
  const [review, setReview] = useState<RoleForm>(roleForm())
  const [editing, setEditing] = useState<RoleKey | ''>('')
  const [verified, setVerified] = useState<Record<string, string>>({})
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!model.data) return
    setPrimary(roleForm(model.data.primary)); setReview(roleForm(model.data.review))
  }, [model.data])
  const data = model.data
  const submitPreferences = async (nextPrimary: RoleForm, nextReview: RoleForm, success: string) => {
    setBusy(true); setMessage('')
    try {
      await mutation.mutateAsync({ primary: payload(nextPrimary), review: payload(nextReview) })
      await model.refetch()
      setEditing('')
      setMessage(success)
    } catch { setMessage('配置无法保存，请检查供应商、模型与访问密钥，或联系管理员检查密钥存储。') }
    finally { setBusy(false) }
  }
  const save = (event: React.FormEvent) => {
    event.preventDefault()
    void submitPreferences(primary, review, '已保存；是否连得通，点“验证连接”确认。仅影响之后新建的任务。')
  }
  const resetRole = (role: RoleKey) => {
    if (!window.confirm('恢复系统默认？仅影响之后新建的任务。')) return
    const nextPrimary = role === 'primary' ? roleForm({ source: 'system' } as ModelRoleSettings) : primary
    const nextReview = role === 'review' ? roleForm({ source: 'system' } as ModelRoleSettings) : review
    setPrimary(nextPrimary); setReview(nextReview)
    void submitPreferences(nextPrimary, nextReview, '已恢复系统默认。')
  }
  const copyPrimaryToReview = () => {
    if (!window.confirm('把修改模型的配置复制给复核模型并保存？')) return
    const nextReview = { ...primary }
    setReview(nextReview)
    void submitPreferences(primary, nextReview, '已复制修改模型的配置到复核模型。')
  }
  const cancelEdit = (role: RoleKey) => {
    if (!data) return
    if (role === 'primary') setPrimary(roleForm(data.primary))
    else setReview(roleForm(data.review))
    setEditing('')
  }
  return <>
    <div className="page-heading"><div><h1>模型配置</h1></div></div>
    {model.error ? <div className="error-state"><span>配置暂不可用，请稍后刷新重试。</span><Button type="button" variant="quiet" onClick={() => void model.refetch()}>重试</Button></div>
      : !data ? <p className="muted">正在读取模型配置…</p> : <>
      {data.config_error && <p role="alert" className="error-state">读取模型密钥时出错，请稍后重试。</p>}
      {data.legacy_preferences && <p className="fundlex-detail-warning">这是旧版配置，再保存一次即升级。</p>}
      <form onSubmit={save}>
        <div className="model-role-grid">
          <RoleCard name="修改模型" role="primary" saved={data.primary} value={primary}
            editing={editing === 'primary'} verified={Boolean(verified.primary && verified.primary === settingsKey(data.primary))}
            busy={busy} providers={data.providers} systemModel={data.primary.system_model || ''}
            onEdit={() => setEditing('primary')} onCancel={() => cancelEdit('primary')} onChange={setPrimary}
            onReset={() => resetRole('primary')} onVerified={() => setVerified(current => ({ ...current, primary: settingsKey(primary) }))} />
          <RoleCard name="复核模型" role="review" saved={data.review} value={review}
            editing={editing === 'review'} verified={Boolean(verified.review && verified.review === settingsKey(data.review))}
            busy={busy} providers={data.providers} systemModel={data.review.system_model || ''}
            onEdit={() => setEditing('review')} onCancel={() => cancelEdit('review')} onChange={setReview}
            onReset={() => resetRole('review')} onVerified={() => setVerified(current => ({ ...current, review: settingsKey(review) }))} />
        </div>
      </form>
      <Card>
        <h2>把修改模型的配置复制给复核模型</h2>
        <div className="model-role-actions">
          <Button type="button" disabled={busy} onClick={copyPrimaryToReview}>复制并保存</Button>
        </div>
      </Card>
    </>}
    {message && <p role="status">{message}</p>}
  </>
}
