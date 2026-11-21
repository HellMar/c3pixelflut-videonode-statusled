# statusled

WS2812-Status-LEDs (1–3 Stück) für die Pixelflut-Video-Nodes (Raspberry Pi 4) beim 40c3.

## Verkabelung

| Streifen | Pi 4 |
|---|---|
| DIN | Pin 40 (GPIO21, PCM) |
| GND | Pin 39 |
| 5V  | Pin 2 oder 4 |

GPIO21 wird über PCM angesteuert (`rpi_ws281x`).

## LEDs

Die LEDs werden vom Pi aus gezählt: LED 0 sitzt am nächsten am Pi. Blinkende Zustände blinken mit 2 Hz.

### LED 0 – Netz

Pingt alle 10 s den Stream-Server an, bei dem der Node sein Video abholt (`NET_HOST`, bei pixelstream `pixelstream.server`). Ob der Server auch Video schickt, zeigt LED 1.

| Farbe | Bedeutung | Was prüfen |
|---|---|---|
| blau | Dienst gerade gestartet, erster Check läuft noch | dauert nur wenige Sekunden; bleibt sie blau, hängt der Dienst |
| grün | Stream-Server antwortet | – |
| orange | Name lässt sich auflösen, aber der Server antwortet nicht auf Ping | Server aus, Routing/Firewall, falsches VLAN |
| rot blinkend | Hostname lässt sich nicht auflösen, also wohl gar kein Netz | Kabel, Link-LED am Switch, DHCP, DNS |

### LED 1 – Video

Liest den Heartbeat aus `/run/statusled/video` (siehe [Schnittstellen](#schnittstellen)).

| Farbe | Bedeutung | Was prüfen |
|---|---|---|
| aus | Datei fehlt oder ist leer: Video-Software läuft nicht oder hat sich noch nie gemeldet | Video-Software starten |
| grün | Software meldet `ok` | – |
| grün blinkend | Software meldet `ok-blink`: läuft, aber im Sonderbetrieb (pixelstream: Bypass ohne Mapping) | gewollt? sonst `pixelstream-mode presentation` |
| orange | Software meldet `warn` oder einen unbekannten Wert (pixelstream: wartet auf den Server, der ist nicht erreichbar, lehnt ab oder schickt nichts) | LED 0 grün? Dann Sender/Server prüfen. Logs der Video-Software |
| orange blinkend | Software meldet `warn-blink`: Hinweis (pixelstream: Mapping-, Textur- oder Quellenmodus aktiv) | fertig? `pixelstream-mode presentation` |
| rot blinkend | Software meldet `err` (pixelstream: Stream nicht dekodierbar, z. B. nicht 8 Bit 4:2:0) | Format beim Sender, Logs der Video-Software |
| lila blinkend | letzter Heartbeat ist älter als 5 s: Software hängt oder ist abgestürzt | Prozess läuft noch? ggf. neu starten |

### LED 2 – Health

Prüft die CPU-Temperatur und die Unterspannungs-/Drosselungsflags des Pi.

| Farbe | Bedeutung | Was prüfen |
|---|---|---|
| grün | Temperatur unter 70 °C, keine Unterspannung, keine Drosselung | – |
| orange | 70 °C oder mehr, oder der Pi drosselt gerade | Kühlung, Luftzufuhr |
| rot blinkend | 80 °C oder mehr, oder gerade Unterspannung | Netzteil/Kabel tauschen, Kühlung |

Kann ein Wert nicht gelesen werden, wird er ignoriert.

### Alles grün: Regenbogen

Sind alle LEDs 5 s lang grün (`ALL_OK_SECONDS`), wechseln sie in einen durchlaufenden Regenbogen. Sobald etwas nicht mehr grün ist, zeigen sie sofort wieder den Status. Grün blinkend (z. B. Bypass) zählt nicht als grün und bleibt sichtbar. Abschalten: `AUTO_RAINBOW = False`.

| LED 0 (Netz) | LED 1 (Video) | heißt |
|---|---|---|
| grün | orange | Netz geht, Server schickt nichts: Sender prüfen |
| orange | orange | Server nicht erreichbar: Server aus, Routing |
| rot blinkend | orange | gar kein Netz: Kabel, DHCP, DNS |

### Sonderfälle

- **Weiß blinkend (alle LEDs):** Locate ist aktiv, der Node wurde per `touch /run/statusled/locate` gesucht. Das überdeckt alle anderen Zustände und hört nach 60 s auf.
- **Regenbogen beim Start (alle LEDs):** Nach dem Start des Dienstes läuft 3 s ein Regenbogen als LED-Test. Bleibt dabei eine LED dunkel oder zeigt falsche Farben, stimmt etwas mit LED oder Verkabelung nicht.
- **Regenbogen (alle LEDs):** Per `/run/statusled/rainbow` ausgelöst (siehe [Schnittstellen](#schnittstellen)), einfach zum Spaß. Locate hat Vorrang.
- **Alle LEDs aus:** Der Dienst läuft nicht oder der Pi hat keinen Strom. Prüfen mit `systemctl status statusled`.
- **Nur eine LED (`NUM_LEDS = 1`):** Sie zeigt den schlechtesten der drei Zustände, in dieser Reihenfolge (schlimmster zuerst): rot blinkend, lila blinkend, orange blinkend, orange, blau, grün blinkend, grün, aus. Welcher Bereich betroffen ist, muss man dann auf dem Node selbst nachsehen.

## Schnittstellen

- **Video-Heartbeat:** Die Video-Software schreibt etwa jede Sekunde `ok`, `warn` oder `err` in die Datei:
  `echo ok > /run/statusled/video`
  Zusätzlich gibt es `ok-blink` und `warn-blink` für Zustände, die auffallen sollen, aber kein Fehler sind.
- **Locate:** Alle LEDs blinken 60 s weiß:
  `ssh <node> touch /run/statusled/locate`
- **Rainbow:** Alle LEDs zeigen einen durchlaufenden Regenbogen. Was in der Datei steht, bestimmt die Dauer:
  ```
  echo 120 > /run/statusled/rainbow   # 120 s
  echo on  > /run/statusled/rainbow   # dauerhaft, bis "off"
  echo off > /run/statusled/rainbow   # sofort aus
  touch /run/statusled/rainbow        # leere Datei: 60 s
  ```
  Die Dauer zählt ab dem letzten Schreiben der Datei. Bei unlesbarem Inhalt gelten 60 s.

## Installation

```
sudo ./install.sh              # installieren bzw. aktualisieren
sudo ./install.sh --leds 1     # mit nur einer LED
sudo ./install.sh --uninstall  # wieder entfernen
```

Das Skript kann beliebig oft ausgeführt werden. Es holt die Pakete, legt das venv an, installiert `rpi_ws281x` (und baut es nur dann selbst, wenn kein fertiges Wheel da ist), kopiert die Dateien und startet den Dienst neu.

Manuelle Installation:

```
sudo apt install python3-venv python3-dev gcc
sudo python3 -m venv /opt/statusled
sudo /opt/statusled/bin/pip install rpi_ws281x
sudo install -m755 statusled.py /usr/local/bin/
sudo cp statusled.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now statusled
```

`python3-dev` und `gcc` sind nur nötig, wenn pip kein fertiges Wheel findet.
