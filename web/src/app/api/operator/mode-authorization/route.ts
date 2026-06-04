import { NextResponse } from "next/server";
import { z } from "zod";
import { createClient } from "@/lib/supabase/server";

const requestSchema = z.object({
  requested_mode: z.enum(["propose_only", "paper", "live"]),
  reason: z.string().trim().min(1),
  confirmation_text: z.string().trim().optional(),
});

function operatorBaseUrl() {
  return process.env.PRESCIENT_OPERATOR_API_URL?.replace(/\/$/, "");
}

async function jsonOrFallback(response: Response) {
  return response.json().catch(() => ({
    error: "Operator endpoint returned malformed JSON",
  }));
}

export async function POST(request: Request) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const operatorUrl = operatorBaseUrl();
  const operatorToken = process.env.PRESCIENT_OPERATOR_API_TOKEN;

  if (!operatorUrl || !operatorToken) {
    return NextResponse.json(
      { error: "Operator action endpoint is not configured" },
      { status: 503 },
    );
  }

  const parsed = requestSchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Invalid mode authorization request" },
      { status: 400 },
    );
  }

  // Defense in depth: live mode is a human + code-rails decision made elsewhere.
  // The frontend must never be a courier for a live request, even via a raw POST.
  if (parsed.data.requested_mode === "live") {
    return NextResponse.json(
      { error: "Frontend is not authorized to request live mode" },
      { status: 403 },
    );
  }

  const response = await fetch(`${operatorUrl}/mode-authorization`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${operatorToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ...parsed.data,
      actor: user.email ?? user.id,
    }),
    cache: "no-store",
  });
  const payload = await jsonOrFallback(response);

  return NextResponse.json(payload, { status: response.status });
}
