import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { format } from "date-fns";
import { api } from "../api/client";
import { OnboardingSetup } from "../components/OnboardingSetup";


type Period = "1h" | "24h" | "7d" | "30d"

type OverviewMetrics = {
    total_spans?: number | string | null
    p95_latency_ms?: number | string | null
    error_rate_pct?: number | string | null
    total_cost_usd?: number | string | null
}


function MetricCard({
  label,
  value,
  loading,
  variant = 'default'
}: {
  label: string
  value?: string
  loading?: boolean
  variant?: 'default' | 'danger'
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="text-sm text-gray-500 mb-1">{label}</div>
      {loading ? (
        <div className="h-7 bg-gray-100 rounded animate-pulse w-24" />
      ) : (
        <div className={`text-2xl font-semibold ${variant === 'danger' ? 'text-red-500' : 'text-gray-900'}`}>
          {value ?? '—'}
        </div>
      )}
    </div>
  )
}


export function Overview({ projectId }: { projectId: string }) {
    const [period, setPeriod] = useState<Period>("24h");

    const { data: metrics, isLoading, isError } = useQuery<OverviewMetrics>({
        queryKey: ["metrics", "overview", period, projectId],
        queryFn: () => api.get(`/v1/metrics/overview?period=${period}&project_id=${projectId}`).then(r => r.data),
        refetchInterval: 30_000,
        staleTime: 15_000,
        enabled: !!projectId,
    });

    const { data: timeseries } = useQuery({
        queryKey: ["metrics", "timeseries", period, projectId],
        queryFn: () => api.get(`/v1/metrics/timeseries?period=${period}&project_id=${projectId}`).then(r => r.data),
        refetchInterval: 60_000,
        enabled: !!projectId,
    });

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
                    {(["1h", "24h", "7d", "30d"] as Period[]).map(p => (
                        <button key={p} onClick={() => setPeriod(p)}
                        className={`min-h-9 min-w-14 rounded-md px-3 text-sm font-medium ${
                        period === p
                            ? 'bg-blue-600 text-white'
                            : 'border border-gray-200 bg-white text-gray-700 hover:bg-gray-100'
                        }`}>
                            {p}
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

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard label="Spans" value={metrics?.total_spans?.toLocaleString()} loading={isLoading}/>
                <MetricCard label="P95 Latency" value={`${Number(metrics?.p95_latency_ms ?? 0).toFixed(0)}ms`} loading={isLoading}/>
                <MetricCard
                label="Error Rate"
                value={`${Number(metrics?.error_rate_pct ?? 0).toFixed(2)}%`}
                variant={Number(metrics?.error_rate_pct ?? 0) > 5 ? 'danger' : 'default'}
                loading={isLoading}
                />
                <MetricCard label="Total Cost" value={`$${Number(metrics?.total_cost_usd ?? 0).toFixed(4)}`} loading={isLoading}/>
            </div>

            {hasNoSpans ? (
                <OnboardingSetup title="No spans yet" />
            ) : (
                <div className="rounded-lg border border-gray-200 bg-white p-4">
                    <h2 className="mb-4 text-sm font-medium text-gray-500">Avg Latency (ms)</h2>
                    <ResponsiveContainer width="100%" height={200}>
                        <LineChart data={timeseries ?? []}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#f5f5f5" />
                            <XAxis dataKey="bucket" tickFormatter={t => format(new Date(t), "HH:mm")} />
                            <YAxis />
                            <Tooltip labelFormatter={t => format(new Date(t), "dd MMM HH:mm")} />
                            <Line type="monotone" dataKey="avg_latency" stroke="#3b82f6" dot={false} strokeWidth={2} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            )}
        </div>
    );
}
