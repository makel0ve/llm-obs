import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import {
  assignProjectMember,
  createOrganizationUser,
  dashboardQueryKeys,
  deleteOrganizationUser,
  listUserProjectAccess,
  listProjects,
  listUsers,
  removeProjectMember,
  updateOrganizationUserRole,
  type OrganizationInvite,
  type OrganizationUser,
  type ProjectMembershipRole,
  type ProjectRecord,
  type UserProjectAccessRecord,
  type UserRole,
} from '../api/dashboard'

const roleOptions: Array<{ value: UserRole; label: string }> = [
  { value: 'admin', label: 'Admin' },
  { value: 'member', label: 'Member' },
  { value: 'viewer', label: 'Viewer' },
]

type ProjectAccessSelectionRole = 'none' | ProjectMembershipRole
type ProjectAccessDisplayRole = ProjectAccessSelectionRole | 'admin'

const projectRoleOptions: Array<{ value: ProjectAccessSelectionRole; label: string }> = [
  { value: 'none', label: 'No access' },
  { value: 'viewer', label: 'Viewer' },
  { value: 'member', label: 'Member' },
]

const projectAccessDisplayOptions: Array<{ value: ProjectAccessDisplayRole; label: string }> = [
  { value: 'admin', label: 'Admin' },
  ...projectRoleOptions,
]

function formatDate(value?: string | null) {
  if (!value) return '-'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'

  return format(date, 'dd MMM yyyy HH:mm')
}

function Alert({
  tone,
  children,
}: {
  tone: 'success' | 'error' | 'warning'
  children: React.ReactNode
}) {
  const classes = {
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    error: 'border-red-200 bg-red-50 text-red-800',
    warning: 'border-amber-200 bg-amber-50 text-amber-800',
  }[tone]

  return <div className={`rounded-lg border p-4 text-sm ${classes}`}>{children}</div>
}

function validateInviteDraft(email: string) {
  if (!email.trim()) return 'Email is required.'
  if (!email.includes('@')) return 'Enter a valid email address.'
  return ''
}

function getErrorDetail(error: unknown) {
  if (!error || typeof error !== 'object' || !('response' in error)) return ''

  const response = (error as { response?: { data?: { detail?: unknown } } }).response
  const detail = response?.data?.detail
  return typeof detail === 'string' ? detail : ''
}

