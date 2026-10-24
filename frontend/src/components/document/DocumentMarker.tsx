import type { PropsWithChildren } from 'react'

export type MarkerDecision = 'pending' | 'accept' | 'reject'

export function DocumentMarker({
  revisionId,
  decision = 'pending',
  active = false,
  onClick,
  children,
}: PropsWithChildren<{
  revisionId: string
  decision?: MarkerDecision
  active?: boolean
  onClick?: (revisionId: string) => void
}>) {
  return <span
    role="button"
    tabIndex={0}
    className={`fundlex-document-marker decision-${decision}${active ? ' is-active' : ''}`}
    data-document-marker={revisionId}
    data-decision={decision}
    aria-current={active ? 'location' : undefined}
    onClick={() => onClick?.(revisionId)}
    onKeyDown={(event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault()
        onClick?.(revisionId)
      }
    }}
  >{children}</span>
}
