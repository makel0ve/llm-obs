import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import {
  createAlertRule,
  dashboardQueryKeys,
  deleteAlertRule,
  listAlertEvents,
  listAlertRules,
  resolveAlertEvent,
  updateAlertRule,
  type AlertCondition,
  type AlertMetric,
  type AlertRule,
  type AlertRuleCreate,
  type AlertRuleUpdate,
} from '../api/dashboard'

type MutationStatus = 'idle' | 'success' | 'error'

type RuleDraft = {
  name: string
  metric: AlertMetric
  condition: AlertCondition
  threshold: string
  window_minutes: string
  cooldown_minutes: string
  notify_email: string
  notify_slack_webhook: string
}

type RuleEditDraft = {
  threshold: string
  notify_email: string
  notify_slack_webhook: string
}

const metricOptions: Array<{ value: AlertMetric; label: string }> = [
  { value: 'latency_p95', label: 'Latency p95' },
  { value: 'error_rate', label: 'Error rate' },
  { value: 'cost_hourly', label: 'Hourly cost' },
  { value: 'anomaly', label: 'Anomaly' },
]

const conditionOptions: Array<{ value: AlertCondition; label: string }> = [
  { value: 'gt', label: 'Greater than' },
  { value: 'lt', label: 'Less than' },
  { value: 'anomaly', label: 'Anomaly' },
]

const emptyDraft: RuleDraft = {
  name: '',
  metric: 'latency_p95',
  condition: 'gt',
  threshold: '',
  window_minutes: '5',
  cooldown_minutes: '15',
  notify_email: '',
  notify_slack_webhook: '',
}

function formatDate(value?: string | null) {
  if (!value) return '-'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'

  return format(date, 'dd MMM HH:mm:ss')
}

function formatMetric(metric: AlertMetric) {
  return metricOptions.find(option => option.value === metric)?.label ?? metric
}

function formatCondition(condition: AlertCondition) {
  return conditionOptions.find(option => option.value === condition)?.label ?? condition
}

function formatThreshold(rule: Pick<AlertRule, 'condition' | 'threshold'>) {
  if (rule.condition === 'anomaly') return 'automatic'
  if (rule.threshold === null || rule.threshold === undefined || rule.threshold === '') return '-'
  return String(rule.threshold)
}

