import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../../api/endpoints'
import { saveBlob } from '../../api/client'
import {
  useGuide,
  useGuideMutation,
  useGuideParseMutation,
  useGuideSettings,
  useGuideUploadMutation,
  useGuides,
} from '../../api/hooks'
import { Button, Card, Spinner, StatusBadge } from '../../components/ui'
import { ErrorState, LoadingCard } from '../Tasks'
import { CompareCard } from './CompareCard'

function guideType(guide: { built_in?: boolean }) {
  return guide.built_in ? '内置' : '自定义'
}

export function enableBlockReasonText(reason?: string | null): string {
  if (reason === 'GUIDE_NOT_CERTIFIED') return '质量检查没过，暂时不能启用'
  if (reason === 'GUIDE_NOT_PARSED') return '还没解析完（或解析失败）'
  return ''
}

export function qualificationStatusText(status?: string): string {
  return ({ certified: '可用', frozen_builtin: '内置默认', not_run: '待解析', failed: '质量未通过' } as Record<string, string>)[status || ''] || status || '—'
}

export function guideOperationLabel(key: string): string {
  return ({ replace: '修改', delete: '删除', insert: '新增', append: '新增', noop: '无需调整' } as Record<string, string>)[key] || '其他调整'
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
        <h1>指引配置</h1>
        <p>管理指引版本，决定新建任务用哪一版。</p>
      </div>
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
        <p className="muted">{guideType(current)} · {current.groups ?? '—'} 条规则</p>
        <div className="action-row">
          <Link to={`/guides/${current.id}`}><Button variant="primary">查看详情</Button></Link>
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
          <thead><tr><th>文件</th><th>状态</th><th>规则</th><th>操作</th></tr></thead>
          <tbody>{guides.data.items.map((guide) => {
            const blockReason = guide.enable_block_reason
              || (['parsed', 'released'].includes(guide.status) ? null : 'GUIDE_NOT_PARSED')
            const canEnable = !blockReason
            return <tr key={guide.id}>
              <td>
                <Link to={`/guides/${guide.id}`}>{guide.filename}</Link>
                <div className="muted">{guideType(guide)}{guide.current ? ' · 当前使用' : guide.parent_version_id ? ' · 历史版本' : ''}</div>
              </td>
              <td>
                <StatusBadge value={guide.status} />
                {(() => {
                  const notes: string[] = []
                  if (guide.issues) notes.push(`${guide.issues} 条解析问题`)
                  if (guide.review?.status === 'needs_review') notes.push('质量可疑，建议人工确认')
                  if (!canEnable && blockReason) notes.push(enableBlockReasonText(blockReason))
                  return notes.length ? <div className="muted" title={notes.join('；')}>{notes.join('；')}</div> : null
                })()}
              </td>
              <td>{guide.groups ?? '—'}</td>
              <td>
                <div className="action-row">
                  <Link to={`/guides/${guide.id}`}>查看</Link>
                  <Button variant="quiet" disabled={busy || !canEnable || guide.current}
                    title={canEnable ? '' : enableBlockReasonText(blockReason)}
                    onClick={() => void selectGuide(guide.id)}>
                    {guide.current ? '当前使用' : canEnable ? '启用' : '不可启用'}
                  </Button>
                </div>
              </td>
            </tr>
          })}</tbody>
        </table>
      </div>}
    </Card>

    <CompareCard items={guides.data?.items || []} currentId={current?.id} />

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
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const guideParseMutation = useGuideParseMutation()

  if (guide.error) return <ErrorState error={guide.error} onRetry={() => void guide.refetch()} />
  if (guide.loading && !guide.data) return <LoadingCard />
  if (!guide.data) return <div className="empty-state">指引版本不存在。</div>
  const data = guide.data
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
        <p>{data.built_in ? '内置指引' : '自定义指引'}{data.parent_version_id ? ' · 历史版本' : ''}</p>
      </div>
      <StatusBadge value={data.status} />
    </div>
    {error && <ErrorState error={error} />}

    <Card>
      <h2>解析结果</h2>
      <div className="stats-grid">
        <div><span className="muted">规则</span><strong className="stat-value">{data.groups ?? '—'}</strong></div>
        <div><span className="muted">问题数</span><strong className="stat-value">{data.issues ?? 0}</strong></div>
        <div><span className="muted">可用状态</span><strong className="stat-value">{qualificationStatusText(data.qualification_status)}</strong></div>
      </div>
      {data.enable_block_reason ? <p className="form-error">{enableBlockReasonText(data.enable_block_reason)}；重新解析会生成新版本并重新检查。</p> : null}
      {data.review?.status === 'needs_review' ?
        <p className="form-error">这版解析质量较前版下降，可启用但建议先人工确认。</p>
        : null}
      <div className="action-row">
        <Button onClick={() => void downloadSource()} disabled={data.built_in}>下载指引原件</Button>
        <Button onClick={() => void downloadRules()}>下载规则清单（JSON）</Button>
        {!data.built_in && ['uploaded', 'parse_failed', 'parsed', 'released'].includes(data.status) && <Button onClick={() => void reparse()} disabled={busy}>{busy ? '解析中…' : '重新解析'}</Button>}
      </div>
      
    </Card>

    <Card>
      <h2>解析问题</h2>
      {data.issues_detail?.error_code === 'GUIDE_VALIDATION_UNCLEAN'
        ? <p className="form-error">解析质量没过关，这一版不能启用。</p>
        : <p className="muted">{data.issues ? `共 ${data.issues} 条解析问题记录。` : '没有记录解析问题。'}</p>}
    </Card>
  </>
}
