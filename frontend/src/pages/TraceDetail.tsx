import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api/client'

type TraceSpan = {
  id: string
  trace_id: string
  parent_span_id?: string | null
  name: string
  provider?: string | null
  model?: string | null
  input_tokens?: number | null
  output_tokens?: number | null
  cost_usd?: number | string | null
  latency_ms?: number | null
  status?: 'ok' | 'error' | string | null
  error?: string | null
  started_at: string
  payload_s3_key?: string | null
  metadata?: Record<string, unknown> | string | null
  payload?: unknown
}

type TraceDetailResponse = {
  id: string
  project_id: string
  started_at: string
  ended_at?: string | null
  total_tokens?: number | null
  total_cost_usd?: number | string | null
  span_count?: number | null
  status?: 'ok' | 'error' | string | null
  spans: TraceSpan[]
}

function formatDate(value?: string | null) {
  if (!value) return '-'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'

  return format(date, 'dd MMM HH:mm:ss')
}

function formatNumber(value?: number | null) {
  return Number(value ?? 0).toLocaleString()
}

function formatCost(value?: number | string | null) {
  return `$${Number(value ?? 0).toFixed(4)}`
}

function formatDuration(value?: number | null) {
  return `${Number(value ?? 0).toFixed(0)}ms`
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

function JsonBlock({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === '') {
    return <span className="text-sm text-gray-500">-</span>
  }

  const parsed = typeof value === 'string'
    ? (() => {
        try {
          return JSON.parse(value)
        } catch {
          return value
        }
      })()
    : value

  return (
    <pre className="max-h-72 overflow-auto rounded-md bg-gray-950 p-3 text-xs leading-5 text-gray-100">
      {typeof parsed === 'string' ? parsed : JSON.stringify(parsed, null, 2)}
    </pre>
  )
}

function SummaryCard({
  label,
  value,
}: {
  label: string
  value: string | number
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="text-sm text-gray-500">{label}</div>
      <div className="mt-1 text-xl font-semibold text-gray-950">{value}</div>
    </div>
  )
}

function getTimelineBounds(spans: TraceSpan[]) {
  const starts = spans.map(span => new Date(span.started_at).getTime()).filter(Number.isFinite)
  const minStart = Math.min(...starts)
  const maxEnd = Math.max(
    ...spans.map(span => {
      const start = new Date(span.started_at).getTime()
      return Number.isFinite(start) ? start + Number(span.latency_ms ?? 0) : 0
    }),
  )

  return {
    minStart: Number.isFinite(minStart) ? minStart : 0,
    duration: Math.max(1, maxEnd - minStart),
  }
}

function SpanRow({ span, minStart, duration }: { span: TraceSpan; minStart: number; duration: number }) {
  const start = new Date(span.started_at).getTime()
  const latency = Math.max(1, Number(span.latency_ms ?? 0))
  const offsetPct = Number.isFinite(start) ? Math.max(0, ((start - minStart) / duration) * 100) : 0
  const widthPct = Math.max(2, Math.min(100 - offsetPct, (latency / duration) * 100))

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-gray-950">{span.name}</h2>
            <StatusBadge status={span.status} />
          </div>
          <p className="mt-1 break-all text-xs text-gray-500">{span.id}</p>
        </div>
        <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4 xl:min-w-[520px]">
          <div>
            <div className="text-xs text-gray-500">Provider</div>
            <div className="font-medium text-gray-900">{span.provider ?? '-'}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Model</div>
            <div className="font-medium text-gray-900">{span.model ?? '-'}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Latency</div>
            <div className="font-medium text-gray-900">{formatDuration(span.latency_ms)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Cost</div>
            <div className="font-medium text-gray-900">{formatCost(span.cost_usd)}</div>
          </div>
        </div>
      </div>

      <div className="mt-4">
        <div className="h-3 rounded-full bg-gray-100">
          <div
            className={`h-3 rounded-full ${span.status === 'error' ? 'bg-red-500' : 'bg-blue-500'}`}
            style={{ marginLeft: `${offsetPct}%`, width: `${widthPct}%` }}
          />
        </div>
        <div className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div>
            <div className="text-xs text-gray-500">Started</div>
            <div className="font-medium text-gray-900">{formatDate(span.started_at)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Input tokens</div>
            <div className="font-medium text-gray-900">{formatNumber(span.input_tokens)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Output tokens</div>
            <div className="font-medium text-gray-900">{formatNumber(span.output_tokens)}</div>
          </div>
          <div>
            <div className="text-xs text-gray-500">Parent span</div>
            <div className="truncate font-medium text-gray-900">{span.parent_span_id ?? '-'}</div>
          </div>
        </div>
      </div>

      {span.error && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          <div className="font-medium">Error</div>
          <div className="mt-1 whitespace-pre-wrap">{span.error}</div>
        </div>
      )}

      <div className="mt-4">
        <div className="mb-2 text-sm font-medium text-gray-700">Metadata</div>
        <JsonBlock value={span.metadata} />
      </div>

      {'payload' in span && (
        <div className="mt-4">
          <div className="mb-2 text-sm font-medium text-gray-700">Payload</div>
          <JsonBlock value={span.payload} />
        </div>
      )}
    </div>
  )
}

export function TraceDetail({ projectId }: { projectId: string }) {
  const { traceId } = useParams()
  const [searchParams] = useSearchParams()
  const [includePayload, setIncludePayload] = useState(false)
  const startedAt = searchParams.get('started_at')

  const query = useQuery({
    queryKey: ['trace-detail', projectId, traceId, startedAt, includePayload],
    queryFn: async () => {
      const params = new URLSearchParams({
        project_id: projectId,
        include_payload: includePayload ? 'true' : 'false',
      })

      if (startedAt) {
        params.set('started_at', startedAt)
      }

      const response = await api.get<TraceDetailResponse>(`/v1/traces/${traceId}?${params.toString()}`)
      return response.data
    },
    enabled: !!projectId && !!traceId,
    retry: false,
  })

  const timeline = useMemo(
    () => getTimelineBounds(query.data?.spans ?? []),
    [query.data?.spans],
  )

  if (!projectId) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          No active project is selected. Sign in again to open trace details.
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <Link to="/traces" className="text-sm font-medium text-blue-700 hover:text-blue-900">
            Back to traces
          </Link>
          <h1 className="mt-3 text-2xl font-semibold text-gray-950">Trace Detail</h1>
          <p className="mt-1 break-all text-sm text-gray-500">{traceId}</p>
        </div>
        <button
          type="button"
          onClick={() => setIncludePayload(value => !value)}
          className={`min-h-10 rounded-md px-4 text-sm font-medium ${
            includePayload
              ? 'bg-red-50 text-red-700 ring-1 ring-red-200 hover:bg-red-100'
              : 'bg-gray-900 text-white hover:bg-gray-700'
          }`}
        >
          {includePayload ? 'Hide payload' : 'Load payload'}
        </button>
      </div>

      {query.isLoading ? (
        <div className="space-y-3">
          <div className="h-28 rounded-lg bg-gray-100 animate-pulse" />
          <div className="h-36 rounded-lg bg-gray-100 animate-pulse" />
          <div className="h-36 rounded-lg bg-gray-100 animate-pulse" />
        </div>
      ) : query.isError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Trace not found or could not be loaded.
        </div>
      ) : query.data ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <SummaryCard label="Status" value={query.data.status ?? 'ok'} />
            <SummaryCard label="Started" value={formatDate(query.data.started_at)} />
            <SummaryCard label="Ended" value={formatDate(query.data.ended_at)} />
            <SummaryCard label="Spans" value={query.data.span_count ?? query.data.spans.length} />
            <SummaryCard label="Cost" value={formatCost(query.data.total_cost_usd)} />
          </div>

          <div className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div>
                <div className="text-sm text-gray-500">Total tokens</div>
                <div className="mt-1 text-xl font-semibold text-gray-950">{formatNumber(query.data.total_tokens)}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Payload mode</div>
                <div className="mt-1 text-xl font-semibold text-gray-950">
                  {includePayload ? 'Loaded' : 'Hidden'}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Timeline duration</div>
                <div className="mt-1 text-xl font-semibold text-gray-950">{formatDuration(timeline.duration)}</div>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <h2 className="text-lg font-semibold text-gray-950">Spans</h2>
              <p className="mt-1 text-sm text-gray-500">Chronological order with relative waterfall timing.</p>
            </div>
            {query.data.spans.length === 0 ? (
              <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6 text-sm text-gray-600">
                No spans are attached to this trace.
              </div>
            ) : (
              query.data.spans.map(span => (
                <SpanRow
                  key={`${span.id}-${span.started_at}`}
                  span={span}
                  minStart={timeline.minStart}
                  duration={timeline.duration}
                />
              ))
            )}
          </div>
        </>
      ) : null}
    </div>
  )
}
