/**
 * useAsyncAction — custom mutation hook (replaces useMutation).
 *
 * Features:
 *  - Stores actionFn + options in refs so inline arrow functions passed by
 *    callers never cause hook identity issues.
 *  - Automatically pushes error/success toasts to the global ToastContainer store.
 *  - Exposes { execute, data, error, isSubmitting, isSuccess, isError, reset }.
 */

import { useCallback, useRef, useState } from 'react';
import type { ApiError } from '@/types/common.types';
import { showToast } from '@/components/feedback/ToastContainer';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface UseAsyncActionOptions<TResult> {
  onSuccess?: (data: TResult) => void;
  onError?: (err: ApiError) => void;
  /** When provided, a success toast is shown automatically. */
  successMessage?: string;
}

export interface UseAsyncActionResult<TArgs extends unknown[], TResult> {
  execute: (...args: TArgs) => Promise<TResult | undefined>;
  data: TResult | null;
  error: ApiError | null;
  isSubmitting: boolean;
  isSuccess: boolean;
  isError: boolean;
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Helper — normalise unknown thrown values into ApiError
// ---------------------------------------------------------------------------

function toApiError(err: unknown): ApiError {
  if (err && typeof err === 'object' && 'code' in err && 'message' in err) {
    const e = err as Partial<ApiError>;
    return {
      status: e.status ?? 0,
      code: e.code ?? 'UNKNOWN',
      message: e.message ?? 'An unexpected error occurred.',
      fieldErrors: e.fieldErrors ?? {},
      requestId: e.requestId,
    };
  }
  const message = err instanceof Error ? err.message : 'An unexpected error occurred.';
  return { status: 0, code: 'UNKNOWN', message, fieldErrors: {} };
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAsyncAction<TArgs extends unknown[], TResult = unknown>(
  actionFn: (...args: TArgs) => Promise<TResult>,
  options?: UseAsyncActionOptions<TResult>,
): UseAsyncActionResult<TArgs, TResult> {
  // ── Refs — stable; never stale-close over caller-provided arrow fns ──────
  const actionRef = useRef(actionFn);
  const optionsRef = useRef(options);
  // Keep refs current on every render (no useEffect needed — synchronous).
  actionRef.current = actionFn;
  optionsRef.current = options;

  // ── State ────────────────────────────────────────────────────────────────
  const [data, setData] = useState<TResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [isError, setIsError] = useState(false);

  // ── execute ──────────────────────────────────────────────────────────────
  const execute = useCallback(
    async (...args: TArgs): Promise<TResult | undefined> => {
      setIsSubmitting(true);
      setIsSuccess(false);
      setIsError(false);
      setError(null);

      try {
        const result = await actionRef.current(...args);

        setData(result);
        setIsSuccess(true);

        const opts = optionsRef.current;
        if (opts?.successMessage) {
          showToast(opts.successMessage, 'success');
        }
        opts?.onSuccess?.(result);

        return result;
      } catch (err: unknown) {
        const apiErr = toApiError(err);

        setError(apiErr);
        setIsError(true);

        showToast(apiErr.message, 'error');
        optionsRef.current?.onError?.(apiErr);

        return undefined;
      } finally {
        setIsSubmitting(false);
      }
    },
    [], // execute itself is stable; state is captured via refs
  );

  // ── reset ────────────────────────────────────────────────────────────────
  const reset = useCallback(() => {
    setData(null);
    setError(null);
    setIsSubmitting(false);
    setIsSuccess(false);
    setIsError(false);
  }, []);

  return { execute, data, error, isSubmitting, isSuccess, isError, reset };
}

