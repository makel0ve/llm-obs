import { afterEach, describe, expect, it } from 'vitest'

import { api } from './client'
import { getApiErrorMessage, SESSION_EXPIRED_EVENT } from './errors'

describe('api client auth', () => {
  afterEach(() => {
    localStorage.clear()
    delete api.defaults.headers.common['Authorization']
  })

  it('sends the dashboard JWT from localStorage as a bearer token', async () => {
    localStorage.setItem('token', 'jwt-token')

    let authorizationHeader: unknown

    await api.get('/v1/projects', {
      adapter: async config => {
        authorizationHeader = config.headers.Authorization

        return {
          config,
          data: [],
          headers: {},
          status: 200,
          statusText: 'OK',
        }
      },
    })

    expect(authorizationHeader).toBe('Bearer jwt-token')
  })

  it('clears the dashboard session and emits an event on non-auth 401 responses', async () => {
    localStorage.setItem('token', 'jwt-token')
    localStorage.setItem('projectId', 'project-1')
    localStorage.setItem('apiKey', 'llmobs_key')
    localStorage.setItem('role', 'admin')
    api.defaults.headers.common['Authorization'] = 'Bearer jwt-token'

    let sessionExpiredEvents = 0
    window.addEventListener(SESSION_EXPIRED_EVENT, () => {
      sessionExpiredEvents += 1
    }, { once: true })

    await expect(api.get('/v1/projects', {
      adapter: async config => Promise.reject({
        config,
        isAxiosError: true,
        response: {
          status: 401,
        },
        toJSON: () => ({}),
      }),
    })).rejects.toMatchObject({ response: { status: 401 } })

    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('projectId')).toBeNull()
    expect(localStorage.getItem('apiKey')).toBeNull()
    expect(localStorage.getItem('role')).toBeNull()
    expect(api.defaults.headers.common['Authorization']).toBeUndefined()
    expect(sessionExpiredEvents).toBe(1)
  })

  it('does not clear the dashboard session for auth endpoint 401 responses', async () => {
    localStorage.setItem('token', 'jwt-token')

    await expect(api.post('/v1/auth/login', {}, {
      adapter: async config => Promise.reject({
        config,
        isAxiosError: true,
        response: {
          status: 401,
        },
        toJSON: () => ({}),
      }),
    })).rejects.toMatchObject({ response: { status: 401 } })

    expect(localStorage.getItem('token')).toBe('jwt-token')
  })
})

describe('api error messages', () => {
  it('maps common API status codes to operator-safe messages', () => {
    expect(getApiErrorMessage({ response: { status: 401 } })).toBe('Your session expired. Sign in again.')
    expect(getApiErrorMessage({ response: { status: 403 } })).toBe('You do not have permission to perform this action.')
    expect(getApiErrorMessage({ response: { status: 429 } })).toBe('Too many requests. Wait a moment and try again.')
    expect(getApiErrorMessage({ response: { status: 503 } })).toBe(
      'The server could not complete the request. Try again after checking the API status.',
    )
    expect(getApiErrorMessage(new Error('boom'), 'Fallback message')).toBe('Fallback message')
  })
})
