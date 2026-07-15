import { Link } from 'react-router-dom'
import { api } from '../api/client'

function CodeBlock({ children }: { children: string }) {
  return (
    <code className="block overflow-x-auto whitespace-pre rounded-md bg-gray-950 p-3 text-sm leading-6 text-gray-100">
      {children}
    </code>
  )
}

export function OnboardingSetup({ title = 'Send your first spans' }: { title?: string }) {
  const endpoint = api.defaults.baseURL ?? 'http://localhost:8000'
  const envVars = `LLM_OBS_API_KEY=llmobs_your_key_here\nLLM_OBS_ENDPOINT=${endpoint}`
  const traceExample = `import llm_obs

@llm_obs.trace(name="demo.llm_call")
async def call_llm(prompt: str) -> str:
    return "demo response"

await call_llm("Hello")
await llm_obs.shutdown()`
  const openAiExample = `import openai
from llm_obs.integrations.openai import patch_openai

client = openai.AsyncOpenAI(api_key="...")
client = patch_openai(client)`

  return (
    <section className="rounded-lg border border-dashed border-gray-300 bg-white p-6">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-950">{title}</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-gray-600">
            Install the SDK, set the project environment variables, then run one traced call.
            The API key is shown once after registration or after rotation in Project Settings.
          </p>
        </div>
        <Link
          to="/dashboard/project-settings"
          className="inline-flex min-h-10 items-center justify-center rounded-md border border-gray-200 bg-white px-4 text-sm font-medium text-gray-700 hover:bg-gray-100"
        >
          Project Settings
        </Link>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-3">
        <div>
          <div className="mb-2 text-sm font-medium text-gray-700">1. Install and configure</div>
          <CodeBlock>{`pip install llm-obs-sdk\n${envVars}`}</CodeBlock>
        </div>
        <div>
          <div className="mb-2 text-sm font-medium text-gray-700">2. Decorate a call</div>
          <CodeBlock>{traceExample}</CodeBlock>
        </div>
        <div>
          <div className="mb-2 text-sm font-medium text-gray-700">3. Patch OpenAI client</div>
          <CodeBlock>{openAiExample}</CodeBlock>
        </div>
      </div>
    </section>
  )
}
