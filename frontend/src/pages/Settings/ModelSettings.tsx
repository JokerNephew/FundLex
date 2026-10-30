import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/endpoints'
import { useModelSettings, useModelSettingsMutation } from '../../api/hooks'
import { Button, Card, Spinner } from '../../components/ui'
import type { ModelRoleSettings, ModelSettings } from '../../types'
import { ErrorState } from '../Tasks'

type RoleForm = {
  source: 'system' | 'personal'; provider: string; model: string
  api_key: string; base_url: string; connection_id: string
}
function roleForm(value?: ModelRoleSettings): RoleForm {
  return { source: value?.source || 'system', provider: value?.source === 'personal' ? value.provider || 'openai' : 'openai',
    model: value?.source === 'personal' ? value.model || '' : '', api_key: '',
    base_url: value?.base_url || '', connection_id: value?.connection_id || '' }
}
function payload(value: RoleForm) {
  return value.source === 'system' ? { source: 'system' } : { ...value, base_url: value.provider === 'custom' ? value.base_url.trim() : '' }
}

function RoleCard({ name, role, value, onChange, providers, systemModel, disabled }: {
  name: string; role: string; value: RoleForm; onChange: (value: RoleForm) => void
  providers: ModelSettings['providers']; systemModel: string; disabled: boolean
}) {
  const [status, setStatus] = useState('')
  const [testing, setTesting] = useState(false)
  const generation = useRef(0)
  useEffect(() => { generation.current += 1; setStatus('') }, [value])
  useEffect(() => () => { generation.current += 1 }, [])
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
    if (!window.confirm('连接测试会向供应商发送一条简短请求，可能产生少量费用，不会发送合同。继续吗？')) return
    const id = ++generation.current
    setTesting(true); setStatus('正在验证连接…')
    try {
      const result = await api.testModelConnection(payload(value))
      if (id === generation.current) setStatus(result.message)
    } catch {
      if (id === generation.current) setStatus('验证失败，请检查供应商、模型、服务地址与访问密钥。')
    } finally { setTesting(false) }
  }
  const suggestions = providers.find(provider => provider.id === value.provider)?.models || []
  return <Card>
    <h2>{name}</h2>
    <p>{role === 'primary' ? '理解合同、定位条款并生成修改内容。' : '核验修改结果，检查错误和遗漏；可以使用不同的供应商和模型。'}</p>
    <div className="form-stack">
      <label>使用方式<select value={value.source} disabled={disabled} onChange={event => update('source', event.target.value)}><option value="system">使用系统默认</option><option value="personal">使用自己的模型</option></select></label>
      {value.source === 'system' ? <p className="muted">系统模型：{systemModel || '尚未配置'}</p> : <>
        <label>供应商<select value={value.provider} disabled={disabled} onChange={event => update('provider', event.target.value)}>{providers.map(provider => <option value={provider.id} key={provider.id}>{provider.label}</option>)}</select></label>
        {value.provider === 'custom' && <label>服务地址<input type="url" value={value.base_url} disabled={disabled} required placeholder="https://你的服务商地址/v1" onChange={event => update('base_url', event.target.value)} /><span className="muted">由供应商提供，仅其他兼容服务需要填写。</span></label>}
        <label>访问密钥（API Key）<input type="password" autoComplete="new-password" maxLength={4096} required={!value.connection_id} value={value.api_key} disabled={disabled} placeholder={value.connection_id ? '已保存；留空保留，填写可更换' : '粘贴供应商提供的访问密钥'} onChange={event => update('api_key', event.target.value)} /><span className="muted">在供应商控制台获取，仅供你本人使用，加密保存，不回显。</span></label>
        <label>模型<input value={value.model} list={`model-${role}-suggestions`} required disabled={disabled} placeholder="选择建议或填写供应商提供的模型名称" onChange={event => update('model', event.target.value)} /><datalist id={`model-${role}-suggestions`}>{suggestions.map(model => <option key={model} value={model} />)}</datalist><span className="muted">建议名称并不保证账户可用，请向供应商确认。</span></label>
        <Button type="button" disabled={disabled || testing} onClick={() => void test()}>{testing ? '验证中…' : '验证连接'}</Button>
        <p className="muted">将向供应商发送一条简短测试，可能产生少量费用，不发送合同。</p>
      </>}
      {status && <p role="status">{status}</p>}
    </div>
  </Card>
}

export function ModelSettingsPage() {
  const model = useModelSettings()
  const mutation = useModelSettingsMutation()
  const [primary, setPrimary] = useState<RoleForm>(roleForm())
  const [review, setReview] = useState<RoleForm>(roleForm())
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!model.data) return
    setPrimary(roleForm(model.data.primary)); setReview(roleForm(model.data.review))
  }, [model.data])
  const save = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setMessage('')
    try {
      await mutation.mutateAsync({ primary: payload(primary), review: payload(review) })
      await model.refetch()
      setMessage('配置已保存；保存不代表已验证连接，仅用于新建合同修改任务。')
    } catch { setMessage('配置无法保存，请检查供应商、模型与访问密钥，或联系管理员检查密钥存储。') }
    finally { setBusy(false) }
  }
  const reset = async () => {
    if (!window.confirm('恢复系统默认？仅影响新建任务，已创建任务不受影响。')) return
    setBusy(true)
    try { await api.resetModelSettings(); await model.refetch(); setMessage('已恢复系统默认。') }
    catch { setMessage('暂时无法恢复默认，请稍后重试。') }
    finally { setBusy(false) }
  }
  return <>
    <div className="page-heading"><div><h1>模型配置</h1><p>分别选择负责修改合同和检查结果的模型。仅影响你的新建合同修改任务；指引解析和法规生成仍用系统模型。</p></div></div>
    {model.error ? <ErrorState error={model.error} onRetry={() => void model.refetch()} /> : !model.data ? <Spinner /> : <form className="form-stack" onSubmit={event => void save(event)}>
      {model.data.config_error && <p role="alert" className="form-error">模型密钥暂时无法读取（{model.data.config_error}），请联系管理员检查加密配置。在问题修复前请勿重置或覆盖个人配置。</p>}
      {model.data.legacy_preferences && <p>旧版设置仍影响新任务：执行模型 {model.data.primary.legacy_model || model.data.primary.system_model || '系统默认'}，检查模型 {model.data.review.legacy_model || model.data.review.system_model || '系统默认'}。保存下方新配置后将替换旧设置；已创建任务不受影响。</p>}
      <RoleCard name="执行模型" role="primary" value={primary} onChange={setPrimary} providers={model.data.providers} systemModel={model.data.primary.system_model || ''} disabled={busy} />
      <Button type="button" disabled={busy} onClick={() => setReview({ ...primary })}>将执行模型配置复制给检查模型</Button>
      <RoleCard name="检查模型" role="review" value={review} onChange={setReview} providers={model.data.providers} systemModel={model.data.review.system_model || ''} disabled={busy} />
      <div className="action-row"><Button type="submit" variant="primary" disabled={busy}>{busy ? '保存中…' : '保存配置'}</Button><Button type="button" disabled={busy} onClick={() => void reset()}>恢复系统默认</Button></div>
    </form>}
    {message && <p role="status">{message}</p>}
  </>
}
