"use client";

import { useState } from "react";
import { ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";

/** Recording an override requires a reason — the journal prices it later.
 * Blank reasons are blocked client-side AND server-side. */
export function OverrideForm({ onCreated }: { onCreated: () => void }) {
  const [what, setWhat] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (reason.trim().length < 3) {
      setError("A reason is required — it is the whole point of the journal.");
      return;
    }
    setBusy(true);
    try {
      await api.createOverride(what.trim(), reason.trim());
      setWhat("");
      setReason("");
      setDone(true);
      setTimeout(() => setDone(false), 3000);
      onCreated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="glass p-5" data-testid="override-form">
      <h2 className="flex items-center gap-2 text-sm font-medium text-text-2">
        <ShieldAlert aria-hidden size={15} />
        Record an override
      </h2>
      <p className="mt-1 text-xs leading-relaxed text-text-3">
        Acted against the plan (or outside it)? Write it down. A year from now
        the journal will tell you what your gut cost — or earned.
      </p>
      <div className="mt-4 flex flex-col gap-3">
        <label className="text-xs text-text-3">
          What you did
          <input
            value={what}
            onChange={(e) => setWhat(e.target.value)}
            required
            placeholder="e.g. sold half of SMH position"
            className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-text-1 placeholder:text-text-3/60 focus:border-white/25"
          />
        </label>
        <label className="text-xs text-text-3">
          Why (required)
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            rows={2}
            placeholder="the honest reason, not the flattering one"
            className="mt-1 w-full resize-none rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-text-1 placeholder:text-text-3/60 focus:border-white/25"
          />
        </label>
        {error && (
          <p role="alert" className="text-xs text-alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="min-h-11 cursor-pointer rounded-lg border border-white/15 px-4 text-sm text-text-1 transition-all duration-200 hover:border-white/30 active:scale-[0.98] disabled:opacity-50"
        >
          {busy ? "Recording…" : done ? "Recorded ✓" : "Record override"}
        </button>
      </div>
    </form>
  );
}
