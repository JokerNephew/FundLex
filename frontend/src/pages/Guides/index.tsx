import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../api/endpoints'
import { saveBlob } from '../../api/client'
import {
  useGuide,
  useGuideMutation,
  useGuideParseMutation,
  useGuideRuleSettings,
  useGuideRuleSettingsMutation,
  useGuideSettings,
  useGuideUploadMutation,
  useGuides,
} from '../../api/hooks'
import { Button, Card, Spinner, StatusBadge } from '../../components/ui'
import { ErrorState, LoadingCard } from '../Tasks'

function guideType(guide: { built_in?: boolean }) {
  return guide.built_in ? '内置' : '自定义'
}

export function GuidesPage() {
  const guides = useGuides({ pollMs: 10_000 })
  const settings = useGuideSettings({ pollMs: 10_000 })
  const [file, setFile] = useState<File>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const guideMutation = useGuideMutation()
  const guideUploadMutation = useGuideUploadMutation()
  const guideParseMutation = useGuideParseMutation()

  const refresh = async () => {
    await Promise.all([guides.refetch(), settings.refetch()])
  }
  const selectGuide = async (id: string | null) => {
    setBusy(true)
    setError('')
    try {
      await guideMutation.mutateAsync(id)
      await refresh()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '指引启用未完成')
    } finally {
      setBusy(false)
    }
  }
  const uploadGuide = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const result = await guideUploadMutation.mutateAsync(file)
      await guideParseMutation.mutateAsync(result.version.id)
      await refresh()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '指引上传或解析未完成')
    } finally {
      setBusy(false)
    }
  }

  const current = settings.data?.current
  return <>
    <div className="page-heading">
      <div>
        <h1>我的指引</h1>
        <p>管理自己的指引版本、启停规则组，并决定新建任务使用哪一版。任务会保存创建时的指引快照。</p>
      </div>
      <Link to="/settings"><Button>设置</Button></Link>
    </div>
    {error && <ErrorState error={error} />}

    <Card>
      <div className="page-heading">
        <div>
          <h2>当前指引</h2>
          <p className="muted">新建任务默认使用这一版；运行中的任务不受后续切换影响。</p>
        </div>
      </div>
      {settings.error ? <ErrorState error={settings.error} onRetry={() => void settings.refetch()} /> : settings.loading && !settings.data ? <Spinner /> : !current ? <div className="empty-state">当前没有可用指引。</div> : <>
        <p>{current.filename} <StatusBadge value={current.status} /></p>
        <p className="muted">版本 {current.id} · {guideType(current)} · 规则组 {current.groups ?? '—'}</p>
        <div className="action-row">
          <Link to={`/guides/${current.id}`}><Button variant="primary">查看与启停规则组</Button></Link>
          <Button disabled={busy || current.built_in} onClick={() => void selectGuide(null)}>恢复默认内置指引</Button>
        </div>
      </>}
    </Card>

    <Card>
      <div className="page-heading">
        <div>
          <h2>我的指引</h2>
          <p className="muted">上传后的版本先解析；解析完成不代表已启用，请在列表里明确启用。</p>
        </div>
        <Button onClick={() => void refresh()} disabled={guides.refreshing || busy}>{guides.refreshing ? '刷新中…' : '刷新'}</Button>
      </div>
      {guides.error ? <ErrorState error={guides.error} onRetry={() => void guides.refetch()} /> : guides.loading && !guides.data ? <Spinner /> : !guides.data?.items.length ? <div className="empty-state">当前账号还没有可用指引。</div> : <div className="table-scroll">
        <table className="data-table">
          <thead><tr><th>文件</th><th>状态</th><th>规则组</th><th>来源哈希</th><th>操作</th></tr></thead>
          <tbody>{guides.data.items.map((guide) => {
            const canEnable = ['parsed', 'released'].includes(guide.status)
            return <tr key={guide.id}>
              <td>
                <Link to={`/guides/${guide.id}`}>{guide.filename}</Link>
                <div className="muted">{guideType(guide)} · {guide.id}{guide.parent_version_id ? ` · 基于 ${guide.parent_version_id.slice(0, 12)}…` : ''}</div>
              </td>
              <td><StatusBadge value={guide.status} />{guide.issues ? <div className="form-error">{guide.issues} 个问题</div> : null}</td>
              <td>{guide.groups ?? '—'}</td>
              <td>{guide.document_sha256 ? `${guide.document_sha256.slice(0, 12)}…` : '—'}</td>
              <td>
                <div className="action-row">
                  <Link to={`/guides/${guide.id}`}><Button variant="quiet">规则组</Button></Link>
                  <Button disabled={busy || !canEnable || guide.current} onClick={() => void selectGuide(guide.id)}>
                    {guide.current ? '当前使用' : canEnable ? '启用' : '不可启用'}
                  </Button>
                </div>
              </td>
            </tr>
          })}</tbody>
        </table>
      </div>}
    </Card>

    <Card>
      <h2>上传新指引</h2>
      <p className="muted">支持与内置指引同结构的 DOCX。上传后会先解析；解析完成不代表已启用。</p>
      <div className="guide-file-picker">
        <label className="ui-button"><span>选择 DOCX 文件</span><input type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onChange={(event) => setFile(event.target.files?.[0])} /></label>
        <span className="guide-file-name" title={file?.name}>{file?.name || '尚未选择文件'}</span>
        <Button variant="primary" disabled={!file || busy} onClick={() => void uploadGuide()}>{busy ? '处理中…' : '上传并解析'}</Button>
      </div>
    </Card>
  </>
}

