import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import App from '../App'
import { Overview } from '../pages/Overview'
import { Traces } from '../pages/Traces'
import {
  acceptOrganizationInvite,
  assignProjectMember,
  createAlertRule,
  createOrganizationUser,
  createPricing,
  createProjectApiKey,
  getMetricsAnalytics,
  getMetricsOverview,
  getMetricsTimeseries,
  getProjectSettings,
  getTraceDetail,
  listAlertEvents,
  listAlertRules,
  listAuditEvents,
  listAccessibleProjects,
  listFailedTasks,
  listPricing,
  listProjectApiKeys,
  listProjectMembers,
  listProjects,
  listTraces,
  listUserProjectAccess,
  listUsers,
  loginUser,
  removeProjectMember,
  registerUser,
  resolveAlertEvent,
  retryFailedTask,
} from '../api/dashboard'

vi.mock('../api/dashboard', () => ({
  acceptOrganizationInvite: vi.fn(),
  assignProjectMember: vi.fn(),
  createAlertRule: vi.fn(),
  createOrganizationUser: vi.fn(),
  createPricing: vi.fn(),
  createProjectApiKey: vi.fn(),
  createProject: vi.fn(),
  dashboardQueryKeys: {
    accessibleProjects: () => ['accessible-projects'],
    alertEvents: (projectId: string) => ['alert-events', projectId],
    alertRules: (projectId: string) => ['alert-rules', projectId],
    analytics: (projectId: string, period: string) => [
      'metrics',
      'analytics',
      projectId,
      period,
    ],
    apiKeys: (projectId: string) => ['api-keys', projectId],
    failedTasks: (projectId: string, includeResolved: boolean) => [
      'failed-tasks',
      projectId,
      includeResolved,
    ],
    overview: (projectId: string, period: string) => [
      'metrics',
      'overview',
      projectId,
      period,
    ],
    pricing: (provider: string, model: string, includeExpired: boolean) => [
      'pricing',
      provider,
      model,
      includeExpired,
    ],
    projectMembers: (projectId: string) => ['project-members', projectId],
    projects: () => ['projects'],
    projectSettings: (projectId: string) => ['project-settings', projectId],
    timeseries: (projectId: string, period: string) => [
      'metrics',
      'timeseries',
      projectId,
      period,
    ],
    traces: (
      projectId: string,
      period: string,
      status: string,
      model: string,
    ) => ['traces', projectId, period, status, model],
    traceDetail: (
      projectId: string,
      traceId: string | undefined,
      startedAt: string | null,
      includePayload: boolean,
    ) => ['trace-detail', projectId, traceId, startedAt, includePayload],
    auditEvents: (
      action: string,
      userId: string,
      fromDt: string,
      toDt: string,
      cursor: string,
    ) => ['audit-events', action, userId, fromDt, toDt, cursor],
    userProjectAccess: (userId: string) => ['user-project-access', userId],
    users: () => ['users'],
  },
  deleteAlertRule: vi.fn(),
  getMetricsAnalytics: vi.fn(),
  getMetricsOverview: vi.fn(),
  getMetricsTimeseries: vi.fn(),
  getProjectSettings: vi.fn(),
  getTraceDetail: vi.fn(),
  endPricing: vi.fn(),
  listAlertEvents: vi.fn(),
  listAlertRules: vi.fn(),
  listAuditEvents: vi.fn(),
  listFailedTasks: vi.fn(),
  listAccessibleProjects: vi.fn(),
  listPricing: vi.fn(),
  listProjectApiKeys: vi.fn(),
  listProjectMembers: vi.fn(),
  listProjects: vi.fn(),
  listTraces: vi.fn(),
  listUserProjectAccess: vi.fn(),
  listUsers: vi.fn(),
  loginUser: vi.fn(),
  removeProjectMember: vi.fn(),
  resolveAlertEvent: vi.fn(),
  retryFailedTask: vi.fn(),
  revokeProjectApiKey: vi.fn(),
  rotateProjectApiKey: vi.fn(),
  registerUser: vi.fn(),
  deleteOrganizationUser: vi.fn(),
  updateAlertRule: vi.fn(),
  updateOrganizationUserRole: vi.fn(),
  updatePricing: vi.fn(),
  updateProjectSettings: vi.fn(),
}))

