import { useEffect, useRef } from "react";

const INITIAL_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30000;

export function useSpanStream(
  projectId: string,
  onSpan: (span: unknown) => void
) {
  const onSpanRef = useRef(onSpan);
  useEffect(() => { onSpanRef.current = onSpan }, [onSpan]);

  useEffect(() => {
    let stopped = false;
    let controller: AbortController | null = null;
    let retryTimeout: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempt = 0;

    function scheduleReconnect() {
      if (stopped || retryTimeout) {
        return;
      }

      const delay = Math.min(
        INITIAL_RECONNECT_DELAY_MS * 2 ** reconnectAttempt,
        MAX_RECONNECT_DELAY_MS,
      );
      reconnectAttempt += 1;
      retryTimeout = setTimeout(() => {
        retryTimeout = null;
        connect();
      }, delay);
    }

    function connect() {
      if (stopped) {
        return;
      }

      controller = new AbortController();
      const baseUrl = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
      const url = `${baseUrl}/v1/stream/spans?project_id=${encodeURIComponent(projectId)}`;
      const token = localStorage.getItem('token');

      if (!projectId || !token) {
        return;
      }

      fetch(url, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Accept': 'text/event-stream',
        },
        signal: controller.signal,
      }).then(async res => {
        if (!res.ok || !res.body) {
          scheduleReconnect();
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let receivedData = false;

        try {
          while (!stopped) {
            const { done, value } = await reader.read();
            if (done) {
              break;
            }

            receivedData = true;
            reconnectAttempt = 0;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() ?? '';
            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  onSpanRef.current(JSON.parse(line.slice(6)));
                } catch {
                  continue;
                }
              }
            }
          }

          if (receivedData) {
            reconnectAttempt = 0;
          }

          scheduleReconnect();
        } finally {
          reader.releaseLock();
        }
      }).catch(() => {
        if (!controller?.signal.aborted && !stopped) {
          scheduleReconnect();
        }
      });
    }

    connect();

    return () => {
      stopped = true;
      controller?.abort();
      if (retryTimeout) {
        clearTimeout(retryTimeout);
      }
    };
  }, [projectId]);
}
