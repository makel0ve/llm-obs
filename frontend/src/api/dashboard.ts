import { api } from './client'

export type Period = '1h' | '24h' | '7d' | '30d'
export type StatusFilter = 'all' | 'ok' | 'error'
export type AlertMetric = 'latency_p95' | 'error_rate' | 'cost_hourly' | 'anomaly'
export type AlertCondition = 'gt' | 'lt' | 'anomaly'

export type AuthResponse = {
  access_token: string
  project_id?: string | null
  api_key?: string
}

export type OverviewMetrics = {
  total_spans?: number | string | null
  p95_latency_ms?: number | string | null
  error_rate_pct?: number | string | null
  total_cost_usd?: number | string | null
}

export type TimeseriesPoint = {
  bucket: string
  cost?: number | string | null
  avg_latency?: number | string | null
  span_count?: number | string | null
  error_count?: number | string | null
}

export type TraceSummary = {
  id: string
  started_at: string
  ended_at?: string | null
  total_tokens?: number | null
  total_cost_usd?: number | string | null
  span_count?: number | null
  status?: 'ok' | 'error' | string | null
}

export type TraceListResponse = {
  traces: TraceSummary[]
  next_cursor: string | null
  has_more: boolean
}

export type TraceSpan = {
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

export type TraceDetailResponse = {
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

export type AlertRule = {
  id: string
  project_id: string
  name: string
  metric: AlertMetric
  condition: AlertCondition
  threshold?: number | string | null
  window_minutes: number
  cooldown_minutes: number
  notify_slack_webhook?: string | null
  notify_email?: string | null
  is_active: boolean
  created_at?: string | null
}

export type AlertEvent = {
  id: string
  rule_id: string
  triggered_at: string
  value: number | string
  message: string
  resolved_at?: string | null
}

export type AlertRuleCreate = {
  project_id: string
  name: string
  metric: AlertMetric
  condition: AlertCondition
  threshold: number | null
  window_minutes: number
  cooldown_minutes: number
  notify_email: string | null
  notify_slack_webhook: string | null
}

export type AlertRuleUpdate = {
  is_active?: boolean
  threshold?: number
  notify_email?: string
  notify_slack_webhook?: string
}

export const dashboardQueryKeys = {
  overview: (projectId: string, period: Period) => ['metrics', 'overview', projectId, period] as const,
  timeseries: (projectId: string, period: Period) => ['metrics', 'timeseries', projectId, period] as const,
  traces: (projectId: string, period: Period, status: StatusFilter, model: string) =>
    ['traces', projectId, period, status, model] as const,
  traceDetail: (projectId: string, traceId: string | undefined, startedAt: string | null, includePayload: boolean) =>
    ['trace-detail', projectId, traceId, startedAt, includePayload] as const,
  alertRules: (projectId: string) => ['alert-rules', projectId] as const,
  alertEvents: (projectId: string) => ['alert-events', projectId] as const,
}

function projectParams(projectId: string) {
  return new URLSearchParams({ project_id: projectId })
}

export async function registerUser(body: { email: string; password: string; org_name: string }) {
  const response = await api.post<AuthResponse>('/v1/auth/register', body)
  return response.data
}

export async function loginUser(body: { email: string; password: string }) {
  const response = await api.post<AuthResponse>('/v1/auth/login', body)
  return response.data
}

export async function getMetricsOverview(projectId: string, period: Period) {
  const params = projectParams(projectId)
  params.set('period', period)
  const response = await api.get<OverviewMetrics>(`/v1/metrics/overview?${params.toString()}`)
  return response.data
}

export async function getMetricsTimeseries(projectId: string, period: Period) {
  const params = projectParams(projectId)
  params.set('period', period)
  const response = await api.get<TimeseriesPoint[]>(`/v1/metrics/timeseries?${params.toString()}`)
  return response.data
}

export async function listTraces({
  projectId,
  fromDt,
  status,
  model,
  cursor,
}: {
  projectId: string
  fromDt: string
  status: StatusFilter
  model: string
  cursor?: string | null
}) {
  const params = projectParams(projectId)
  params.set('from_dt', fromDt)
  params.set('page_size', '50')

  if (status !== 'all') params.set('status', status)
  if (model) params.set('model', model)
  if (cursor) params.set('cursor', cursor)

  const response = await api.get<TraceListResponse>(`/v1/traces?${params.toString()}`)
  return response.data
}

export async function getTraceDetail({
  projectId,
  traceId,
  startedAt,
  includePayload,
}: {
  projectId: string
  traceId: string
  startedAt: string | null
  includePayload: boolean
}) {
  const params = projectParams(projectId)
  params.set('include_payload', includePayload ? 'true' : 'false')
  if (startedAt) params.set('started_at', startedAt)

  const response = await api.get<TraceDetailResponse>(`/v1/traces/${traceId}?${params.toString()}`)
  return response.data
}

export async function listAlertRules(projectId: string) {
  const response = await api.get<AlertRule[]>(`/v1/alerts/rules?${projectParams(projectId).toString()}`)
  return response.data
}

export async function createAlertRule(payload: AlertRuleCreate) {
  await api.post('/v1/alerts/rules', payload)
}

export async function updateAlertRule(ruleId: string, payload: AlertRuleUpdate) {
  await api.patch(`/v1/alerts/rules/${ruleId}`, payload)
}

export async function deleteAlertRule(ruleId: string) {
  await api.delete(`/v1/alerts/rules/${ruleId}`)
}

export async function listAlertEvents(projectId: string) {
  const response = await api.get<AlertEvent[]>(`/v1/alerts/events?${projectParams(projectId).toString()}`)
  return response.data
}

export async function resolveAlertEvent(eventId: string) {
  await api.post(`/v1/alerts/events/${eventId}/resolve`)
}

export async function updateProjectSettings(projectId: string, retentionDays: number) {
  const response = await api.patch<{ retention_days: number }>(`/v1/projects/${projectId}/settings`, {
    retention_days: retentionDays,
  })
  return response.data
}

export async function rotateProjectApiKey(projectId: string) {
  const response = await api.post<{ api_key: string }>(`/v1/projects/${projectId}/rotate-key`)
  return response.data
}
