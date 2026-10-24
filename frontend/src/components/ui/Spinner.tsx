export function Spinner({ label = '加载中' }: { label?: string }) {
  return <span className="ui-spinner" role="status" aria-label={label} />
}
