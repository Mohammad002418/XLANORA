// Backend selection for the contact form.
//   backend: "local"    -> POST /api/contact on the Python server (SQLite database)
//   backend: "supabase" -> POST to Supabase REST API (Postgres, row-level security)
// The anon key is public by design; RLS limits it to inserting contact messages.
// Never put the service role key in this file.
window.XLANORA_CONFIG = {
  backend: "supabase",
  endpoint: "/api/contact",
  supabaseUrl: "https://vohfzgufykejuzcblwjt.supabase.co",
  supabaseAnonKey: "sb_publishable_zWQfnK4f7-quFbw-NtjDSg_oqCLBLkg"
};
