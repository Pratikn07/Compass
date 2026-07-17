"use client";

import { useEffect, useState } from "react";

/** Minimal data hook: loading -> skeleton, error -> recoverable message. */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let alive = true;
    fetcher()
      .then((d) => alive && setData(d))
      .catch((e: Error) => alive && setError(e.message));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return {
    data,
    error,
    retry: () => {
      setData(null);
      setError(null);
      setTick((t) => t + 1);
    },
  };
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="glass p-6 text-center" role="alert">
      <p className="text-sm text-text-2">
        {message.startsWith("401") ? "Your session has expired." : "Could not reach the Compass API."}
      </p>
      <p className="tnum mt-1 text-xs text-text-3">{message}</p>
      <button
        onClick={onRetry}
        className="mt-4 cursor-pointer rounded-lg border border-white/15 px-4 py-2 text-sm text-text-2 transition-colors hover:border-white/30 hover:text-text-1"
      >
        Retry
      </button>
      {message.startsWith("401") && (
        <a href="/login" className="ml-3 text-sm text-accent-a">Sign in</a>
      )}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={`skeleton ${className ?? ""}`} />;
}
