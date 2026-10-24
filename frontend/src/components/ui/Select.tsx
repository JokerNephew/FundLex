import type { SelectHTMLAttributes } from 'react'

export function Select({ className = '', ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <span className="ui-select-wrap">
    <select className={`ui-select ${className}`.trim()} {...props} />
    <span className="ui-select-chevron" aria-hidden="true" />
  </span>
}
