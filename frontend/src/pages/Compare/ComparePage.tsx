import { createElement, useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type CSSProperties, type ReactNode, type RefObject } from 'react'
import { Button, Card, Spinner, StatusBadge } from '../../components/ui'
import {
  useCompareSealMutation,
  useCompareTask,
  useCompareTaskMutation,
  useCompareTasks,
  useCompareUploadMutation,
  useCompareView,
  refetchCompareTask,
} from '../../api/hooks'
import type { CompareDiff, ComparePair, ComparePairManifest, CompareTask, CompareView } from '../../types'

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
type DirectoryFile = File & { webkitRelativePath?: string }
type PairDraft = { left?: File; right?: File }
type UploadDraft = { task: CompareTask; manifests: ComparePairManifest[]; files: PairDraft[]; next: number }

function useMediaQuery(query: string): boolean {
  const read = () => typeof window !== 'undefined' && typeof window.matchMedia === 'function' ? window.matchMedia(query).matches : false
  const [matches, setMatches] = useState(read)
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const media = window.matchMedia(query)
    const update = () => setMatches(media.matches)
    update()
    if (media.addEventListener) {
      media.addEventListener('change', update)
      return () => media.removeEventListener('change', update)
    }
    media.addListener(update)
    return () => media.removeListener(update)
  }, [query])
  return matches
}

function fileName(file?: File | null): string { return String(file?.name || '').replace(/\\/g, '/').split('/').pop() || '' }
function relativePath(file: File): string {
  const raw = String((file as DirectoryFile).webkitRelativePath || '').replace(/\\/g, '/')
  return raw ? raw.split('/').filter(Boolean).slice(1).join('/') || fileName(file) : fileName(file)
}
function messageOf(error: unknown, fallback: string): string { return error instanceof Error ? error.message : fallback }
function statusLabel(status?: string): string {
  if (!status) return '—'
  return ({ pending: '待上传', queued: '排队中', leased: '处理中', running: '处理中', succeeded: '已完成', incomplete: '覆盖不完整', failed: '失败', retry_wait: '等待重试', sealed: '已提交', uploading: '上传中', completed: '已处理' } as Record<string, string>)[status] || '处理中'
}
function pairDone(pair?: ComparePair): boolean { return Boolean(pair && ['succeeded', 'incomplete'].includes(pair.status)) }

