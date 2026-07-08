#!/usr/bin/env python3
"""
Console controller for the Smart Robot Car (Arduino UNO R4 WiFi).

Talks to the robot over UDP (port 2390). The robot has a 300ms motor
watchdog, so if no packet arrives the car auto-stops — meaning a hold-
to-drive UX needs you to keep sending packets while a key is held.

By default this script stays on your home WiFi and only hops onto the
robot's 'RobotCar' AP for the duration of each command. Use 'stay' for
burst control (camp on the robot AP, drive at full speed, then 'home').
"""

import atexit
import socket
import subprocess
import sys
import time

WIFI_IF      = "en0"
ROBOT_SSID   = "RobotCar"
ROBOT_PASS   = "robotcar1234"
ROBOT_IP     = "192.168.4.1"
ROBOT_PORT   = 2390
SWITCH_WAIT  = 15    # association + DHCP

VALID_DIRS = {"F", "B", "L", "R", "FL", "FR", "BL", "BR", "S"}

HELP = """
Commands:
  F B L R         drive forward / back / rotate left / rotate right (~300ms pulse)
  FL FR BL BR     diagonal moves (~300ms pulse)
  S               stop
  drive D SECS    sustained motion: stream packets for SECS seconds (requires 'stay')
  speed N         set speed (0-255), persists for next moves
  stay            camp on RobotCar WiFi (fast, but no internet)
  home            return to home WiFi
  where           show current WiFi + IP
  ?               this help
  q               quit (auto-returns to home WiFi)

Note: the firmware has a 300ms motor watchdog, so single commands give a brief
pulse. For sustained motion use 'stay' then 'drive F 2' (2 seconds forward).
"""


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def current_ssid(iface=WIFI_IF):
    r = run(["networksetup", "-getairportnetwork", iface])
    out = r.stdout.strip()
    if ":" in out:
        ssid = out.split(":", 1)[1].strip()
        if ssid and "not associated" not in ssid.lower():
            return ssid
    return None


def current_ip(iface=WIFI_IF):
    return run(["ipconfig", "getifaddr", iface]).stdout.strip() or None


def switch_to(ssid, password=None, iface=WIFI_IF, timeout=SWITCH_WAIT):
    """Switch the WiFi interface to `ssid` and wait for DHCP. Returns elapsed seconds, or None on failure."""
    if current_ssid(iface) == ssid and current_ip(iface):
        return 0.0

    t0 = time.time()
    cmd = ["networksetup", "-setairportnetwork", iface, ssid]
    if password:
        cmd.append(password)
    r = run(cmd)

    # macOS prints errors to stdout. Common: "Could not find network", "Failed to join".
    bad = ("could not find" in r.stdout.lower()
           or "failed" in r.stdout.lower()
           or "error" in r.stdout.lower())
    if r.returncode != 0 or bad:
        print(f"  !! networksetup said: {r.stdout.strip() or r.stderr.strip()}")
        return None

    deadline = time.time() + timeout
    while time.time() < deadline:
        if current_ssid(iface) == ssid and current_ip(iface):
            return time.time() - t0
        time.sleep(0.25)
    return None


_udp_sock = None

def _get_sock():
    global _udp_sock
    if _udp_sock is None:
        _udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return _udp_sock


def send_udp(direction, speed):
    """Fire-and-forget UDP command. Firmware no longer acks (saves modem load).
    Failures are visible: the motor watchdog stops the car within 300ms."""
    payload = f"{direction} {speed}".encode("ascii")
    try:
        _get_sock().sendto(payload, (ROBOT_IP, ROBOT_PORT))
        return "sent", None
    except OSError as e:
        return None, f"{type(e).__name__}: {e}"


class State:
    def __init__(self, home_ssid):
        self.home_ssid = home_ssid
        self.speed = 200
        self.camped = False  # True = stay on RobotCar across commands


def drive(state, direction):
    need_switch = not state.camped

    if need_switch:
        print(f"  -> switching to {ROBOT_SSID}...")
        ts = switch_to(ROBOT_SSID, ROBOT_PASS)
        if ts is None:
            print("  !! could not join RobotCar — is the robot powered on and in range?")
            return
    else:
        ts = 0.0

    t1 = time.time()
    ack, err = send_udp(direction, state.speed)
    t2 = time.time()
    if err:
        print(f"  sent {direction} (speed {state.speed}) -> {err}")
    else:
        print(f"  sent {direction} (speed {state.speed}) -> {ack}")

    if need_switch:
        if state.home_ssid:
            print(f"  -> switching back to {state.home_ssid}...")
            tb = switch_to(state.home_ssid)
            if tb is None:
                print("  !! could not rejoin home WiFi — reconnect manually")
                tb = 0.0
        else:
            tb = 0.0
            print("  (no home SSID known; staying on RobotCar)")
        print(f"  timing: out={ts:.1f}s send={t2-t1:.2f}s back={tb:.1f}s total={ts+(t2-t1)+tb:.1f}s")
    else:
        print(f"  timing: send={t2-t1:.2f}s")


