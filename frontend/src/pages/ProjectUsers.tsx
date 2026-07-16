import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  assignProjectMember,
  dashboardQueryKeys,
  listProjectMembers,
  removeProjectMember,
  type ProjectMember,
  type ProjectMembershipRole,
} from '../api/dashboard'

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

const projectRoleOptions: Array<{ value: ProjectMembershipRole; label: string }> = [
  { value: 'viewer', label: 'Viewer' },
  { value: 'member', label: 'Member' },
]

function formatDateTime(value?: string | null) {
  if (!value) return '-'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'

  return new Intl.DateTimeFormat(undefined, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function ProjectUsers({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const membersQuery = useQuery({
    queryKey: dashboardQueryKeys.projectMembers(projectId),
    queryFn: () => listProjectMembers(projectId),
    enabled: !!projectId,
  })

  const invalidateMembers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.projectMembers(projectId) }),
      queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.accessibleProjects() }),
    ])
  }

  const updateMember = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: ProjectMembershipRole }) =>
      assignProjectMember(projectId, { user_id: userId, role }),
    onSuccess: invalidateMembers,
  })

  const removeMember = useMutation({
    mutationFn: (userId: string) => removeProjectMember(projectId, userId),
    onSuccess: invalidateMembers,
  })

  const changeProjectRole = (member: ProjectMember, role: ProjectMembershipRole) => {
    if (member.project_role === role) return
    updateMember.mutate({ userId: member.user_id, role })
  }

  const members = membersQuery.data ?? []

  if (!projectId) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <Alert tone="warning">No active project is selected. Sign in again to open project users.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-950">Users</h1>
        <p className="mt-1 text-sm text-gray-500">Users with explicit access to this project.</p>
      </div>

      {membersQuery.isError && <Alert tone="error">Could not load project users.</Alert>}
      {updateMember.isError && <Alert tone="error">Could not update project role.</Alert>}
      {removeMember.isError && <Alert tone="error">Could not remove project access.</Alert>}

      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-[760px] w-full text-left text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">User</th>
                <th scope="col" className="px-4 py-3 font-medium">Organization role</th>
                <th scope="col" className="px-4 py-3 font-medium">Project role</th>
                <th scope="col" className="px-4 py-3 font-medium">Updated</th>
                <th scope="col" className="px-4 py-3 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {membersQuery.isLoading && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-gray-600">Loading project users...</td>
                </tr>
              )}
              {!membersQuery.isLoading && !membersQuery.isError && members.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-gray-600">No users have explicit access to this project.</td>
                </tr>
              )}
              {members.map(member => (
                <tr key={member.user_id} className="align-middle hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{member.email}</div>
                    <div className="mt-1 text-xs text-gray-500">{member.is_active ? 'active' : 'inactive'}</div>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{member.org_role}</td>
                  <td className="px-4 py-3">
                    <select
                      value={member.project_role}
                      onChange={event => changeProjectRole(member, event.target.value as ProjectMembershipRole)}
                      disabled={updateMember.isPending}
                      className="min-h-9 w-36 rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900 disabled:bg-gray-100 disabled:text-gray-500"
                    >
                      {projectRoleOptions.map(option => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-700">{formatDateTime(member.updated_at)}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => removeMember.mutate(member.user_id)}
                      disabled={removeMember.isPending}
                      className="min-h-9 rounded-md border border-red-200 bg-white px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
