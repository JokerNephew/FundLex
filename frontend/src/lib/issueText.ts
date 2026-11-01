// 错误码/原因码 → 用户可读文案的唯一来源（FL-D899 X1）。
// 任何面向用户的错误码渲染必须走这里，禁止在页面上裸渲染 error_code 原文。
const issueCodeLabels: Record<string, string> = {
  UPLOAD_SIZE_LIMIT: '文件超过大小上限',
  UPLOAD_HASH_MISMATCH: '文件内容与登记信息不一致',
  DOCUMENT_PROTECTED: '文档受密码保护',
  EMPTY_DOCUMENT: '文档内容为空',
  INVALID_DOCX: '不是有效的 DOCX 文件',
  UNSUPPORTED_FORMAT: '文件格式不支持',
  DUPLICATE_NAME: '任务中已存在同名文件',
  PROCESS_LIMIT: '处理资源超限',
}

export function issueCodeText(code?: string | null): string {
  if (!code) return ''
  return issueCodeLabels[code] || '这份文件没处理成功，打开看详情'
}

export function reasonCodesText(codes?: string[]): string {
  if (!codes?.length) return ''
  return codes.map((code) => issueCodeText(code) || '详见报告').join('；')
}
