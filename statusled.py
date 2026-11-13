#!/usr/bin/env python3
"""
statusled – WS2812-Status-LEDs für Pixelflut-Video-Nodes (Raspberry Pi 4)

Daten: GPIO21 (Pin 40), PCM via rpi_ws281x – läuft als root, keine config.txt-Änderung.

LED 0  Netz:   Verbindung zu flood.c3pixelflut.de (TCP-Connect)
LED 1  Video:  Heartbeat-Datei /run/statusled/video ("ok" | "warn" | "err")
LED 2  Health: Temperatur + Unterspannung/Throttling

Locate:  touch /run/statusled/locate  -> alle LEDs blinken 60 s weiß
Rainbow: echo <s>|on|off > /run/statusled/rainbow -> Regenbogen für <s> Sekunden,
         dauerhaft bzw. aus; leere Datei (touch) = 60 s. Locate hat Vorrang.
Beim Start läuft kurz ein Regenbogen als LED-Test.
Bei NUM_LEDS = 1 zeigt die eine LED den schlechtesten Zustand.
"""
import colorsys
import signal
import socket
import sys
import threading
import time
from pathlib import Path

from rpi_ws281x import PixelStrip, Color

NUM_LEDS = 3
BRIGHTNESS = 0.12            # Halle ist dunkel, WS2812 auf 100 % blendet
STATE_DIR = Path("/run/statusled")
FLOOD_HOST = "flood.c3pixelflut.de"
FLOOD_PORT = 1337
NET_INTERVAL = 10            # s zwischen Netz-Checks
HEARTBEAT_TTL = 5            # s – älterer Video-Heartbeat gilt als "stale"
LOCATE_SECONDS = 60
RAINBOW_SECONDS = 60
RAINBOW_PERIOD = 3.0         # s pro Farbumlauf
STARTUP_RAINBOW = 3.0        # s Regenbogen beim Start (LED-Test)
TEMP_WARN, TEMP_ERR = 70.0, 80.0

COL = {
    "off":    (0, 0, 0),
    "boot":   (0, 0, 255),     # blau: Check läuft noch
    "ok":     (0, 255, 0),
    "warn":   (255, 100, 0),
    "err":    (255, 0, 0),     # blinkt
    "stale":  (160, 0, 255),   # lila blinkend: Video-Software meldet sich nicht mehr
    "locate": (255, 255, 255),
}
SEVERITY = ["off", "ok", "boot", "warn", "stale", "err"]
BLINKING = {"err", "stale"}

net_state = "boot"


# ---------------------------------------------------------------- WS2812
LED_PIN = 21                 # GPIO21 = PCM -> kein Konflikt mit Analog-Audio


def show(strip, pixels):
    for i, (r, g, b) in enumerate(pixels):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()


# ---------------------------------------------------------------- Checks
def net_worker():
    global net_state
    while True:
        try:
            with socket.create_connection((FLOOD_HOST, FLOOD_PORT), timeout=3):
                net_state = "ok"
        except socket.gaierror:
            net_state = "err"                # kein DNS -> vermutlich gar kein Netz
        except OSError:
            net_state = "warn"               # Netz da, Server nicht erreichbar
        time.sleep(NET_INTERVAL)


def video_state(now):
    p = STATE_DIR / "video"
    try:
        mtime = p.stat().st_mtime
        val = p.read_text().split()[0]
    except (FileNotFoundError, IndexError):
        return "off"                         # Video-Software (noch) nicht vorhanden
    if now - mtime > HEARTBEAT_TTL:
        return "stale"
    return val if val in ("ok", "warn", "err") else "warn"


def health_state():
    state = "ok"
    try:
        t = int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
        if t >= TEMP_ERR:
            return "err"
        if t >= TEMP_WARN:
            state = "warn"
    except OSError:
        pass
    try:
        # Bit 0: Unterspannung jetzt, Bit 2: gedrosselt jetzt
        thr = int(Path("/sys/devices/platform/soc/soc:firmware/get_throttled").read_text(), 16)
        if thr & 0x1:
            return "err"
        if thr & 0x4:
            state = "warn"
    except (OSError, ValueError):
        pass
    return state


def trigger_active(name, seconds, now):
    p = STATE_DIR / name
    try:
        if now - p.stat().st_mtime < seconds:
            return True
        p.unlink()
    except FileNotFoundError:
        pass
    return False


def rainbow_active(now):
    """Inhalt der Datei: Sekunden, "on" (dauerhaft), "off" (aus); leer = RAINBOW_SECONDS."""
    p = STATE_DIR / "rainbow"
    try:
        mtime = p.stat().st_mtime
        val = p.read_text().strip().lower()
    except FileNotFoundError:
        return False
    if val == "on":
        return True
    if val == "off":
        p.unlink(missing_ok=True)
        return False
    try:
        seconds = float(val) if val else RAINBOW_SECONDS
    except ValueError:
        seconds = RAINBOW_SECONDS            # Unsinn in der Datei -> Standarddauer
    if now - mtime < seconds:
        return True
    p.unlink(missing_ok=True)
    return False


def rainbow(now):
    px = []
    for i in range(NUM_LEDS):
        hue = (now / RAINBOW_PERIOD + i / max(NUM_LEDS, 3)) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        px.append((int(r * 255), int(g * 255), int(b * 255)))
    return px


# ---------------------------------------------------------------- Main
def main():
    STATE_DIR.mkdir(exist_ok=True)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    strip = PixelStrip(NUM_LEDS, LED_PIN, brightness=int(255 * BRIGHTNESS))
    strip.begin()

    threading.Thread(target=net_worker, daemon=True).start()
    started = time.time()

    try:
        while True:
            now = time.time()
            blink_on = int(now * 4) % 2 == 0          # 2 Hz

            rainbow_on = False
            if trigger_active("locate", LOCATE_SECONDS, now):
                px = [COL["locate"] if blink_on else COL["off"]] * NUM_LEDS
            elif now - started < STARTUP_RAINBOW or rainbow_active(now):
                px = rainbow(now)
                rainbow_on = True
            else:
                states = [net_state, video_state(now), health_state()]
                if NUM_LEDS == 1:
                    states = [max(states, key=SEVERITY.index)]
                px = []
                for s in states[:NUM_LEDS]:
                    px.append(COL["off"] if s in BLINKING and not blink_on else COL[s])

            show(strip, px)
            time.sleep(0.02 if rainbow_on else 0.1)   # Regenbogen braucht flüssige Frames
    finally:
        show(strip, [(0, 0, 0)] * NUM_LEDS)


if __name__ == "__main__":
    main()
