import type { MouseEvent, PropsWithChildren } from 'react'

export function DocumentAnchor({
  anchorId,
  active = false,
  onClick,
  children,
}: PropsWithChildren<{
  anchorId: string
  active?: boolean
  onClick?: (anchorId: string) => void
}>) {
  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault()
    onClick?.(anchorId)
  }
  return <button
    type="button"
    className={`fundlex-document-anchor${active ? ' is-active' : ''}`}
    data-document-anchor={anchorId}
    aria-current={active ? 'location' : undefined}
    onClick={handleClick}
  >{children}</button>
}
