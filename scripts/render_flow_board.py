#!/usr/bin/env python3
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path('/u01/app/agent_monitor')
STATUS_PATH = ROOT / 'docs' / 'flow_test_status.json'
OUT_PATH = ROOT / 'docs' / 'flow_test_board.html'


def cls(status: str) -> str:
    return status if status in {'pending','running','passed','failed','manual_verify'} else 'pending'


def step_html(step: dict) -> str:
    return f'''<div class="step {cls(step.get('status','pending'))}" data-step="{html.escape(step.get('id',''))}">
      <div class="dot"></div>
      <div><div class="step-title">{html.escape(step.get('id','').upper())} — {html.escape(step.get('label',''))}</div>
      <div class="detail">{html.escape(step.get('detail',''))}</div></div>
    </div>'''


def render() -> None:
    data = json.loads(STATUS_PATH.read_text())
    env = data.get('environment', {})
    notes = data.get('notes', [])
    tracks = {t['id']: t for t in data.get('tracks', [])}
    track_a = tracks.get('track_a', {'steps': []})
    track_b = tracks.get('track_b', {'steps': []})
    active = {s['id'] for t in data.get('tracks', []) for s in t.get('steps', []) if s.get('status') == 'running'}

    endpoints_html = ''.join(
        f'<div class="endpoint"><small>{html.escape(k)}</small><code>{html.escape(str(v))}</code></div>'
        for k, v in env.items()
    )
    notes_html = ''.join(f'<li>{html.escape(str(n))}</li>' for n in notes)
    track_a_html = ''.join(step_html(s) for s in track_a.get('steps', []))
    track_b_html = ''.join(step_html(s) for s in track_b.get('steps', []))

    def active_cls(step_id: str) -> str:
        return ' active' if step_id in active else ''

    html_doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Agent Monitor Flow Test Board</title>
  <style>
    :root {{ --bg:#020617; --panel:#0f172a; --text:#e5eefb; --muted:#94a3b8; --border:#1e293b; --cyan:#22d3ee; --emerald:#34d399; --amber:#fbbf24; --running:#38bdf8; --pending:#475569; --passed:#22c55e; --failed:#ef4444; --manual:#f59e0b; --shadow:0 10px 40px rgba(0,0,0,.35); }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif; color:var(--text); background:linear-gradient(rgba(2,6,23,.96),rgba(2,6,23,.96)),linear-gradient(#1e293b 1px,transparent 1px),linear-gradient(90deg,#1e293b 1px,transparent 1px); background-size:auto,32px 32px,32px 32px; min-height:100vh; }}
    .wrap {{ max-width:1500px; margin:0 auto; padding:28px; }}
    .hero,.card {{ background:rgba(15,23,42,.92); border:1px solid var(--border); border-radius:20px; box-shadow:var(--shadow); }}
    .hero {{ padding:24px; margin-bottom:20px; }} .eyebrow {{ color:var(--cyan); text-transform:uppercase; letter-spacing:.14em; font-size:12px; }} h1 {{ margin:8px 0 10px; font-size:34px; }} .sub {{ color:var(--muted); max-width:900px; line-height:1.6; }}
    .meta {{ display:flex; gap:12px; flex-wrap:wrap; margin-top:14px; }} .pill {{ border:1px solid var(--border); border-radius:999px; padding:8px 12px; color:var(--muted); background:rgba(2,6,23,.6); }}
    .grid {{ display:grid; grid-template-columns:330px 1fr; gap:20px; }} .stack {{ display:grid; gap:20px; }} .card {{ padding:18px; }} .card h2 {{ margin:0 0 14px; font-size:18px; }}
    .endpoint {{ padding:10px 12px; border:1px solid var(--border); border-radius:12px; background:rgba(2,6,23,.45); margin-bottom:10px; }} .endpoint small {{ display:block; color:var(--muted); margin-bottom:4px; }} .endpoint code {{ color:#c7d2fe; font-size:12px; word-break:break-all; }}
    .flow {{ display:grid; grid-template-columns:repeat(7,minmax(110px,1fr)); gap:12px; align-items:center; margin-bottom:20px; }}
    .node {{ min-height:92px; padding:12px; border:1px solid var(--border); border-radius:16px; background:linear-gradient(180deg,rgba(15,23,42,.98),rgba(15,23,42,.72)); display:flex; flex-direction:column; justify-content:center; text-align:center; position:relative; overflow:hidden; }}
    .node::after {{ content:""; position:absolute; inset:-30%; opacity:0; background:radial-gradient(circle,currentColor 0%,transparent 58%); transition:opacity .25s ease; }} .node.active::after {{ opacity:.18; }} .node small {{ color:var(--muted); font-size:12px; }} .node strong {{ font-size:14px; margin-top:6px; }}
    .frontend {{ color:var(--cyan); }} .backend {{ color:var(--emerald); }} .external {{ color:#cbd5e1; }} .gateway {{ color:var(--amber); }} .db {{ color:#a78bfa; }}
    .arrow {{ height:2px; background:linear-gradient(90deg,transparent,#334155,transparent); position:relative; }} .arrow::after {{ content:""; position:absolute; right:0; top:-4px; border-left:8px solid #475569; border-top:5px solid transparent; border-bottom:5px solid transparent; }}
    .track {{ margin-top:18px; }} .track h3 {{ margin:0 0 12px; font-size:16px; color:#dbeafe; }} .steps {{ display:grid; gap:10px; }}
    .step {{ border:1px solid var(--border); border-radius:14px; padding:12px 14px; background:rgba(2,6,23,.55); display:grid; grid-template-columns:18px 1fr; gap:12px; align-items:start; }}
    .dot {{ width:14px; height:14px; border-radius:50%; background:var(--pending); margin-top:2px; }} .step.running .dot {{ background:var(--running); box-shadow:0 0 18px rgba(56,189,248,.9); }} .step.passed .dot {{ background:var(--passed); box-shadow:0 0 14px rgba(34,197,94,.75); }} .step.failed .dot {{ background:var(--failed); box-shadow:0 0 14px rgba(239,68,68,.75); }} .step.manual_verify .dot {{ background:var(--manual); box-shadow:0 0 14px rgba(245,158,11,.75); }}
    .step-title {{ font-weight:700; }} .detail {{ color:var(--muted); font-size:13px; margin-top:4px; white-space:pre-wrap; }} .legend {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }} .legend span {{ display:flex; align-items:center; gap:8px; color:var(--muted); font-size:13px; }} .legend i {{ width:11px; height:11px; border-radius:50%; display:inline-block; }} ul.notes {{ margin:0; padding-left:18px; color:var(--muted); line-height:1.6; }} .footer-note {{ color:var(--muted); font-size:12px; margin-top:14px; }}
    @media (max-width:1180px) {{ .grid {{ grid-template-columns:1fr; }} .flow {{ grid-template-columns:1fr; }} .arrow {{ height:24px; width:2px; margin:0 auto; }} .arrow::after {{ right:-4px; top:auto; bottom:0; border-left:5px solid transparent; border-right:5px solid transparent; border-top:8px solid #475569; border-bottom:0; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero"><div class="eyebrow">Live Test Board</div><h1>{html.escape(data.get('title','Agent Monitor End-to-End Flow Test'))}</h1><div class="sub">This board shows where the current test run is, which checkpoint passed/failed, and what still needs manual verification.</div><div class="meta"><div class="pill">Updated: {html.escape(str(data.get('updated_at') or 'waiting for first run'))}</div><div class="pill">Fallback path: public IP 118.69.205.10:2222</div><div class="pill">Preferred final path: gcp.leevo.top</div></div></section>
    <section class="grid"><div class="stack"><div class="card"><h2>Runtime Endpoints</h2>{endpoints_html}</div><div class="card"><h2>Notes / Blockers</h2><ul class="notes">{notes_html}</ul></div><div class="card"><h2>Status Legend</h2><div class="legend"><span><i style="background:#475569"></i> Pending</span><span><i style="background:#38bdf8"></i> Running</span><span><i style="background:#22c55e"></i> Passed</span><span><i style="background:#ef4444"></i> Failed</span><span><i style="background:#f59e0b"></i> Manual verify</span></div><div class="footer-note">Run <code>scripts/run_flow_tests.py</code> to refresh this board.</div></div></div>
    <div class="stack"><div class="card"><h2>Flow Map</h2><div class="flow"><div class="node external{active_cls('a3')}"><small>Source</small><strong>OEM Event</strong></div><div class="arrow"></div><div class="node backend{active_cls('a4')}"><small>openclaw</small><strong>Agent 2020</strong></div><div class="arrow"></div><div class="node db{active_cls('a4')}"><small>storage</small><strong>Incident DB</strong></div><div class="arrow"></div><div class="node gateway{active_cls('a6')}"><small>gcp</small><strong>Gateway 2222</strong></div></div><div class="flow"><div class="node external{active_cls('b2')}"><small>Source</small><strong>Google Chat Event</strong></div><div class="arrow"></div><div class="node gateway{active_cls('b3')}"><small>gcp</small><strong>Gateway 2222</strong></div><div class="arrow"></div><div class="node backend{active_cls('b5')}"><small>openclaw</small><strong>Agent 2020</strong></div><div class="arrow"></div><div class="node frontend{active_cls('b5')}"><small>response</small><strong>job_id Accepted</strong></div></div></div>
    <div class="card track"><h3>Track A — OEM -> Agent -> Gateway -> Google Chat</h3><div class="steps">{track_a_html}</div></div><div class="card track"><h3>Track B — Google Chat -> Gateway -> Agent</h3><div class="steps">{track_b_html}</div></div></div></section>
  </div>
</body>
</html>'''
    OUT_PATH.write_text(html_doc)
    print(OUT_PATH)


if __name__ == '__main__':
    render()
