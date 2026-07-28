import { useMemo, useState, type FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { getApiErrorMessage } from '../api/errors'
import {
  dashboardQueryKeys,
  listAuditEvents,
  listUsers,
  type AuditLogEvent,
} from '../api/dashboard'

function formatDateTime(value?: string | null) {
  if (!value) return '-'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'

  return format(date, 'dd MMM yyyy HH:mm:ss')
}

function formatMetadata(metadata: Record<string, unknown>) {
  const entries = Object.entries(metadata)
  if (entries.length === 0) return '-'

  return entries
    .map(([key, value]) => {
      if (value === null || value === undefined) return `${key}: -`
      if (typeof value === 'object') return `${key}: ${JSON.stringify(value)}`
      return `${key}: ${String(value)}`
    })
    .join(', ')
}

function userLabel(event: AuditLogEvent) {
  if (event.user_email) return event.user_email
  if (event.user_id) return event.user_id.slice(0, 8)
  return 'system'
}

export function AuditLog() {
  const [actionDraft, setActionDraft] = useState('')
  const [userDraft, setUserDraft] = useState('')
  const [fromDraft, setFromDraft] = useState('')
  const [toDraft, setToDraft] = useState('')
  const [filters, setFilters] = useState({
    action: '',
    userId: '',
    fromDt: '',
    toDt: '',
  })
  const [cursor, setCursor] = useState('')
  const [events, setEvents] = useState<AuditLogEvent[]>([])

  const usersQuery = useQuery({
    queryKey: dashboardQueryKeys.users(),
    queryFn: listUsers,
  })

  const auditQuery = useQuery({
    queryKey: dashboardQueryKeys.auditEvents(
      filters.action,
      filters.userId,
      filters.fromDt,
      filters.toDt,
      cursor
    ),
    queryFn: () => listAuditEvents({ ...filters, cursor }),
  })

  const shownEvents = useMemo(() => {
    if (cursor) return [...events, ...(auditQuery.data?.events ?? [])]
    return auditQuery.data?.events ?? []
  }, [auditQuery.data?.events, cursor, events])

  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setEvents([])
    setCursor('')
    setFilters({
      action: actionDraft,
      userId: userDraft,
      fromDt: fromDraft,
      toDt: toDraft,
    })
  }

  const loadMore = () => {
    if (!auditQuery.data?.next_cursor) return
    setEvents(shownEvents)
    setCursor(auditQuery.data.next_cursor)
  }

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-950">Audit Log</h1>
        <p className="mt-1 text-sm text-gray-500">Review governance events for this organization.</p>
      </div>

      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <form onSubmit={applyFilters} className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(180px,1fr)_minmax(180px,1fr)_220px_220px_auto]">
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Action</span>
            <input
              value={actionDraft}
              onChange={event => setActionDraft(event.target.value)}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              placeholder="project.settings.update"
              maxLength={100}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">User</span>
            <select
              value={userDraft}
              onChange={event => setUserDraft(event.target.value)}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
            >
              <option value="">All users</option>
              {(usersQuery.data ?? []).map(user => (
                <option key={user.id} value={user.id}>{user.email}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">From</span>
            <input
              type="datetime-local"
              value={fromDraft}
              onChange={event => setFromDraft(event.target.value)}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">To</span>
            <input
              type="datetime-local"
              value={toDraft}
              onChange={event => setToDraft(event.target.value)}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
            />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              className="min-h-10 w-full rounded-md bg-gray-900 px-4 text-sm font-medium text-white hover:bg-gray-700 xl:w-auto"
            >
              Apply
            </button>
          </div>
        </form>
      </section>

      <section className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <div className="overflow-x-auto">
          <table className="min-w-[1100px] w-full text-left text-sm">
            <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">Time</th>
                <th scope="col" className="px-4 py-3 font-medium">Action</th>
                <th scope="col" className="px-4 py-3 font-medium">User</th>
                <th scope="col" className="px-4 py-3 font-medium">Resource</th>
                <th scope="col" className="px-4 py-3 font-medium">Metadata</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {auditQuery.isLoading && shownEvents.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-gray-600">Loading audit events...</td>
                </tr>
              )}
              {auditQuery.isError && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-red-700">
                    {getApiErrorMessage(auditQuery.error, 'Could not load audit events.')}
                  </td>
                </tr>
              )}
              {!auditQuery.isLoading && !auditQuery.isError && shownEvents.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-gray-600">No audit events found.</td>
                </tr>
              )}
              {shownEvents.map(event => (
                <tr key={event.id} className="align-top hover:bg-gray-50">
                  <td className="whitespace-nowrap px-4 py-3 text-gray-700">{formatDateTime(event.created_at)}</td>
                  <td className="px-4 py-3 font-medium text-gray-900">{event.action}</td>
                  <td className="px-4 py-3 text-gray-700">{userLabel(event)}</td>
                  <td className="px-4 py-3 text-gray-700">{event.resource_id ?? '-'}</td>
                  <td className="px-4 py-3 text-gray-700">{formatMetadata(event.metadata)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {auditQuery.data?.next_cursor && (
          <div className="border-t border-gray-100 p-4">
            <button
              type="button"
              onClick={loadMore}
              disabled={auditQuery.isFetching}
              className="min-h-10 rounded-md border border-gray-200 bg-white px-4 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {auditQuery.isFetching ? 'Loading...' : 'Load more'}
            </button>
          </div>
        )}
      </section>
    </div>
  )
}
