import axios from 'axios';
import {
  clearStoredSession,
  isUnauthorizedApiError,
  SESSION_EXPIRED_EVENT,
} from './errors'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  response => response,
  error => {
    const url = String(error.config?.url ?? '')
    const isAuthEndpoint = url.includes('/v1/auth/')
    if (isUnauthorizedApiError(error) && !isAuthEndpoint) {
      clearStoredSession()
      delete api.defaults.headers.common['Authorization']
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
    }
    return Promise.reject(error)
  }
)
