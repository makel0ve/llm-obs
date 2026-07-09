import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import {
  createOrganizationUser,
  dashboardQueryKeys,
  deleteOrganizationUser,
  listUsers,
  updateOrganizationUserRole,
  type OrganizationInvite,
  type OrganizationUser,
  type UserRole,
} from '../api/dashboard'

const roleOptions: Array<{ value: UserRole; label: string }> = [
  { value: 'admin', label: 'Admin' },
  { value: 'member', label: 'Member' },
  { value: 'viewer', label: 'Viewer' },
]

function formatDate(value?: string | null) {
  if (!value) return '-'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'

  return format(date, 'dd MMM yyyy HH:mm')
}

function roleHelp(role: UserRole) {
  if (role === 'admin') return 'Full access, including users, pricing, API key rotation and retention.'
  if (role === 'member') return 'Can inspect data and manage alert workflows.'
  return 'Read-only access to project observability data.'
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
  const [newRole, setNewRole] = useState<UserRole>('member')
  const [validationError, setValidationError] = useState('')
  const [message, setMessage] = useState('')
  const [createdInvite, setCreatedInvite] = useState<OrganizationInvite | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<OrganizationUser | null>(null)
  const [deleteConfirmation, setDeleteConfirmation] = useState('')

  const canManageUsers = role === 'admin'

  const usersQuery = useQuery({
    queryKey: dashboardQueryKeys.users(),
    queryFn: listUsers,
    enabled: canManageUsers,
  })

  const users = useMemo(() => usersQuery.data ?? [], [usersQuery.data])

  const invalidateUsers = async () => {
    await queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.users() })
  }

  const createUser = useMutation({
    mutationFn: createOrganizationUser,
    onSuccess: async invite => {
      setEmail('')
      setNewRole('member')
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
      role: newRole,
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
        <form onSubmit={submitCreate} className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(220px,1fr)_180px_auto]">
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
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Role</span>
            <select
              value={newRole}
              onChange={event => setNewRole(event.target.value as UserRole)}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
            >
              {roleOptions.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
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
        </form>
        <p className="mt-3 text-sm text-gray-500">{roleHelp(newRole)}</p>
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
                        <button
                          type="button"
                          onClick={() => openDeleteModal(user)}
                          disabled={deleteUser.isPending}
                          className="min-h-9 rounded-md border border-red-200 bg-white px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

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
