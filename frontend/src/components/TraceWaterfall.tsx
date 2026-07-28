import { useState } from "react";


interface Span {
    id: string;
    name: string;
    latency_ms: number;
    started_at: string;
    status: "ok" | "error";
    model: string;
    provider: string;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
}

export function TraceWaterfall({ spans }: { spans: Span[] }) {
    const [selected, setSelected] = useState<Span | null>(null);

    if (!spans.length) return <div className="text-gray-500 text-sm">No spans</div>;

    const sorted = [...spans].sort((a, b) =>
        new Date(a.started_at).getTime() - new Date(b.started_at).getTime()
    );
    const t0 = new Date(sorted[0]?.started_at).getTime();
    const tEnd = Math.max(...sorted.map(s => new Date(s.started_at).getTime() + s.latency_ms));
    const duration = tEnd - t0 || 1;

    return (
        <div className="flex gap-4">
            <div className="flex-1 font-mono text-xs space-y-0.5">
                {sorted.map(span => {
                    const offset =((new Date(span.started_at).getTime() - t0) / duration) * 100;
                    const width = Math.max((span.latency_ms / duration) * 100, 0.3);
                    const isErr = span.status === "error";

                    return (
                        <button key={span.id}
                            type="button"
                            className="flex w-full items-center gap-2 rounded px-2 py-1 text-left hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-100"
                            aria-label={`${selected?.id === span.id ? 'Collapse' : 'Expand'} span ${span.name}`}
                            aria-pressed={selected?.id === span.id}
                            onClick={() => setSelected(s => s?.id === span.id ? null : span)}>
                            <div className="w-44 truncate text-gray-700">{span.name}</div>
                            <div className="flex-1 relative h-4 bg-gray-100 rounded overflow-hidden">
                                <div className={`absolute h-full rounded ${isErr ? 'bg-red-400' : 'bg-blue-400'}`}
                                style={{ left: `${offset}%`, width: `${width}%`}} />
                            </div>
                            <div className="w-14 text-right text-gray-500">{span.latency_ms.toFixed(0)}ms</div>
                            {isErr && <span className="text-red-500 font-bold" aria-label="error">!</span>}
                        </button>
                    );
                })}
            </div>

            {selected && (
                <div className="w-60 border-l pl-4 text-sm space-y-1.5">
                    <p className="font-semibold text-gray-800">{selected.name}</p>
                    <p className="text-gray-500">Model: <span className="font-mono text-gray-700">{selected.model}</span></p>
                    <p className="text-gray-500">Tokens: {selected.input_tokens} → {selected.output_tokens}</p>
                    <p className="text-gray-500">Cost: <span className="text-gray-700">${selected.cost_usd.toFixed(6)}</span></p>
                    <p className="text-gray-500">Latency: <span className="text-gray-700">{selected.latency_ms.toFixed(0)}ms</span></p>
                    {selected.status === "error" && (
                        <p className="text-red-600 font-medium">⚠ Error</p>
                    )}
                </div>
            )}
        </div>
    );
}
