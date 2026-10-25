import { forwardRef, type ButtonHTMLAttributes } from 'react'

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet' | 'danger' }>(function Button({ variant = 'secondary', ...props }, ref) {
  return <button ref={ref} className={`ui-button ui-button--${variant}`} {...props} />
})
