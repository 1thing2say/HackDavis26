# Legacy / archived

These files are from an earlier iteration and are **not part of the working
setup**. They're kept for reference only. The maintained path is `robot_pi.py`
plus the `SmartRobotCarV4.0_V1_20230201working` firmware (see the top-level
README).

## `robot_web.py` and `robot_console.py`

The original laptop-based control stack. These drive the car over **UDP** to its
own `RobotCar` access point (`192.168.4.1:2390`). Because the laptop has to join
the car's AP to send those packets (losing internet in the process), they rely on
macOS-only WiFi switching (`networksetup`, `en0`) that hops between the robot AP
and your home network for each command. This is slow (~15s per association) and
does not work on Linux or Windows.

They also contain the robot AP's hardcoded password. Treat them as insecure and
unmaintained.

## `Uno_R4_WiFi_Camera_Bridge/`

A camera-only firmware for the Arduino R4 that only understands a bare `S`
capture trigger and ignores motor commands. It is superseded by the unified
`SmartRobotCarV4.0_V1_20230201working` firmware, which handles motors (`CMD:<DIR>
<SPEED>`), the 300 ms motor watchdog, and camera capture together.

**Do not flash this bridge if you're using `robot_pi.py`.** It won't move the
motors, and because it triggers a capture on any `S` byte, the stop command
`CMD:S 0` would fire a spurious image capture instead of stopping.
