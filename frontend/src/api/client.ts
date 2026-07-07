import axios from 'axios';

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
    if (error.response?.status === 401 && !isAuthEndpoint) {
      localStorage.removeItem('token')
      localStorage.removeItem('apiKey')
      localStorage.removeItem('projectId')
      window.location.href = '/'
    }
    return Promise.reject(error)
  }
)