export function Users({ role }: { role: UserRole }) {
  const queryClient = useQueryClient()
  const [email, setEmail] = useState('')
  const [projectAssignments, setProjectAssignments] = useState<Record<string, ProjectMembershipRole>>({})
  const [validationError, setValidationError] = useState('')
  const [message, setMessage] = useState('')
  const [createdInvite, setCreatedInvite] = useState<OrganizationInvite | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<OrganizationUser | null>(null)
  const [deleteConfirmation, setDeleteConfirmation] = useState('')
  const [accessTarget, setAccessTarget] = useState<OrganizationUser | null>(null)
  const [accessError, setAccessError] = useState('')

  const canManageUsers = role === 'admin'

  const usersQuery = useQuery({
    queryKey: dashboardQueryKeys.users(),
    queryFn: listUsers,
    enabled: canManageUsers,
  })

  const projectsQuery = useQuery({
    queryKey: dashboardQueryKeys.projects(),
    queryFn: listProjects,
    enabled: canManageUsers,
  })

  const users = useMemo(() => usersQuery.data ?? [], [usersQuery.data])
  const projects = useMemo(() => projectsQuery.data ?? [], [projectsQuery.data])

  const userProjectAccessQuery = useQuery({
    queryKey: dashboardQueryKeys.userProjectAccess(accessTarget?.id ?? ''),
    queryFn: () => listUserProjectAccess(accessTarget?.id ?? ''),
    enabled: canManageUsers && Boolean(accessTarget),
  })

  const invalidateUsers = async () => {
    await queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.users() })
  }

  const createUser = useMutation({
    mutationFn: createOrganizationUser,
    onSuccess: async invite => {
      setEmail('')
      setProjectAssignments({})
      setValidationError('')
      setCreatedInvite(invite)
      setMessage('Invite created.')
      await invalidateUsers()
    },
    onError: error => {
      setMessage('')
      setCreatedInvite(null)
      const detail = getErrorDetail(error)
      setValidationError(detail || 'Could not create invite. Check that the email is not already registered.')
    },
  })

  const updateRole = useMutation({
    mutationFn: ({ userId, nextRole }: { userId: string; nextRole: UserRole }) =>
      updateOrganizationUserRole(userId, nextRole),
    onSuccess: async () => {
      setValidationError('')
      setMessage('Role updated.')
      await invalidateUsers()
    },
    onError: error => {
      setMessage('')
      const detail = getErrorDetail(error)
      setValidationError(detail || 'Could not update role. The organization must keep at least one admin.')
    },
  })

  const deleteUser = useMutation({
    mutationFn: deleteOrganizationUser,
    onSuccess: async () => {
      setDeleteTarget(null)
      setDeleteConfirmation('')
      setValidationError('')
      setMessage('User deleted.')
      await invalidateUsers()
    },
    onError: error => {
      setMessage('')
      const detail = getErrorDetail(error)
      setValidationError(detail || 'Could not delete user. The organization must keep at least one admin.')
    },
  })

  const updateProjectAccess = useMutation({
    mutationFn: async ({
      targetUser,
      projectAccess,
      nextRole,
    }: {
      targetUser: OrganizationUser
      projectAccess: UserProjectAccessRecord
      nextRole: ProjectAccessSelectionRole
    }) => {
      if (nextRole === 'none') {
        if (!projectAccess.project_role || projectAccess.project_role === 'admin') return null
        await removeProjectMember(projectAccess.project_id, targetUser.id)
        return null
      }

      return assignProjectMember(projectAccess.project_id, {
        user_id: targetUser.id,
        role: nextRole,
      })
    },
    onSuccess: async (_result, variables) => {
      setAccessError('')
      setValidationError('')
      setMessage('Project access updated.')
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: dashboardQueryKeys.userProjectAccess(variables.targetUser.id),
        }),
        queryClient.invalidateQueries({
          queryKey: dashboardQueryKeys.projectMembers(variables.projectAccess.project_id),
        }),
        queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.accessibleProjects() }),
      ])
    },
    onError: error => {
      setMessage('')
      const detail = getErrorDetail(error)
      setAccessError(detail || 'Could not update project access.')
    },
  })

  const submitCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMessage('')
    setCreatedInvite(null)

    const error = validateInviteDraft(email)
    if (error) {
      setValidationError(error)
      return
    }

    createUser.mutate({
      email: email.trim(),
      role: 'member',
      project_assignments: Object.entries(projectAssignments).map(([projectId, role]) => ({
        project_id: projectId,
        role,
      })),
    })
  }

  const toggleProjectAssignment = (project: ProjectRecord, checked: boolean) => {
    setProjectAssignments(current => {
      const next = { ...current }
      if (checked) {
        next[project.id] = next[project.id] ?? 'viewer'
      } else {
        delete next[project.id]
      }
      return next
    })
  }

  const setProjectAssignmentRole = (projectId: string, role: ProjectAccessSelectionRole) => {
    setProjectAssignments(current => {
      const next = { ...current }
      if (role === 'none') {
        delete next[projectId]
      } else {
        next[projectId] = role
      }
      return next
    })
  }

  const changeRole = (user: OrganizationUser, nextRole: UserRole) => {
    if (nextRole === user.role) return
    setMessage('')
    setValidationError('')
    updateRole.mutate({ userId: user.id, nextRole })
  }

  const openDeleteModal = (user: OrganizationUser) => {
    setMessage('')
    setValidationError('')
    setAccessError('')
    setDeleteConfirmation('')
    setDeleteTarget(user)
  }

  const closeDeleteModal = () => {
    if (deleteUser.isPending) return
    setDeleteTarget(null)
    setDeleteConfirmation('')
  }

  const confirmDeleteUser = () => {
    if (!deleteTarget || deleteConfirmation !== deleteTarget.email) return
    deleteUser.mutate(deleteTarget.id)
  }

  const openProjectAccess = (user: OrganizationUser) => {
    setMessage('')
    setValidationError('')
    setAccessError('')
    setAccessTarget(user)
  }

  const changeProjectAccess = (
    targetUser: OrganizationUser,
    projectAccess: UserProjectAccessRecord,
    nextRole: ProjectAccessSelectionRole,
  ) => {
    if (projectAccess.project_role === 'admin' || (projectAccess.project_role ?? 'none') === nextRole) return
    setMessage('')
    setValidationError('')
    setAccessError('')
    updateProjectAccess.mutate({ targetUser, projectAccess, nextRole })
  }

  const inviteLink = createdInvite
    ? `${window.location.origin}/accept-invite?token=${encodeURIComponent(createdInvite.invite_token)}`
    : ''

  if (!canManageUsers) {
    return (
      <div className="space-y-4 p-4 sm:p-6 lg:p-8">
        <div>
          <h1 className="text-2xl font-semibold text-gray-950">Users</h1>
          <p className="mt-1 text-sm text-gray-500">Manage organization access and roles.</p>
        </div>
        <Alert tone="warning">Only admins can manage organization users.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-950">Users</h1>
        <p className="mt-1 text-sm text-gray-500">Invite users and assign organization roles.</p>
      </div>

      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <h2 className="text-lg font-semibold text-gray-950">Invite user</h2>
        <form onSubmit={submitCreate} className="mt-4 space-y-5">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(220px,1fr)_auto]">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Email</span>
              <input
                type="email"
                value={email}
                onChange={event => {
                  setValidationError('')
                  setEmail(event.target.value)
                }}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
                placeholder="teammate@example.com"
                maxLength={255}
                required
              />
            </label>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={createUser.isPending}
                className="min-h-10 w-full rounded-md bg-gray-900 px-4 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60 xl:w-auto"
              >
                {createUser.isPending ? 'Creating...' : 'Create invite'}
              </button>
            </div>
          </div>
          <div>
            <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h3 className="text-sm font-semibold text-gray-950">Project access</h3>
                <p className="mt-1 text-sm text-gray-500">Choose only projects this user should see after accepting the invite.</p>
              </div>
              {projectsQuery.isLoading && <span className="text-sm text-gray-500">Loading projects...</span>}
            </div>
            {projectsQuery.isError && (
              <div className="mt-3">
                <Alert tone="error">Could not load projects for access assignment.</Alert>
              </div>
            )}
            {!projectsQuery.isLoading && !projectsQuery.isError && projects.length === 0 && (
              <div className="mt-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 text-sm text-gray-600">
                No projects are available for assignment.
              </div>
            )}
            {projects.length > 0 && (
              <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                {projects.map(project => {
                  const selectedRole = projectAssignments[project.id]
                  return (
                    <div key={project.id} className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <label className="flex min-w-0 items-start gap-3">
                          <input
                            type="checkbox"
                            checked={Boolean(selectedRole)}
                            onChange={event => toggleProjectAssignment(project, event.target.checked)}
                            className="mt-1 h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                          />
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium text-gray-950">{project.name}</span>
                            <span className="mt-1 block text-xs text-gray-500">Retention {project.retention_days}d</span>
                          </span>
                        </label>
                        <select
                          value={selectedRole ?? 'none'}
                          onChange={event => setProjectAssignmentRole(project.id, event.target.value as ProjectAccessSelectionRole)}
                          className="min-h-9 w-32 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900"
                          aria-label={`${project.name} project role`}
                        >
                          {projectRoleOptions.map(option => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </form>
        <div className="mt-4 space-y-3">
          {validationError && <Alert tone="error">{validationError}</Alert>}
          {message && <Alert tone="success">{message}</Alert>}
          {createdInvite && (
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
              <div className="font-medium">Invite link for {createdInvite.email}</div>
              <p className="mt-1 text-blue-800">This link expires in 24 hours.</p>
              <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-center">
                <code className="block min-w-0 flex-1 overflow-x-auto rounded-md border border-blue-200 bg-white px-3 py-2 text-blue-950">
                  {inviteLink}
                </code>
                <button
                  type="button"
                  onClick={() => navigator.clipboard?.writeText(inviteLink)}
                  className="min-h-10 rounded-md border border-blue-200 bg-white px-4 text-sm font-medium text-blue-800 hover:bg-blue-100"
                >
                  Copy
                </button>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-gray-950">Organization users</h2>
        {usersQuery.isLoading && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-sm text-gray-600">Loading users...</div>
        )}
        {usersQuery.isError && <Alert tone="error">Could not load users.</Alert>}
        {!usersQuery.isLoading && !usersQuery.isError && users.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-sm text-gray-600">No users found.</div>
        )}
        {users.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <div className="overflow-x-auto">
              <table className="min-w-[880px] w-full text-left text-sm">
                <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">Email</th>
                    <th scope="col" className="px-4 py-3 font-medium">Role</th>
                    <th scope="col" className="px-4 py-3 font-medium">Status</th>
                    <th scope="col" className="px-4 py-3 font-medium">Created</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {users.map(user => (
                    <tr key={user.id} className="align-middle hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium text-gray-900">{user.email}</td>
                      <td className="px-4 py-3">
                        <select
                          value={user.role}
                          onChange={event => changeRole(user, event.target.value as UserRole)}
                          disabled={updateRole.isPending}
                          className="min-h-9 w-40 rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900 disabled:bg-gray-100 disabled:text-gray-500"
                        >
                          {roleOptions.map(option => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex min-h-6 items-center rounded-md px-2 text-xs font-medium ${
                            user.is_active
                              ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
                              : 'bg-gray-100 text-gray-600 ring-1 ring-gray-200'
                          }`}
                        >
                          {user.is_active ? 'active' : 'inactive'}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-gray-700">{formatDate(user.created_at)}</td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => openProjectAccess(user)}
                            className="min-h-9 rounded-md border border-gray-200 bg-white px-3 text-sm font-medium text-gray-700 hover:bg-gray-100"
                          >
                            Project access
                          </button>
                        <button
                          type="button"
                          onClick={() => openDeleteModal(user)}
                          disabled={deleteUser.isPending}
                          className="min-h-9 rounded-md border border-red-200 bg-white px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Delete
                        </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {accessTarget && (
        <section className="space-y-4 rounded-lg border border-gray-200 bg-white p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-lg font-semibold text-gray-950">Project access</h2>
              <p className="mt-1 text-sm text-gray-500">{accessTarget.email}</p>
            </div>
            <button
              type="button"
              onClick={() => {
                setAccessTarget(null)
                setAccessError('')
              }}
              className="min-h-9 rounded-md border border-gray-200 bg-white px-3 text-sm font-medium text-gray-700 hover:bg-gray-100"
            >
              Close
            </button>
          </div>
          {accessError && <Alert tone="error">{accessError}</Alert>}
          {userProjectAccessQuery.isLoading && (
            <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 text-sm text-gray-600">
              Loading project access...
            </div>
          )}
          {userProjectAccessQuery.isError && <Alert tone="error">Could not load project access.</Alert>}
          {!userProjectAccessQuery.isLoading &&
            !userProjectAccessQuery.isError &&
            (userProjectAccessQuery.data ?? []).length === 0 && (
              <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 text-sm text-gray-600">
                No active projects are available.
              </div>
            )}
          {(userProjectAccessQuery.data ?? []).length > 0 && (
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              {(userProjectAccessQuery.data ?? []).map(projectAccess => (
                <div key={projectAccess.project_id} className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-gray-950">{projectAccess.project_name}</div>
                      <div className="mt-1 text-xs text-gray-500">Retention {projectAccess.retention_days}d</div>
                    </div>
                    <select
                      value={(projectAccess.project_role ?? 'none') as ProjectAccessDisplayRole}
                      onChange={event =>
                        changeProjectAccess(
                          accessTarget,
                          projectAccess,
                          event.target.value as ProjectAccessSelectionRole,
                        )
                      }
                      disabled={updateProjectAccess.isPending || projectAccess.project_role === 'admin'}
                      className="min-h-9 w-32 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900 disabled:bg-gray-100 disabled:text-gray-500"
                      aria-label={`${projectAccess.project_name} existing user project role`}
                    >
                      {(projectAccess.project_role === 'admin' ? projectAccessDisplayOptions : projectRoleOptions).map(option => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-user-title"
        >
          <div className="w-full max-w-lg rounded-lg border border-gray-200 bg-white p-6 shadow-xl">
            <h2 id="delete-user-title" className="text-lg font-semibold text-gray-950">
              Delete user
            </h2>
            <p className="mt-3 text-sm leading-6 text-gray-600">
              You are about to delete user <span className="font-semibold text-gray-950">{deleteTarget.email}</span>.
              Type this email to enable confirmation.
            </p>
            <label className="mt-5 block">
              <span className="text-sm font-medium text-gray-700">User email</span>
              <input
                value={deleteConfirmation}
                onChange={event => setDeleteConfirmation(event.target.value)}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
                placeholder={deleteTarget.email}
                autoFocus
              />
            </label>
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={closeDeleteModal}
                disabled={deleteUser.isPending}
                className="min-h-10 rounded-md border border-gray-200 bg-white px-4 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDeleteUser}
                disabled={deleteConfirmation !== deleteTarget.email || deleteUser.isPending}
                className="min-h-10 rounded-md bg-red-600 px-4 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {deleteUser.isPending ? 'Deleting...' : 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
