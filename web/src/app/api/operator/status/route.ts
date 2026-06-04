import { NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

function operatorBaseUrl() {
  return process.env.PRESCIENT_OPERATOR_API_URL?.replace(/\/$/, "");
}

async function jsonOrFallback(response: Response) {
  return response.json().catch(() => ({
    error: "Operator endpoint returned malformed JSON",
  }));
}

export async function GET() {
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

  const response = await fetch(`${operatorUrl}/status`, {
    headers: { Authorization: `Bearer ${operatorToken}` },
    cache: "no-store",
  });
  const payload = await jsonOrFallback(response);

  return NextResponse.json(payload, { status: response.status });
}
