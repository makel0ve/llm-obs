import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import App from '../App'
import { Traces } from '../pages/Traces'
import {
  createProjectApiKey,
  getProjectSettings,
  listAccessibleProjects,
  listFailedTasks,
  listProjectApiKeys,
  listProjectMembers,
  listProjects,
  listTraces,
  listUsers,
  loginUser,
  registerUser,
} from '../api/dashboard'

vi.mock('../api/dashboard', () => ({
  assignProjectMember: vi.fn(),
  createProjectApiKey: vi.fn(),
  createProject: vi.fn(),
  dashboardQueryKeys: {
    accessibleProjects: () => ['accessible-projects'],
    apiKeys: (projectId: string) => ['api-keys', projectId],
    failedTasks: (projectId: string, includeResolved: boolean) => [
      'failed-tasks',
      projectId,
      includeResolved,
    ],
    projectMembers: (projectId: string) => ['project-members', projectId],
    projects: () => ['projects'],
    projectSettings: (projectId: string) => ['project-settings', projectId],
    traces: (
      projectId: string,
      period: string,
      status: string,
      model: string,
    ) => ['traces', projectId, period, status, model],
    users: () => ['users'],
  },
  getProjectSettings: vi.fn(),
  listFailedTasks: vi.fn(),
  listAccessibleProjects: vi.fn(),
  listProjectApiKeys: vi.fn(),
  listProjectMembers: vi.fn(),
  listProjects: vi.fn(),
  listTraces: vi.fn(),
  listUsers: vi.fn(),
  loginUser: vi.fn(),
  removeProjectMember: vi.fn(),
  retryFailedTask: vi.fn(),
  revokeProjectApiKey: vi.fn(),
  rotateProjectApiKey: vi.fn(),
  registerUser: vi.fn(),
  updateProjectSettings: vi.fn(),
}))

const mockedCreateProjectApiKey = vi.mocked(createProjectApiKey)
const mockedGetProjectSettings = vi.mocked(getProjectSettings)
const mockedListAccessibleProjects = vi.mocked(listAccessibleProjects)
const mockedListFailedTasks = vi.mocked(listFailedTasks)
const mockedListProjectApiKeys = vi.mocked(listProjectApiKeys)
const mockedListProjectMembers = vi.mocked(listProjectMembers)
const mockedListProjects = vi.mocked(listProjects)
const mockedListTraces = vi.mocked(listTraces)
const mockedListUsers = vi.mocked(listUsers)
const mockedLoginUser = vi.mocked(loginUser)
const mockedRegisterUser = vi.mocked(registerUser)

const project = {
  id: 'project-1',
  name: 'Production API',
  is_active: true,
  retention_days: 90,
  payload_storage_mode: 'all' as const,
  payload_max_bytes: 262144,
  payload_redact_keys: 'api_key,password,secret,token,authorization',
}

function storeAdminSession(route = '/', selectedProject = project) {
  localStorage.setItem('token', 'admin-token')
  localStorage.setItem('projectId', selectedProject.id)
  localStorage.setItem('role', 'admin')
  window.history.pushState(null, '', route)
}

