import { createBrowserClient } from "@supabase/ssr";
import type { Database } from "@/lib/supabase/database.types";
import { getSupabaseEnv } from "@/lib/supabase/env";

export function createClient() {
  const { publishableKey, url } = getSupabaseEnv();

  return createBrowserClient<Database, "prescient_storage">(
    url,
    publishableKey,
    {
      db: { schema: "prescient_storage" },
    },
  );
}
