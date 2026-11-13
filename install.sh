#!/usr/bin/env bash
# install.sh – installiert/aktualisiert statusled auf einem Pixelflut-Video-Node (Raspberry Pi 4)
#
#   sudo ./install.sh              # installieren bzw. aktualisieren
#   sudo ./install.sh --leds 1     # Anzahl der LEDs setzen (1–3, Standard 3)
#   sudo ./install.sh --uninstall  # alles wieder entfernen
#
# Das Skript ist idempotent und kann beliebig oft ausgeführt werden.
set -euo pipefail

VENV=/opt/statusled
BIN=/usr/local/bin/statusled.py
UNIT=/etc/systemd/system/statusled.service
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

NUM_LEDS=""
UNINSTALL=0

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mFehler:\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --leds)      NUM_LEDS="${2:-}"; shift 2 ;;
        --leds=*)    NUM_LEDS="${1#*=}"; shift ;;
        --uninstall) UNINSTALL=1; shift ;;
        -h|--help)   usage 0 ;;
        *)           echo "Unbekannte Option: $1" >&2; usage 1 ;;
    esac
done

[[ $EUID -eq 0 ]] || die "Bitte als root ausführen: sudo $0 $*"

if [[ -n "$NUM_LEDS" && ! "$NUM_LEDS" =~ ^[1-3]$ ]]; then
    die "--leds muss 1, 2 oder 3 sein"
fi

# ---------------------------------------------------------------- Deinstallation
if [[ $UNINSTALL -eq 1 ]]; then
    log "Entferne statusled"
    systemctl disable --now statusled 2>/dev/null || true
    rm -f "$UNIT" "$BIN"
    rm -rf "$VENV"
    systemctl daemon-reload
    log "Fertig."
    exit 0
fi

# ---------------------------------------------------------------- Installation
for f in statusled.py statusled.service; do
    [[ -f "$SRC_DIR/$f" ]] || die "$f nicht gefunden in $SRC_DIR"
done

if ! grep -q "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    echo "Warnung: Das scheint kein Raspberry Pi zu sein – rpi_ws281x wird hier nicht funktionieren." >&2
fi

log "Installiere Systempakete"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv >/dev/null

if [[ ! -x "$VENV/bin/python" ]]; then
    log "Lege venv in $VENV an"
    python3 -m venv "$VENV"
fi

log "Installiere rpi_ws281x"
"$VENV/bin/pip" install -q --upgrade pip
if ! "$VENV/bin/pip" install -q --upgrade --only-binary=:all: rpi_ws281x 2>/dev/null; then
    log "Kein fertiges Wheel gefunden – baue aus den Quellen (python3-dev, gcc)"
    apt-get install -y -qq python3-dev gcc >/dev/null
    "$VENV/bin/pip" install -q --upgrade rpi_ws281x
fi

log "Kopiere Dateien"
install -m755 "$SRC_DIR/statusled.py" "$BIN"
if [[ -n "$NUM_LEDS" ]]; then
    sed -i "s/^NUM_LEDS = .*/NUM_LEDS = $NUM_LEDS/" "$BIN"
    log "NUM_LEDS = $NUM_LEDS"
fi
install -m644 "$SRC_DIR/statusled.service" "$UNIT"

log "Starte Dienst"
systemctl daemon-reload
systemctl enable statusled >/dev/null 2>&1
systemctl restart statusled

sleep 2
if systemctl is-active --quiet statusled; then
    log "statusled läuft."
else
    systemctl --no-pager status statusled || true
    die "statusled ist nicht gestartet – siehe: journalctl -u statusled"
fi
