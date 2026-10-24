import type { ReactNode } from 'react'
import { useState } from 'react'

export function SplitPane({
  left,
  right,
  leftLabel = '文档',
  rightLabel = '修订',
}: {
  left: ReactNode
  right: ReactNode
  leftLabel?: string
  rightLabel?: string
}) {
  const [mobilePane, setMobilePane] = useState<'left' | 'right'>('left')
   return <div className="fundlex-split-pane">
    <div className="fundlex-split-pane__mobile" role="tablist" aria-label="复核面板切换">
      <button type="button" className={`ui-button ${mobilePane === 'left' ? 'ui-button--primary' : ''}`} aria-selected={mobilePane === 'left'} onClick={() => setMobilePane('left')}>{leftLabel}</button>
      <button type="button" className={`ui-button ${mobilePane === 'right' ? 'ui-button--primary' : ''}`} aria-selected={mobilePane === 'right'} onClick={() => setMobilePane('right')}>{rightLabel}</button>
    </div>
    <section className={`fundlex-split-pane__panel${mobilePane === 'left' ? ' is-mobile-visible' : ''}`} aria-label={leftLabel}><div className="fundlex-split-pane__body">{left}</div></section>
    <section className={`fundlex-split-pane__panel${mobilePane === 'right' ? ' is-mobile-visible' : ''}`} aria-label={rightLabel}><div className="fundlex-split-pane__body">{right}</div></section>
  </div>
}
