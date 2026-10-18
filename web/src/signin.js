// Signing in: the start screen a new visitor sees, and the email-code form it shares with
// the "Save your map" dialog. No passwords: the visitor types an email, then the code
// Supabase emails them.
import * as auth from "./auth.js";
import { esc } from "./util.js";

// The two-step form (email, then code), drawn into `box`. Resolves with the signed-in user.
// create: whether an address with no account may make one (false behind "Log in").
export function codeForm(box, { create }) {
  return new Promise((resolve) => {
    let email = "";

    function askEmail(msg = "") {
      box.innerHTML = `<form class="field" id="cf-email">
          <label for="cf-email-in">Email</label>
          <input id="cf-email-in" type="email" required autocomplete="email" placeholder="you@example.com" value="${esc(email)}">
          <button type="submit" class="btn primary">Email me a code</button></form>
        <p class="note-saved" id="cf-msg" role="status">${esc(msg)}</p>
        <p class="md-or" hidden>or</p>
        <button type="button" class="btn" id="cf-google" hidden>Continue with Google</button>`;
      const form = box.querySelector("#cf-email"), input = box.querySelector("#cf-email-in");
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        email = input.value.trim();
        const btn = form.querySelector("button");
        btn.disabled = true;
        box.querySelector("#cf-msg").textContent = "Sending…";
        try { await auth.sendCode(email, { create }); askCode(); }
        catch (err) { btn.disabled = false; box.querySelector("#cf-msg").textContent = auth.friendlyError(err); }
      });
      box.querySelector("#cf-google").addEventListener("click", async () => {
        try { await auth.signInWithGoogle(); } catch (err) { box.querySelector("#cf-msg").textContent = auth.friendlyError(err); }
      });
      auth.providers().then((p) => {
        if (!box.contains(form)) return;
        box.querySelector("#cf-google").hidden = !p.google;
        box.querySelector(".md-or").hidden = !p.google;
      });
      input.focus();
    }

    function askCode(msg = "") {
      box.innerHTML = `<p class="small">We emailed a code to <b>${esc(email)}</b>. It can take a minute, and may land in spam.</p>
        <form class="field" id="cf-code">
          <label for="cf-code-in">Code from the email</label>
          <input id="cf-code-in" class="code-in num" type="text" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6,10}" maxlength="10" required placeholder="123456">
          <button type="submit" class="btn primary">Sign in</button></form>
        <p class="note-saved" id="cf-msg" role="status">${esc(msg)}</p>
        <p class="small muted"><button type="button" class="link" id="cf-resend">Send a new code</button> · <button type="button" class="link" id="cf-other">Use a different email</button></p>`;
      const form = box.querySelector("#cf-code"), input = box.querySelector("#cf-code-in");
      const say = (t) => { box.querySelector("#cf-msg").textContent = t; };
      input.addEventListener("input", () => { input.value = input.value.replace(/\D/g, ""); });
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const btn = form.querySelector("button");
        btn.disabled = true;
        say("Checking…");
        try { const user = await auth.verifyCode(email, input.value); say("Signed in. Opening your map…"); resolve(user); }
        catch (err) { btn.disabled = false; say(auth.friendlyError(err)); }
      });
      box.querySelector("#cf-resend").addEventListener("click", async () => {
        say("Sending…");
        try { await auth.sendCode(email, { create }); say(`New code sent to ${email}.`); }
        catch (err) { say(auth.friendlyError(err)); }
      });
      box.querySelector("#cf-other").addEventListener("click", () => askEmail());
      input.focus();
    }

    askEmail();
  });
}

// What a visitor sees first when accounts are on and this device has no map yet.
// Resolves { user } once signed in, or { guest: true } to try the site without an account.
// invited: they followed a partner's invite link, so the only way on is to sign in.
export function startScreen({ invited = false } = {}) {
  const root = document.getElementById("wizard");
  root.hidden = false;
  document.body.classList.add("wizard-open");

  return new Promise((resolve) => {
    function card(inner) {
      root.innerHTML = `<div class="wz-card start" role="dialog" aria-modal="true" aria-labelledby="st-title">
        <div class="wz-top"><span class="wz-brand">WILINSKI <i>ATLAS</i></span></div>${inner}</div>`;
    }

    function choose() {
      card(`<h2 id="st-title">Where should you live?</h2>
        <p class="wz-lede">The Atlas scores every US county and every town over 5,000 people against what matters to you, and puts the places you already like next to the ones the data says you should see.</p>
        <div class="start-btns">
          <button type="button" class="btn" id="st-login">Log in</button>
          <button type="button" class="btn primary" id="st-setup">Set up account</button>
        </div>
        <p class="small muted start-guest"><button type="button" class="link" id="st-guest">Look around without an account</button> (your map stays on this device)</p>`);
      root.querySelector("#st-login").addEventListener("click", () => signIn("login"));
      root.querySelector("#st-setup").addEventListener("click", () => signIn("setup"));
      root.querySelector("#st-guest").addEventListener("click", () => resolve({ guest: true }));
      root.querySelector("#st-setup").focus();
    }

    function signIn(kind) {
      const title = { login: "Log in", setup: "Set up your account", invite: "Join your partner's map" }[kind];
      const lede = {
        login: "Type the email you signed up with. We'll send you a code; no password needed.",
        setup: "Type your email and we'll send you a code to confirm it. Then a few questions build your map, saved to your account so it's on every device.",
        invite: "Your partner invited you to share their map. Sign in, or create an account, with your email: we'll send you a code.",
      }[kind];
      card(`<h2 id="st-title">${esc(title)}</h2>
        <p class="wz-lede">${esc(lede)}</p>
        <div id="st-form"></div>
        ${kind === "invite" ? "" : `<div class="wz-nav"><button type="button" class="btn" id="st-back">Back</button></div>`}`);
      root.querySelector("#st-back")?.addEventListener("click", choose);
      codeForm(root.querySelector("#st-form"), { create: kind !== "login" }).then((user) => {
        root.querySelector("#st-back")?.remove();
        resolve({ user });
      });
    }

    if (invited) signIn("invite"); else choose();
  });
}
