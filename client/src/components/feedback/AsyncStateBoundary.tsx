/**
 * AsyncStateBoundary.tsx — Declarative render-gate for async data states.
 *
 * Props:
 *   status          — AsyncStatus ('idle' | 'loading' | 'success' | 'empty' | 'error')
 *   error           — ApiError | null  (shown on 'error')
 *   onRetry?        — callback wired to the "Retry" button on 'error'
 *   emptyTitle?     — heading shown on 'empty' (default: "Nothing here yet")
 *   emptyDescription? — body copy on 'empty'
 *   loadingLabel?   — accessible label for skeleton (default: "Loading…")
 *   children        — rendered only when status === 'success'
 */

import type { ReactNode } from 'react';
import { AlertTriangle, InboxIcon, RefreshCw } from 'lucide-react';
import clsx from 'clsx';
import type { ApiError, AsyncStatus } from '@/types/common.types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AsyncStateBoundaryProps {
  status: AsyncStatus;
  error: ApiError | null;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyDescription?: string;
  loadingLabel?: string;
  children: ReactNode;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Animated skeleton card set — mimics typical content grid. */
function LoadingSkeleton({ label }: { label: string }) {
  return (
    <div role="status" aria-label={label} className="space-y-4">
      {/* Three skeleton "cards" */}
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className={clsx(
            'rounded-xl border border-slate-200 bg-white p-5 shadow-sm',
            'animate-pulse',
          )}
        >
          {/* Fake header line */}
          <div
            className="h-3 rounded-full bg-slate-200"
            style={{ width: `${60 - i * 8}%` }}
          />
          {/* Fake body lines */}
          <div className="mt-3 space-y-2">
            <div className="h-2.5 w-full rounded-full bg-slate-100" />
            <div className="h-2.5 rounded-full bg-slate-100" style={{ width: '80%' }} />
          </div>
          {/* Fake footer chip */}
          <div className="mt-4 flex gap-2">
            <div className="h-5 w-16 rounded-md bg-slate-100" />
            <div className="h-5 w-20 rounded-md bg-slate-100" />
          </div>
        </div>
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}

/** Red alert card shown on 'error'. */
function ErrorCard({
  error,
  onRetry,
}: {
  error: ApiError | null;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col gap-4 rounded-xl border border-red-200 bg-red-50 p-6 text-red-900"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle
          className="mt-0.5 h-5 w-5 shrink-0 text-red-500"
          aria-hidden="true"
        />
        <div className="flex-1">
          <p className="text-sm font-semibold leading-snug">
            {error?.message ?? 'Something went wrong.'}
          </p>
          {error?.code && (
            <p className="mt-1 text-xs text-red-700 opacity-80">
              Error code:{' '}
              <code className="rounded bg-red-100 px-1 py-0.5 font-mono text-[11px]">
                {error.code}
              </code>
              {error.requestId && (
                <>
                  {' '}
                  · Request:{' '}
                  <code className="rounded bg-red-100 px-1 py-0.5 font-mono text-[11px]">
                    {error.requestId}
                  </code>
                </>
              )}
            </p>
          )}
        </div>
      </div>

      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className={clsx(
            'inline-flex items-center gap-2 self-start rounded-lg',
            'border border-red-300 bg-white px-4 py-2 text-sm font-semibold text-red-700',
            'transition-colors hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-500',
          )}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  );
}

/** Empty-state illustration card. */
function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-14 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-2xl border border-slate-200 bg-white shadow-sm text-slate-400">
        <InboxIcon className="h-7 w-7" aria-hidden="true" />
      </span>
      <div>
        <p className="text-sm font-semibold text-slate-700">{title}</p>
        {description && (
          <p className="mt-1 text-xs leading-relaxed text-slate-500">{description}</p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function AsyncStateBoundary({
  status,
  error,
  onRetry,
  emptyTitle = 'Nothing here yet',
  emptyDescription,
  loadingLabel = 'Loading…',
  children,
}: AsyncStateBoundaryProps) {
  if (status === 'idle' || status === 'loading') {
    return <LoadingSkeleton label={loadingLabel} />;
  }

  if (status === 'error') {
    return <ErrorCard error={error} onRetry={onRetry} />;
  }

  if (status === 'empty') {
    return <EmptyState title={emptyTitle} description={emptyDescription} />;
  }

  // status === 'success'
  return <>{children}</>;
}

