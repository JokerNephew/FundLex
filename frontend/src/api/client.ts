import type { ApiErrorBody } from '../types'

export const AUTH_TOKEN_KEY = 'fundlex-auth-token'
export const DEV_USER_KEY = 'fundlex-dev-user'

export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly body?: unknown

  constructor(message: string, status: number, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
    const detail = (body as ApiErrorBody | undefined)?.detail
    this.code = typeof detail === 'string' ? detail : undefined
  }
}

export class SessionExpiredError extends ApiError {
  constructor() {
    super('登录状态已失效，请重新登录。', 401)
    this.name = 'SessionExpiredError'
  }
}

function notifySessionExpired(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('fundlex:session-expired'))
  }
}

export type UploadProgress = (loaded: number, total: number) => void

function authHeaders(): Headers {
  const headers = new Headers()
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY)
  const devUser = localStorage.getItem(DEV_USER_KEY)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (devUser) headers.set('X-FundLex-User', devUser)
  return headers
}

export function getBasePath(): string {
  if (typeof document === 'undefined') return ''
  const configured = document.querySelector<HTMLMetaElement>('meta[name="fundlex-base-path"]')?.content
  const base = (configured || '').trim()
  if (!base || base === '/') return ''
  return `/${base.replace(/^\/+|\/+$/g, '')}`
}

export function assetPath(path: string): string {
  if (!path.startsWith('/') || path.startsWith('//')) {
    throw new Error('页面返回了不支持的资源路径。')
  }
  return `${getBasePath()}${path}`
}

export function assertApiPath(path: string): string {
  if (!path.startsWith('/api/') || path.startsWith('//')) {
    throw new Error('服务端返回了不支持的路径。')
  }
  return `${getBasePath()}${path}`
}

async function parseError(response: Response): Promise<never> {
  let body: unknown
  try { body = await response.json() } catch { body = undefined }
  if (response.status === 401) {
    notifySessionExpired()
    throw new SessionExpiredError()
  }
  const detail = (body as ApiErrorBody | undefined)?.detail
  const message = typeof detail === 'string' ? detail : response.statusText || `请求失败（${response.status}）`
  throw new ApiError(message, response.status, body)
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = authHeaders()
  new Headers(init.headers).forEach((value, key) => headers.set(key, value))
  if (init.body && !headers.has('Content-Type') && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(assertApiPath(path), { ...init, headers, cache: 'no-store' })
  if (!response.ok) return parseError(response)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function requestText(path: string, init: RequestInit = {}): Promise<string> {
  const headers = authHeaders()
  new Headers(init.headers).forEach((value, key) => headers.set(key, value))
  const response = await fetch(assertApiPath(path), { ...init, headers, cache: 'no-store' })
  if (!response.ok) return parseError(response)
  return response.text()
}

export async function download(path: string): Promise<Blob> {
  const response = await fetch(assertApiPath(path), { headers: authHeaders(), cache: 'no-store' })
  if (!response.ok) return parseError(response)
  return response.blob()
}

export function upload<T>(path: string, form: FormData, onProgress?: UploadProgress): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', assertApiPath(path))
    authHeaders().forEach((value, key) => xhr.setRequestHeader(key, value))
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress?.(event.loaded, event.total)
    }
    xhr.onerror = () => reject(new ApiError('网络连接中断，请稍后重试。', 0))
    xhr.onabort = () => reject(new ApiError('上传已取消。', 0))
    xhr.onload = () => {
      let body: unknown
      try { body = xhr.responseText ? JSON.parse(xhr.responseText) : undefined } catch { body = undefined }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T)
      else if (xhr.status === 401) {
        notifySessionExpired()
        reject(new SessionExpiredError())
      }
      else reject(new ApiError(typeof (body as ApiErrorBody | undefined)?.detail === 'string' ? (body as ApiErrorBody).detail as string : '文件上传未完成。', xhr.status, body))
    }
    xhr.send(form)
  })
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export function jsonBody(value: unknown): BodyInit {
  return JSON.stringify(value)
}
