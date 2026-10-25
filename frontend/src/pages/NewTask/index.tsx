import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../../api/endpoints'
import { invalidateQuery, useAllTaskDocuments, useCapabilities, useGuideSettings, useSealTaskMutation, useTask, useUploadTaskMutation } from '../../api/hooks'
import { saveBlob } from '../../api/client'
import { Button, Card, Select, Spinner, StatusBadge } from '../../components/ui'
import type { TaskDocument, UploadReceipt } from '../../types'

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
type DirectoryFile = File & { webkitRelativePath?: string }
type FileIssue = { file: File; message: string }

const asId = (file: File) => `${file.name}:${file.size}:${file.lastModified}`
const manifestKey = (name: string, size?: number) => `${name.toLowerCase()}|${size ?? ''}`

function validateFiles(files: File[], maxBytes?: number): { accepted: File[]; issues: FileIssue[] } {
  const accepted: File[] = []
  const issues: FileIssue[] = []
  const seen = new Set<string>()
  for (const file of files) {
    const key = file.name.toLowerCase()
    if (!/\.docx$/i.test(file.name) || (file.type && file.type !== DOCX && file.type !== 'application/octet-stream')) issues.push({ file, message: '只支持 DOCX 文件。' })
    else if (!file.size) issues.push({ file, message: '空文件无法上传。' })
    else if (maxBytes && file.size > maxBytes) issues.push({ file, message: `文件超过 ${Math.round(maxBytes / 1024 / 1024)} MB 限制。` })
    else if (seen.has(key)) issues.push({ file, message: '同一批次中存在同名文件。' })
    else { seen.add(key); accepted.push(file) }
  }
  return { accepted, issues }
}

