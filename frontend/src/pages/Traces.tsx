import { useMemo, useState, type FormEvent } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { Link } from 'react-router-dom'
import { OnboardingSetup } from '../components/OnboardingSetup'
import {
  dashboardQueryKeys,
  listTraces,
  type Period,
  type StatusFilter,
  type TraceSummary,
} from '../api/dashboard'

const periods: Period[] = ['1h', '24h', '7d', '30d']
const statuses: StatusFilter[] = ['all', 'ok', 'error']

function getFromDate(period: Period) {
  const hours = {
    '1h': 1,
    '24h': 24,
    '7d': 24 * 7,
    '30d': 24 * 30,
  }[period]

  return new Date(Date.now() - hours * 60 * 60 * 1000).toISOString()
}

function formatDate(value?: string | null) {
  if (!value) return '-'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'

  return format(date, 'dd MMM HH:mm:ss')
}

function formatTokens(value?: number | null) {
  return Number(value ?? 0).toLocaleString()
}

function formatCost(value?: number | string | null) {
  return `$${Number(value ?? 0).toFixed(4)}`
}

function StatusBadge({ status }: { status?: string | null }) {
  const isError = status === 'error'

  return (
    <span
      className={`inline-flex min-h-7 items-center rounded-md px-2 text-xs font-medium ${
        isError
          ? 'bg-red-50 text-red-700 ring-1 ring-red-200'
          : 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
      }`}
    >
      {status ?? 'ok'}
    </span>
  )
}

function EmptyState({ filtered }: { filtered: boolean }) {
  if (!filtered) {
    return <OnboardingSetup title="No traces yet" />
  }

  return (
    <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6">
      <h2 className="text-lg font-semibold text-gray-950">No matching traces</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-600">
        Change the status or model filters, then refresh this page.
      </p>
    </div>
  )
}

function TraceTable({ traces }: { traces: TraceSummary[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="overflow-x-auto">
        <table className="min-w-[760px] w-full text-left text-sm">
          <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium">Started</th>
              <th scope="col" className="px-4 py-3 font-medium">Status</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Spans</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Tokens</th>
              <th scope="col" className="px-4 py-3 text-right font-medium">Cost</th>
              <th scope="col" className="px-4 py-3 font-medium">Trace</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {traces.map(trace => (
              <tr key={trace.id} className="hover:bg-gray-50">
                <td className="whitespace-nowrap px-4 py-3 text-gray-900">
                  {formatDate(trace.started_at)}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={trace.status} />
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                  {trace.span_count ?? 0}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                  {formatTokens(trace.total_tokens)}
                </td>
                <td className="px-4 py-3 text-right tabular-nums text-gray-700">
                  {formatCost(trace.total_cost_usd)}
                </td>
                <td className="px-4 py-3">
                  <Link
                    to={`/traces/${trace.id}?started_at=${encodeURIComponent(trace.started_at)}`}
                    className="font-medium text-blue-700 hover:text-blue-900"
                  >
                    {trace.id.slice(0, 8)}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function Traces({ projectId }: { projectId: string }) {
  const [period, setPeriod] = useState<Period>('24h')
  const [status, setStatus] = useState<StatusFilter>('all')
  const [modelInput, setModelInput] = useState('')
  const [model, setModel] = useState('')

  const query = useInfiniteQuery({
    queryKey: dashboardQueryKeys.traces(projectId, period, status, model),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => (
      listTraces({
        projectId,
        fromDt: getFromDate(period),
        status,
        model,
        cursor: pageParam,
      })
    ),
    getNextPageParam: lastPage => lastPage.next_cursor ?? undefined,
    refetchInterval: 30_000,
    staleTime: 15_000,
    enabled: !!projectId,
  })

  const traces = useMemo(
    () => query.data?.pages.flatMap(page => page.traces) ?? [],
    [query.data],
  )
  const hasActiveFilter = status !== 'all' || !!model

  const applyModelFilter = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setModel(modelInput.trim())
  }

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-950">Traces</h1>
          <p className="mt-1 text-sm text-gray-500">Inspect recent LLM calls by time range, status and model.</p>
        </div>
        <form onSubmit={applyModelFilter} className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <input
            type="search"
            value={modelInput}
            onChange={event => setModelInput(event.target.value)}
            placeholder="Filter model"
            className="min-h-10 rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900 placeholder:text-gray-400 sm:w-56"
          />
          <button
            type="submit"
            className="min-h-10 rounded-md bg-gray-900 px-3 text-sm font-medium text-white hover:bg-gray-700"
          >
            Apply
          </button>
        </form>
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex gap-2 overflow-x-auto">
          {periods.map(item => (
            <button
              key={item}
              type="button"
              onClick={() => setPeriod(item)}
              className={`min-h-9 min-w-14 rounded-md px-3 text-sm font-medium ${
                period === item
                  ? 'bg-blue-600 text-white'
                  : 'border border-gray-200 bg-white text-gray-700 hover:bg-gray-100'
              }`}
            >
              {item}
            </button>
          ))}
        </div>

        <div className="flex gap-2 overflow-x-auto">
          {statuses.map(item => (
            <button
              key={item}
              type="button"
              onClick={() => setStatus(item)}
              className={`min-h-9 min-w-16 rounded-md px-3 text-sm font-medium capitalize ${
                status === item
                  ? 'bg-gray-900 text-white'
                  : 'border border-gray-200 bg-white text-gray-700 hover:bg-gray-100'
              }`}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {model && (
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <span>Model filter:</span>
          <span className="rounded-md bg-gray-100 px-2 py-1 font-medium text-gray-900">{model}</span>
          <button
            type="button"
            onClick={() => {
              setModel('')
              setModelInput('')
            }}
            className="font-medium text-blue-700 hover:text-blue-900"
          >
            Clear
          </button>
        </div>
      )}

      {!projectId ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          No active project is selected. Sign in again or create an account to open traces.
        </div>
      ) : query.isLoading ? (
        <div className="space-y-3">
          <div className="h-14 rounded-lg bg-gray-100 animate-pulse" />
          <div className="h-14 rounded-lg bg-gray-100 animate-pulse" />
          <div className="h-14 rounded-lg bg-gray-100 animate-pulse" />
        </div>
      ) : query.isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Could not load traces. Check that the API is running and your session is still valid.
        </div>
      ) : traces.length === 0 ? (
        <EmptyState filtered={hasActiveFilter} />
      ) : (
        <>
          <TraceTable traces={traces} />
          {query.hasNextPage && (
            <div className="flex justify-center">
              <button
                type="button"
                onClick={() => query.fetchNextPage()}
                disabled={query.isFetchingNextPage}
                className="min-h-10 rounded-md border border-gray-200 bg-white px-4 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {query.isFetchingNextPage ? 'Loading...' : 'Load more'}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
