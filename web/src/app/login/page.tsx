"use client";

import { useState, type FormEvent } from "react";
import { ErrorState } from "@/components/states/error-state";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    const supabase = createClient();
    const { error: signInError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    setBusy(false);

    if (signInError) {
      setError(signInError.message);
      return;
    }

    window.location.assign("/decisions");
  }

  return (
    <main className="flex min-h-dvh items-center justify-center px-6 py-10">
      <Card className="w-full max-w-sm">
        <div className="mb-6">
          <h1 className="text-xl font-semibold">Prescient</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Sign in to review engine decisions.
          </p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="email" className="text-sm font-medium">
              Email
            </label>
            <Input
              id="email"
              autoComplete="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <label htmlFor="password" className="text-sm font-medium">
              Password
            </label>
            <Input
              id="password"
              autoComplete="current-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>
          {error ? <ErrorState title={error} /> : null}
          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Signing in..." : "Sign in"}
          </Button>
        </form>
      </Card>
    </main>
  );
}
