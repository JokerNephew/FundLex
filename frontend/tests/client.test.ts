import { afterEach, describe, expect, it, vi } from 'vitest'
import { download, request, SessionExpiredError, upload } from '../src/api/client'

describe('API session expiry', () => {
  afterEach(() => vi.restoreAllMocks())

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
