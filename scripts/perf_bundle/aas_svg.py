#!/usr/bin/env python3
import csv, os, math, html, argparse
from datetime import datetime, timedelta

ORDER = ["CPU","User I/O","System I/O","Concurrency","Application","Administrative","Commit","Network","Cluster","Other"]
COLORS = {
  "CPU":"#7FC97F","User I/O":"#1F77B4","System I/O":"#9ED0FF","Concurrency":"#8C6BB1",
  "Application":"#FF7F0E","Administrative":"#F2B447","Commit":"#FFD54F",
  "Network":"#76D7C4","Cluster":"#F39CBD","Other":"#E377C2",
}

def args_():
    ap = argparse.ArgumentParser()
    ap.add_argument('-i','--input', required=True)
    ap.add_argument('-o','--output', required=True)
    ap.add_argument('--max-cpu', type=float, default=0)
    ap.add_argument('--title', default='Average Active Sessions')
    return ap.parse_args()


def parse_ts(s):
    try:
        return datetime.strptime(s[:19], '%Y-%m-%d %H:%M:%S')
    except Exception:
        return None


def load_rows(path):
    agg = {}
    with open(path, newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            ts = (row.get('timestamp') or '').strip()
            if not ts:
                continue
            if ts not in agg:
                agg[ts] = {k:0.0 for k in ORDER}
                agg[ts]['_ts'] = ts
                agg[ts]['_dt'] = parse_ts(ts)
            for k in ORDER:
                try: agg[ts][k] += float(row.get(k,0) or 0)
                except: pass
    rows = [agg[k] for k in sorted(agg, key=lambda x: (agg[x]['_dt'] is None, agg[x]['_dt'], x))]
    if not rows:
        return []
    if len(rows) < 30:
        step = 20
        anchor = rows[0]['_dt'] or datetime.utcnow()
        pads = []
        for i in range(30-len(rows),0,-1):
            dt = anchor - timedelta(seconds=i*step)
            z = {k:0.0 for k in ORDER}
            z['_ts'] = dt.strftime('%Y-%m-%d %H:%M:%S')
            z['_dt'] = dt
            pads.append(z)
        rows = pads + rows
    return rows


def nice(v):
    if v <= 0: return 1.0
    e = math.floor(math.log10(v))
    for m in (1,2,4,5,8,10):
        x = m * (10**e)
        if x >= v: return x
    return 10**(e+1)


def main():
    a = args_()
    rows = load_rows(a.input)
    if not rows:
        open(a.output,'w').write('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="300"><text x="20" y="40">No ASH data</text></svg>')
        return

    W,H = 1400,520
    PAD_L,PAD_R,PAD_T,PAD_B = 80,220,56,80
    plotW, plotH = W-PAD_L-PAD_R, H-PAD_T-PAD_B
    totals = [sum(r[k] for k in ORDER) for r in rows]
    ymax = nice(max(max(totals), a.max_cpu or 0)*1.05)
    n = len(rows)
    delta = plotW / n
    barW = max(1, delta)
    def y_of(v): return PAD_T + plotH*(1-v/(ymax if ymax else 1))
    def x_of(i): return PAD_L + i*delta

    out=[]
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    out.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="#ffffff"/>')
    out.append(f'<text x="{PAD_L}" y="38" font-family="sans-serif" font-size="18" fill="#222">{html.escape(a.title)}</text>')
    out.append(f'<text x="{PAD_L}" y="54" font-family="sans-serif" font-size="12" fill="#666">ASH Dimensions: Wait Class | DB flex/FLEXING</text>')
    out.append(f'<rect x="{PAD_L}" y="{PAD_T}" width="{plotW}" height="{plotH}" fill="#fff" stroke="#ddd"/>')

    for i in range(7):
        val = i*ymax/6
        y = y_of(val)
        out.append(f'<line x1="{PAD_L}" y1="{y:.2f}" x2="{PAD_L+plotW}" y2="{y:.2f}" stroke="#eee"/>')
        out.append(f'<text x="{PAD_L-10}" y="{y+4:.2f}" text-anchor="end" font-family="sans-serif" font-size="12" fill="#444">{val:.0f}</text>')

    if a.max_cpu > 0:
        y = y_of(a.max_cpu)
        out.append(f'<line x1="{PAD_L}" y1="{y:.2f}" x2="{PAD_L+plotW}" y2="{y:.2f}" stroke="#a16207" stroke-width="2"/>')
        out.append(f'<text x="{PAD_L+plotW+8}" y="{y+4:.2f}" font-family="sans-serif" font-size="12" fill="#a16207">Max CPU {a.max_cpu:.0f} cores</text>')

    label_every = max(1, round(n/14))
    for j in range(n+1):
        x = PAD_L + j*delta
        out.append(f'<line x1="{x:.2f}" y1="{PAD_T}" x2="{x:.2f}" y2="{PAD_T+plotH}" stroke="#f0f0f0"/>')
    for j in range(0, n, label_every):
        x = x_of(j) + delta/2
        ts = rows[j]['_ts'][11:19]
        out.append(f'<text x="{x:.2f}" y="{PAD_T+plotH+16}" text-anchor="middle" font-family="sans-serif" font-size="11" fill="#444">{ts}</text>')

    for i, r in enumerate(rows):
        x = x_of(i)
        acc = 0.0
        total = totals[i]
        for k in ORDER:
            v = r[k]
            if v <= 0: continue
            y0,y1 = y_of(acc+v), y_of(acc)
            h=max(0.4,y1-y0)
            tip=f'{k}: {v:.2f} | total {total:.2f} @ {r["_ts"]}'
            out.append(f'<rect x="{x:.2f}" y="{y0:.2f}" width="{barW:.2f}" height="{h:.2f}" fill="{COLORS[k]}" stroke="#fff" stroke-width="0.5"><title>{html.escape(tip)}</title></rect>')
            acc += v

    lx,ly = W-PAD_R+20, PAD_T+6
    out.append(f'<text x="{lx}" y="{PAD_T-10}" font-family="sans-serif" font-size="12" fill="#666">Display</text>')
    for k in ORDER[::-1]:
        out.append(f'<rect x="{lx}" y="{ly}" width="14" height="14" fill="{COLORS[k]}" stroke="#ccc"/>')
        out.append(f'<text x="{lx+22}" y="{ly+12}" font-family="sans-serif" font-size="12" fill="#333">{html.escape(k)}</text>')
        ly += 20
    out.append(f'<text x="{PAD_L}" y="{H-6}" font-family="sans-serif" font-size="12" fill="#666">{rows[0]["_ts"][:10]}</text>')
    out.append('</svg>')
    with open(a.output,'w',encoding='utf-8') as f:
        f.write('\n'.join(out))

if __name__ == '__main__':
    main()
