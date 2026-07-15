import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { format } from 'date-fns'
import { OnboardingSetup } from '../components/OnboardingSetup'
import {
  dashboardQueryKeys,
  getMetricsAnalytics,
  getMetricsOverview,
  getMetricsTimeseries,
  type AnalyticsResponse,
  type AnalyticsTrace,
  type CostByModel,
  type CostByProvider,
  type ErrorFingerprint,
  type ErrorMessageGroup,
  type ErrorsByModel,
  type ErrorsByProvider,
  type FailedTrace,
  type LatencyByModel,
  type LatencyByProvider,
  type Period,
} from '../api/dashboard'

function formatNumber(value?: number | string | null) {
  return Number(value ?? 0).toLocaleString()
}

function formatCurrency(value?: number | string | null) {
  return `$${Number(value ?? 0).toFixed(4)}`
}

function formatMs(value?: number | string | null) {
  return `${Number(value ?? 0).toFixed(0)}ms`
}

function formatBucket(value: string, period: Period) {
  return format(new Date(value), period === '30d' ? 'dd MMM' : 'HH:mm')
}

function traceHref(trace: AnalyticsTrace) {
  const params = new URLSearchParams()
  if (trace.started_at) params.set('started_at', trace.started_at)
  const query = params.toString()
  return `/dashboard/traces/${trace.trace_id}${query ? `?${query}` : ''}`
}

function failedTraceHref(trace: FailedTrace) {
  const params = new URLSearchParams()
  if (trace.started_at) params.set('started_at', trace.started_at)
  const query = params.toString()
  return `/dashboard/traces/${trace.trace_id}${query ? `?${query}` : ''}`
}

function MetricCard({
  label,
  value,
  loading,
  variant = 'default',
}: {
  label: string
  value?: string
  loading?: boolean
  variant?: 'default' | 'danger'
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-1 text-sm text-gray-500">{label}</div>
      {loading ? (
        <div className="h-7 w-24 animate-pulse rounded bg-gray-100" />
      ) : (
        <div className={`text-2xl font-semibold ${variant === 'danger' ? 'text-red-500' : 'text-gray-900'}`}>
          {value ?? '-'}
        </div>
      )}
    </div>
  )
}

function ChartCard({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h2 className="mb-4 text-sm font-medium text-gray-500">{title}</h2>
      {children}
    </div>
  )
}

function ResponsiveLineChart({
  chartKey,
  data,
  height,
  yAxisTickFormatter,
  children,
}: {
  chartKey: string
  data: unknown[]
  height: number
  yAxisTickFormatter?: (value: number | string) => string
  children: React.ReactNode
}) {
  return (
    <ResponsiveContainer key={chartKey} width="100%" height={height} debounce={50}>
      <LineChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f5f5f5" />
        {children}
        <YAxis tickFormatter={yAxisTickFormatter} />
      </LineChart>
    </ResponsiveContainer>
  )
}

