import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSpanStream } from './useSpanStream'

function streamResponse(
  reader: {
    read: () => Promise<ReadableStreamReadResult<Uint8Array>>
    releaseLock: () => void
  },
) {
  return {
    ok: true,
    body: {
      getReader: () => reader,
    },
  } as unknown as Response
}

describe('useSpanStream', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
    localStorage.setItem('token', 'token-1')
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    cleanupTimers()
    localStorage.clear()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  function cleanupTimers() {
    vi.clearAllTimers()
  }

  async function flushPromises() {
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  it('reconnects after a non-2xx stream response', async () => {
    fetchMock.mockResolvedValue({ ok: false, body: null } as Response)

    renderHook(() => useSpanStream('project-1', vi.fn()))

    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock).toHaveBeenLastCalledWith(
      'http://localhost:8000/v1/stream/spans?project_id=project-1',
      expect.objectContaining({
        headers: {
          Authorization: 'Bearer token-1',
          Accept: 'text/event-stream',
        },
      }),
    )
  })

  it('reconnects after a normal stream close', async () => {
    const releaseLock = vi.fn()
    fetchMock.mockResolvedValue(
      streamResponse({
        read: vi.fn().mockResolvedValue({ done: true, value: undefined }),
        releaseLock,
      }),
    )

    renderHook(() => useSpanStream('project-1', vi.fn()))

    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(releaseLock).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('cleans up the stream and pending reconnect on unmount', async () => {
    const releaseLock = vi.fn()
    fetchMock.mockResolvedValue(
      streamResponse({
        read: vi.fn().mockResolvedValue({ done: true, value: undefined }),
        releaseLock,
      }),
    )

    const { unmount } = renderHook(() => useSpanStream('project-1', vi.fn()))

    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(releaseLock).toHaveBeenCalledTimes(1)

    const fetchOptions = fetchMock.mock.calls[0][1] as RequestInit
    const signal = fetchOptions.signal as AbortSignal

    unmount()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(signal.aborted).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
