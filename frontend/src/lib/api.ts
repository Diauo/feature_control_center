export interface ApiErrorBody {
  error?: {
    code?: string
    message?: string
    details?: Record<string, unknown>
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown>

  constructor(status: number, body: ApiErrorBody) {
    super(body.error?.message ?? '请求失败，请稍后重试')
    this.name = 'ApiError'
    this.status = status
    this.code = body.error?.code ?? 'REQUEST_FAILED'
    this.details = body.error?.details ?? {}
  }
}

let csrfToken = ''

export function setCsrfToken(value: string): void {
  csrfToken = value
}

export function clearCsrfToken(): void {
  csrfToken = ''
}

export async function refreshCsrfToken(): Promise<string> {
  const result = await rawRequest<{ csrfToken: string }>('/api/auth/csrf')
  setCsrfToken(result.csrfToken)
  return result.csrfToken
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(method)
  if (unsafe && !csrfToken) {
    await refreshCsrfToken()
  }
  try {
    return await rawRequest<T>(path, options, unsafe ? csrfToken : undefined)
  } catch (error) {
    if (unsafe && error instanceof ApiError && error.code === 'CSRF_INVALID') {
      await refreshCsrfToken()
      return rawRequest<T>(path, options, csrfToken)
    }
    throw error
  }
}

async function rawRequest<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const headers = new Headers(options.headers)
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData
  if (options.body && !isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (csrf) {
    headers.set('X-CSRF-Token', csrf)
  }
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: 'include',
  })
  const body = (await response.json().catch(() => ({}))) as T & ApiErrorBody
  if (!response.ok) {
    if (body.error?.code === 'AUTHENTICATION_REQUIRED') {
      window.dispatchEvent(new CustomEvent('fcc:auth-expired'))
    }
    throw new ApiError(response.status, body)
  }
  return body
}

export async function downloadFile(path: string): Promise<void> {
  const response = await fetch(path, { credentials: 'include' })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody
    if (body.error?.code === 'AUTHENTICATION_REQUIRED') {
      window.dispatchEvent(new CustomEvent('fcc:auth-expired'))
    }
    throw new ApiError(response.status, body)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const basic = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  const filename = encoded ? decodeURIComponent(encoded) : (basic ?? 'download.bin')
  const url = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    anchor.click()
  } finally {
    URL.revokeObjectURL(url)
  }
}
