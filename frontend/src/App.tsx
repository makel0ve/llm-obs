import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { lazy, Suspense, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { BrowserRouter, Routes, Route, Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api } from './api/client'
import {
  createProject,
  dashboardQueryKeys,
  listAccessibleProjects,
  loginUser,
  registerUser,
  type AccessibleProjectRecord,
  type ProjectCreateResponse,
  type UserRole,
} from './api/dashboard'

const queryClient = new QueryClient()
const Overview = lazy(() => import('./pages/Overview').then(module => ({ default: module.Overview })))
const Traces = lazy(() => import('./pages/Traces').then(module => ({ default: module.Traces })))
const TraceDetail = lazy(() => import('./pages/TraceDetail').then(module => ({ default: module.TraceDetail })))
const Alerts = lazy(() => import('./pages/Alerts').then(module => ({ default: module.Alerts })))
const ProjectUsers = lazy(() => import('./pages/ProjectUsers').then(module => ({ default: module.ProjectUsers })))
const ProjectSettings = lazy(() => import('./pages/ProjectSettings').then(module => ({ default: module.ProjectSettings })))
const OrganizationSettings = lazy(() => import('./pages/OrganizationSettings').then(module => ({ default: module.OrganizationSettings })))
const Pricing = lazy(() => import('./pages/Pricing').then(module => ({ default: module.Pricing })))
const Users = lazy(() => import('./pages/Users').then(module => ({ default: module.Users })))
const AuditLog = lazy(() => import('./pages/AuditLog').then(module => ({ default: module.AuditLog })))
const AcceptInvite = lazy(() => import('./pages/AcceptInvite').then(module => ({ default: module.AcceptInvite })))

type AuthMode = 'login' | 'register'
type DashboardNavItem = {
  label: string
  path: string
  end?: boolean
  adminOnly?: boolean
}

const dashboardNavItems: DashboardNavItem[] = [
  { label: 'Overview', path: '/dashboard', end: true },
  { label: 'Traces', path: '/dashboard/traces' },
  { label: 'Alerts', path: '/dashboard/alerts' },
  { label: 'Users', path: '/dashboard/users', adminOnly: true },
  { label: 'Project Settings', path: '/dashboard/project-settings', adminOnly: true },
]

const organizationNavItems: DashboardNavItem[] = [
  { label: 'Organization Settings', path: '/admin-settings', adminOnly: true },
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

function DashboardNav({
  role,
  variant = 'desktop',
  area,
}: {
  role: UserRole
  variant?: 'desktop' | 'mobile'
  area: 'organization' | 'project'
}) {
  const isMobile = variant === 'mobile'
  const visibleItems = (area === 'organization' ? organizationNavItems : dashboardNavItems)
    .filter(item => !item.adminOnly || role === 'admin')

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

function ProjectSwitcher({
  projectId,
  projects,
  isLoading,
  isError,
  role,
  onProjectChange,
}: {
  projectId: string
  projects: AccessibleProjectRecord[]
  isLoading: boolean
  isError: boolean
  role: UserRole
  onProjectChange: (projectId: string) => void
}) {
  if (isLoading) {
    return <div className="text-xs text-gray-500">Loading projects...</div>
  }

  if (isError) {
    return <div className="text-xs text-red-600">Projects unavailable</div>
  }

  if (projects.length === 0) {
    return <div className="text-xs text-amber-700">{role === 'admin' ? 'No active project' : 'No project access'}</div>
  }

  return (
    <label className="mt-1 block">
      <span className="sr-only">Active project</span>
      <select
        value={projectId}
        onChange={event => onProjectChange(event.target.value)}
        className="max-w-full rounded-md border border-gray-200 bg-white px-2 py-1 text-xs font-medium text-gray-700 shadow-sm hover:border-gray-300 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
      >
        {projects.map(project => (
          <option key={project.id} value={project.id}>
            {`${project.name} (${project.project_role})`}
          </option>
        ))}
      </select>
    </label>
  )
}

function useAccessibleProjects() {
  return useQuery({
    queryKey: dashboardQueryKeys.accessibleProjects(),
    queryFn: listAccessibleProjects,
    retry: false,
  })
}

function NoProjectAccess({ role, isLoading, isError }: { role: UserRole; isLoading: boolean; isError: boolean }) {
  if (isLoading) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-600">
          Loading project access...
        </div>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-800">
          Project access could not be loaded. Sign in again or contact an organization admin.
        </div>
      </div>
    )
  }

  if (role === 'admin') {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-800">
          No active project exists. Create a project to open dashboard data.
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-6">
        <h1 className="text-lg font-semibold text-amber-950">No project access</h1>
        <p className="mt-2 text-sm leading-6 text-amber-800">
          Your account is active, but it is not assigned to any project. Contact an organization admin to request project access.
        </p>
      </div>
    </div>
  )
}

function ProjectSelectionLanding({
  onProjectChange,
}: {
  onProjectChange: (projectId: string) => void
}) {
  const navigate = useNavigate()
  const projectsQuery = useAccessibleProjects()
  const projects = projectsQuery.data ?? []

  const openProject = (projectId: string) => {
    onProjectChange(projectId)
    window.setTimeout(() => navigate('/dashboard'), 0)
  }

  if (projectsQuery.isLoading) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-32 animate-pulse rounded-lg bg-gray-100" />
          ))}
        </div>
      </div>
    )
  }

  if (projectsQuery.isError) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-800">
          Project access could not be loaded. Sign in again or contact an organization admin.
        </div>
      </div>
    )
  }

  if (projects.length === 0) {
    return <NoProjectAccess role="viewer" isLoading={false} isError={false} />
  }

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-950">Projects</h1>
        <p className="mt-1 text-sm text-gray-500">Open a project to view traces, alerts and settings.</p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {projects.map(project => (
          <button
            key={project.id}
            type="button"
            onClick={() => openProject(project.id)}
            className="min-h-32 rounded-lg border border-gray-200 bg-white p-4 text-left shadow-sm transition hover:border-blue-300 hover:bg-blue-50 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="truncate text-base font-semibold text-gray-950">{project.name}</h2>
                <p className="mt-1 text-xs font-medium uppercase tracking-wide text-gray-500">
                  {project.project_role}
                </p>
              </div>
              <span className="rounded-full bg-green-50 px-2 py-1 text-xs font-medium text-green-700">
                Active
              </span>
            </div>
            <dl className="mt-5 grid grid-cols-2 gap-3 text-xs">
              <div>
                <dt className="text-gray-500">Retention</dt>
                <dd className="mt-1 font-medium text-gray-900">{project.retention_days}d</dd>
              </div>
              <div>
                <dt className="text-gray-500">Payloads</dt>
                <dd className="mt-1 font-medium text-gray-900">{project.payload_storage_mode}</dd>
              </div>
            </dl>
          </button>
        ))}
      </div>
    </div>
  )
}

