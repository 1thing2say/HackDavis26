#!/usr/bin/env python3
"""
Web UI for the Smart Robot Car (Arduino UNO R4 WiFi).

Runs a small HTTP server on your laptop. Open the page in your browser
and hold buttons (or use WASD / arrow keys) to drive. The server forwards
each button press as a UDP packet to the robot on 192.168.4.1:2390.

Usage:
    python3 robot_web.py
    # then open http://localhost:8765/

You must be on the RobotCar WiFi network for the UDP packets to reach
the robot. The page has a 'Stay'/'Home' button that switches your laptop's
WiFi between RobotCar and your home network.
"""

import atexit
import http.server
import json
import socket
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse

WIFI_IF      = "en0"
ROBOT_SSID   = "RobotCar"
ROBOT_PASS   = "robotcar1234"
ROBOT_IP     = "192.168.4.1"
ROBOT_PORT   = 2390
HTTP_PORT    = 8765
SWITCH_WAIT  = 15

VALID_DIRS = {"F", "B", "L", "R", "FL", "FR", "BL", "BR", "S"}


# ---------- WiFi helpers (same logic as robot_console.py) ----------

def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def current_ssid(iface=WIFI_IF):
    out = _run(["networksetup", "-getairportnetwork", iface]).stdout.strip()
    if ":" in out:
        ssid = out.split(":", 1)[1].strip()
        if ssid and "not associated" not in ssid.lower():
            return ssid
    return None


def current_ip(iface=WIFI_IF):
    return _run(["ipconfig", "getifaddr", iface]).stdout.strip() or None


def switch_to(ssid, password=None, iface=WIFI_IF, timeout=SWITCH_WAIT):
    if current_ssid(iface) == ssid and current_ip(iface):
        return 0.0
    t0 = time.time()
    cmd = ["networksetup", "-setairportnetwork", iface, ssid]
    if password:
        cmd.append(password)
    r = _run(cmd)
    bad = ("could not find" in r.stdout.lower()
           or "failed" in r.stdout.lower()
           or "error" in r.stdout.lower())
    if r.returncode != 0 or bad:
        return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        if current_ssid(iface) == ssid and current_ip(iface):
            return time.time() - t0
        time.sleep(0.25)
    return None


# ---------- UDP send ----------

_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def send_udp(direction, speed):
    payload = f"{direction} {speed}".encode("ascii")
    try:
        _udp_sock.sendto(payload, (ROBOT_IP, ROBOT_PORT))
        return True
    except OSError:
        return False


# ---------- State ----------

class State:
    def __init__(self):
        ssid = current_ssid()
        self.home_ssid = ssid if ssid and ssid != ROBOT_SSID else None
        self.camped = ssid == ROBOT_SSID


# ---------- HTML page (single-file) ----------