export function GuideDetailPage() {
  const { guideId } = useParams()
  const navigate = useNavigate()
  const guide = useGuide(guideId)
  const ruleSettings = useGuideRuleSettings(guideId)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [disabled, setDisabled] = useState<string[]>([])
  const [loadedVersion, setLoadedVersion] = useState('')
  const [dirty, setDirty] = useState(false)
  const guideParseMutation = useGuideParseMutation()
  const ruleMutation = useGuideRuleSettingsMutation()

  useEffect(() => {
    if (!ruleSettings.data) return
    if (loadedVersion === ruleSettings.data.version_id) return
    setDisabled(ruleSettings.data.disabled_rule_ids)
    setLoadedVersion(ruleSettings.data.version_id)
    setDirty(false)
  }, [loadedVersion, ruleSettings.data])

  if (guide.error) return <ErrorState error={guide.error} onRetry={() => void guide.refetch()} />
  if (guide.loading && !guide.data) return <LoadingCard />
  if (!guide.data) return <div className="empty-state">指引版本不存在。</div>
  const data = guide.data
  const canEditRules = ['parsed', 'released'].includes(data.status)
  const enabledCount = (ruleSettings.data?.rules || []).filter((rule) => !disabled.includes(rule.rule_id)).length
  const toggleRule = (ruleId: string) => {
    setMessage('')
    setDirty(true)
    setDisabled((current) => {
      if (current.includes(ruleId)) return current.filter((item) => item !== ruleId)
      if (enabledCount <= 1) return current
      return [...current, ruleId]
    })
  }
  const saveRules = async () => {
    if (!guideId) return
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await ruleMutation.mutateAsync({ id: guideId, disabled })
      setDirty(false)
      setMessage('规则组启停已保存；只影响之后新建的任务，运行中的任务仍使用创建时的快照。')
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '规则组启停保存失败')
    } finally {
      setBusy(false)
    }
  }
  const downloadSource = async () => {
    try {
      if (!guideId) return
      const blob = await api.guideSource(guideId)
      saveBlob(blob, data.filename || 'guide.docx')
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '原件下载失败')
    }
  }
  const reparse = async () => {
    if (!guideId) return
    setBusy(true)
    setError('')
    try {
      const result = await guideParseMutation.mutateAsync(guideId)
      const nextId = result?.version?.id
      if (nextId && nextId !== guideId) navigate(`/guides/${nextId}`)
      else await guide.refetch()
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '重新解析失败')
    } finally {
      setBusy(false)
    }
  }
  const downloadRules = async () => {
    try {
      const rules = await api.guideRules(data.id)
      saveBlob(new Blob([JSON.stringify(rules, null, 2)], { type: 'application/json;charset=utf-8' }), `${data.filename.replace(/\.docx$/i, '')}_rules.json`)
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : '规则读取失败')
    }
  }

  return <>
    <div className="page-heading">
      <div>
        <p><Link to="/guides">我的指引</Link> / 详情</p>
        <h1>{data.filename}</h1>
        <p>版本 {data.id} · {data.built_in ? '内置指引' : '自定义指引'}{data.parent_version_id ? ` · 基于 ${data.parent_version_id}` : ''}</p>
      </div>
      <StatusBadge value={data.status} />
    </div>
    {error && <ErrorState error={error} />}
    {message && <p role="status">{message}</p>}

    <Card>
      <h2>解析结果</h2>
      <div className="stats-grid">
        <div><span className="muted">规则组</span><strong className="stat-value">{data.groups ?? '—'}</strong></div>
        <div><span className="muted">问题数</span><strong className="stat-value">{data.issues ?? 0}</strong></div>
        <div><span className="muted">资格状态</span><strong className="stat-value">{data.qualification_status || '—'}</strong></div>
        <div><span className="muted">规则哈希</span><strong className="hash-value">{data.rules_sha256?.slice(0, 16) || '—'}</strong></div>
      </div>
      <div className="action-row">
        <Button onClick={() => void downloadSource()} disabled={data.built_in}>下载原始 DOCX</Button>
        <Button onClick={() => void downloadRules()}>下载规则 JSON</Button>
        {!data.built_in && ['uploaded', 'parse_failed', 'parsed', 'released'].includes(data.status) && <Button onClick={() => void reparse()} disabled={busy}>{busy ? '解析中…' : '重新解析'}</Button>}
      </div>
    </Card>

    <Card>
      <div className="page-heading">
        <div>
          <h2>规则组启停</h2>
          <p className="muted">关闭的规则不会在之后新建的任务中执行，并会在报告里列为“用户关闭的规则”。至少保留一条启用规则。</p>
        </div>
        <Button variant="primary" onClick={() => void saveRules()} disabled={busy || !canEditRules || !ruleSettings.data || !dirty}>{busy ? '保存中…' : '保存启停'}</Button>
      </div>
      {!canEditRules ? <div className="empty-state">指引解析完成后才能配置规则组。</div> : ruleSettings.error ? <ErrorState error={ruleSettings.error} onRetry={() => void ruleSettings.refetch()} /> : ruleSettings.loading && !ruleSettings.data ? <Spinner /> : !ruleSettings.data?.rules.length ? <div className="empty-state">该版本还没有可配置的规则组。</div> : <div className="table-scroll">
        <table className="data-table">
          <thead><tr><th>启用</th><th>规则</th><th>章节</th><th>操作统计</th></tr></thead>
          <tbody>{ruleSettings.data.rules.map((rule) => {
            const overview = data.rules_overview?.find((item) => item.rule_id === rule.rule_id)
            const operations = overview?.operations ? Object.entries(overview.operations).map(([key, value]) => `${key}: ${value}`).join(' · ') : '—'
            const checked = !disabled.includes(rule.rule_id)
            return <tr key={rule.rule_id}>
              <td><input aria-label={`启用规则 ${rule.rule_id}`} type="checkbox" checked={checked} disabled={busy || (checked && enabledCount <= 1)} onChange={() => toggleRule(rule.rule_id)} /></td>
              <td><strong>{rule.rule_id}</strong><div>{rule.title || '—'}</div></td>
              <td>{rule.section_hint || '—'}</td>
              <td>{operations}</td>
            </tr>
          })}</tbody>
        </table>
      </div>}
      <p className="muted">当前启用 {enabledCount} / {ruleSettings.data?.rules.length ?? 0} 条。关闭规则属于业务例外，不会让报告伪造为“全部完成”。</p>
    </Card>

    <Card>
      <h2>解析问题</h2>
      {Object.keys(data.issues_detail || {}).length ? <pre className="preserve">{JSON.stringify(data.issues_detail, null, 2)}</pre> : <p className="muted">服务端没有记录解析问题。</p>}
    </Card>
  </>
}
