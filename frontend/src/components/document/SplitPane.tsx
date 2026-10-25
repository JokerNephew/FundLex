import type { ReactNode } from 'react'
import { useState } from 'react'

export function SplitPane({
  left,
  right,
  leftLabel = '文档',
  rightLabel = '修订',
  mobilePane: controlledPane,
  onMobilePaneChange,
}: {
  left: ReactNode
  right: ReactNode
  leftLabel?: string
  rightLabel?: string
  mobilePane?: 'left' | 'right'
  onMobilePaneChange?: (pane: 'left' | 'right') => void
}) {
  const [mobilePane, setMobilePane] = useState<'left' | 'right'>('left')
  const pane = controlledPane || mobilePane
  const changePane = (next: 'left' | 'right') => {
    setMobilePane(next)
    onMobilePaneChange?.(next)
  }
  return <div className="fundlex-split-pane">
    <div className="fundlex-split-pane__mobile" role="tablist" aria-label="复核面板切换">
       <button type="button" role="tab" className={`ui-button ${pane === 'left' ? 'ui-button--primary' : ''}`} aria-selected={pane === 'left'} onClick={() => changePane('left')}>{leftLabel}</button>
       <button type="button" role="tab" className={`ui-button ${pane === 'right' ? 'ui-button--primary' : ''}`} aria-selected={pane === 'right'} onClick={() => changePane('right')}>{rightLabel}</button>
    </div>
    <section className={`fundlex-split-pane__panel${pane === 'left' ? ' is-mobile-visible' : ''}`} aria-label={leftLabel}><div className="fundlex-split-pane__body">{left}</div></section>
    <section className={`fundlex-split-pane__panel${pane === 'right' ? ' is-mobile-visible' : ''}`} aria-label={rightLabel}><div className="fundlex-split-pane__body">{right}</div></section>
  </div>
}