def main() -> int:
    home = current_ssid()
    if home == ROBOT_SSID:
        print(f"Already on '{ROBOT_SSID}' — running in stay mode (no switching).")
        state = State(home_ssid=None)
        state.camped = True
    elif home:
        print(f"Home WiFi detected: {home}")
        print(f"Each command will hop to '{ROBOT_SSID}' and back. Use 'stay' for burst control.")
        state = State(home_ssid=home)
    else:
        # No home WiFi — try joining the robot AP directly.
        print(f"No WiFi detected. Trying to connect to '{ROBOT_SSID}'...")
        ts = switch_to(ROBOT_SSID, ROBOT_PASS)
        if ts is None:
            print(f"  !! Could not join '{ROBOT_SSID}'. Make sure the robot is powered on and in range.")
            print(f"  Tip: you can also connect manually in System Settings > WiFi, then re-run this script.")
            return 1
        print(f"  Connected to '{ROBOT_SSID}' ({ts:.1f}s). Running in stay mode.")
        state = State(home_ssid=None)
        state.camped = True

    print("Type ? for help, q to quit.")

    def cleanup():
        if state.camped and state.home_ssid:
            print(f"\n[exit] returning to {state.home_ssid}...")
            switch_to(state.home_ssid)
    atexit.register(cleanup)

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ("q", "quit", "exit"):
            break
        if cmd in ("?", "help", "h"):
            print(HELP)
            continue
        if cmd == "where":
            print(f"  WiFi: {current_ssid()}   IP: {current_ip()}   camped: {state.camped}")
            continue
        if cmd == "speed":
            if len(parts) != 2 or not parts[1].isdigit():
                print("  usage: speed N  (0-255)")
                continue
            v = int(parts[1])
            if not 0 <= v <= 255:
                print("  speed must be 0-255")
                continue
            state.speed = v
            print(f"  speed = {state.speed}")
            continue
        if cmd == "stay":
            if state.camped:
                print("  already camped on RobotCar.")
                continue
            print(f"  -> switching to {ROBOT_SSID}...")
            ts = switch_to(ROBOT_SSID, ROBOT_PASS)
            if ts is None:
                print("  !! switch failed")
                continue
            state.camped = True
            print(f"  camped on {ROBOT_SSID} ({ts:.1f}s). No internet until you 'home'.")
            continue
        if cmd == "drive":
            if len(parts) != 3:
                print("  usage: drive <DIR> <SECS>   e.g. drive F 2")
                continue
            d = parts[1].upper()
            if d not in VALID_DIRS or d == "S":
                print(f"  bad direction: {parts[1]!r}")
                continue
            try:
                secs = float(parts[2])
            except ValueError:
                print("  SECS must be a number")
                continue
            if not 0 < secs <= 30:
                print("  SECS must be between 0 and 30")
                continue
            if not state.camped:
                print("  'drive' requires stay mode — run 'stay' first.")
                continue
            print(f"  driving {d} for {secs:.1f}s @ speed {state.speed}...")
            t_end = time.time() + secs
            sent = 0
            while time.time() < t_end:
                send_udp(d, state.speed)
                sent += 1
                time.sleep(0.2)  # 5 Hz keep-alive (well under the 300ms watchdog)
            send_udp("S", 0)  # explicit stop at end
            print(f"  done ({sent} packets sent, motors stopped).")
            continue
        if cmd == "home":
            if not state.camped:
                print("  already on home WiFi.")
                continue
            if not state.home_ssid:
                print("  no home SSID was recorded; reconnect manually.")
                continue
            print(f"  -> switching back to {state.home_ssid}...")
            tb = switch_to(state.home_ssid)
            if tb is None:
                print("  !! switch failed")
                continue
            state.camped = False
            print(f"  back on {state.home_ssid} ({tb:.1f}s).")
            continue

        d = parts[0].upper()
        if d in VALID_DIRS:
            drive(state, d)
            continue

        print(f"  unknown: {parts[0]!r} (try ?)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