function csvEscape(value: unknown): string {
  const text = String(value ?? '')
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

export function NewTaskPage() {
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const directoryRef = useRef<HTMLInputElement>(null)
  const replaceInputRef = useRef<HTMLInputElement>(null)
  const replaceTargetRef = useRef<string | undefined>(undefined)
  const [searchParams] = useSearchParams()
  const recoveryTaskId = searchParams.get('taskId') || undefined
  const capabilities = useCapabilities()
  const guide = useGuideSettings()
  const recoveryTask = useTask(recoveryTaskId)
  const recoveryDocuments = useAllTaskDocuments(recoveryTaskId)
  const uploadMutation = useUploadTaskMutation()
  const sealMutation = useSealTaskMutation()
  const [name, setName] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [issues, setIssues] = useState<FileIssue[]>([])
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [progress, setProgress] = useState(0)
  const [error, setError] = useState('')
  const [taskId, setTaskId] = useState<string>()
  const [serverItems, setServerItems] = useState<TaskDocument[]>([])
  const [clientIds, setClientIds] = useState<Record<string, string>>({})
  const [recoveryLoaded, setRecoveryLoaded] = useState(false)
  const [replaceName, setReplaceName] = useState<string>()
  const [fileQuery, setFileQuery] = useState('')
  const [fileFilter, setFileFilter] = useState<'all' | 'accepted' | 'issue'>('all')
  const [filePage, setFilePage] = useState(1)
  const maxBytes = capabilities.data?.upload_limits?.max_file_bytes
  const maxRequestFiles = capabilities.data?.upload_limits?.max_request_files || 20
  const maxRequestBytes = capabilities.data?.upload_limits?.max_request_bytes
  const recoveryItems = useMemo(() => recoveryDocuments.data || [], [recoveryDocuments.data])
  const recoveryIds = Object.fromEntries(recoveryItems.filter((item) => item.client_id).map((item) => [manifestKey(item.name, item.size), item.client_id as string]))
  const visibleFiles = useMemo(() => {
    const query = fileQuery.trim().toLowerCase()
    const issueByName = new Map(issues.map((issue) => [issue.file.name.toLowerCase(), issue.message]))
    const rows = [...files.map((file) => ({ file, issue: issueByName.get(file.name.toLowerCase()) })), ...issues.filter(({ file }) => !files.some((candidate) => candidate.name.toLowerCase() === file.name.toLowerCase())).map(({ file, message }) => ({ file, issue: message }))]
    const filtered = rows.filter((row) => (!query || row.file.name.toLowerCase().includes(query)) && (fileFilter === 'all' || (fileFilter === 'issue' ? Boolean(row.issue) : !row.issue)))
    const pageSize = 10
    const pages = Math.max(1, Math.ceil(filtered.length / pageSize))
    return { rows: filtered.slice((Math.min(filePage, pages) - 1) * pageSize, Math.min(filePage, pages) * pageSize), total: filtered.length, pages }
  }, [fileFilter, filePage, fileQuery, files, issues])

  useEffect(() => {
    if (!recoveryTaskId || !recoveryTask.data || !recoveryDocuments.data || recoveryLoaded) return
    setTaskId(recoveryTaskId)
    setName(recoveryTask.data.name)
    setServerItems(recoveryItems)
    setRecoveryLoaded(true)
  }, [recoveryDocuments.data, recoveryItems, recoveryLoaded, recoveryTask.data, recoveryTaskId])

  const addFiles = (incoming: File[]) => {
    const result = validateFiles(incoming, maxBytes)
    const existingNames = new Set(files.map((file) => file.name.toLowerCase()))
    const duplicateIssues = result.accepted.filter((file) => existingNames.has(file.name.toLowerCase())).map((file) => ({ file, message: '清单中已有同名文件，请先移除或替换。' }))
    const additions = result.accepted.filter((file) => !existingNames.has(file.name.toLowerCase()))
    setFiles((current) => [...current, ...additions.filter((file) => !current.some((item) => item.name.toLowerCase() === file.name.toLowerCase()))])
    setClientIds((current) => Object.fromEntries(additions.map((file) => [file.name.toLowerCase(), recoveryIds[manifestKey(file.name, file.size)] || current[file.name.toLowerCase()] || asId(file)]).concat(Object.entries(current))))
    const changedNames = new Set([...result.issues.map((issue) => issue.file), ...duplicateIssues.map((issue) => issue.file), ...additions].map((file) => file.name.toLowerCase()))
    setIssues((current) => [...current.filter((issue) => !changedNames.has(issue.file.name.toLowerCase())), ...result.issues, ...duplicateIssues])
    setFilePage(1)
    setError('')
  }

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!name.trim() && !taskId) { setError('请填写任务名称。'); return }
    if (!files.length) { setError('请至少选择一个可上传的 DOCX 文件。'); return }
    if (!taskId && (guide.error || !guide.data?.current?.id)) { setError('当前指引不可用，请先在指引配置中完成解析或启用。'); return }
    setBusy(true); setError(''); setProgress(0)
    try {
      const uploadIds = files.map((file) => clientIds[file.name.toLowerCase()] || asId(file))
      const created = taskId
        ? await api.task(taskId)
        : await api.createTask({ name: name.trim(), engine_id: 'recall_first', guide_version_id: guide.data?.current?.id, files: files.map((file, index) => ({ client_id: uploadIds[index], name: file.name, size: file.size })) }, crypto.randomUUID())
      setTaskId(created.id)
      const chunks: Array<{ files: File[]; ids: string[] }> = []
      let chunkFiles: File[] = []; let chunkIds: string[] = []; let chunkBytes = 0
      files.forEach((file, index) => {
        if (chunkFiles.length >= maxRequestFiles || Boolean(maxRequestBytes && chunkFiles.length && chunkBytes + file.size > maxRequestBytes)) {
          chunks.push({ files: chunkFiles, ids: chunkIds }); chunkFiles = []; chunkIds = []; chunkBytes = 0
        }
        chunkFiles.push(file); chunkIds.push(uploadIds[index]); chunkBytes += file.size
      })
      if (chunkFiles.length) chunks.push({ files: chunkFiles, ids: chunkIds })
      const totalBytes = files.reduce((sum, file) => sum + file.size, 0)
      let uploadedBytes = 0
      const receipts: UploadReceipt[] = []
      for (const part of chunks) {
        const uploaded = await uploadMutation.mutateAsync({ id: created.id, files: part.files, clientIds: part.ids, onProgress: (loaded, total) => setProgress(totalBytes ? (uploadedBytes + (total ? loaded / total * part.files.reduce((sum, file) => sum + file.size, 0) : loaded)) / totalBytes * 100 : 0) })
        receipts.push(...(uploaded.receipts || []))
        uploadedBytes += part.files.reduce((sum, file) => sum + file.size, 0)
        setProgress(totalBytes ? uploadedBytes / totalBytes * 100 : 100)
      }
      const items: TaskDocument[] = receipts.map((receipt) => ({
        client_id: receipt.client_id,
        name: files.find((file) => (clientIds[file.name.toLowerCase()] || asId(file)) === receipt.client_id)?.name || receipt.client_id,
        upload_status: receipt.status === 'accepted' || receipt.status === 'already_accepted' ? 'accepted' : 'rejected',
        job_status: receipt.status,
        document_id: receipt.document_id,
        batch_id: receipt.batch_id,
        error_code: receipt.error_code,
      }))
      setServerItems(items)
      const rejected = receipts.filter((receipt) => receipt.status !== 'accepted' && receipt.status !== 'already_accepted')
      if (rejected.length) {
        const rejectedIds = new Set(rejected.map((receipt) => receipt.client_id))
        setFiles((current) => current.filter((file) => rejectedIds.has(clientIds[file.name.toLowerCase()] || asId(file))))
        setError(`${rejected.length} 个文件未接收。请修正后重新选择文件，再从此页补传。`)
        return
      }
      if (!taskId) await sealMutation.mutateAsync(created.id)
      invalidateQuery('tasks:'); invalidateQuery(`task:${created.id}`)
      navigate(`/tasks/${created.id}`)
    } catch (nextError) { setError(nextError instanceof Error ? nextError.message : '任务创建或上传未完成。') }
    finally { setBusy(false) }
  }

  const clearFile = (fileName: string) => {
    setFiles((current) => current.filter((file) => file.name !== fileName))
    setIssues((current) => current.filter((issue) => issue.file.name !== fileName))
    setClientIds((current) => { const next = { ...current }; delete next[fileName.toLowerCase()]; return next })
  }
  const clearAll = () => { if (!busy) { setFiles([]); setClientIds({}); setIssues([]); setServerItems([]); setFilePage(1); setError('') } }
  const replaceFile = (file: File) => {
    const targetName = replaceName || replaceTargetRef.current
    if (!targetName) return
    const result = validateFiles([file], maxBytes)
    const oldName = targetName
    const oldFile = files.find((item) => item.name === oldName)
    const replacementIssue = result.issues[0] || (files.some((item) => item.name !== oldName && item.name.toLowerCase() === file.name.toLowerCase()) ? { file, message: '清单中已有同名文件，请先移除该文件。' } : undefined)
    if (replacementIssue) {
      setFiles((current) => current.filter((item) => item.name !== oldName))
      setClientIds((current) => { const next = { ...current }; delete next[oldName.toLowerCase()]; return next })
      setIssues((current) => [...current.filter((issue) => issue.file.name.toLowerCase() !== oldName.toLowerCase()), replacementIssue])
      replaceTargetRef.current = undefined; setReplaceName(undefined); setFilePage(1); setError('')
      return
    }
    setFiles((current) => current.some((item) => item.name === oldName) ? current.map((item) => item.name === oldName ? file : item) : [...current, file])
    setIssues((current) => current.filter((issue) => issue.file.name !== oldName))
    setClientIds((current) => { const next = { ...current }; delete next[oldName.toLowerCase()]; next[file.name.toLowerCase()] = recoveryIds[manifestKey(file.name, file.size)] || (oldFile && oldFile.name === file.name && oldFile.size === file.size ? current[oldName.toLowerCase()] : asId(file)); return next })
    replaceTargetRef.current = undefined; setReplaceName(undefined); setFilePage(1); setError('')
  }
  const exportPending = () => {
    const pending = recoveryItems.filter((item) => item.upload_status !== 'accepted')
    const rows = [['文件名', '大小(字节)', '状态'], ...pending.map((item) => [item.name, item.size || 0, item.upload_status === 'rejected' ? '接收失败' : '待上传'])]
    const csv = `\ufeff${rows.map((row) => row.map(csvEscape).join(',')).join('\r\n')}`
    saveBlob(new Blob([csv], { type: 'text/csv;charset=utf-8' }), `${name || '任务'}_待补传清单.csv`)
  }
  const onInput = (event: React.ChangeEvent<HTMLInputElement>) => { addFiles(Array.from(event.target.files || [])); event.target.value = '' }
  const backTo = taskId ? `/tasks/${taskId}` : '/tasks'

  return <>
    <div className="page-heading"><div><h1>{taskId ? '补传合同' : '新建任务'}</h1><p>{taskId ? '为已有任务补传尚未接收的合同，上传完成后任务会继续处理。' : '上传真实合同后，服务端会绑定当前指引并创建持久任务。'}</p></div><Link to={backTo}><Button>返回任务</Button></Link></div>
    <Card><h2>当前指引</h2>{guide.loading ? <Spinner /> : guide.error && !taskId ? <p className="form-error">当前指引读取失败：{guide.error instanceof Error ? guide.error.message : '未知错误'}</p> : <p>{guide.data?.current?.filename || '沿用任务指引快照'} {!taskId && <StatusBadge value={guide.data?.current?.status} />} <span className="muted">版本 {taskId ? recoveryTask.data?.guide_snapshot?.version_id || '—' : guide.data?.current?.id || '—'}</span></p>}<p className="muted">任务创建后会固定这个指引版本，补传不会切换任务指引。</p></Card>
    <Card><form className="form-stack" onSubmit={submit}>
      <label>任务名称<input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：四季度合同修订" disabled={Boolean(taskId)} /></label>
      <div><span className="muted">合同文件</span><div className={`empty-state dropzone${dragging ? ' is-dragging' : ''}`} onDragOver={(event) => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); addFiles(Array.from(event.dataTransfer.files)) }}><p>拖拽 DOCX 文件到这里</p><Button type="button" onClick={() => inputRef.current?.click()} disabled={busy}>选择文件</Button><Button type="button" onClick={() => directoryRef.current?.click()} disabled={busy}>选择文件夹</Button><input ref={inputRef} type="file" accept={`.docx,${DOCX}`} multiple hidden onChange={onInput} /><input ref={directoryRef} type="file" multiple hidden onChange={onInput} {...{ webkitdirectory: '', directory: '' }} /><input ref={replaceInputRef} type="file" accept={`.docx,${DOCX}`} hidden onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ''; if (file) replaceFile(file) }} /></div></div>
      {(files.length > 0 || issues.length > 0) && <div className="upload-manifest"><div className="upload-list-heading"><div><p className="muted">文件清单</p><div className="inline-kpis"><span className="inline-kpi"><b>{files.length + issues.length}</b>文件总数</span><span className="inline-kpi"><b>{files.reduce((sum, file) => sum + file.size, 0)}</b>总大小（字节）</span><span className="inline-kpi"><b>{files.length}</b>可接收</span><span className="inline-kpi"><b>{issues.length}</b>异常</span></div></div><Button type="button" variant="quiet" onClick={clearAll} disabled={busy}>清空清单</Button></div><div className="upload-list-toolbar"><input type="search" value={fileQuery} onChange={(event) => { setFileQuery(event.target.value); setFilePage(1) }} placeholder="搜索当前待提交文件" aria-label="搜索当前待提交文件" /><Select value={fileFilter} onChange={(event) => { setFileFilter(event.target.value as 'all' | 'accepted' | 'issue'); setFilePage(1) }}><option value="all">全部文件</option><option value="accepted">可接收</option><option value="issue">异常文件</option></Select></div>{visibleFiles.rows.length ? <div className="table-scroll"><table className="data-table upload-manifest-table"><thead><tr><th>文件名</th><th>大小</th><th>状态</th><th>操作</th></tr></thead><tbody>{visibleFiles.rows.map(({ file, issue }) => <tr key={asId(file)}><td title={(file as DirectoryFile).webkitRelativePath || file.name}>{(file as DirectoryFile).webkitRelativePath || file.name}</td><td>{(file.size / 1024 / 1024).toFixed(2)} MB</td><td>{issue ? <span className="form-error">{issue}</span> : <StatusBadge value={serverItems.find((item) => item.client_id === (clientIds[file.name.toLowerCase()] || asId(file)))?.upload_status || 'accepted'} />}</td><td className="action-row"><Button type="button" variant="quiet" onClick={() => { replaceTargetRef.current = file.name; setReplaceName(file.name); replaceInputRef.current?.click() }} disabled={busy}>替换</Button><Button type="button" variant="quiet" onClick={() => clearFile(file.name)} disabled={busy}>移除</Button></td></tr>)}</tbody></table></div> : <div className="empty-state">当前清单没有匹配文件，请调整搜索或筛选。</div>}{visibleFiles.pages > 1 && <div className="upload-pagination action-row"><Button type="button" disabled={filePage <= 1} onClick={() => setFilePage((page) => page - 1)}>上一页</Button><span className="muted">第 {Math.min(filePage, visibleFiles.pages)} / {visibleFiles.pages} 页，共 {visibleFiles.total} 个文件</span><Button type="button" disabled={filePage >= visibleFiles.pages} onClick={() => setFilePage((page) => page + 1)}>下一页</Button></div>}</div>}
      {serverItems.length > 0 && <div><p className="muted">服务端接收结果</p><ul>{serverItems.map((item) => <li key={item.client_id || item.name}>{item.name}：<StatusBadge value={item.upload_status || item.job_status} /> {item.error_code || ''}</li>)}</ul></div>}
      {taskId && recoveryDocuments.data && <div className="action-row"><span className="muted">待补传 {recoveryItems.filter((item) => item.upload_status !== 'accepted').length} 份</span><Button type="button" variant="quiet" onClick={exportPending}>下载待补传 CSV</Button></div>}
      {busy && <p className="muted"><progress value={progress} max="100" /> 上传中 {Math.round(progress)}%</p>}
      {error && <p className="form-error">{error} {taskId && <Link to={backTo}>查看任务</Link>}</p>}
      <div className="action-row"><Button variant="primary" type="submit" disabled={busy || !files.length}>{busy ? '上传中…' : taskId ? '提交补传' : '创建任务并上传'}</Button></div>
    </form></Card>
  </>
}