function AlertMessage({
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

function EmptyState({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6">
      <h2 className="text-lg font-semibold text-gray-950">{title}</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-600">{text}</p>
    </div>
  )
}

function buildEditDraft(rule: AlertRule): RuleEditDraft {
  return {
    threshold: rule.threshold === null || rule.threshold === undefined ? '' : String(rule.threshold),
    notify_email: rule.notify_email ?? '',
    notify_slack_webhook: rule.notify_slack_webhook ?? '',
  }
}

function validateDraft(draft: RuleDraft) {
  if (!draft.name.trim()) return 'Rule name is required.'
  if (!draft.notify_email.trim() && !draft.notify_slack_webhook.trim()) {
    return 'Add an email or Slack webhook target.'
  }

  const windowMinutes = Number(draft.window_minutes)
  const cooldownMinutes = Number(draft.cooldown_minutes)
  if (!Number.isInteger(windowMinutes) || windowMinutes < 1) return 'Window must be at least 1 minute.'
  if (!Number.isInteger(cooldownMinutes) || cooldownMinutes < 1) return 'Cooldown must be at least 1 minute.'

  if (draft.condition !== 'anomaly') {
    const threshold = Number(draft.threshold)
    if (!draft.threshold.trim() || Number.isNaN(threshold)) return 'Threshold must be a number.'
  }

  return ''
}

function buildCreatePayload(projectId: string, draft: RuleDraft): AlertRuleCreate {
  const isAnomaly = draft.metric === 'anomaly' || draft.condition === 'anomaly'

  return {
    project_id: projectId,
    name: draft.name.trim(),
    metric: draft.metric,
    condition: isAnomaly ? 'anomaly' : draft.condition,
    threshold: isAnomaly ? null : Number(draft.threshold),
    window_minutes: Number(draft.window_minutes),
    cooldown_minutes: Number(draft.cooldown_minutes),
    notify_email: draft.notify_email.trim() || null,
    notify_slack_webhook: draft.notify_slack_webhook.trim() || null,
  }
}

function buildPatchPayload(rule: AlertRule, draft: RuleEditDraft): AlertRuleUpdate {
  return {
    threshold: rule.condition === 'anomaly' || !draft.threshold.trim() ? undefined : Number(draft.threshold),
    notify_email: draft.notify_email.trim(),
    notify_slack_webhook: draft.notify_slack_webhook.trim(),
  }
}

export function Alerts({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<RuleDraft>(emptyDraft)
  const [validationError, setValidationError] = useState('')
  const [createStatus, setCreateStatus] = useState<MutationStatus>('idle')
  const [editDrafts, setEditDrafts] = useState<Record<string, RuleEditDraft>>({})

  const rulesQuery = useQuery({
    queryKey: dashboardQueryKeys.alertRules(projectId),
    queryFn: () => listAlertRules(projectId),
    enabled: !!projectId,
  })

  const eventsQuery = useQuery({
    queryKey: dashboardQueryKeys.alertEvents(projectId),
    queryFn: () => listAlertEvents(projectId),
    enabled: !!projectId,
    refetchInterval: 30_000,
  })

  const rules = useMemo(() => rulesQuery.data ?? [], [rulesQuery.data])
  const events = useMemo(() => eventsQuery.data ?? [], [eventsQuery.data])

  const ruleNames = useMemo(
    () => Object.fromEntries(rules.map(rule => [rule.id, rule.name])),
    [rules],
  )

  const invalidateAlerts = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.alertRules(projectId) }),
      queryClient.invalidateQueries({ queryKey: dashboardQueryKeys.alertEvents(projectId) }),
    ])
  }

  const createRule = useMutation({
    mutationFn: createAlertRule,
    onSuccess: async () => {
      setDraft(emptyDraft)
      setValidationError('')
      setCreateStatus('success')
      await invalidateAlerts()
    },
    onError: () => setCreateStatus('error'),
  })

  const patchRule = useMutation({
    mutationFn: ({ ruleId, payload }: { ruleId: string; payload: AlertRuleUpdate }) => updateAlertRule(ruleId, payload),
    onSuccess: invalidateAlerts,
  })

  const deleteRule = useMutation({
    mutationFn: deleteAlertRule,
    onSuccess: invalidateAlerts,
  })

  const resolveEvent = useMutation({
    mutationFn: resolveAlertEvent,
    onSuccess: invalidateAlerts,
  })

  const updateDraft = (patch: Partial<RuleDraft>) => {
    setCreateStatus('idle')
    setValidationError('')
    setDraft(current => {
      const next = { ...current, ...patch }
      if (patch.metric === 'anomaly') {
        next.condition = 'anomaly'
        next.threshold = ''
      }
      if (patch.metric && patch.metric !== 'anomaly' && next.condition === 'anomaly') {
        next.condition = 'gt'
      }
      if (patch.condition === 'anomaly') {
        next.threshold = ''
      }
      return next
    })
  }

  const submitCreateRule = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const error = validateDraft(draft)
    if (error) {
      setValidationError(error)
      setCreateStatus('idle')
      return
    }
    createRule.mutate(buildCreatePayload(projectId, draft))
  }

  const getEditDraft = (rule: AlertRule) => editDrafts[rule.id] ?? buildEditDraft(rule)

  const updateEditDraft = (rule: AlertRule, patch: Partial<RuleEditDraft>) => {
    setEditDrafts(current => ({
      ...current,
      [rule.id]: {
        ...getEditDraft(rule),
        ...patch,
      },
    }))
  }

  const saveRuleTargets = (rule: AlertRule) => {
    const current = getEditDraft(rule)
    const payload = buildPatchPayload(rule, current)

    if (
      payload.threshold !== undefined &&
      (typeof payload.threshold !== 'number' || Number.isNaN(payload.threshold))
    ) {
      return
    }

    patchRule.mutate({ ruleId: rule.id, payload })
  }

  const toggleRule = (rule: AlertRule) => {
    patchRule.mutate({ ruleId: rule.id, payload: { is_active: !rule.is_active } })
  }

  if (!projectId) {
    return (
      <div className="p-4 sm:p-6 lg:p-8">
        <AlertMessage tone="warning">No active project is selected. Sign in again to open alerts.</AlertMessage>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-950">Alerts</h1>
        <p className="mt-1 text-sm text-gray-500">Create alert rules, route notifications and resolve triggered events.</p>
      </div>

      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <h2 className="text-lg font-semibold text-gray-950">New rule</h2>
        <form onSubmit={submitCreateRule} className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-4">
          <label className="block xl:col-span-2">
            <span className="text-sm font-medium text-gray-700">Name</span>
            <input
              value={draft.name}
              onChange={event => updateDraft({ name: event.target.value })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              placeholder="Production latency"
              maxLength={255}
              required
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Metric</span>
            <select
              value={draft.metric}
              onChange={event => updateDraft({ metric: event.target.value as AlertMetric })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
            >
              {metricOptions.map(option => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Condition</span>
            <select
              value={draft.condition}
              onChange={event => updateDraft({ condition: event.target.value as AlertCondition })}
              disabled={draft.metric === 'anomaly'}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900 disabled:bg-gray-100 disabled:text-gray-500"
            >
              {conditionOptions
                .filter(option => draft.metric === 'anomaly' || option.value !== 'anomaly')
                .map(option => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Threshold</span>
            <input
              type="number"
              step="0.0001"
              value={draft.threshold}
              onChange={event => updateDraft({ threshold: event.target.value })}
              disabled={draft.condition === 'anomaly'}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900 disabled:bg-gray-100 disabled:text-gray-500"
              placeholder={draft.condition === 'anomaly' ? 'automatic' : '500'}
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Window minutes</span>
            <input
              type="number"
              min={1}
              value={draft.window_minutes}
              onChange={event => updateDraft({ window_minutes: event.target.value })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              required
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Cooldown minutes</span>
            <input
              type="number"
              min={1}
              value={draft.cooldown_minutes}
              onChange={event => updateDraft({ cooldown_minutes: event.target.value })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              required
            />
          </label>
          <label className="block xl:col-span-2">
            <span className="text-sm font-medium text-gray-700">Email target</span>
            <input
              type="email"
              value={draft.notify_email}
              onChange={event => updateDraft({ notify_email: event.target.value })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              placeholder="alerts@example.com"
              maxLength={255}
            />
          </label>
          <label className="block xl:col-span-2">
            <span className="text-sm font-medium text-gray-700">Slack webhook</span>
            <input
              type="url"
              value={draft.notify_slack_webhook}
              onChange={event => updateDraft({ notify_slack_webhook: event.target.value })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              placeholder="https://hooks.slack.com/services/..."
              maxLength={500}
            />
          </label>
          <div className="flex flex-col gap-3 xl:col-span-4">
            <button
              type="submit"
              disabled={createRule.isPending}
              className="min-h-10 w-full rounded-md bg-gray-900 px-4 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-fit"
            >
              {createRule.isPending ? 'Creating...' : 'Create rule'}
            </button>
            {validationError && <AlertMessage tone="error">{validationError}</AlertMessage>}
            {createStatus === 'success' && <AlertMessage tone="success">Alert rule created.</AlertMessage>}
            {createStatus === 'error' && <AlertMessage tone="error">Could not create alert rule.</AlertMessage>}
          </div>
        </form>
      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg font-semibold text-gray-950">Rules</h2>
          {rulesQuery.isFetching && <span className="text-sm text-gray-500">Refreshing...</span>}
        </div>
        {rulesQuery.isLoading && <EmptyState title="Loading alert rules" text="Rules will appear here after the request completes." />}
        {rulesQuery.isError && <AlertMessage tone="error">Could not load alert rules.</AlertMessage>}
        {!rulesQuery.isLoading && !rulesQuery.isError && rules.length === 0 && (
          <EmptyState title="No alert rules" text="Create a rule above to start monitoring latency, error rate, cost or anomaly signals." />
        )}
        {rules.length > 0 && (
          <div className="space-y-3">
            {rules.map(rule => {
              const current = getEditDraft(rule)
              const isSaving = patchRule.isPending
              return (
                <article key={rule.id} className="rounded-lg border border-gray-200 bg-white p-4">
                  <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-semibold text-gray-950">{rule.name}</h3>
                        <span
                          className={`inline-flex min-h-6 items-center rounded-md px-2 text-xs font-medium ${
                            rule.is_active
                              ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
                              : 'bg-gray-100 text-gray-600 ring-1 ring-gray-200'
                          }`}
                        >
                          {rule.is_active ? 'active' : 'inactive'}
                        </span>
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-3 text-sm text-gray-600 sm:grid-cols-4 xl:grid-cols-6">
                        <div>
                          <div className="text-xs text-gray-500">Metric</div>
                          <div className="font-medium text-gray-900">{formatMetric(rule.metric)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-500">Condition</div>
                          <div className="font-medium text-gray-900">{formatCondition(rule.condition)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-500">Threshold</div>
                          <div className="font-medium text-gray-900">{formatThreshold(rule)}</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-500">Window</div>
                          <div className="font-medium text-gray-900">{rule.window_minutes}m</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-500">Cooldown</div>
                          <div className="font-medium text-gray-900">{rule.cooldown_minutes}m</div>
                        </div>
                        <div>
                          <div className="text-xs text-gray-500">Created</div>
                          <div className="font-medium text-gray-900">{formatDate(rule.created_at)}</div>
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => toggleRule(rule)}
                        disabled={isSaving}
                        className="min-h-9 rounded-md border border-gray-200 bg-white px-3 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {rule.is_active ? 'Disable' : 'Enable'}
                      </button>
                      <button
                        type="button"
                        onClick={() => deleteRule.mutate(rule.id)}
                        disabled={deleteRule.isPending}
                        className="min-h-9 rounded-md border border-red-200 bg-white px-3 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(120px,180px)_1fr_1fr_auto]">
                    <label className="block">
                      <span className="text-sm font-medium text-gray-700">Threshold</span>
                      <input
                        type="number"
                        step="0.0001"
                        value={current.threshold}
                        onChange={event => updateEditDraft(rule, { threshold: event.target.value })}
                        disabled={rule.condition === 'anomaly'}
                        className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900 disabled:bg-gray-100 disabled:text-gray-500"
                      />
                    </label>
                    <label className="block">
                      <span className="text-sm font-medium text-gray-700">Email target</span>
                      <input
                        type="email"
                        value={current.notify_email}
                        onChange={event => updateEditDraft(rule, { notify_email: event.target.value })}
                        className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
                      />
                    </label>
                    <label className="block">
                      <span className="text-sm font-medium text-gray-700">Slack webhook</span>
                      <input
                        type="url"
                        value={current.notify_slack_webhook}
                        onChange={event => updateEditDraft(rule, { notify_slack_webhook: event.target.value })}
                        className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
                      />
                    </label>
                    <div className="flex items-end">
                      <button
                        type="button"
                        onClick={() => saveRuleTargets(rule)}
                        disabled={patchRule.isPending}
                        className="min-h-10 w-full rounded-md bg-gray-900 px-4 text-sm font-medium text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60 xl:w-auto"
                      >
                        Save
                      </button>
                    </div>
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg font-semibold text-gray-950">Events</h2>
          {eventsQuery.isFetching && <span className="text-sm text-gray-500">Refreshing...</span>}
        </div>
        {eventsQuery.isLoading && <EmptyState title="Loading alert events" text="Triggered alerts will appear here after the request completes." />}
        {eventsQuery.isError && <AlertMessage tone="error">Could not load alert events.</AlertMessage>}
        {!eventsQuery.isLoading && !eventsQuery.isError && events.length === 0 && (
          <EmptyState title="No alert events" text="Open events will appear when active rules are triggered by incoming spans." />
        )}
        {events.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <div className="overflow-x-auto">
              <table className="min-w-[820px] w-full text-left text-sm">
                <thead className="border-b border-gray-200 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <tr>
                    <th scope="col" className="px-4 py-3 font-medium">Triggered</th>
                    <th scope="col" className="px-4 py-3 font-medium">Rule</th>
                    <th scope="col" className="px-4 py-3 text-right font-medium">Value</th>
                    <th scope="col" className="px-4 py-3 font-medium">Message</th>
                    <th scope="col" className="px-4 py-3 font-medium">Status</th>
                    <th scope="col" className="px-4 py-3 font-medium">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {events.map(event => (
                    <tr key={event.id} className="align-top hover:bg-gray-50">
                      <td className="whitespace-nowrap px-4 py-3 text-gray-900">{formatDate(event.triggered_at)}</td>
                      <td className="px-4 py-3 text-gray-700">{ruleNames[event.rule_id] ?? event.rule_id.slice(0, 8)}</td>
                      <td className="px-4 py-3 text-right tabular-nums text-gray-700">{String(event.value)}</td>
                      <td className="max-w-xl px-4 py-3 text-gray-700">{event.message}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex min-h-6 items-center rounded-md px-2 text-xs font-medium ${
                            event.resolved_at
                              ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200'
                              : 'bg-red-50 text-red-700 ring-1 ring-red-200'
                          }`}
                        >
                          {event.resolved_at ? 'resolved' : 'open'}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        {!event.resolved_at && (
                          <button
                            type="button"
                            onClick={() => resolveEvent.mutate(event.id)}
                            disabled={resolveEvent.isPending}
                            className="min-h-9 rounded-md border border-gray-200 bg-white px-3 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            Resolve
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
