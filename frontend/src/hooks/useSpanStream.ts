import { useEffect, useCallback, useRef } from "react";

export function useSpanStream(
  onSpan: (span: unknown) => void
) {
  const onSpanRef = useRef(onSpan);
  useEffect(() => { onSpanRef.current = onSpan }, [onSpan]);

  const connect = useCallback(() => {
    const controller = new AbortController();
    const url = `${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/v1/stream/spans`;
    const token = localStorage.getItem('token');

    fetch(url, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'text/event-stream',
      },
      signal: controller.signal,
    }).then(async res => {
      if (!res.ok || !res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              onSpanRef.current(JSON.parse(line.slice(6)));
            } catch {}
          }
        }
      }
    }).catch(() => {
      if (!controller.signal.aborted) {
        setTimeout(connect, 3000);
      }
    });

    return controller;
  }, []);

  useEffect(() => {
    const controller = connect();
    return () => controller.abort();
  }, [connect]);
}
