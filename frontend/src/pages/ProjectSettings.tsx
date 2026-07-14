import { useState, type FormEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import {
  assignProjectMember,
  createProjectApiKey,
  dashboardQueryKeys,
  getProjectSettings,
  listProjectApiKeys,
  listProjectMembers,
  listUsers,
  removeProjectMember,
  revokeProjectApiKey,
  rotateProjectApiKey,
  updateProjectSettings,
  type ApiKeyScope,
  type OrganizationUser,
  type PayloadStorageMode,
  type ProjectMember,
  type ProjectMembershipRole,
} from '../api/dashboard'

type CopyState = 'idle' | 'copied' | 'failed'
type ApiKeyDraft = {
  name: string
  description: string
  scope: ApiKeyScope
}
type PayloadPrivacyDraft = {
  payload_storage_mode: PayloadStorageMode | null
  payload_max_bytes: string | null
  payload_redact_keys: string | null
}
type MemberDraft = {
  userId: string
  role: ProjectMembershipRole
}

const scopeOptions: Array<{ value: ApiKeyScope; label: string }> = [
  { value: 'ingest', label: 'Ingest only' },
  { value: 'read', label: 'Read only' },
  { value: 'read_write', label: 'Read/write' },
]

const payloadModeOptions: Array<{ value: PayloadStorageMode; label: string; help: string }> = [
  { value: 'all', label: 'Store all large payloads', help: 'Keep stored objects for spans that exceed the inline threshold.' },
  { value: 'errors', label: 'Store only error payloads', help: 'Keep payload objects only for failed spans.' },
  { value: 'none', label: 'Do not store payloads', help: 'Drop payload objects before S3 storage.' },
]

const projectRoleOptions: Array<{ value: ProjectMembershipRole; label: string }> = [
  { value: 'member', label: 'Member' },
  { value: 'viewer', label: 'Viewer' },
]

function CopyButton({ value, label = 'Copy' }: { value: string; label?: string }) {
  const [state, setState] = useState<CopyState>('idle')

  const copy = async () => {
    try {
      if (!navigator.clipboard) {
        throw new Error('Clipboard API is unavailable')
      }
      await navigator.clipboard.writeText(value)
      setState('copied')
    } catch {
      setState('failed')
    } finally {
      window.setTimeout(() => setState('idle'), 1800)
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      className="min-h-9 rounded-md border border-gray-200 bg-white px-3 text-sm font-medium text-gray-700 hover:bg-gray-100"
    >
      {state === 'copied' ? 'Copied' : state === 'failed' ? 'Failed' : label}
    </button>
  )
}

function CodeRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-gray-700">{label}</div>
        <CopyButton value={value} />
      </div>
      <code className="block overflow-x-auto rounded-md bg-gray-950 p-3 text-sm text-gray-100">
        {value}
      </code>
    </div>
  )
}

function Alert({
  tone,
  children,
}: {
  tone: 'success' | 'error' | 'warning'
  children: ReactNode
}) {
  const classes = {
    success: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    error: 'border-red-200 bg-red-50 text-red-800',
    warning: 'border-amber-200 bg-amber-50 text-amber-800',
  }[tone]

  return <div className={`rounded-lg border p-4 text-sm ${classes}`}>{children}</div>
}

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

function formatScope(scope: ApiKeyScope) {
  return scopeOptions.find(option => option.value === scope)?.label ?? scope
}