function BreakdownTable({
  title,
  label,
  rows,
  kind,
}: {
  title: string
  label: string
  rows: Array<CostByModel | CostByProvider | LatencyByModel | LatencyByProvider>
  kind: 'cost' | 'latency'
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-950">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-100 text-sm">
          <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-3">{label}</th>
              {kind === 'cost' ? (
                <>
                  <th className="px-4 py-3">Cost</th>
                  <th className="px-4 py-3">Tokens</th>
                </>
              ) : (
                <>
                  <th className="px-4 py-3">P95</th>
                  <th className="px-4 py-3">Avg</th>
                </>
              )}
              <th className="px-4 py-3">Spans</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-gray-500" colSpan={4}>
                  No data
                </td>
              </tr>
            ) : (
              rows.map(row => {
                const label = 'model' in row ? row.model : row.provider
                return (
                  <tr key={label}>
                    <td className="px-4 py-3 font-medium text-gray-950">{label}</td>
                    {kind === 'cost' ? (
                      <>
                        <td className="px-4 py-3 text-gray-700">
                          {formatCurrency((row as CostByModel).total_cost_usd)}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {'total_tokens' in row ? formatNumber(row.total_tokens) : '-'}
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="px-4 py-3 text-gray-700">
                          {formatMs((row as LatencyByModel).p95_latency_ms)}
                        </td>
                        <td className="px-4 py-3 text-gray-700">
                          {formatMs((row as LatencyByModel).avg_latency_ms)}
                        </td>
                      </>
                    )}
                    <td className="px-4 py-3 text-gray-700">{formatNumber(row.span_count)}</td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function TraceRankingTable({
  title,
  rows,
  metric,
}: {
  title: string
  rows: AnalyticsTrace[]
  metric: 'cost' | 'latency'
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-950">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-100 text-sm">
          <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-3">Trace</th>
              <th className="px-4 py-3">{metric === 'cost' ? 'Cost' : 'Max latency'}</th>
              <th className="px-4 py-3">Spans</th>
              <th className="px-4 py-3">Started</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-gray-500" colSpan={4}>
                  No data
                </td>
              </tr>
            ) : (
              rows.map(trace => (
                <tr key={trace.trace_id}>
                  <td className="px-4 py-3">
                    <Link className="font-medium text-blue-600 hover:text-blue-700" to={traceHref(trace)}>
                      {trace.trace_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-700">
                    {metric === 'cost' ? formatCurrency(trace.total_cost_usd) : formatMs(trace.max_latency_ms)}
                  </td>
                  <td className="px-4 py-3 text-gray-700">{formatNumber(trace.span_count)}</td>
                  <td className="px-4 py-3 text-gray-700">
                    {trace.started_at ? format(new Date(trace.started_at), 'dd MMM HH:mm') : '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ErrorBreakdownTable({
  title,
  label,
  rows,
}: {
  title: string
  label: string
  rows: Array<ErrorsByModel | ErrorsByProvider>
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-950">{title}</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-100 text-sm">
          <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-3">{label}</th>
              <th className="px-4 py-3">Error rate</th>
              <th className="px-4 py-3">Errors</th>
              <th className="px-4 py-3">Spans</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-gray-500" colSpan={4}>
                  No data
                </td>
              </tr>
            ) : (
              rows.map(row => {
                const value = 'model' in row ? row.model : row.provider
                return (
                  <tr key={value}>
                    <td className="px-4 py-3 font-medium text-gray-950">{value}</td>
                    <td className="px-4 py-3 text-gray-700">{Number(row.error_rate_pct ?? 0).toFixed(2)}%</td>
                    <td className="px-4 py-3 text-gray-700">{formatNumber(row.error_count)}</td>
                    <td className="px-4 py-3 text-gray-700">{formatNumber(row.span_count)}</td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ErrorMessagesTable({ rows }: { rows: ErrorMessageGroup[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-950">Top error messages</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-100 text-sm">
          <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-3">Message</th>
              <th className="px-4 py-3">Errors</th>
              <th className="px-4 py-3">Last seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-gray-500" colSpan={3}>
                  No data
                </td>
              </tr>
            ) : (
              rows.map(row => (
                <tr key={`${row.error_message}-${row.last_seen_at ?? ''}`}>
                  <td className="max-w-[34rem] px-4 py-3 text-gray-950">
                    <div className="truncate" title={row.error_message}>
                      {row.error_message}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{formatNumber(row.error_count)}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                    {row.last_seen_at ? format(new Date(row.last_seen_at), 'dd MMM HH:mm') : '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FailedTracesTable({ rows }: { rows: FailedTrace[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-950">Recent failed traces</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-100 text-sm">
          <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-3">Trace</th>
              <th className="px-4 py-3">Errors</th>
              <th className="px-4 py-3">Last error</th>
              <th className="px-4 py-3">Started</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-gray-500" colSpan={4}>
                  No data
                </td>
              </tr>
            ) : (
              rows.map(trace => (
                <tr key={trace.trace_id}>
                  <td className="px-4 py-3">
                    <Link className="font-medium text-blue-600 hover:text-blue-700" to={failedTraceHref(trace)}>
                      {trace.trace_id.slice(0, 8)}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{formatNumber(trace.error_count)}</td>
                  <td className="max-w-[28rem] px-4 py-3 text-gray-700">
                    <div className="truncate" title={trace.error_message ?? ''}>
                      {trace.error_message ?? '-'}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                    {trace.started_at ? format(new Date(trace.started_at), 'dd MMM HH:mm') : '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ErrorFingerprintsTable({ rows }: { rows: ErrorFingerprint[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-gray-950">Error fingerprints</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-100 text-sm">
          <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-3">Fingerprint</th>
              <th className="px-4 py-3">Errors</th>
              <th className="px-4 py-3">Traces</th>
              <th className="px-4 py-3">Top source</th>
              <th className="px-4 py-3">Last seen</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.length === 0 ? (
              <tr>
                <td className="px-4 py-4 text-gray-500" colSpan={5}>
                  No data
                </td>
              </tr>
            ) : (
              rows.map(row => (
                <tr key={row.fingerprint}>
                  <td className="max-w-[28rem] px-4 py-3 text-gray-950">
                    <div className="truncate font-medium" title={row.sample_message}>
                      {row.sample_message}
                    </div>
                    <div className="mt-1 truncate font-mono text-xs text-gray-500" title={row.fingerprint}>
                      {row.fingerprint}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-700">{formatNumber(row.error_count)}</td>
                  <td className="px-4 py-3 text-gray-700">{formatNumber(row.affected_trace_count)}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                    {[row.top_provider, row.top_model].filter(Boolean).join(' / ') || '-'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-700">
                    {row.last_seen_at ? format(new Date(row.last_seen_at), 'dd MMM HH:mm') : '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ErrorAnalyticsSections({
  analytics,
  period,
}: {
  analytics?: AnalyticsResponse
  period: Period
}) {
  return (
    <div className="space-y-4">
      <ChartCard title="Error rate trend">
        <ResponsiveLineChart
          chartKey={`error-rate-${period}`}
          data={analytics?.error_rate_trend ?? []}
          height={220}
          yAxisTickFormatter={value => `${Number(value).toFixed(0)}%`}
        >
          <XAxis dataKey="bucket" tickFormatter={value => formatBucket(value, period)} />
          <Tooltip
            formatter={value => [`${Number(value ?? 0).toFixed(2)}%`, 'Error rate']}
            labelFormatter={value => format(new Date(value), 'dd MMM HH:mm')}
          />
          <Line
            type="linear"
            dataKey="error_rate_pct"
            stroke="#dc2626"
            dot={false}
            strokeWidth={2}
            isAnimationActive
            animationDuration={450}
            animationEasing="ease-out"
          />
        </ResponsiveLineChart>
      </ChartCard>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ErrorBreakdownTable title="Errors by model" label="Model" rows={analytics?.errors_by_model ?? []} />
        <ErrorBreakdownTable title="Errors by provider" label="Provider" rows={analytics?.errors_by_provider ?? []} />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ErrorMessagesTable rows={analytics?.top_error_messages ?? []} />
        <FailedTracesTable rows={analytics?.recent_failed_traces ?? []} />
      </div>

      <ErrorFingerprintsTable rows={analytics?.error_fingerprints ?? []} />
    </div>
  )
}

function AnalyticsSections({
  analytics,
  period,
}: {
  analytics?: AnalyticsResponse
  period: Period
}) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartCard title="Cost over time">
          <ResponsiveLineChart
            chartKey={`cost-over-time-${period}`}
            data={analytics?.cost_over_time ?? []}
            height={220}
            yAxisTickFormatter={value => `$${Number(value).toFixed(2)}`}
          >
            <XAxis dataKey="bucket" tickFormatter={value => formatBucket(value, period)} />
            <Tooltip
              formatter={value => [formatCurrency(value as number | string), 'Cost']}
              labelFormatter={value => format(new Date(value), 'dd MMM HH:mm')}
            />
            <Line
              type="monotone"
              dataKey="total_cost_usd"
              stroke="#16a34a"
              dot={false}
              strokeWidth={2}
              isAnimationActive
              animationDuration={450}
              animationEasing="ease-out"
            />
          </ResponsiveLineChart>
        </ChartCard>

        <ChartCard title="Span volume">
          <ResponsiveLineChart chartKey={`span-volume-${period}`} data={analytics?.cost_over_time ?? []} height={220}>
            <XAxis dataKey="bucket" tickFormatter={value => formatBucket(value, period)} />
            <Tooltip labelFormatter={value => format(new Date(value), 'dd MMM HH:mm')} />
            <Line
              type="monotone"
              dataKey="span_count"
              stroke="#3b82f6"
              dot={false}
              strokeWidth={2}
              isAnimationActive
              animationDuration={450}
              animationEasing="ease-out"
            />
          </ResponsiveLineChart>
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <BreakdownTable title="Cost by model" label="Model" rows={analytics?.cost_by_model ?? []} kind="cost" />
        <BreakdownTable title="Cost by provider" label="Provider" rows={analytics?.cost_by_provider ?? []} kind="cost" />
        <BreakdownTable title="Latency by model" label="Model" rows={analytics?.latency_by_model ?? []} kind="latency" />
        <BreakdownTable
          title="Latency by provider"
          label="Provider"
          rows={analytics?.latency_by_provider ?? []}
          kind="latency"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <TraceRankingTable title="Top expensive traces" rows={analytics?.top_expensive_traces ?? []} metric="cost" />
        <TraceRankingTable title="Slowest traces" rows={analytics?.slowest_traces ?? []} metric="latency" />
      </div>
    </div>
  )
}

export function Overview({ projectId }: { projectId: string }) {
  const [period, setPeriod] = useState<Period>('24h')

  const {
    data: metrics,
    isLoading,
    isError,
  } = useQuery({
    queryKey: dashboardQueryKeys.overview(projectId, period),
    queryFn: () => getMetricsOverview(projectId, period),
    refetchInterval: 30_000,
    staleTime: 15_000,
    enabled: !!projectId,
  })

  const { data: timeseries } = useQuery({
    queryKey: dashboardQueryKeys.timeseries(projectId, period),
    queryFn: () => getMetricsTimeseries(projectId, period),
    refetchInterval: 60_000,
    enabled: !!projectId,
  })

  const { data: analytics, isError: isAnalyticsError } = useQuery({
    queryKey: dashboardQueryKeys.analytics(projectId, period),
    queryFn: () => getMetricsAnalytics(projectId, period),
    refetchInterval: 60_000,
    enabled: !!projectId,
  })

  const totalSpans = Number(metrics?.total_spans ?? 0)
  const hasNoSpans = !isLoading && !isError && !!projectId && totalSpans === 0

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-950">Overview</h1>
          <p className="mt-1 text-sm text-gray-500">Latency, errors, usage and spend for the active project.</p>
        </div>
        <div className="flex w-full gap-2 overflow-x-auto sm:w-auto">
          {(['1h', '24h', '7d', '30d'] as Period[]).map(value => (
            <button
              key={value}
              type="button"
              onClick={() => setPeriod(value)}
              className={`min-h-9 min-w-14 rounded-md px-3 text-sm font-medium ${
                period === value
                  ? 'bg-blue-600 text-white'
                  : 'border border-gray-200 bg-white text-gray-700 hover:bg-gray-100'
              }`}
            >
              {value}
            </button>
          ))}
        </div>
      </div>

      {!projectId && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          No active project is selected. Sign in again or create an account to open the overview.
        </div>
      )}

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Could not load overview metrics. Check that the API is running and your session is still valid.
        </div>
      )}

      {isAnalyticsError && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Analytics breakdowns could not be loaded. Summary metrics are still available.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Spans" value={metrics?.total_spans?.toLocaleString()} loading={isLoading} />
        <MetricCard label="P95 Latency" value={formatMs(metrics?.p95_latency_ms)} loading={isLoading} />
        <MetricCard
          label="Error Rate"
          value={`${Number(metrics?.error_rate_pct ?? 0).toFixed(2)}%`}
          variant={Number(metrics?.error_rate_pct ?? 0) > 5 ? 'danger' : 'default'}
          loading={isLoading}
        />
        <MetricCard label="Total Cost" value={formatCurrency(metrics?.total_cost_usd)} loading={isLoading} />
      </div>

      {hasNoSpans ? (
        <OnboardingSetup title="No spans yet" />
      ) : (
        <>
          <ChartCard title="Avg latency (ms)">
            <ResponsiveLineChart chartKey={`avg-latency-${period}`} data={timeseries ?? []} height={200}>
              <XAxis dataKey="bucket" tickFormatter={value => formatBucket(value, period)} />
              <Tooltip labelFormatter={value => format(new Date(value), 'dd MMM HH:mm')} />
              <Line
                type="monotone"
                dataKey="avg_latency"
                stroke="#3b82f6"
                dot={false}
                strokeWidth={2}
                isAnimationActive
                animationDuration={450}
                animationEasing="ease-out"
              />
            </ResponsiveLineChart>
          </ChartCard>
          <ErrorAnalyticsSections analytics={analytics} period={period} />
          <AnalyticsSections analytics={analytics} period={period} />
        </>
      )}
    </div>
  )
}
