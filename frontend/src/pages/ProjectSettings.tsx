import { useState, type FormEvent, type ReactNode } from 'react'
import { api } from '../api/client'

type CopyState = 'idle' | 'copied' | 'failed'

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

export function ProjectSettings({ projectId }: { projectId: string }) {
  const [retentionDays, setRetentionDays] = useState('90')
  const [savedRetentionDays, setSavedRetentionDays] = useState<number | null>(null)
  const [settingsStatus, setSettingsStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [rotateStatus, setRotateStatus] = useState<'idle' | 'rotating' | 'success' | 'error'>('idle')
  const [newApiKey, setNewApiKey] = useState('')

  const endpoint = api.defaults.baseURL ?? 'http://localhost:8000'
  const envVars = `LLM_OBS_API_KEY=llmobs_your_key_here\nLLM_OBS_ENDPOINT=${endpoint}`
  const basicExample = `import llm_obs

@llm_obs.trace(name="demo.llm_call")
async def call_llm(prompt: str) -> str:
    return "demo response"

await call_llm("Hello")
await llm_obs.shutdown()`

  const updateRetention = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSettingsStatus('saving')

    try {
      const days = Number(retentionDays)
      const response = await api.patch<{ retention_days: number }>(
        `/v1/projects/${projectId}/settings`,
        { retention_days: days },
      )
      setSavedRetentionDays(response.data.retention_days)
      setSettingsStatus('success')
    } catch {
      setSettingsStatus('error')
    }
  }

  const rotateApiKey = async () => {
    setRotateStatus('rotating')
    setNewApiKey('')

    try {
      const response = await api.post<{ api_key: string }>(`/v1/projects/${projectId}/rotate-key`)
      setNewApiKey(response.data.api_key)
      setRotateStatus('success')
    } catch {
      setRotateStatus('error')
    }
  }

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
                value={retentionDays}
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
          <h2 className="text-lg font-semibold text-gray-950">API key</h2>
          <p className="mt-1 text-sm text-gray-500">Rotate the project ingest key if it was lost or exposed.</p>
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
    </div>
  )
}