INDEX_HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Robot Car</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{font-family:system-ui,sans-serif;background:#1b1b1b;color:#eee;margin:0;padding:18px;text-align:center;user-select:none;-webkit-user-select:none;-webkit-touch-callout:none}
h2{margin:6px 0 14px}
.bar{display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:18px;flex-wrap:wrap}
.pill{padding:6px 12px;border-radius:99px;background:#2a2a2a;font-size:14px}
.pill.on{background:#0a8f5a}
button.tog{padding:8px 14px;border-radius:10px;border:0;background:#3a3a3a;color:#eee;font-weight:600;cursor:pointer;font-size:14px}
button.tog:disabled{opacity:.5}
.pad{display:grid;grid-template-columns:repeat(3,96px);grid-template-rows:repeat(3,96px);gap:10px;justify-content:center}
.pad button{font-size:30px;font-weight:600;border-radius:16px;border:0;background:#3a3a3a;color:#eee;touch-action:none;cursor:pointer}
.pad button.on{background:#0a8f5a}
.stop{background:#a23030 !important;font-size:18px !important}
.stop.on{background:#d04040 !important}
.sp{margin-top:18px}
.sp input{width:min(80%,360px)}
.sv{font-size:18px;margin-top:6px}
.hint{margin-top:14px;font-size:13px;color:#888}
</style>
</head>
<body>
  <h2>Robot Car</h2>
  <div class="bar">
    <span id="wifi" class="pill">…</span>
    <button class="tog" id="tog">Stay</button>
  </div>
  <div class="pad">
    <button data-d="FL">↖</button>
    <button data-d="F">↑</button>
    <button data-d="FR">↗</button>
    <button data-d="L">←</button>
    <button data-d="S" class="stop">STOP</button>
    <button data-d="R">→</button>
    <button data-d="BL">↙</button>
    <button data-d="B">↓</button>
    <button data-d="BR">↘</button>
  </div>
  <div class="sp"><input type="range" min="80" max="255" value="200" id="sp"></div>
  <div class="sv">Speed: <span id="sv">200</span></div>
  <div class="hint">Hold to drive. Keys: W/A/S/D or arrows, Space = STOP.</div>
<script>
const sp=document.getElementById('sp'),sv=document.getElementById('sv');
sp.oninput=()=>sv.textContent=sp.value;

let timer=null,curDir=null;
function send(d){fetch(`/cmd?d=${d}&s=${sp.value}`).catch(()=>{})}

function startHold(d){
  if(curDir===d) return;
  stopHold(false);
  if(d==='S'){send('S');return;}
  curDir=d;
  document.querySelector(`[data-d="${d}"]`)?.classList.add('on');
  send(d);
  timer=setInterval(()=>send(d),200);
}
function stopHold(sendStop=true){
  if(timer){clearInterval(timer);timer=null;}
  if(curDir){
    document.querySelector(`[data-d="${curDir}"]`)?.classList.remove('on');
    curDir=null;
    if(sendStop) send('S');
  }
}

for(const b of document.querySelectorAll('.pad button')){
  const d=b.dataset.d;
  if(d==='S'){b.onclick=()=>send('S');continue;}
  b.addEventListener('pointerdown',e=>{e.preventDefault();b.setPointerCapture(e.pointerId);startHold(d)});
  b.addEventListener('pointerup',e=>{e.preventDefault();stopHold()});
  b.addEventListener('pointercancel',()=>stopHold());
}

// Keyboard
const KEY={KeyW:'F',KeyS:'B',KeyA:'L',KeyD:'R',ArrowUp:'F',ArrowDown:'B',ArrowLeft:'L',ArrowRight:'R'};
document.addEventListener('keydown',e=>{
  if(e.repeat) return;
  if(e.code==='Space'){e.preventDefault();stopHold();send('S');return;}
  const d=KEY[e.code];
  if(d){e.preventDefault();startHold(d);}
});
document.addEventListener('keyup',e=>{
  const d=KEY[e.code];
  if(d&&curDir===d) stopHold();
});

// Failsafe: stop on tab leave / page hide
window.addEventListener('blur',()=>stopHold());
window.addEventListener('pagehide',()=>stopHold());
document.addEventListener('visibilitychange',()=>{if(document.hidden)stopHold()});

// WiFi status + toggle
const wifi=document.getElementById('wifi'),tog=document.getElementById('tog');
let camped=false;
async function refresh(){
  try{
    const j=await(await fetch('/status')).json();
    camped=!!j.camped;
    wifi.textContent=(j.ssid||'?')+(j.ip?' • '+j.ip:'');
    wifi.className='pill '+(camped?'on':'');
    tog.textContent=camped?'Home':'Stay';
  }catch(e){}
}
tog.onclick=async()=>{
  tog.disabled=true;
  const path=camped?'/wifi/home':'/wifi/stay';
  tog.textContent='switching…';
  try{await fetch(path);}catch(e){}
  await refresh();
  tog.disabled=false;
};
refresh();
setInterval(refresh,3000);
</script>
</body>
</html>
"""


# ---------- HTTP handler ----------

class CmdHandler(http.server.BaseHTTPRequestHandler):
    state: State = None  # type: ignore[assignment]

    def log_message(self, fmt, *args):  # quieter access log
        return

    def _send(self, code, ctype, body):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, "application/json", json.dumps(obj))

    def do_GET(self):
        url = urlparse(self.path)

        if url.path == "/":
            self._send(200, "text/html; charset=utf-8", INDEX_HTML)
            return

        if url.path == "/cmd":
            qs = parse_qs(url.query)
            d = (qs.get("d", [""])[0] or "").upper()
            try:
                s = int(qs.get("s", ["200"])[0])
            except ValueError:
                s = 200
            s = max(0, min(255, s))
            if d not in VALID_DIRS:
                self._send(400, "text/plain", "bad direction")
                return
            ok = send_udp(d, s)
            self._send(200 if ok else 502, "text/plain", "ok" if ok else "send-failed")
            return

        if url.path == "/status":
            self._json({
                "ssid": current_ssid(),
                "ip": current_ip(),
                "camped": self.state.camped,
                "home_ssid": self.state.home_ssid,
                "robot_ssid": ROBOT_SSID,
            })
            return

        if url.path == "/wifi/stay":
            ts = switch_to(ROBOT_SSID, ROBOT_PASS)
            if ts is not None:
                self.state.camped = True
            self._json({"ok": ts is not None, "elapsed": ts})
            return

        if url.path == "/wifi/home":
            if not self.state.home_ssid:
                self._json({"ok": False, "error": "no home ssid recorded"}, 400)
                return
            tb = switch_to(self.state.home_ssid)
            if tb is not None:
                self.state.camped = False
            self._json({"ok": tb is not None, "elapsed": tb})
            return

        self.send_error(404)


def main() -> int:
    state = State()
    CmdHandler.state = state

    def cleanup():
        # Best-effort STOP on shutdown so the car can't keep running.
        try:
            send_udp("S", 0)
        except Exception:
            pass
        if state.camped and state.home_ssid:
            print(f"\n[exit] returning to {state.home_ssid}...")
            switch_to(state.home_ssid)
    atexit.register(cleanup)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), CmdHandler)
    here = current_ssid() or "(none)"
    print(f"Robot web UI:  http://localhost:{HTTP_PORT}/")
    print(f"Current WiFi:  {here}   camped on RobotCar: {state.camped}")
    if not state.camped:
        print("Tip: click 'Stay' on the page to switch this laptop to the RobotCar AP.")
    print("Ctrl-C to quit.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
