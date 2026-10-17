// Boot: load the data, then decide what the visitor sees.
//
//   first visit            -> setup wizard -> their map, saved on this device
//   map on this device     -> their map, with "Save your map" (sign-up) in the header
//   signed in              -> their household's map from Supabase, live for a couple
//   ?invite=<token>        -> sign in, join the partner's household
//
// The account wall sits after the wizard by design: a visitor sees what the Atlas does
// for them before being asked for anything.
import "./styles.css";
import { createApp } from "./app.js";
import * as auth from "./auth.js";
import { defaultSettings, Model, normalizeSettings } from "./model.js";
import { LocalStore, RemoteStore } from "./store.js";
import { esc } from "./util.js";
import { runWizard } from "./wizard.js";

const DONATE_URL = import.meta.env.VITE_DONATE_URL || "";
const $ = (sel) => document.querySelector(sel);

let model, app, remote = null, household = null, unsubscribe = () => {};
const local = new LocalStore();

// ------------------------------------------------------------------ modal
function modal(title, html, wire) {
  const m = $("#modal");
  m.innerHTML = `<div class="md-card" role="dialog" aria-modal="true" aria-labelledby="md-title">
    <div class="md-top"><h2 id="md-title">${esc(title)}</h2><button type="button" class="link" id="md-close" aria-label="Close">Close</button></div>
    <div class="md-body">${html}</div></div>`;
  m.hidden = false;
  const close = () => { m.hidden = true; m.innerHTML = ""; };
  $("#md-close").addEventListener("click", close);
  m.onclick = (e) => { if (e.target === m) close(); };
  m.onkeydown = (e) => { if (e.key === "Escape") close(); };
  if (wire) wire(m, close);
  (m.querySelector("input, button.primary") || $("#md-close")).focus();
  return close;
}

function signInModal(reason) {
  modal("Save your map", `
    <p class="small muted">${esc(reason || "Create a free account to keep your map, use it on your phone, and share it with your partner. No password: we email you a sign-in link.")}</p>
    <form id="md-email" class="field"><label for="md-email-in">Email</label>
      <input id="md-email-in" type="email" required autocomplete="email" placeholder="you@example.com">
      <button type="submit" class="btn primary">Email me a sign-in link</button></form>
    <p class="md-or">or</p>
    <button type="button" class="btn" id="md-google">Continue with Google</button>
    <p class="note-saved" id="md-msg" role="status"></p>
    <p class="small muted">Your map stays on this device until you sign in, then moves to your account. We store your settings, pins and notes, nothing else. You can delete it all at any time.</p>`,
  (m) => {
    m.querySelector("#md-email").addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = m.querySelector("#md-email-in").value.trim();
      const msg = m.querySelector("#md-msg");
      msg.textContent = "Sending…";
      try { await auth.sendMagicLink(email); msg.textContent = `Check ${email} for a sign-in link. Open it on this device to keep the map you just made.`; }
      catch (err) { msg.textContent = `Could not send the link: ${err.message}`; }
    });
    m.querySelector("#md-google").addEventListener("click", async () => {
      try { await auth.signInWithGoogle(); } catch (err) { m.querySelector("#md-msg").textContent = `Google sign-in failed: ${err.message}`; }
    });
  });
}

