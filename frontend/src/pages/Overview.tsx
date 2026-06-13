import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { format } from "date-fns";
import { api } from "../api/client";


type Period = "1h" | "24h" | "7d" | "30d"


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
    <div className="bg-white rounded-xl border p-4">
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

    const { data: metrics, isLoading } = useQuery({
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

    return (
        <div className="p-6 space-y-6">
            <div className="flex gap-2">
                {(["1h", "24h", "7d", "30d"] as Period[]).map(p => (
                    <button key={p} onClick={() => setPeriod(p)}
                    className={`px-3 py-1 rounded text-sm font-medium ${
                    period === p
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}>
                        {p}
                    </button>
                ))}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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

            <div className="bg-white rounded-xl border p-4">
                <h3 className="text-sm font-medium text-gray-500 mb-4">Avg Latency (ms)</h3>
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
        </div>
    );
}
