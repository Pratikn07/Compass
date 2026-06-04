import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import type { Database } from "@/lib/supabase/database.types";
import { getSupabaseEnv } from "@/lib/supabase/env";

export async function createClient() {
  const cookieStore = await cookies();
  const { publishableKey, url } = getSupabaseEnv();

  return createServerClient<Database, "prescient_storage">(url, publishableKey, {
    db: { schema: "prescient_storage" },
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, options, value }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // Server Components cannot set cookies directly; the request proxy
          // handles session refresh writes.
        }
      },
    },
  });
}
