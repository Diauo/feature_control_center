import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiRequest, clearCsrfToken } from '@/lib/api'


describe('apiRequest', () => {
  afterEach(() => {
    clearCsrfToken()
    vi.unstubAllGlobals()
  })

  it('fetches pre-auth CSRF and sends it with unsafe requests', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'preauth-token' }))
      .mockResolvedValueOnce(jsonResponse({ created: true }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await apiRequest<{ created: boolean }>('/api/example', {
      method: 'POST',
      body: JSON.stringify({ name: 'example' }),
    })

    expect(result.created).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [, request] = fetchMock.mock.calls[1]!
    const headers = new Headers(request?.headers)
    expect(headers.get('X-CSRF-Token')).toBe('preauth-token')
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(request?.credentials).toBe('include')
  })

  it('refreshes a stale CSRF token once and retries the request', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'first-token' }))
      .mockResolvedValueOnce(
        jsonResponse({ error: { code: 'CSRF_INVALID', message: 'expired', details: {} } }, 403),
      )
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'second-token' }))
      .mockResolvedValueOnce(jsonResponse({ saved: true }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await apiRequest<{ saved: boolean }>('/api/example', { method: 'PATCH' })

    expect(result.saved).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(4)
    const headers = new Headers(fetchMock.mock.calls[3]![1]?.headers)
    expect(headers.get('X-CSRF-Token')).toBe('second-token')
  })

  it('lets the browser add the multipart boundary for FormData', async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: 'upload-token' }))
      .mockResolvedValueOnce(jsonResponse({ uploaded: true }))
    vi.stubGlobal('fetch', fetchMock)
    const form = new FormData()
    form.append('file', new Blob(['data']), 'data.xlsx')

    await apiRequest('/api/upload', { method: 'PUT', body: form })

    const headers = new Headers(fetchMock.mock.calls[1]![1]?.headers)
    expect(headers.has('Content-Type')).toBe(false)
    expect(headers.get('X-CSRF-Token')).toBe('upload-token')
  })
})

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
