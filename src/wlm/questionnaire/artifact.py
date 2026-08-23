"""Bake the questionnaire into a self-contained page, one per person.

The localhost server stays the canonical instrument. This exists because Emil asked to
answer on a phone, and it makes one structural change to do it: **one artifact per person**.

That separation is not convenience, it is `GOAL.md` Principle 8. Both partners are scored
separately and disagreement is surfaced rather than averaged away, which only means anything
if neither saw the other's answers first. With the `artifact` capability a page's markup *is*
the shared document, so a single page for both would show Winsor exactly what Emil picked.
Two pages keep them apart by construction rather than by discipline.

**Storage, in three layers, because only the first is certain.**

  1. `localStorage` — always works, private to that phone, survives a reload.
  2. The `artifact` capability — answers live in the DOM, so a tap saves them where they can
     be read back without anyone emailing a file. Whether a *shared* viewer may write is not
     something this code can determine, so it is treated as a bonus rather than a promise.
  3. `downloads` — an explicit export, which is the escape hatch if 2 turns out not to work
     for the second person.

**The trade, which is real.** Answers stored this way leave the laptop. The questionnaire was
built local-first on purpose; this is the opposite, chosen deliberately, and `make
questionnaire` still works for anyone who would rather keep it on the machine.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from wlm.questionnaire import generate
from wlm.questionnaire.session import PRACTICE, normalize_person

OUT = Path("output")


def build_page(person: str, questions: list[dict] | None = None) -> str:
    """Render the whole questionnaire as one page for one person."""
    person = normalize_person(person)
    questions = questions if questions is not None else generate.build()
    practice = person == PRACTICE
    payload = json.dumps(questions, separators=(",", ":"))

    # One empty slot per question, served as markup. The answer lives on `data-v`, set
    # inside the tap handler — a DOM change made by a gesture is what the artifact
    # capability persists; anything script does on load is not part of the document.
    slots = "".join(
        f'<i class="slot" data-q="{html.escape(q["id"])}" data-v=""></i>' for q in questions
    )

    title = "Practice Run" if practice else f"{person.title()}'s Questionnaire"
    return f"""<title>{html.escape(title)}</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Spectral:wght@400;500&display=swap">
<style>
:root {{
  --paper:#eef1f5; --card:#ffffff; --ink:#141d29; --dim:#5d6b7d; --rule:#d3dae3;
  --accent:#0d6d78; --accent-soft:#d9e8ea; --warn:#8a6c12; --bad:#9c4030;
  --display:'Archivo',system-ui,sans-serif; --read:'Spectral',Georgia,serif;
  --data:'IBM Plex Mono',ui-monospace,monospace;
  --tap:52px;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --paper:#0e141c; --card:#18212c; --ink:#e4eaf1; --dim:#8d9bad; --rule:#2a3745;
    --accent:#4fb3bd; --accent-soft:#1c3a3f; --warn:#d4b04a; --bad:#e08a76;
  }}
}}
:root[data-theme="dark"] {{
  --paper:#0e141c; --card:#18212c; --ink:#e4eaf1; --dim:#8d9bad; --rule:#2a3745;
  --accent:#4fb3bd; --accent-soft:#1c3a3f; --warn:#d4b04a; --bad:#e08a76;
}}
* {{ box-sizing:border-box; }}
body {{ background:var(--paper); color:var(--ink); margin:0;
  font:400 17px/1.55 var(--read); -webkit-text-size-adjust:100%; }}
.slot {{ display:none; }}

.bar {{ position:sticky; top:0; z-index:5; height:4px; background:var(--rule); }}
.bar i {{ display:block; height:100%; background:var(--accent); transition:width .25s ease; }}

.wrap {{ max-width:34rem; margin:0 auto; padding:18px 18px 132px; }}
.meta {{ display:flex; justify-content:space-between; align-items:center; gap:12px;
  font:600 10px/1 var(--display); letter-spacing:.13em; text-transform:uppercase;
  color:var(--dim); margin-bottom:22px; }}
.pill {{ color:var(--warn); border:1px solid var(--warn); border-radius:99px;
  padding:.42em .7em; }}
h2 {{ font:600 1.42rem/1.28 var(--display); letter-spacing:-.015em; margin:0 0 14px;
  text-wrap:balance; }}
