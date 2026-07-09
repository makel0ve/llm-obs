import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { lazy, Suspense, useState, type FormEvent, type ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink, Outlet } from 'react-router-dom'
import { api } from './api/client'
import { loginUser, registerUser, type UserRole } from './api/dashboard'

const queryClient = new QueryClient()
const Overview = lazy(() => import('./pages/Overview').then(module => ({ default: module.Overview })))
const Traces = lazy(() => import('./pages/Traces').then(module => ({ default: module.Traces })))
const TraceDetail = lazy(() => import('./pages/TraceDetail').then(module => ({ default: module.TraceDetail })))
const Alerts = lazy(() => import('./pages/Alerts').then(module => ({ default: module.Alerts })))
const ProjectSettings = lazy(() => import('./pages/ProjectSettings').then(module => ({ default: module.ProjectSettings })))
const Pricing = lazy(() => import('./pages/Pricing').then(module => ({ default: module.Pricing })))
const Users = lazy(() => import('./pages/Users').then(module => ({ default: module.Users })))
const AcceptInvite = lazy(() => import('./pages/AcceptInvite').then(module => ({ default: module.AcceptInvite })))

type AuthMode = 'login' | 'register'
type DashboardNavItem = {
  label: string
  path: string
  end?: boolean
  adminOnly?: boolean
}

const dashboardNavItems: DashboardNavItem[] = [
  { label: 'Overview', path: '/', end: true },
  { label: 'Traces', path: '/traces' },
  { label: 'Alerts', path: '/alerts' },
  { label: 'Pricing', path: '/pricing', adminOnly: true },
  { label: 'Users', path: '/users', adminOnly: true },
  { label: 'Project Settings', path: '/project-settings', adminOnly: true },
]

function isUserRole(value: unknown): value is UserRole {
  return value === 'admin' || value === 'member' || value === 'viewer'
}

function decodeJwtRole(token: string | null) {
  if (!token) return null

  try {
    const payload = token.split('.')[1]
    if (!payload) return null

    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(normalized.length + ((4 - normalized.length % 4) % 4), '=')
    const decoded = JSON.parse(atob(padded)) as { role?: unknown }
    return isUserRole(decoded.role) ? decoded.role : null
  } catch {
    return null
  }
}

function readStoredRole(): UserRole {
  const stored = localStorage.getItem('role')
  if (isUserRole(stored)) return stored

  return decodeJwtRole(localStorage.getItem('token')) ?? 'viewer'
}

function DashboardNav({ role, variant = 'desktop' }: { role: UserRole; variant?: 'desktop' | 'mobile' }) {
  const isMobile = variant === 'mobile'
  const visibleItems = dashboardNavItems.filter(item => !item.adminOnly || role === 'admin')

  return (
    <nav
      className={
        isMobile
          ? 'flex gap-2 overflow-x-auto px-4 py-3 sm:px-6 lg:hidden'
          : 'space-y-1 p-3'
      }
      aria-label="Dashboard"
    >
      {visibleItems.map(item => (
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
  onLogin: (token: string, pid: string, role: UserRole, apiKey?: string) => void
}) {
  const [mode, setMode] = useState<AuthMode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [orgName, setOrgName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (mode === 'register') {
        const res = await registerUser({
          email,
          password,
          org_name: orgName,
        })
        onLogin(res.access_token, res.project_id ?? '', res.role, res.api_key)
      } else {
        const res = await loginUser({ email, password })
        onLogin(res.access_token, res.project_id ?? '', res.role)
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
  role,
  onDismissApiKey,
  onLogout,
}: {
  projectId: string
  registrationApiKey: string
  role: UserRole
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
        <DashboardNav role={role} variant="mobile" />
      </header>

      <div className="lg:flex">
        <aside className="hidden min-h-[calc(100svh-4rem)] w-64 shrink-0 border-r border-gray-200 bg-white lg:block">
          <DashboardNav role={role} />
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

function PageLoader() {
  return (
    <div className="space-y-3 p-4 sm:p-6 lg:p-8">
      <div className="h-10 w-48 animate-pulse rounded-lg bg-gray-100" />
      <div className="h-32 animate-pulse rounded-lg bg-gray-100" />
      <div className="h-32 animate-pulse rounded-lg bg-gray-100" />
    </div>
  )
}

function LazyPage({ children }: { children: ReactNode }) {
  return <Suspense fallback={<PageLoader />}>{children}</Suspense>
}

function PrivateRoute({ children }: { children: ReactNode }) {
  const token = localStorage.getItem('token')
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

function AdminRoute({ role, children }: { role: UserRole; children: ReactNode }) {
  return role === 'admin' ? <>{children}</> : <Navigate to="/" replace />
}

export default function App() {
  const [token, setToken] = useState(localStorage.getItem('token') ?? '')
  const [projectId, setProjectId] = useState(localStorage.getItem('projectId') ?? '')
  const [role, setRole] = useState<UserRole>(readStoredRole)
  const [registrationApiKey, setRegistrationApiKey] = useState('')

  const handleLogin = (t: string, pid: string, userRole: UserRole, apiKey?: string) => {
    localStorage.setItem('token', t)
    localStorage.setItem('projectId', pid)
    localStorage.setItem('role', userRole)
    api.defaults.headers.common['Authorization'] = `Bearer ${t}`
    setToken(t)
    setProjectId(pid)
    setRole(userRole)
    setRegistrationApiKey(apiKey ?? '')
  }

  const handleLogout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('projectId')
    localStorage.removeItem('apiKey')
    localStorage.removeItem('role')
    delete api.defaults.headers.common['Authorization']
    setToken('')
    setProjectId('')
    setRole('viewer')
    setRegistrationApiKey('')
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/accept-invite" element={
            token
              ? <Navigate to="/" replace />
              : <LazyPage><AcceptInvite onLogin={handleLogin} /></LazyPage>
          } />
          <Route path="/login" element={
            token ? <Navigate to="/" replace /> : <LoginPage onLogin={handleLogin} />
          } />
          <Route path="/" element={
            <PrivateRoute>
              <Dashboard
                projectId={projectId}
                registrationApiKey={registrationApiKey}
                role={role}
                onDismissApiKey={() => setRegistrationApiKey('')}
                onLogout={handleLogout}
              />
            </PrivateRoute>
          }>
            <Route index element={<LazyPage><Overview projectId={projectId} /></LazyPage>} />
            <Route path="traces" element={<LazyPage><Traces projectId={projectId} /></LazyPage>} />
            <Route path="traces/:traceId" element={<LazyPage><TraceDetail projectId={projectId} /></LazyPage>} />
            <Route path="alerts" element={<LazyPage><Alerts projectId={projectId} role={role} /></LazyPage>} />
            <Route path="pricing" element={<AdminRoute role={role}><LazyPage><Pricing /></LazyPage></AdminRoute>} />
            <Route path="users" element={<AdminRoute role={role}><LazyPage><Users role={role} /></LazyPage></AdminRoute>} />
            <Route path="project-settings" element={<AdminRoute role={role}><LazyPage><ProjectSettings projectId={projectId} /></LazyPage></AdminRoute>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
