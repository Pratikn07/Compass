"use client";

import { useState } from "react";
import { Hourglass, Scale } from "lucide-react";
import { api } from "@/lib/api";
import { Cascade, Rise } from "@/components/motion";
import { Countdown } from "@/components/countdown";
import { ErrorState, Skeleton, useApi } from "@/components/use-api";
import { cn } from "@/lib/utils";

export default function RulesPage() {
  const { data, error, retry } = useApi(() => api.ruleChanges());
  const [proposal, setProposal] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function propose(e: React.FormEvent) {
    e.preventDefault();
    setFormError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(proposal);
    } catch {
      parsed = { description: proposal.trim() };
    }
    if (!proposal.trim()) {
      setFormError("Describe the change first.");
      return;
    }
    setBusy(true);
    try {
      await api.proposeRuleChange(parsed);
      setProposal("");
      retry();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={retry} />;

  return (
    <Cascade className="flex flex-col gap-6">
      <Rise>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <Scale aria-hidden size={20} className="text-text-3" />
          Rule changes
        </h1>
        <p className="mt-1 max-w-xl text-sm leading-relaxed text-text-3">
          Changing the rules is the most dangerous trade there is — so every
          change waits 48 hours before it can take effect. Panic has a
          half-life; the clock outlasts it.
        </p>
      </Rise>

      <Rise>
        <form onSubmit={propose} className="glass p-5">
          <label className="text-xs text-text-3">
            Propose a change (plain words or JSON)
            <textarea
              value={proposal}
              onChange={(e) => setProposal(e.target.value)}
              rows={2}
              placeholder='e.g. "raise the Lab cap" — takes effect no earlier than 48 hours from now'
              className="mt-1 w-full resize-none rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-sm text-text-1 placeholder:text-text-3/60 focus:border-white/25"
            />
          </label>
          {formError && (
            <p role="alert" className="mt-2 text-xs text-alert">
              {formError}
            </p>
          )}
          <button
            type="submit"
            disabled={busy}
            className="mt-3 min-h-11 cursor-pointer rounded-lg border border-white/15 px-4 text-sm transition-all duration-200 hover:border-white/30 active:scale-[0.98] disabled:opacity-50"
          >
            {busy ? "Starting the clock…" : "Propose — start the 48h clock"}
          </button>
        </form>
      </Rise>

      {!data ? (
        <Skeleton className="h-32 w-full" />
      ) : data.length === 0 ? (
        <Rise>
          <div className="glass p-8 text-center">
            <p className="text-sm text-text-2">No rule changes proposed.</p>
            <p className="mt-1 text-xs text-text-3">
              The rules that survived the backtest are still the rules.
            </p>
          </div>
        </Rise>
      ) : (
        data.map((rc) => (
          <Rise key={rc.id}>
            <div className="glass flex flex-wrap items-center justify-between gap-3 p-4">
              <div className="min-w-0">
                <p className="truncate text-sm">
                  {JSON.stringify(rc.change)}
                </p>
                <p className="tnum mt-1 text-xs text-text-3">
                  proposed {new Date(rc.proposed_at).toLocaleString()}
                </p>
              </div>
              <span
                className={cn(
                  "flex items-center gap-2 rounded-full border px-3 py-1 text-xs",
                  rc.active
                    ? "border-up/25 text-up"
                    : "border-white/15 text-text-2",
                )}
              >
                <Hourglass aria-hidden size={12} />
                {rc.active ? (
                  "active"
                ) : (
                  <>
                    cooling off · <Countdown until={rc.effective_at} />
                    {!rc.approved && " · unapproved"}
                  </>
                )}
              </span>
            </div>
          </Rise>
        ))
      )}
    </Cascade>
  );
}