.intro, .help {{ color:var(--dim); font-size:.93rem; margin:0 0 16px; }}
.anchor {{ font:500 .88rem var(--data); background:var(--accent-soft); color:var(--ink);
  border-left:3px solid var(--accent); padding:.7em .9em; margin:0 0 16px; }}

.opt {{ display:block; width:100%; text-align:left; min-height:var(--tap);
  background:var(--card); color:var(--ink); border:1px solid var(--rule);
  border-radius:10px; padding:14px 16px; margin:0 0 10px;
  font:400 1rem/1.4 var(--read); cursor:pointer; -webkit-tap-highlight-color:transparent; }}
.opt:active {{ transform:scale(.985); }}
.opt.sel {{ border-color:var(--accent); background:var(--accent-soft);
  box-shadow:inset 0 0 0 1px var(--accent); }}

.pair {{ display:grid; gap:12px; margin-bottom:12px; }}
@media (min-width:620px) {{ .pair {{ grid-template-columns:1fr 1fr; }} }}
.card {{ background:var(--card); border:1px solid var(--rule); border-radius:12px;
  padding:16px; cursor:pointer; -webkit-tap-highlight-color:transparent; }}
.card:active {{ transform:scale(.99); }}
.card.sel {{ border-color:var(--accent); box-shadow:inset 0 0 0 2px var(--accent); }}
.card h3 {{ font:600 10px/1 var(--display); letter-spacing:.14em; text-transform:uppercase;
  color:var(--dim); margin:0 0 12px; }}
.attr {{ display:flex; justify-content:space-between; gap:12px; align-items:baseline;
  padding:7px 0; border-bottom:1px solid var(--rule); font-size:.88rem; }}
.attr:last-child {{ border-bottom:none; }}
.attr b {{ font:500 .85rem var(--data); white-space:nowrap; }}

.row {{ display:flex; align-items:center; gap:10px; padding:9px 0;
  border-bottom:1px solid var(--rule); }}
.row label {{ flex:1; font-size:.95rem; }}
.step {{ display:flex; align-items:center; gap:2px; }}
.step button {{ width:38px; height:38px; border:1px solid var(--rule); background:var(--card);
  color:var(--ink); border-radius:8px; font:600 1.1rem var(--display); cursor:pointer;
  -webkit-tap-highlight-color:transparent; }}
.step button:active {{ background:var(--accent-soft); }}
.step output {{ width:3.2ch; text-align:center; font:500 1rem var(--data); }}
.tot {{ position:sticky; bottom:76px; background:var(--card); border:1px solid var(--rule);
  border-radius:10px; padding:10px 14px; margin-top:14px; text-align:center;
  font:500 .9rem var(--data); }}
.tot.bad {{ border-color:var(--warn); color:var(--warn); }}

textarea, input.txt {{ width:100%; min-height:var(--tap); background:var(--card);
  color:var(--ink); border:1px solid var(--rule); border-radius:10px; padding:13px 14px;
  font:400 1rem var(--read); }}
textarea {{ min-height:120px; resize:vertical; }}

.nav {{ position:fixed; left:0; right:0; bottom:0; z-index:5; background:var(--paper);
  border-top:1px solid var(--rule); padding:10px 18px calc(10px + env(safe-area-inset-bottom));
  display:flex; gap:8px; max-width:34rem; margin:0 auto; }}
.nav button {{ flex:1; min-height:var(--tap); border-radius:10px; border:1px solid var(--rule);
  background:var(--card); color:var(--ink); font:600 .95rem var(--display); cursor:pointer;
  -webkit-tap-highlight-color:transparent; }}
