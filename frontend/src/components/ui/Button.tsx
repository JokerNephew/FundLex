import type { ButtonHTMLAttributes } from 'react'

export function Button({ variant = 'secondary', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet' | 'danger' }) {
  return <button className={`ui-button ui-button--${variant}`} {...props} />
}