// ------------------------------------------------------------------ header account area
function renderAccount(user) {
  const box = $("#account");
  const donate = DONATE_URL ? `<a class="btn" href="${esc(DONATE_URL)}" target="_blank" rel="noopener">Support</a>` : "";
  if (!user) {
    box.innerHTML = `${donate}${auth.configured ? `<button type="button" class="btn primary" id="acct-save">Save your map</button>` : ""}
      <button type="button" class="btn" id="acct-menu" aria-haspopup="true">Menu</button>`;
    $("#acct-save")?.addEventListener("click", () => signInModal());
    $("#acct-menu").addEventListener("click", () => modal("This map", `
      <div class="md-list">
        <button type="button" class="btn" id="mm-setup">Redo setup</button>
        <button type="button" class="btn danger" id="mm-reset">Start over (clears this device)</button>
      </div>`, (m, close) => {
      m.querySelector("#mm-setup").addEventListener("click", () => { close(); editSetup(); });
      m.querySelector("#mm-reset").addEventListener("click", () => { local.clear(); window.location.reload(); });
    }));
    return;
  }
  box.innerHTML = `${donate}<button type="button" class="btn" id="acct-menu" aria-haspopup="true">${esc((user.email || "Account").split("@")[0])}</button>`;
  $("#acct-menu").addEventListener("click", () => modal("Your account", `
    <p class="small muted">Signed in as ${esc(user.email || "")}. ${household?.mode === "couple" ? "This is a shared map for two." : "This map is just yours."}</p>
    <div class="md-list">
      <button type="button" class="btn" id="mm-setup">Redo setup</button>
      ${household?.mode === "couple" ? `<button type="button" class="btn" id="mm-invite">Invite your partner</button>` : `<button type="button" class="btn" id="mm-couple">Make this a couple's map</button>`}
      <button type="button" class="btn" id="mm-out">Sign out</button>
      <button type="button" class="btn danger" id="mm-delete">Delete my account</button>
    </div>
    <div id="mm-extra"></div>`, (m, close) => {
    m.querySelector("#mm-setup").addEventListener("click", () => { close(); editSetup(); });
    m.querySelector("#mm-out").addEventListener("click", async () => { await auth.signOut(); window.location.reload(); });
    const invite = async () => {
      const extra = m.querySelector("#mm-extra");
      extra.innerHTML = `<p class="small muted">Creating a link…</p>`;
      try {
        const link = await auth.createInvite(household.id);
        extra.innerHTML = `<div class="field"><label for="mm-link">Send this link to your partner. It works once and expires in 7 days.</label>
          <input id="mm-link" readonly value="${esc(link)}"><button type="button" class="btn primary" id="mm-copy">Copy link</button></div>`;
        m.querySelector("#mm-copy").addEventListener("click", async () => {
          const inp = m.querySelector("#mm-link");
          try { await navigator.clipboard.writeText(inp.value); m.querySelector("#mm-copy").textContent = "Copied"; }
          catch { inp.select(); }
        });
      } catch (err) { extra.innerHTML = `<p class="small">Could not create a link: ${esc(err.message)}</p>`; }
    };
    m.querySelector("#mm-invite")?.addEventListener("click", invite);
    m.querySelector("#mm-couple")?.addEventListener("click", async () => {
      model.settings.mode = "couple";
      await remote.saveSettings(model.settings);
      household.mode = "couple";
      await invite();
    });
    m.querySelector("#mm-delete").addEventListener("click", () => {
      m.querySelector("#mm-extra").innerHTML = `<p class="small">This deletes your account${household?.mode === "couple" ? " and removes you from the shared map (your partner keeps it)" : ", your map, pins and notes"}. It cannot be undone.</p>
        <button type="button" class="btn danger" id="mm-delete-yes">Yes, delete everything</button>`;
      m.querySelector("#mm-delete-yes").addEventListener("click", async () => {
        try { await auth.deleteAccount(); local.clear(); window.location.reload(); }
        catch (err) { m.querySelector("#mm-extra").innerHTML = `<p class="small">Could not delete: ${esc(err.message)}</p>`; }
      });
    });
  }));
}

// ------------------------------------------------------------------ setup
async function saveAll(store, { settings, pins }, previousPins = []) {
  await store.saveSettings(settings);
  const keep = new Set(pins.map((p) => p.id));
  for (const p of previousPins) if (!keep.has(p.id)) await store.removePin(p.id);
  for (const p of pins) await store.savePin(p);
}

async function editSetup() {
  const store = app.store;
  const before = await Promise.resolve(store.load());
  const result = await runWizard(model, { settings: model.settings, pins: before.pins, cancellable: true });
  if (!result) return;
  await saveAll(store, result, before.pins);
  const data = await Promise.resolve(store.load());
  data.settings = normalizeSettings(model.core, data.settings);
  app.show(data);
}

async function firstRun(store) {
  const result = await runWizard(model, { settings: defaultSettings(model.core), pins: [] });
  await saveAll(store, result);
  return { settings: result.settings, pins: result.pins, towns: {} };
}

// ------------------------------------------------------------------ accounts
async function enterAccount(user, inviteToken) {
  const draft = local.load();
  if (inviteToken) {
    try {
      household = { id: await auth.acceptInvite(inviteToken), mode: "couple" };
    } catch (err) {
      const msg = String(err.message || "");
      if (msg.includes("already_in_household")) {
        modal("You already have a map", `<p class="small">This account already has its own map. To join your partner's instead, delete your account from the menu first, then open the invite link again.</p>`);
      } else {
        modal("That invite didn't work", `<p class="small">${esc(msg.includes("invite_") ? "The link has expired or was already used. Ask your partner for a new one." : msg)}</p>`);
      }
    }
    clearUrl();
  }
  if (!household) household = await auth.myHousehold();
  const sb = await auth.supabase();
  if (!household) {
    const id = await auth.createHousehold(draft.settings?.mode || "single");
    household = { id, mode: draft.settings?.mode || "single" };
    remote = new RemoteStore(sb, id);
    if (draft.settings?.done) { await remote.importDraft(draft); local.clear(); }
  } else {
    remote = new RemoteStore(sb, household.id);
  }
  app.setStore(remote);
  let data = await remote.load();
  if (!data.settings) data = await firstRun(remote);
  data.settings = normalizeSettings(model.core, data.settings);
  app.show(data);
  renderAccount(user);
  unsubscribe();
  unsubscribe = remote.subscribe(async () => {
    const editing = document.activeElement && ["note", "md-email-in"].includes(document.activeElement.id);
    if (editing || document.activeElement?.type === "range") return;
    const fresh = await remote.load();
    fresh.settings = normalizeSettings(model.core, fresh.settings);
    app.show(fresh);
  });
}

