// Accounts, through Supabase. Only loaded when the site is configured with a project
// (VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY at build time); without them the site runs
// in this-browser-only mode and never contacts Supabase.
//
// The anon key is public by design: what a visitor may read or write is decided by the
// row-level security in web/supabase/migrations, never by keeping this key secret.

const URL = import.meta.env.VITE_SUPABASE_URL;
const KEY = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const configured = Boolean(URL && KEY);

let client = null;
export async function supabase() {
  if (!configured) return null;
  if (!client) {
    const { createClient } = await import("@supabase/supabase-js");
    client = createClient(URL, KEY, { auth: { persistSession: true, detectSessionInUrl: true, flowType: "pkce" } });
  }
  return client;
}

// Where an email link or Google sign-in should come back to: this page, keeping an invite.
function returnUrl() {
  const u = new window.URL(window.location.href);
  u.hash = "";
  for (const k of [...u.searchParams.keys()]) if (k !== "invite") u.searchParams.delete(k);
  return u.toString();
}

// Which sign-in methods the project has switched on, read from Supabase's public settings,
// so the page never offers a button that cannot work (Google stays hidden until set up).
let providersCache = null;
export function providers() {
  if (!configured) return Promise.resolve({ email: false, google: false });
  if (!providersCache) {
    providersCache = fetch(`${URL}/auth/v1/settings`, { headers: { apikey: KEY } })
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => ({ email: j ? Boolean(j.external?.email) : true, google: Boolean(j?.external?.google) }))
      .catch(() => ({ email: true, google: false }));
  }
  return providersCache;
}

// Supabase's own wording, turned into something a visitor can act on.
export function friendlyError(err) {
  const m = String(err?.message || err || "");
  if (/not authori[sz]ed/i.test(m)) {
    return "This site can't send sign-in emails to that address yet: it is still in a private test. Ask the person who shared it with you to add you.";
  }
  if (/rate limit|too many|security purposes/i.test(m)) {
    return "Too many sign-in emails in a short time. Wait a few minutes and try again.";
  }
  if (/invalid.*email/i.test(m)) return "That doesn't look like an email address.";
  return m || "Something went wrong. Try again in a moment.";
}

export async function sendMagicLink(email) {
  const sb = await supabase();
  const { error } = await sb.auth.signInWithOtp({ email, options: { emailRedirectTo: returnUrl() } });
  if (error) throw error;
}

export async function signInWithGoogle() {
  const sb = await supabase();
  const { error } = await sb.auth.signInWithOAuth({ provider: "google", options: { redirectTo: returnUrl() } });
  if (error) throw error;
}

export async function currentUser() {
  const sb = await supabase();
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session ? data.session.user : null;
}

export async function signOut() {
  const sb = await supabase();
  await sb.auth.signOut();
}

// The household this user belongs to, or null for a brand-new account.
export async function myHousehold() {
  const sb = await supabase();
  const { data, error } = await sb.from("household_members")
    .select("household_id, households(id, mode)")
    .limit(1).maybeSingle();
  if (error) throw error;
  return data ? { id: data.household_id, mode: data.households?.mode || "single" } : null;
}

export async function createHousehold(mode) {
  const sb = await supabase();
  const { data, error } = await sb.rpc("create_household", { p_mode: mode === "couple" ? "couple" : "single" });
  if (error) throw error;
  return data;
}

export async function createInvite(householdId) {
  const sb = await supabase();
  const { data, error } = await sb.rpc("create_invite", { p_household: householdId });
  if (error) throw error;
  const u = new window.URL(window.location.href);
  u.search = ""; u.hash = "";
  u.searchParams.set("invite", data);
  return u.toString();
}

export async function acceptInvite(token) {
  const sb = await supabase();
  const { data, error } = await sb.rpc("accept_invite", { p_token: token });
  if (error) throw error;
  return data;
}

export async function deleteAccount() {
  const sb = await supabase();
  const { error } = await sb.rpc("delete_my_account");
  if (error) throw error;
  await sb.auth.signOut();
}
