import { afterEach, describe, expect, it, vi } from 'vitest'
import { assetPath, assertApiPath, download, request, SessionExpiredError, upload } from '../src/api/client'

describe('API session expiry', () => {
  afterEach(() => {
    document.head.innerHTML = ''
    vi.restoreAllMocks()
  })

  it('keeps API paths same-origin while applying the configured deployment prefix', async () => {
    document.head.innerHTML = '<meta name="fundlex-base-path" content="/test/">'
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }))

    await request('/api/capabilities')
    expect(fetchMock).toHaveBeenCalledWith('/test/api/capabilities', expect.objectContaining({ cache: 'no-store' }))
    expect(assertApiPath('/api/tasks')).toBe('/test/api/tasks')
    expect(() => assertApiPath('https://example.com/api/tasks')).toThrow()
    expect(() => assertApiPath('//example.com/api/tasks')).toThrow()
    expect(() => assetPath('https://example.com/logo.png')).toThrow()
    expect(() => assetPath('//example.com/logo.png')).toThrow()
  })

  it('applies the prefix to authenticated downloads', async () => {
    document.head.innerHTML = '<meta name="fundlex-base-path" content="/test">'
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('file', { status: 200 }))

    await download('/api/tasks/task/download/all')
    expect(fetchMock).toHaveBeenCalledWith('/test/api/tasks/task/download/all', expect.objectContaining({ cache: 'no-store' }))
  })

  it('applies the prefix to uploads without accepting an external target', async () => {
    document.head.innerHTML = '<meta name="fundlex-base-path" content="/test">'
    let openedPath = ''
    class SuccessfulXHR {
      upload = {}
      status = 200
      responseText = '{}'
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      onabort: (() => void) | null = null
      open(_method: string, path: string) { openedPath = path }
      setRequestHeader() {}
      send() { this.onload?.() }
    }
    vi.stubGlobal('XMLHttpRequest', SuccessfulXHR)
    await upload('/api/tasks/task/uploads', new FormData())
    expect(openedPath).toBe('/test/api/tasks/task/uploads')
    expect(() => assertApiPath('/api/tasks/task/uploads')).not.toThrow()
  })

  it('emits one shared event for a 401 response', async () => {
    const onExpired = vi.fn()
    window.addEventListener('fundlex:session-expired', onExpired)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: 'expired' }), { status: 401, headers: { 'Content-Type': 'application/json' } }))

    await expect(request('/api/tasks')).rejects.toBeInstanceOf(SessionExpiredError)
    expect(onExpired).toHaveBeenCalledTimes(1)
    window.removeEventListener('fundlex:session-expired', onExpired)
  })

  it('uses the same event for authenticated download and upload failures', async () => {
    const onExpired = vi.fn()
    window.addEventListener('fundlex:session-expired', onExpired)
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', { status: 401 }))
    await expect(download('/api/tasks/task/download/all')).rejects.toBeInstanceOf(SessionExpiredError)

    class UnauthorizedXHR {
      upload = {}
      status = 401
      responseText = JSON.stringify({ detail: 'expired' })
      onload: (() => void) | null = null
      onerror: (() => void) | null = null
      onabort: (() => void) | null = null
      open() {}
      setRequestHeader() {}
      send() { this.onload?.() }
    }
    vi.stubGlobal('XMLHttpRequest', UnauthorizedXHR)
    await expect(upload('/api/tasks/task/uploads', new FormData())).rejects.toBeInstanceOf(SessionExpiredError)
    expect(onExpired).toHaveBeenCalledTimes(2)
    window.removeEventListener('fundlex:session-expired', onExpired)
  })
})
