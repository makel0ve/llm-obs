import axios from 'axios'

export const SESSION_EXPIRED_EVENT = 'llmobs:session-expired'

export type ApiErrorKind =
  | 'unauthorized'
  | 'forbidden'
  | 'rate_limited'
  | 'server_error'
  | 'network_error'
  | 'unknown'

export function getApiErrorStatus(error: unknown) {
  if (axios.isAxiosError(error)) {
    return error.response?.status
  }

  if (error && typeof error === 'object' && 'response' in error) {
    return (error.response as { status?: number } | undefined)?.status
  }

  return undefined
}

export function getApiErrorKind(error: unknown): ApiErrorKind {
  const status = getApiErrorStatus(error)

  if (status === 401) return 'unauthorized'
  if (status === 403) return 'forbidden'
  if (status === 429) return 'rate_limited'
  if (status && status >= 500) return 'server_error'

  if (axios.isAxiosError(error) && !error.response) {
    return 'network_error'
  }

  return 'unknown'
}

export function getApiErrorMessage(error: unknown, fallback = 'Request failed. Try again.') {
  switch (getApiErrorKind(error)) {
    case 'unauthorized':
      return 'Your session expired. Sign in again.'
    case 'forbidden':
      return 'You do not have permission to perform this action.'
    case 'rate_limited':
      return 'Too many requests. Wait a moment and try again.'
    case 'server_error':
      return 'The server could not complete the request. Try again after checking the API status.'
    case 'network_error':
      return 'The API could not be reached. Check the server connection and try again.'
    default:
      return fallback
  }
}

export function clearStoredSession() {
  localStorage.removeItem('token')
  localStorage.removeItem('projectId')
  localStorage.removeItem('apiKey')
  localStorage.removeItem('role')
}

export function isUnauthorizedApiError(error: unknown) {
  return getApiErrorKind(error) === 'unauthorized'
}