function clearUrl() {
  const u = new URL(window.location.href);
  for (const k of ["invite", "code"]) u.searchParams.delete(k);
  window.history.replaceState(null, "", u.toString());
}

// ------------------------------------------------------------------ boot
async function boot() {
  const [core, us] = await Promise.all([
    fetch("data/core.json").then((r) => { if (!r.ok) throw new Error(`data/core.json ${r.status}`); return r.json(); }),
    fetch("geo/us.json").then((r) => { if (!r.ok) throw new Error(`geo/us.json ${r.status}`); return r.json(); }),
  ]);
  model = new Model(core);
  app = createApp({ model, store: local, onEditSetup: editSetup });
  await app.start(us);
  $("#loading").hidden = true;

  const inviteToken = new URLSearchParams(window.location.search).get("invite");
  const user = auth.configured ? await auth.currentUser() : null;
  if (user) {
    clearUrl();
    await enterAccount(user, inviteToken);
    return;
  }
  // An invited partner joins an existing map: no wizard, straight to signing in.
  if (inviteToken && auth.configured) {
    app.show({ settings: defaultSettings(core), pins: [], towns: {} });
    renderAccount(null);
    signInModal("Your partner invited you to share their map. Sign in, or create an account, to join it. The link brings you back here.");
    return;
  }
  let data = local.load();
  if (!data.settings?.done) data = await firstRun(local);
  data.settings = normalizeSettings(core, data.settings);
  app.show(data);
  renderAccount(null);
}

boot().catch((e) => {
  $("#loading").hidden = false;
  $("#loading").textContent = "Could not load the map: " + e.message;
});
