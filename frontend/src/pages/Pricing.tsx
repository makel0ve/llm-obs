import { useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { getApiErrorMessage } from '../api/errors'
import {
  createPricing,
  dashboardQueryKeys,
  endPricing,
  listPricing,
  updatePricing,
  type PricingRecord,
} from '../api/dashboard'

type PricingDraft = {
  provider: string
  model: string
  input_cost_per_1k_tokens: string
  output_cost_per_1k_tokens: string
  valid_from: string
}

type EditDraft = {
  input_cost_per_1k_tokens: string
  output_cost_per_1k_tokens: string
  valid_from: string
  valid_to: string
}

const emptyDraft: PricingDraft = {
  provider: 'openai',
  model: '',
  input_cost_per_1k_tokens: '',
  output_cost_per_1k_tokens: '',
  valid_from: '',
}

function formatLocalDateTime(value?: string | null, emptyValue = 'Open') {
  if (!value) return emptyValue
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return emptyValue
  return format(date, 'dd MMM yyyy HH:mm')
}

function numberValue(value: string) {
  const parsed = Number(value.replace(',', '.'))
  return Number.isFinite(parsed) ? parsed : null
}

function formatDecimal(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return ''

  const raw = String(value).trim()
  const parsed = Number(raw.replace(',', '.'))
  if (!Number.isFinite(parsed)) return raw

  const fixed = parsed.toFixed(10)
  return fixed.replace(/\.?0+$/, '') || '0'
}

function validateDraft(draft: PricingDraft) {
  if (!draft.provider.trim()) return 'Provider is required.'
  if (!draft.model.trim()) return 'Model is required.'
  if (numberValue(draft.input_cost_per_1k_tokens) === null) return 'Input cost must be a number.'
  if (numberValue(draft.output_cost_per_1k_tokens) === null) return 'Output cost must be a number.'
  if (
    Number(draft.input_cost_per_1k_tokens.replace(',', '.')) < 0 ||
    Number(draft.output_cost_per_1k_tokens.replace(',', '.')) < 0
  ) {
    return 'Costs cannot be negative.'
  }
  return ''
}

function buildEditDraft(record: PricingRecord): EditDraft {
  return {
    input_cost_per_1k_tokens: formatDecimal(record.input_cost_per_1k_tokens),
    output_cost_per_1k_tokens: formatDecimal(record.output_cost_per_1k_tokens),
    valid_from: formatUtcInput(record.valid_from),
    valid_to: formatUtcInput(record.valid_to),
  }
}

function formatUtcInput(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  const year = date.getUTCFullYear()
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  const hours = String(date.getUTCHours()).padStart(2, '0')
  const minutes = String(date.getUTCMinutes()).padStart(2, '0')

  return `${year}-${month}-${day}T${hours}:${minutes}`
}

function utcInputToIso(value: string) {
  if (!value) return null
  const parsed = new Date(`${value}:00.000Z`)
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString()
}

function Notice({
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

  return <div className={`rounded-md border p-3 text-sm ${classes}`}>{children}</div>
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed border-gray-300 bg-white p-6">
      <h2 className="text-lg font-semibold text-gray-950">No pricing records</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-gray-600">
        Add model prices to enable cost calculation for incoming spans.
      </p>
    </div>
  )
}

export function Pricing() {
  const queryClient = useQueryClient()
  const [providerFilter, setProviderFilter] = useState('')
  const [modelFilter, setModelFilter] = useState('')
  const [includeExpired, setIncludeExpired] = useState(true)
  const [draft, setDraft] = useState<PricingDraft>(emptyDraft)
  const [editDrafts, setEditDrafts] = useState<Record<number, EditDraft>>({})
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null)

  const pricingQuery = useQuery({
    queryKey: dashboardQueryKeys.pricing(providerFilter, modelFilter, includeExpired),
    queryFn: () => listPricing({ provider: providerFilter, model: modelFilter, includeExpired }),
  })

  const records = useMemo(() => pricingQuery.data ?? [], [pricingQuery.data])

  const refreshPricing = async () => {
    await queryClient.invalidateQueries({ queryKey: ['pricing'] })
  }

  const createMutation = useMutation({
    mutationFn: createPricing,
    onSuccess: async () => {
      setDraft(emptyDraft)
      setMessage({ tone: 'success', text: 'Pricing record created.' })
      await refreshPricing()
    },
    onError: () => setMessage({ tone: 'error', text: 'Could not create pricing record.' }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Parameters<typeof updatePricing>[1] }) =>
      updatePricing(id, payload),
    onSuccess: async () => {
      setMessage({ tone: 'success', text: 'Pricing record updated.' })
      await refreshPricing()
    },
    onError: () => setMessage({ tone: 'error', text: 'Could not update pricing record.' }),
  })

  const endMutation = useMutation({
    mutationFn: ({ id, validTo }: { id: number; validTo?: string | null }) => endPricing(id, validTo),
    onSuccess: async () => {
      setMessage({ tone: 'success', text: 'Pricing record ended.' })
      await refreshPricing()
    },
    onError: () => setMessage({ tone: 'error', text: 'Could not end pricing record.' }),
  })

  const handleCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const error = validateDraft(draft)
    if (error) {
      setMessage({ tone: 'error', text: error })
      return
    }

    createMutation.mutate({
      provider: draft.provider.trim().toLowerCase(),
      model: draft.model.trim(),
      input_cost_per_1k_tokens: formatDecimal(draft.input_cost_per_1k_tokens),
      output_cost_per_1k_tokens: formatDecimal(draft.output_cost_per_1k_tokens),
      valid_from: utcInputToIso(draft.valid_from),
    })
  }

  const setEditDraft = (record: PricingRecord, patch: Partial<EditDraft>) => {
    setEditDrafts(current => ({
      ...current,
      [record.id]: {
        ...(current[record.id] ?? buildEditDraft(record)),
        ...patch,
      },
    }))
  }

  const handleUpdate = (record: PricingRecord) => {
    const edit = editDrafts[record.id] ?? buildEditDraft(record)
    const inputCost = numberValue(edit.input_cost_per_1k_tokens)
    const outputCost = numberValue(edit.output_cost_per_1k_tokens)
    if (inputCost === null || outputCost === null || inputCost < 0 || outputCost < 0) {
      setMessage({ tone: 'error', text: 'Costs must be non-negative numbers.' })
      return
    }
    if (!edit.valid_from) {
      setMessage({ tone: 'error', text: 'Valid from is required.' })
      return
    }
    const validFrom = utcInputToIso(edit.valid_from)
    if (!validFrom) {
      setMessage({ tone: 'error', text: 'Valid from must be a valid UTC date.' })
      return
    }

    updateMutation.mutate({
      id: record.id,
      payload: {
        input_cost_per_1k_tokens: formatDecimal(edit.input_cost_per_1k_tokens),
        output_cost_per_1k_tokens: formatDecimal(edit.output_cost_per_1k_tokens),
        valid_from: validFrom,
        valid_to: utcInputToIso(edit.valid_to),
      },
    })
  }

  return (
    <div className="space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold text-gray-950">Pricing</h1>
        <p className="mt-1 text-sm text-gray-500">Manage global model prices used for cost calculation.</p>
      </div>

      {message && <Notice tone={message.tone}>{message.text}</Notice>}

      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <h2 className="text-lg font-semibold text-gray-950">New pricing record</h2>
        <form onSubmit={handleCreate} className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-6">
          <label className="block xl:col-span-1">
            <span className="text-sm font-medium text-gray-700">Provider</span>
            <input
              value={draft.provider}
              onChange={event => setDraft({ ...draft, provider: event.target.value })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              required
            />
          </label>
          <label className="block xl:col-span-2">
            <span className="text-sm font-medium text-gray-700">Model</span>
            <input
              value={draft.model}
              onChange={event => setDraft({ ...draft, model: event.target.value })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              required
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Input / 1K</span>
            <input
              type="text"
              inputMode="decimal"
              value={draft.input_cost_per_1k_tokens}
              onChange={event => setDraft({ ...draft, input_cost_per_1k_tokens: event.target.value })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              required
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Output / 1K</span>
            <input
              type="text"
              inputMode="decimal"
              value={draft.output_cost_per_1k_tokens}
              onChange={event => setDraft({ ...draft, output_cost_per_1k_tokens: event.target.value })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              required
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-700">Valid from</span>
            <input
              type="datetime-local"
              value={draft.valid_from}
              onChange={event => setDraft({ ...draft, valid_from: event.target.value })}
              className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
            />
            <span className="mt-1 block min-h-4 text-xs text-gray-500">
              {formatLocalDateTime(utcInputToIso(draft.valid_from), '')}
            </span>
          </label>
          <div className="xl:col-span-6">
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="min-h-10 rounded-md bg-gray-900 px-4 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-60"
            >
              {createMutation.isPending ? 'Creating...' : 'Create pricing'}
            </button>
          </div>
        </form>
      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-950">Records</h2>
            <p className="mt-1 text-sm text-gray-500">Historical prices are ordered by provider, model and validity.</p>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,12rem)_minmax(0,16rem)_auto] sm:items-end">
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Provider</span>
              <input
                value={providerFilter}
                onChange={event => setProviderFilter(event.target.value)}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-gray-700">Model</span>
              <input
                value={modelFilter}
                onChange={event => setModelFilter(event.target.value)}
                className="mt-2 min-h-10 w-full rounded-md border border-gray-300 bg-white px-3 text-sm text-gray-900"
              />
            </label>
            <label className="flex min-h-10 items-center gap-2 text-sm font-medium text-gray-700">
              <input
                type="checkbox"
                checked={includeExpired}
                onChange={event => setIncludeExpired(event.target.checked)}
                className="h-4 w-4 rounded border-gray-300"
              />
              Expired
            </label>
          </div>
        </div>

        {pricingQuery.isLoading ? (
          <div className="h-32 animate-pulse rounded-lg bg-gray-100" />
        ) : pricingQuery.isError ? (
          <Notice tone="error">{getApiErrorMessage(pricingQuery.error, 'Could not load pricing records.')}</Notice>
        ) : records.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                <tr>
                  <th className="px-4 py-3">Provider</th>
                  <th className="px-4 py-3">Model</th>
                  <th className="px-4 py-3">Input / 1K</th>
                  <th className="px-4 py-3">Output / 1K</th>
                  <th className="px-4 py-3">Valid from</th>
                  <th className="px-4 py-3">Valid to</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {records.map(record => {
                  const edit = editDrafts[record.id] ?? buildEditDraft(record)
                  return (
                    <tr key={record.id} className="align-top">
                      <td className="px-4 py-3 font-medium text-gray-950">{record.provider}</td>
                      <td className="px-4 py-3 text-gray-700">{record.model}</td>
                      <td className="px-4 py-3">
                        <input
                          type="text"
                          inputMode="decimal"
                          value={edit.input_cost_per_1k_tokens}
                          onChange={event => setEditDraft(record, { input_cost_per_1k_tokens: event.target.value })}
                          className="min-h-9 w-32 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="text"
                          inputMode="decimal"
                          value={edit.output_cost_per_1k_tokens}
                          onChange={event => setEditDraft(record, { output_cost_per_1k_tokens: event.target.value })}
                          className="min-h-9 w-32 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="datetime-local"
                          value={edit.valid_from}
                          onChange={event => setEditDraft(record, { valid_from: event.target.value })}
                          className="min-h-9 w-56 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900"
                          aria-label={`Valid from for ${record.provider} ${record.model}`}
                        />
                        <div className="mt-1 whitespace-nowrap text-xs text-gray-500">
                          {formatLocalDateTime(utcInputToIso(edit.valid_from), '-')}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="datetime-local"
                          value={edit.valid_to}
                          onChange={event => setEditDraft(record, { valid_to: event.target.value })}
                          className="min-h-9 w-56 rounded-md border border-gray-300 bg-white px-2 text-sm text-gray-900"
                          aria-label={`Valid to for ${record.provider} ${record.model}`}
                        />
                        <div className="mt-1 whitespace-nowrap text-xs text-gray-500">
                          {formatLocalDateTime(utcInputToIso(edit.valid_to), 'Open')}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => handleUpdate(record)}
                            disabled={updateMutation.isPending}
                            className="min-h-9 rounded-md bg-gray-900 px-3 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-60"
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            onClick={() => endMutation.mutate({ id: record.id })}
                            disabled={endMutation.isPending || !!record.valid_to}
                            className="min-h-9 rounded-md border border-red-200 bg-white px-3 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                          >
                            End now
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
