import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink, Outlet } from 'react-router-dom'
import { Overview } from './pages/Overview'
import { Traces } from './pages/Traces'
import { TraceDetail } from './pages/TraceDetail'
import { ProjectSettings } from './pages/ProjectSettings'
import { Alerts } from './pages/Alerts'
import { api } from './api/client'

const queryClient = new QueryClient()

type AuthMode = 'login' | 'register'
type DashboardNavItem = {
  label: string
  path: string
  end?: boolean
}

const dashboardNavItems: DashboardNavItem[] = [
  { label: 'Overview', path: '/', end: true },
  { label: 'Traces', path: '/traces' },
  { label: 'Alerts', path: '/alerts' },
  { label: 'Project Settings', path: '/project-settings' },
]

function DashboardNav({ variant = 'desktop' }: { variant?: 'desktop' | 'mobile' }) {
  const isMobile = variant === 'mobile'

  return (
    <nav
      className={
        isMobile
          ? 'flex gap-2 overflow-x-auto px-4 py-3 sm:px-6 lg:hidden'
          : 'space-y-1 p-3'
      }
      aria-label="Dashboard"
    >
      {dashboardNavItems.map(item => (
        <NavLink
          key={item.path}
          to={item.path}
          end={item.end}
          className={({ isActive }) =>
            [
              'flex min-h-10 items-center whitespace-nowrap rounded-md px-3 text-sm font-medium transition',
              isMobile ? 'justify-center border' : 'w-full',
              isActive
                ? 'border-blue-200 bg-blue-50 text-blue-700'
                : 'border-gray-200 text-gray-600 hover:bg-gray-100 hover:text-gray-950',
            ].join(' ')
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  )
}

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
  onLogout,
}: {
  projectId: string
  registrationApiKey: string
  onDismissApiKey: () => void
  onLogout: () => void
}) {
  return (
    <div className="min-h-screen bg-gray-50 text-gray-950">
      <header className="sticky top-0 z-20 border-b border-gray-200 bg-white">
        <div className="flex min-h-16 items-center justify-between gap-4 px-4 sm:px-6">
          <div className="min-w-0">
            <div className="text-base font-semibold text-gray-950">LLM Obs</div>
            <div className="truncate text-xs text-gray-500">Project {projectId || 'not selected'}</div>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="rounded-md border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-950"
          >
            Logout
          </button>
        </div>
        <DashboardNav variant="mobile" />
      </header>

      <div className="lg:flex">
        <aside className="hidden min-h-[calc(100svh-4rem)] w-64 shrink-0 border-r border-gray-200 bg-white lg:block">
          <DashboardNav />
        </aside>
        <main className="min-w-0 flex-1">
          {registrationApiKey && (
            <div className="border-b border-blue-100 bg-blue-50 px-4 py-4 sm:px-6">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0 space-y-2">
                  <p className="text-sm font-medium text-blue-950">Default project API key</p>
                  <code className="block max-w-full overflow-x-auto rounded-md border border-blue-200 bg-white px-3 py-2 text-sm text-blue-950">
                    {registrationApiKey}
                  </code>
                  <p className="text-xs text-blue-800">This key is shown once. Store it before dismissing.</p>
                </div>
                <button
                  type="button"
                  onClick={onDismissApiKey}
                  className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 sm:w-auto"
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}
          <div className="min-w-0">
            <Outlet />
          </div>
        </main>
      </div>
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
    api.defaults.headers.common['Authorization'] = `Bearer ${t}`
    setToken(t)
    setProjectId(pid)
    setRegistrationApiKey(apiKey ?? '')
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('projectId')
    localStorage.removeItem('apiKey')
    delete api.defaults.headers.common['Authorization']
    setToken('')
    setProjectId('')
    setRegistrationApiKey('')
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
                onLogout={handleLogout}
              />
            </PrivateRoute>
          }>
            <Route index element={<Overview projectId={projectId} />} />
            <Route path="traces" element={<Traces projectId={projectId} />} />
            <Route path="traces/:traceId" element={<TraceDetail projectId={projectId} />} />
            <Route path="alerts" element={<Alerts projectId={projectId} />} />
            <Route path="project-settings" element={<ProjectSettings projectId={projectId} />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
