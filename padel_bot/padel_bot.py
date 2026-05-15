#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  REGELN & INVARIANTEN – BITTE BEI ÄNDERUNGEN STRIKT EINHALTEN!           ║
║  (Vor jedem Refactor lesen. "Mache keine Fehler!")                       ║
╚══════════════════════════════════════════════════════════════════════════╝

═══════════════════════════════════════════════════════════════════════════
 SERVER-REGELN (vom BSBB-Server erzwungen – können wir nicht umgehen)
═══════════════════════════════════════════════════════════════════════════

R1) EINE BUCHUNG PRO ACCOUNT
    Pro eingeloggtem Account ist immer nur EINE aktive (zukünftige) Buchung
    erlaubt. Versuche eine zweite zu erstellen → Server-Reject.

    Konsequenz für den Code:
    • _aggressiv_buchen_ab() macht IMMER einen Pre-Check via
      sync_buchung_vom_server(expected_slot=...) bevor er feuert.
    • Parallele Court-Threads: bei Doppel-Treffer (Server-Race, theoretisch
      sollte das nicht möglich sein, aber Versicherung) MUSS automatisch
      der nicht-bevorzugte Court storniert werden.
    • Fallback-Loop prüft vor jedem Retry per sync, ob wir den Slot
      bereits haben → sofortiger Abbruch.
    • Schiebe-Phase3 muss zwingend storno-vor-rebook fahren, niemals
      rebook-vor-storno (würde am Server scheitern).

R2) 7-TAGE-ROLLING-FENSTER (auf die Minute genau)
    Zum Zeitpunkt T kann man Slots buchen die spätestens bei T + 7 Tage
    starten. Beispiele:
      • 14.05. 07:00 Uhr → buchbar: 21.05. 07:00 (und alles davor)
      • 14.05. 13:00 Uhr → buchbar: 21.05. 13:00 (und alles davor)
      • 14.05. 13:30 Uhr → buchbar: 21.05. 13:30 (und alles davor)
    Slot 21.05. 14:00 ist am 14.05. erst um 14:00 buchbar.

    Konsequenz für den Code:
    • berechne_freie_slots() filtert per `grenze = jetzt + timedelta(days=7)`
      → NIEMALS auf `days=7` ohne Stundenkomponente reduzieren!
    • Früh-Methode zielt deshalb exklusiv auf den 07:00-Slot am D+7-Tag
      (nur DER ist um 07:00 freigeschaltet, 07:30 erst um 07:30).
    • Direkte Taktik: feuert genau zur Uhrzeit T → erlaubt Slots ab T.
    • Spät-Taktik kann nur Slots erwischen die bis "jetzt" freigeschaltet
      wurden.

R3) ANLAGEN-ÖFFNUNGSZEITEN
    Court-Slots: 07:00 – 22:00 (ANLAGE_OEFFNUNG / ANLAGE_SCHLUSS).
    Slot-Granularität: 30 Minuten (Start nur :00 oder :30).
    Buchungsdauer: 60 oder 90 Minuten.
    Letzter Buchungsstart = 22:00 – Dauer.

R4) COURTS
    Es gibt genau zwei Courts: Court 1 und Court 2.
    Default-Präferenz (wenn user "Egal" wählt): Court 2 zuerst, dann Court 1.
    Server-Konstanten: MODULE="4", BOOKING_TYPE="4". NICHT ÄNDERN.

═══════════════════════════════════════════════════════════════════════════
 HTTP-FLOW (Spring Webflow Sequenz – Reihenfolge ist Pflicht)
═══════════════════════════════════════════════════════════════════════════

R5) BUCHUNGS-FLOW IST DREI-PHASIG
    r1: GET  /court-single-booking-flow  →  liefert execution=eXs1
    r2: POST execution=eXs1 &_eventId=next   →  Wizard auf s2, claimt Slot
    r3: POST execution=eXs2 &_eventId=commit →  COMMIT, schreibt Buchung

    Eine execution ist nach Verbrauch tot. r3 fehlgeschlagen → komplett
    neue Sequenz starten, NICHT dieselbe execution wiederverwenden.
    Pre-Warm darf NUR r1 vorab feuern (Token cachen), niemals r2!

R6) STORNO-FLOW IST ZWEI-PHASIG
    POST /bookings/{id}/cancel-flow                       → liefert execution
    POST /bookings/{id}/cancel-flow ?execution=...&_eventId=confirm
         + form: confirmKey={CONFIRM_KEY}&confirmValue=true
    CONFIRM_KEY ist eine Server-Konstante. NICHT ändern.

═══════════════════════════════════════════════════════════════════════════
 SCHIEBE-LOGIK (die Quelle vieler historischer Bugs)
═══════════════════════════════════════════════════════════════════════════

R7) SCHIEBE-MOMENT = HEUTE, NICHT BUCHUNGSTAG
    In _schiebe_phase3():
        schiebe_moment = datetime.combine(jetzt.date(), ...)   ✅ RICHTIG
        schiebe_moment = datetime.combine(datum_obj.date(), ...) ❌ FALSCH
    Das Schieben passiert HEUTE (z.B. 19.04), nicht am gebuchten Tag
    (z.B. 26.04). Diese Zeile NIEMALS "vereinfachen".

R8) SCHIEBE-INTERVALL IST ZUFÄLLIG
    Zwischen Schiebe-Versuchen 5–20 Min Zufallspause
    (SCHIEBE_MINUTEN_VOR_MIN / _MAX). NICHT auf festen Wert reduzieren –
    Pattern-Detection vom Server möglich.

R9) PHASE 3 IST STORNO → REBOOK, NIE UMGEKEHRT
    Reihenfolge: alten Slot stornieren, sofort danach neuen Slot buchen.
    Würde die Reihenfolge gedreht, scheitert das Rebook an R1
    (Account hat schon eine aktive Buchung). Bei fehlgeschlagenem Rebook
    MUSS der alte Slot zurückgewonnen werden (Recovery-Pfad in Phase3).

═══════════════════════════════════════════════════════════════════════════
 IDENTITÄTS- & SESSION-REGELN
═══════════════════════════════════════════════════════════════════════════

R10) PERSON-ID-VERIFIKATION NACH JEDEM TREFFER
     /padel?currentDate=... liefert ALLE Reservierungen auf den Courts,
     auch fremde – jeweils mit personId-Feld. Nach einer Buchung muss
     personId == eigene person_id geprüft werden, sonst landet eine
     fremde Buchung in aktive_buchung.

     buche_slot_blitz(verify_person_id=True) macht das. Im Sniper und
     in der Direkten Taktik IMMER eingeschaltet lassen.

R11) /user/my-bookings IST DIE GROUND TRUTH FÜR EIGENE BUCHUNGEN
     Nur dieser Endpoint zeigt zuverlässig die eigenen Buchungen.
     /padel zeigt alle (auch fremde). Bei Unsicherheit: my-bookings.

R12) SYNC MIT expected_slot FILTERN
     sync_buchung_vom_server() ohne Filter holt die zeitlich nächste
     Buchung – das kann eine ALTE zukünftige Buchung sein.
     Nach einer frischen Buchung IMMER mit expected_slot syncen.

R13) PRO ACCOUNT EIGENE Session, CSRF, person_id
     Jeder Account hat eigenes requests.Session + Lock. Niemals Sessions
     vermischen oder Cookies zwischen Accounts kopieren – führt zu R10-
     Verstoß und falscher Buchungs-Zuordnung.

R14) LOGIN-COOLDOWN 30s
     ist_eingeloggt() checkt höchstens alle 30s (LOGIN_CHECK_COOLDOWN).
     Vor zeitkritischen Aktionen (Direkt/Früh): bei T-90s frischer Login
     via _session_refresh_vor_aktion(). Diese 90s-Marge NICHT verkürzen –
     Login kann mal 5–10s dauern.

═══════════════════════════════════════════════════════════════════════════
 TIMING-REGELN BLITZ-PFAD
═══════════════════════════════════════════════════════════════════════════

R15) PRE-WARM BEI T-10s, FEUER BEI T-0
     BLITZ_PREWARM_SECONDS = 10 ist die getestete Marge.
     Kleiner: Pre-Warm-Request läuft evtl. nicht rechtzeitig fertig.
     Größer: execution-Token könnte stale werden (Spring Webflow killt
     idle executions; ~30 min sind ok, aber bleibt konservativ).

R16) FEUER NICHT VOR buchbar_dt
     Wer r2 vor Freischaltung feuert → Server-Reject ("nicht möglich").
     BLITZ_FIRE_OFFSET_MS = 0 (auf die Sekunde, eher minimal später als
     früher). Niemals negativ setzen.

R17) PARALLELE THREADS NUTZEN GETEILTE SESSION
     Court-1- und Court-2-Thread teilen sich requests.Session des
     Accounts. OK für 2 Threads à 2 Requests, aber NICHT auf 5+ Threads
     skalieren ohne Session-Klon oder Lock – Connection-Pool blockiert.

R18) MULTI-SHOT NACH FREISCHALTUNG (v10.3.3)
     Bei verfehltem ersten Burst: bis zu MULTI_SHOT_COUNT weitere Bursts
     mit jeweils frischen Executions. Bursts mit MULTI_SHOT_GAP_MS
     Pause zwischen sich (Connection-Pool entlasten).
     Niemals VOR buchbar_dt feuern (siehe R16).

═══════════════════════════════════════════════════════════════════════════
 SMART-SNIPER-REGELN
═══════════════════════════════════════════════════════════════════════════

R20) SNIPER LAUER-FENSTER = LETZTE 30 MIN VOR FREMDER ENDZEIT (v10.3.3)
     Beobachtung: Menschen die schieben (Storno + Rebook), tun das
     fast immer in den letzten 30 Min ihrer Buchung. Davor lauern ist
     Verschwendung.

     Beispiel: Max hat 17:00–18:30 gebucht.
       • Lauer-Start:  18:00  (= 18:30 - SNIPER_PRE_END_MINUTES)
       • Lauer-Ende:   18:30  (= fremde Endzeit)
       • Login-Refresh: 17:55 (= Lauer-Start - SNIPER_LOGIN_BUFFER)

     User startet Sniper z.B. um 14:00 → Bot schläft bis 17:55, ohne
     den Server zu belasten. Spart Resourcen und vermeidet
     Pattern-Detection.

R21) SNIPER ZIEL-SLOTS (beachte 7-Tage-Regel R2!)
     Während Lauer-Fenster 18:00–18:30 (Beispiel):
       Phase 1 (18:00 bis 18:30): Hämmere Slot der bei fremder
         Startzeit beginnt (18:00–19:30) auf user-gewähltem Court.
         Bei "Egal": nur den Court wo fremde Buchung läuft.
         → Buchbar weil 7 Tage exakt erreicht
         → Belegt durch Max → nur Treffer wenn Max storniert
       Phase 2 (ab 18:30): Wechsel zu Multi-Shot Blitz auf
         18:30–20:00 (= direkt anschließender Slot, jetzt
         frisch freigeschaltet durch 7-Tage-Regel).
         Bei "Egal": beide Courts parallel (wie Direkte Taktik).

R22) SNIPER-TIMEOUT IST DEADLINE = FREMDE ENDZEIT + BLITZ-BUDGET
     Sniper macht keinen Sinn nach Maxes Endzeit (= Slot-Start unserer
     Buchung). Bot bricht spätestens 60s nach fremder Endzeit ab.
     SNIPER_TIMEOUT (1200s = 20 min) bleibt als Hard-Cap erhalten falls
     User außerhalb Lauer-Fenster manuell startet.

═══════════════════════════════════════════════════════════════════════════
 ZEITZONE
═══════════════════════════════════════════════════════════════════════════

R19) IMMER jetzt_lokal() VERWENDEN
     Nie datetime.now() ohne Zeitzone. jetzt_lokal() liefert
     naive datetime in Europe/Berlin. Server rechnet ebenfalls in
     lokaler Zeit. Sommerzeit-Umstellung wird automatisch berücksichtigt.

  ❌ schiebe_moment-Zeile in _schiebe_phase3 (R7)
  ❌ Reihenfolge r1→r2→r3 oder execution-Wiederverwendung (R5)
  ❌ CONFIRM_KEY-Wert (R6)
  ❌ MODULE / BOOKING_TYPE (R4)
  ❌ Person-ID-Check abschalten (R10)
  ❌ expected_slot-Filter in Sync für frische Buchungen weglassen (R12)
  ❌ Parallele Court-Threads ohne Doppel-Treffer-Dedup (R1)
  ❌ Storno-vor-Rebook-Reihenfolge in Phase 3 umdrehen (R9)
  ❌ 90s-Login-Marge oder 10s-Pre-Warm-Marge stark verkürzen (R14/R15)
  ❌ Feuern vor buchbar_dt (R16)
  ❌ Sniper lauert außerhalb des 30-Min-Fensters vor fremder Endzeit (R20)
  ❌ Phase 1 Sniper auf falschem Slot (muss = fromTime fremde, nicht fromTime+dauer) (R21)

═══════════════════════════════════════════════════════════════════════════
 Padel Bot v10.3.3
═══════════════════════════════════════════════════════════════════════════

ÄNDERUNGEN gegenüber v10.2.0:

NEU: prewarm_execution()
     Feuert r1 EINMALIG vorab und gibt das execution-Token + frisches CSRF zurück.
     Wird ~10s vor Zielzeit aufgerufen, damit zur Zielzeit nur noch r2+r3
     gefeuert werden müssen.

NEU: buche_slot_blitz()
     Ersetzt buche_slot_schnell() vollständig.
     - Wenn prewarm_exec gegeben: skippt r1 (nur 2 HTTP-Requests im heißen Pfad)
     - Sonst: voller r1+r2+r3 Flow (Fallback)
     - Person-ID-Verifikation via /padel: erkennt fremde Buchungen
     - Setzt aktive_buchung NICHT direkt (Caller entscheidet → thread-safe für Parallel)

GEÄNDERT: _aggressiv_buchen_ab() – PARALLEL-MODUS
     1. T-10s: Pre-warm r1 für Court 2 UND Court 1 parallel
     2. T-0:   Feuere r2+r3 auf BEIDEN Courts gleichzeitig in 2 Threads
     3. Bei 1 Treffer: fertig
     4. Bei 2 Treffern: behalte bevorzugten Court, storniere automatisch den anderen
     5. Bei 0 Treffern: serielles Fallback-Hämmern mit buche_slot_blitz
     Ergebnis: ~200ms statt ~500ms im heißen Pfad – kein Mensch mehr schneller.

GEÄNDERT: _sniper_intern()
     - Nutzt buche_slot_blitz() mit Person-ID-Verifikation
     - sync_buchung_vom_server() mit expected_slot-Parameter
     - Kein falscher Schiebe-Start mehr durch alte Buchungen

GEÄNDERT: sync_buchung_vom_server(expected_slot=...)
     Wenn expected_slot übergeben: matcht NUR den erwarteten Slot.
     Verhindert dass alte Buchungen als gerade gemachte erkannt werden.

GEÄNDERT: _schiebe_intern() Direkt-Branch
     Gibt die Wartelogik komplett an _aggressiv_buchen_ab ab.
     Kein "spam_start_dt = buchbar_dt - 1s"-Sleep mehr.
     Pre-warm + parallel-Feuer übernimmt das Timing.

ENTFERNT: buche_slot_schnell()
     Vollständig ersetzt durch buche_slot_blitz().

UNVERÄNDERT:
     buche_slot()              → Früh-Methode, Spät-Taktik, klassische Buchung
     _aggressiv_buchen_07()    → Früh-Methode (07:00 Dauerbeschuss)
     _schiebe_phase3()         → Schiebe-Loop (Storno + Rebook)

══════════════════════════════════════════════════════════════════════
SCHIEBE-LOGIK – BITTE NIEMALS ÄNDERN!
══════════════════════════════════════════════════════════════════════
Das Schieben geschieht HEUTE (z.B. 19.04), nicht am Buchungstag (26.04)!
  schiebe_moment = datetime.combine(jetzt.date(), ...) ← jetzt.date() = HEUTE
  NICHT:          datetime.combine(datum_obj.date(), ...) ← wäre Buchungstag!