.nav button.go {{ background:var(--accent); border-color:var(--accent); color:#fff; flex:2; }}
:root:not([data-theme="light"]) .nav button.go {{ color:#0e141c; }}
.nav button:disabled {{ opacity:.4; }}
.done {{ text-align:center; padding:40px 0; }}
.done h2 {{ font-size:1.6rem; }}
.foot {{ margin-top:26px; text-align:center; font-size:.8rem; color:var(--dim); }}
.foot a {{ color:var(--accent); }}
:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
@media (prefers-reduced-motion:reduce) {{ * {{ transition:none !important; }} }}
</style>

<div class="bar"><i id="prog" style="width:0%"></i></div>
<div id="store" hidden>{slots}</div>
<div class="wrap"><div id="app"></div></div>
<div class="nav">
  <button id="back">Back</button>
  <button id="skip">Skip</button>
  <button class="go" id="next">Next</button>
</div>

<script>
/* Without this a phone lays the page out at 980px and scales the result down: the type goes
   unreadable and the two trade-off cards sit side by side in 248px instead of stacking.
   The head belongs to whatever wraps this page, so it is added here and only if absent. */
if (!document.querySelector('meta[name="viewport"]')) {{
  const m = document.createElement("meta");
  m.name = "viewport";
  m.content = "width=device-width, initial-scale=1, viewport-fit=cover";
  document.head.appendChild(m);
}}

const Q = {payload};
const PERSON = {json.dumps(person)};
const PRACTICE = {json.dumps(practice)};
const KEY = "wlm:" + PERSON;

const store = document.getElementById("store");
const slotOf = id => store.querySelector('.slot[data-q="' + CSS.escape(id) + '"]');

/* localStorage always works and is private to this phone. The artifact capability, when
   the viewer has it, additionally persists what a tap changes in the DOM. */
function readAnswers() {{
  const out = {{}};
  store.querySelectorAll(".slot").forEach(s => {{
    if (s.dataset.v) {{ try {{ out[s.dataset.q] = JSON.parse(s.dataset.v); }} catch (e) {{}} }}
  }});
  if (Object.keys(out).length) return out;
  try {{ return JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{ return {{}}; }}
}}

function write(id, value) {{
  const slot = slotOf(id);
  if (value === null || value === undefined || value === "" ||
      (Array.isArray(value) && !value.length) ||
      (value && typeof value === "object" && !Array.isArray(value) && !Object.keys(value).length)) {{
    if (slot) slot.dataset.v = "";              /* a blank is not an answer */
  }} else if (slot) {{
    slot.dataset.v = JSON.stringify(value);
  }}
  try {{ localStorage.setItem(KEY, JSON.stringify(readAnswers())); }} catch (e) {{}}
}}

let at = 0;
try {{ at = Math.min(parseInt(localStorage.getItem(KEY + ":at") || "0", 10) || 0, Q.length); }} catch (e) {{}}
const seek = n => {{ at = Math.max(0, Math.min(n, Q.length));
  try {{ localStorage.setItem(KEY + ":at", String(at)); }} catch (e) {{}} render(); }};

const esc = s => String(s ?? "").replace(/[&<>"]/g, c =>
  ({{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }})[c]);

let draft = null;   /* what the current screen has collected but not committed */

function render() {{
  const app = document.getElementById("app");
  const nav = document.querySelector(".nav");
  document.getElementById("prog").style.width = (100 * at / Q.length) + "%";
  draft = null;

  if (at >= Q.length) {{
    nav.style.display = "none";
    const n = Object.keys(readAnswers()).length;
    app.innerHTML = '<div class="done"><h2>Done \\u2014 thank you.</h2>' +
      '<p class="intro">' + n + ' of ' + Q.length + ' questions answered.' +
      (PRACTICE ? ' This was practice, so nothing counts.' : '') + '</p>' +
      '<button class="opt" id="export" style="text-align:center">Save my answers as a file</button>' +
      '<button class="opt" id="again" style="text-align:center">Go back through them</button></div>';
    document.getElementById("again").onclick = () => seek(0);
    document.getElementById("export").onclick = exportAnswers;
    return;
  }}
  nav.style.display = "flex";

  const q = Q[at], prev = readAnswers()[q.id];
  const sect = q.section || {{}};
  const showIntro = sect.intro && (at === 0 || (Q[at - 1].section || {{}}).id !== sect.id);
  let body = "";

  if (q.type === "choice_pair") {{
    body = '<div class="pair">' + ["a", "b"].map((k, i) =>
      '<div class="card" data-v="' + (i ? "B" : "A") + '"><h3>Place ' + (i ? "B" : "A") + '</h3>' +
      q.attributes.map(a => '<div class="attr"><span>' + esc(a.label) + '</span><b>' +
        esc(a[k]) + '</b></div>').join("") + '</div>').join("") + '</div>' +
      '<button class="opt" data-v="skip">I genuinely cannot choose</button>';
  }} else if (q.type === "budget") {{
    body = q.items.map(it => '<div class="row"><label>' + esc(it.label) + '</label>' +
      '<span class="step"><button data-d="-1" data-id="' + esc(it.id) + '">\\u2212</button>' +
      '<output data-id="' + esc(it.id) + '">0</output>' +
      '<button data-d="1" data-id="' + esc(it.id) + '">+</button></span></div>').join("") +
      '<div class="tot bad" id="tot">0 of ' + q.total + ' points</div>';
  }} else if (q.type === "rating_grid") {{
    body = q.places.map(p => '<div class="row"><label>' + esc(p.name) + '</label>' +
      '<span class="step"><button data-d="-1" data-id="' + esc(p.geo_id) + '">\\u2212</button>' +
      '<output data-id="' + esc(p.geo_id) + '">\\u2013</output>' +
      '<button data-d="1" data-id="' + esc(p.geo_id) + '">+</button></span></div>').join("") +
      '<p class="help">Leave any place you do not genuinely know at \\u2013.</p>';
  }} else if (q.type === "text") {{
    body = '<textarea id="t" placeholder="Optional"></textarea>';
  }} else if (q.type === "number") {{
    body = '<input class="txt" id="t" type="number" inputmode="numeric" placeholder="e.g. 400000">';
  }} else {{
    body = (q.options || []).map(o => '<button class="opt' +
      (q.type === "multi" ? " multi" : "") + '" data-v="' + esc(o) + '">' +
      esc(o) + '</button>').join("");
  }}

  app.innerHTML =
    '<div class="meta"><span>' + esc(sect.title || "") + ' \\u00b7 ' + (at + 1) + ' of ' + Q.length + '</span>' +
    '<span>' + (PRACTICE ? '<span class="pill">Practice</span>' : esc(PERSON)) + '</span></div>' +
    (showIntro ? '<p class="intro">' + esc(sect.intro) + '</p>' : '') +
    '<h2>' + esc(q.text) + '</h2>' +
    (q.anchor ? '<div class="anchor">' + esc(q.anchor) + '</div>' : '') +
    (q.help ? '<p class="help">' + esc(q.help) + '</p>' : '') +
    body +
    '<p class="foot">Saved on this phone as you go \\u00b7 <a href="#" id="reset">start over</a></p>';

  wire(q, prev);
  document.getElementById("back").disabled = at === 0;
  document.getElementById("next").textContent = at + 1 === Q.length ? "Finish" : "Next";
  document.getElementById("reset").onclick = e => {{
    e.preventDefault();
    if (!confirm("Discard every answer and start again?")) return;
    store.querySelectorAll(".slot").forEach(s => {{ s.dataset.v = ""; }});
    try {{ localStorage.removeItem(KEY); localStorage.removeItem(KEY + ":at"); }} catch (e2) {{}}
    seek(0);
  }};
}}

function wire(q, prev) {{
  const app = document.getElementById("app");

  if (q.type === "budget" || q.type === "rating_grid") {{
    const vals = Object.assign({{}}, prev || {{}});
    const lo = q.type === "budget" ? 0 : 1, hi = q.type === "budget" ? 100 : 10;
    const paint = () => {{
      app.querySelectorAll("output").forEach(o => {{
        const v = vals[o.dataset.id];
        o.textContent = v === undefined ? (q.type === "budget" ? "0" : "\\u2013") : v;
      }});
      const tot = document.getElementById("tot");
      if (tot) {{
        const sum = Object.values(vals).reduce((a, b) => a + b, 0);
        tot.textContent = sum + " of " + q.total + " points";
        tot.className = "tot" + (sum === q.total ? "" : " bad");
      }}
      draft = vals;
    }};
    app.querySelectorAll(".step button").forEach(b => b.onclick = () => {{
      const id = b.dataset.id, d = +b.dataset.d;
      const base = vals[id] === undefined ? (q.type === "budget" ? 0 : (d > 0 ? lo - 1 : hi + 1)) : vals[id];
      const next = base + d;
      if (next < lo) {{ delete vals[id]; }} else if (next <= hi) {{ vals[id] = next; }}
      paint();
    }});
    paint();
    return;
  }}

  if (q.type === "text" || q.type === "number") {{
    const t = document.getElementById("t");
    if (prev !== undefined) t.value = prev;
    t.oninput = () => {{ draft = t.value; }};
    draft = t.value;
    return;
  }}

  if (q.type === "multi") {{
    const picked = new Set(Array.isArray(prev) ? prev : []);
    app.querySelectorAll(".opt").forEach(el => {{
      if (picked.has(el.dataset.v)) el.classList.add("sel");
      el.onclick = () => {{
        el.classList.toggle("sel");
        picked.has(el.dataset.v) ? picked.delete(el.dataset.v) : picked.add(el.dataset.v);
        draft = [...picked];
      }};
    }});
    draft = [...picked];
    return;
  }}

  /* single-choice and trade-off pairs: one tap picks and moves on */
  const targets = app.querySelectorAll(".card, .opt");
  targets.forEach(el => {{
    if (prev !== undefined && el.dataset.v === prev) el.classList.add("sel");
    el.onclick = () => {{
      targets.forEach(x => x.classList.remove("sel"));
      el.classList.add("sel");
      write(q.id, el.dataset.v === "skip" ? null : el.dataset.v);
      setTimeout(() => seek(at + 1), 160);
    }};
  }});
}}

function commit() {{
  const q = Q[at];
  if (q.type === "budget") {{
    const sum = Object.values(draft || {{}}).reduce((a, b) => a + b, 0);
    if (sum !== q.total) {{ alert("Points must total " + q.total + " \\u2014 currently " + sum + "."); return false; }}
  }}
  write(q.id, draft);
  return true;
}}

document.getElementById("next").onclick = () => {{ if (commit()) seek(at + 1); }};
document.getElementById("back").onclick = () => seek(at - 1);
document.getElementById("skip").onclick = () => {{ write(Q[at].id, null); seek(at + 1); }};

async function exportAnswers() {{
  const blob = JSON.stringify({{ person: PERSON, practice: PRACTICE,
    answers: readAnswers(), saved_at: new Date().toISOString() }}, null, 2);
  const downloads = await (window.claude?.use?.("downloads") ?? Promise.resolve(null));
  if (downloads) {{
    try {{
      await downloads.save({{ filename: PERSON + "-answers.json", data: blob }});
      return;
    }} catch (e) {{ /* the viewer declined, or the capability refused; fall through */ }}
  }}
  /* Nothing to download to: show it so it can be copied by hand. */
  const t = document.createElement("textarea");
  t.value = blob; t.style.height = "50vh";
  document.getElementById("app").appendChild(t);
  t.select();
}}

/* Ask for the artifact capability so a tap persists beyond this phone. Null is a normal
   answer -- the page keeps working on localStorage alone. */
(async () => {{ try {{ await (window.claude?.use?.("artifact") ?? null); }} catch (e) {{}} }})();

render();
</script>"""


def write_page(person: str, *, out_dir: Path = OUT, questions=None) -> Path:
    page = build_page(person, questions)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"questionnaire-{normalize_person(person)}.html"
    path.write_text(page)
    return path


def read_answers(payload: dict | str) -> dict:
    """Turn an exported file, or a page read back, into a session answers dict."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload.get("answers", payload)


def answers_from_page(markup: str) -> dict:
    """Recover answers from a published page's own HTML.

    The answer slots are served as markup and mutated by taps, so a page read back carries
    the answers in `data-v`. This is what makes the phone route work without anyone emailing
    a file: the page *is* the record.
    """
    import re

    answers: dict = {}
    for slot in re.findall(r'<i class="slot"[^>]*>', markup):
        qid = re.search(r'data-q="([^"]*)"', slot)
        raw = re.search(r'data-v="([^"]*)"', slot)
        if not qid or not raw or not raw.group(1):
            continue
        text = html.unescape(raw.group(1))
        try:
            answers[qid.group(1)] = json.loads(text)
        except json.JSONDecodeError:
            answers[qid.group(1)] = text
    return answers


def land(person: str, answers: dict, *, sessions_dir: Path | None = None) -> Path:
    """Write recovered answers into the session file the rest of the pipeline reads.

    Practice is refused for the same reason `Session.finish` refuses it: a practice run must
    not be able to become a real profile by a different route.
    """
    from wlm.questionnaire.session import SESSIONS, Session, is_practice

    person = normalize_person(person)
    if is_practice(person):
        raise ValueError("practice answers do not become a profile - that is the point")

    session = Session.load(person, sessions_dir=sessions_dir or SESSIONS)
    session.answers.update(answers)
    session.position = len(generate.build())
    session.save()
    return session.path
