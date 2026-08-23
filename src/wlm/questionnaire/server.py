"""Local questionnaire server. Standard library only — nothing to install.

    make questionnaire PERSON=practice   # a run that cannot touch real answers
    make questionnaire PERSON=emil
    make questionnaire PERSON=emil RESET=1

Runs on http://localhost:8765 and binds to loopback only, so it is reachable from this
laptop and nowhere else. Answers are written to disk after every question and never leave
the machine.
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from wlm.questionnaire import generate
from wlm.questionnaire.session import (
    PRACTICE,
    REAL_PEOPLE,
    Session,
    SessionError,
    both_finished,
    is_practice,
    normalize_person,
)

HOST, PORT = "127.0.0.1", 8765


def read_domains() -> list[dict]:
    """Scoring domains with their weights, descriptions and lock state."""
    import yaml

    from wlm.paths import CONFIG

    data = yaml.safe_load((CONFIG / "domains.yaml").read_text())["domains"]
    return [
        {
            "id": d["id"],
            "label": d["label"],
            "description": " ".join((d.get("description") or "").split()),
            "weight": d["default_weight"],
            "locked": bool(d.get("locked")),
        }
        for d in data
        if d.get("scoring")
    ]


def save_domains(weights: dict[str, float], locked: list[str]) -> None:
    """Write adjusted weights back to config/domains.yaml.

    Edits the existing file line by line rather than re-dumping it, so every comment
    explaining why a weight is what it is survives the round trip.
    """
    import re

    from wlm.paths import CONFIG

    path = CONFIG / "domains.yaml"
    total = sum(float(v) for v in weights.values())
    if weights and abs(total - 100.0) > 0.5:
        raise ValueError(f"weights must total 100, got {total:g}")

    lines = path.read_text().split("\n")
    out, current = [], None
    for line in lines:
        m = re.match(r"^  - id: (\S+)", line)
        if m:
            current = m.group(1)
        if current in weights and re.match(r"^    default_weight:", line):
            out.append(f"    default_weight: {float(weights[current]):g}")
            continue
        if current is not None and re.match(r"^    locked:", line):
            continue  # rewritten below
        if current in weights and re.match(r"^    scoring:", line):
            out.append(line)
            if current in locked:
                out.append("    locked: true")
            continue
        out.append(line)
    path.write_text("\n".join(out))

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Where should we live?</title><style>
:root{--bg:#fbfaf8;--fg:#1c1a17;--muted:#6b6560;--line:#e2ddd6;--accent:#3d5a45;--card:#fff;--warn:#8a5a2b}
@media(prefers-color-scheme:dark){:root{--bg:#171815;--fg:#ece8e2;--muted:#a09a92;--line:#32332e;--accent:#7fa98a;--card:#1f211d;--warn:#c99a5e}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:24px 20px 80px}
.bar{height:4px;background:var(--line);border-radius:2px;overflow:hidden;margin-bottom:6px}
.bar i{display:block;height:100%;background:var(--accent);transition:width .25s}
.meta{display:flex;justify-content:space-between;color:var(--muted);font-size:13px;margin-bottom:22px}
.pill{background:var(--warn);color:#fff;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600}
h1{font-size:19px;margin:0 0 4px} h2{font-size:24px;line-height:1.3;margin:0 0 10px;font-weight:600}
.intro{color:var(--muted);margin:0 0 22px;font-size:15px}
.help{color:var(--muted);font-size:14px;margin:-2px 0 16px}
.anchor{display:inline-block;background:var(--card);border:1px solid var(--line);border-radius:6px;padding:4px 10px;font-size:14px;margin-bottom:16px}
button.opt{display:block;width:100%;text-align:left;padding:13px 15px;margin-bottom:9px;border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:9px;font:inherit;cursor:pointer}
button.opt:hover{border-color:var(--accent)} button.opt.sel{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
.card{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:14px;cursor:pointer}
.card:hover{border-color:var(--accent)} .card.sel{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent)}
.card h3{margin:0 0 10px;font-size:15px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.attr{display:flex;justify-content:space-between;gap:8px;padding:5px 0;border-top:1px solid var(--line);font-size:14px}
.attr:first-of-type{border-top:none} .attr b{font-weight:600;white-space:nowrap}
.attr span{color:var(--muted);font-size:13px}
.row{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--line)}
.row label{flex:1;font-size:15px} .row input{width:74px;padding:7px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);font:inherit}
.total{margin:14px 0;font-size:15px} .total.bad{color:var(--warn);font-weight:600}
textarea,input.txt{width:100%;padding:11px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);font:inherit}
textarea{min-height:100px;resize:vertical}
.nav{display:flex;gap:10px;margin-top:24px}
.nav button{padding:11px 20px;border-radius:8px;font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--fg)}
.nav button.go{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
.nav button:disabled{opacity:.4;cursor:not-allowed}
.foot{margin-top:34px;padding-top:14px;border-top:1px solid var(--line);color:var(--muted);font-size:13px;display:flex;justify-content:space-between}
.foot a{color:var(--muted)}
.done{text-align:center;padding:50px 0}.done h2{font-size:26px}
.cat{border:1px solid var(--line);background:var(--card);border-radius:10px;padding:14px 16px;margin-bottom:10px}
.cathead{display:flex;align-items:center;gap:12px;margin-bottom:6px}
.cathead label{flex:1;font-weight:600;font-size:16px}
.cathead input{width:64px;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--fg);font:inherit;text-align:right}
.cat p{margin:0;color:var(--muted);font-size:14px;line-height:1.5}
.lock{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:5px;white-space:nowrap}
.empty{color:var(--warn);font-weight:600;font-size:12px}
.sticky{position:sticky;bottom:0;background:var(--bg);padding:12px 0;border-top:1px solid var(--line);margin-top:16px}
</style></head><body><div class="wrap" id="app">Loading…</div>
<script>
let S=null;
const $=(h)=>{const d=document.createElement('div');d.innerHTML=h;return d.firstElementChild};
async function api(p,b){const r=await fetch(p,b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}:{});return r.json()}
async function load(){S=await api('/api/state'+location.search);
  // Fresh session opens on the categories screen; a resumed one goes straight back to work.
  if(S.screen===undefined)S.screen=(!S.done&&S.index===0)?'start':'q';
  render()}
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}

async function renderStart(){
  const app=document.getElementById('app');
  const {domains}=await api('/api/domains');
  const total=domains.reduce((a,d)=>a+(+d.weight||0),0);
  app.innerHTML=`<h1>Where should we live?</h1>
    <p class="intro">Before you start: these are the categories the ranking is built from, and
    how much each currently counts. <b>They are placeholder numbers</b> — the questionnaire
    replaces them by watching which trade-offs you actually make.</p>
    <p class="intro">Adjust one only if you want to. Tick <b>lock</b> to keep your number
    instead of the elicited one — that gets recorded in your profile so it is never mistaken
    for something you were asked.</p>
    ${domains.map(d=>`<div class="cat">
      <div class="cathead"><label for="w_${d.id}">${esc(d.label)}</label>
        <span class="lock"><input type="checkbox" id="l_${d.id}" ${d.locked?'checked':''}> lock</span>
        <input type="number" min="0" max="100" step="1" id="w_${d.id}" data-id="${d.id}" value="${d.weight}">
      </div>
      <p>${esc(d.description)}</p></div>`).join('')}
    <div class="sticky"><div class="total" id="stot">${total} of 100 allocated</div>
      <div class="nav">
        <button class="go" id="begin">Start the questionnaire</button>
        <button id="savew">Save weights</button>
      </div></div>
    <div class="foot"><span>Nothing here is sent anywhere</span></div>`;
  const stot=document.getElementById('stot');
  const recount=()=>{const s=[...app.querySelectorAll('input[type=number]')].reduce((a,x)=>a+(+x.value||0),0);
    stot.textContent=`${s} of 100 allocated`;stot.className='total'+(Math.abs(s-100)<0.5?'':' bad');return s};
  app.querySelectorAll('input[type=number]').forEach(i=>i.oninput=recount);
  document.getElementById('savew').onclick=async()=>{
    if(Math.abs(recount()-100)>0.5){alert('Weights must total 100.');return}
    const w={},l=[];
    app.querySelectorAll('input[type=number]').forEach(i=>{w[i.dataset.id]=+i.value;
      if(document.getElementById('l_'+i.dataset.id).checked)l.push(i.dataset.id)});
    const r=await api('/api/weights',{person:S.person,weights:w,locked:l});
    if(r.error){alert(r.error)}else{alert('Saved to config/domains.yaml.')}};
  document.getElementById('begin').onclick=()=>{S.screen='q';render()};
}

function render(){
  const app=document.getElementById('app');
  if(S.screen==='start'){renderStart();return}
  if(S.done){app.innerHTML=`<div class="done"><h2>Done — thank you.</h2>
    <p class="intro">${esc(S.done_message)}</p></div>`;return}
  const q=S.question,pct=Math.round(100*S.index/S.total);
  let body='';
  if(q.type==='choice_pair'){
    body=`<div class="pair">
      ${['a','b'].map((k,i)=>`<div class="card" data-v="${i?'B':'A'}"><h3>Place ${i?'B':'A'}</h3>
        ${q.attributes.map(a=>`<div class="attr"><span>${esc(a.label)}</span><b>${esc(a[k])}</b></div>`).join('')}
      </div>`).join('')}</div>
      <button class="opt" data-v="skip">Genuinely can't choose</button>`;
  } else if(q.type==='budget'){
    body=q.items.map(it=>`<div class="row"><label>${esc(it.label)}</label>
      <input type="number" min="0" max="100" value="0" data-id="${it.id}"></div>`).join('')
      +`<div class="total" id="tot">0 of ${q.total} allocated</div>`;
  } else if(q.type==='rating_grid'){
    body=q.places.map(p=>`<div class="row"><label>${esc(p.name)}</label>
      <input type="number" min="1" max="10" placeholder="—" data-id="${p.geo_id}"></div>`).join('')
      +`<div class="help">Leave blank for anywhere you don't genuinely know.</div>`;
  } else if(q.type==='text'){
    body=`<textarea id="t" placeholder="Optional"></textarea>`;
  } else if(q.type==='number'){
    body=`<input class="txt" type="number" id="t" placeholder="e.g. 400000">`;
  } else if(q.type==='multi'){
    body=q.options.map(o=>`<button class="opt multi" data-v="${esc(o)}">${esc(o)}</button>`).join('');
  } else {
    body=q.options.map(o=>`<button class="opt" data-v="${esc(o)}">${esc(o)}</button>`).join('');
  }
  app.innerHTML=`<div class="bar"><i style="width:${pct}%"></i></div>
    <div class="meta"><span>${esc(q.section.title)} · ${S.index+1} of ${S.total}</span>
      <span>${S.practice?'<span class="pill">PRACTICE</span>':esc(S.person)}</span></div>
    ${S.section_start&&q.section.intro?`<p class="intro">${esc(q.section.intro)}</p>`:''}
    <h2>${esc(q.text)}</h2>
    ${q.anchor?`<div class="anchor">${esc(q.anchor)}</div>`:''}
    ${q.help?`<p class="help">${esc(q.help)}</p>`:''}
    ${body}
    <div class="nav">
      <button id="back" ${S.index?'':'disabled'}>Back</button>
      <button class="go" id="next">${S.index+1===S.total?'Finish':'Next'}</button>
      <button id="skip">Skip</button>
    </div>
    <div class="foot"><span>Saved automatically</span>
      <span><a href="#" id="cats">Categories &amp; weights</a> &nbsp;·&nbsp;
      <a href="#" id="reset">Start over</a></span></div>`;

  let picked=null,multi=new Set();
  app.querySelectorAll('.card,.opt').forEach(el=>el.onclick=()=>{
    if(el.classList.contains('multi')){
      el.classList.toggle('sel');
      multi.has(el.dataset.v)?multi.delete(el.dataset.v):multi.add(el.dataset.v);return}
    app.querySelectorAll('.card,.opt').forEach(x=>x.classList.remove('sel'));
    el.classList.add('sel');picked=el.dataset.v;
    if(q.type!=='multi')setTimeout(()=>submit(picked),140);
  });
  const tot=document.getElementById('tot');
  if(tot)app.querySelectorAll('input[data-id]').forEach(i=>i.oninput=()=>{
    const s=[...app.querySelectorAll('input[data-id]')].reduce((a,x)=>a+(+x.value||0),0);
    tot.textContent=`${s} of ${q.total} allocated`;tot.className='total'+(s===q.total?'':' bad')});
  document.getElementById('next').onclick=()=>{
    if(q.type==='budget'||q.type==='rating_grid'){
      const o={};app.querySelectorAll('input[data-id]').forEach(i=>{if(i.value!=='')o[i.dataset.id]=+i.value});
      if(q.type==='budget'){const s=Object.values(o).reduce((a,b)=>a+b,0);
        if(s!==q.total){alert(`Points must total ${q.total} — currently ${s}.`);return}}
      submit(o);
    } else if(q.type==='text'||q.type==='number'){submit(document.getElementById('t').value)}
    else if(q.type==='multi'){submit([...multi])}
    else if(picked!==null){submit(picked)} else {alert('Pick one, or press Skip.')}};
  document.getElementById('back').onclick=async()=>{S=await api('/api/back',{person:S.person});render()};
  document.getElementById('skip').onclick=()=>submit(null);
  document.getElementById('cats').onclick=(e)=>{e.preventDefault();S.screen='start';render()};
  document.getElementById('reset').onclick=async(e)=>{e.preventDefault();
    if(confirm('Discard every answer and start again?')){S=await api('/api/reset',{person:S.person});render()}};
}
async function submit(v){S=await api('/api/answer',{person:S.person,id:S.question.id,value:v});render()}
load();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    questions: list[dict] = []
    default_person: str = PRACTICE

    def log_message(self, *args):  # keep the terminal quiet
        pass

    # ---------------------------------------------------------------- plumbing

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict, code: int = 200) -> None:
        self._send(json.dumps(payload).encode(), "application/json", code)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or "{}")

    def _person(self, requested: str | None) -> str:
        return normalize_person(requested or self.default_person)

    # ------------------------------------------------------------------ state

    def _state(self, session: Session) -> dict:
        total = len(self.questions)
        index = min(session.position, total)
        if index >= total:
            target = session.finish()
            if target:
                from wlm.profile import write_profile

                write_profile(session, self.questions, target)
                message = (
                    f"Answers written to {target.name}. "
                    + ("Both of you have finished." if both_finished()
                       else "Results stay hidden until the other one has finished too.")
                )
            else:
                message = (
                    "This was a practice run, so nothing was saved to a real profile. "
                    "Start again with PERSON=emil or PERSON=winsor when you're ready."
                )
            return {"done": True, "done_message": message, "person": session.person}

        question = self.questions[index]
        previous = self.questions[index - 1] if index else None
        return {
            "done": False,
            "person": session.person,
            "practice": is_practice(session.person),
            "index": index,
            "total": total,
            "question": question,
            "section_start": previous is None
            or previous["section"]["id"] != question["section"]["id"],
        }

    # -------------------------------------------------------------- endpoints

    def do_GET(self):  # noqa: N802
        route = urlparse(self.path)
        if route.path == "/":
            return self._send(PAGE.encode(), "text/html; charset=utf-8")
        if route.path == "/api/domains":
            return self._json({"domains": read_domains()})
        if route.path == "/api/state":
            person = self._person((parse_qs(route.query).get("person") or [None])[0])
            return self._json(self._state(Session.load(person)))
        self._send(b"not found", "text/plain", 404)

    def do_POST(self):  # noqa: N802
        route = urlparse(self.path).path
        try:
            body = self._body()
            session = Session.load(self._person(body.get("person")))
        except (SessionError, ValueError) as exc:
            return self._json({"error": str(exc)}, 400)

        if route == "/api/weights":
            try:
                save_domains(body.get("weights") or {}, body.get("locked") or [])
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            return self._json({"domains": read_domains()})

        if route == "/api/answer":
            if body.get("value") is not None:
                session.record(body["id"], body["value"])
            session.position += 1
            session.save()
        elif route == "/api/back":
            session.position = max(0, session.position - 1)
            session.save()
        elif route == "/api/reset":
            session.reset()
        else:
            return self._json({"error": "unknown endpoint"}, 404)

        return self._json(self._state(session))


def serve(person: str, *, reset: bool = False, open_browser: bool = True) -> None:
    person = normalize_person(person)
    session = Session.load(person)

    if reset:
        session.reset()
        print(f"reset: {person}'s previous answers discarded")

    Handler.questions = generate.build()
    Handler.default_person = person

    banner = "PRACTICE — nothing here can touch a real profile" if is_practice(person) else person
    print(f"\n  Questionnaire for: {banner}")
    print(f"  {len(Handler.questions)} questions · answers save automatically")
    if session.answers:
        print(f"  Resuming at question {session.position + 1}")
    print(f"\n  Open  http://{HOST}:{PORT}\n  Stop with Ctrl-C\n")

    if open_browser:
        try:
            webbrowser.open(f"http://{HOST}:{PORT}")
        except Exception:
            pass

    with ThreadingHTTPServer((HOST, PORT), Handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Stopped. Progress is saved — rerun the same command to continue.\n")


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="wlm-questionnaire")
    ap.add_argument("--person", default=PRACTICE,
                    help=f"one of {', '.join(REAL_PEOPLE)}, or '{PRACTICE}'")
    ap.add_argument("--reset", action="store_true", help="discard this person's answers first")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    try:
        serve(args.person, reset=args.reset, open_browser=not args.no_browser)
    except SessionError as exc:
        print(f"error: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv[1:]))