export function ProjectSettings({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const [retentionDays, setRetentionDays] = useState<string | null>(null)
  const [savedRetentionDays, setSavedRetentionDays] = useState<number | null>(null)
  const [settingsStatus, setSettingsStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [privacyDraft, setPrivacyDraft] = useState<PayloadPrivacyDraft>({
    payload_storage_mode: null,
    payload_max_bytes: null,
    payload_redact_keys: null,
  })
  const [privacyStatus, setPrivacyStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [rotateStatus, setRotateStatus] = useState<'idle' | 'rotating' | 'success' | 'error'>('idle')
  const [newApiKey, setNewApiKey] = useState('')
  const [keyDraft, setKeyDraft] = useState<ApiKeyDraft>({
    name: '',
    description: '',
    scope: 'ingest',
  })
  const [keyError, setKeyError] = useState('')
  const [createdApiKey, setCreatedApiKey] = useState('')
  const [memberDraft, setMemberDraft] = useState<MemberDraft>({
    userId: '',
    role: 'viewer',
  })
  const [memberMessage, setMemberMessage] = useState('')
  const [memberError, setMemberError] = useState('')

  const settingsQuery = useQuery({
    queryKey: dashboardQueryKeys.projectSettings(projectId),
    queryFn: () => getProjectSettings(projectId),
    enabled: !!projectId,
  })

  const apiKeysQuery = useQuery({
    queryKey: dashboardQueryKeys.apiKeys(projectId),
    queryFn: () => listProjectApiKeys(projectId),
    enabled: !!projectId,
  })

  const usersQuery = useQuery({
    queryKey: dashboardQueryKeys.users(),
    queryFn: listUsers,
    enabled: !!projectId,
  })

  const membersQuery = useQuery({
    queryKey: dashboardQueryKeys.projectMembers(projectId),
    queryFn: () => listProjectMembers(projectId),
    enabled: !!projectId,
  })

  const invalidateApiKeys = async () => {
    await queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.apiKeys(projectId) })
  }

  const invalidateMembers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.projectMembers(projectId) }),
      queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.accessibleProjects() }),
    ])
  }

  const assignMember = useMutation({
    mutationFn: (draft: MemberDraft) => assignProjectMember(projectId, {
      user_id: draft.userId,
      role: draft.role,
    }),
    onSuccess: async member => {
      setMemberDraft({ userId: '', role: 'viewer' })
      setMemberError('')
      setMemberMessage(`Access updated for ${member.email}.`)
      await invalidateMembers()
    },
    onError: () => {
      setMemberMessage('')
      setMemberError('Could not update project access.')
    },
  })

  const removeMember = useMutation({
    mutationFn: (userId: string) => removeProjectMember(projectId, userId),
    onSuccess: async () => {
      setMemberError('')
      setMemberMessage('Project access removed.')
      await invalidateMembers()
    },
    onError: () => {
      setMemberMessage('')
      setMemberError('Could not remove project access.')
    },
  })

  const createKey = useMutation({
    mutationFn: () => createProjectApiKey(projectId, {
      name: keyDraft.name.trim(),
      description: keyDraft.description.trim() || null,
      scope: keyDraft.scope,
    }),
    onSuccess: async result => {
      setCreatedApiKey(result.api_key)
      setKeyDraft({ name: '', description: '', scope: 'ingest' })
      setKeyError('')
      await invalidateApiKeys()
    },
    onError: () => {
      setCreatedApiKey('')
      setKeyError('Could not create API key.')
    },
  })

  const revokeKey = useMutation({
    mutationFn: (keyId: string) => revokeProjectApiKey(projectId, keyId),
    onSuccess: invalidateApiKeys,
    onError: () => setKeyError('Could not revoke API key.'),
  })

  const endpoint = api.defaults.baseURL ?? 'http://localhost:8000'
  const envVars = `LLM_OBS_API_KEY=llmobs_your_key_here\nLLM_OBS_ENDPOINT=${endpoint}`
  const basicExample = `import llm_obs

@llm_obs.trace(name="demo.llm_call")
async def call_llm(prompt: str) -> str:
    return "demo response"

await call_llm("Hello")
await llm_obs.shutdown()`
  const retentionValue = retentionDays ?? String(settingsQuery.data?.retention_days ?? 90)
  const payloadModeValue = privacyDraft.payload_storage_mode ?? settingsQuery.data?.payload_storage_mode ?? 'all'
  const payloadMaxBytesValue = privacyDraft.payload_max_bytes ?? String(settingsQuery.data?.payload_max_bytes ?? 262144)
  const payloadRedactKeysValue =
    privacyDraft.payload_redact_keys ??
    settingsQuery.data?.payload_redact_keys ??
    'api_key,password,secret,token,authorization'

  const updateRetention = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSettingsStatus('saving')

    try {
      const days = Number(retentionValue)
      const response = await updateProjectSettings(projectId, { retention_days: days })
      setRetentionDays(String(response.retention_days))
      setSavedRetentionDays(response.retention_days)
      setSettingsStatus('success')
    } catch {
      setSettingsStatus('error')
    }
  }

  const updatePayloadPrivacy = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setPrivacyStatus('saving')

    try {
      const maxBytes = Number(payloadMaxBytesValue)
      const response = await updateProjectSettings(projectId, {
        payload_storage_mode: payloadModeValue,
        payload_max_bytes: maxBytes,
        payload_redact_keys: payloadRedactKeysValue,
      })
      setPrivacyDraft({
        payload_storage_mode: response.payload_storage_mode,
        payload_max_bytes: String(response.payload_max_bytes),
        payload_redact_keys: response.payload_redact_keys,
      })
      await queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.projectSettings(projectId) })
      setPrivacyStatus('success')
    } catch {
      setPrivacyStatus('error')
    }
  }

  const rotateApiKey = async () => {
    setRotateStatus('rotating')
    setNewApiKey('')

    try {
      const response = await rotateProjectApiKey(projectId)
      setNewApiKey(response.api_key)
      setRotateStatus('success')
    } catch {
      setRotateStatus('error')
    }
  }

  const submitCreateKey = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setCreatedApiKey('')

    if (!keyDraft.name.trim()) {
      setKeyError('Key name is required.')
      return
    }

    setKeyError('')
    createKey.mutate()
  }

  const submitAssignMember = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setMemberMessage('')

    if (!memberDraft.userId) {
      setMemberError('Choose a user.')
      return
    }

    setMemberError('')
    assignMember.mutate(memberDraft)
  }

  const changeProjectRole = (member: ProjectMember, role: ProjectMembershipRole) => {
    if (member.project_role === role) return
    setMemberMessage('')
    setMemberError('')
    assignMember.mutate({ userId: member.user_id, role })
  }

  const members = membersQuery.data ?? []
  const memberUserIds = new Set(members.map(member => member.user_id))
  const assignableUsers = (usersQuery.data ?? []).filter((user: OrganizationUser) => (
    user.is_active && !memberUserIds.has(user.id)
  ))

  if (!projectId) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <Alert tone="warning">No active project is selected. Sign in again to open project settings.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-950">Project Settings</h1>
        <p className="mt-1 text-sm text-gray-500">SDK setup, retention policy and API key rotation for this project.</p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="text-sm text-gray-500">Current project id</div>
        <div className="mt-2 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <code className="block overflow-x-auto rounded-md bg-gray-100 px-3 py-2 text-sm text-gray-900">{projectId}</code>
          <CopyButton value={projectId} />
        </div>
      </div>

      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-950">Project access</h2>
          <p className="mt-1 text-sm text-gray-500">Assign users who can inspect this project.</p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <form onSubmit={submitAssignMember} className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(220px,1fr)_180px_auto]">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">User</span>
              <select
                value={memberDraft.userId}
                onChange={event => setMemberDraft(current => ({
                  ...current,
                  userId: event.target.value,
                }))}
                disabled={usersQuery.isLoading || assignableUsers.length === 0}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900 disabled:bg-gray-100 disabled:text-gray-500"
              >
                <option value="">
                  {usersQuery.isLoading ? 'Loading users...' : 'Select user'}
                </option>
                {assignableUsers.map(user => (
                  <option key={user.id} value={user.id}>
                    {user.email} ({user.role})
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Project role</span>
              <select
                value={memberDraft.role}
                onChange={event => setMemberDraft(current => ({
                  ...current,
                  role: event.target.value as ProjectMembershipRole,
                }))}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              >
                {projectRoleOptions.map(option => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={assignMember.isPending || usersQuery.isLoading || assignableUsers.length === 0}
                className="min-h-10 w-full rounded-md bg-gray-900 px-4 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60 xl:w-auto"
              >
                {assignMember.isPending ? 'Saving...' : 'Assign'}
              </button>
            </div>
          </form>
          <div className="mt-4 space-y-3">
            {usersQuery.isError && <Alert tone="error">Could not load organization users.</Alert>}
            {membersQuery.isError && <Alert tone="error">Could not load project members.</Alert>}
            {memberError && <Alert tone="error">{memberError}</Alert>}
            {memberMessage && <Alert tone="success">{memberMessage}</Alert>}
            {!usersQuery.isLoading && assignableUsers.length === 0 && (
              <Alert tone="warning">All active organization users already have explicit access to this project.</Alert>
            )}
          </div>
        </div>

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
                    <td colSpan={5} className="px-4 py-6 text-gray-600">Loading project members...</td>
                  </tr>
                )}
                {!membersQuery.isLoading && !membersQuery.isError && members.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-6 text-gray-600">No explicit project members yet.</td>
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
                        disabled={assignMember.isPending}
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
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-950">SDK setup</h2>
          <p className="mt-1 text-sm text-gray-500">Use these values in the application that sends LLM spans.</p>
        </div>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <CodeRow label="Install" value="pip install llm-obs-sdk" />
          <CodeRow label="Environment" value={envVars} />
        </div>
        <CodeRow label="Minimal async example" value={basicExample} />
      </section>

      <section className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-lg font-semibold text-gray-950">Retention</h2>
          <p className="mt-1 text-sm text-gray-500">Keep trace data between 7 and 365 days.</p>
          <form onSubmit={updateRetention} className="mt-4 space-y-4">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Retention days</span>
              <input
                type="number"
                min={7}
                max={365}
                value={retentionValue}
                onChange={event => setRetentionDays(event.target.value)}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
                required
              />
            </label>
            <button
              type="submit"
              disabled={settingsStatus === 'saving'}
              className="min-h-10 rounded-md bg-gray-900 px-4 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {settingsStatus === 'saving' ? 'Saving...' : 'Save retention'}
            </button>
          </form>
          {settingsStatus === 'success' && (
            <div className="mt-4">
              <Alert tone="success">Retention updated to {savedRetentionDays} days.</Alert>
            </div>
          )}
          {settingsStatus === 'error' && (
            <div className="mt-4">
              <Alert tone="error">Could not update retention. Check the value and try again.</Alert>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="text-lg font-semibold text-gray-950">Legacy API key</h2>
          <p className="mt-1 text-sm text-gray-500">Rotate the original project key if it was lost or exposed.</p>
          <button
            type="button"
            onClick={rotateApiKey}
            disabled={rotateStatus === 'rotating'}
            className="mt-4 min-h-10 rounded-md bg-red-600 px-4 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {rotateStatus === 'rotating' ? 'Rotating...' : 'Rotate API key'}
          </button>
          {rotateStatus === 'error' && (
            <div className="mt-4">
              <Alert tone="error">Could not rotate the API key. Try again after checking your session.</Alert>
            </div>
          )}
          {newApiKey && (
            <div className="mt-4 space-y-3">
              <Alert tone="warning">
                Save this API key now. It is shown once and cannot be recovered later.
              </Alert>
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-gray-700">New API key</span>
                  <CopyButton value={newApiKey} />
                </div>
                <code className="block overflow-x-auto rounded-md bg-gray-950 p-3 text-sm text-gray-100">
                  {newApiKey}
                </code>
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <h2 className="text-lg font-semibold text-gray-950">Payload privacy</h2>
        <p className="mt-1 text-sm text-gray-500">Control how sensitive LLM input and output payloads are stored.</p>
        {settingsQuery.isError && (
          <div className="mt-4">
            <Alert tone="error">Could not load payload privacy settings.</Alert>
          </div>
        )}
        <form onSubmit={updatePayloadPrivacy} className="mt-4 space-y-4">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(240px,1fr)_220px]">
            <div>
              <span className="text-sm font-medium text-gray-700">Payload storage</span>
              <div className="mt-2 grid grid-cols-1 gap-2 rounded-md border border-gray-200 bg-gray-50 p-1 sm:grid-cols-3">
                {payloadModeOptions.map(option => {
                  const selected = option.value === payloadModeValue

                  return (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setPrivacyDraft(current => ({
                        ...current,
                        payload_storage_mode: option.value,
                      }))}
                      className={`min-h-10 rounded px-3 text-left text-sm font-medium transition sm:text-center ${
                        selected
                          ? 'bg-gray-900 text-white shadow-sm'
                          : 'text-gray-700 hover:bg-white hover:text-gray-950'
                      }`}
                    >
                      {option.label}
                    </button>
                  )
                })}
              </div>
              <span className="mt-1 block text-xs text-gray-500">
                {payloadModeOptions.find(option => option.value === payloadModeValue)?.help}
              </span>
            </div>
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Max payload bytes</span>
              <input
                type="number"
                min={0}
                max={10 * 1024 * 1024}
                value={payloadMaxBytesValue}
                onChange={event => setPrivacyDraft(current => ({
                  ...current,
                  payload_max_bytes: event.target.value,
                }))}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
                required
              />
            </label>
          </div>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Redact keys</span>
            <input
              value={payloadRedactKeysValue}
              onChange={event => setPrivacyDraft(current => ({
                ...current,
                payload_redact_keys: event.target.value,
              }))}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              placeholder="api_key,password,secret,token,authorization"
              maxLength={1000}
            />
            <span className="mt-1 block text-xs text-gray-500">Comma-separated field names are matched case-insensitively before payload storage.</span>
          </label>
          <button
            type="submit"
            disabled={privacyStatus === 'saving' || settingsQuery.isLoading}
            className="min-h-10 rounded-md bg-gray-900 px-4 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {privacyStatus === 'saving' ? 'Saving...' : 'Save payload privacy'}
          </button>
        </form>
        {privacyStatus === 'success' && (
          <div className="mt-4">
            <Alert tone="success">Payload privacy settings updated.</Alert>
          </div>
        )}
        {privacyStatus === 'error' && (
          <div className="mt-4">
            <Alert tone="error">Could not update payload privacy settings.</Alert>
          </div>
        )}
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-950">Managed API keys</h2>
          <p className="mt-1 text-sm text-gray-500">Create scoped keys for ingestion and read-only integrations.</p>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <form onSubmit={submitCreateKey} className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(180px,1fr)_minmax(180px,1fr)_180px_auto]">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Name</span>
              <input
                value={keyDraft.name}
                onChange={event => setKeyDraft(current => ({ ...current, name: event.target.value }))}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
                maxLength={100}
                placeholder="Production ingest"
                required
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Description</span>
              <input
                value={keyDraft.description}
                onChange={event => setKeyDraft(current => ({ ...current, description: event.target.value }))}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
                maxLength={500}
                placeholder="Optional"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Scope</span>
              <select
                value={keyDraft.scope}
                onChange={event => setKeyDraft(current => ({ ...current, scope: event.target.value as ApiKeyScope }))}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              >
                {scopeOptions.map(option => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <div className="flex items-end">
              <button
                type="submit"
                disabled={createKey.isPending}
                className="min-h-10 w-full rounded-md bg-gray-900 px-4 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60 xl:w-auto"
              >
                {createKey.isPending ? 'Creating...' : 'Create key'}
              </button>
            </div>
          </form>
          <div className="mt-4 space-y-3">
            {keyError && <Alert tone="error">{keyError}</Alert>}
            {createdApiKey && (
              <div className="space-y-3">
                <Alert tone="warning">Save this API key now. It is shown once and cannot be recovered later.</Alert>
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <span className="text-sm font-medium text-gray-700">New API key</span>
                    <CopyButton value={createdApiKey} />
                  </div>
                  <code className="block overflow-x-auto rounded-md bg-gray-950 p-3 text-sm text-gray-100">
                    {createdApiKey}
                  </code>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <div className="overflow-x-auto">
            <table className="min-w-[920px] w-full text-left text-sm">
              <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">Name</th>
                  <th scope="col" className="px-4 py-3 font-medium">Scope</th>
                  <th scope="col" className="px-4 py-3 font-medium">Created</th>
                  <th scope="col" className="px-4 py-3 font-medium">Last used</th>
                  <th scope="col" className="px-4 py-3 font-medium">Status</th>
                  <th scope="col" className="px-4 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {apiKeysQuery.isLoading && (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-gray-600">Loading API keys...</td>
                  </tr>
                )}
                {apiKeysQuery.isError && (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-red-700">Could not load API keys.</td>
                  </tr>
                )}
                {!apiKeysQuery.isLoading && !apiKeysQuery.isError && (apiKeysQuery.data ?? []).length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-gray-600">No managed API keys yet.</td>
                  </tr>
                )}
                {(apiKeysQuery.data ?? []).map(key => (
                  <tr key={key.id} className="align-top hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="font-medium text-gray-900">{key.name}</div>
                      {key.description && <div className="mt-1 text-xs text-gray-500">{key.description}</div>}
                    </td>
                    <td className="px-4 py-3 text-gray-700">{formatScope(key.scope)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">{formatDateTime(key.created_at)}</td>
                    <td className="whitespace-nowrap px-4 py-3 text-gray-700">{formatDateTime(key.last_used_at)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex min-h-6 items-center rounded-md px-2 text-xs font-medium ${
                          key.revoked_at || !key.is_active
                            ? 'bg-gray-100 text-gray-600 ring-1 ring-gray-200'
                            : 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
                        }`}
                      >
                        {key.revoked_at || !key.is_active ? 'revoked' : 'active'}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {!key.revoked_at && key.is_active && (
                        <button
                          type="button"
                          onClick={() => revokeKey.mutate(key.id)}
                          disabled={revokeKey.isPending}
                          className="min-h-9 rounded-md border border-red-200 bg-white px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  )
}
