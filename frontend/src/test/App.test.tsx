import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from '../App'
import {
  listAccessibleProjects,
  listProjects,
  loginUser,
  registerUser,
} from '../api/dashboard'

vi.mock('../api/dashboard', () => ({
  createProject: vi.fn(),
  dashboardQueryKeys: {
    projects: () => ['projects'],
    accessibleProjects: () => ['accessible-projects'],
  },
  listAccessibleProjects: vi.fn(),
  listProjects: vi.fn(),
  loginUser: vi.fn(),
  registerUser: vi.fn(),
}))

const mockedListAccessibleProjects = vi.mocked(listAccessibleProjects)
const mockedListProjects = vi.mocked(listProjects)
const mockedLoginUser = vi.mocked(loginUser)
const mockedRegisterUser = vi.mocked(registerUser)

describe('App', () => {
  beforeEach(() => {
    mockedListAccessibleProjects.mockResolvedValue([])
    mockedListProjects.mockResolvedValue([])
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
})
