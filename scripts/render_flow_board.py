#!/usr/bin/env python3
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path('/u01/app/agent_monitor')
STATUS_PATH = ROOT / 'docs' / 'flow_test_status.json'
OUT_PATH = ROOT / 'docs' / 'flow_test_board.html'


VALID = {'pending', 'running', 'passed', 'failed', 'manual_verify', 'skipped'}


def cls(status: str) -> str:
    return status if status in VALID else 'pending'


def step_html(step: dict) -> str:
    title = f"{step.get('id', '').upper()} — {step.get('label', '')}"
    detail = step.get('detail', '')
    return f'''<div class="step {cls(step.get('status','pending'))}">
      <div class="dot"></div>
      <div>
        <div class="step-title">{html.escape(title)}</div>
        <div class="detail">{html.escape(detail)}</div>
      </div>
    </div>'''


def render() -> None:
    data = json.loads(STATUS_PATH.read_text())
    env = data.get('environment', {})
    notes = data.get('notes', [])
    tracks = data.get('tracks', [])

    endpoints_html = ''.join(
        f'<div class="endpoint"><small>{html.escape(k)}</small><code>{html.escape(str(v))}</code></div>'
        for k, v in env.items()
    )
    notes_html = ''.join(f'<li>{html.escape(str(n))}</li>' for n in notes)
    tracks_html = ''.join(
        f'<div class="card track"><h3>{html.escape(t.get("name", t.get("id", "Track")))}</h3><div class="steps">'
        + ''.join(step_html(s) for s in t.get('steps', []))
        + '</div></div>'
        for t in tracks
    )

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
    .wrap {{ max-width:1600px; margin:0 auto; padding:28px; }}
    .hero,.card {{ background:rgba(15,23,42,.92); border:1px solid var(--border); border-radius:20px; box-shadow:var(--shadow); }}
    .hero {{ padding:24px; margin-bottom:20px; }}
    .eyebrow {{ color:var(--cyan); text-transform:uppercase; letter-spacing:.14em; font-size:12px; }}
    h1 {{ margin:8px 0 10px; font-size:34px; }}
    .sub {{ color:var(--muted); max-width:980px; line-height:1.6; }}
    .meta {{ display:flex; gap:12px; flex-wrap:wrap; margin-top:14px; }}
    .pill {{ border:1px solid var(--border); border-radius:999px; padding:8px 12px; color:var(--muted); background:rgba(2,6,23,.6); }}
    .grid {{ display:grid; grid-template-columns:330px 1fr; gap:20px; }}
    .stack {{ display:grid; gap:20px; }}
    .card {{ padding:18px; }}
    .card h2, .card h3 {{ margin:0 0 14px; }}
    .endpoint {{ padding:10px 12px; border:1px solid var(--border); border-radius:12px; background:rgba(2,6,23,.45); margin-bottom:10px; }}
    .endpoint small {{ display:block; color:var(--muted); margin-bottom:4px; }}
    .endpoint code {{ color:#c7d2fe; font-size:12px; word-break:break-all; }}
    .steps {{ display:grid; gap:10px; }}
    .step {{ border:1px solid var(--border); border-radius:14px; padding:12px 14px; background:rgba(2,6,23,.55); display:grid; grid-template-columns:18px 1fr; gap:12px; align-items:start; }}
    .dot {{ width:14px; height:14px; border-radius:50%; background:var(--pending); margin-top:2px; }}
    .step.running .dot {{ background:var(--running); box-shadow:0 0 18px rgba(56,189,248,.9); }}
    .step.passed .dot {{ background:var(--passed); box-shadow:0 0 14px rgba(34,197,94,.75); }}
    .step.failed .dot {{ background:var(--failed); box-shadow:0 0 14px rgba(239,68,68,.75); }}
    .step.manual_verify .dot {{ background:var(--manual); box-shadow:0 0 14px rgba(245,158,11,.75); }}
    .step.skipped .dot {{ background:#64748b; }}
    .step-title {{ font-weight:700; }}
    .detail {{ color:var(--muted); font-size:13px; margin-top:4px; white-space:pre-wrap; }}
    .legend {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:12px; }}
    .legend span {{ display:flex; align-items:center; gap:8px; color:var(--muted); font-size:13px; }}
    .legend i {{ width:11px; height:11px; border-radius:50%; display:inline-block; }}
    ul.notes {{ margin:0; padding-left:18px; color:var(--muted); line-height:1.6; }}
    .footer-note {{ color:var(--muted); font-size:12px; margin-top:14px; }}
    @media (max-width:1180px) {{ .grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="eyebrow">Live Demo Board</div>
      <h1>{html.escape(data.get('title', 'Agent Monitor Flow Test'))}</h1>
      <div class="sub">Realtime board for practical demo flows: preflight, inbound OEM-like scenarios, and reverse Google Chat command/audit scenarios.</div>
      <div class="meta">
        <div class="pill">Updated: {html.escape(str(data.get('updated_at') or 'waiting'))}</div>
        <div class="pill">Forward flow: OEM -> Agent -> Dashboard/Audit -> Gateway</div>
        <div class="pill">Reverse flow: Google Chat -> Gateway -> Agent -> Audit</div>
      </div>
    </section>
    <section class="grid">
      <div class="stack">
        <div class="card"><h2>Runtime Endpoints</h2>{endpoints_html}</div>
        <div class="card"><h2>Notes / Caveats</h2><ul class="notes">{notes_html}</ul></div>
        <div class="card"><h2>Status Legend</h2><div class="legend"><span><i style="background:#475569"></i> Pending</span><span><i style="background:#38bdf8"></i> Running</span><span><i style="background:#22c55e"></i> Passed</span><span><i style="background:#ef4444"></i> Failed</span><span><i style="background:#f59e0b"></i> Manual verify</span><span><i style="background:#64748b"></i> Skipped</span></div><div class="footer-note">Runner: scripts/run_demo_flows.py</div></div>
      </div>
      <div class="stack">{tracks_html}</div>
    </section>
  </div>
</body>
</html>'''
    OUT_PATH.write_text(html_doc)
    print(OUT_PATH)


if __name__ == '__main__':
    render()
