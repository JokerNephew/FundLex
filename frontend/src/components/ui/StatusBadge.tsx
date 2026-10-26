const labels: Record<string, string> = {
  queued: '排队中', running: '处理中', paused: '已暂停', completed: '已完成', completed_with_exceptions: '已完成（含异常）', failed: '失败',
  accepted: '已接收', rejected: '接收失败', complete: '交付完成', incomplete: '结果不完整',
  not_generated: '未生成', parsed: '已解析', released: '已发布', parse_failed: '解析失败',
}

export function StatusBadge({ value }: { value?: string | null }) {
  const text = value ? labels[value] || value : '未确认'
  const tone = value?.includes('fail') || value === 'rejected' || value === 'incomplete' || value === 'completed_with_exceptions' ? 'danger' : value === 'completed' || value === 'complete' || value === 'released' || value === 'accepted' ? 'success' : value === 'running' || value === 'queued' || value === 'parsed' ? 'info' : 'neutral'
  return <span className={`status-badge status-badge--${tone}`}>{text}</span>
}
