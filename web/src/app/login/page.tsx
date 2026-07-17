"use client";

import { useState, type FormEvent } from "react";
import { Compass } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const { error: signInError } = await createClient().auth.signInWithPassword({
      email,
      password,
    });
    setBusy(false);
    if (signInError) {
      setError("Sign-in failed. Check your email and password.");
      return;
    }
    window.location.assign("/");
  }

  return (
    <div className="flex min-h-[80dvh] items-center justify-center px-4">
      <section className="glass w-full max-w-sm p-6">
        <Compass aria-hidden size={24} className="text-accent-a" />
        <h1 className="mt-4 text-2xl font-semibold">Compass</h1>
        <p className="mt-1 text-sm text-text-3">Sign in to your private research workspace.</p>
        <form onSubmit={signIn} className="mt-6 space-y-4">
          <label className="block text-sm text-text-2">
            Email
            <input
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-text-1"
            />
          </label>
          <label className="block text-sm text-text-2">
            Password
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="mt-1 w-full rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 text-text-1"
            />
          </label>
          {error && <p role="alert" className="text-sm text-alert">{error}</p>}
          <button
            type="submit"
            disabled={busy}
            className="min-h-11 w-full rounded-lg bg-text-1 px-4 text-sm font-medium text-ink-0 disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </section>
    </div>
  );
}