function renderTracesWithTestClient(projectId: string) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Traces projectId={projectId} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('App', () => {
  beforeEach(() => {
    mockedListAccessibleProjects.mockResolvedValue([])
    mockedListProjects.mockResolvedValue([])
    mockedListTraces.mockResolvedValue({
      traces: [],
      next_cursor: null,
      has_more: false,
    })
    mockedGetProjectSettings.mockResolvedValue({
      retention_days: 90,
      payload_storage_mode: 'all',
      payload_max_bytes: 262144,
      payload_redact_keys: 'api_key,password,secret,token,authorization',
    })
    mockedListProjectApiKeys.mockResolvedValue([])
    mockedListUsers.mockResolvedValue([])
    mockedListProjectMembers.mockResolvedValue([])
    mockedListFailedTasks.mockResolvedValue([])
    mockedCreateProjectApiKey.mockResolvedValue({
      id: 'key-1',
      name: 'Production ingest',
      description: 'Primary ingest key',
      scope: 'ingest',
      is_active: true,
      api_key: 'llmobs_new_scoped_key',
      created_at: '2026-07-14T08:00:00Z',
    })
    mockedLoginUser.mockResolvedValue({
      access_token: 'member-token',
      project_id: 'project-1',
      role: 'member',
    })
    mockedRegisterUser.mockResolvedValue({
      access_token: 'admin-token',
      project_id: 'project-1',
      role: 'admin',
      api_key: 'llmobs_test_key',
    })
  })

  afterEach(() => {
    cleanup()
    localStorage.clear()
    vi.clearAllMocks()
    window.history.pushState(null, '', '/')
  })

  it('renders the sign-in screen when no token is stored', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'LLM Obs' })).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Email')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Password')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Sign in' })).toHaveLength(2)
  })

  it('logs in and stores session values', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.type(screen.getByPlaceholderText('Email'), 'member@example.com')
    await user.type(screen.getByPlaceholderText('Password'), 'secret123')
    await user.click(screen.getAllByRole('button', { name: 'Sign in' })[1])

    expect(mockedLoginUser).toHaveBeenCalledWith({
      email: 'member@example.com',
      password: 'secret123',
    })
    expect(await screen.findAllByText('No project access')).toHaveLength(2)
    expect(localStorage.getItem('token')).toBe('member-token')
    expect(localStorage.getItem('projectId')).toBe('')
    expect(localStorage.getItem('role')).toBe('member')
  })

  it('registers a new account and shows the one-time api key', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Create account' }))
    await user.type(screen.getByPlaceholderText('Organization name'), 'Demo Org')
    await user.type(screen.getByPlaceholderText('Email'), 'admin@example.com')
    await user.type(screen.getByPlaceholderText('Password'), 'secret123')
    await user.click(screen.getAllByRole('button', { name: 'Create account' })[1])

    expect(mockedRegisterUser).toHaveBeenCalledWith({
      email: 'admin@example.com',
      password: 'secret123',
      org_name: 'Demo Org',
    })
    expect(await screen.findByText('Default project API key')).toBeInTheDocument()
    expect(screen.getByText('llmobs_test_key')).toBeInTheDocument()
    expect(localStorage.getItem('role')).toBe('admin')
  })

  it('shows admin-only navigation only for admins', async () => {
    mockedListProjects.mockResolvedValue([])
    localStorage.setItem('token', 'admin-token')
    localStorage.setItem('role', 'admin')

    render(<App />)

    expect(await screen.findAllByRole('link', { name: 'Pricing' })).toHaveLength(2)
    expect(screen.getAllByRole('link', { name: 'Users' })).toHaveLength(2)
    expect(screen.getAllByRole('link', { name: 'Audit Log' })).toHaveLength(2)
    expect(screen.getAllByRole('link', { name: 'Project Settings' })).toHaveLength(2)
  })

  it('hides admin-only navigation for non-admin users', async () => {
    mockedListAccessibleProjects.mockResolvedValue([])
    localStorage.setItem('token', 'member-token')
    localStorage.setItem('role', 'member')

    render(<App />)

    expect(await screen.findAllByText('No project access')).toHaveLength(2)
    expect(screen.queryByRole('link', { name: 'Pricing' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Audit Log' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Project Settings' })).not.toBeInTheDocument()
  })

  it('logs out and clears stored session values', async () => {
    const user = userEvent.setup()
    localStorage.setItem('token', 'admin-token')
    localStorage.setItem('projectId', 'project-1')
    localStorage.setItem('apiKey', 'api-key')
    localStorage.setItem('role', 'admin')

    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Logout' }))

    expect(screen.getByPlaceholderText('Email')).toBeInTheDocument()
    expect(localStorage.getItem('token')).toBeNull()
    expect(localStorage.getItem('projectId')).toBeNull()
    expect(localStorage.getItem('apiKey')).toBeNull()
    expect(localStorage.getItem('role')).toBeNull()
  })

  it('shows trace explorer loading state while traces are pending', async () => {
    const loadingProject = { ...project, id: 'project-loading' }
    mockedListProjects.mockResolvedValue([loadingProject])
    mockedListTraces.mockReturnValue(new Promise(() => {}))
    storeAdminSession('/traces', loadingProject)

    const { container } = render(<App />)

    expect(await screen.findByRole('heading', { name: 'Traces' })).toBeInTheDocument()
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(3)
  })

  it('shows trace explorer empty state when the selected project has no traces', async () => {
    const emptyProject = { ...project, id: 'project-empty' }
    mockedListProjects.mockResolvedValue([emptyProject])
    mockedListTraces.mockResolvedValue({
      traces: [],
      next_cursor: null,
      has_more: false,
    })
    storeAdminSession('/traces', emptyProject)

    render(<App />)

    expect(await screen.findByText('No traces yet')).toBeInTheDocument()
    expect(mockedListTraces).toHaveBeenCalledWith(expect.objectContaining({
      projectId: emptyProject.id,
      status: 'all',
      model: '',
      cursor: null,
    }))
  })

  it('shows trace explorer error state when traces cannot be loaded', async () => {
    const errorProject = { ...project, id: 'project-error' }
    mockedListTraces.mockRejectedValue(new Error('traces unavailable'))

    renderTracesWithTestClient(errorProject.id)

    expect(await screen.findByText(/Could not load traces/i)).toBeInTheDocument()
  })

  it('shows trace explorer data rows for the selected project', async () => {
    const dataProject = { ...project, id: 'project-data' }
    mockedListProjects.mockResolvedValue([dataProject])
    mockedListTraces.mockResolvedValue({
      traces: [
        {
          id: 'trace-alpha-123456',
          started_at: '2026-07-14T08:30:00Z',
          span_count: 3,
          total_tokens: 1234,
          total_cost_usd: '0.4321',
          status: 'error',
        },
      ],
      next_cursor: null,
      has_more: false,
    })
    storeAdminSession('/traces', dataProject)

    render(<App />)

    expect(await screen.findByRole('link', { name: 'trace-al' })).toBeInTheDocument()
    expect(screen.getAllByText('error')).toHaveLength(2)
    expect(screen.getByText('1,234')).toBeInTheDocument()
    expect(screen.getByText('$0.4321')).toBeInTheDocument()
  })

  it('creates a scoped project api key and reveals it once', async () => {
    const user = userEvent.setup()
    mockedListProjects.mockResolvedValue([project])
    storeAdminSession('/project-settings')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Project Settings' })).toBeInTheDocument()
    await user.type(screen.getByPlaceholderText('Production ingest'), 'Production ingest')
    await user.type(screen.getByPlaceholderText('Optional'), 'Primary ingest key')
    await user.click(screen.getByRole('button', { name: 'Create key' }))

    expect(mockedCreateProjectApiKey).toHaveBeenCalledWith(project.id, {
      name: 'Production ingest',
      description: 'Primary ingest key',
      scope: 'ingest',
    })
    expect(await screen.findByText('Save this API key now. It is shown once and cannot be recovered later.')).toBeInTheDocument()
    expect(screen.getByText('llmobs_new_scoped_key')).toBeInTheDocument()
  })
})