const mockedAcceptOrganizationInvite = vi.mocked(acceptOrganizationInvite)
const mockedAssignProjectMember = vi.mocked(assignProjectMember)
const mockedCreateAlertRule = vi.mocked(createAlertRule)
const mockedCreateOrganizationUser = vi.mocked(createOrganizationUser)
const mockedCreatePricing = vi.mocked(createPricing)
const mockedCreateProjectApiKey = vi.mocked(createProjectApiKey)
const mockedGetMetricsAnalytics = vi.mocked(getMetricsAnalytics)
const mockedGetMetricsOverview = vi.mocked(getMetricsOverview)
const mockedGetMetricsTimeseries = vi.mocked(getMetricsTimeseries)
const mockedGetProjectSettings = vi.mocked(getProjectSettings)
const mockedGetTraceDetail = vi.mocked(getTraceDetail)
const mockedListAlertEvents = vi.mocked(listAlertEvents)
const mockedListAlertRules = vi.mocked(listAlertRules)
const mockedListAuditEvents = vi.mocked(listAuditEvents)
const mockedListAccessibleProjects = vi.mocked(listAccessibleProjects)
const mockedListFailedTasks = vi.mocked(listFailedTasks)
const mockedListPricing = vi.mocked(listPricing)
const mockedListProjectApiKeys = vi.mocked(listProjectApiKeys)
const mockedListProjectMembers = vi.mocked(listProjectMembers)
const mockedListProjects = vi.mocked(listProjects)
const mockedListTraces = vi.mocked(listTraces)
const mockedListUserProjectAccess = vi.mocked(listUserProjectAccess)
const mockedListUsers = vi.mocked(listUsers)
const mockedLoginUser = vi.mocked(loginUser)
const mockedRemoveProjectMember = vi.mocked(removeProjectMember)
const mockedRegisterUser = vi.mocked(registerUser)
const mockedResolveAlertEvent = vi.mocked(resolveAlertEvent)
const mockedRetryFailedTask = vi.mocked(retryFailedTask)

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

