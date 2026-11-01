const labels: Record<string, string> = {
  queued: '排队中', running: '处理中', paused: '已暂停', completed: '已完成', completed_with_exceptions: '已完成（部分需人工核对）', failed: '处理失败',
  accepted: '已接收', already_accepted: '已接收', rejected: '接收失败', complete: '文件已完整交付', complete_with_exceptions: '已交付（部分需人工核对）', incomplete: '未改完',
  not_generated: '未生成', diagnosed: '仅出报告未修改', evaluation_modified: '已修改（评测）',
  evaluation_modified_with_exceptions: '已修改（部分需核对，评测）', evaluation_unmodified: '无需修改（评测）',
  parsed: '已解析', released: '已发布', parse_failed: '解析失败', validated: '校验通过', archived: '已归档', uploaded: '已上传', parsing: '解析中',
  planned: '已规划', pending: '等待中', blocked: '已阻塞', partial: '部分已交付', not_started: '未开始', succeeded: '已完成',
  sealed: '已提交', uploading: '上传中', leased: '处理中', retry_wait: '等待重试',
  disabled: '已停用', eligible: '可以处理', ineligible: '不能处理',
  needs_edit: '待修改', unresolved: '未完成', unsupported: '不支持',
  modified_verified: '已修改并复核', satisfied: '已满足', not_applicable: '不适用',
  not_matched: '未命中', unknown: '未确认',
}

export function StatusBadge({ value }: { value?: string | null }) {
  // Never echo raw english status codes; already-localized Chinese labels pass through.
  const text = value ? labels[value] || (/[\u3400-\u9fff]/.test(value) ? value : '未知状态') : '未确认'
  const tone = value?.includes('fail') || value === 'rejected' || value === 'incomplete' || value === 'completed_with_exceptions' || value === 'blocked' || value === 'disabled' || value === 'ineligible' ? 'danger' : value === 'completed' || value === 'complete' || value === 'complete_with_exceptions' || value === 'released' || value === 'accepted' || value === 'already_accepted' || value === 'succeeded' || value === 'eligible' ? 'success' : value === 'running' || value === 'queued' || value === 'parsed' || value === 'leased' || value === 'parsing' || value === 'uploading' ? 'info' : 'neutral'
  return <span className={`status-badge status-badge--${tone}`}>{text}</span>
}
