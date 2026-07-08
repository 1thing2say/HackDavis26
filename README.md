# davishacks: AI Robot Car

A Raspberry Pi drives an Elegoo Smart Robot Car and streams photos from an
onboard ESP32 camera to Google Gemini, which decides where to go. You can drive
it manually from a phone/laptop browser or hand control to Gemini with a goal
like "avoid obstacles and move forward."

> This is the **hardened `fixes` branch**. See [What changed on this branch](#what-changed-on-this-branch)
> for the differences from `main`.

## How it works

The core problem: one WiFi radio cannot be on the camera's access point and the
internet at the same time. This build solves it by splitting roles across a Pi
and an Arduino, connected by USB:

```
                    USB serial (motors + JPEG frames)
   Raspberry Pi  ───────────────────────────────────▶  Arduino R4 WiFi
   (robot_pi.py)                                        (SmartRobotCar firmware)
        │                                                     │ WiFi
        │  web UI :8080                                       ▼
        │  + Gemini API                              ESP32-CAM access point
        ▼                                            (streams JPEG over HTTP)
   your phone / laptop browser
```

- The **Arduino R4** joins the ESP32-CAM's WiFi on its own radio, so it can pull
  camera frames without tying up the Pi's network.
- The **Pi** talks to the Arduino over USB serial: it sends motor commands
  (`CMD:<DIR> <SPEED>`) and a capture trigger (`S`), and receives JPEG frames
  back via a small magic-header protocol.
- The **Pi's WiFi stays free** for the internet, so it can reach Gemini and host
  the control UI. This is why you do not need to hop networks the way the old
  laptop scripts did.

The firmware runs a **300 ms motor watchdog**: if no command arrives within that
window the car stops on its own, so a dropped connection can't leave it driving.

## Hardware

- Raspberry Pi (any model with USB)
- Arduino UNO R4 WiFi
- Elegoo Smart Robot Car V4.0 chassis + motor driver
- Elegoo ESP32-CAM module (broadcasts its own WiFi AP)

## Firmware

Flash `SmartRobotCarV4.0_V1_20230201working/` to the Arduino R4 WiFi.

1. Copy `arduino_secrets.h.example` to `arduino_secrets.h` and fill in your WiFi
   credentials. `arduino_secrets.h` is gitignored so it is never committed.
2. Confirm the camera AP SSID in the sketch matches your ESP32-CAM.
3. Flash from the Arduino IDE.

## Running it (on the Pi)

```sh
source venv.sh          # creates .venv, installs deps, loads .env
python3 robot_pi.py     # auto-detects the Arduino serial port
```

Then open the printed URL. On your phone, use the LAN URL (also printed) while on
the same network as the Pi. Hold the D-pad or use WASD / arrow keys to drive;
Space or the STOP button stops. **Capture** grabs a photo; **Gemini** prompts for
a goal and hands driving to the model until you stop it.

### Configuration

Set these in `.env` (copied from `.env.example` on first run):

| Variable | Purpose |
| --- | --- |
| `GEMINI_API_KEY` | Required for the Capture-to-decision Gemini calls |
| `ROBOT_TOKEN` | Optional shared secret. If set, every request needs `?token=<value>` |

## Remote access

For a robot on your own network, just use the **LAN URL**. To reach it from
anywhere, prefer a private path such as **Tailscale**, or a **named Cloudflare
tunnel with Access** in front of it.

`cloudflared.sh` starts a quick tunnel for convenience, but a quick tunnel is
**public**: anyone with the URL can drive the robot. Only use it with
`ROBOT_TOKEN` set.

## What changed on this branch

This branch fixes the issues found in the original hackathon build.

**Security**
- Added optional `ROBOT_TOKEN` auth to the web UI. When set, every request
  (page and API) must carry the token; it is compared in constant time.
- Untracked `arduino_secrets.h` (which had committed WiFi credentials), replaced
  its contents with placeholders, added an `arduino_secrets.h.example` template,
  and gitignored the real file.
- `cloudflared.sh` now warns loudly that a quick tunnel is public and recommends
  setting `ROBOT_TOKEN`.

**Safety**
- `robot_pi.py` now uses a threaded HTTP server, and an incoming STOP aborts any
  in-flight capture so an emergency stop is never queued behind a slow (up to
  30 s) capture or Gemini call.
- Raised the default Gemini loop interval from 150 ms to 800 ms so the AI mode
  no longer hammers the API.

**Clarity / correctness**
- Moved the old laptop UDP stack (`robot_web.py`, `robot_console.py`) and the
  redundant camera-only `Uno_R4_WiFi_Camera_Bridge` firmware into `legacy/`, with
  a note explaining why they are archived (the bridge firmware silently breaks
  motor control and turns STOP into a spurious capture).

**Housekeeping**
- Captured JPEGs now go to a `captures/` folder (gitignored) and are pruned to
  the most recent 50 instead of piling up in the working directory.
- Fixed `venv.sh` to load `.env` safely (the old `export $(cat .env)` broke on
  values with spaces or quotes).
- Corrected the `google-genai` version pin in `requirements.txt`.
- Renamed `cloudfared` to `cloudflared.sh` and made it architecture-aware and
  idempotent.

### Follow-up not done here

The old WiFi credentials still exist in **git history**. To remove them fully,
rewrite history (for example with `git filter-repo`) and rotate the credentials.
This branch only stops them from being committed going forward.

## Repository layout

```
davishacks/
├── robot_pi.py          # Main: Pi web server + serial bridge + Gemini control
├── capture_image.py     # Standalone single-image capture over serial
├── SmartRobotCarV4.0.../ # Arduino R4 firmware (motors + camera + watchdog)
├── cloudflared.sh       # Optional public tunnel for the web UI (use with care)
├── venv.sh              # Dev setup: venv + deps + .env
├── requirements.txt
├── .env.example
└── legacy/              # Archived earlier stacks (see legacy/README.md)
```
