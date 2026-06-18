import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Overview } from './pages/Overview'
import { api } from './api/client'

const queryClient = new QueryClient()

type AuthMode = 'login' | 'register'

function LoginPage({
  onLogin,
}: {
  onLogin: (token: string, pid: string, apiKey?: string) => void
}) {
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [orgName, setOrgName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (mode === 'register') {
        const res = await api.post('/v1/auth/register', {
          email,
          password,
          org_name: orgName,
        })
        onLogin(res.data.access_token, res.data.project_id ?? '', res.data.api_key)
      } else {
        const res = await api.post('/v1/auth/login', { email, password })
        onLogin(res.data.access_token, res.data.project_id ?? '')
      }
    } catch (err) {
      const status = err && typeof err === 'object' && 'response' in err
        ? (err.response as { status?: number } | undefined)?.status
        : undefined
      setError(
        mode === 'register' && status === 409
          ? 'Email already registered'
          : mode === 'register'
            ? 'Could not create account'
            : 'Invalid email or password'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white p-8 rounded-xl border w-full max-w-sm space-y-4">
        <h1 className="text-xl font-semibold text-gray-900">LLM Obs</h1>
        <div className="grid grid-cols-2 rounded border border-gray-200 bg-gray-50 p-1 text-sm">
          <button
            type="button"
            onClick={() => { setMode('login'); setError('') }}
            className={`rounded px-3 py-2 font-medium ${mode === 'login' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}
          >
            Sign in
          </button>
          <button
            type="button"
            onClick={() => { setMode('register'); setError('') }}
            className={`rounded px-3 py-2 font-medium ${mode === 'register' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}
          >
            Create account
          </button>
        </div>
        <form onSubmit={handleSubmit} className="space-y-3">
          {mode === 'register' && (
            <input
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 bg-white placeholder-gray-400"
              type="text" placeholder="Organization name"
              value={orgName} onChange={e => setOrgName(e.target.value)} required minLength={2} maxLength={100}
            />
          )}
          <input
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 bg-white placeholder-gray-400"
            type="email" placeholder="Email"
            value={email} onChange={e => setEmail(e.target.value)} required
          />
          <input
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 bg-white placeholder-gray-400"
            type="password" placeholder="Password"
            value={password} onChange={e => setPassword(e.target.value)} required
          />
          {error && <p className="text-red-500 text-sm">{error}</p>}
          <button
            type="submit" disabled={loading}
            className="w-full bg-blue-600 text-white rounded px-3 py-2 text-sm font-medium disabled:opacity-50"
          >
            {loading
              ? mode === 'register' ? 'Creating account...' : 'Signing in...'
              : mode === 'register' ? 'Create account' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}

function Dashboard({
  projectId,
  registrationApiKey,
  onDismissApiKey,
}: {
  projectId: string
  registrationApiKey: string
  onDismissApiKey: () => void
}) {
  useEffect(() => {
    const token = localStorage.getItem('token')
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`
    }
  }, [])

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b px-6 py-3 flex items-center justify-between">
        <span className="font-semibold text-gray-900">LLM Obs</span>
        <button
          onClick={() => { localStorage.clear(); window.location.href = '/login' }}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Logout
        </button>
      </header>
      {registrationApiKey && (
        <div className="border-b border-blue-100 bg-blue-50 px-6 py-4">
          <div className="mx-auto flex max-w-6xl flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 space-y-2">
              <p className="text-sm font-medium text-blue-950">Default project API key</p>
              <code className="block overflow-x-auto rounded border border-blue-200 bg-white px-3 py-2 text-sm text-blue-950">
                {registrationApiKey}
              </code>
              <p className="text-xs text-blue-800">This key is shown once. Store it before dismissing.</p>
            </div>
            <button
              type="button"
              onClick={onDismissApiKey}
              className="shrink-0 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
      <Overview projectId={projectId} />
    </div>
  )
}

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('token')
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token') ?? '')
  const [projectId, setProjectId] = useState(localStorage.getItem('projectId') ?? '')
  const [registrationApiKey, setRegistrationApiKey] = useState('')

  const handleLogin = (t: string, pid: string, apiKey?: string) => {
    localStorage.setItem('token', t)
    localStorage.setItem('projectId', pid)
    setToken(t)
    setProjectId(pid)
    setRegistrationApiKey(apiKey ?? '')
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={
            token ? <Navigate to="/" replace /> : <LoginPage onLogin={handleLogin} />
          } />
          <Route path="/" element={
            <PrivateRoute>
              <Dashboard
                projectId={projectId}
                registrationApiKey={registrationApiKey}
                onDismissApiKey={() => setRegistrationApiKey('')}
              />
            </PrivateRoute>
          } />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
