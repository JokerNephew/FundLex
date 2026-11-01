import { createElement, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import { Button, Spinner } from '../../components/ui'
import type { CompareDiff, ComparePair, ComparePairManifest, CompareTask, CompareView } from '../../types'
export const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
export type DirectoryFile = File & { webkitRelativePath?: string }
export type PairDraft = { left?: File; right?: File }
export type UploadDraft = { task: CompareTask; manifests: ComparePairManifest[]; files: PairDraft[]; next: number }

export function useMediaQuery(query: string): boolean {
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

export function fileName(file?: File | null): string { return String(file?.name || '').replace(/\\/g, '/').split('/').pop() || '' }
export function relativePath(file: File): string {
  const raw = String((file as DirectoryFile).webkitRelativePath || '').replace(/\\/g, '/')
  return raw ? raw.split('/').filter(Boolean).slice(1).join('/') || fileName(file) : fileName(file)
}
export function messageOf(error: unknown, fallback: string): string { return error instanceof Error ? error.message : fallback }
export function statusLabel(status?: string): string {
  if (!status) return '—'
  return ({ pending: '待上传', queued: '排队中', leased: '处理中', running: '处理中', succeeded: '已完成', incomplete: '覆盖不完整', failed: '失败', retry_wait: '等待重试', sealed: '已提交', uploading: '上传中', completed: '已处理' } as Record<string, string>)[status] || '处理中'
}
export function pairDone(pair?: ComparePair): boolean { return Boolean(pair && ['succeeded', 'incomplete'].includes(pair.status)) }

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

export function PairInput({ pair, index, onChange, onRemove }: { pair: PairDraft; index: number; onChange: (side: 'left' | 'right', file?: File) => void; onRemove: () => void }) {
  return <div className="compare-pair-input"><div className="compare-pair-head"><strong>第 {index + 1} 组</strong><Button type="button" variant="quiet" disabled={index === 0} onClick={onRemove}>移除</Button></div><div className="compare-side-inputs"><label><span>原版</span><input type="file" accept={`.docx,${DOCX}`} onChange={(event) => onChange('left', event.target.files?.[0])} /></label><label><span>对比版</span><input type="file" accept={`.docx,${DOCX}`} onChange={(event) => onChange('right', event.target.files?.[0])} /></label></div><p className="muted compare-file-label">{[pair.left, pair.right].map(fileName).filter(Boolean).join(' / ') || '尚未选择文件'}</p></div>
}

export function taskDescription(task: CompareTask): string {
  const pairs = task.pairs || []
  const done = pairs.filter(pairDone).length
  const differences = pairs.reduce((total, pair) => total + (pair.summary?.total || 0), 0)
  return `${done}/${task.total || pairs.length || 0} 组完成 · ${differences ? `${differences} 处差异` : '差异待读取'}`
}

export type WordPane = 'merged' | 'left' | 'right'
export type ViewMode = 'word' | 'classic'
export type ClassicSide = 'left' | 'right'

export type CompareReaderProps = {
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
}

export function CompareReader({ view, selectedPair, viewQuery, activeDiff, visibleDiffs, diffIndex, diffType, mobilePane, viewMode, classicSide, isMobile, showSources, markup, setDiffType, setMobilePane, setViewMode, setClassicSide, setShowSources, setMarkup, focusDiff, selectPairDiff, mergedRef, leftRef, rightRef, classicLeftRef, classicRightRef }: CompareReaderProps) {
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
            <div ref={mergedRef} className="compare-word-pane compare-merged-pane"><SafeCompareDocument html={view?.merged?.html || view?.right.html || ''} label="比较的文档" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div>
          </section>
          {showSources && <aside className="compare-word-sources" aria-label="源文档">
            <section className="compare-word-source" aria-labelledby="compare-source-left-title">
              <div className="compare-word-pane-head"><div><span className="compare-word-pane-kicker">原文档</span><strong id="compare-source-left-title">{leftName}</strong><small>只读源文档</small></div><button className="compare-word-close" type="button" onClick={() => setShowSources(false)} aria-label="关闭源文档">×</button></div>
              <div ref={leftRef} className="compare-word-pane"><SafeCompareDocument html={view?.left.html || ''} label="原文档" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div>
            </section>
            <section className="compare-word-source" aria-labelledby="compare-source-right-title">
              <div className="compare-word-pane-head"><div><span className="compare-word-pane-kicker">修订的文档</span><strong id="compare-source-right-title">{rightName}</strong><small>只读源文档</small></div><button className="compare-word-close" type="button" onClick={() => setShowSources(false)} aria-label="关闭源文档">×</button></div>
              <div ref={rightRef} className="compare-word-pane"><SafeCompareDocument html={view?.right.html || ''} label="修订的文档" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div>
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
            <div ref={classicLeftRef} className="compare-pane"><SafeCompareDocument html={view?.left.html || ''} label="合同A正文" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div>
            <div className="compare-classic-divider" aria-hidden="true" />
            <div ref={classicRightRef} className="compare-pane"><SafeCompareDocument html={view?.right.html || ''} label="合同B正文" activeDiffId={activeDiff?.id} onDiff={selectPairDiff} /></div>
          </div>
        </div>
      </div>
    </div>
    {isMobile && <p className="compare-word-mobile-note">用上方标签切换要看的文档。</p>}
  </div>
}
