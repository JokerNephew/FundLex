import { forwardRef, type ButtonHTMLAttributes } from 'react'

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet' | 'danger' }>(function Button({ variant = 'secondary', className, ...props }, ref) {
  const classes = ['ui-button', `ui-button--${variant}`, className].filter(Boolean).join(' ')
  return <button ref={ref} className={classes} {...props} />
})
