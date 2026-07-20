import { afterEach, describe, expect, it } from 'vitest'

import { api } from './client'

describe('api client auth', () => {
  afterEach(() => {
    localStorage.clear()
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
})
