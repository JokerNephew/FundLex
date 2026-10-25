import { createElement, useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import { Button, Card, Spinner, StatusBadge } from '../../components/ui'
import { saveBlob } from '../../api/client'
import {
  useCompareSealMutation,
  useCompareTask,
  useCompareTaskMutation,
  useCompareTasks,
  useCompareUploadMutation,
  useCompareView,
} from '../../api/hooks'
import type { ComparePair, ComparePairManifest, CompareTask } from '../../types'

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
type DirectoryFile = File & { webkitRelativePath?: string }
type PairDraft = { left?: File; right?: File }
type UploadDraft = { task: CompareTask; manifests: ComparePairManifest[]; files: PairDraft[]; next: number }

function fileName(file?: File | null): string { return String(file?.name || '').replace(/\\/g, '/').split('/').pop() || '' }
function relativePath(file: File): string {
  const raw = String((file as DirectoryFile).webkitRelativePath || '').replace(/\\/g, '/')
  return raw ? raw.split('/').filter(Boolean).slice(1).join('/') || fileName(file) : fileName(file)
}
function messageOf(error: unknown, fallback: string): string { return error instanceof Error ? error.message : fallback }
function statusLabel(status?: string): string {
  return ({ pending: '待上传', queued: '排队中', leased: '处理中', running: '处理中', succeeded: '已完成', incomplete: '覆盖不完整', failed: '失败', retry_wait: '等待重试', sealed: '已提交', uploading: '上传中', completed: '已处理' } as Record<string, string>)[status || ''] || status || '—'
}
function pairDone(pair?: ComparePair): boolean { return Boolean(pair && ['succeeded', 'incomplete'].includes(pair.status)) }

const safeTags = new Set(['article', 'blockquote', 'br', 'caption', 'col', 'colgroup', 'dd', 'div', 'dl', 'dt', 'em', 'figcaption', 'figure', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'li', 'mark', 'main', 'ol', 'p', 'pre', 'q', 'section', 'small', 'span', 'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'u', 'ul'])
const voidTags = new Set(['br', 'col', 'hr'])

function safeProps(element: Element): Record<string, string | number> {
  const props: Record<string, string | number> = {}
  for (const attribute of Array.from(element.attributes)) {
    const name = attribute.name.toLowerCase()
    if (name === 'class') props.className = attribute.value
    else if (name === 'colspan' || name === 'rowspan') props[name] = Number(attribute.value) || 1
    else if (name === 'title') props.title = attribute.value
    else if (name === 'data-block-id' || name === 'data-location') props[name] = attribute.value
  }
  return props
}

function renderCompareNode(node: Node, key: string, onDiff: (id: string) => void, activeDiffId?: string): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent
  if (node.nodeType !== Node.ELEMENT_NODE) return null
  const element = node as Element
  const tag = element.tagName.toLowerCase()
  if (!safeTags.has(tag)) return null
  const children = Array.from(element.childNodes).map((child, index) => renderCompareNode(child, `${key}-${index}`, onDiff, activeDiffId))
  const diffId = element.getAttribute('data-diff-id')
  if (diffId) {
    const backendClass = element.getAttribute('class') || ''
    const kind = backendClass.match(/compare-diff-(modify|insert|delete)/)?.[1]
    return <mark key={key} className={`compare-diff ${kind || ''} ${activeDiffId === diffId ? 'is-active' : ''}`.trim()} data-diff-id={diffId} tabIndex={0} role="button" aria-label="定位此处差异" onClick={() => onDiff(diffId)} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onDiff(diffId) } }}>{children}</mark>
  }
  const props = { key, ...safeProps(element) }
  return voidTags.has(tag) ? createElement(tag, props) : createElement(tag, props, children)
}

export function SafeCompareDocument({ html, side, activeDiffId, onDiff }: { html: string; side: 'left' | 'right'; activeDiffId?: string; onDiff: (id: string) => void }) {
  const content = useMemo(() => {
    if (typeof DOMParser === 'undefined') return []
    const parsed = new DOMParser().parseFromString(html, 'text/html')
    return Array.from(parsed.body.childNodes).map((node, index) => renderCompareNode(node, `${side}-${index}`, onDiff, activeDiffId))
  }, [activeDiffId, html, onDiff, side])
  return <article className="compare-pane" aria-label={side === 'left' ? '原版合同' : '对比版合同'} tabIndex={0}>{content.length ? content : <p className="compare-empty">暂无可呈现内容。</p>}</article>
}

