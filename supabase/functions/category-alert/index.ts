// Supabase Edge Function: "a customer is looking for <category>".
//
// The browser calls this function with the signed-in client's token. The function:
//   1. asks the database to queue the alert as that client (request_category_alert checks the role,
//      the category and the 24-hour limit);
//   2. sends each queued e-mail through Resend with the service role key, which never leaves the server;
//   3. deletes the sent rows from email_outbox so no freelancer e-mail address is kept longer than needed.
//
// Secrets to set in Supabase (Project Settings > Edge Functions > Secrets, or `supabase secrets set`):
//   RESEND_API_KEY   the Resend API key
//   ALERT_FROM       a sender you verified in Resend, for example "XLANORA <alerts@your-domain.com>"
//   SITE_ORIGIN      the website address, for example https://your-site.netlify.app (used for CORS)
// SUPABASE_URL, SUPABASE_ANON_KEY and SUPABASE_SERVICE_ROLE_KEY are provided by Supabase automatically.

import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const ANON_KEY = Deno.env.get("SUPABASE_ANON_KEY") ?? "";
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const RESEND_KEY = Deno.env.get("RESEND_API_KEY") ?? "";
const FROM = Deno.env.get("ALERT_FROM") ?? "";
const SITE_ORIGIN = Deno.env.get("SITE_ORIGIN") ?? "";

const corsHeaders = {
  "Access-Control-Allow-Origin": SITE_ORIGIN || "null",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Vary": "Origin",
};

function json(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

// Map the database's own messages to HTTP answers. Anything else is a server error with no details.
function refusalStatus(message: string): number | null {
  if (message.includes("not_signed_in")) return 401;
  if (message.includes("clients_only")) return 403;
  if (message.includes("invalid_category")) return 400;
  return null;
}

async function sendEmail(to: string, subject: string, text: string): Promise<boolean> {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${RESEND_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ from: FROM, to: [to], subject, text }),
  });
  return res.ok;
}

Deno.serve(async (req: Request): Promise<Response> => {
  if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders });
  if (req.method !== "POST") return json(405, { error: "method_not_allowed" });
  if (!SUPABASE_URL || !ANON_KEY || !SERVICE_KEY) return json(500, { error: "server_not_configured" });

  const authorization = req.headers.get("Authorization") ?? "";
  if (!authorization.startsWith("Bearer ")) return json(401, { error: "not_signed_in" });

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return json(400, { error: "bad_json" });
  }
  const category = typeof (body as { category?: unknown })?.category === "string"
    ? (body as { category: string }).category
    : "";

  // Step 1: queue as the signed-in client. Row-level security and the function's own checks apply.
  const asClient = createClient(SUPABASE_URL, ANON_KEY, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await asClient.rpc("request_category_alert", { p_category: category });
  if (error) {
    const status = refusalStatus(error.message ?? "");
    return status ? json(status, { error: error.message }) : json(500, { error: "alert_failed" });
  }
  const queued: number[] = Array.isArray(data?.queued) ? data.queued : [];
  const recent = Boolean(data?.recent);

  // Step 2: send with the service role. Only queued rows are read.
  let sent = 0;
  let failed = 0;
  if (queued.length > 0) {
    if (!RESEND_KEY || !FROM) {
      // Rows stay queued until the e-mail service is configured; nothing is lost.
      return json(202, { queued: queued.length, recent, delivery: "queued" });
    }
    const admin = createClient(SUPABASE_URL, SERVICE_KEY, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: rows, error: readError } = await admin
      .from("email_outbox")
      .select("id, to_address, subject, body")
      .in("id", queued)
      .eq("status", "queued");
    if (readError) return json(500, { error: "alert_failed" });

    for (const row of rows ?? []) {
      const ok = await sendEmail(row.to_address, row.subject, row.body).catch(() => false);
      if (ok) {
        await admin.from("email_outbox").delete().eq("id", row.id);
        sent += 1;
      } else {
        await admin.from("email_outbox").update({ status: "failed" }).eq("id", row.id);
        failed += 1;
      }
    }
  }

  return json(202, { queued: queued.length, recent, sent, failed, delivery: "sent" });
});
