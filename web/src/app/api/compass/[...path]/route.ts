import { type NextRequest, NextResponse } from "next/server";
import { createClient } from "@/lib/supabase/server";

type RouteContext = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, context: RouteContext) {
  const supabase = await createClient();
  const [{ data: userData }, { data: sessionData }] = await Promise.all([
    supabase.auth.getUser(),
    supabase.auth.getSession(),
  ]);
  const token = sessionData.session?.access_token;
  if (!userData.user || !token) {
    return NextResponse.json({ detail: "Authentication required" }, { status: 401 });
  }

  const baseUrl = process.env.COMPASS_API_URL;
  if (!baseUrl) {
    return NextResponse.json({ detail: "Compass API unavailable" }, { status: 503 });
  }
  const { path } = await context.params;
  const target = new URL(`/${path.join("/")}${request.nextUrl.search}`, baseUrl);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": request.headers.get("content-type") ?? "application/json",
      },
      body,
      cache: "no-store",
    });
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json({ detail: "Compass API unavailable" }, { status: 503 });
  }
}

export const GET = forward;
export const POST = forward;