function PairInput({ pair, index, onChange, onRemove }: { pair: PairDraft; index: number; onChange: (side: 'left' | 'right', file?: File) => void; onRemove: () => void }) {
  return <div className="compare-pair-input"><div className="compare-pair-head"><strong>第 {index + 1} 组</strong><Button type="button" variant="quiet" disabled={index === 0} onClick={onRemove}>移除</Button></div><div className="compare-side-inputs"><label><span>原版（基准）</span><input type="file" accept={`.docx,${DOCX}`} onChange={(event) => onChange('left', event.target.files?.[0])} /></label><label><span>对比版（修订）</span><input type="file" accept={`.docx,${DOCX}`} onChange={(event) => onChange('right', event.target.files?.[0])} /></label></div><p className="muted compare-file-label">{[pair.left, pair.right].map(fileName).filter(Boolean).join(' / ') || '尚未选择文件'}</p></div>
}

function taskDescription(task: CompareTask): string {
  const pairs = task.pairs || []
  const done = pairs.filter(pairDone).length
  const differences = pairs.reduce((total, pair) => total + (pair.summary?.total || 0), 0)
  return `${done}/${task.total || pairs.length || 0} 组完成 · ${differences ? `${differences} 处差异` : '差异待读取'}`
}

export function ComparePage() {
  const tasks = useCompareTasks()
  const [selectedTaskId, setSelectedTaskId] = useState<string>()
  const task = useCompareTask(selectedTaskId, { pollMs: 2500 })
  const [pairs, setPairs] = useState<PairDraft[]>([{}])
  const [taskName, setTaskName] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [uploadDraft, setUploadDraft] = useState<UploadDraft>()
  const [selectedPairId, setSelectedPairId] = useState<string>()
  const [diffType, setDiffType] = useState('')
  const [diffIndex, setDiffIndex] = useState(0)
  const [activeOnly, setActiveOnly] = useState(false)
  const [mobileSide, setMobileSide] = useState<'left' | 'right'>('left')
  const [folderFiles, setFolderFiles] = useState<{ left: File[]; right: File[] }>({ left: [], right: [] })
  const createMutation = useCompareTaskMutation()
  const uploadMutation = useCompareUploadMutation()
  const sealMutation = useCompareSealMutation()
  const selectedPair = task.data?.pairs?.find((pair) => pair.id === selectedPairId)
  const selectedPairIndex = task.data?.pairs?.findIndex((pair) => pair.id === selectedPairId) ?? -1
  const viewQuery = useCompareView(selectedPairId && pairDone(selectedPair) ? selectedPairId : undefined)
  const view = viewQuery.data
  const leftRef = useRef<HTMLDivElement>(null)
  const rightRef = useRef<HTMLDivElement>(null)
  const columnsRef = useRef<HTMLDivElement>(null)
  const [lines, setLines] = useState<Array<{ id: string; x1: number; y1: number; x2: number; y2: number }>>([])
  const [lineSize, setLineSize] = useState({ width: 100, height: 100 })

  useEffect(() => {
    if (!selectedTaskId && tasks.data?.items[0]) setSelectedTaskId(tasks.data.items[0].id)
  }, [selectedTaskId, tasks.data?.items])
  useEffect(() => {
    const first = task.data?.pairs?.find(pairDone)
    if (!selectedPairId || !task.data?.pairs?.some((pair) => pair.id === selectedPairId)) setSelectedPairId(first?.id)
  }, [selectedPairId, task.data?.pairs])
  const visibleDiffs = useMemo(() => {
    const all = view?.diffs || []
    return diffType ? all.filter((item) => item.type === diffType) : all
  }, [diffType, view?.diffs])
  const activeDiff = visibleDiffs[diffIndex]
  const focusDiff = useCallback((index: number) => {
    if (!visibleDiffs.length) return
    const nextIndex = (index + visibleDiffs.length) % visibleDiffs.length
    setDiffIndex(nextIndex)
    const id = visibleDiffs[nextIndex].id
    for (const pane of [leftRef.current, rightRef.current]) pane?.querySelector(`[data-diff-id="${CSS.escape(id)}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [visibleDiffs])
  useEffect(() => { setDiffIndex(0) }, [diffType, view?.pair.id])

  const drawLines = useCallback(() => {
    if (!columnsRef.current || !leftRef.current || !rightRef.current || !view || window.matchMedia('(max-width: 760px)').matches) { setLines([]); return }
    const root = columnsRef.current.getBoundingClientRect()
    setLineSize({ width: root.width || 100, height: root.height || 100 })
    const left = leftRef.current.getBoundingClientRect()
    const right = rightRef.current.getBoundingClientRect()
    const active = activeDiff?.id
    const next = (view.diffs || []).flatMap((diff) => {
      if (activeOnly && diff.id !== active) return []
      const leftMark = leftRef.current?.querySelector(`[data-diff-id="${CSS.escape(diff.id)}"]`)
      const rightMark = rightRef.current?.querySelector(`[data-diff-id="${CSS.escape(diff.id)}"]`)
      if (!leftMark || !rightMark) return []
      const a = leftMark.getBoundingClientRect(); const b = rightMark.getBoundingClientRect()
      if (a.bottom < left.top && b.bottom < right.top) return []
      if (a.top > left.bottom && b.top > right.bottom) return []
      const x1 = a.right - root.left; const x2 = b.left - root.left
      return [{ id: diff.id, x1, y1: a.top + a.height / 2 - root.top, x2, y2: b.top + b.height / 2 - root.top }]
    })
    setLines(next)
  }, [activeDiff?.id, activeOnly, view])
  useEffect(() => { const frame = requestAnimationFrame(drawLines); return () => cancelAnimationFrame(frame) }, [drawLines, view?.left.html, view?.right.html, diffIndex])
  useEffect(() => { const onResize = () => drawLines(); window.addEventListener('resize', onResize); return () => window.removeEventListener('resize', onResize) }, [drawLines])

  const syncScroll = (source: HTMLElement) => {
    const target = source === leftRef.current ? rightRef.current : leftRef.current
    if (!target || window.matchMedia('(max-width: 760px)').matches) { drawLines(); return }
    const sourceMax = Math.max(0, source.scrollHeight - source.clientHeight)
    const targetMax = Math.max(0, target.scrollHeight - target.clientHeight)
    target.scrollTop = sourceMax ? source.scrollTop / sourceMax * targetMax : 0
    drawLines()
  }

  const selectFiles = (index: number, side: 'left' | 'right', file?: File) => setPairs((current) => current.map((pair, itemIndex) => itemIndex === index ? { ...pair, [side]: file } : pair))
  const applyFolder = (side: 'left' | 'right', event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || []).filter((file) => /\.docx$/i.test(file.name)).sort((a, b) => relativePath(a).localeCompare(relativePath(b)))
    if (!files.length) return
    const nextFolders = { ...folderFiles, [side]: files }
    setFolderFiles(nextFolders)
    const left = nextFolders.left; const right = nextFolders.right
    if (!left.length || !right.length) return
    const rightMap = new Map(right.map((file) => [relativePath(file), file])); const used = new Set<File>()
    const next: PairDraft[] = left.map((file) => { const match = rightMap.get(relativePath(file)); if (match) used.add(match); return { left: file, right: match } })
    for (const file of right) if (!used.has(file)) next.push({ left: undefined, right: file })
    setPairs(next)
    setMessage(`已按相对路径配对 ${next.filter((pair) => pair.left && pair.right).length} 组；${next.filter((pair) => !pair.left || !pair.right).length} 个文件未配对。`)
  }

  const continueUpload = async (draft: UploadDraft) => {
    setError(''); setMessage('')
    try {
      for (let index = draft.next; index < draft.files.length; index += 1) {
        const files = draft.files[index]; const manifest = draft.manifests[index]
        if (!files.left || !files.right) throw new Error(`第 ${index + 1} 组缺少原版或对比版文件。`)
        setMessage(`正在上传第 ${index + 1} / ${draft.files.length} 组…`)
        const result = await uploadMutation.mutateAsync({ id: draft.task.id, files: [files.left, files.right], clientIds: [manifest.left.client_id, manifest.right.client_id] })
        const receipts = result.receipts || []
        if (receipts.some((receipt) => !['accepted', 'already_accepted'].includes(receipt.status))) throw new Error(`第 ${index + 1} 组上传未完成。`)
        draft.next = index + 1; setUploadDraft({ ...draft })
      }
      await sealMutation.mutateAsync(draft.task.id)
      setUploadDraft(undefined); setCreateOpen(false); setMessage('已提交，对比任务正在处理。'); setSelectedTaskId(draft.task.id); await tasks.refetch(); await task.refetch()
    } catch (nextError) { setError(`上传中断：${messageOf(nextError, '文件上传未完成')}。已完成的文件已保留，可继续上传。`) }
  }

  const createTask = async () => {
    if (!pairs.length || pairs.some((pair) => !pair.left || !pair.right)) { setError('每组都需要同时选择原版和对比版 DOCX。'); return }
    const manifests = pairs.map((pair, index) => ({ client_pair_id: `P${index + 1}`, label: `合同 ${index + 1}`, left: { client_id: `L${index}-${crypto.randomUUID()}`, name: fileName(pair.left), size: pair.left?.size || 0 }, right: { client_id: `R${index}-${crypto.randomUUID()}`, name: fileName(pair.right), size: pair.right?.size || 0 } }))
    try {
      const created = await createMutation.mutateAsync({ name: taskName.trim() || '合同对比', pairs: manifests, key: `compare-${crypto.randomUUID()}` })
      const draft = { task: created, manifests, files: pairs, next: 0 }; setUploadDraft(draft); await continueUpload(draft)
    } catch (nextError) { setError(`创建任务失败：${messageOf(nextError, '对比任务创建未完成')}`) }
  }

  const resetCreate = () => { setCreateOpen(true); setError(''); setMessage(''); setPairs([{}]); setFolderFiles({ left: [], right: [] }); setTaskName(''); setUploadDraft(undefined) }
  const selectPairDiff = (id: string) => { const index = visibleDiffs.findIndex((diff) => diff.id === id); if (index >= 0) focusDiff(index) }
  const movePair = (direction: -1 | 1) => {
    const pairItems = task.data?.pairs || []
    const currentIndex = pairItems.findIndex((pair) => pair.id === selectedPairId)
    const next = pairItems[currentIndex + direction]
    if (next) {
      setSelectedPairId(next.id)
      setMobileSide('left')
    }
  }
  const downloadReport = () => { if (!view) return; saveBlob(new Blob([JSON.stringify(view, null, 2)], { type: 'application/json;charset=utf-8' }), `${task.data?.name || '合同对比'}-差异报告.json`) }

  return <div className="fundlex-compare-page">
    <div className="page-heading"><div><h1>合同对比</h1><p>按“原版 → 对比版”阅读两份 DOCX 的正文与普通表格差异，结果只代表已覆盖内容。</p></div><div className="action-row"><Button type="button" onClick={() => void tasks.refetch()}>刷新</Button><Button type="button" variant="primary" onClick={resetCreate}>＋ 新建对比任务</Button></div></div>
    {error && <div className="error-state" role="alert">{error}</div>}{message && <div className="fundlex-message" role="status">{message}</div>}
    <Card className="compare-task-card"><div className="page-heading"><div><h2>我的对比任务</h2><p className="muted">多组任务会分别展示处理状态，失败或覆盖不完整的分组保留人工复核提示。</p></div></div>{tasks.error ? <div className="error-state">读取对比任务失败：{messageOf(tasks.error, '服务暂时不可用')}</div> : tasks.loading && !tasks.data ? <Spinner /> : tasks.data?.items.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>任务</th><th>分组</th><th>状态</th><th>结果</th><th /></tr></thead><tbody>{tasks.data.items.map((item) => <tr key={item.id}><td><button type="button" className="table-link" onClick={() => setSelectedTaskId(item.id)}>{item.name}</button></td><td>{item.total || item.pairs?.length || 0}</td><td><StatusBadge value={statusLabel(item.status)} /></td><td>{taskDescription(item)}</td><td><Button type="button" onClick={() => setSelectedTaskId(item.id)}>查看</Button></td></tr>)}</tbody></table></div> : <div className="empty-state"><strong>还没有合同对比任务</strong><p>创建一组或多组左右合同开始比较。</p></div>}</Card>
    {createOpen && <Card className="compare-create"><div className="compare-create-intro"><div><h2>新建对比任务</h2><p className="muted">先选择原版（基准文本），再选择对比版（修订文本）。</p></div><span className="compare-step">1 / 2 · 准备文件</span></div><label className="compare-task-name">任务名称<input value={taskName} maxLength={200} onChange={(event) => setTaskName(event.target.value)} placeholder="例如：法务与产品部合同差异" /></label><div className="compare-folder-actions"><label className="ui-button"><span>选择原版文件夹</span><input type="file" {...{ webkitdirectory: '', directory: '' } as Record<string, string>} multiple hidden onChange={(event) => applyFolder('left', event)} /></label><label className="ui-button"><span>选择对比版文件夹</span><input type="file" {...{ webkitdirectory: '', directory: '' } as Record<string, string>} multiple hidden onChange={(event) => applyFolder('right', event)} /></label><span className="muted">按相同相对路径配对；未配对文件可以手工补齐。</span></div>{pairs.map((pair, index) => <PairInput key={index} pair={pair} index={index} onChange={(side, file) => selectFiles(index, side, file)} onRemove={() => setPairs((current) => current.length > 1 ? current.filter((_, itemIndex) => itemIndex !== index) : current)} />)}<div className="action-row"><Button type="button" onClick={() => setPairs((current) => [...current, {}])}>＋ 添加一组</Button><Button type="button" variant="primary" disabled={createMutation.isPending || uploadMutation.isPending || sealMutation.isPending} onClick={() => void (uploadDraft ? continueUpload(uploadDraft) : createTask())}>{uploadDraft ? '继续上传' : '开始上传并对比'}</Button></div></Card>}
    {selectedTaskId && <Card className="compare-detail"><div className="page-heading"><div><h2>{task.data?.name || '合同对比任务'}</h2><p className="muted">{task.data ? `${statusLabel(task.data.status)} · ${task.data.pairs?.length || 0} 组` : '正在读取任务…'}</p></div><Button type="button" onClick={() => void task.refetch()} disabled={task.refreshing}>刷新状态</Button></div><div className="compare-direction-note"><span className="compare-direction-icon" aria-hidden="true">→</span><div><strong>阅读方向</strong><span>原版（基准） → 对比版（修订）</span></div><small>新增 / 删除均按此方向解释</small></div>{task.error ? <div className="error-state">读取任务失败：{messageOf(task.error, '服务暂时不可用')}</div> : task.loading && !task.data ? <Spinner /> : <div className="compare-pair-statuses">{(task.data?.pairs || []).map((pair, index) => <button type="button" className={`compare-pair-status ${pair.id === selectedPairId ? 'is-selected' : ''} ${pairDone(pair) ? 'is-done' : ''} ${pair.status === 'incomplete' ? 'is-incomplete' : ''} ${pair.status === 'failed' ? 'is-failed' : ''}`} key={pair.id} onClick={() => setSelectedPairId(pair.id)}><span className="compare-pair-number">{String(index + 1).padStart(2, '0')}</span><span className="compare-pair-main"><strong>{pair.label || `第 ${index + 1} 组`}</strong><small>{pair.left?.name || '原版未命名'} → {pair.right?.name || '对比版未命名'}</small></span><span className="compare-pair-state">{statusLabel(pair.status)}{pair.summary ? ` · ${pair.summary.total || 0} 处` : ''}</span>{pair.error_code && <span className="compare-pair-error">处理失败：{pair.error_code}</span>}</button>)}</div>}</Card>}
    {selectedPairId && <Card className="compare-viewer" data-mobile-side={mobileSide}><div className="compare-viewer-toolbar"><div className="compare-viewer-title"><div><span className="eyebrow">DIFF READER</span><strong>{view?.pair.label || selectedPair?.label || '合同对比'}</strong><p className="compare-reader-subtitle">逐处核对正文变化，点击标记或差异条目可定位段落。</p></div><div className="action-row"><Button type="button" onClick={() => movePair(-1)} disabled={selectedPairIndex <= 0}>上一组</Button><span className="compare-pair-counter">{task.data?.pairs?.length && selectedPairIndex >= 0 ? `${selectedPairIndex + 1} / ${task.data.pairs.length}` : '0 / 0'}</span><Button type="button" onClick={() => movePair(1)} disabled={!task.data?.pairs || selectedPairIndex < 0 || selectedPairIndex >= task.data.pairs.length - 1}>下一组</Button><Button type="button" onClick={() => focusDiff(diffIndex - 1)} disabled={!visibleDiffs.length}>上一处</Button><span className="compare-diff-counter">{visibleDiffs.length ? `${diffIndex + 1} / ${visibleDiffs.length}` : '0 / 0'}</span><Button type="button" onClick={() => focusDiff(diffIndex + 1)} disabled={!visibleDiffs.length}>下一处</Button><Button type="button" onClick={downloadReport} disabled={!view}>下载差异报告</Button></div></div><div className="compare-summary-row"><div className="compare-summary-stat"><span>当前结果</span><strong>{view?.summary ? `共 ${view.summary.total || 0} 处差异 · 修改 ${view.summary.modify || 0} · 新增 ${view.summary.insert || 0} · 删除 ${view.summary.delete || 0}` : '结果尚未就绪'}</strong></div><div className="compare-sync-note">双栏联动阅读</div></div>{view?.coverage?.status !== 'complete' && view?.coverage && <p className="compare-coverage is-incomplete" role="status">覆盖不完整：以下内容未纳入比较。请人工复核，不要据此确认全文无差异。{view.coverage.warnings?.length ? ` 未覆盖：${view.coverage.warnings.join('、')}` : ''}</p>}</div>{viewQuery.error ? <div className="error-state">读取结果失败：{messageOf(viewQuery.error, '结果暂时不可用')}</div> : viewQuery.loading && !view ? <Spinner label="正在读取对比结果" /> : view && <><div className="compare-reader-label"><span>合同正文</span><small>差异连线仅展示当前可见区域</small></div><div className="compare-columns-head"><span><i className="compare-side-badge">A</i><b>原版 · 基准</b><small>{view.left.name}</small></span><span className="compare-columns-arrow" aria-hidden="true">→</span><span><i className="compare-side-badge is-revised">B</i><b>对比版 · 修订</b><small>{view.right.name}</small></span></div><div className="compare-mobile-switch" role="group" aria-label="移动端阅读侧栏"><Button type="button" aria-pressed={mobileSide === 'left'} onClick={() => setMobileSide('left')}>查看原版</Button><Button type="button" aria-pressed={mobileSide === 'right'} onClick={() => setMobileSide('right')}>查看对比版</Button></div><div className="compare-columns" ref={columnsRef}><div ref={leftRef} className="compare-pane-wrap" onScroll={(event) => syncScroll(event.currentTarget)}><SafeCompareDocument html={view.left.html} side="left" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div><div className="compare-gutter" aria-hidden="true"><span>同步</span></div><div ref={rightRef} className="compare-pane-wrap" onScroll={(event) => syncScroll(event.currentTarget)}><SafeCompareDocument html={view.right.html} side="right" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div><svg className="compare-lines" aria-hidden="true" viewBox={`0 0 ${lineSize.width} ${lineSize.height}`} preserveAspectRatio="none">{lines.map((line) => <path key={line.id} d={`M ${line.x1} ${line.y1} C ${(line.x1 + line.x2) / 2} ${line.y1}, ${(line.x1 + line.x2) / 2} ${line.y2}, ${line.x2} ${line.y2}`} className={line.id === activeDiff?.id ? 'active' : ''} />)}</svg></div><div className="compare-diff-toolbar"><div className="action-row"><Button type="button" aria-pressed={activeOnly} onClick={() => setActiveOnly((value) => !value)}>仅显示当前连线</Button><label className="muted">类型 <select value={diffType} onChange={(event) => setDiffType(event.target.value)}><option value="">全部</option><option value="modify">修改</option><option value="insert">新增</option><option value="delete">删除</option></select></label></div></div><div className="compare-diff-list">{visibleDiffs.length ? visibleDiffs.map((diff, index) => <button type="button" className={`compare-diff-item ${index === diffIndex ? 'is-active' : ''}`} key={diff.id} onClick={() => focusDiff(index)}><span>{index + 1}</span><strong>{diff.type === 'modify' ? '修改' : diff.type === 'insert' ? '新增' : '删除'}</strong><span>{diff.section || '正文'} · {diff.left?.text || ''}{diff.right?.text ? ` → ${diff.right.text}` : ''}</span></button>) : <p className="empty-state">{view.coverage?.status === 'complete' ? '两份合同没有文字差异。' : '已覆盖范围内没有发现文字差异，无法确认全文无差异。'}</p>}</div></>}</Card>}
  </div>
}
