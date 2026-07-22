import { api } from './client'

export type Period = '1h' | '24h' | '7d' | '30d'
export type StatusFilter = 'all' | 'ok' | 'error'
export type AlertMetric = 'latency_p95' | 'error_rate' | 'cost_hourly' | 'anomaly'
export type AlertCondition = 'gt' | 'lt' | 'anomaly'
export type UserRole = 'admin' | 'member' | 'viewer'
export type ApiKeyScope = 'ingest' | 'read' | 'read_write'
export type PayloadStorageMode = 'all' | 'errors' | 'none'
export type PayloadStorageStatus = 'stored' | 'stored_redacted' | 'omitted' | 'too_large' | 'storage_failed'
export type ProjectMembershipRole = 'member' | 'viewer'

export type AuthResponse = {
  access_token: string
  project_id?: string | null
  api_key?: string
  role: UserRole
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

export type CostByModel = {
  model: string
  total_cost_usd?: number | string | null
  total_tokens?: number | string | null
  span_count?: number | string | null
}

export type CostByProvider = {
  provider: string
  total_cost_usd?: number | string | null
  total_tokens?: number | string | null
  span_count?: number | string | null
}

export type CostOverTimePoint = {
  bucket: string
  total_cost_usd?: number | string | null
  span_count?: number | string | null
}

export type LatencyByModel = {
  model: string
  avg_latency_ms?: number | string | null
  p95_latency_ms?: number | string | null
  span_count?: number | string | null
}

export type LatencyByProvider = {
  provider: string
  avg_latency_ms?: number | string | null
  p95_latency_ms?: number | string | null
  span_count?: number | string | null
}

export type AnalyticsTrace = {
  trace_id: string
  total_cost_usd?: number | string | null
  max_latency_ms?: number | string | null
  avg_latency_ms?: number | string | null
  span_count?: number | string | null
  started_at?: string | null
}

export type ErrorRatePoint = {
  bucket: string
  span_count?: number | string | null
  error_count?: number | string | null
  error_rate_pct?: number | string | null
}

export type ErrorMessageGroup = {
  error_message: string
  error_count?: number | string | null
  last_seen_at?: string | null
}

export type ErrorsByModel = {
  model: string
  span_count?: number | string | null
  error_count?: number | string | null
  error_rate_pct?: number | string | null
}

export type ErrorsByProvider = {
  provider: string
  span_count?: number | string | null
  error_count?: number | string | null
  error_rate_pct?: number | string | null
}

export type FailedTrace = {
  trace_id: string
  started_at?: string | null
  error_count?: number | string | null
  error_message?: string | null
}

export type ErrorFingerprint = {
  fingerprint: string
  sample_message: string
  error_count?: number | string | null
  affected_trace_count?: number | string | null
  top_provider?: string | null
  top_model?: string | null
  last_seen_at?: string | null
}

export type FailedTask = {
  id: number
  task_name: string
  project_id?: string | null
  task_args?: Record<string, unknown> | null
  error?: string | null
  attempts?: number | null
  failed_at: string
  resolved: boolean
}

export type AnalyticsResponse = {
  cost_by_model: CostByModel[]
  cost_by_provider: CostByProvider[]
  cost_over_time: CostOverTimePoint[]
  latency_by_model: LatencyByModel[]
  latency_by_provider: LatencyByProvider[]
  top_expensive_traces: AnalyticsTrace[]
  slowest_traces: AnalyticsTrace[]
  error_rate_trend: ErrorRatePoint[]
  top_error_messages: ErrorMessageGroup[]
  errors_by_model: ErrorsByModel[]
  errors_by_provider: ErrorsByProvider[]
  recent_failed_traces: FailedTrace[]
  error_fingerprints: ErrorFingerprint[]
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
  payload_status?: PayloadStorageStatus | null
  payload_drop_reason?: string | null
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

export type ProjectSettings = {
  retention_days: number
  payload_storage_mode: PayloadStorageMode
  payload_max_bytes: number
  payload_redact_keys: string
}

export type ProjectRecord = ProjectSettings & {
  id: string
  name: string
  is_active: boolean
  created_at?: string | null
}

export type AccessibleProjectRecord = ProjectRecord & {
  project_role: UserRole
}

export type ProjectCreate = {
  name: string
}

export type ProjectCreateResponse = ProjectRecord & {
  api_key: string
  note: string
}

export type ProjectSettingsUpdate = Partial<ProjectSettings>

export type ProjectMember = {
  user_id: string
  email: string
  org_role: UserRole
  project_role: ProjectMembershipRole
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
}

export type ProjectMemberAssign = {
  user_id: string
  role: ProjectMembershipRole
}

export type UserProjectAccessRecord = {
  project_id: string
  project_name: string
  project_role: UserRole | null
  is_active: boolean
  retention_days: number
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

export type PricingRecord = {
  id: number
  provider: string
  model: string
  input_cost_per_1k_tokens: string | number
  output_cost_per_1k_tokens: string | number
  valid_from: string
  valid_to?: string | null
}

export type PricingCreate = {
  provider: string
  model: string
  input_cost_per_1k_tokens: string | number
  output_cost_per_1k_tokens: string | number
  valid_from?: string | null
}

export type PricingUpdate = {
  input_cost_per_1k_tokens?: string | number
  output_cost_per_1k_tokens?: string | number
  valid_from?: string | null
  valid_to?: string | null
}

export type OrganizationUser = {
  id: string
  email: string
  role: UserRole
  is_active: boolean
  created_at?: string | null
}

export type OrganizationUserCreate = {
  email: string
  role: UserRole
  project_assignments: Array<{
    project_id: string
    role: ProjectMembershipRole
  }>
}

export type OrganizationInvite = {
  id: string
  email: string
  role: UserRole
  project_assignments: Array<{
    project_id: string
    role: ProjectMembershipRole
  }>
  invite_token: string
  expires_at: string
}

export type InviteAcceptPayload = {
  token: string
  password: string
}

export type AuditLogEvent = {
  id: number
  action: string
  user_id?: string | null
  user_email?: string | null
  resource_id?: string | null
  metadata: Record<string, unknown>
  created_at: string
}

export type AuditLogResponse = {
  events: AuditLogEvent[]
  next_cursor?: string | null
}

export type ProjectApiKey = {
  id: string
  name: string
  description?: string | null
  scope: ApiKeyScope
  is_active: boolean
  created_at?: string | null
  last_used_at?: string | null
  revoked_at?: string | null
}

export type ProjectApiKeyCreate = {
  name: string
  description?: string | null
  scope: ApiKeyScope
}

export type ProjectApiKeyCreateResponse = ProjectApiKey & {
  api_key: string
}

export const dashboardQueryKeys = {
  overview: (projectId: string, period: Period) => ['metrics', 'overview', projectId, period] as const,
  timeseries: (projectId: string, period: Period) => ['metrics', 'timeseries', projectId, period] as const,
  analytics: (projectId: string, period: Period) => ['metrics', 'analytics', projectId, period] as const,
  traces: (projectId: string, period: Period, status: StatusFilter, model: string) =>
    ['traces', projectId, period, status, model] as const,
  traceDetail: (projectId: string, traceId: string | undefined, startedAt: string | null, includePayload: boolean) =>
    ['trace-detail', projectId, traceId, startedAt, includePayload] as const,
  alertRules: (projectId: string) => ['alert-rules', projectId] as const,
  alertEvents: (projectId: string) => ['alert-events', projectId] as const,
  pricing: (provider: string, model: string, includeExpired: boolean) =>
    ['pricing', provider, model, includeExpired] as const,
  users: () => ['users'] as const,
  auditEvents: (action: string, userId: string, fromDt: string, toDt: string, cursor: string) =>
    ['audit-events', action, userId, fromDt, toDt, cursor] as const,
  projectSettings: (projectId: string) => ['project-settings', projectId] as const,
  projectMembers: (projectId: string) => ['project-members', projectId] as const,
  userProjectAccess: (userId: string) => ['user-project-access', userId] as const,
  apiKeys: (projectId: string) => ['api-keys', projectId] as const,
  failedTasks: (projectId: string, includeResolved: boolean) =>
    ['failed-tasks', projectId, includeResolved] as const,
  projects: () => ['projects'] as const,
  accessibleProjects: () => ['accessible-projects'] as const,
}

function projectParams(projectId: string) {
  return new URLSearchParams({ project_id: projectId })
}

export async function registerUser(body: {
  email: string
  password: string
  org_name: string
  bootstrap_token?: string
}) {
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

export async function getMetricsAnalytics(projectId: string, period: Period) {
  const params = projectParams(projectId)
  params.set('period', period)
  const response = await api.get<AnalyticsResponse>(`/v1/metrics/analytics?${params.toString()}`)
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

export async function updateAlertRule(projectId: string, ruleId: string, payload: AlertRuleUpdate) {
  await api.patch(`/v1/alerts/rules/${ruleId}?${projectParams(projectId).toString()}`, payload)
}

export async function deleteAlertRule(projectId: string, ruleId: string) {
  await api.delete(`/v1/alerts/rules/${ruleId}?${projectParams(projectId).toString()}`)
}

export async function listAlertEvents(projectId: string) {
  const response = await api.get<AlertEvent[]>(`/v1/alerts/events?${projectParams(projectId).toString()}`)
  return response.data
}

export async function resolveAlertEvent(projectId: string, eventId: string) {
  await api.post(`/v1/alerts/events/${eventId}/resolve?${projectParams(projectId).toString()}`)
}

export async function getProjectSettings(projectId: string) {
  const response = await api.get<ProjectSettings>(`/v1/projects/${projectId}/settings`)
  return response.data
}

export async function listProjects() {
  const response = await api.get<ProjectRecord[]>('/v1/projects')
  return response.data
}

export async function listAccessibleProjects() {
  const response = await api.get<AccessibleProjectRecord[]>('/v1/projects/accessible')
  return response.data
}

export async function createProject(payload: ProjectCreate) {
  const response = await api.post<ProjectCreateResponse>('/v1/projects', payload)
  return response.data
}

export async function updateProjectSettings(projectId: string, payload: ProjectSettingsUpdate) {
  const response = await api.patch<ProjectSettings>(`/v1/projects/${projectId}/settings`, payload)
  return response.data
}

export async function listProjectMembers(projectId: string) {
  const response = await api.get<ProjectMember[]>(`/v1/projects/${projectId}/members`)
  return response.data
}

export async function listUserProjectAccess(userId: string) {
  const response = await api.get<UserProjectAccessRecord[]>(`/v1/users/${userId}/projects`)
  return response.data
}

export async function assignProjectMember(projectId: string, payload: ProjectMemberAssign) {
  const response = await api.post<ProjectMember>(`/v1/projects/${projectId}/members`, payload)
  return response.data
}

export async function removeProjectMember(projectId: string, userId: string) {
  await api.delete(`/v1/projects/${projectId}/members/${userId}`)
}

export async function rotateProjectApiKey(projectId: string) {
  const response = await api.post<{ api_key: string }>(`/v1/projects/${projectId}/rotate-key`)
  return response.data
}

export async function listProjectApiKeys(projectId: string) {
  const response = await api.get<ProjectApiKey[]>(`/v1/projects/${projectId}/api-keys`)
  return response.data
}

export async function createProjectApiKey(projectId: string, payload: ProjectApiKeyCreate) {
  const response = await api.post<ProjectApiKeyCreateResponse>(`/v1/projects/${projectId}/api-keys`, payload)
  return response.data
}

export async function revokeProjectApiKey(projectId: string, keyId: string) {
  await api.post(`/v1/projects/${projectId}/api-keys/${keyId}/revoke`)
}

export async function listFailedTasks(projectId: string, includeResolved = false) {
  const params = new URLSearchParams({
    project_id: projectId,
    include_resolved: includeResolved ? 'true' : 'false',
    limit: '25',
  })
  const response = await api.get<FailedTask[]>(`/v1/failed-tasks?${params.toString()}`)
  return response.data
}

export async function retryFailedTask(taskId: number) {
  await api.post(`/v1/failed-tasks/${taskId}/retry`)
}

export async function listPricing({
  provider,
  model,
  includeExpired,
}: {
  provider: string
  model: string
  includeExpired: boolean
}) {
  const params = new URLSearchParams()
  if (provider) params.set('provider', provider)
  if (model) params.set('model', model)
  params.set('include_expired', includeExpired ? 'true' : 'false')

  const response = await api.get<PricingRecord[]>(`/v1/pricing?${params.toString()}`)
  return response.data
}

export async function createPricing(payload: PricingCreate) {
  const response = await api.post<PricingRecord>('/v1/pricing', payload)
  return response.data
}

export async function updatePricing(pricingId: number, payload: PricingUpdate) {
  const response = await api.patch<PricingRecord>(`/v1/pricing/${pricingId}`, payload)
  return response.data
}

export async function endPricing(pricingId: number, validTo?: string | null) {
  const response = await api.post<PricingRecord>(`/v1/pricing/${pricingId}/end`, {
    valid_to: validTo ?? null,
  })
  return response.data
}

export async function listUsers() {
  const response = await api.get<OrganizationUser[]>('/v1/users')
  return response.data
}

export async function createOrganizationUser(payload: OrganizationUserCreate) {
  const response = await api.post<OrganizationInvite>('/v1/users/invites', payload)
  return response.data
}

export async function acceptOrganizationInvite(payload: InviteAcceptPayload) {
  const response = await api.post<AuthResponse>('/v1/users/invites/accept', payload)
  return response.data
}

export async function updateOrganizationUserRole(userId: string, role: UserRole) {
  const response = await api.patch<OrganizationUser>(`/v1/users/${userId}/role`, { role })
  return response.data
}

export async function deleteOrganizationUser(userId: string) {
  await api.delete(`/v1/users/${userId}`)
}

export async function listAuditEvents({
  action,
  userId,
  fromDt,
  toDt,
  cursor,
}: {
  action: string
  userId: string
  fromDt: string
  toDt: string
  cursor?: string | null
}) {
  const params = new URLSearchParams()
  params.set('page_size', '50')
  if (action.trim()) params.set('action', action.trim())
  if (userId) params.set('user_id', userId)
  if (fromDt) params.set('from_dt', new Date(fromDt).toISOString())
  if (toDt) params.set('to_dt', new Date(toDt).toISOString())
  if (cursor) params.set('cursor', cursor)

  const response = await api.get<AuditLogResponse>(`/v1/audit/events?${params.toString()}`)
  return response.data
}