function renderOverviewWithTestClient(projectId: string) {
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
        <Overview projectId={projectId} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('App', () => {
  beforeEach(() => {
    mockedAcceptOrganizationInvite.mockResolvedValue({
      access_token: 'invite-token-auth',
      project_id: 'project-1',
      role: 'member',
    })
    mockedCreateAlertRule.mockResolvedValue(undefined)
    mockedCreatePricing.mockResolvedValue({
      id: 2,
      provider: 'openai',
      model: 'gpt-4o-mini',
      input_cost_per_1k_tokens: '0.00015',
      output_cost_per_1k_tokens: '0.0006',
      valid_from: '2026-07-28T08:00:00Z',
      valid_to: null,
    })
    mockedGetMetricsOverview.mockResolvedValue({
      total_spans: 0,
      p95_latency_ms: 0,
      error_rate_pct: 0,
      total_cost_usd: 0,
    })
    mockedGetMetricsTimeseries.mockResolvedValue([])
    mockedGetMetricsAnalytics.mockResolvedValue({
      cost_by_model: [],
      cost_by_provider: [],
      cost_over_time: [],
      latency_by_model: [],
      latency_by_provider: [],
      top_expensive_traces: [],
      slowest_traces: [],
      error_rate_trend: [],
      top_error_messages: [],
      errors_by_model: [],
      errors_by_provider: [],
      recent_failed_traces: [],
      error_fingerprints: [],
    })
    mockedListAlertRules.mockResolvedValue([])
    mockedListAlertEvents.mockResolvedValue([])
    mockedListAuditEvents.mockResolvedValue({ events: [], next_cursor: null })
    mockedListAccessibleProjects.mockResolvedValue([])
    mockedListProjects.mockResolvedValue([project])
    mockedListPricing.mockResolvedValue([])
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
    mockedGetTraceDetail.mockResolvedValue({
      id: 'trace-1',
      project_id: project.id,
      started_at: '2026-07-28T08:00:00Z',
      ended_at: '2026-07-28T08:00:02Z',
      total_tokens: 42,
      total_cost_usd: '0.0042',
      span_count: 1,
      status: 'ok',
      spans: [],
    })
    mockedListProjectApiKeys.mockResolvedValue([])
    mockedListUsers.mockResolvedValue([])
    mockedListProjectMembers.mockResolvedValue([])
    mockedListUserProjectAccess.mockResolvedValue([])
    mockedListFailedTasks.mockResolvedValue([])
    mockedAssignProjectMember.mockResolvedValue({
      user_id: 'org-user-1',
      email: 'org-user@example.com',
      org_role: 'member',
      project_role: 'member',
      is_active: true,
      created_at: '2026-07-15T08:00:00Z',
      updated_at: '2026-07-15T08:00:00Z',
    })
    mockedRemoveProjectMember.mockResolvedValue(undefined)
    mockedResolveAlertEvent.mockResolvedValue(undefined)
    mockedCreateProjectApiKey.mockResolvedValue({
      id: 'key-1',
      name: 'Production ingest',
      description: 'Primary ingest key',
      scope: 'ingest',
      is_active: true,
      api_key: 'llmobs_new_scoped_key',
      created_at: '2026-07-14T08:00:00Z',
    })
    mockedCreateOrganizationUser.mockResolvedValue({
      id: 'invite-1',
      email: 'viewer@example.com',
      role: 'viewer',
      project_assignments: [],
      invite_token: 'invite-token',
      expires_at: '2026-07-15T08:00:00Z',
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
    expect(await screen.findAllByText('No project access')).toHaveLength(1)
    expect(screen.queryByLabelText('Active project')).not.toBeInTheDocument()
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

  it('sends a bootstrap token when creating the first admin', async () => {
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Create account' }))
    await user.type(screen.getByPlaceholderText('Organization name'), 'Bootstrap Org')
    await user.type(screen.getByPlaceholderText('Bootstrap token'), 'bootstrap-secret')
    await user.type(screen.getByPlaceholderText('Email'), 'admin@example.com')
    await user.type(screen.getByPlaceholderText('Password'), 'secret123')
    await user.click(screen.getAllByRole('button', { name: 'Create account' })[1])

    expect(mockedRegisterUser).toHaveBeenCalledWith({
      email: 'admin@example.com',
      password: 'secret123',
      org_name: 'Bootstrap Org',
      bootstrap_token: 'bootstrap-secret',
    })
  })

  it('shows a closed-registration error when registration is disabled', async () => {
    mockedRegisterUser.mockRejectedValueOnce({ response: { status: 403 } })
    const user = userEvent.setup()
    render(<App />)

    await user.click(screen.getByRole('button', { name: 'Create account' }))
    await user.type(screen.getByPlaceholderText('Organization name'), 'Demo Org')
    await user.type(screen.getByPlaceholderText('Email'), 'admin@example.com')
    await user.type(screen.getByPlaceholderText('Password'), 'secret123')
    await user.click(screen.getAllByRole('button', { name: 'Create account' })[1])

    expect(
      await screen.findByText('Registration is disabled. Ask an admin for an invite or use the bootstrap token.'),
    ).toBeInTheDocument()
  })

  it('accepts an invite and stores the returned session values', async () => {
    const user = userEvent.setup()
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'member' }])
    window.history.pushState(null, '', '/accept-invite?token=invite-token')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Accept invite' })).toBeInTheDocument()
    await user.type(screen.getByLabelText('Password'), 'secret123')
    await user.type(screen.getByLabelText('Confirm password'), 'secret123')
    await user.click(screen.getByRole('button', { name: 'Join organization' }))

    expect(mockedAcceptOrganizationInvite).toHaveBeenCalledWith({
      token: 'invite-token',
      password: 'secret123',
    })
    expect(await screen.findByRole('heading', { name: 'Projects' })).toBeInTheDocument()
    expect(localStorage.getItem('token')).toBe('invite-token-auth')
    expect(localStorage.getItem('projectId')).toBe(project.id)
    expect(localStorage.getItem('role')).toBe('member')
  })

  it('shows admin-only navigation only for admins', async () => {
    mockedListAccessibleProjects.mockResolvedValue([])
    localStorage.setItem('token', 'admin-token')
    localStorage.setItem('role', 'admin')

    render(<App />)

    expect(await screen.findAllByRole('link', { name: 'Organization Settings' })).toHaveLength(2)
    expect(screen.queryByRole('link', { name: 'Project Settings' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Pricing' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Audit Log' })).not.toBeInTheDocument()
  })

  it('hides admin-only navigation for non-admin users', async () => {
    mockedListAccessibleProjects.mockResolvedValue([])
    localStorage.setItem('token', 'member-token')
    localStorage.setItem('role', 'member')

    render(<App />)

    expect(await screen.findAllByText('No project access')).toHaveLength(1)
    expect(screen.queryByLabelText('Active project')).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Pricing' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Users' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Audit Log' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Project Settings' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Organization Settings' })).not.toBeInTheDocument()
  })

  it('groups organization-wide admin controls under organization settings', async () => {
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    storeAdminSession('/admin-settings/users')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Organization Settings' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Users' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Users' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Pricing' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Audit Log' })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Organization Settings' })).toHaveLength(2)
  })

  it('creates an organization invite with project access but no organization role selector', async () => {
    const user = userEvent.setup()
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    mockedCreateOrganizationUser.mockResolvedValue({
      id: 'invite-1',
      email: 'teammate@example.com',
      role: 'member',
      project_assignments: [{ project_id: project.id, role: 'member' }],
      invite_token: 'invite-token',
      expires_at: '2026-07-15T08:00:00Z',
    })
    storeAdminSession('/admin-settings/users')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument()
    const inviteSection = screen.getByRole('heading', { name: 'Invite user' }).closest('section')
    expect(inviteSection).not.toBeNull()
    expect(within(inviteSection as HTMLElement).queryByText('Role')).not.toBeInTheDocument()
    expect(screen.getByText('Project access')).toBeInTheDocument()
    expect(screen.getByLabelText('Production API project role')).toHaveValue('none')
    await user.type(screen.getByPlaceholderText('teammate@example.com'), 'teammate@example.com')
    await user.selectOptions(screen.getByLabelText('Production API project role'), 'member')
    await user.click(screen.getByRole('button', { name: 'Create invite' }))

    expect(mockedCreateOrganizationUser.mock.calls[0][0]).toEqual({
      email: 'teammate@example.com',
      role: 'member',
      project_assignments: [{ project_id: project.id, role: 'member' }],
    })
  })

  it('edits project access for an existing organization user', async () => {
    const user = userEvent.setup()
    const secondProject = {
      ...project,
      id: 'project-2',
      name: 'Search API',
      retention_days: 60,
    }
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    mockedListUsers.mockResolvedValue([
      {
        id: 'org-user-1',
        email: 'org-user@example.com',
        role: 'member',
        is_active: true,
        created_at: '2026-07-15T08:00:00Z',
      },
    ])
    mockedListUserProjectAccess.mockResolvedValue([
      {
        project_id: project.id,
        project_name: project.name,
        project_role: null,
        is_active: true,
        retention_days: project.retention_days,
      },
      {
        project_id: secondProject.id,
        project_name: secondProject.name,
        project_role: 'viewer',
        is_active: true,
        retention_days: secondProject.retention_days,
      },
    ])
    storeAdminSession('/admin-settings/users')

    render(<App />)

    expect(await screen.findByText('org-user@example.com')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Project access' }))

    expect(await screen.findByLabelText('Production API existing user project role')).toHaveValue('none')
    expect(screen.getByLabelText('Search API existing user project role')).toHaveValue('viewer')

    await user.selectOptions(screen.getByLabelText('Production API existing user project role'), 'member')

    expect(mockedAssignProjectMember).toHaveBeenCalledWith(project.id, {
      user_id: 'org-user-1',
      role: 'member',
    })

    await user.selectOptions(screen.getByLabelText('Search API existing user project role'), 'member')

    expect(mockedAssignProjectMember).toHaveBeenCalledWith(secondProject.id, {
      user_id: 'org-user-1',
      role: 'member',
    })

    await user.selectOptions(screen.getByLabelText('Search API existing user project role'), 'none')

    expect(mockedRemoveProjectMember).toHaveBeenCalledWith(secondProject.id, 'org-user-1')
  })

  it('shows implicit project access for organization admins', async () => {
    const user = userEvent.setup()
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    mockedListUsers.mockResolvedValue([
      {
        id: 'admin-user-1',
        email: 'admin@example.com',
        role: 'admin',
        is_active: true,
        created_at: '2026-07-15T08:00:00Z',
      },
    ])
    mockedListUserProjectAccess.mockResolvedValue([
      {
        project_id: project.id,
        project_name: project.name,
        project_role: 'admin',
        is_active: true,
        retention_days: project.retention_days,
      },
    ])
    storeAdminSession('/admin-settings/users')

    render(<App />)

    expect(await screen.findByText('admin@example.com')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Project access' }))

    const projectRole = await screen.findByLabelText('Production API existing user project role')
    expect(projectRole).toHaveValue('admin')
    expect(projectRole).toBeDisabled()
  })

  it('shows project settings in project navigation after selecting a project', async () => {
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    storeAdminSession('/dashboard')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: 'Users' })).toHaveLength(2)
    expect(screen.getAllByRole('link', { name: 'Project Settings' })).toHaveLength(2)
    expect(screen.queryByRole('link', { name: 'Organization Settings' })).not.toBeInTheDocument()
  })

  it('shows only users with access to the selected project', async () => {
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    mockedListProjectMembers.mockResolvedValue([
      {
        user_id: 'project-user-1',
        email: 'project-user@example.com',
        org_role: 'member',
        project_role: 'viewer',
        is_active: true,
        created_at: '2026-07-15T08:00:00Z',
        updated_at: '2026-07-15T08:00:00Z',
      },
    ])
    mockedListUsers.mockResolvedValue([
      {
        id: 'org-user-1',
        email: 'org-only@example.com',
        role: 'member',
        is_active: true,
        created_at: '2026-07-15T08:00:00Z',
      },
    ])
    storeAdminSession('/dashboard/users')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Users' })).toBeInTheDocument()
    expect(await screen.findByText('project-user@example.com')).toBeInTheDocument()
    expect(screen.queryByText('org-only@example.com')).not.toBeInTheDocument()
    expect(mockedListProjectMembers).toHaveBeenCalledWith(project.id)
    expect(mockedListUsers).not.toHaveBeenCalled()
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
    mockedListAccessibleProjects.mockResolvedValue([{ ...loadingProject, project_role: 'admin' }])
    mockedListTraces.mockReturnValue(new Promise(() => {}))
    storeAdminSession('/dashboard/traces', loadingProject)

    const { container } = render(<App />)

    expect(await screen.findByRole('heading', { name: 'Traces' })).toBeInTheDocument()
    expect(container.querySelectorAll('.animate-pulse')).toHaveLength(3)
  })

  it('shows trace explorer empty state when the selected project has no traces', async () => {
    const emptyProject = { ...project, id: 'project-empty' }
    mockedListAccessibleProjects.mockResolvedValue([{ ...emptyProject, project_role: 'admin' }])
    mockedListTraces.mockResolvedValue({
      traces: [],
      next_cursor: null,
      has_more: false,
    })
    storeAdminSession('/dashboard/traces', emptyProject)

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
    mockedListAccessibleProjects.mockResolvedValue([{ ...dataProject, project_role: 'admin' }])
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
    storeAdminSession('/dashboard/traces', dataProject)

    render(<App />)

    expect(await screen.findByRole('link', { name: 'trace-al' })).toBeInTheDocument()
    expect(screen.getAllByText('error')).toHaveLength(2)
    expect(screen.getByText('1,234')).toBeInTheDocument()
    expect(screen.getByText('$0.4321')).toBeInTheDocument()
  })

  it('loads trace detail payloads on demand for the selected trace', async () => {
    const user = userEvent.setup()
    const traceProject = { ...project, id: 'project-trace-detail' }
    mockedListAccessibleProjects.mockResolvedValue([{ ...traceProject, project_role: 'admin' }])
    mockedGetTraceDetail
      .mockResolvedValueOnce({
        id: 'trace-detail-123',
        project_id: traceProject.id,
        started_at: '2026-07-28T08:00:00Z',
        ended_at: '2026-07-28T08:00:01Z',
        total_tokens: 128,
        total_cost_usd: '0.0123',
        span_count: 1,
        status: 'ok',
        spans: [
          {
            id: 'span-root',
            trace_id: 'trace-detail-123',
            parent_span_id: null,
            name: 'openai.chat',
            provider: 'openai',
            model: 'gpt-4o-mini',
            input_tokens: 64,
            output_tokens: 64,
            cost_usd: '0.0123',
            latency_ms: 1200,
            status: 'ok',
            started_at: '2026-07-28T08:00:00Z',
            payload_s3_key: 'payloads/project-trace-detail/span-root.json.gz',
            payload_status: 'stored_redacted',
            metadata: { source: 'sdk' },
          },
        ],
      })
      .mockResolvedValueOnce({
        id: 'trace-detail-123',
        project_id: traceProject.id,
        started_at: '2026-07-28T08:00:00Z',
        ended_at: '2026-07-28T08:00:01Z',
        total_tokens: 128,
        total_cost_usd: '0.0123',
        span_count: 1,
        status: 'ok',
        spans: [
          {
            id: 'span-root',
            trace_id: 'trace-detail-123',
            parent_span_id: null,
            name: 'openai.chat',
            provider: 'openai',
            model: 'gpt-4o-mini',
            input_tokens: 64,
            output_tokens: 64,
            cost_usd: '0.0123',
            latency_ms: 1200,
            status: 'ok',
            started_at: '2026-07-28T08:00:00Z',
            payload_s3_key: 'payloads/project-trace-detail/span-root.json.gz',
            payload_status: 'stored_redacted',
            metadata: { source: 'sdk' },
            payload: {
              input: { prompt: '[REDACTED]' },
              output: { text: 'hello' },
            },
          },
        ],
      })
    storeAdminSession('/dashboard/traces/trace-detail-123?started_at=2026-07-28T08%3A00%3A00Z', traceProject)

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Trace Detail' })).toBeInTheDocument()
    expect(await screen.findByText('openai.chat')).toBeInTheDocument()
    expect(screen.getByText('Hidden')).toBeInTheDocument()
    expect(mockedGetTraceDetail).toHaveBeenCalledWith({
      projectId: traceProject.id,
      traceId: 'trace-detail-123',
      startedAt: '2026-07-28T08:00:00Z',
      includePayload: false,
    })

    await user.click(screen.getByRole('button', { name: 'Load payload' }))

    expect(await screen.findByText('Loaded (1)')).toBeInTheDocument()
    expect(screen.getByText('Payload loaded from storage with the redaction policy applied.')).toBeInTheDocument()
    expect(screen.getByText(/REDACTED/)).toBeInTheDocument()
    expect(mockedGetTraceDetail).toHaveBeenLastCalledWith({
      projectId: traceProject.id,
      traceId: 'trace-detail-123',
      startedAt: '2026-07-28T08:00:00Z',
      includePayload: true,
    })
  })

  it('shows trace detail empty and no-payload states without blank content', async () => {
    const user = userEvent.setup()
    const traceProject = { ...project, id: 'project-trace-empty' }
    mockedListAccessibleProjects.mockResolvedValue([{ ...traceProject, project_role: 'admin' }])
    mockedGetTraceDetail
      .mockResolvedValueOnce({
        id: 'trace-empty-123',
        project_id: traceProject.id,
        started_at: '2026-07-28T08:00:00Z',
        ended_at: null,
        total_tokens: 0,
        total_cost_usd: '0',
        span_count: 0,
        status: 'ok',
        spans: [],
      })
      .mockResolvedValueOnce({
        id: 'trace-empty-123',
        project_id: traceProject.id,
        started_at: '2026-07-28T08:00:00Z',
        ended_at: null,
        total_tokens: 0,
        total_cost_usd: '0',
        span_count: 0,
        status: 'ok',
        spans: [],
      })
    storeAdminSession('/dashboard/traces/trace-empty-123', traceProject)

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Trace Detail' })).toBeInTheDocument()
    expect(await screen.findByText('No spans are attached to this trace.')).toBeInTheDocument()
    expect(screen.getByText('Hidden')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Load payload' }))

    expect(await screen.findByText('Loaded (0)')).toBeInTheDocument()
    expect(screen.getByText(/Payload was requested, but no payload objects were loaded/)).toBeInTheDocument()
  })

  it('shows accessible project tiles and stores the selected project', async () => {
    const user = userEvent.setup()
    mockedListAccessibleProjects.mockResolvedValue([
      {
        ...project,
        project_role: 'member',
      },
    ])
    localStorage.setItem('token', 'member-token')
    localStorage.setItem('role', 'member')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Projects' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Production API/i })).toBeInTheDocument()
    expect(screen.queryByLabelText('Active project')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Production API/i }))

    expect(localStorage.getItem('projectId')).toBe(project.id)
    expect(mockedListAccessibleProjects).toHaveBeenCalled()
  })

  it('lets non-admin users switch between accessible projects from the dashboard', async () => {
    const user = userEvent.setup()
    const secondProject = {
      ...project,
      id: 'project-2',
      name: 'Staging API',
    }
    mockedListAccessibleProjects.mockResolvedValue([
      { ...project, project_role: 'member' },
      { ...secondProject, project_role: 'viewer' },
    ])
    localStorage.setItem('token', 'member-token')
    localStorage.setItem('projectId', project.id)
    localStorage.setItem('role', 'member')
    window.history.pushState(null, '', '/dashboard')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Overview' })).toBeInTheDocument()
    await screen.findByRole('option', { name: 'Staging API (viewer)' })

    await user.selectOptions(screen.getByLabelText('Active project'), secondProject.id)

    expect(localStorage.getItem('projectId')).toBe(secondProject.id)
    await waitFor(() => {
      expect(mockedGetMetricsOverview).toHaveBeenCalledWith(secondProject.id, '24h')
    })
  })

  it('creates an alert rule and resolves an open alert event for the selected project', async () => {
    const user = userEvent.setup()
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'member' }])
    mockedListAlertRules.mockResolvedValue([
      {
        id: 'rule-1',
        project_id: project.id,
        name: 'Production latency',
        metric: 'latency_p95',
        condition: 'gt',
        threshold: 500,
        window_minutes: 5,
        cooldown_minutes: 15,
        notify_email: 'alerts@example.com',
        notify_slack_webhook: null,
        is_active: true,
        created_at: '2026-07-28T08:00:00Z',
      },
    ])
    mockedListAlertEvents.mockResolvedValue([
      {
        id: 'event-1',
        rule_id: 'rule-1',
        triggered_at: '2026-07-28T08:10:00Z',
        value: 650,
        message: 'p95 latency exceeded threshold',
        resolved_at: null,
      },
    ])
    localStorage.setItem('token', 'member-token')
    localStorage.setItem('projectId', project.id)
    localStorage.setItem('role', 'member')
    window.history.pushState(null, '', '/dashboard/alerts')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Alerts' })).toBeInTheDocument()
    expect(await screen.findByText('p95 latency exceeded threshold')).toBeInTheDocument()
    await user.type(screen.getByPlaceholderText('Production latency'), 'High p95 latency')
    await user.type(screen.getByPlaceholderText('500'), '750')
    await user.type(screen.getByPlaceholderText('alerts@example.com'), 'alerts@example.com')
    await user.click(screen.getByRole('button', { name: 'Create rule' }))

    expect(mockedCreateAlertRule.mock.calls[0][0]).toEqual({
      project_id: project.id,
      name: 'High p95 latency',
      metric: 'latency_p95',
      condition: 'gt',
      threshold: 750,
      window_minutes: 5,
      cooldown_minutes: 15,
      notify_email: 'alerts@example.com',
      notify_slack_webhook: null,
    })

    await user.click(screen.getByRole('button', { name: 'Resolve' }))

    expect(mockedResolveAlertEvent).toHaveBeenCalledWith(project.id, 'event-1')
  })

  it('routes the LLM Obs title back to the project selection page', async () => {
    const user = userEvent.setup()
    mockedListAccessibleProjects.mockResolvedValue([
      {
        ...project,
        project_role: 'admin',
      },
    ])
    storeAdminSession('/dashboard/traces')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Traces' })).toBeInTheDocument()

    await user.click(screen.getByRole('link', { name: 'LLM Obs' }))

    expect(await screen.findByRole('heading', { name: 'Projects' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Active project')).not.toBeInTheDocument()
  })

  it('shows error fingerprints on the overview analytics section', async () => {
    mockedGetMetricsOverview.mockResolvedValue({
      total_spans: 12,
      p95_latency_ms: 450,
      error_rate_pct: 25,
      total_cost_usd: '0.1234',
    })
    mockedGetMetricsAnalytics.mockResolvedValue({
      cost_by_model: [],
      cost_by_provider: [],
      cost_over_time: [],
      latency_by_model: [],
      latency_by_provider: [],
      top_expensive_traces: [],
      slowest_traces: [],
      error_rate_trend: [],
      top_error_messages: [],
      errors_by_model: [],
      errors_by_provider: [],
      recent_failed_traces: [],
      error_fingerprints: [
        {
          fingerprint: 'rate limit exceeded for request <uuid>',
          sample_message: 'Rate limit exceeded for request <uuid>',
          error_count: 4,
          affected_trace_count: 2,
          top_provider: 'openai',
          top_model: 'gpt-4o',
          last_seen_at: '2026-07-14T08:30:00Z',
        },
      ],
    })

    renderOverviewWithTestClient(project.id)

    expect(await screen.findByText('Error fingerprints')).toBeInTheDocument()
    expect(await screen.findByText('Rate limit exceeded for request <uuid>')).toBeInTheDocument()
    expect(screen.getByText('rate limit exceeded for request <uuid>')).toBeInTheDocument()
    expect(screen.getByText('openai / gpt-4o')).toBeInTheDocument()
    expect(mockedGetMetricsAnalytics).toHaveBeenCalledWith(project.id, '24h')
  })

  it('creates a scoped project api key and reveals it once', async () => {
    const user = userEvent.setup()
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    storeAdminSession('/dashboard/project-settings')

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

  it('creates a pricing record from organization settings', async () => {
    const user = userEvent.setup()
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    mockedListPricing.mockResolvedValue([
      {
        id: 1,
        provider: 'openai',
        model: 'gpt-4o',
        input_cost_per_1k_tokens: '0.005',
        output_cost_per_1k_tokens: '0.015',
        valid_from: '2026-07-01T00:00:00Z',
        valid_to: null,
      },
    ])
    storeAdminSession('/admin-settings/pricing')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Pricing' })).toBeInTheDocument()
    expect(await screen.findByText('gpt-4o')).toBeInTheDocument()
    const createSection = screen.getByRole('heading', { name: 'New pricing record' }).closest('section')
    expect(createSection).not.toBeNull()
    const createForm = within(createSection as HTMLElement)

    await user.clear(createForm.getByLabelText('Provider'))
    await user.type(createForm.getByLabelText('Provider'), 'OpenAI')
    await user.type(createForm.getByLabelText('Model'), 'gpt-4o-mini')
    await user.type(createForm.getByLabelText('Input / 1K'), '0,00015')
    await user.type(createForm.getByLabelText('Output / 1K'), '0.0006')
    await user.click(createForm.getByRole('button', { name: 'Create pricing' }))

    expect(mockedCreatePricing.mock.calls[0][0]).toEqual({
      provider: 'openai',
      model: 'gpt-4o-mini',
      input_cost_per_1k_tokens: '0.00015',
      output_cost_per_1k_tokens: '0.0006',
      valid_from: null,
    })
  })

  it('shows pricing load errors instead of an empty pricing table', async () => {
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    mockedListPricing.mockRejectedValue({ response: { status: 429 } })
    storeAdminSession('/admin-settings/pricing')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Pricing' })).toBeInTheDocument()
    expect(
      await screen.findByText('Too many requests. Wait a moment and try again.', {}, { timeout: 5_000 }),
    ).toBeInTheDocument()
    expect(screen.queryByText('No pricing records')).not.toBeInTheDocument()
  }, 10_000)

  it('filters audit events and loads the next page', async () => {
    const user = userEvent.setup()
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    mockedListUsers.mockResolvedValue([
      {
        id: 'admin-user-1',
        email: 'admin@example.com',
        role: 'admin',
        is_active: true,
        created_at: '2026-07-15T08:00:00Z',
      },
    ])
    mockedListAuditEvents
      .mockResolvedValueOnce({
        events: [],
        next_cursor: null,
      })
      .mockResolvedValueOnce({
        events: [
          {
            id: 1,
            action: 'project.settings.update',
            user_id: 'admin-user-1',
            user_email: 'admin@example.com',
            resource_id: project.id,
            metadata: { field: 'retention_days' },
            created_at: '2026-07-28T08:00:00Z',
          },
        ],
        next_cursor: 'cursor-2',
      })
      .mockResolvedValueOnce({
        events: [
          {
            id: 2,
            action: 'project.api_key.create',
            user_id: 'admin-user-1',
            user_email: 'admin@example.com',
            resource_id: 'key-1',
            metadata: { scope: 'ingest' },
            created_at: '2026-07-28T08:05:00Z',
          },
        ],
        next_cursor: null,
      })
    storeAdminSession('/admin-settings/audit-log')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Audit Log' })).toBeInTheDocument()
    expect(await screen.findByText('No audit events found.')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Action'), 'project.settings.update')
    await user.selectOptions(screen.getByLabelText('User'), 'admin-user-1')
    await user.click(screen.getByRole('button', { name: 'Apply' }))

    expect(await screen.findByText('project.settings.update')).toBeInTheDocument()
    expect(screen.getByText('field: retention_days')).toBeInTheDocument()
    expect(mockedListAuditEvents).toHaveBeenLastCalledWith({
      action: 'project.settings.update',
      userId: 'admin-user-1',
      fromDt: '',
      toDt: '',
      cursor: '',
    })

    await user.click(screen.getByRole('button', { name: 'Load more' }))

    expect(await screen.findByText('project.api_key.create')).toBeInTheDocument()
    expect(screen.getByText('scope: ingest')).toBeInTheDocument()
    expect(mockedListAuditEvents).toHaveBeenLastCalledWith({
      action: 'project.settings.update',
      userId: 'admin-user-1',
      fromDt: '',
      toDt: '',
      cursor: 'cursor-2',
    })
  })

  it('shows retry only for failed tasks with complete span payloads', async () => {
    const user = userEvent.setup()
    mockedListAccessibleProjects.mockResolvedValue([{ ...project, project_role: 'admin' }])
    mockedListFailedTasks.mockResolvedValue([
      {
        id: 1,
        task_name: 'process_span_batch',
        project_id: project.id,
        task_args: {
          batch_id: 'batch-summary',
          project_id: project.id,
          span_count: 2,
        },
        error: 'boom',
        attempts: 3,
        failed_at: '2026-07-17T08:00:00Z',
        resolved: false,
      },
      {
        id: 2,
        task_name: 'process_span_batch',
        project_id: project.id,
        task_args: {
          batch_id: 'batch-full',
          project_id: project.id,
          spans: [{ span_id: 'span-1' }],
        },
        error: 'boom',
        attempts: 3,
        failed_at: '2026-07-17T08:05:00Z',
        resolved: false,
      },
    ])
    mockedRetryFailedTask.mockResolvedValue(undefined)
    storeAdminSession('/dashboard/project-settings')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Project Settings' })).toBeInTheDocument()
    expect(await screen.findByText('Not retryable')).toBeInTheDocument()

    const retryButton = screen.getByRole('button', { name: 'Retry' })
    await user.click(retryButton)

    expect(mockedRetryFailedTask.mock.calls[0][0]).toBe(2)
  })
})
