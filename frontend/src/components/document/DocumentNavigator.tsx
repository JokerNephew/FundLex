import { Button } from '../ui'

export function DocumentNavigator({
  index,
  total,
  onPrevious,
  onNext,
  previousLabel = '上一份',
  nextLabel = '下一份',
  disabled = false,
}: {
  index: number
  total: number
  onPrevious?: () => void
  onNext?: () => void
  previousLabel?: string
  nextLabel?: string
  disabled?: boolean
}) {
  return <nav className="fundlex-document-navigator" aria-label="合同导航">
    <Button type="button" disabled={disabled || index <= 0} onClick={onPrevious}>← {previousLabel}</Button>
    <span aria-live="polite">第 {total ? index + 1 : 0} / {total} 份</span>
    <Button type="button" disabled={disabled || index < 0 || index >= total - 1} onClick={onNext}>{nextLabel} →</Button>
  </nav>
}
