// Boot: load the data, then decide what the visitor sees.
//
//   first visit            -> start screen: Log in, or Set up account (email code, then
//                             the setup wizard), or look around without an account
//   map on this device     -> their map, with "Save your map" (sign-up) in the header
//   signed in              -> their household's map from Supabase, live for a couple
//   ?invite=<token>        -> sign in with an email code, join the partner's household
//
// Without Supabase settings (the artifact preview) there is no start screen: the wizard
// runs straight away and the map stays on this device.
import "./styles.css";
import { createApp } from "./app.js";
import * as auth from "./auth.js";
import { defaultSettings, Model, normalizeSettings } from "./model.js";
import { LocalStore, RemoteStore } from "./store.js";
import { codeForm, startScreen } from "./signin.js";
import { esc } from "./util.js";
import { closeWizard, runWizard } from "./wizard.js";

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

function signInModal() {
  modal("Save your map", `
    <p class="small muted">Create a free account to keep your map, use it on your phone, and share it with your partner. Already have one? Use the same email. No password: we email you a code.</p>
    <div id="md-form"></div>
    <p class="small muted">Your map stays on this device until you sign in, then moves to your account. We store your settings, pins and notes, nothing else. You can delete it all at any time.</p>`,
  (m, close) => {
    codeForm(m.querySelector("#md-form"), { create: true }).then(async (user) => {
      close();
      try { await enterAccount(user, null); }
      catch (err) { modal("Could not open your account", `<p class="small">${esc(err.message)}</p>`); }
    });
  });
}

// ------------------------------------------------------------------ donate banner
// Floats over the map until dismissed; a dismissal holds on this device for 30 days. The
// same link stays in the menus. Hidden entirely when the build has no donate link.
const BANNER_KEY = "atlas.donate.hidden";
const COFFEE = `<svg class="donate-ico" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 10h12v4.5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V10z"/><path d="M16 11.5h1.5a2.5 2.5 0 0 1 0 5H16"/>
  <path d="M8 2.8c-.8.9.8 1.8 0 2.7M11.5 2.8c-.8.9.8 1.8 0 2.7"/><path d="M3 21.5h14"/></svg>`;

function donateBanner() {
  if (!DONATE_URL) return;
  try { if (Date.now() - Number(localStorage.getItem(BANNER_KEY) || 0) < 30 * 864e5) return; }
  catch { /* storage blocked: show the banner */ }
  const b = document.createElement("aside");
  b.className = "donate";
  b.id = "donate";
  b.setAttribute("aria-label", "Support this project");
  b.innerHTML = `${COFFEE}<p>This project is entirely free, feel free to buy me a coffee. <a href="${esc(DONATE_URL)}" target="_blank" rel="noopener">Donate here</a></p>
    <button type="button" class="donate-x" aria-label="Hide this banner">×</button>`;
  b.querySelector(".donate-x").addEventListener("click", () => {
    b.remove();
    try { localStorage.setItem(BANNER_KEY, String(Date.now())); } catch { /* it returns next visit */ }
  });
  document.body.appendChild(b);
}

// ------------------------------------------------------------------ header account area
function renderAccount(user) {
  const box = $("#account");
  const donate = DONATE_URL ? `<a class="btn" href="${esc(DONATE_URL)}" target="_blank" rel="noopener">Support this project</a>` : "";
  if (!user) {
    box.innerHTML = `${auth.configured ? `<button type="button" class="btn primary" id="acct-save">Save your map</button>` : ""}
      <button type="button" class="btn" id="acct-menu" aria-haspopup="true">Menu</button>`;
    $("#acct-save")?.addEventListener("click", () => signInModal());
    $("#acct-menu").addEventListener("click", () => modal("This map", `
      <div class="md-list">
        <button type="button" class="btn" id="mm-setup">Redo setup</button>
        ${donate}
        <button type="button" class="btn danger" id="mm-reset">Start over (clears this device)</button>
      </div>`, (m, close) => {
      m.querySelector("#mm-setup").addEventListener("click", () => { close(); editSetup(); });
      m.querySelector("#mm-reset").addEventListener("click", () => { local.clear(); window.location.reload(); });
    }));
    return;
  }
  box.innerHTML = `<button type="button" class="btn" id="acct-menu" aria-haspopup="true">${esc((user.email || "Account").split("@")[0])}</button>`;
  $("#acct-menu").addEventListener("click", () => modal("Your account", `
    <p class="small muted">Signed in as ${esc(user.email || "")}. ${household?.mode === "couple" ? "This is a shared map for two." : "This map is just yours."}</p>
    <div class="md-list">
      <button type="button" class="btn" id="mm-setup">Redo setup</button>
      ${household?.mode === "couple" ? `<button type="button" class="btn" id="mm-invite">Invite your partner</button>` : `<button type="button" class="btn" id="mm-couple">Make this a couple's map</button>`}
      ${donate}
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
  closeWizard();
}

// The loading screen stays up until there is something to show: a returning visitor's map
// arrives only after the sign-in check (which loads the Supabase library) and, signed in,
// a round trip to Supabase; until then the map would be empty.
const ready = () => { $("#loading").hidden = true; };

async function firstRun(store) {
  ready();
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
  if (!data.settings) {
    data = await firstRun(remote);
    // Account first ("Set up account"): the household was made before the wizard asked
    // who's moving, so take its answer now.
    if (data.settings.mode !== household.mode) {
      await auth.setHouseholdMode(household.id, data.settings.mode);
      household.mode = data.settings.mode;
    }
  }
  data.settings = normalizeSettings(model.core, data.settings);
  app.show(data);
  ready();
  closeWizard();
  renderAccount(user);
  unsubscribe();
  unsubscribe = remote.subscribe(async () => {
    const editing = document.activeElement && ["note", "cf-email-in", "cf-code-in"].includes(document.activeElement.id);
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

  donateBanner();
  const inviteToken = new URLSearchParams(window.location.search).get("invite");
  const user = auth.configured ? await auth.currentUser() : null;
  if (user) {
    clearUrl();
    await enterAccount(user, inviteToken);
    return;
  }
  let data = local.load();
  // A partner's invite always signs in (no wizard: they join an existing map). Otherwise
  // the start screen shows until this device has a map of its own.
  if (auth.configured && (inviteToken || !data.settings?.done)) {
    ready();
    const start = await startScreen({ invited: Boolean(inviteToken) });
    if (start.user) {
      await enterAccount(start.user, inviteToken);
      return;
    }
  }
  if (!data.settings?.done) data = await firstRun(local);
  data.settings = normalizeSettings(core, data.settings);
  app.show(data);
  ready();
  closeWizard();
  renderAccount(null);
}

boot().catch((e) => {
  closeWizard();
  $("#loading").hidden = false;
  $("#loading").textContent = "Could not load the map: " + e.message;
});
