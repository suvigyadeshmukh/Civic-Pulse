/**
 * useAsyncData — generic data-fetching hook with AbortController lifecycle management.
 *
 * Concurrency rules enforced:
 *  1. fetcher + options are stored in refs so caller-inline arrow functions never
 *     re-trigger the effect.
 *  2. A fresh AbortController is created on every execution; any previous in-flight
 *     request is aborted when deps change or the component unmounts.
 *  3. AbortError / ERR_CANCELED are silently ignored — they never flip status to 'error'.
 *  4. status = 'empty'  when Array.isArray(result) && result.length === 0
 *              OR options.isEmptyCheck?.(result) returns true.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import type { ApiError, AsyncStatus } from '@/types/common.types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseAsyncDataOptions<T> {
  /** Called when data arrives; return true to treat the result as "empty". */
  isEmptyCheck?: (data: T) => boolean;
  /** Set to false to skip the initial fetch entirely (useful for conditional fetches). */
  enabled?: boolean;
}

export interface UseAsyncDataResult<T> {
  data: T | null;
  status: AsyncStatus;
  error: ApiError | null;
  /** Re-run the fetch manually (e.g. after a "Retry" button press). */
  refetch: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isAbortError(err: unknown): boolean {
  if (err instanceof DOMException && err.name === 'AbortError') return true;
  if (err instanceof Error) {
    // Axios surfaces aborted requests as ERR_CANCELED
    if ((err as Error & { code?: string }).code === 'ERR_CANCELED') return true;
    if (err.name === 'AbortError' || err.name === 'CanceledError') return true;
  }
  return false;
}

function toApiError(err: unknown, status = 0): ApiError {
  if (err && typeof err === 'object' && 'code' in err && 'message' in err) {
    const e = err as Partial<ApiError>;
    return {
      status: e.status ?? status,
      code: e.code ?? 'UNKNOWN',
      message: e.message ?? 'An unexpected error occurred.',
      fieldErrors: e.fieldErrors ?? {},
      requestId: e.requestId,
    };
  }
  const message = err instanceof Error ? err.message : 'An unexpected error occurred.';
  return { status, code: 'UNKNOWN', message, fieldErrors: {} };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * @param fetcher   Async function that accepts an AbortSignal and returns T.
 * @param deps      Dependency array — changing values re-execute the fetch.
 * @param options   Optional behaviour overrides.
 */
export function useAsyncData<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[] = [],
  options: UseAsyncDataOptions<T> = {},
): UseAsyncDataResult<T> {
  // ── Refs — stable references that never stale-close over caller arrow fns ──
  const fetcherRef = useRef(fetcher);
  const optionsRef = useRef(options);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });
  useEffect(() => {
    optionsRef.current = options;
  });

  // ── State ──────────────────────────────────────────────────────────────────
  const [data, setData] = useState<T | null>(null);
  const [status, setStatus] = useState<AsyncStatus>('idle');
  const [error, setError] = useState<ApiError | null>(null);

  // Incrementing counter lets the consumer trigger a manual refetch without
  // changing the semantic deps (avoids spurious dep-array mutations).
  const [retryCount, setRetryCount] = useState(0);

  // AbortController for the currently in-flight request.
  const controllerRef = useRef<AbortController | null>(null);

  // ── Effect ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    const enabled = optionsRef.current.enabled ?? true;
    if (!enabled) {
      setStatus('idle');
      return;
    }

    // Abort any previous in-flight request.
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setStatus('loading');
    setError(null);

    fetcherRef.current(controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;

        const opts = optionsRef.current;
        const isEmpty =
          (Array.isArray(result) && (result as unknown[]).length === 0) ||
          (opts.isEmptyCheck ? opts.isEmptyCheck(result) : false);

        setData(result);
        setStatus(isEmpty ? 'empty' : 'success');
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (isAbortError(err)) return; // Silently ignore abort errors.

        setError(toApiError(err));
        setStatus('error');
      });

    // Cleanup: abort on dep-change or unmount.
    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryCount, ...deps]);

  // ── Public API ─────────────────────────────────────────────────────────────
  const refetch = useCallback(() => setRetryCount((c) => c + 1), []);

  return { data, status, error, refetch };
}