const safeTags = new Set(['article', 'blockquote', 'br', 'caption', 'col', 'colgroup', 'dd', 'del', 'div', 'dl', 'dt', 'em', 'figcaption', 'figure', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'ins', 'li', 'mark', 'main', 'ol', 'p', 'pre', 'q', 'section', 'small', 'span', 'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'u', 'ul'])
const voidTags = new Set(['br', 'col', 'hr'])

function safeStyle(element: Element): CSSProperties {
  const source = (element as HTMLElement).style
  const style: Record<string, string> = {}
  if (!source) return style
  const sizes = new Set(['font-size', 'margin-left', 'margin-right', 'margin-top', 'margin-bottom', 'text-indent', 'max-width', 'width', 'padding-left', 'padding-right', 'padding-top', 'padding-bottom'])
  const enums: Record<string, string[]> = {
    'text-align': ['left', 'right', 'center', 'justify', 'start', 'end'],
    'font-weight': ['bold', 'normal'], 'font-style': ['italic', 'normal'],
    'vertical-align': ['super', 'sub', 'baseline', 'top', 'middle', 'bottom'],
    'break-before': ['page'], 'border-style': ['solid', 'none'],
    'text-decoration': ['underline', 'line-through', 'underline line-through', 'none'],
    'text-decoration-line': ['underline', 'line-through', 'underline line-through', 'none'],
  }
  for (const property of Array.from(source)) {
    const value = source.getPropertyValue(property).trim()
    const valid = sizes.has(property) ? /^-?\d+(?:\.\d+)?(?:pt|px|em|%)$/.test(value)
      : property === 'line-height' ? /^\d+(?:\.\d+)?(?:pt|px)?$/.test(value)
      : ['color', 'background-color'].includes(property) ? /^(?:#[a-f0-9]{6}|rgb\(\d+, \d+, \d+\))$/i.test(value)
      : property === 'font-family' ? /^[\w .(),"' -]{1,300}$/.test(value)
      : enums[property]?.includes(value)
    if (valid) style[property.replace(/-([a-z])/g, (_, letter: string) => letter.toUpperCase())] = value
  }
  return style as CSSProperties
}

function safeProps(element: Element): Record<string, string | number | CSSProperties> {
  const props: Record<string, string | number | CSSProperties> = {}
  for (const attribute of Array.from(element.attributes)) {
    const name = attribute.name.toLowerCase()
    if (name === 'class') props.className = attribute.value
    else if (name === 'colspan' || name === 'rowspan') props[name === 'colspan' ? 'colSpan' : 'rowSpan'] = Math.max(1, Math.min(1000, Number(attribute.value) || 1))
    else if (name === 'title') props.title = attribute.value
    else if (name === 'data-block-id' || name === 'data-location') props[name] = attribute.value
    else if (name === 'style') props.style = safeStyle(element)
  }
  return props
}

function renderCompareNode(node: Node, key: string): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent
  if (node.nodeType !== Node.ELEMENT_NODE) return null
  const element = node as Element
  const tag = element.tagName.toLowerCase()
  if (!safeTags.has(tag)) return null
  const children = Array.from(element.childNodes).map((child, index) => renderCompareNode(child, `${key}-${index}`))
  const diffId = element.getAttribute('data-diff-id')
  if (diffId) {
    if (tag === 'ins' || tag === 'del') return createElement(tag, { key, className: tag === 'ins' ? 'compare-ins' : 'compare-del', 'data-diff-id': diffId, tabIndex: -1, role: 'button', 'aria-label': '定位此处差异' }, children)
    const backendClass = element.getAttribute('class') || ''
    const kind = backendClass.split(/\s+/).map((token) => token.match(/^(?:(?:compare-)?diff-)?(modify|insert|delete)$/)?.[1]).find(Boolean)
    if (backendClass.split(/\s+/).includes('compare-diff-anchor')) return <span key={key} className="compare-diff-anchor" data-diff-id={diffId} aria-hidden="true" />
    return <mark key={key} className={`compare-diff ${kind || ''}`.trim()} data-diff-id={diffId} tabIndex={-1} role="button" aria-label="定位此处差异">{children}</mark>
  }
  const props = { key, ...safeProps(element) }
  return voidTags.has(tag) ? createElement(tag, props) : createElement(tag, props, children)
}

export function SafeCompareDocument({ html, label, activeDiffId, onDiff }: { html: string; label: string; activeDiffId?: string; onDiff: (id: string) => void }) {
  const articleRef = useRef<HTMLElement>(null)
  const content = useMemo(() => {
    if (typeof DOMParser === 'undefined') return []
    const parsed = new DOMParser().parseFromString(html, 'text/html')
    return Array.from(parsed.body.childNodes).map((node, index) => renderCompareNode(node, `${label}-${index}`))
  }, [html, label])
  useEffect(() => {
    const article = articleRef.current
    article?.querySelectorAll('.is-active').forEach((node) => { node.classList.remove('is-active'); node.setAttribute('tabindex', '-1') })
    const marks = activeDiffId ? article?.querySelectorAll<HTMLElement>(`[data-diff-id="${CSS.escape(activeDiffId)}"]`) : undefined
    marks?.forEach((node) => node.classList.add('is-active'))
    const first = marks?.[0] || article?.querySelector<HTMLElement>('[data-diff-id]')
    first?.setAttribute('tabindex', '0')
  }, [activeDiffId, html])
  return <article ref={articleRef} className="compare-word-doc-content" aria-label={label} tabIndex={0} onClick={(event) => { const id = (event.target as Element).closest('[data-diff-id]')?.getAttribute('data-diff-id'); if (id) onDiff(id) }} onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { const id = (event.target as Element).closest('[data-diff-id]')?.getAttribute('data-diff-id'); if (id) { event.preventDefault(); onDiff(id) } } }}>{content.length ? content : <p className="compare-empty">暂无可呈现内容。</p>}</article>
}

function PairInput({ pair, index, onChange, onRemove }: { pair: PairDraft; index: number; onChange: (side: 'left' | 'right', file?: File) => void; onRemove: () => void }) {
  return <div className="compare-pair-input"><div className="compare-pair-head"><strong>第 {index + 1} 组</strong><Button type="button" variant="quiet" disabled={index === 0} onClick={onRemove}>移除</Button></div><div className="compare-side-inputs"><label><span>原版</span><input type="file" accept={`.docx,${DOCX}`} onChange={(event) => onChange('left', event.target.files?.[0])} /></label><label><span>对比版</span><input type="file" accept={`.docx,${DOCX}`} onChange={(event) => onChange('right', event.target.files?.[0])} /></label></div><p className="muted compare-file-label">{[pair.left, pair.right].map(fileName).filter(Boolean).join(' / ') || '尚未选择文件'}</p></div>
}

function taskDescription(task: CompareTask): string {
  const pairs = task.pairs || []
  const done = pairs.filter(pairDone).length
  const differences = pairs.reduce((total, pair) => total + (pair.summary?.total || 0), 0)
  return `${done}/${task.total || pairs.length || 0} 组完成 · ${differences ? `${differences} 处差异` : '差异待读取'}`
}

type WordPane = 'merged' | 'left' | 'right'
type ViewMode = 'word' | 'classic'
type ClassicSide = 'left' | 'right'

type CompareReaderProps = {
  view?: CompareView
  selectedPair?: ComparePair
  viewQuery: { error?: unknown; loading?: boolean }
  activeDiff?: CompareDiff
  visibleDiffs: CompareDiff[]
  diffIndex: number
  diffType: string
  mobilePane: WordPane
  viewMode: ViewMode
  classicSide: ClassicSide
  isMobile: boolean
  showSources: boolean
  markup: 'all' | 'simple' | 'final'
  setDiffType: (value: string) => void
  setMobilePane: (value: WordPane) => void
  setViewMode: (value: ViewMode) => void
  setClassicSide: (value: ClassicSide) => void
  setShowSources: (value: boolean) => void
  setMarkup: (value: 'all' | 'simple' | 'final') => void
  focusDiff: (index: number) => void
  selectPairDiff: (id: string) => void
  mergedRef: RefObject<HTMLDivElement | null>
  leftRef: RefObject<HTMLDivElement | null>
  rightRef: RefObject<HTMLDivElement | null>
  classicLeftRef: RefObject<HTMLDivElement | null>
  classicRightRef: RefObject<HTMLDivElement | null>
  syncScroll: (source: HTMLElement) => void
}

function CompareReader({ view, selectedPair, viewQuery, activeDiff, visibleDiffs, diffIndex, diffType, mobilePane, viewMode, classicSide, isMobile, showSources, markup, setDiffType, setMobilePane, setViewMode, setClassicSide, setShowSources, setMarkup, focusDiff, selectPairDiff, mergedRef, leftRef, rightRef, classicLeftRef, classicRightRef, syncScroll }: CompareReaderProps) {
  const leftName = view?.left.name || selectedPair?.left.name || '原合同'
  const rightName = view?.right.name || selectedPair?.right.name || '改后的合同'
  const mergedName = view?.merged?.name || rightName
  const pairLabel = view?.pair.label || selectedPair?.label || '合同比较'
  return <div className="compare-word-shell">
    <div className="compare-word-toolbar" role="toolbar" aria-label="文档比较显示设置">
      <div className="compare-word-toolbar-main">
        <div className="compare-view-mode" role="group" aria-label="对比视图">
          <Button type="button" aria-pressed={viewMode === 'word'} onClick={() => setViewMode('word')}>Word 视图</Button>
          <Button type="button" aria-pressed={viewMode === 'classic'} onClick={() => setViewMode('classic')}>双栏对照</Button>
        </div>
        <span className="compare-word-revision-summary"><strong>{view?.summary?.total ?? visibleDiffs.length}</strong> 处修订</span>
        {viewMode === 'word' && <label className="compare-word-toggle"><input type="checkbox" checked={showSources} onChange={(event) => setShowSources(event.target.checked)} /> 显示源文档</label>}
        {viewMode === 'word' && <label className="compare-word-markup">显示<select value={markup} onChange={(event) => setMarkup(event.target.value as 'all' | 'simple' | 'final')}><option value="all">全部修改痕迹</option><option value="simple">只标位置</option><option value="final">最终样子</option></select></label>}
      </div>
    </div>
    <div className="compare-view-body" data-view-mode={viewMode}>
      <aside className="compare-diff-rail compare-word-revisions" aria-labelledby="compare-rail-title">
        <div className="compare-word-pane-head compare-word-revisions-head"><div><span className="compare-word-pane-kicker">修订</span><strong id="compare-rail-title">{visibleDiffs.length} 处修订</strong></div><div className="compare-diff-nav"><Button type="button" onClick={() => focusDiff(diffIndex - 1)} disabled={!visibleDiffs.length}>↑ 上一处</Button><strong>{visibleDiffs.length ? `${diffIndex + 1} / ${visibleDiffs.length}` : '0 / 0'}</strong><Button type="button" onClick={() => focusDiff(diffIndex + 1)} disabled={!visibleDiffs.length}>下一处 ↓</Button></div></div>
        <div className="compare-diff-toolbar"><label className="muted">筛选 <select value={diffType} onChange={(event) => setDiffType(event.target.value)}><option value="">全部</option><option value="modify">修改</option><option value="insert">新增</option><option value="delete">删除</option></select></label></div>
        {viewQuery.error ? <div className="error-state">读取结果失败：{messageOf(viewQuery.error, '结果暂时不可用')}</div> : viewQuery.loading && !view ? <Spinner label="正在读取对比结果" /> : <div className="compare-diff-list">{visibleDiffs.length ? visibleDiffs.map((diff, index) => <div className={`compare-diff-item ${index === diffIndex ? 'is-active' : ''}`} key={diff.id}><button type="button" className="compare-diff-jump" onClick={() => focusDiff(index)}><span className="compare-diff-index">{index + 1}</span><span className={`compare-diff-kind is-${diff.type}`}>{diff.type === 'modify' ? '修改' : diff.type === 'insert' ? '插入' : '删除'}</span><span className="compare-diff-preview"><span>{diff.section || '正文'} · {diff.left?.text || ''}{diff.right?.text ? ` → ${diff.right.text}` : ''}</span></span></button></div>) : <p className="empty-state">{view?.coverage?.status === 'complete' ? '两份合同没有文字差异。' : '已比对的部分没发现不同；没比对到的部分不敢保证一样。'}</p>}</div>}
      </aside>
      <div className="compare-word-view" hidden={viewMode !== 'word'}>
        <div className="compare-mobile-switch" role="group" aria-label="切换文档视图">
          {(['merged', 'left', 'right'] as const).map((pane) => <Button key={pane} type="button" aria-pressed={mobilePane === pane} onClick={() => { if (pane !== 'merged') setShowSources(true); setMobilePane(pane) }}>{pane === 'merged' ? '对照结果' : pane === 'left' ? '原合同' : '改后的合同'}</Button>)}
        </div>
        <div className={`compare-word-layout ${showSources ? '' : 'is-sources-hidden'}`.trim()} data-markup={markup}>
          <section className="compare-word-document" aria-labelledby="compare-merged-title">
            <div className="compare-word-pane-head"><div><span className="compare-word-pane-kicker">比较的文档</span><strong id="compare-merged-title">{pairLabel}</strong><small>{mergedName}</small></div><span className="compare-word-legend" aria-label="修订标记说明"><i className="compare-legend-ins">插入</i><i className="compare-legend-del">删除</i></span></div>
            <div ref={mergedRef} className="compare-word-pane compare-merged-pane" onScroll={(event) => syncScroll(event.currentTarget)}><SafeCompareDocument html={view?.merged?.html || view?.right.html || ''} label="比较的文档" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div>
          </section>
          {showSources && <aside className="compare-word-sources" aria-label="源文档">
            <section className="compare-word-source" aria-labelledby="compare-source-left-title">
              <div className="compare-word-pane-head"><div><span className="compare-word-pane-kicker">原文档</span><strong id="compare-source-left-title">{leftName}</strong><small>只读源文档</small></div><button className="compare-word-close" type="button" onClick={() => setShowSources(false)} aria-label="关闭源文档">×</button></div>
              <div ref={leftRef} className="compare-word-pane" onScroll={(event) => syncScroll(event.currentTarget)}><SafeCompareDocument html={view?.left.html || ''} label="原文档" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div>
            </section>
            <section className="compare-word-source" aria-labelledby="compare-source-right-title">
              <div className="compare-word-pane-head"><div><span className="compare-word-pane-kicker">修订的文档</span><strong id="compare-source-right-title">{rightName}</strong><small>只读源文档</small></div><button className="compare-word-close" type="button" onClick={() => setShowSources(false)} aria-label="关闭源文档">×</button></div>
              <div ref={rightRef} className="compare-word-pane" onScroll={(event) => syncScroll(event.currentTarget)}><SafeCompareDocument html={view?.right.html || ''} label="修订的文档" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div>
            </section>
          </aside>}
        </div>
      </div>
      <div className="compare-classic-view" hidden={viewMode !== 'classic'}>
        <div className="compare-document-area">
          <div className="compare-reader-label"><span>合同正文</span></div>
          <div className="compare-columns-head"><span><i className="compare-side-badge">A</i><b>合同A</b><small>{leftName}</small></span><span className="compare-columns-arrow" aria-hidden="true">→</span><span><i className="compare-side-badge is-revised">B</i><b>合同B</b><small>{rightName}</small></span></div>
          <div className="compare-mobile-switch" role="group" aria-label="切换合同A或合同B">
            <Button type="button" aria-pressed={classicSide === 'left'} onClick={() => setClassicSide('left')}>查看合同A</Button>
            <Button type="button" aria-pressed={classicSide === 'right'} onClick={() => setClassicSide('right')}>查看合同B</Button>
          </div>
          <div className="compare-columns" data-mobile-side={classicSide}>
            <div ref={classicLeftRef} className="compare-pane" onScroll={(event) => syncScroll(event.currentTarget)}><SafeCompareDocument html={view?.left.html || ''} label="合同A正文" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div>
            <div className="compare-classic-divider" aria-hidden="true" />
            <div ref={classicRightRef} className="compare-pane" onScroll={(event) => syncScroll(event.currentTarget)}><SafeCompareDocument html={view?.right.html || ''} label="合同B正文" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div>
          </div>
        </div>
      </div>
    </div>
    {isMobile && <p className="compare-word-mobile-note">用上方标签切换要看的文档。</p>}
  </div>
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
  const [mobilePane, setMobilePane] = useState<WordPane>('merged')
  const [viewMode, setViewMode] = useState<ViewMode>('word')
  const [classicSide, setClassicSide] = useState<ClassicSide>('left')
  const [viewerOpen, setViewerOpen] = useState(false)
  const [showSources, setShowSources] = useState(false)
  const [markup, setMarkup] = useState<'all' | 'simple' | 'final'>('all')
  const [folderFiles, setFolderFiles] = useState<{ left: File[]; right: File[] }>({ left: [], right: [] })
  const isMobile = useMediaQuery('(max-width: 760px)')
  const createMutation = useCompareTaskMutation()
  const uploadMutation = useCompareUploadMutation()
  const sealMutation = useCompareSealMutation()
  const selectedPair = task.data?.pairs?.find((pair) => pair.id === selectedPairId)
  const selectedPairIndex = task.data?.pairs?.findIndex((pair) => pair.id === selectedPairId) ?? -1
  const viewQuery = useCompareView(selectedPairId && pairDone(selectedPair) ? selectedPairId : undefined)
  const view = viewQuery.data
  const mergedRef = useRef<HTMLDivElement>(null)
  const leftRef = useRef<HTMLDivElement>(null)
  const rightRef = useRef<HTMLDivElement>(null)
  const classicLeftRef = useRef<HTMLDivElement>(null)
  const classicRightRef = useRef<HTMLDivElement>(null)
  const scrollLockRef = useRef(false)

  useEffect(() => {
    if (!selectedTaskId && tasks.data?.items[0]) setSelectedTaskId(tasks.data.items[0].id)
  }, [selectedTaskId, tasks.data?.items])
  useEffect(() => {
    const first = task.data?.pairs?.find(pairDone)
    if (!selectedPairId || !task.data?.pairs?.some((pair) => pair.id === selectedPairId)) {
      setSelectedPairId(first?.id)
      setViewerOpen(Boolean(first))
    }
  }, [selectedPairId, task.data?.pairs])
  useEffect(() => {
    const open = viewerOpen && Boolean(selectedPairId)
    document.body.classList.toggle('compare-fullscreen-open', open)
    return () => document.body.classList.remove('compare-fullscreen-open')
  }, [selectedPairId, viewerOpen])
  useEffect(() => {
    if (!viewerOpen) return
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setViewerOpen(false) }
    document.addEventListener('keydown', closeOnEscape)
    return () => document.removeEventListener('keydown', closeOnEscape)
  }, [viewerOpen])
  const visibleDiffs = useMemo(() => {
    const all = view?.diffs || []
    return diffType ? all.filter((item) => item.type === diffType) : all
  }, [diffType, view?.diffs])
  const activeDiff = visibleDiffs[diffIndex]
  const scrollToDiff = useCallback((pane: HTMLDivElement | null, id: string) => {
    if (!pane || !pane.clientHeight) return false
    const target = pane.querySelector<HTMLElement>(`[data-diff-id="${CSS.escape(id)}"]`)
    if (!target) return false
    const paneRect = pane.getBoundingClientRect()
    const targetRect = target.getBoundingClientRect()
    const nextTop = pane.scrollTop + targetRect.top - paneRect.top - (pane.clientHeight - targetRect.height) / 2
    pane.scrollTo({ top: Math.max(0, Math.min(nextTop, pane.scrollHeight - pane.clientHeight)), behavior: 'auto' })
    return true
  }, [])
  const allPanes = useCallback(() => [mergedRef.current, leftRef.current, rightRef.current, classicLeftRef.current, classicRightRef.current], [])
  const focusDiff = useCallback((index: number) => {
    if (!visibleDiffs.length) return
    const nextIndex = (index + visibleDiffs.length) % visibleDiffs.length
    const id = visibleDiffs[nextIndex].id
    setDiffIndex(nextIndex)
    const selector = `[data-diff-id="${CSS.escape(id)}"]`
    const wordPanes: Record<WordPane, HTMLDivElement | null> = { merged: mergedRef.current, left: leftRef.current, right: rightRef.current }
    const classicPanes: Record<ClassicSide, HTMLDivElement | null> = { left: classicLeftRef.current, right: classicRightRef.current }
    if (isMobile) {
      let target: HTMLDivElement | null = null
      if (viewMode === 'word') {
        let targetKey: WordPane = mobilePane
        if (!wordPanes[targetKey]?.querySelector(selector)) {
          targetKey = (['merged', 'right', 'left'] as const).find((pane) => wordPanes[pane]?.querySelector(selector)) || mobilePane
          if (targetKey !== mobilePane) setMobilePane(targetKey)
        }
        target = wordPanes[targetKey]
      } else {
        let targetSide: ClassicSide = classicSide
        if (!classicPanes[targetSide]?.querySelector(selector)) {
          const other: ClassicSide = targetSide === 'left' ? 'right' : 'left'
          if (classicPanes[other]?.querySelector(selector)) { targetSide = other; setClassicSide(other) }
        }
        target = classicPanes[targetSide]
      }
      scrollLockRef.current = true
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          scrollToDiff(target, id)
          scrollLockRef.current = false
        })
      })
      return
    }
    scrollLockRef.current = true
    allPanes().forEach((pane) => scrollToDiff(pane, id))
    requestAnimationFrame(() => { scrollLockRef.current = false })
  }, [allPanes, classicSide, isMobile, mobilePane, scrollToDiff, viewMode, visibleDiffs])
  useEffect(() => {
    const id = activeDiff?.id
    if (!id) return
    const frame = requestAnimationFrame(() => {
      const panes = isMobile
        ? viewMode === 'word'
          ? [mobilePane === 'merged' ? mergedRef.current : mobilePane === 'left' ? leftRef.current : rightRef.current]
          : [classicSide === 'left' ? classicLeftRef.current : classicRightRef.current]
        : allPanes()
      scrollLockRef.current = true
      panes.forEach((pane) => scrollToDiff(pane, id))
      requestAnimationFrame(() => { scrollLockRef.current = false })
    })
    return () => cancelAnimationFrame(frame)
  }, [activeDiff?.id, allPanes, classicSide, isMobile, mobilePane, scrollToDiff, viewMode])
  useEffect(() => { setDiffIndex(0) }, [diffType, view?.pair.id])

  const syncScroll = (source: HTMLElement) => {
    if (scrollLockRef.current || isMobile) return
    const panes = allPanes().filter((pane): pane is HTMLDivElement => Boolean(pane && pane.clientHeight))
    const targets = panes.filter((pane) => pane !== source)
    if (!targets.length) return
    const sourceMax = Math.max(0, source.scrollHeight - source.clientHeight)
    const ratio = sourceMax ? source.scrollTop / sourceMax : 0
    scrollLockRef.current = true
    targets.forEach((target) => {
      const targetMax = Math.max(0, target.scrollHeight - target.clientHeight)
      target.scrollTop = ratio * targetMax
    })
    requestAnimationFrame(() => { scrollLockRef.current = false })
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
    setMessage(`配成了 ${next.filter((pair) => pair.left && pair.right).length} 对；还有 ${next.filter((pair) => !pair.left || !pair.right).length} 个文件配不上对。`)
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
        if (receipts.some((receipt) => !['accepted', 'already_accepted'].includes(receipt.status))) throw new Error(`第 ${index + 1} 对还没上传完。`)
        draft.next = index + 1; setUploadDraft({ ...draft })
      }
      await sealMutation.mutateAsync(draft.task.id)
    } catch (nextError) {
      setError(`上传断了：${messageOf(nextError, '文件没传完')}；传好的没丢，继续传就行。`)
      return
    }
    setUploadDraft(undefined); setCreateOpen(false); setMessage('已提交，对比任务正在处理。'); setSelectedTaskId(draft.task.id)
    try {
      await Promise.all([tasks.refetch(), refetchCompareTask(draft.task.id)])
    } catch (nextError) {
      setError(`任务已提交，但状态刷新失败：${messageOf(nextError, '服务暂时不可用')}。请稍后刷新。`)
    }
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
      setMobilePane('merged')
    }
  }
  return <div className="fundlex-compare-page">
    <div className="page-heading"><div><h1>合同对比</h1></div><div className="action-row"><Button type="button" onClick={() => void tasks.refetch()}>刷新</Button><Button type="button" variant="primary" onClick={resetCreate}>＋ 新建对比任务</Button></div></div>
    {error && <div className="error-state" role="alert">{error}</div>}{message && <div className="fundlex-message" role="status">{message}</div>}
     <Card className="compare-task-card"><div className="page-heading"><div><h2>我的对比任务</h2></div></div>{tasks.error ? <div className="error-state">读取对比任务失败：{messageOf(tasks.error, '服务暂时不可用')}</div> : tasks.loading && !tasks.data ? <Spinner /> : tasks.data?.items.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>任务</th><th>分组</th><th>状态</th><th>结果</th><th /></tr></thead><tbody>{tasks.data.items.map((item) => <tr key={item.id}><td><button type="button" className="table-link compare-task-name-cell" title={item.name} onClick={() => setSelectedTaskId(item.id)}>{item.name}</button></td><td>{item.total || item.pairs?.length || 0}</td><td><StatusBadge value={statusLabel(item.status)} /></td><td className="compare-task-result-cell">{taskDescription(item)}</td><td><Button type="button" variant="primary" onClick={() => setSelectedTaskId(item.id)}>查看</Button></td></tr>)}</tbody></table></div> : <div className="empty-state"><strong>还没有合同对比任务</strong><p>创建一组或多组左右合同开始比较。</p></div>}</Card>
    {createOpen && <Card className="compare-create"><div className="compare-create-intro"><div><h2>新建对比任务</h2></div><span className="compare-step">1 / 2 · 准备文件</span></div><label className="compare-task-name">任务名称<input value={taskName} maxLength={200} onChange={(event) => setTaskName(event.target.value)} placeholder="例如：法务与产品部合同差异" /></label><div className="compare-folder-actions"><label className="ui-button"><span>选择原版文件夹</span><input type="file" {...{ webkitdirectory: '', directory: '' } as Record<string, string>} multiple hidden onChange={(event) => applyFolder('left', event)} /></label><label className="ui-button"><span>选择对比版文件夹</span><input type="file" {...{ webkitdirectory: '', directory: '' } as Record<string, string>} multiple hidden onChange={(event) => applyFolder('right', event)} /></label><span className="muted">按相同相对路径配对；未配对文件可以手工补齐。</span></div>{pairs.map((pair, index) => <PairInput key={index} pair={pair} index={index} onChange={(side, file) => selectFiles(index, side, file)} onRemove={() => setPairs((current) => current.length > 1 ? current.filter((_, itemIndex) => itemIndex !== index) : current)} />)}<div className="action-row"><Button type="button" onClick={() => setPairs((current) => [...current, {}])}>＋ 添加一组</Button><Button type="button" variant="primary" disabled={createMutation.isPending || uploadMutation.isPending || sealMutation.isPending} onClick={() => void (uploadDraft ? continueUpload(uploadDraft) : createTask())}>{uploadDraft ? '继续上传' : '开始上传并对比'}</Button></div></Card>}
    {selectedTaskId && <Card className="compare-detail"><div className="page-heading"><div><h2>{task.data?.name || '合同对比任务'}</h2><p className="muted">{task.data ? `${statusLabel(task.data.status)} · ${task.data.pairs?.length || 0} 组` : '正在读取任务…'}</p></div><Button type="button" onClick={() => void task.refetch()} disabled={task.refreshing}>刷新状态</Button></div><div className="compare-direction-note"><span className="compare-direction-icon" aria-hidden="true">→</span><div><strong>阅读方向</strong><span>原版（基准） → 对比版（修订）</span></div><small>新增 / 删除均按此方向解释</small></div>{task.error ? <div className="error-state">读取任务失败：{messageOf(task.error, '服务暂时不可用')}</div> : task.loading && !task.data ? <Spinner /> : <div className="compare-pair-statuses">{(task.data?.pairs || []).map((pair, index) => <button type="button" className={`compare-pair-status ${pair.id === selectedPairId ? 'is-selected' : ''} ${pairDone(pair) ? 'is-done' : ''} ${pair.status === 'incomplete' ? 'is-incomplete' : ''} ${pair.status === 'failed' ? 'is-failed' : ''}`} key={pair.id} onClick={() => { setSelectedPairId(pair.id); setViewerOpen(true) }}><span className="compare-pair-number">{String(index + 1).padStart(2, '0')}</span><span className="compare-pair-main"><strong>{pair.label || `第 ${index + 1} 组`}</strong><small>{pair.left?.name || '原版未命名'} → {pair.right?.name || '对比版未命名'}</small></span><span className="compare-pair-state">{statusLabel(pair.status)}{pair.summary ? ` · ${pair.summary.total || 0} 处` : ''}</span>{pair.error_code && <span className="compare-pair-error">处理失败：{pair.error_code}</span>}</button>)}</div>}</Card>}
    {selectedPairId && viewerOpen && <Card className="compare-viewer" role="dialog" aria-modal="true" aria-label="合同比对结果" data-mobile-pane={mobilePane} data-view-mode={viewMode}>
      <div className="compare-viewer-toolbar">
        <div className="compare-viewer-title"><div><strong>{view?.pair.label || selectedPair?.label || '合同对比'}</strong></div>
          <div className="action-row"><Button type="button" onClick={() => movePair(-1)} disabled={selectedPairIndex <= 0}>上一组</Button><span className="compare-pair-counter">{task.data?.pairs?.length && selectedPairIndex >= 0 ? `${selectedPairIndex + 1} / ${task.data.pairs.length}` : '0 / 0'}</span><Button type="button" onClick={() => movePair(1)} disabled={!task.data?.pairs || selectedPairIndex < 0 || selectedPairIndex >= task.data.pairs.length - 1}>下一组</Button><Button type="button" className="compare-viewer-close" onClick={() => setViewerOpen(false)}>× 关闭</Button></div>
        </div>
        <div className="compare-summary-row"><div className="compare-summary-stat"><span>当前结果</span><strong>{view?.summary ? `共 ${view.summary.total || 0} 处差异 · 修改 ${view.summary.modify || 0} · 新增 ${view.summary.insert || 0} · 删除 ${view.summary.delete || 0}` : '结果尚未就绪'}</strong></div>{view?.coverage?.status !== 'complete' && view?.coverage && <details className="compare-coverage-chip"><summary>覆盖不完整 · {view.coverage.warnings?.length || 0} 项未覆盖</summary><div className="compare-coverage-popover" role="status"><p>以下内容未纳入比较，请人工复核，不要据此确认全文无差异。</p>{view.coverage.warnings?.length ? <ul>{view.coverage.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul> : null}</div></details>}</div>
      </div>
      {viewQuery.error ? <div className="error-state">读取结果失败：{messageOf(viewQuery.error, '结果暂时不可用')}</div> : viewQuery.loading && !view ? <Spinner label="正在读取对比结果" /> : view && <CompareReader view={view} selectedPair={selectedPair} viewQuery={viewQuery} activeDiff={activeDiff} visibleDiffs={visibleDiffs} diffIndex={diffIndex} diffType={diffType} mobilePane={mobilePane} viewMode={viewMode} classicSide={classicSide} isMobile={isMobile} showSources={showSources} markup={markup} setDiffType={setDiffType} setMobilePane={setMobilePane} setViewMode={setViewMode} setClassicSide={setClassicSide} setShowSources={setShowSources} setMarkup={setMarkup} focusDiff={focusDiff} selectPairDiff={selectPairDiff} mergedRef={mergedRef} leftRef={leftRef} rightRef={rightRef} classicLeftRef={classicLeftRef} classicRightRef={classicRightRef} syncScroll={syncScroll} />}
    </Card>}

  </div>
}
