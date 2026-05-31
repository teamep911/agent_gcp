#!/usr/bin/env python3
from __future__ import annotations
import hashlib, hmac, json, sys, urllib.request
from pathlib import Path
ROOT = Path('/u01/app/agent_monitor')
ENV = ROOT / '.env.runtime'

def load_env():
    env={}
    for line in ENV.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1); env[k.strip()]=v.strip().strip('"').strip("'")
    return env

payload_path=Path(sys.argv[1])
payload=json.loads(payload_path.read_text())
body=json.dumps(payload,separators=(',',':')).encode()
env=load_env()
secret=env['AGENT_WEBHOOK_SECRET']
url='http://127.0.0.1:2020/webhook/oem'
req=urllib.request.Request(url, data=body, method='POST', headers={'Content-Type':'application/json','X-Signature':hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()})
with urllib.request.urlopen(req, timeout=90) as resp:
    print(resp.getcode(), resp.read().decode())
