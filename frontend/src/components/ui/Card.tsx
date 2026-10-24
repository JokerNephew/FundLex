import type { HTMLAttributes, PropsWithChildren } from 'react'

export function Card({ className = '', children, ...props }: PropsWithChildren<HTMLAttributes<HTMLElement>>) {
  return <section className={`ui-card ${className}`.trim()} {...props}>{children}</section>
}