══════════════════════════════════════════════════════════════════════
"""

import re
import json
import random
import requests
import threading
import time
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
# ZEITZONE
# ─────────────────────────────────────────────

_BERLIN = ZoneInfo("Europe/Berlin")

def jetzt_lokal() -> datetime:
    return datetime.now(_BERLIN).replace(tzinfo=None)

# ─────────────────────────────────────────────
# WETTER
# ─────────────────────────────────────────────

WETTER_LAT = 51.545839
WETTER_LON = 6.928109
WETTER_CODES = {
    0: "☀️ Klar", 1: "🌤️ Überwiegend klar", 2: "⛅ Teilweise bewölkt",
    3: "☁️ Bedeckt", 45: "🌫️ Nebel", 48: "🌫️ Reifnebel",
    51: "🌦️ Leichter Nieselregen", 53: "🌦️ Nieselregen", 55: "🌧️ Starker Nieselregen",
    61: "🌧️ Leichter Regen", 63: "🌧️ Regen", 65: "🌧️ Starker Regen",
    71: "🌨️ Leichter Schnee", 73: "🌨️ Schnee", 75: "❄️ Starker Schnee",
    80: "🌦️ Leichte Schauer", 81: "🌧️ Schauer", 82: "⛈️ Starke Schauer",
    95: "⛈️ Gewitter", 96: "⛈️ Gewitter mit Hagel", 99: "⛈️ Schweres Gewitter",
}

def hole_wetter(datum_de: str, from_time: str) -> str:
    try:
        datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
        datum_iso = datum_obj.strftime("%Y-%m-%d")
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":   WETTER_LAT,
                "longitude":  WETTER_LON,
                "hourly":     "temperature_2m,precipitation_probability,weathercode,windspeed_10m",
                "start_date": datum_iso,
                "end_date":   datum_iso,
                "timezone":   "Europe/Berlin",
            },
            timeout=8,
        )
        if r.status_code != 200:
            return ""
        data   = r.json()
        temps  = data["hourly"]["temperature_2m"]
        precip = data["hourly"]["precipitation_probability"]
        codes  = data["hourly"]["weathercode"]
        winds  = data["hourly"]["windspeed_10m"]
        stunde = int(from_time.split(":")[0])
        idx    = min(stunde, len(temps) - 1)
        temp   = temps[idx]
        rain   = precip[idx]
        code   = codes[idx]
        wind   = winds[idx]
        desc   = WETTER_CODES.get(code, "❓")
        return (f"\n{desc} | 🌡️ {temp:.0f}°C | ☔ {rain}% | 💨 {wind:.0f} km/h")
    except Exception as e:
        log.warning(f"Wetter-API Fehler: {e}")
        return ""


# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────

_OPTIONS_PATH = "/data/options.json"

def _lade_options() -> dict:
    try:
        with open(_OPTIONS_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"❌ {_OPTIONS_PATH} nicht gefunden!")
    except json.JSONDecodeError as e:
        raise SystemExit(f"❌ Fehler beim Lesen von {_OPTIONS_PATH}: {e}")

_cfg = _lade_options()

def _required(key: str) -> str:
    val = _cfg.get(key, "").strip()
    if not val:
        raise SystemExit(f"❌ Option '{key}' ist leer!")
    return val

def _optional(key: str, default: str = "") -> str:
    return _cfg.get(key, default).strip()

TELEGRAM_BOT_TOKEN = _required("telegram_bot_token")
TELEGRAM_CHAT_ID   = _required("telegram_chat_id")

ANLAGE_OEFFNUNG     = "07:00"
ANLAGE_SCHLUSS      = "22:00"

SCHIEBE_MINUTEN_VOR_MIN = 5
SCHIEBE_MINUTEN_VOR_MAX = 20
LOGIN_CHECK_COOLDOWN    = 30
AGGRESSIVE_TIMEOUT      = 60    # v10.3.3: 60s statt 300s (Slot ist eh in Sek. weg)
SNIPER_TIMEOUT          = 1200  # 20 min – Sniper darf lauern auf fremde Stornos

# v10.3.3 NEU – Smart-Sniper-Konfiguration (siehe R20)
SNIPER_PRE_END_MINUTES = 30     # Lauer-Fenster = letzte 30 Min vor fremder Endzeit
SNIPER_LOGIN_BUFFER    = 5      # Login-Refresh X Min vor Lauer-Start
AGGRESSIVE_INTERVAL     = 0.05  # v10.3: schnellere Retry-Frequenz (war 0.1)
FRUEH_EXKLUSIV_VERSUCHE = 8

# v10.3 NEU – Blitz-Konfiguration
BLITZ_PREWARM_SECONDS = 10      # Wie viele Sek. vor Zielzeit r1 gefeuert wird
BLITZ_FIRE_OFFSET_MS  = 0       # ms vor/nach Zielzeit zum Feuern (0 = exakt)

# v10.3.3 NEU – Multi-Shot-Konfiguration (siehe R18)
MULTI_SHOT_COUNT  = 5           # Anzahl Bursts (1=alt-Verhalten, 5=Standard)
MULTI_SHOT_GAP_MS = 50          # Pause zwischen Bursts in ms (Connection-Pool)

# ─────────────────────────────────────────────
# KONSTANTEN
# ─────────────────────────────────────────────

BASE_URL     = "https://bsbb.ebusy.de"
MODULE       = "4"
BOOKING_TYPE = "4"
CONFIRM_KEY  = "de.productiveweb.ebusy.model.tenant.general.booking.UserBookingCancelConfirm"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# ACCOUNTS
# ─────────────────────────────────────────────

def _lade_accounts() -> dict:
    accounts = {}

    email1 = _optional("account_1_email")
    pw1    = _optional("account_1_passwort")
    if not email1 or not pw1:
        raise SystemExit("❌ account_1_email / account_1_passwort fehlen in options.json!")
    label1 = _optional("account_1_label") or "ACC1"
    accounts[label1] = {"email": email1, "passwort": pw1}

    email2 = _optional("account_2_email")
    pw2    = _optional("account_2_passwort")
    if email2 and pw2:
        label2 = _optional("account_2_label") or "ACC2"
        if label2 == label1:
            label2 = label2 + "_2"
        accounts[label2] = {"email": email2, "passwort": pw2}

    email3 = _optional("account_3_email")
    pw3    = _optional("account_3_passwort")
    if email3 and pw3:
        label3 = _optional("account_3_label") or "ACC3"
        if label3 in (label1,) or (len(accounts) > 1 and label3 in accounts):
            label3 = label3 + "_3"
        accounts[label3] = {"email": email3, "passwort": pw3}

    email4 = _optional("account_4_email")
    pw4    = _optional("account_4_passwort")
    if email4 and pw4:
        label4 = _optional("account_4_label") or "ACC4"
        if label4 in accounts:
            label4 = label4 + "_4"
        accounts[label4] = {"email": email4, "passwort": pw4}

    email5 = _optional("account_5_email")
    pw5    = _optional("account_5_passwort")
    if email5 and pw5:
        label5 = _optional("account_5_label") or "ACC5"
        if label5 in accounts:
            label5 = label5 + "_5"
        accounts[label5] = {"email": email5, "passwort": pw5}

    email6 = _optional("account_6_email")
    pw6    = _optional("account_6_passwort")
    if email6 and pw6:
        label6 = _optional("account_6_label") or "ACC6"
        if label6 in accounts:
            label6 = label6 + "_6"
        accounts[label6] = {"email": email6, "passwort": pw6}

    labels = list(accounts.keys())
    if len(labels) == 1:
        log.info(f"   Account geladen: {labels[0]} (Einzelmodus)")
    else:
        log.info(f"   Accounts geladen: {', '.join(labels)}")

    return accounts

ACCOUNTS = _lade_accounts()

# ─────────────────────────────────────────────
# ACCOUNT-ZUSTAND
# ─────────────────────────────────────────────

def _neue_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "accept-language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
    })
    return s

def neuer_account_zustand(kuerzel: str) -> dict:
    return {
        "kuerzel":            kuerzel,
        "http":               _neue_session(),
        "csrf_token":         "",
        "person_id":          "",
        "letzter_logincheck": 0.0,
        "lock":               threading.Lock(),
        "aktive_buchung":     None,
        # Schiebe
        "schiebe_aktiv":      False,
        "schiebe_modus":      None,
        "schiebe_datum":      None,
        "schiebe_ziel":       None,
        "schiebe_dauer":      None,
        "schiebe_buchbar_ab": None,
        "schiebe_court":      None,
        "schiebe_thread":     None,
        # Sniper
        "sniper_aktiv":       False,
        "sniper_datum":       None,
        "sniper_court":       None,
        "sniper_fremder_bis": None,
        "sniper_dauer":       None,
        "sniper_ziel":        None,
        "sniper_thread":      None,
        # Flow
        "flow":               None,
        "flow_datum":         None,
        "flow_dauer":         None,
    }

acc = {k: neuer_account_zustand(k) for k in ACCOUNTS}
_flow_account   = {"kuerzel": None}
_flow_lock      = threading.Lock()
telegram_offset = 0

# ─────────────────────────────────────────────
# ACCOUNT-HELFER
# ─────────────────────────────────────────────

def az_get(k: str, key: str):
    with acc[k]["lock"]: return acc[k][key]

def az_set(k: str, key: str, val):
    with acc[k]["lock"]: acc[k][key] = val

def az_set_multi(k: str, **kwargs):
    with acc[k]["lock"]: acc[k].update(kwargs)

def az_snap(k: str, *keys):
    with acc[k]["lock"]: return {x: acc[k][x] for x in keys}

def get_flow_account() -> str | None:
    with _flow_lock: return _flow_account["kuerzel"]

def set_flow_account(k: str | None):
    with _flow_lock: _flow_account["kuerzel"] = k

# ══════════════════════════════════════════════
# TELEGRAM HELPERS
# ══════════════════════════════════════════════

def tg(method: str, payload: dict) -> dict:
    try:
        r = requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}",
                          json=payload, timeout=10)
        return r.json()
    except Exception as e:
        log.error(f"Telegram {method}: {e}")
        return {}

def senden(text: str, buttons: list = None):
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    tg("sendMessage", payload)

def beantworte_callback(cid: str, text: str = "✅"):
    tg("answerCallbackQuery", {"callback_query_id": cid, "text": text})

def hole_updates() -> list:
    global telegram_offset
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                         params={"offset": telegram_offset, "timeout": 5}, timeout=10)
        updates = r.json().get("result", [])
        if updates:
            telegram_offset = updates[-1]["update_id"] + 1
        return updates
    except Exception:
        return []

# ══════════════════════════════════════════════
# MENÜ-FUNKTIONEN
# ══════════════════════════════════════════════

WOCHENTAGE      = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WOCHENTAGE_LANG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

def _datum_mit_tag(datum_de: str) -> str:
    try:
        d  = datetime.strptime(datum_de, "%d.%m.%Y")
        wt = WOCHENTAGE_LANG[d.weekday()]
        return f"{wt} {datum_de}"
    except Exception:
        return datum_de

def account_status_label(k: str) -> str:
    snap   = az_snap(k, "aktive_buchung", "schiebe_aktiv", "schiebe_datum", "schiebe_ziel",
                     "sniper_aktiv", "sniper_datum")
    aktiv  = snap["aktive_buchung"]
    schiebe = snap["schiebe_aktiv"]
    sniper  = snap["sniper_aktiv"]

    thread        = acc[k].get("schiebe_thread")
    sniper_thread = acc[k].get("sniper_thread")
    if schiebe and thread and not thread.is_alive():
        az_set(k, "schiebe_aktiv", False)
        schiebe = False
    if sniper and sniper_thread and not sniper_thread.is_alive():
        az_set(k, "sniper_aktiv", False)
        sniper = False

    if aktiv:
        datum_str = _datum_mit_tag(aktiv.get("datum_de", "?"))
        court_str = aktiv.get("court", "?")
        return (f"🔴 {k} – {datum_str} "
                f"{aktiv.get('fromTime','?')}–{aktiv.get('toTime','?')} C{court_str}")
    elif schiebe:
        datum_str = _datum_mit_tag(snap["schiebe_datum"] or "?")
        return f"🟡 {k} – Schiebe {datum_str}"
    elif sniper:
        datum_str = _datum_mit_tag(snap["sniper_datum"] or "?")
        return f"🔵 {k} – Sniper {datum_str}"
    return f"✅ {k} – frei"

def zeige_account_auswahl():
    set_flow_account(None)
    for k in ACCOUNTS:
        try:
            sync_buchung_vom_server(k)
        except Exception as e:
            log.warning(f"[{k}] Sync: {e}")

    anzahl     = len(ACCOUNTS)
    modus_label = "Dual-Account" if anzahl > 1 else "Einzel-Account"
    buttons = []
    for k in ACCOUNTS:
        buttons.append([{"text": account_status_label(k), "callback_data": f"acc_{k}"}])
    buttons.append([{"text": "🔄 Aktualisieren", "callback_data": "refresh_accounts"}])

    status_zeilen = ""
    for k in ACCOUNTS:
        label = account_status_label(k)
        aktiv = az_get(k, "aktive_buchung")
        if aktiv:
            w = hole_wetter(aktiv["datum_de"], aktiv["fromTime"])
            status_zeilen += f"\n{label}"
            if w:
                status_zeilen += f"\n{w.strip()}"
        else:
            status_zeilen += f"\n{label}"

    senden(f"🎾 <b>Padel Bot – Account wählen</b> ({modus_label})\n\n"
           f"✅ frei  |  🔴 Buchung  |  🟡 Schiebe  |  🔵 Sniper"
           f"{status_zeilen}",
           buttons=buttons)

def zeige_account_menue(k: str):
    snap    = az_snap(k, "aktive_buchung", "schiebe_aktiv",
                      "schiebe_ziel", "schiebe_datum", "schiebe_dauer", "schiebe_modus",
                      "sniper_aktiv", "sniper_datum", "sniper_ziel")
    aktiv   = snap["aktive_buchung"]
    schiebe = snap["schiebe_aktiv"]
    sniper  = snap["sniper_aktiv"]
    modus_l = {"frueh": "Früh", "spaet": "Spät", "direkt": "Direkt", "sniper": "Sniper-Fortsetzung"}.get(
        snap["schiebe_modus"] or "", "")

    if aktiv:
        status = (f"🔴 <b>Aktive Buchung:</b>\n"
                  f"   {aktiv['datum_de']} | {aktiv['fromTime']}–{aktiv['toTime']} | Court {aktiv['court']}")
        if schiebe:
            status += (f"\n🟡 Schiebe ({modus_l}) → Ziel {snap['schiebe_ziel']} Uhr "
                       f"({snap['schiebe_dauer']} Min)")
    elif schiebe:
        status = (f"🟡 Schiebe-Taktik ({modus_l}) läuft\n"
                  f"   Ziel: {(snap['schiebe_datum'] or '')[:5]} {snap['schiebe_ziel']} Uhr "
                  f"({snap['schiebe_dauer']} Min)")
    elif sniper:
        status = (f"🔵 Sniper aktiv\n"
                  f"   Datum: {snap['sniper_datum'] or '?'} | Ziel: {snap['sniper_ziel'] or '?'} Uhr")
    else:
        status = "✅ Kein aktiver Prozess"

    back_btn = (
        [{"text": "↩️ Account-Auswahl", "callback_data": "zurueck_accounts"}]
        if len(ACCOUNTS) > 1 else []
    )

    senden(f"🎾 <b>Account: {k}</b>\n\n{status}\n\nWas möchtest du tun?",
           buttons=[
               [{"text": "📅 Klassisch buchen",       "callback_data": f"menu_slots_{k}"}],
               [{"text": "🔄 Schiebe-Taktik",          "callback_data": f"menu_schiebe_{k}"}],
               [{"text": "🎯 Sniper-Modus",            "callback_data": f"menu_sniper_{k}"}],
               [{"text": "📊 Status",                  "callback_data": f"menu_status_{k}"}],
               [{"text": "⏹️ Stoppen (Schiebe/Sniper)", "callback_data": f"menu_stopp_{k}"}],
               [{"text": "🗑️ Buchung stornieren",      "callback_data": f"menu_storno_{k}"}],
               *([back_btn] if back_btn else []),
           ])

def zeige_schiebe_modus_auswahl(k: str):
    senden(
        f"🔄 <b>[{k}] Schiebe-Taktik – Modus wählen</b>\n\n"
        f"🌅 <b>Früh-Methode:</b>\nWartet auf 07:00 am 7-Tage-Tag. "
        f"~2s Dauerbeschuss exklusiv auf 07:00, dann Fallback auf frühesten freien Slot. "
        f"Schiebt zur Wunschzeit.\n\n"
        f"🕐 <b>Spät-Taktik:</b>\n07:00 verpasst → Bot bucht sofort den spätesten "
        f"freien Slot und schiebt weiter zur Wunschzeit.\n\n"
        f"🎯 <b>Direkte Taktik:</b>\nDu weißt ab wann buchbar (z.B. 17:30 heute). "
        f"Bot wartet bis 17:30, bucht dann und schiebt zur Wunschzeit.\n"
        f"<i>v10.3: Pre-warm + parallele Courts → ~200ms statt ~500ms im heißen Pfad</i>",
        buttons=[
            [{"text": "🌅 Früh-Methode  (07:00 Dauerbeschuss + Fallback)",
              "callback_data": f"schiebe_modus_frueh_{k}"}],
            [{"text": "🕐 Spät-Taktik  (spätester freier Slot jetzt)",
              "callback_data": f"schiebe_modus_spaet_{k}"}],
            [{"text": "🎯 Direkte Taktik  ⚡ BLITZ  (bekannte Startzeit)",
              "callback_data": f"schiebe_modus_direkt_{k}"}],
            [{"text": "↩️ Zurück", "callback_data": f"acc_{k}"}],
        ])

# ══════════════════════════════════════════════
# BUTTON-HELFER
# ══════════════════════════════════════════════

def erstelle_datum_buttons(prefix: str, nur_im_fenster: bool = False) -> list:
    heute = jetzt_lokal()
    buttons, reihe = [], []
    for i in range(1, 11):
        tag      = heute + timedelta(days=i)
        tage_dif = (tag.date() - heute.date()).days
        if nur_im_fenster and tage_dif > 7:
            continue
        wt    = WOCHENTAGE[tag.weekday()]
        label = f"{wt} {tag.strftime('%d.%m.')}"
        reihe.append({"text": label,
                      "callback_data": f"{prefix}_{tag.strftime('%d.%m.%Y')}"})
        if len(reihe) == 4:
            buttons.append(reihe)
            reihe = []
    if reihe:
        buttons.append(reihe)
    buttons.append([{"text": "❌ Abbrechen", "callback_data": "abbrechen"}])
    return buttons

def dauer_buttons(prefix: str) -> list:
    return [[
        {"text": "60 Minuten", "callback_data": f"{prefix}_60"},
        {"text": "90 Minuten", "callback_data": f"{prefix}_90"},
    ]]

def court_buttons(prefix: str) -> list:
    return [[
        {"text": "🏟️ Court 1", "callback_data": f"{prefix}_1"},
        {"text": "🏟️ Court 2", "callback_data": f"{prefix}_2"},
        {"text": "🎲 Egal (bevorzuge Court 2)", "callback_data": f"{prefix}_0"},
    ]]

def zielzeit_buttons(prefix: str, dauer_min: int) -> list:
    schluss = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")
    letzter = schluss - timedelta(minutes=dauer_min)
    buttons, reihe = [], []
    t = datetime.strptime(ANLAGE_OEFFNUNG, "%H:%M")
    while t <= letzter:
        reihe.append({"text": t.strftime("%H:%M"),
                      "callback_data": f"{prefix}_{t.strftime('%H:%M')}"})
        if len(reihe) == 4:
            buttons.append(reihe)
            reihe = []
        t += timedelta(minutes=30)
    if reihe:
        buttons.append(reihe)
    buttons.append([{"text": "❌ Abbrechen", "callback_data": "abbrechen"}])
    return buttons

def sniper_endzeit_buttons(prefix: str) -> list:
    """Buttons für die Endzeit der FREMDEN Buchung (07:30–22:00)."""
    buttons, reihe = [], []
    t   = datetime.strptime("07:30", "%H:%M")
    end = datetime.strptime("22:00", "%H:%M")
    while t <= end:
        reihe.append({"text": t.strftime("%H:%M"),
                      "callback_data": f"{prefix}_{t.strftime('%H:%M')}"})
        if len(reihe) == 4:
            buttons.append(reihe)
            reihe = []
        t += timedelta(minutes=30)
    if reihe:
        buttons.append(reihe)
    buttons.append([{"text": "❌ Abbrechen", "callback_data": "abbrechen"}])
    return buttons

# ══════════════════════════════════════════════
# LOGIN & SESSION
# ══════════════════════════════════════════════

def hole_csrf(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in [soup.find("meta", {"name": "_csrf"}),
                soup.find("input", {"name": "_csrf"})]:
        if tag:
            val = tag.get("content") or tag.get("value")
            if val:
                return val
    m = re.search(r'"_csrf"\s*:\s*"([a-f0-9-]{30,})"', html)
    return m.group(1) if m else ""

def extrahiere_person_id(html: str) -> str:
    patterns = [
        r'purchaseTemplate.person["\s]*[=:]["\s]*(\d+)',
        r'"personId"\s*:\s*(\d+)',
        r'data-person[="\s]+(\d+)',
        r'<option[^>]+value="(\d{3,6})"[^>]*selected',
        r'person.*?value="(\d{3,6})"',
        r'/user/(\d{3,6})/profile',
        r'"userId"\s*:\s*(\d+)',
        r'userId=(\d+)',
    ]
    for p in patterns:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""

def einloggen(k: str) -> bool:
    cfg  = ACCOUNTS[k]
    http = acc[k]["http"]
    log.info(f"🔑 [{k}] Login…")
    try:
        r    = http.get(f"{BASE_URL}/login", timeout=15)
        csrf = hole_csrf(r.text)
        r2   = http.post(f"{BASE_URL}/login",
                         data={"username": cfg["email"],
                               "password": cfg["passwort"], "_csrf": csrf},
                         headers={"content-type": "application/x-www-form-urlencoded",
                                  "origin": BASE_URL, "referer": f"{BASE_URL}/login"},
                         allow_redirects=True, timeout=15)
        ok = ("logout" in r2.text.lower() or "abmelden" in r2.text.lower()
              or "/login" not in r2.url)
        if ok:
            person_id = ""
            csrf_t    = ""

            r3     = http.get(f"{BASE_URL}/padel", timeout=10)
            csrf_t = hole_csrf(r3.text) or http.cookies.get("XSRF-TOKEN", "")
            person_id = extrahiere_person_id(r3.text)

            if not person_id:
                try:
                    r4 = http.get(f"{BASE_URL}/court-single-booking-flow",
                                  params={"module": MODULE, "court": "1", "courts": "1,2",
                                          "fromTime": "10:00", "toTime": "11:00",
                                          "date": jetzt_lokal().strftime("%m/%d/%Y")},
                                  timeout=10)
                    person_id = extrahiere_person_id(r4.text)
                except Exception:
                    pass

            if not person_id:
                for url in [f"{BASE_URL}/user/profile",
                            f"{BASE_URL}/user/my-bookings",
                            f"{BASE_URL}/account"]:
                    try:
                        rx = http.get(url, timeout=10)
                        person_id = extrahiere_person_id(rx.text)
                        if person_id:
                            break
                    except Exception:
                        continue

            if not person_id:
                person_id = extrahiere_person_id(r2.text)

            if not person_id:
                log.warning(f"[{k}] ⚠️ Person-ID konnte nicht ermittelt werden!")
            else:
                log.info(f"[{k}] PERSON_ID: {person_id}")

            az_set_multi(k, csrf_token=csrf_t, person_id=person_id,
                         letzter_logincheck=time.time())
            log.info(f"✅ [{k}] Login OK")
            return True
        log.error(f"❌ [{k}] Login fehlgeschlagen")
        return False
    except Exception as e:
        log.error(f"[{k}] Login: {e}")
        return False

def ist_eingeloggt(k: str) -> bool:
    jetzt_t = time.time()
    if jetzt_t - az_get(k, "letzter_logincheck") < LOGIN_CHECK_COOLDOWN:
        return True
    try:
        r = acc[k]["http"].get(f"{BASE_URL}/padel", timeout=10,
                               headers={"accept": "text/html,*/*",
                                        "x-requested-with": "XMLHttpRequest"})
        ok = (r.status_code == 200 and
              ("logout" in r.text.lower() or "abmelden" in r.text.lower()))
        if ok:
            az_set(k, "letzter_logincheck", time.time())
        return ok
    except Exception:
        return False

def stelle_session_sicher(k: str) -> bool:
    if not ist_eingeloggt(k):
        senden(f"🔑 [{k}] Session abgelaufen, logge neu ein…")
        ok = einloggen(k)
        senden(f"✅ [{k}] Neu eingeloggt!" if ok else f"❌ [{k}] Login fehlgeschlagen!")
        return ok
    return True

def _session_refresh_vor_aktion(k: str, kontext: str = "") -> bool:
    log.info(f"[{k}] Session-Refresh vor: {kontext}")
    ok = einloggen(k)
    if not ok:
        log.error(f"[{k}] ❌ Session-Refresh fehlgeschlagen ({kontext})")
        senden(f"❌ [{k}] Neu-Login fehlgeschlagen vor: {kontext}")
    return ok

# ══════════════════════════════════════════════
# SLOT-BERECHNUNG
# ══════════════════════════════════════════════

def floor_to_30min(dt: datetime) -> datetime:
    return dt.replace(minute=(dt.minute // 30) * 30, second=0, microsecond=0)

def hole_reservierungen(k: str, datum_api: str) -> list:
    try:
        r = acc[k]["http"].get(f"{BASE_URL}/padel",
                               params={"timestamp": "", "currentDate": datum_api},
                               headers={"accept": "application/json, text/javascript, */*; q=0.01",
                                        "x-requested-with": "XMLHttpRequest",
                                        "referer": f"{BASE_URL}/padel"},
                               timeout=10)
        return r.json().get("reservations", []) if r.status_code == 200 else []
    except Exception as e:
        log.error(f"[{k}] Reservierungen: {e}")
        return []

def berechne_freie_slots(k: str, datum_de: str, dauer_min: int,
                         ignoriere_booking_id: int = None) -> list:
    datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
    datum_api = datum_obj.strftime("%m/%d/%Y")
    jetzt     = jetzt_lokal()
    res       = hole_reservierungen(k, datum_api)

    if ignoriere_booking_id:
        res = [r for r in res if r.get("booking") != ignoriere_booking_id
               and r.get("bookingOrBlockingId") != ignoriere_booking_id]

    schluss       = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")
    letzter_start = schluss - timedelta(minutes=dauer_min)
    grenze        = jetzt + timedelta(days=7)

    freie = []
    for court in [2, 1]:
        belegt = [(datetime.strptime(r["fromTime"], "%H:%M"),
                   datetime.strptime(r["toTime"],   "%H:%M"))
                  for r in res if r["court"] == court]
        t = datetime.strptime(ANLAGE_OEFFNUNG, "%H:%M")
        while t <= letzter_start:
            t_bis = t + timedelta(minutes=dauer_min)
            if t_bis > schluss:
                t += timedelta(minutes=30)
                continue
            slot_dt = datetime.combine(datum_obj.date(), t.time())
            if slot_dt > grenze:
                t += timedelta(minutes=30)
                continue
            if not any(not (t_bis <= bv or t >= bb) for bv, bb in belegt):
                freie.append({
                    "court":     court,
                    "fromTime":  t.strftime("%H:%M"),
                    "toTime":    t_bis.strftime("%H:%M"),
                    "dauer":     dauer_min,
                    "datum_api": datum_api,
                    "datum_de":  datum_de,
                    "key":       f"{datum_api}_{court}_{t.strftime('%H:%M')}_{dauer_min}",
                })
            t += timedelta(minutes=30)
    return freie

# ══════════════════════════════════════════════
# BUCHUNG (mit Verifikation) – unverändert für Früh/Spät/Klassisch
# ══════════════════════════════════════════════

def buche_slot(k: str, slot: dict) -> bool:
    court     = str(slot["court"])
    from_t    = slot["fromTime"]
    to_t      = slot["toTime"]
    datum_de  = slot["datum_de"]
    datum_api = slot["datum_api"]
    snap      = az_snap(k, "csrf_token", "person_id", "http")
    csrf_t    = snap["csrf_token"]
    person_id = snap["person_id"]
    http      = snap["http"]

    if not person_id:
        log.warning(f"[{k}] Person-ID fehlt – versuche erneuten Login...")
        einloggen(k)
        person_id = az_get(k, "person_id")
        if not person_id:
            log.error(f"[{k}] Person-ID konnte nicht ermittelt werden – Buchung abgebrochen!")
            senden(f"❌ [{k}] Person-ID fehlt!\nManuell buchen: {BASE_URL}/padel")
            return False

    log.info(f"🎾 [{k}] Buche Court {court} | {datum_de} | {from_t}–{to_t}")
    h  = {"accept": "*/*", "x-ajax-call": "true", "x-csrf-token": csrf_t,
          "x-requested-with": "XMLHttpRequest",
          "referer": f"{BASE_URL}/padel?currentDate={datum_api}"}
    hp = {**h, "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
          "origin": BASE_URL}
    try:
        r1 = http.get(f"{BASE_URL}/court-single-booking-flow", headers=h,
                      params={"module": MODULE, "court": court, "courts": "1,2",
                              "fromTime": from_t, "toTime": to_t, "date": datum_api},
                      timeout=10)
        execution = "e1s1"
        m = re.search(r"execution=(e\d+s\d+)", r1.text)
        if m:
            execution = m.group(1)

        if not person_id:
            person_id = extrahiere_person_id(r1.text)
            if person_id:
                az_set(k, "person_id", person_id)

        r2 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                       params={"execution": execution, "_eventId": "next"},
                       data=(f"purchaseTemplate.repetition.date={datum_de}"
                             f"&purchaseTemplate.repetition.fromTime={from_t.replace(':', '%3A')}"
                             f"&purchaseTemplate.repetition.toTime={to_t.replace(':', '%3A')}"
                             f"&bookingModel.courts%5B0%5D={court}"
                             f"&purchaseTemplate.court={court}"
                             f"&purchaseTemplate.person={person_id}"
                             f"&purchaseTemplate.bookingType={BOOKING_TYPE}"
                             f"&_csrf={csrf_t}"),
                       timeout=10)
        exec2 = execution.replace("s1", "s2")
        m2 = re.search(r"execution=(e\d+s\d+)", r2.text)
        if m2:
            exec2 = m2.group(1)

        r3 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                       params={"execution": exec2, "_eventId": "commit"},
                       data=f"purchaseTemplate.comment=&_csrf={csrf_t}",
                       timeout=10)

        if r3.status_code not in [200, 302]:
            return False
        if any(w in r3.text.lower() for w in ["fehler", "error", "nicht möglich"]):
            log.warning(f"[{k}] Buchung: Server-Fehler")
            return False

        booking_id = None
        for pat in [r'"bookingId"\s*:\s*(\d+)', r'/bookings/(\d+)', r'booking[=_](\d+)']:
            mid = re.search(pat, r3.text)
            if mid:
                booking_id = int(mid.group(1))
                break

        time.sleep(1.0)
        verifiziert = False

        def _verifiziere_via_my_bookings() -> bool:
            nonlocal booking_id
            try:
                r_pages = http.get(
                    f"{BASE_URL}/user/my-bookings/total-pages",
                    params={"size": "20", "sort": ["serviceDate,desc", "id,desc"]},
                    headers={**h, "accept": "application/json, text/javascript, */*; q=0.01"},
                    timeout=10)
                if r_pages.status_code != 200:
                    return False
                total_pages = 1
                try:
                    raw = r_pages.json()
                    total_pages = int(raw) if isinstance(raw, (int, float, str)) else 1
                except Exception:
                    total_pages = 1
                total_pages = max(1, min(total_pages, 3))

                datum_obj_v = datetime.strptime(datum_de, "%d.%m.%Y")
                for page in range(total_pages):
                    r_page = http.get(
                        f"{BASE_URL}/user/my-bookings/page",
                        params={"page": str(page), "size": "20",
                                "sort": ["serviceDate,desc", "id,desc"]},
                        headers={**h, "accept": "text/html,*/*"},
                        timeout=10)
                    if r_page.status_code != 200:
                        break
                    soup  = BeautifulSoup(r_page.text, "html.parser")
                    karten = soup.find_all("div", class_=lambda c: c and
                                           "col-12" in c and "col-sm-6" in c)
                    if not karten:
                        karten = list({
                            tag.find_parent("div") for tag in
                            soup.find_all(attrs={"href": re.compile(r"/bookings/\d+")}) +
                            soup.find_all(attrs={"data-target": re.compile(r"/bookings/\d+")})
                            if tag.find_parent("div")
                        })
                    if not karten:
                        karten = [soup]
                    for karte in karten:
                        if karte.find(class_=lambda c: c and
                                      ("badge-danger" in c or "cancelled" in c or
                                       "storniert" in c)):
                            continue
                        text = karte.get_text(" ", strip=True)
                        dm = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
                        if not dm or dm.group(1) != datum_de:
                            continue
                        zm = re.search(
                            r"(?:von\s+)?(\d{1,2}:\d{2})\s*(?:Uhr\s+)?(?:bis|–|-)\s*(\d{1,2}:\d{2})",
                            text, re.I)
                        if not zm:
                            continue
                        f_str = zm.group(1).zfill(5)
                        t_str = zm.group(2).zfill(5)
                        if f_str != from_t or t_str != to_t:
                            continue
                        cm = re.search(r"[Cc]ourt\s*(\d+)", text)
                        if not cm or int(cm.group(1)) != int(court):
                            continue
                        for pa in ["data-target", "href", "data-url", "action"]:
                            for tag in karte.find_all(attrs={pa: re.compile(r"/bookings/\d+")}):
                                m_bid = re.search(r"/bookings/(\d+)", tag.get(pa, ""))
                                if m_bid:
                                    booking_id = int(m_bid.group(1))
                                    break
                            if booking_id:
                                break
                        log.info(f"[{k}] Verifikation via my-bookings OK: "
                                 f"{datum_de} {from_t}–{to_t} Court {court} ID={booking_id}")
                        return True
            except Exception as ve:
                log.warning(f"[{k}] my-bookings Verifikation Fehler: {ve}")
            return False

        def _verifiziere_via_padel() -> bool:
            nonlocal booking_id
            try:
                pid = az_get(k, "person_id")
                server_res = hole_reservierungen(k, datum_api)
                for res in server_res:
                    if (res["court"] == int(court) and
                            res["fromTime"] == from_t and res["toTime"] == to_t):
                        res_bid = res.get("booking") or res.get("bookingOrBlockingId")
                        res_pid = str(res.get("personId", res.get("person_id", "")))
                        if pid and res_pid and res_pid != str(pid):
                            log.warning(f"[{k}] /padel: Slot belegt, aber andere Person-ID "
                                        f"({res_pid} != {pid}) – jemand war schneller!")
                            return False
                        if booking_id and res_bid and res_bid == booking_id:
                            log.info(f"[{k}] Verifikation via /padel OK (booking_id Match)")
                            return True
                        elif not booking_id and res_bid:
                            booking_id = res_bid
                            log.info(f"[{k}] Verifikation via /padel OK (ID aus Server)")
                            return True
                        elif not res_bid:
                            log.info(f"[{k}] Verifikation via /padel OK (kein bid-Feld)")
                            return True
            except Exception as ve:
                log.warning(f"[{k}] /padel Verifikation Fehler: {ve}")
            return False

        verifiziert = _verifiziere_via_my_bookings()

        if not verifiziert:
            try:
                time.sleep(1.5)
                verifiziert = _verifiziere_via_my_bookings()
                if not verifiziert:
                    verifiziert = _verifiziere_via_padel()
            except Exception as ve2:
                log.warning(f"[{k}] Verifikations-Versuch 2 fehlgeschlagen: {ve2}")

        if not verifiziert:
            log.warning(f"[{k}] ⚠️ Buchung NICHT verifiziert – möglicherweise zwischengebucht!")
            az_set(k, "aktive_buchung", None)
            return False

        az_set(k, "aktive_buchung", {**slot, "court": int(court), "booking_id": booking_id})
        log.info(f"✅ [{k}] Buchung OK + verifiziert – ID: {booking_id}")
        return True
    except Exception as e:
        log.error(f"[{k}] Buchungsfehler: {e}")
        return False



# ══════════════════════════════════════════════
# NEU v10.3: prewarm_execution
# ══════════════════════════════════════════════

def prewarm_execution(k: str, slot: dict):
    """
    Feuert r1 (GET /court-single-booking-flow) EINMALIG und liefert
    (execution_id, csrf_token) für die spätere r2+r3-Sequenz zurück.

    Wird ~10s vor Zielzeit aufgerufen, damit zur Zielzeit nur noch
    r2+r3 gefeuert werden müssen → ~200ms statt ~500ms im heißen Pfad.

    Returns: (execution_id: str|None, csrf_token: str|None)
    """
    court     = str(slot["court"])
    from_t    = slot["fromTime"]
    to_t      = slot["toTime"]
    datum_api = slot["datum_api"]
    http      = az_get(k, "http")
    csrf_t    = az_get(k, "csrf_token")

    h = {"accept": "*/*", "x-ajax-call": "true", "x-csrf-token": csrf_t,
         "x-requested-with": "XMLHttpRequest",
         "referer": f"{BASE_URL}/padel?currentDate={datum_api}"}
    try:
        r1 = http.get(f"{BASE_URL}/court-single-booking-flow", headers=h,
                      params={"module": MODULE, "court": court, "courts": "1,2",
                              "fromTime": from_t, "toTime": to_t, "date": datum_api},
                      timeout=10)
        if r1.status_code != 200:
            log.warning(f"[{k}] Pre-warm Court {court}: HTTP {r1.status_code}")
            return (None, None)
        m = re.search(r"execution=(e\d+s\d+)", r1.text)
        if not m:
            log.warning(f"[{k}] Pre-warm Court {court}: kein execution-Token gefunden")
            return (None, None)
        execution = m.group(1)
        fresh_csrf = hole_csrf(r1.text) or csrf_t
        log.info(f"⚡ [{k}] Pre-warm Court {court} OK: execution={execution}")
        return (execution, fresh_csrf)
    except Exception as e:
        log.warning(f"[{k}] Pre-warm Court {court}: {e}")
        return (None, None)


# ══════════════════════════════════════════════
# NEU v10.3: buche_slot_blitz
# ══════════════════════════════════════════════

def buche_slot_blitz(k: str, slot: dict,
                     prewarm_exec: str = None, prewarm_csrf: str = None,
                     verify_person_id: bool = True) -> tuple:
    """
    Hyper-schnelle Buchung mit optionaler Pre-warm-Optimierung.

    Wenn prewarm_exec gegeben: NUR r2+r3 (heißer Pfad, ~200ms).
    Sonst: voller r1+r2+r3 Flow (~500ms).

    Optional: Person-ID-Verifikation gegen /padel → erkennt fremde Buchungen.

    WICHTIG: Setzt aktive_buchung NICHT direkt → Caller entscheidet!
             (Thread-Safety bei parallelen Court-Threads.)

    Returns: (success: bool, info: dict|None)
        info = {"court": int, "datum_de": str, "fromTime": str,
                "toTime": str, "datum_api": str, "booking_id": int|None}
    """
    court     = str(slot["court"])
    from_t    = slot["fromTime"]
    to_t      = slot["toTime"]
    datum_de  = slot["datum_de"]
    datum_api = slot["datum_api"]
    snap      = az_snap(k, "csrf_token", "person_id", "http")
    csrf_t    = prewarm_csrf or snap["csrf_token"]
    person_id = snap["person_id"]
    http      = snap["http"]

    if not person_id:
        log.error(f"[{k}] Blitz: Person-ID fehlt – Buchung abgebrochen!")
        return (False, None)

    h  = {"accept": "*/*", "x-ajax-call": "true", "x-csrf-token": csrf_t,
          "x-requested-with": "XMLHttpRequest",
          "referer": f"{BASE_URL}/padel?currentDate={datum_api}"}
    hp = {**h, "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
          "origin": BASE_URL}

    try:
        # Phase 1: r1 nur wenn KEIN pre-warm vorhanden
        if prewarm_exec:
            execution = prewarm_exec
        else:
            r1 = http.get(f"{BASE_URL}/court-single-booking-flow", headers=h,
                          params={"module": MODULE, "court": court, "courts": "1,2",
                                  "fromTime": from_t, "toTime": to_t,
                                  "date": datum_api},
                          timeout=10)
            m = re.search(r"execution=(e\d+s\d+)", r1.text)
            execution = m.group(1) if m else "e1s1"

        # Phase 2: r2 (advance to s2 mit Buchungsdetails)
        r2 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                       params={"execution": execution, "_eventId": "next"},
                       data=(f"purchaseTemplate.repetition.date={datum_de}"
                             f"&purchaseTemplate.repetition.fromTime={from_t.replace(':', '%3A')}"
                             f"&purchaseTemplate.repetition.toTime={to_t.replace(':', '%3A')}"
                             f"&bookingModel.courts%5B0%5D={court}"
                             f"&purchaseTemplate.court={court}"
                             f"&purchaseTemplate.person={person_id}"
                             f"&purchaseTemplate.bookingType={BOOKING_TYPE}"
                             f"&_csrf={csrf_t}"),
                       timeout=10)
        if r2.status_code not in [200, 302]:
            return (False, None)
        m2 = re.search(r"execution=(e\d+s\d+)", r2.text)
        exec2 = m2.group(1) if m2 else execution.replace("s1", "s2")

        # Phase 3: r3 (commit)
        r3 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                       params={"execution": exec2, "_eventId": "commit"},
                       data=f"purchaseTemplate.comment=&_csrf={csrf_t}",
                       timeout=10)
        if r3.status_code not in [200, 302]:
            return (False, None)
        if any(w in r3.text.lower() for w in ["fehler", "error", "nicht möglich"]):
            return (False, None)

        # booking_id extrahieren (best effort)
        booking_id = None
        for pat in [r'"bookingId"\s*:\s*(\d+)', r'/bookings/(\d+)', r'booking[=_](\d+)']:
            mid = re.search(pat, r3.text)
            if mid:
                booking_id = int(mid.group(1))
                break

        info = {"court": int(court), "datum_de": datum_de, "fromTime": from_t,
                "toTime": to_t, "datum_api": datum_api, "booking_id": booking_id,
                "dauer": slot.get("dauer"), "key": slot.get("key")}

        # Person-ID Verifikation (erkennt fremde Buchung!)
        if verify_person_id:
            try:
                server_res = hole_reservierungen(k, datum_api)
                gefunden = False
                for res in server_res:
                    if (res["court"] == int(court) and
                            res["fromTime"] == from_t and res["toTime"] == to_t):
                        res_pid = str(res.get("personId", res.get("person_id", "")))
                        if res_pid and str(res_pid) != str(person_id):
                            log.warning(f"❌ [{k}] Blitz Court {court}: "
                                        f"FREMDE Person-ID ({res_pid} != {person_id}) – "
                                        f"Jemand war schneller!")
                            return (False, None)
                        res_bid = res.get("booking") or res.get("bookingOrBlockingId")
                        if res_bid and not booking_id:
                            info["booking_id"] = res_bid
                        gefunden = True
                        break
                if not gefunden:
                    log.warning(f"⚠️ [{k}] Blitz Court {court}: r3 OK aber Slot nicht "
                                f"in Reservierungen – möglicher false positive")
                    return (False, None)
            except Exception as ve:
                log.warning(f"[{k}] Blitz-Verifikation Fehler: {ve} – vertraue r3")

        log.info(f"⚡ [{k}] Blitz-Treffer Court {court}: {datum_de} {from_t}–{to_t} "
                 f"ID={info['booking_id']}")
        return (True, info)
    except Exception as e:
        log.error(f"[{k}] Blitz Court {court}: {e}")
        return (False, None)



# ══════════════════════════════════════════════
# STORNIERUNG
# ══════════════════════════════════════════════

def storniere_buchung(k: str, booking_id: int = None) -> bool:
    if booking_id is None:
        aktiv = az_get(k, "aktive_buchung")
        if not aktiv or not aktiv.get("booking_id"):
            log.warning(f"[{k}] Stornierung: keine booking_id verfügbar")
            return False
        booking_id = aktiv["booking_id"]

    snap   = az_snap(k, "csrf_token", "http")
    csrf_t = snap["csrf_token"]
    http   = snap["http"]

    h  = {"accept": "*/*", "x-ajax-call": "true", "x-csrf-token": csrf_t,
          "x-requested-with": "XMLHttpRequest",
          "referer": f"{BASE_URL}/user/my-bookings"}
    hp = {**h, "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
          "origin": BASE_URL}

    log.info(f"🗑️ [{k}] Storniere Buchung {booking_id}")
    try:
        r = http.post(f"{BASE_URL}/bookings/{booking_id}/cancel-flow",
                      headers=hp, data=f"_csrf={csrf_t}", timeout=10)
        execution = "e1s1"
        m = re.search(r"execution=(e\d+s\d+)", r.text)
        if m:
            execution = m.group(1)

        r2 = http.post(f"{BASE_URL}/bookings/{booking_id}/cancel-flow",
                       headers=hp,
                       params={"execution": execution, "_eventId": "confirm"},
                       data=(f"confirmKey={CONFIRM_KEY}"
                             f"&confirmValue=true&_csrf={csrf_t}"),
                       timeout=10)
        if r2.status_code in [200, 302]:
            log.info(f"✅ [{k}] Storno OK: {booking_id}")
            aktiv = az_get(k, "aktive_buchung")
            if aktiv and aktiv.get("booking_id") == booking_id:
                az_set(k, "aktive_buchung", None)
            return True
        log.error(f"[{k}] Storno: HTTP {r2.status_code}")
        return False
    except Exception as e:
        log.error(f"[{k}] Storno: {e}")
        return False


# ══════════════════════════════════════════════
# SYNC – v10.3 MIT expected_slot
# ══════════════════════════════════════════════

def sync_buchung_vom_server(k: str, expected_slot: dict = None,
                            debug_telegram: bool = False) -> bool:
    """
    Holt die aktuelle Buchung vom Server. Setzt aktive_buchung.

    v10.3 NEU: Wenn expected_slot gegeben, wird NUR eine Buchung
    akzeptiert die exakt diesem Slot entspricht (court+fromTime+toTime+datum).
    Verhindert dass alte/falsche Buchungen als die gerade gemachte erkannt werden.

    Returns: True wenn eine matching Buchung gefunden (und aktive_buchung gesetzt).
    """
    http = az_get(k, "http")
    try:
        r = http.get(f"{BASE_URL}/user/my-bookings/page",
                     params={"page": "0", "size": "20",
                             "sort": ["serviceDate,desc", "id,desc"]},
                     headers={"accept": "text/html,*/*",
                              "x-requested-with": "XMLHttpRequest"},
                     timeout=10)
        if r.status_code != 200:
            return False
        soup   = BeautifulSoup(r.text, "html.parser")
        karten = soup.find_all("div", class_=lambda c: c and
                               "col-12" in c and "col-sm-6" in c)
        if not karten:
            karten = [soup]

        jetzt = jetzt_lokal()
        gefundene = []
        for karte in karten:
            if karte.find(class_=lambda c: c and
                          ("badge-danger" in c or "cancelled" in c or
                           "storniert" in c)):
                continue
            text = karte.get_text(" ", strip=True)
            dm = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
            if not dm:
                continue
            datum_de  = dm.group(1)
            try:
                datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
            except Exception:
                continue
            zm = re.search(
                r"(?:von\s+)?(\d{1,2}:\d{2})\s*(?:Uhr\s+)?(?:bis|–|-)\s*(\d{1,2}:\d{2})",
                text, re.I)
            if not zm:
                continue
            from_str = zm.group(1).zfill(5)
            to_str   = zm.group(2).zfill(5)
            cm = re.search(r"[Cc]ourt\s*(\d+)", text)
            if not cm:
                continue
            court = int(cm.group(1))

            # Nur zukünftige Buchungen
            try:
                slot_end = datetime.combine(
                    datum_obj.date(),
                    datetime.strptime(to_str, "%H:%M").time())
                if slot_end < jetzt:
                    continue
            except Exception:
                pass

            # v10.3: Filter auf expected_slot
            if expected_slot:
                if (datum_de != expected_slot.get("datum_de") or
                        from_str  != expected_slot.get("fromTime") or
                        to_str    != expected_slot.get("toTime")  or
                        court     != int(expected_slot.get("court", -1))):
                    continue

            booking_id = None
            for pa in ["data-target", "href", "data-url", "action"]:
                for tag in karte.find_all(attrs={pa: re.compile(r"/bookings/\d+")}):
                    m_bid = re.search(r"/bookings/(\d+)", tag.get(pa, ""))
                    if m_bid:
                        booking_id = int(m_bid.group(1))
                        break
                if booking_id:
                    break

            try:
                dauer = int((datetime.strptime(to_str, "%H:%M") -
                             datetime.strptime(from_str, "%H:%M")).total_seconds() // 60)
            except Exception:
                dauer = 60

            gefundene.append({
                "court": court, "fromTime": from_str, "toTime": to_str,
                "datum_de": datum_de,
                "datum_api": datum_obj.strftime("%m/%d/%Y"),
                "dauer": dauer, "booking_id": booking_id,
                "key": f"{datum_obj.strftime('%m/%d/%Y')}_{court}_{from_str}_{dauer}",
                "_slot_start": datetime.combine(
                    datum_obj.date(),
                    datetime.strptime(from_str, "%H:%M").time()),
            })

        if not gefundene:
            if expected_slot:
                if debug_telegram:
                    senden(f"⚠️ [{k}] Sync: keine matching Buchung gefunden "
                           f"für {expected_slot.get('datum_de')} "
                           f"{expected_slot.get('fromTime')}–{expected_slot.get('toTime')} "
                           f"C{expected_slot.get('court')}")
                return False
            # Kein expected_slot und nichts gefunden → reset aktive_buchung
            az_set(k, "aktive_buchung", None)
            return False

        # Nächste (zeitlich frühste) Buchung wählen
        gefundene.sort(key=lambda b: b["_slot_start"])
        winner = gefundene[0]
        winner.pop("_slot_start", None)
        az_set(k, "aktive_buchung", winner)
        if debug_telegram:
            senden(f"🔄 [{k}] Sync: Buchung {winner['datum_de']} "
                   f"{winner['fromTime']}–{winner['toTime']} C{winner['court']} "
                   f"(ID={winner['booking_id']})")
        return True
    except Exception as e:
        log.warning(f"[{k}] Sync: {e}")
        return False



# ══════════════════════════════════════════════
# AGGRESSIV BUCHEN 07:00 (Früh-Methode) – unverändert
# ══════════════════════════════════════════════

def _aggressiv_buchen_07(k: str, datum_de: str, datum_api: str,
                          dauer_min: int, bevorzugter_court: int = 0) -> bool:
    """
    Bucht exklusiv den 07:00-Slot am 7-Tage-Tag mit ~2s Dauerbeschuss.
    Fallback: berechne_freie_slots → frühester freier Slot.
    """
    log.info(f"🌅 [{k}] Früh-Methode: 07:00 Exklusiv-Beschuss")
    senden(f"🌅 [{k}] 07:00 Dauerbeschuss läuft…")

    # Reihenfolge der Courts
    if bevorzugter_court == 1:
        courts = [1, 2]
    else:
        courts = [2, 1]

    deadline = time.time() + 2.5
    versuche = 0
    while time.time() < deadline and versuche < FRUEH_EXKLUSIV_VERSUCHE:
        for court in courts:
            slot = {
                "court": court, "fromTime": "07:00", "toTime":
                    (datetime.strptime("07:00", "%H:%M") +
                     timedelta(minutes=dauer_min)).strftime("%H:%M"),
                "datum_de": datum_de, "datum_api": datum_api,
                "dauer": dauer_min,
                "key": f"{datum_api}_{court}_07:00_{dauer_min}",
            }
            if buche_slot(k, slot):
                log.info(f"🎯 [{k}] Früh-Treffer 07:00 Court {court}")
                senden(f"🎯 [{k}] 07:00 GEBUCHT Court {court}!")
                return True
        versuche += 1
        time.sleep(0.05)

    # Fallback: frühester freier Slot
    log.info(f"[{k}] 07:00 verpasst – Fallback frühester Slot")
    freie = berechne_freie_slots(k, datum_de, dauer_min)
    if not freie:
        log.warning(f"[{k}] Keine freien Slots im Fallback!")
        return False

    # Sortiere nach Uhrzeit, bevorzuge angegeben Court
    def _sort_key(s):
        court_pref = 0 if s["court"] == (bevorzugter_court or 2) else 1
        return (s["fromTime"], court_pref)
    freie.sort(key=_sort_key)

    for slot in freie[:5]:
        if buche_slot(k, slot):
            log.info(f"✅ [{k}] Fallback-Treffer {slot['fromTime']} Court {slot['court']}")
            senden(f"✅ [{k}] Fallback gebucht: {slot['fromTime']} Court {slot['court']}")
            return True

    return False


# ══════════════════════════════════════════════
# AGGRESSIV BUCHEN AB ZEIT – v10.3 BLITZ + PARALLEL
# ══════════════════════════════════════════════

def _aggressiv_buchen_ab(k: str, datum_de: str, datum_api: str,
                          dauer_min: int, ab_dt: datetime,
                          bis_dt: datetime = None,
                          bevorzugter_court: int = 0) -> bool:
    """
    v10.3 BLITZ: Bucht ab gegebener Zeit – mit Pre-warm + parallelen Courts.

    Ablauf:
      1. Pre-check: hat Account schon eine matching Buchung? → fertig
      2. T-10s: Pre-warm r1 für Court 2 UND Court 1 parallel
      3. T-0:   Feuere r2+r3 auf BEIDEN Courts gleichzeitig in 2 Threads
      4. 1 Treffer → fertig
      5. 2 Treffer → behalte bevorzugten Court, storniere automatisch den anderen
                     (one-per-account constraint!)
      6. 0 Treffer → serielles Fallback-Hämmern (max AGGRESSIVE_TIMEOUT)

    ab_dt enthält das volle datetime (Datum + Uhrzeit ab wann buchbar).
    """
    # Berechne das Ziel-Datetime (volles datum + ab_dt time)
    jetzt = jetzt_lokal()
    if ab_dt.year < 2000:
        # Nur Uhrzeit-Component – an heute anhängen
        buchbar_dt = datetime.combine(jetzt.date(), ab_dt.time())
        if buchbar_dt < jetzt:
            buchbar_dt += timedelta(days=1)
    else:
        buchbar_dt = ab_dt

    # Ziel-Zeitfenster berechnen
    schluss       = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")
    target_from   = floor_to_30min(buchbar_dt)
    target_to_dt  = target_from + timedelta(minutes=dauer_min)
    if target_to_dt.time() > schluss.time():
        log.warning(f"[{k}] Slot übersteigt Anlagen-Schluss – abbruch")
        senden(f"❌ [{k}] Slot {target_from.strftime('%H:%M')} +{dauer_min}m über {ANLAGE_SCHLUSS}!")
        return False

    from_t = target_from.strftime("%H:%M")
    to_t   = target_to_dt.strftime("%H:%M")

    # Court-Reihenfolge (bevorzugt zuerst)
    if bevorzugter_court == 1:
        courts_order = [1, 2]
    else:
        courts_order = [2, 1]

    # Slot-Objekte für beide Courts
    slots = {}
    for court in courts_order:
        slots[court] = {
            "court": court, "fromTime": from_t, "toTime": to_t,
            "datum_de": datum_de, "datum_api": datum_api,
            "dauer": dauer_min,
            "key": f"{datum_api}_{court}_{from_t}_{dauer_min}",
        }

    # ─────────────── Pre-Check (one-per-account) ───────────────
    try:
        if sync_buchung_vom_server(k, expected_slot=slots[courts_order[0]]):
            log.info(f"✅ [{k}] Slot bereits gebucht – nichts zu tun")
            return True
        # Auch den zweiten Court probieren
        if sync_buchung_vom_server(k, expected_slot=slots[courts_order[1]]):
            log.info(f"✅ [{k}] Slot (Court {courts_order[1]}) bereits gebucht")
            return True
    except Exception:
        pass

    # ─────────────── Phase 1: Warte bis T-10s ───────────────
    prewarm_dt = buchbar_dt - timedelta(seconds=BLITZ_PREWARM_SECONDS)
    log.info(f"⚡ [{k}] BLITZ Ziel={buchbar_dt.strftime('%H:%M:%S')} "
             f"Pre-warm bei {prewarm_dt.strftime('%H:%M:%S')} "
             f"Slot {from_t}–{to_t}")
    senden(f"⚡ [{k}] BLITZ-Buchung: {datum_de} {from_t}–{to_t}\n"
           f"   Pre-warm @ {prewarm_dt.strftime('%H:%M:%S')}\n"
           f"   Feuer @ {buchbar_dt.strftime('%H:%M:%S')}\n"
           f"   v10.3.3: Pre-warm + Parallel + Multi-Shot")

    while jetzt_lokal() < prewarm_dt:
        if not az_get(k, "schiebe_aktiv") and not az_get(k, "sniper_aktiv"):
            # Direkt-Modus startet nur via _schiebe_intern – beide Flags prüfen
            # Falls user manuell stoppt:
            pass
        rest = (prewarm_dt - jetzt_lokal()).total_seconds()
        time.sleep(min(rest, 1.0) if rest > 1.0 else max(rest, 0.0))
        if rest <= 0:
            break

    # ─────────────── Phase 2: Pre-warm BEIDE Courts parallel ───────────────
    prewarm_results = {}
    prewarm_lock    = threading.Lock()

    def _do_prewarm(court):
        ex, csrf = prewarm_execution(k, slots[court])
        with prewarm_lock:
            prewarm_results[court] = (ex, csrf)

    pw_threads = [threading.Thread(target=_do_prewarm, args=(c,), daemon=True)
                  for c in courts_order]
    for t in pw_threads:
        t.start()
    for t in pw_threads:
        t.join(timeout=8)

    # ─────────────── Phase 3: Warte präzise bis T-0 ───────────────
    fire_dt = buchbar_dt + timedelta(milliseconds=BLITZ_FIRE_OFFSET_MS)
    while jetzt_lokal() < fire_dt:
        rest = (fire_dt - jetzt_lokal()).total_seconds()
        if rest > 0.5:
            time.sleep(0.1)
        elif rest > 0.05:
            time.sleep(0.01)
        elif rest > 0:
            time.sleep(0.001)
        else:
            break

    # ─────────────── Phase 4: MULTI-SHOT FEUER (v10.3.3, R18) ───────────────
    log.info(f"🔥 [{k}] BLITZ MULTI-SHOT START bei "
             f"{jetzt_lokal().strftime('%H:%M:%S.%f')[:-3]} "
             f"({MULTI_SHOT_COUNT} Bursts)")

    def _fire_burst(burst_idx: int, pw_per_court: dict) -> dict:
        """Feuert eine Burst (parallele r2+r3 auf alle Courts).
        pw_per_court: {court: (exec, csrf)} oder leeres dict für fresh r1+r2+r3.
        Returns: {court: (ok, info)}"""
        results = {}
        lock = threading.Lock()

        def _do_blitz(court):
            pw_ex, pw_csrf = pw_per_court.get(court, (None, None))
            ok, info = buche_slot_blitz(k, slots[court],
                                         prewarm_exec=pw_ex,
                                         prewarm_csrf=pw_csrf,
                                         verify_person_id=True)
            with lock:
                results[court] = (ok, info)

        threads = [threading.Thread(target=_do_blitz, args=(c,), daemon=True)
                   for c in courts_order]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        return results

    blitz_results = {}
    treffer = []
    for burst in range(MULTI_SHOT_COUNT):
        # Stopp-Signal prüfen
        if not az_get(k, "schiebe_aktiv") and not az_get(k, "sniper_aktiv"):
            break

        # Burst 0 nutzt Pre-warm-Token; danach jeder Burst macht fresh r1+r2+r3
        pw_for_burst = prewarm_results if burst == 0 else {}

        burst_start = jetzt_lokal()
        log.info(f"🔥 [{k}] Burst {burst+1}/{MULTI_SHOT_COUNT} "
                 f"@ {burst_start.strftime('%H:%M:%S.%f')[:-3]}"
                 f"{' (pre-warmed)' if burst == 0 else ''}")

        blitz_results = _fire_burst(burst, pw_for_burst)
        treffer = [(c, info) for c, (ok, info) in blitz_results.items()
                   if ok and info]

        if treffer:
            # Treffer! → raus aus dem Burst-Loop
            break

        # Verfehlt – kurze Pause, dann nächster Burst
        if burst < MULTI_SHOT_COUNT - 1:
            log.info(f"[{k}] Burst {burst+1} verfehlt – warte "
                     f"{MULTI_SHOT_GAP_MS}ms")
            time.sleep(MULTI_SHOT_GAP_MS / 1000.0)

    # ─────────────── Phase 5: Auswertung ───────────────
    if len(treffer) == 1:
        court, info = treffer[0]
        az_set(k, "aktive_buchung", info)
        log.info(f"🎯 [{k}] BLITZ-Treffer Court {court}: {from_t}–{to_t}")
        senden(f"🎯 [{k}] BLITZ-Treffer!\n   Court {court} | {from_t}–{to_t}")
        return True

    if len(treffer) >= 2:
        # one-per-account (R1): Server SOLLTE das verhindern. Falls doch
        # beide durchkommen (Server-Race), ist das hier das Sicherheitsnetz.
        treffer.sort(key=lambda x: 0 if x[0] == (bevorzugter_court or 2) else 1)
        keep_court, keep_info = treffer[0]
        az_set(k, "aktive_buchung", keep_info)
        log.warning(f"⚠️ [{k}] DOPPEL-TREFFER (Server-Race)! Behalte Court {keep_court}")
        senden(f"⚠️ [{k}] DOPPEL-TREFFER (sehr selten – Server-Race)!\n"
               f"   Behalte Court {keep_court}\n"
               f"   Storniere zweite Buchung…")
        for court, info in treffer[1:]:
            if info.get("booking_id"):
                try:
                    storniere_buchung(k, info["booking_id"])
                except Exception as e:
                    log.error(f"[{k}] Auto-Storno Court {court}: {e}")
        # aktive_buchung könnte vom storno gelöscht worden sein → wieder setzen
        az_set(k, "aktive_buchung", keep_info)
        return True

    # ─────────────── Phase 6: Fallback – serielles Hämmern ───────────────
    log.warning(f"[{k}] Blitz verfehlt – Fallback serielles Hämmern")
    senden(f"⚠️ [{k}] Blitz verfehlt – Fallback läuft…")

    deadline = time.time() + AGGRESSIVE_TIMEOUT
    versuche = 0
    while time.time() < deadline:
        if not az_get(k, "schiebe_aktiv") and not az_get(k, "sniper_aktiv"):
            log.info(f"[{k}] Fallback abgebrochen (Stopp-Signal)")
            return False

        # Pre-check: haben wir schon einen Treffer durch parallele Race?
        for court in courts_order:
            if sync_buchung_vom_server(k, expected_slot=slots[court]):
                log.info(f"✅ [{k}] Fallback erkennt bereits gebuchten Slot")
                return True

        # Re-Login alle 50 Versuche
        if versuche > 0 and versuche % 50 == 0:
            if not _session_refresh_vor_aktion(k, "Aggressiv-Fallback"):
                senden(f"❌ [{k}] Fallback abgebrochen (Login-Fehler)")
                return False

        for court in courts_order:
            ok, info = buche_slot_blitz(k, slots[court],
                                         prewarm_exec=None, prewarm_csrf=None,
                                         verify_person_id=True)
            if ok and info:
                az_set(k, "aktive_buchung", info)
                log.info(f"✅ [{k}] Fallback-Treffer Court {court}")
                senden(f"✅ [{k}] Fallback gebucht: Court {court} {from_t}–{to_t}")
                return True

        versuche += 1
        time.sleep(AGGRESSIVE_INTERVAL)

    log.error(f"[{k}] Aggressiv-Timeout ({AGGRESSIVE_TIMEOUT}s) – nichts gebucht")
    senden(f"❌ [{k}] Timeout: Slot {from_t}–{to_t} nicht ergattert")
    return False



# ══════════════════════════════════════════════
# SCHIEBE PHASE 3 (Storno + Rebook) – UNVERÄNDERT
# ──────────────────────────────────────────────
# WICHTIG: schiebe_moment = datetime.combine(jetzt.date(), ...)
#          ← jetzt.date() = HEUTE, NICHT datum_obj.date()!
# ══════════════════════════════════════════════

def _schiebe_phase3(k: str, datum_de: str, datum_api: str, dauer_min: int, ziel_str: str):
    """
    Phase 3: Schrittweise schieben bis Zielzeit.

    Logik aus v11.0 übernommen (v10.3.3):
      - schiebe_moment basiert auf ende_dt - random_offset (5-20 Min)
        → KRITISCH: combine mit jetzt.date(), nicht datum_obj.date()! (R7)
      - Detaillierte Telegram-Updates vor jeder Wartephase und Aktion
      - Storno-Retry: 6× × 10s
      - Rebook-Loop: 30× × 0.1s mit alternierendem Court
      - Stunden-Session-Check während langer Wartephasen
    """
    datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
    ziel_dt   = datetime.strptime(ziel_str, "%H:%M")
    schluss   = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")

    def aktiv() -> bool:
        return az_get(k, "schiebe_aktiv")

    def schlafe(sek: float) -> bool:
        ende = time.time() + sek
        while time.time() < ende:
            if not aktiv():
                return False
            time.sleep(min(1, max(0, ende - time.time())))
        return True

    def beende(msg: str = ""):
        az_set(k, "schiebe_aktiv", False)
        if msg:
            senden(msg)
        zeige_account_menue(k)

    letzter_session_check = time.time()

    while aktiv():
        aktive_b = az_get(k, "aktive_buchung")
        if not aktive_b:
            log.warning(f"[{k}] Phase3: Keine aktive Buchung mehr.")
            break

        start_dt = datetime.strptime(aktive_b["fromTime"], "%H:%M")
        ende_dt  = datetime.strptime(aktive_b["toTime"],   "%H:%M")

        if start_dt >= ziel_dt:
            wetter_str = hole_wetter(aktive_b["datum_de"], aktive_b["fromTime"])
            beende(f"🎯 <b>[{k}] Zielzeit erreicht!</b>\n"
                   f"📅 {_datum_mit_tag(aktive_b['datum_de'])}\n"
                   f"🕐 {aktive_b['fromTime']}–{aktive_b['toTime']} Uhr\n"
                   f"🏟️ Court {aktive_b['court']}\n\nViel Spaß! 🎾"
                   + wetter_str)
            return

        jetzt = jetzt_lokal()
        random_offset  = random.randint(SCHIEBE_MINUTEN_VOR_MIN, SCHIEBE_MINUTEN_VOR_MAX)
        # ════════ KRITISCH R7: jetzt.date() – NICHT datum_obj.date()! ════════
        schiebe_moment = datetime.combine(
            jetzt.date(),
            (ende_dt - timedelta(minutes=random_offset)).time())
        # ════════════════════════════════════════════════════════════════════

        sek = (schiebe_moment - jetzt).total_seconds()

        if sek > 0:
            tage_r = int(sek // 86400)
            std_r  = int((sek % 86400) // 3600)
            min_r  = int((sek % 3600) // 60)
            if tage_r > 0:
                warte_str = f"{tage_r}T {std_r}h {min_r}min"
            elif std_r > 0:
                warte_str = f"{std_r}h {min_r}min"
            else:
                warte_str = f"{min_r}min"

            log.info(f"[{k}] Warte {sek:.0f}s bis {schiebe_moment.strftime('%d.%m.%Y %H:%M:%S')}")
            senden(f"⏳ [{k}] Nächstes Schieben um "
                   f"<b>{schiebe_moment.strftime('%d.%m.%Y %H:%M')} Uhr</b>\n"
                   f"   📅 {aktive_b['datum_de']} | "
                   f"{aktive_b['fromTime']}–{aktive_b['toTime']} | Court {aktive_b['court']}\n"
                   f"   ⏱️ Noch {warte_str}")

            while aktiv():
                restzeit = (schiebe_moment - jetzt_lokal()).total_seconds()
                if restzeit <= 90:
                    break
                chunk = min(restzeit - 90, 3600)
                if not schlafe(chunk):
                    return
                if time.time() - letzter_session_check > 3600:
                    if not ist_eingeloggt(k):
                        log.info(f"[{k}] Stunden-Check: Session abgelaufen – logge neu ein...")
                        if einloggen(k):
                            log.info(f"[{k}] Stunden-Check: Neu eingeloggt.")
                        else:
                            log.warning(f"[{k}] Stunden-Check: Neu-Login fehlgeschlagen.")
                    letzter_session_check = time.time()

            restzeit = (schiebe_moment - jetzt_lokal()).total_seconds()
            if restzeit > 2:
                if not schlafe(restzeit - 2):
                    return
            restzeit = (schiebe_moment - jetzt_lokal()).total_seconds()
            if restzeit > 0:
                time.sleep(restzeit)

        if not aktiv():
            return

        neuer_start = ende_dt - timedelta(minutes=30)
        neues_ende  = neuer_start + timedelta(minutes=dauer_min)
        booking_id  = aktive_b.get("booking_id")

        if neuer_start > ziel_dt:
            neuer_start = ziel_dt
            neues_ende  = neuer_start + timedelta(minutes=dauer_min)
        if neues_ende > schluss:
            beende(f"⚠️ [{k}] Nächster Slot würde nach 22:00 enden.\n"
                   f"✅ Behalte: {aktive_b['fromTime']}–{aktive_b['toTime']}")
            return

        naechster_von = neuer_start.strftime("%H:%M")
        naechster_bis = neues_ende.strftime("%H:%M")

        senden(f"⚡ <b>[{k}] Schiebe jetzt!</b>\n"
               f"🗑️ {aktive_b['fromTime']}–{aktive_b['toTime']} "
               f"→ {naechster_von}–{naechster_bis}")

        log.info(f"[{k}] Erzwungener Login vor Stornierung (Schiebe-Loop)...")
        if not _session_refresh_vor_aktion(k, f"Stornierung {aktive_b['fromTime']}"):
            senden(f"❌ [{k}] Session vor Stornierung fehlgeschlagen – retry in 10s.")
            if not schlafe(10):
                return
            continue

        # R9: STORNO VOR REBOOK!
        storno_ok = False
        for storno_versuch in range(6):
            if not aktiv():
                return
            if storniere_buchung(k, booking_id):
                storno_ok = True
                break
            log.warning(f"[{k}] Storno-Retry {storno_versuch+1}/6 (kein Telegram-Spam)")
            time.sleep(10)

        if not storno_ok:
            senden(f"❌ [{k}] Stornierung nach 6 Versuchen fehlgeschlagen – retry in 30s.\n"
                   f"Buchung bleibt: {aktive_b['fromTime']}–{aktive_b['toTime']}")
            if not schlafe(30):
                return
            continue

        # Sofort-Rebook nach Storno (30× × 0.1s, alternierender Court)
        neuer_slot    = {
            "fromTime":  naechster_von,
            "toTime":    naechster_bis,
            "dauer":     dauer_min,
            "datum_api": datum_api,
            "datum_de":  datum_de,
        }
        gerade_court  = aktive_b["court"]
        anderer_court = 1 if gerade_court == 2 else 2

        ok = False
        for versuch in range(30):
            if not aktiv():
                return
            court_v = gerade_court if versuch % 2 == 0 else anderer_court
            slot_v  = {**neuer_slot, "court": court_v,
                       "key": f"{datum_api}_{court_v}_{naechster_von}_{dauer_min}"}
            if buche_slot(k, slot_v):
                ok = True
                break
            time.sleep(0.1 if versuch < 15 else 0.5)

        letzter_session_check = time.time()

        if ok:
            gebuchter = az_get(k, "aktive_buchung")
            if not gebuchter:
                try:
                    sync_buchung_vom_server(k)
                    gebuchter = az_get(k, "aktive_buchung")
                except Exception:
                    pass

            eff_court = gebuchter["court"] if gebuchter else gerade_court
            ist_ziel  = (neuer_start >= ziel_dt)

            if ist_ziel:
                wetter_str = hole_wetter(datum_de, naechster_von)
                senden(f"✅ <b>[{k}] 🎯 Ziel erreicht!</b>\n"
                       f"📅 {_datum_mit_tag(datum_de)}\n"
                       f"🕐 {naechster_von}–{naechster_bis} | Court {eff_court}\n\nViel Spaß! 🎾"
                       + wetter_str)
                az_set(k, "schiebe_aktiv", False)
                zeige_account_menue(k)
                return
            else:
                senden(f"✅ <b>[{k}] Verschoben!</b>\n"
                       f"🕐 {naechster_von}–{naechster_bis} | Court {eff_court}\n"
                       f"🔄 Weiter → {ziel_str} Uhr...")
        else:
            beende(f"❌ [{k}] Neubuchung nach Stornierung fehlgeschlagen!\n"
                   f"🆘 SOFORT manuell buchen:\n{BASE_URL}/padel?currentDate={datum_api}")
            return

    zeige_account_menue(k)



# ══════════════════════════════════════════════
# SCHIEBE-INTERNAL – v10.3.3 (Blitz-Start beibehalten)
# ══════════════════════════════════════════════

def _schiebe_intern(k: str):
    """
    Hauptlogik der Schiebe-Taktik.

    Direkt-Branch (v10.3.x):
      - KEIN spam_start_dt = buchbar_dt - 1s mehr.
      - Login bei T-90s, dann _aggressiv_buchen_ab() → Blitz Multi-Shot.
      - Nach Treffer: _schiebe_phase3() mit detaillierten Status-Updates.

    Phase 3 nutzt das alte ende_dt - random_offset System (v11.0).
    """
    log.info(f"🔄 [{k}] Schiebe-Loop gestartet")
    datum_de   = az_get(k, "schiebe_datum")
    ziel_str   = az_get(k, "schiebe_ziel")
    dauer_min  = az_get(k, "schiebe_dauer") or 90
    modus      = az_get(k, "schiebe_modus") or "frueh"
    buchbar_ab = az_get(k, "schiebe_buchbar_ab")
    court      = az_get(k, "schiebe_court") or 0

    if not all([modus, datum_de, ziel_str, dauer_min]):
        log.error(f"[{k}] Schiebe: unvollständige Parameter")
        senden(f"❌ [{k}] Schiebe abgebrochen (Parameter fehlen)")
        az_set(k, "schiebe_aktiv", False)
        return

    datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
    datum_api = datum_obj.strftime("%m/%d/%Y")
    ziel_dt   = datetime.strptime(ziel_str, "%H:%M")
    schluss   = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")

    def aktiv() -> bool:
        return az_get(k, "schiebe_aktiv")

    def schlafe(sek: float) -> bool:
        ende = time.time() + sek
        while time.time() < ende:
            if not aktiv():
                return False
            time.sleep(min(1, max(0, ende - time.time())))
        return True

    def beende(msg: str = ""):
        az_set(k, "schiebe_aktiv", False)
        if msg:
            senden(msg)
        zeige_account_menue(k)

    # ── Phase 1: Warten auf 7-Tage-Fenster (frueh/direkt) ────────────────────
    if modus in ("frueh", "direkt"):
        while aktiv():
            jetzt   = jetzt_lokal()
            fenster = datetime.combine(
                (datum_obj - timedelta(days=7)).date(),
                datetime.strptime("07:00", "%H:%M").time())
            if jetzt >= fenster:
                break
            sek_bis = (fenster - jetzt).total_seconds()

            tage_r_w = int(sek_bis // 86400)
            std_r_w  = int((sek_bis % 86400) // 3600)
            min_r_w  = int((sek_bis % 3600) // 60)
            if tage_r_w > 0:
                warte_str_w = f"{tage_r_w}T {std_r_w}h {min_r_w}min"
            elif std_r_w > 0:
                warte_str_w = f"{std_r_w}h {min_r_w}min"
            else:
                warte_str_w = f"{min_r_w}min"

            senden(f"⏳ <b>[{k}] Wartet auf 7-Tage-Fenster</b>\n"
                   f"📅 {datum_de}\n"
                   f"🔓 Buchbar ab: {fenster.strftime('%d.%m.%Y um 07:00 Uhr')}\n"
                   f"⏱️ Noch {warte_str_w}")

            schlaf = min(sek_bis - 30, 23 * 3600)
            if schlaf > 1:
                if not schlafe(schlaf):
                    return
            else:
                if not schlafe(max(0, sek_bis)):
                    return
                break

    if not aktiv():
        return

    # ── Phase 2: Ersten Slot buchen ───────────────────────────────────────────
    erfolg = False

    if modus == "frueh":
        jetzt       = jetzt_lokal()
        fenster_tag = (datum_obj - timedelta(days=7)).date()
        start_07    = datetime.combine(fenster_tag,
                                       datetime.strptime("07:00", "%H:%M").time())
        login_zeitpunkt = start_07 - timedelta(seconds=90)

        if jetzt < login_zeitpunkt:
            sek_bis_login = (login_zeitpunkt - jetzt).total_seconds()
            senden(f"⏳ [{k}] Warte bis 06:58:30 Uhr (noch {int(sek_bis_login/60)} Min)...")
            if not schlafe(sek_bis_login):
                return
            senden(f"🔑 [{k}] Frischer Login – 90s vor 07:00 Uhr...")
            if not _session_refresh_vor_aktion(k, "Früh-Methode 06:58:30"):
                beende(f"❌ [{k}] Login vor 07:00 fehlgeschlagen!")
                return
            senden(f"✅ [{k}] Eingeloggt – warte auf exakt 07:00:00 Uhr...")
            restzeit = (start_07 - jetzt_lokal()).total_seconds()
            if restzeit > 0:
                time.sleep(restzeit)

        elif jetzt < start_07:
            senden(f"🔑 [{k}] Frischer Login (weniger als 90s bis 07:00)...")
            if not _session_refresh_vor_aktion(k, "Früh-Methode <90s"):
                beende(f"❌ [{k}] Login fehlgeschlagen!")
                return
            senden(f"✅ [{k}] Eingeloggt – warte auf exakt 07:00:00 Uhr...")
            restzeit = (start_07 - jetzt_lokal()).total_seconds()
            if restzeit > 0:
                time.sleep(restzeit)

        else:
            senden(f"🔑 [{k}] Frischer Login vor Dauerbeschuss (07:00 bereits vorbei)...")
            if not _session_refresh_vor_aktion(k, "Früh-Methode sofort"):
                beende(f"❌ [{k}] Login fehlgeschlagen!")
                return

        senden(f"🌅 <b>[{k}] Früh-Methode – Dauerbeschuss startet!</b>\n"
               f"📅 {datum_de} | 07:00 Uhr | {dauer_min} Min\n"
               f"🔫 ~2s exklusiv Court 2→1 auf 07:00, dann Fallback auf frühesten freien Slot")

        erfolg = _aggressiv_buchen_07(k, datum_de, datum_api, dauer_min, court)

        if not erfolg:
            beende(f"❌ [{k}] Kein Slot buchbar nach {AGGRESSIVE_TIMEOUT}s.")
            return

        buchung = az_get(k, "aktive_buchung")
        senden(f"✅ <b>[{k}] Früh-Slot gebucht!</b>\n"
               f"🕐 {buchung['fromTime']}–{buchung['toTime']} | Court {buchung['court']}\n"
               f"🔄 Schiebe Richtung {ziel_str} Uhr...")

    elif modus == "spaet":
        if not stelle_session_sicher(k):
            beende(f"❌ [{k}] Login fehlgeschlagen.")
            return
        senden(f"🕐 <b>[{k}] Spät-Taktik – analysiere bestehende Belegung...</b>\n"
               f"📅 {datum_de} | Ziel: {ziel_str} Uhr | {dauer_min} Min")

        for versuch in range(30):
            if not aktiv():
                return
            datum_api_z    = datum_obj.strftime("%m/%d/%Y")
            reservierungen = hole_reservierungen(k, datum_api_z)

            aktive_b_now = az_get(k, "aktive_buchung")
            eigene_id    = aktive_b_now.get("booking_id") if aktive_b_now else None
            endzeiten    = []
            for res in reservierungen:
                try:
                    res_end = datetime.strptime(res["toTime"], "%H:%M")
                    res_id  = res.get("booking") or res.get("bookingOrBlockingId")
                    if eigene_id and res_id == eigene_id:
                        continue
                    if res_end <= ziel_dt:
                        endzeiten.append(res_end)
                except Exception:
                    continue
            spaeteste_ende = min(endzeiten) if endzeiten else None

            freie = berechne_freie_slots(k, datum_de, dauer_min)
            alle_kandidaten = [
                s for s in freie
                if datetime.strptime(s["fromTime"], "%H:%M") < ziel_dt
                and datetime.strptime(s["toTime"], "%H:%M") <= schluss
            ]

            if not alle_kandidaten:
                log.info(f"[{k}] Spät: Kein freier Slot, Versuch {versuch+1}/30")
                if not schlafe(3):
                    return
                continue

            if spaeteste_ende:
                kandidaten_ab_ende = [
                    s for s in alle_kandidaten
                    if datetime.strptime(s["fromTime"], "%H:%M") >= spaeteste_ende
                ]
                if kandidaten_ab_ende:
                    kandidaten_ab_ende_sorted = sorted(
                        kandidaten_ab_ende,
                        key=lambda s: (s["fromTime"], 0 if s["court"] == 2 else 1)
                    )
                    bester = kandidaten_ab_ende_sorted[0]
                else:
                    bester = sorted(
                        alle_kandidaten,
                        key=lambda s: (s["fromTime"], 0 if s["court"] == 2 else 1),
                        reverse=True
                    )[0]
            else:
                bester = sorted(
                    alle_kandidaten,
                    key=lambda s: (s["fromTime"], 0 if s["court"] == 2 else 1),
                    reverse=True
                )[0]

            start_info = (f"ab {spaeteste_ende.strftime('%H:%M')} Uhr"
                          if spaeteste_ende else "spätester freier Slot")
            if buche_slot(k, bester):
                buchung = az_get(k, "aktive_buchung")
                senden(f"✅ <b>[{k}] Startslot gebucht!</b>\n"
                       f"🕐 {buchung['fromTime']}–{buchung['toTime']} | Court {buchung['court']}\n"
                       f"📌 Eingestiegen: {start_info}\n"
                       f"🔄 Schiebe Richtung {ziel_str} Uhr...")
                erfolg = True
                break
            if not schlafe(3):
                return

        if not erfolg:
            beende(f"❌ [{k}] Kein buchbarer Slot gefunden.")
            return

    elif modus == "direkt":
        # v10.3.x: Blitz-Start via _aggressiv_buchen_ab (Pre-warm + Multi-Shot)
        if not buchbar_ab:
            beende(f"❌ [{k}] Keine Startzeit angegeben.")
            return

        jetzt        = jetzt_lokal()
        buchbar_zeit = datetime.strptime(buchbar_ab, "%H:%M").time()
        buchbar_dt   = datetime.combine(jetzt.date(), buchbar_zeit)
        if buchbar_dt < jetzt:
            buchbar_dt += timedelta(days=1)

        if jetzt < buchbar_dt:
            sek_wait = (buchbar_dt - jetzt).total_seconds()
            senden(f"🎯 <b>[{k}] Direkte Taktik – warte auf Startzeit</b>\n"
                   f"📅 {datum_de} | Buchbar ab heute {buchbar_ab} Uhr\n"
                   f"🎯 Ziel: {ziel_str} Uhr | {dauer_min} Min\n"
                   f"⏳ Noch {int(sek_wait/60)} Min bis {buchbar_ab} Uhr...")
            if not schlafe(max(0, sek_wait - 90)):
                return
            senden(f"🔑 [{k}] Frischer Login 90s vor {buchbar_ab} Uhr...")
            if not _session_refresh_vor_aktion(k, f"Direkt {buchbar_ab}"):
                beende(f"❌ [{k}] Login vor {buchbar_ab} fehlgeschlagen!")
                return
            senden(f"✅ [{k}] Eingeloggt – warte auf Blitz-Feuer @ {buchbar_ab} Uhr "
                   f"(Pre-warm + Parallel + Multi-Shot)")
        else:
            if not _session_refresh_vor_aktion(k, f"Direkt sofort ab {buchbar_ab}"):
                beende(f"❌ [{k}] Login fehlgeschlagen!")
                return

        # _aggressiv_buchen_ab macht das Pre-warm + Multi-Shot intern
        erfolg = _aggressiv_buchen_ab(k, datum_de, datum_api, dauer_min,
                                       buchbar_dt, None, court)

        if not erfolg:
            beende(f"❌ [{k}] Kein Slot ab {buchbar_ab} Uhr buchbar nach Blitz+Fallback.")
            return

        buchung = az_get(k, "aktive_buchung")
        senden(f"✅ <b>[{k}] Direkt-Slot gebucht!</b>\n"
               f"📅 {_datum_mit_tag(datum_de)}\n"
               f"🕐 {buchung['fromTime']}–{buchung['toTime']} | Court {buchung['court']}\n"
               f"🎯 Schiebe-Ziel: {ziel_str} Uhr\n"
               f"🔄 Schiebe Richtung {ziel_str} Uhr...")

    elif modus == "sniper":
        # Sniper-Fortsetzung: aktive_buchung sollte gesetzt sein
        if not az_get(k, "aktive_buchung"):
            beende(f"❌ [{k}] Sniper-Schiebe: keine aktive Buchung")
            return
        erfolg = True

    # ── Phase 3: Schrittweise schieben ───────────────────────────────────────
    if erfolg:
        _schiebe_phase3(k, datum_de, datum_api, dauer_min, ziel_str)

    az_set(k, "schiebe_aktiv", False)
    log.info(f"[{k}] Schiebe-Thread beendet")


# ══════════════════════════════════════════════
# SNIPER-INTERNAL – v10.3 (buche_slot_blitz statt _schnell)
# ══════════════════════════════════════════════

def _sniper_intern(k: str):
    """
    Sniper-Modus v10.3.3: SMART-LAUER.

    Wartet bis zum letzten 30-Min-Fenster vor der fremden Endzeit
    und hämmert dann gezielt auf den freiwerdenden Slot. Falls
    fremder NICHT storniert: bei genau fremder Endzeit Wechsel zu
    Multi-Shot-Blitz auf den nachfolgenden Slot (R20, R21).

    Beispiel: Max hat 21.05. 17:00–18:30 Court 2 gebucht.
        User-Eingabe: fremder_bis=18:30, dauer=90, court=2, ziel=18:30

      14:00 → User startet Sniper → Bot schläft 😴
      17:55 → Login-Refresh (5 Min vor Lauer-Start)
      18:00 → Lauer-Start. Hämmere "21.05. 18:00–19:30 Court 2"
              (= Maxes Slot; nur Treffer wenn Max storniert)
      18:15 → Max storniert → Bot trifft Slot 18:00–19:30 ✅
      ODER
      18:30 → Lauer-Ende, Max hat nicht storniert
              → Multi-Shot-Blitz auf "21.05. 18:30–20:00"
              (= jetzt frisch freigeschaltet durch 7-Tage-Regel R2)
    """
    snap         = az_snap(k, "sniper_datum", "sniper_court", "sniper_fremder_bis",
                           "sniper_dauer", "sniper_ziel")
    datum_de     = snap["sniper_datum"]
    court        = snap["sniper_court"]
    fremder_bis  = snap["sniper_fremder_bis"]
    dauer        = snap["sniper_dauer"]
    ziel         = snap["sniper_ziel"]

    if not all([datum_de, court, fremder_bis, dauer]):
        senden(f"❌ [{k}] Sniper: Parameter fehlen")
        az_set(k, "sniper_aktiv", False)
        return

    # ─── Berechne Zeitpunkte (R20, R21) ───
    datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
    datum_api = datum_obj.strftime("%m/%d/%Y")

    # Fremde Endzeit als volles datetime (Buchungstag + Endzeit)
    fremder_bis_time = datetime.strptime(fremder_bis, "%H:%M").time()
    fremde_endzeit_dt = datetime.combine(datum_obj.date(), fremder_bis_time)
    # → 7-Tage-Regel: heute zur gleichen Zeit ist der Slot ab fremder Endzeit
    #   buchbar. Lauer-Zeitpunkte beziehen sich also auf HEUTE, nicht
    #   auf den Buchungstag (analog R7 Schiebe-Logik).
    jetzt = jetzt_lokal()
    fremde_endzeit_heute = datetime.combine(jetzt.date(), fremder_bis_time)
    # Falls Zeit schon vorbei: morgen
    if fremde_endzeit_heute < jetzt:
        fremde_endzeit_heute += timedelta(days=1)

    lauer_start_dt = fremde_endzeit_heute - timedelta(minutes=SNIPER_PRE_END_MINUTES)
    login_dt       = lauer_start_dt - timedelta(minutes=SNIPER_LOGIN_BUFFER)
    blitz_dt       = fremde_endzeit_heute  # Wechsel zu Multi-Shot-Blitz

    # ─── Slot-Definitionen ───
    # Phase 1: Slot der bei fremder STARTZEIT beginnt – das ist Maxes Slot.
    # ABER: Wir wissen nicht wann Max angefangen hat, nur seine Endzeit.
    # → Slot ist (endzeit - dauer) bis endzeit. ABER das stimmt nur wenn
    #   wir gleiche Dauer wie Max wollen.
    # Korrektur: User wählt dauer für SEINE Buchung. Bei Treffer bekommen
    # wir IMMER unsere gewählte dauer. Slot start = (endzeit - dauer).
    # Falls also Max von 17:00–18:30 (90min) und wir wollen 90 Min:
    #   → Slot 17:00–18:30 (Maxes Slot)
    # Falls Max von 17:00–18:30 (90min) und wir wollen 60 Min:
    #   → Slot 17:30–18:30 (passt in Maxes belegtes Fenster, würde frei
    #     wenn er storniert)
    phase1_from_dt = fremde_endzeit_dt - timedelta(minutes=dauer)
    phase1_from    = phase1_from_dt.strftime("%H:%M")
    phase1_to      = fremder_bis

    # Phase 2: Slot direkt NACH fremder Endzeit (regulär freigeschaltet
    # ab fremde_endzeit_heute durch 7-Tage-Regel)
    phase2_from    = fremder_bis
    phase2_to      = (datetime.strptime(fremder_bis, "%H:%M") +
                       timedelta(minutes=dauer)).strftime("%H:%M")

    # Anlagen-Schluss prüfen (R3)
    schluss_time = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M").time()
    if datetime.strptime(phase2_to, "%H:%M").time() > schluss_time:
        senden(f"⚠️ [{k}] Sniper: Phase-2-Slot ({phase2_from}–{phase2_to}) "
               f"übersteigt {ANLAGE_SCHLUSS} – nur Phase 1 läuft")
        phase2_aktiv = False
    else:
        phase2_aktiv = True

    # Phase-1-Slot (wir lauern auf fremde Stornierung)
    phase1_slot = {
        "court": court, "fromTime": phase1_from, "toTime": phase1_to,
        "datum_de": datum_de, "datum_api": datum_api, "dauer": dauer,
        "key": f"{datum_api}_{court}_{phase1_from}_{dauer}",
    }
    # Phase-2-Slot (regulärer Folge-Slot)
    phase2_slot = {
        "court": court, "fromTime": phase2_from, "toTime": phase2_to,
        "datum_de": datum_de, "datum_api": datum_api, "dauer": dauer,
        "key": f"{datum_api}_{court}_{phase2_from}_{dauer}",
    }

    # ─── User informieren ───
    senden(f"🎯 [{k}] SMART-SNIPER aktiv (v10.3.3)\n"
           f"   📅 {_datum_mit_tag(datum_de)} Court {court}\n"
           f"   🎯 Fremde Endzeit: {fremder_bis}\n"
           f"   💤 Schlaf bis {login_dt.strftime('%H:%M')} (Login)\n"
           f"   👁 Lauer: {lauer_start_dt.strftime('%H:%M')} – "
                          f"{blitz_dt.strftime('%H:%M')}\n"
           f"      → Phase 1: Slot {phase1_from}–{phase1_to} (fremde Storno)\n"
           f"   ⚡ Bei {blitz_dt.strftime('%H:%M')} Blitz-Phase 2:\n"
           f"      → Slot {phase2_from}–{phase2_to}"
           f"{' (NICHT verfügbar)' if not phase2_aktiv else ''}")

    log.info(f"[{k}] Sniper geplant: Lauer {lauer_start_dt} – {blitz_dt}, "
             f"Phase1={phase1_from}-{phase1_to}, Phase2={phase2_from}-{phase2_to}")

    # ═══════════════════════════════════════
    # SCHLAF bis Login-Zeitpunkt
    # ═══════════════════════════════════════
    while jetzt_lokal() < login_dt and az_get(k, "sniper_aktiv"):
        rest = (login_dt - jetzt_lokal()).total_seconds()
        time.sleep(min(rest, 5.0) if rest > 5 else max(rest, 0))

    if not az_get(k, "sniper_aktiv"):
        log.info(f"[{k}] Sniper abgebrochen (vor Login)")
        return

    # ═══════════════════════════════════════
    # LOGIN bei T-5 Min
    # ═══════════════════════════════════════
    if not _session_refresh_vor_aktion(k, "Smart-Sniper-Login"):
        senden(f"❌ [{k}] Sniper abgebrochen (Login-Fehler)")
        az_set(k, "sniper_aktiv", False)
        return

    # ═══════════════════════════════════════
    # SCHLAF bis Lauer-Start
    # ═══════════════════════════════════════
    while jetzt_lokal() < lauer_start_dt and az_get(k, "sniper_aktiv"):
        rest = (lauer_start_dt - jetzt_lokal()).total_seconds()
        time.sleep(min(rest, 1.0) if rest > 1.0 else max(rest, 0))

    if not az_get(k, "sniper_aktiv"):
        log.info(f"[{k}] Sniper abgebrochen (vor Lauer-Start)")
        return

    senden(f"👁 [{k}] Lauer-Fenster GESTARTET – hämmere "
           f"Slot {phase1_from}–{phase1_to} Court {court}")

    # ═══════════════════════════════════════
    # PHASE 1: LAUERN (lauer_start_dt bis blitz_dt)
    # ═══════════════════════════════════════
    versuche      = 0
    letzter_log   = time.time()
    letzter_login = time.time()

    while az_get(k, "sniper_aktiv") and jetzt_lokal() < blitz_dt:
        # Re-Login alle 30s
        if time.time() - letzter_login > 30:
            if not _session_refresh_vor_aktion(k, "Sniper-Refresh"):
                senden(f"❌ [{k}] Sniper abgebrochen (Re-Login-Fehler)")
                az_set(k, "sniper_aktiv", False)
                return
            letzter_login = time.time()

        # Status-Log alle 30s
        if time.time() - letzter_log > 30:
            rest_min = (blitz_dt - jetzt_lokal()).total_seconds() / 60.0
            log.info(f"[{k}] Phase 1: {versuche} Versuche, "
                     f"noch {rest_min:.1f} Min bis Blitz-Phase")
            letzter_log = time.time()

        # Lauer-Versuch auf Maxes Slot (Phase 1)
        ok, info = buche_slot_blitz(k, phase1_slot,
                                     prewarm_exec=None, prewarm_csrf=None,
                                     verify_person_id=True)
        if ok and info:
            az_set(k, "aktive_buchung", info)
            log.info(f"🎯 [{k}] PHASE-1-TREFFER (fremde Storno erkannt)!")
            senden(f"🎯 [{k}] SNIPER-TREFFER (Phase 1)!\n"
                   f"   Fremder hat storniert!\n"
                   f"   {datum_de} {phase1_from}–{phase1_to} Court {court}")
            time.sleep(0.5)
            sync_buchung_vom_server(k, expected_slot=phase1_slot)

            # Optional Schiebe-Phase3
            if ziel and ziel != phase1_from:
                az_set_multi(k,
                              schiebe_aktiv=True,
                              schiebe_modus="sniper",
                              schiebe_datum=datum_de,
                              schiebe_ziel=ziel,
                              schiebe_dauer=dauer,
                              schiebe_court=court)
                senden(f"🔄 [{k}] Sniper → Schiebe-Phase3 zu {ziel} Uhr…")
                _schiebe_phase3(k, datum_de, datum_api, dauer, ziel)
                az_set(k, "schiebe_aktiv", False)

            az_set(k, "sniper_aktiv", False)
            return

        versuche += 1
        time.sleep(0.2)  # 5 Versuche/Sek

    if not az_get(k, "sniper_aktiv"):
        log.info(f"[{k}] Sniper-Phase-1 abgebrochen")
        return

    log.info(f"[{k}] Phase 1 zu Ende ({versuche} Versuche) – "
             f"fremder hat NICHT storniert. Wechsel zu Phase 2 (Blitz).")

    # ═══════════════════════════════════════
    # PHASE 2: MULTI-SHOT-BLITZ (ab blitz_dt = fremde Endzeit)
    # ═══════════════════════════════════════
    if not phase2_aktiv:
        senden(f"⌛ [{k}] Sniper: Fremder hat nicht storniert UND Phase-2 "
               f"übersteigt Anlagen-Schluss. Kein Treffer.")
        az_set(k, "sniper_aktiv", False)
        return

    senden(f"⚡ [{k}] Fremder hat nicht storniert – BLITZ auf "
           f"{phase2_from}–{phase2_to}")

    # Übergabe an _aggressiv_buchen_ab mit fremder Endzeit als ab_dt
    # (das ist genau JETZT, also passt auch wenn wir leicht drüber sind)
    # _aggressiv_buchen_ab handhabt: Pre-warm + parallele Courts + Multi-Shot + Fallback
    # Bei Court "Egal" (0) → beide Courts; sonst nur gewählter
    erfolg = _aggressiv_buchen_ab(k, datum_de, datum_api, dauer,
                                   blitz_dt, None, court)

    if erfolg:
        # Sniper-spezifisches Schiebe-Ziel ggf. anwenden
        if ziel and ziel != phase2_from:
            az_set_multi(k,
                          schiebe_aktiv=True,
                          schiebe_modus="sniper",
                          schiebe_datum=datum_de,
                          schiebe_ziel=ziel,
                          schiebe_dauer=dauer,
                          schiebe_court=court)
            senden(f"🔄 [{k}] Sniper-Phase 2 erfolgreich → Schiebe zu {ziel}…")
            _schiebe_phase3(k, datum_de, datum_api, dauer, ziel)
            az_set(k, "schiebe_aktiv", False)
    else:
        senden(f"⌛ [{k}] Sniper: kein Treffer in Phase 1 noch Phase 2")

    az_set(k, "sniper_aktiv", False)
    log.info(f"[{k}] Sniper-Thread beendet")



# ══════════════════════════════════════════════
# THREAD-WRAPPER
# ══════════════════════════════════════════════

def schiebe_loop(k: str):
    try:
        _schiebe_intern(k)
    except Exception as e:
        log.exception(f"[{k}] Schiebe-Loop crash: {e}")
        senden(f"💥 [{k}] Schiebe-Loop Crash: {e}")
    finally:
        az_set(k, "schiebe_aktiv", False)


def sniper_loop(k: str):
    try:
        _sniper_intern(k)
    except Exception as e:
        log.exception(f"[{k}] Sniper-Loop crash: {e}")
        senden(f"💥 [{k}] Sniper-Loop Crash: {e}")
    finally:
        az_set(k, "sniper_aktiv", False)


# ══════════════════════════════════════════════
# TELEGRAM HANDLER
# ══════════════════════════════════════════════

def handle_text(msg: dict):
    text = msg.get("text", "").strip()
    chat = str(msg.get("chat", {}).get("id", ""))
    if chat != str(TELEGRAM_CHAT_ID):
        return

    if text in ("/start", "/menu", "start", "menu"):
        zeige_account_auswahl()
        return

    if text.lower() in ("/status", "status"):
        for k in ACCOUNTS:
            sync_buchung_vom_server(k)
        zeige_account_auswahl()
        return

    if text.lower() in ("/stop", "stop"):
        for k in ACCOUNTS:
            az_set(k, "schiebe_aktiv", False)
            az_set(k, "sniper_aktiv", False)
        senden("⏹️ Alle Schiebe/Sniper-Prozesse gestoppt")
        return

    # Direkt-Eingabe in einem Flow (z.B. Uhrzeit für direkte Taktik)
    k_flow = get_flow_account()
    if k_flow:
        flow = az_get(k_flow, "flow")
        if flow == "warte_buchbar_zeit":
            # Parse Uhrzeit aus Text
            m = re.match(r"^(\d{1,2}):(\d{2})$", text)
            if not m:
                senden("⚠️ Bitte Uhrzeit im Format HH:MM senden (z.B. 17:30)")
                return
            try:
                buchbar = datetime.strptime(text, "%H:%M").strftime("%H:%M")
            except Exception:
                senden("⚠️ Ungültige Uhrzeit")
                return
            az_set_multi(k_flow,
                          schiebe_buchbar_ab=buchbar,
                          flow=None)
            # Starte Schiebe-Thread
            t = threading.Thread(target=schiebe_loop, args=(k_flow,), daemon=True)
            az_set_multi(k_flow, schiebe_aktiv=True, schiebe_thread=t)
            t.start()
            senden(f"⚡ [{k_flow}] Direkte Taktik startet – buchbar ab {buchbar}")
            set_flow_account(None)
            return

    senden("Tippe /menu für das Hauptmenü.")


def handle_callback(cb: dict):
    cid  = cb["id"]
    data = cb.get("data", "")
    chat = str(cb.get("message", {}).get("chat", {}).get("id", ""))
    if chat != str(TELEGRAM_CHAT_ID):
        beantworte_callback(cid, "unauth")
        return

    beantworte_callback(cid)

    # Universelle Buttons
    if data == "abbrechen":
        set_flow_account(None)
        zeige_account_auswahl()
        return
    if data == "refresh_accounts" or data == "zurueck_accounts":
        zeige_account_auswahl()
        return

    # Account-Auswahl
    if data.startswith("acc_"):
        k = data[4:]
        if k in ACCOUNTS:
            set_flow_account(k)
            zeige_account_menue(k)
        return

    # Menü-Ebene
    if data.startswith("menu_"):
        rest = data[5:]
        # Form: <aktion>_<kuerzel>
        aktion, _, k = rest.partition("_")
        if k not in ACCOUNTS:
            senden(f"⚠️ Unbekannter Account: {k}")
            return
        set_flow_account(k)

        if aktion == "slots":
            # Klassisch buchen → Datum-Buttons
            az_set(k, "flow", "klassisch_datum")
            senden(f"📅 [{k}] Datum wählen:",
                   buttons=erstelle_datum_buttons(f"kdatum_{k}", nur_im_fenster=True))
            return
        if aktion == "schiebe":
            zeige_schiebe_modus_auswahl(k)
            return
        if aktion == "sniper":
            az_set(k, "flow", "sniper_datum")
            senden(f"🎯 [{k}] Sniper – Datum der fremden Buchung:",
                   buttons=erstelle_datum_buttons(f"sdatum_{k}"))
            return
        if aktion == "status":
            sync_buchung_vom_server(k)
            zeige_account_menue(k)
            return
        if aktion == "stopp":
            az_set(k, "schiebe_aktiv", False)
            az_set(k, "sniper_aktiv", False)
            senden(f"⏹️ [{k}] Schiebe/Sniper gestoppt")
            zeige_account_menue(k)
            return
        if aktion == "storno":
            aktiv = az_get(k, "aktive_buchung")
            if not aktiv or not aktiv.get("booking_id"):
                senden(f"⚠️ [{k}] Keine aktive Buchung")
                return
            if storniere_buchung(k, aktiv["booking_id"]):
                senden(f"🗑️ [{k}] Storniert: {aktiv['datum_de']} "
                       f"{aktiv['fromTime']} Court {aktiv['court']}")
            else:
                senden(f"❌ [{k}] Storno fehlgeschlagen")
            zeige_account_menue(k)
            return

    # Schiebe-Modus-Auswahl
    if data.startswith("schiebe_modus_"):
        rest = data[len("schiebe_modus_"):]
        modus, _, k = rest.partition("_")
        if k not in ACCOUNTS:
            return
        set_flow_account(k)
        az_set(k, "schiebe_modus", modus)
        # Datum
        az_set(k, "flow", f"schiebe_{modus}_datum")
        nur_fenster = (modus in ("frueh",))
        senden(f"📅 [{k}] Schiebe-{modus} – Datum:",
               buttons=erstelle_datum_buttons(f"shdatum_{modus}_{k}",
                                               nur_im_fenster=nur_fenster))
        return

    # Klassisch-Buchung Flow
    if data.startswith("kdatum_"):
        # kdatum_<k>_<datum>
        rest = data[len("kdatum_"):]
        # k bis _<datum>
        m = re.match(r"^(.+?)_(\d{2}\.\d{2}\.\d{4})$", rest)
        if not m:
            return
        k, datum_de = m.group(1), m.group(2)
        if k not in ACCOUNTS:
            return
        set_flow_account(k)
        az_set_multi(k, flow_datum=datum_de, flow="klassisch_dauer")
        senden(f"⏱ [{k}] Dauer wählen:",
               buttons=dauer_buttons(f"kdauer_{k}"))
        return

    if data.startswith("kdauer_"):
        rest = data[len("kdauer_"):]
        m = re.match(r"^(.+?)_(\d+)$", rest)
        if not m: return
        k, dauer = m.group(1), int(m.group(2))
        if k not in ACCOUNTS: return
        az_set_multi(k, flow_dauer=dauer, flow="klassisch_slot")
        datum_de = az_get(k, "flow_datum")
        if not _session_refresh_vor_aktion(k, "Klassisch-Buchung"):
            return
        freie = berechne_freie_slots(k, datum_de, dauer)
        if not freie:
            senden(f"❌ [{k}] Keine freien Slots am {datum_de}")
            return
        # Slot-Buttons
        btns = []
        for slot in freie[:30]:
            btns.append([{
                "text": f"C{slot['court']} {slot['fromTime']}–{slot['toTime']}",
                "callback_data": f"kslot_{k}_{slot['key']}",
            }])
        btns.append([{"text": "❌ Abbrechen", "callback_data": "abbrechen"}])
        senden(f"🎾 [{k}] {datum_de} ({dauer} Min) – Slot wählen:", buttons=btns)
        # Cache slots
        az_set(k, "_klassisch_slots", {s["key"]: s for s in freie})
        return

    if data.startswith("kslot_"):
        rest = data[len("kslot_"):]
        # kslot_<k>_<key>
        # key: <datum_api>_<court>_<from>_<dauer>
        parts = rest.split("_", 1)
        if len(parts) < 2: return
        k = parts[0]
        slot_key = parts[1]
        if k not in ACCOUNTS: return
        cache = az_get(k, "_klassisch_slots") or {}
        slot = cache.get(slot_key)
        if not slot:
            senden(f"⚠️ [{k}] Slot nicht mehr verfügbar")
            return
        if buche_slot(k, slot):
            senden(f"✅ [{k}] Gebucht: {slot['datum_de']} "
                   f"{slot['fromTime']}–{slot['toTime']} Court {slot['court']}")
        else:
            senden(f"❌ [{k}] Buchung fehlgeschlagen")
        az_set(k, "flow", None)
        zeige_account_menue(k)
        return

    # Schiebe-Datum-Auswahl
    if data.startswith("shdatum_"):
        rest = data[len("shdatum_"):]
        m = re.match(r"^(frueh|spaet|direkt)_(.+?)_(\d{2}\.\d{2}\.\d{4})$", rest)
        if not m: return
        modus, k, datum_de = m.group(1), m.group(2), m.group(3)
        if k not in ACCOUNTS: return
        set_flow_account(k)
        az_set_multi(k, schiebe_datum=datum_de, flow=f"schiebe_{modus}_dauer")
        senden(f"⏱ [{k}] Schiebe-{modus} – Dauer:",
               buttons=dauer_buttons(f"shdauer_{modus}_{k}"))
        return

    if data.startswith("shdauer_"):
        rest = data[len("shdauer_"):]
        m = re.match(r"^(frueh|spaet|direkt)_(.+?)_(\d+)$", rest)
        if not m: return
        modus, k, dauer = m.group(1), m.group(2), int(m.group(3))
        if k not in ACCOUNTS: return
        az_set_multi(k, schiebe_dauer=dauer, flow=f"schiebe_{modus}_court")
        senden(f"🏟️ [{k}] Court-Präferenz:",
               buttons=court_buttons(f"shcourt_{modus}_{k}"))
        return

    if data.startswith("shcourt_"):
        rest = data[len("shcourt_"):]
        m = re.match(r"^(frueh|spaet|direkt)_(.+?)_(\d+)$", rest)
        if not m: return
        modus, k, court_v = m.group(1), m.group(2), int(m.group(3))
        if k not in ACCOUNTS: return
        az_set_multi(k, schiebe_court=court_v, flow=f"schiebe_{modus}_ziel")
        dauer = az_get(k, "schiebe_dauer")
        senden(f"🎯 [{k}] Schiebe-{modus} – Ziel-Uhrzeit:",
               buttons=zielzeit_buttons(f"shziel_{modus}_{k}", dauer))
        return

    if data.startswith("shziel_"):
        rest = data[len("shziel_"):]
        m = re.match(r"^(frueh|spaet|direkt)_(.+?)_(\d{1,2}:\d{2})$", rest)
        if not m: return
        modus, k, ziel = m.group(1), m.group(2), m.group(3)
        if k not in ACCOUNTS: return
        az_set(k, "schiebe_ziel", ziel)

        if modus == "direkt":
            # Frage nach Buchbar-Zeit
            az_set(k, "flow", "warte_buchbar_zeit")
            senden(f"⏰ [{k}] Ab wann ist der Slot buchbar?\n"
                   f"   Sende die Uhrzeit im Format HH:MM (z.B. 17:30)")
        else:
            # frueh/spaet: starte sofort
            az_set(k, "flow", None)
            t = threading.Thread(target=schiebe_loop, args=(k,), daemon=True)
            az_set_multi(k, schiebe_aktiv=True, schiebe_thread=t)
            t.start()
            senden(f"🚀 [{k}] Schiebe-{modus} gestartet → Ziel {ziel}")
            set_flow_account(None)
        return

    # Sniper Flow
    if data.startswith("sdatum_"):
        rest = data[len("sdatum_"):]
        m = re.match(r"^(.+?)_(\d{2}\.\d{2}\.\d{4})$", rest)
        if not m: return
        k, datum_de = m.group(1), m.group(2)
        if k not in ACCOUNTS: return
        set_flow_account(k)
        az_set_multi(k, sniper_datum=datum_de, flow="sniper_court")
        senden(f"🏟️ [{k}] Sniper – welcher Court?",
               buttons=court_buttons(f"scourt_{k}"))
        return

    if data.startswith("scourt_"):
        rest = data[len("scourt_"):]
        m = re.match(r"^(.+?)_(\d+)$", rest)
        if not m: return
        k, court_v = m.group(1), int(m.group(2))
        if k not in ACCOUNTS: return
        # Sniper braucht spezifischen Court (0 = beide nicht sinnvoll → default 2)
        if court_v == 0:
            court_v = 2
        az_set_multi(k, sniper_court=court_v, flow="sniper_dauer")
        senden(f"⏱ [{k}] Sniper – Dauer der Buchung:",
               buttons=dauer_buttons(f"sdauer_{k}"))
        return

    if data.startswith("sdauer_"):
        rest = data[len("sdauer_"):]
        m = re.match(r"^(.+?)_(\d+)$", rest)
        if not m: return
        k, dauer = m.group(1), int(m.group(2))
        if k not in ACCOUNTS: return
        az_set_multi(k, sniper_dauer=dauer, flow="sniper_bis")
        senden(f"🕐 [{k}] Sniper – Endzeit der FREMDEN Buchung (=Start unserer):",
               buttons=sniper_endzeit_buttons(f"sbis_{k}"))
        return

    if data.startswith("sbis_"):
        rest = data[len("sbis_"):]
        m = re.match(r"^(.+?)_(\d{1,2}:\d{2})$", rest)
        if not m: return
        k, bis_t = m.group(1), m.group(2)
        if k not in ACCOUNTS: return
        az_set_multi(k, sniper_fremder_bis=bis_t, flow="sniper_ziel")
        dauer = az_get(k, "sniper_dauer")
        senden(f"🎯 [{k}] Sniper – Schiebe-Ziel-Uhrzeit (= unser End-Slot, "
               f"oder gleich {bis_t} für 'kein Schieben'):",
               buttons=zielzeit_buttons(f"sziel_{k}", dauer))
        return

    if data.startswith("sziel_"):
        rest = data[len("sziel_"):]
        m = re.match(r"^(.+?)_(\d{1,2}:\d{2})$", rest)
        if not m: return
        k, ziel = m.group(1), m.group(2)
        if k not in ACCOUNTS: return
        az_set_multi(k, sniper_ziel=ziel, flow=None)
        t = threading.Thread(target=sniper_loop, args=(k,), daemon=True)
        az_set_multi(k, sniper_aktiv=True, sniper_thread=t)
        t.start()
        senden(f"🎯 [{k}] Sniper gestartet – Ziel {ziel}")
        set_flow_account(None)
        return


def telegram_loop():
    log.info("📱 Telegram-Loop gestartet")
    while True:
        try:
            updates = hole_updates()
            for upd in updates:
                if "message" in upd:
                    handle_text(upd["message"])
                elif "callback_query" in upd:
                    handle_callback(upd["callback_query"])
        except Exception as e:
            log.exception(f"Telegram-Loop: {e}")
        time.sleep(0.5)


# ══════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════

if __name__ == "__main__":
    log.info("═" * 60)
    log.info("🎾 Padel Bot v10.3.3 startet…")
    log.info("   ⚡ BLITZ-Modus: Pre-warm + Parallel-Courts + Multi-Shot")
    log.info("   🎯 SMART-SNIPER: Lauer letzte 30 Min vor fremder Endzeit")
    log.info("   🔍 Person-ID-Verifikation aktiv")
    log.info("   🛡️ Sync mit expected_slot")
    log.info(f"   Accounts: {', '.join(ACCOUNTS.keys())}")
    log.info("═" * 60)

    # Initial-Login aller Accounts
    for k in ACCOUNTS:
        try:
            if einloggen(k):
                sync_buchung_vom_server(k)
            else:
                senden(f"❌ [{k}] Initial-Login fehlgeschlagen!")
        except Exception as e:
            log.exception(f"[{k}] Init: {e}")

    accs_str = ", ".join(ACCOUNTS.keys())
    senden(f"🎾 <b>Padel Bot v10.3.3 online</b>\n\n"
           f"⚡ BLITZ-Modus aktiv:\n"
           f"   • Pre-warm r1 bei T-10s\n"
           f"   • r2+r3 parallel auf Court 1 & 2\n"
           f"   • Multi-Shot ({MULTI_SHOT_COUNT} Bursts) bei Verfehlen\n"
           f"   • Person-ID-Check (kein fremdes Schieben)\n"
           f"   • Sync mit expected_slot\n\n"
           f"🎯 SMART-SNIPER (NEU v10.3.3):\n"
           f"   • Lauer nur in letzten {SNIPER_PRE_END_MINUTES} Min "
                  f"vor fremder Endzeit\n"
           f"   • Phase 2: Blitz auf Folge-Slot wenn kein Storno\n\n"
           f"Accounts: {accs_str}\n\n"
           f"Tippe /menu zum Starten.")

    try:
        telegram_loop()
    except KeyboardInterrupt:
        log.info("Bot beendet (Ctrl+C)")
        senden("⏹️ Padel Bot beendet")
