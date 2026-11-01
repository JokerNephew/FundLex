import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button, Card, Spinner } from '../../components/ui'
import { useCompareTask, useCompareView } from '../../api/hooks'
import {
  CompareReader,
  messageOf,
  pairDone,
  statusLabel,
  useMediaQuery,
  type ClassicSide,
  type ViewMode,
  type WordPane,
} from './shared'

// P3 比对工作台（FL-D846：/compare/:taskId?pair=）：任务头 + 合同组 chip 切换条 +
// 页面内嵌结果区（region，不再是叠层 dialog；无关闭/上一组/下一组——
// 退出经「← 返回对比任务列表」，组切换经 chip 点选，与 V1 的 IA 对齐）。
export function CompareTaskPage() {
  const { taskId = '' } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation() as { state?: { notice?: string; warning?: string } }
  const task = useCompareTask(taskId || undefined, { pollMs: 2500 })
  const selectedPairId = searchParams.get('pair') || undefined
  const [diffType, setDiffType] = useState('')
  const [diffIndex, setDiffIndex] = useState(0)
  const [mobilePane, setMobilePane] = useState<WordPane>('merged')
  const [viewMode, setViewMode] = useState<ViewMode>('word')
  const [classicSide, setClassicSide] = useState<ClassicSide>('left')
  const [showSources, setShowSources] = useState(false)
  const [markup, setMarkup] = useState<'all' | 'simple' | 'final'>('all')
  const isMobile = useMediaQuery('(max-width: 760px)')
  const pairs = useMemo(() => task.data?.pairs || [], [task.data?.pairs])
  const selectedPair = pairs.find((pair) => pair.id === selectedPairId)
  const viewQuery = useCompareView(selectedPairId && pairDone(selectedPair) ? selectedPairId : undefined)
  const view = viewQuery.data
  const mergedRef = useRef<HTMLDivElement>(null)
  const leftRef = useRef<HTMLDivElement>(null)
  const rightRef = useRef<HTMLDivElement>(null)
  const classicLeftRef = useRef<HTMLDivElement>(null)
  const classicRightRef = useRef<HTMLDivElement>(null)
  const scrollLockRef = useRef(false)

  useEffect(() => {
    if (!pairs.length) return
    if (!selectedPairId || !pairs.some((pair) => pair.id === selectedPairId)) {
      const first = pairs.find(pairDone) || pairs[0]
      // 必须带上 location.state：replace 不传 state 会清掉新建页经 navigate
      // 带来的提交成功提示（notice/warning），首传闭环回归（FL-D846 漏配）抓到。
      setSearchParams({ pair: first.id }, { replace: true, state: location.state })
      setMobilePane('merged')
    }
  }, [selectedPairId, pairs, setSearchParams, location.state])
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

  // Linked scrolling: throttle to one rAF per frame, suppress the echo
  // events the programmatic writes cause, and release the echo guard only
  // after the gesture settles. The previous version wrote target scrollTop
  // synchronously on every scroll event and released its lock after a
  // single frame, so momentum scrolling echoed back and jittered (FL-D842).
  const syncTargetsRef = useRef<Set<HTMLElement>>(new Set())
  const syncFrameRef = useRef<number | null>(null)
  const syncReleaseRef = useRef<number | undefined>(undefined)
  const syncScroll = useCallback((source: HTMLElement) => {
    if (scrollLockRef.current || isMobile) return
    if (syncTargetsRef.current.has(source)) return
    if (syncFrameRef.current !== null) return
    syncFrameRef.current = requestAnimationFrame(() => {
      syncFrameRef.current = null
      const panes = allPanes().filter((pane): pane is HTMLDivElement => Boolean(pane && pane.clientHeight))
      const targets = panes.filter((pane) => pane !== source)
      if (!targets.length) return
      const sourceMax = Math.max(0, source.scrollHeight - source.clientHeight)
      const ratio = sourceMax ? source.scrollTop / sourceMax : 0
      targets.forEach((target) => {
        syncTargetsRef.current.add(target)
        const targetMax = Math.max(0, target.scrollHeight - target.clientHeight)
        target.scrollTop = ratio * targetMax
      })
      window.clearTimeout(syncReleaseRef.current)
      syncReleaseRef.current = window.setTimeout(() => { syncTargetsRef.current.clear() }, 160)
    })
  }, [allPanes, isMobile])
  useEffect(() => {
    // Bind natively so the listeners can be passive; React's onScroll prop
    // is never passive and would keep the compositor waiting on the handler.
    const refs = [mergedRef, leftRef, rightRef, classicLeftRef, classicRightRef]
    const panes = refs.map((ref) => ref.current).filter((pane): pane is HTMLDivElement => Boolean(pane))
    const onScroll = (event: Event) => syncScroll(event.currentTarget as HTMLElement)
    const takeControl = (event: Event) => { syncTargetsRef.current.delete(event.currentTarget as HTMLElement) }
    panes.forEach((pane) => {
      pane.addEventListener('scroll', onScroll, { passive: true })
      pane.addEventListener('wheel', takeControl, { passive: true })
      pane.addEventListener('pointerdown', takeControl, { passive: true })
      pane.addEventListener('touchstart', takeControl, { passive: true })
    })
    return () => panes.forEach((pane) => {
      pane.removeEventListener('scroll', onScroll)
      pane.removeEventListener('wheel', takeControl)
      pane.removeEventListener('pointerdown', takeControl)
      pane.removeEventListener('touchstart', takeControl)
    })
  }, [syncScroll, showSources, view?.pair.id])

  const selectPair = (id: string) => { setSearchParams({ pair: id }); setMobilePane('merged'); setShowSources(false) }
  const selectPairDiff = (id: string) => { const index = visibleDiffs.findIndex((diff) => diff.id === id); if (index >= 0) focusDiff(index) }
  const selectPairReady = selectedPair && pairDone(selectedPair)
  const pending = pairs.length && !pairs.some(pairDone)
  return <div className="fundlex-compare-page">
    <div className="page-heading"><div><Button type="button" variant="quiet" onClick={() => navigate('/compare')}>← 返回对比任务列表</Button><h1>{task.data?.name || '合同对比任务'}</h1><p className="muted">{task.data ? `${statusLabel(task.data.status)} · ${pairs.length} 组` : '正在读取任务…'}</p></div><Button type="button" onClick={() => void task.refetch()} disabled={task.refreshing}>刷新状态</Button></div>
    {location.state?.warning && <div className="error-state" role="alert">{location.state.warning}</div>}{location.state?.notice && <div className="fundlex-message" role="status">{location.state.notice}</div>}
    {task.error ? <div className="error-state">读取任务失败：{messageOf(task.error, '服务暂时不可用')}</div> : task.loading && !task.data ? <Spinner /> : <>
      {pending ? <p className="muted">任务正在处理或等待上传，暂无比对结果；下方芯片可核对各组文件配对，处理完成后选择合同组查看差异。</p> : null}
      <div className="compare-pair-statuses" role="tablist" aria-label="合同组" aria-orientation="horizontal">{pairs.map((pair, index) => <button type="button" role="tab" aria-selected={pair.id === selectedPairId ? 'true' : 'false'} className={`compare-pair-status ${pair.id === selectedPairId ? 'is-selected' : ''} ${pairDone(pair) ? 'is-done' : ''} ${pair.status === 'incomplete' ? 'is-incomplete' : ''} ${pair.status === 'failed' ? 'is-failed' : ''}`} key={pair.id} onClick={() => selectPair(pair.id)}><span className="compare-pair-number">{String(index + 1).padStart(2, '0')}</span><span className="compare-pair-main"><strong>{pair.label || `第 ${index + 1} 组`}</strong><small>{pair.left?.name || '原版未命名'} → {pair.right?.name || '对比版未命名'}</small></span><span className="compare-pair-state">{statusLabel(pair.status)}{pair.summary ? ` · ${pair.summary.total || 0} 处` : ''}</span>{pair.error_code && <span className="compare-pair-error">处理失败：{pair.error_code}</span>}</button>)}</div>
      {selectedPair && <Card className="compare-viewer" role="region" aria-label="合同比对结果" data-mobile-pane={mobilePane} data-view-mode={viewMode}>
        <div className="compare-viewer-toolbar">
          <div className="compare-viewer-title"><div><strong id="compare-pair-title">{view?.pair.label || selectedPair?.label || '合同对比'}</strong></div></div>
          {selectPairReady ? <div className="compare-summary-row"><div className="compare-summary-stat"><span>合同A → 合同B</span><strong>{view?.summary ? `共 ${view.summary.total || 0} 处差异 · 修改 ${view.summary.modify || 0} · 新增 ${view.summary.insert || 0} · 删除 ${view.summary.delete || 0}` : '结果尚未就绪'}</strong></div>{view?.coverage?.status !== 'complete' && view?.coverage && <details className="compare-coverage-chip"><summary>覆盖不完整 · {view.coverage.warnings?.length || 0} 项未覆盖</summary><div className="compare-coverage-popover" role="status"><p>以下内容未纳入比较，请人工复核，不要据此确认全文无差异。</p>{view.coverage.warnings?.length ? <ul>{view.coverage.warnings.map((warning, index) => <li key={`${warning}-${index}`}>{warning}</li>)}</ul> : null}</div></details>}</div> : null}
        </div>
        {!selectPairReady ? <p className="compare-viewer-empty" role="status">{selectedPair.status === 'failed' ? `该组处理失败${selectedPair.error_code ? `：${selectedPair.error_code}` : '，请重新创建合同组'}` : '该组正在处理或等待上传，暂无比对结果。'}</p> : viewQuery.error ? <div className="error-state">读取结果失败：{messageOf(viewQuery.error, '结果暂时不可用')}</div> : viewQuery.loading && !view ? <Spinner label="正在读取对比结果" /> : view && <CompareReader view={view} selectedPair={selectedPair} viewQuery={viewQuery} activeDiff={activeDiff} visibleDiffs={visibleDiffs} diffIndex={diffIndex} diffType={diffType} mobilePane={mobilePane} viewMode={viewMode} classicSide={classicSide} isMobile={isMobile} showSources={showSources} markup={markup} setDiffType={setDiffType} setMobilePane={setMobilePane} setViewMode={setViewMode} setClassicSide={setClassicSide} setShowSources={setShowSources} setMarkup={setMarkup} focusDiff={focusDiff} selectPairDiff={selectPairDiff} mergedRef={mergedRef} leftRef={leftRef} rightRef={rightRef} classicLeftRef={classicLeftRef} classicRightRef={classicRightRef} />}
      </Card>}
    </>}
  </div>
}