function ProjectCreatePanel({
  error,
  isCreating,
  onCancel,
  onCreate,
}: {
  error: string
  isCreating: boolean
  onCancel: () => void
  onCreate: (name: string) => void
}) {
  const [name, setName] = useState('')

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    const trimmed = name.trim()
    if (trimmed) {
      onCreate(trimmed)
    }
  }

  return (
    <div className="border-b border-gray-200 bg-white px-4 py-4 sm:px-6">
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 md:flex-row md:items-end">
        <label className="min-w-0 flex-1">
          <span className="text-xs font-medium text-gray-600">Project name</span>
          <input
            value={name}
            onChange={event => setName(event.target.value)}
            minLength={1}
            maxLength={255}
            required
            autoFocus
            className="mt-1 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-100"
            placeholder="Production API"
          />
        </label>
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={isCreating}
            className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isCreating ? 'Creating...' : 'Create project'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-950"
          >
            Cancel
          </button>
        </div>
      </form>
      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
    </div>
  )
}

function OneTimeApiKeyBanner({
  title,
  apiKey,
  onDismiss,
}: {
  title: string
  apiKey: string
  onDismiss: () => void
}) {
  return (
    <div className="border-b border-blue-100 bg-blue-50 px-4 py-4 sm:px-6">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 space-y-2">
          <p className="text-sm font-medium text-blue-950">{title}</p>
          <code className="block max-w-full overflow-x-auto rounded-md border border-blue-200 bg-white px-3 py-2 text-sm text-blue-950">
            {apiKey}
          </code>
          <p className="text-xs text-blue-800">This key is shown once. Store it before dismissing.</p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="w-full rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700 sm:w-auto"
        >
          Dismiss
        </button>
      </div>
    </div>
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
  const [bootstrapToken, setBootstrapToken] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      if (mode === 'register') {
        const trimmedBootstrapToken = bootstrapToken.trim()
        const res = await registerUser({
          email,
          password,
          org_name: orgName,
          ...(trimmedBootstrapToken ? { bootstrap_token: trimmedBootstrapToken } : {}),
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
          : mode === 'register' && status === 403
            ? 'Registration is disabled. Ask an admin for an invite or use the bootstrap token.'
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
            <>
              <input
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 bg-white placeholder-gray-400"
                type="text" placeholder="Organization name"
                value={orgName} onChange={e => setOrgName(e.target.value)} required minLength={2} maxLength={100}
              />
              <input
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm text-gray-900 bg-white placeholder-gray-400"
                type="password" placeholder="Bootstrap token"
                value={bootstrapToken} onChange={e => setBootstrapToken(e.target.value)}
              />
            </>
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
  onProjectChange,
  onDismissApiKey,
  onLogout,
}: {
  projectId: string
  registrationApiKey: string
  role: UserRole
  onProjectChange: (projectId: string) => void
  onDismissApiKey: () => void
  onLogout: () => void
}) {
  const location = useLocation()
  const queryClient = useQueryClient()
  const [showCreateProject, setShowCreateProject] = useState(false)
  const [createProjectError, setCreateProjectError] = useState('')
  const [createdProjectKey, setCreatedProjectKey] = useState<ProjectCreateResponse | null>(null)
  const accessibleProjectsQuery = useAccessibleProjects()
  const projects = useMemo(() => accessibleProjectsQuery.data ?? [], [accessibleProjectsQuery.data])
  const projectQueryIsLoading = accessibleProjectsQuery.isLoading
  const projectQueryIsError = accessibleProjectsQuery.isError
  const selectedProjectExists = projects.some(project => project.id === projectId)
  const isResolvingProject = !projectQueryIsLoading && !projectQueryIsError && projects.length > 0 && !selectedProjectExists
  const canOpenDashboard = selectedProjectExists
  const isProjectSelectionPage = location.pathname === '/'
  const isOrganizationSettingsPage = location.pathname.startsWith('/admin-settings')
  const navigationArea = isProjectSelectionPage || isOrganizationSettingsPage ? 'organization' : 'project'
  const canRenderRoute = canOpenDashboard || isProjectSelectionPage || isOrganizationSettingsPage

  useEffect(() => {
    if (projectQueryIsLoading || projectQueryIsError) return
    if (projects.length === 0) {
      if (projectId) onProjectChange('')
      return
    }

    const selectedExists = projects.some(project => project.id === projectId)
    if (!selectedExists) {
      onProjectChange(projects[0].id)
    }
  }, [
    onProjectChange,
    projectId,
    projects,
    projectQueryIsError,
    projectQueryIsLoading,
  ])
  const createProjectMutation = useMutation({
    mutationFn: createProject,
    onSuccess: async project => {
      setCreateProjectError('')
      setShowCreateProject(false)
      setCreatedProjectKey(project)
      await queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.accessibleProjects() })
      onProjectChange(project.id)
    },
    onError: error => {
      const status = error && typeof error === 'object' && 'response' in error
        ? (error.response as { status?: number } | undefined)?.status
        : undefined
      setCreateProjectError(
        status === 409 ? 'Project name already exists' : 'Could not create project'
      )
    },
  })

  return (
    <div className="min-h-screen bg-gray-50 text-gray-950">
      <header className="sticky top-0 z-20 border-b border-gray-200 bg-white">
        <div className="flex min-h-16 items-center justify-between gap-4 px-4 sm:px-6">
          <div className="min-w-0">
            <NavLink
              to="/"
              className="inline-flex text-base font-semibold text-gray-950 hover:text-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-100"
            >
              LLM Obs
            </NavLink>
            {navigationArea === 'project' && (
              <ProjectSwitcher
                projectId={projectId}
                projects={projects}
                isLoading={projectQueryIsLoading}
                isError={projectQueryIsError}
                role={role}
                onProjectChange={onProjectChange}
              />
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {role === 'admin' && (
              <button
                type="button"
                onClick={() => {
                  setCreateProjectError('')
                  setShowCreateProject(value => !value)
                }}
                className="rounded-md bg-gray-900 px-3 py-2 text-sm font-medium text-white hover:bg-gray-700"
              >
                New project
              </button>
            )}
            <button
              type="button"
              onClick={onLogout}
              className="rounded-md border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-950"
            >
              Logout
            </button>
          </div>
        </div>
        <DashboardNav role={role} variant="mobile" area={navigationArea} />
      </header>

      <div className="lg:flex">
        <aside className="hidden min-h-[calc(100svh-4rem)] w-64 shrink-0 border-r border-gray-200 bg-white lg:block">
          <DashboardNav role={role} area={navigationArea} />
        </aside>
        <main className="min-w-0 flex-1">
          {showCreateProject && role === 'admin' && (
            <ProjectCreatePanel
              error={createProjectError}
              isCreating={createProjectMutation.isPending}
              onCancel={() => {
                setCreateProjectError('')
                setShowCreateProject(false)
              }}
              onCreate={name => createProjectMutation.mutate({ name })}
            />
          )}
          {registrationApiKey && (
            <OneTimeApiKeyBanner
              title="Default project API key"
              apiKey={registrationApiKey}
              onDismiss={onDismissApiKey}
            />
          )}
          {createdProjectKey && (
            <OneTimeApiKeyBanner
              title={`${createdProjectKey.name} API key`}
              apiKey={createdProjectKey.api_key}
              onDismiss={() => setCreatedProjectKey(null)}
            />
          )}
          <div className="min-w-0">
            {canRenderRoute ? (
              <Outlet />
            ) : (
              <NoProjectAccess
                role={role}
                isLoading={projectQueryIsLoading || isResolvingProject}
                isError={projectQueryIsError}
              />
            )}
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

  const handleProjectChange = (pid: string) => {
    localStorage.setItem('projectId', pid)
    setProjectId(pid)
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
                onProjectChange={handleProjectChange}
                onDismissApiKey={() => setRegistrationApiKey('')}
                onLogout={handleLogout}
              />
            </PrivateRoute>
          }>
            <Route index element={<ProjectSelectionLanding onProjectChange={handleProjectChange} />} />
            <Route path="dashboard" element={<LazyPage><Overview projectId={projectId} /></LazyPage>} />
            <Route path="dashboard/traces" element={<LazyPage><Traces projectId={projectId} /></LazyPage>} />
            <Route path="dashboard/traces/:traceId" element={<LazyPage><TraceDetail projectId={projectId} /></LazyPage>} />
            <Route path="dashboard/alerts" element={<LazyPage><Alerts projectId={projectId} role={role} /></LazyPage>} />
            <Route path="dashboard/users" element={<AdminRoute role={role}><LazyPage><ProjectUsers projectId={projectId} /></LazyPage></AdminRoute>} />
            <Route path="dashboard/project-settings" element={<AdminRoute role={role}><LazyPage><ProjectSettings projectId={projectId} /></LazyPage></AdminRoute>} />
            <Route path="admin-settings" element={<AdminRoute role={role}><LazyPage><OrganizationSettings /></LazyPage></AdminRoute>}>
              <Route index element={<Navigate to="users" replace />} />
              <Route path="users" element={<LazyPage><Users role={role} /></LazyPage>} />
              <Route path="pricing" element={<LazyPage><Pricing /></LazyPage>} />
              <Route path="audit-log" element={<LazyPage><AuditLog /></LazyPage>} />
            </Route>
            <Route path="dashboard/admin-settings/*" element={<Navigate to="/admin-settings" replace />} />
            <Route path="dashboard/pricing" element={<Navigate to="/admin-settings/pricing" replace />} />
            <Route path="dashboard/audit-log" element={<Navigate to="/admin-settings/audit-log" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
