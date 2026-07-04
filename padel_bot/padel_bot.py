#!/usr/bin/env python3
"""Padel Bot v13.0.0

NEU v13.0.0: 3h-MODUS (Block). Rein additiv – KERN-CODE UNVERÄNDERT.
        Zwei Accounts erzeugen zusammen einen durchgehenden 3-Stunden-Block
        (2× 90 Min). Ablauf:
          1. Button "3h-Modus" in der Account-Auswahl
          2. Account 1 (Schieber) + Account 2 (Anschluss-Blitzer) wählen
          3. Datum → Court → Wunschanfang (Block-Start) → Buchbar-ab-Zeit X
        Konfiguration (beide laufen über den UNVERÄNDERTEN schiebe_loop):
          • Account 1 = Direkte Taktik: Start ab X, schiebt bis Wunschanfang
            (z.B. 10:30 → Slot 10:30–12:00).
          • Account 2 = Direkte Taktik: blitzt den DIREKT folgenden Slot bei
            dessen Freischaltung (Start = Wunschanfang+90 = 12:00 → 12:00–13:30),
            Ziel == Start → kein Schieben, nur Blitz. "Bekannte Startzeit".
        Ergebnis: durchgehender Block Wunschanfang … Wunschanfang+180 (3 Std.).
        Bei festem Court liegt der ganze Block auf einem Platz.

NEU v12.0.0: BLITZ-SCHIEBEN. Der Schiebe-Rebook arbeitet jetzt wie die
        Direkt-Blitz-Taktik: das langsame r1 (Formular/Token) wird BEREITS VOR
        dem Storno geholt (pre_warm_r1), solange die alte Buchung noch hält.
        Im kritischen Fenster NACH dem Storno feuern dann nur noch r2+r3
        (burst_r2_r3) – Multi-Shot, nur aktueller Court, SPEED-Verifikation per
        my-bookings. Dadurch schrumpft das "offene" Fenster (Storno→Neubuchung)
        spürbar → weniger Slot-Klau beim Schieben. Bei leerem Prewarm-Token
        fällt es automatisch auf den alten buche_slot-Loop zurück (kein Risiko).
        Greift im Einzel-Direkt-Schiebe UND im Duo (fester Court).

FIX v11.0.1: Duo-Schiebe-Rebook nagelt den Court jetzt FEST (kein Alternieren
        auf den Partner-Court). Vorher konnte ein Duo-Account beim Schieben den
        Court des Partners anvisieren → gegenseitiges Platz-Klauen / vergeudete
        STRIKT-Verifikationsversuche, bis einer "nur storniert, nicht neugebucht"
        hatte. Jeder Duo-Schiebevorgang läuft nun 1:1 wie ein einzelner auf festem
        Court. Zusätzlich Duo-Sicherheitsnetz: bei verzögerter Verifikation wird
        per my-bookings geprüft, ob doch gebucht wurde, bevor aufgegeben wird.
        (Einzel-/Normal-Schiebe unverändert – Alternieren bleibt dort als Fallback.)

ÄNDERUNGEN gegenüber v10.0.0:

PERF 1: Telegram-Reaktion deutlich schneller (keine Funktionsänderung!).
        - Eine gemeinsame requests.Session für ALLE Telegram-Calls
          (Keep-Alive statt neuem TLS-Handshake pro senden/Button/getUpdates).
        - time.sleep(1) im telegram_loop entfernt (getUpdates pollt bereits
          serverseitig 5s → kein Busy-Loop). Buttons reagieren sofort.
        - zeige_account_auswahl(): Account-Syncs laufen PARALLEL statt seriell
          (identisches Ergebnis, aber 1× statt N× Wartezeit bei mehreren Accounts).
        - hole_wetter(): 10-Min-Cache → keine wiederholten 8s-Timeouts beim
          Menü-Rendern.

NEU 2:  Duo-Modus (👥) – zwei Accounts parallel auf Court 1 + Court 2.
        Basis = "Direkte Taktik". Ablauf:
          1. Button "Duo-Modus" in der Account-Auswahl
          2. Zwei freie Accounts wählen (Acc1 → Court 1, Acc2 → Court 2)
          3. Datum → Zielzeit → Buchbar-ab-Zeit (90 Min fix)
          4. Beide blitzen GLEICHZEITIG auf ihren Court bei Freischaltung
          5. Versetzter Schiebe-Rhythmus: Court-1-Acc schiebt 5–8 Min vor Ende,
             Court-2-Acc 11–14 Min vor Ende → ~5–6 Min Versatz, nie gleichzeitig.
        Normaler Schiebe-Modus bleibt 100% unverändert (5–20 Min Random).

ÄNDERUNGEN gegenüber v9.0.0:

FIX 1: Buchungsbestätigung nur wenn wirklich gebucht.
        buche_slot() hat Exception-Fallback `verifiziert = True` entfernt.
        Bei Verifikations-Fehler: zweiter Versuch mit 1.5s Pause.
        Falls immer noch nicht verifizierbar → False zurückgeben.
        Kein Falsch-Positiv mehr "storniert und neugebucht" obwohl nur storniert.

FIX 2: Schiebe-Taktik robuster und schneller.
        - Phase 3 in eigene Funktion _schiebe_phase3() ausgelagert.
        - Storno-Retry prüft jetzt aktiv() → stoppt sofort bei "Stopp"-Button.
        - Rebook nach Storno: 30 Versuche, 0.1s für erste 15, dann 0.5s.
          Kein exponentieller Backoff mehr der Sekunden kostet.
        - Nach erfolgreichem Rebook: aktive_buchung via az_get() geprüft,
          bei None nochmal Server-Sync vor der Bestätigungsnachricht.

NEU 3: Sniper-Modus.
        Jemand schiebt manuell → Bot zielt automatisch auf den nächsten Slot.
        Ablauf:
          1. User gibt an: Datum, Court, Endzeit der fremden Buchung, Dauer, Zielzeit
          2. Bot berechnet: Ziel = fremdes Ende - 30 Min (z.B. 09:30 → 09:00)
          3. Bot hämmert sekündlich auf diesen Slot
          4. Treffer → Bot schickt Bestätigung
          5. Danach: normaler Schiebe-Loop (_schiebe_phase3) bis Zielzeit

BEIBEHALTEN (alle Fixes aus v9.x):
  FIX 4: Login exakt 90s VOR 07:00 (also 06:58:30).
  FIX 5: Storno-Retry sendet KEINE Telegram-Nachrichten während der Retries.
  FIX 6: schiebe_moment verwendet jetzt.date() (nicht datum_obj.date()).
  FIX 7: Neubuchung nach Storno versucht zuerst gleichen Court.

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

# PERF: Wetter-Cache (10 Min) – Forecasts ändern sich nicht sekündlich, aber
# hole_wetter() wird bei jedem Menü-Render aufgerufen (Timeout 8s pro Call).
_wetter_cache: dict = {}            # (datum_de, stunde) -> (timestamp, text)
_wetter_cache_lock = threading.Lock()
WETTER_CACHE_TTL = 600              # Sekunden

def hole_wetter(datum_de: str, from_time: str) -> str:
    try:
        _stunde_key = int(from_time.split(":")[0])
    except Exception:
        _stunde_key = 0
    _cache_key = (datum_de, _stunde_key)
    _now = time.time()
    with _wetter_cache_lock:
        _cached = _wetter_cache.get(_cache_key)
        if _cached and (_now - _cached[0]) < WETTER_CACHE_TTL:
            return _cached[1]
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
        ergebnis = (f"\n{desc} | 🌡️ {temp:.0f}°C | ☔ {rain}% | 💨 {wind:.0f} km/h")
        with _wetter_cache_lock:
            _wetter_cache[_cache_key] = (_now, ergebnis)
        return ergebnis
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
AGGRESSIVE_TIMEOUT      = 300
AGGRESSIVE_INTERVAL     = 0.3
FRUEH_EXKLUSIV_VERSUCHE = 8

# Smart-Sniper (R20–R23)
SNIPER_PRE_END_MINUTES = 30      # Lauer-Fenster: letzte 30 Min vor fremder Endzeit
SNIPER_LOGIN_BUFFER    = 5       # Min vor Lauer-Start: Refresh-Login
SNIPER_PHASE1_INTERVAL = 0.1     # s: Hammer-Intervall in Phase 1 (Lauern)
SNIPER_DEADLINE_BUFFER = 60      # s: Abbruch X Sek nach fremder Endzeit

# Direkt-Blitz
BLITZ_PREWARM_SECONDS  = 10      # s: Pre-Warm r1 bei T-10s, Token cachen
BLITZ_FIRE_OFFSET_MS   = 0       # ms: Feuer-Offset relativ buchbar_dt (nie negativ!)
MULTI_SHOT_COUNT       = 5       # Anzahl Burst-Wellen nach erstem Miss
MULTI_SHOT_GAP_MS      = 150     # ms: Pause zwischen Bursts
PHASE1_HANDOFF_MARGIN  = 180     # s: Direkt-Modus wacht so viel vor Freischaltung auf (Phase 2 macht Login+Pre-Warm+Blitz)

# Duo-Modus: zwei Accounts parallel auf Court 1 + Court 2 (Basis = Direkte Taktik).
# Versetzter Schiebe-Rhythmus, damit beide nie gleichzeitig schieben:
#   Court-1-Account: 5–8 Min vor Slot-Ende   (schiebt später, näher am Ende)
#   Court-2-Account: 11–14 Min vor Slot-Ende (schiebt früher)
# → typischer Versatz ~5–6 Min, garantiert ≥3 Min Abstand.
DUO_COURT1_OFFSET_MIN  = 5
DUO_COURT1_OFFSET_MAX  = 8
DUO_COURT2_OFFSET_MIN  = 11
DUO_COURT2_OFFSET_MAX  = 14
DUO_DAUER_MIN          = 90      # Duo immer 90 Min Spielzeit

# 3h-Modus (Block): Acc1 schiebt bis Wunschanfang, Acc2 blitzt den Anschluss-Slot.
# Beide je 90 Min → zusammen ein durchgehender 3-Stunden-Block (2× 90 Min).
BLOCK_DAUER_MIN        = 90

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
    for i in range(1, 7):   # Account 1..6
        email = _optional(f"account_{i}_email")
        pw    = _optional(f"account_{i}_passwort")
        if i == 1:
            if not email or not pw:
                raise SystemExit("❌ account_1_email / account_1_passwort fehlen in options.json!")
        else:
            if not email or not pw:
                continue
        label = _optional(f"account_{i}_label") or f"ACC{i}"
        if label in accounts:
            label = f"{label}_{i}"
        accounts[label] = {"email": email, "passwort": pw}

    labels = list(accounts.keys())
    if len(labels) == 1:
        log.info(f"   Account geladen: {labels[0]} (Einzelmodus)")
    else:
        log.info(f"   Accounts geladen ({len(labels)}): {', '.join(labels)}")

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
        # Duo-Modus: optionales Schiebe-Offset-Band (None = normaler 5–20-Min-Random)
        "schiebe_offset_min": None,
        "schiebe_offset_max": None,
        "duo_court":          None,   # None = kein Duo; 1/2 = fester Court im Duo (kein Alternieren)
        # Sniper
        "sniper_aktiv":       False,
        "sniper_datum":       None,
        "sniper_court":       None,
        "sniper_fremder_bis": None,   # Endzeit der fremden Buchung (z.B. "09:30")
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

# Duo-Modus: Auswahl-Flow über ZWEI Accounts (nicht an einen Account gebunden).
_duo = {"flow": None, "acc_a": None, "acc_b": None, "datum": None, "ziel": None}
_duo_lock = threading.Lock()

def _duo_reset():
    with _duo_lock:
        _duo.update(flow=None, acc_a=None, acc_b=None, datum=None, ziel=None)

def _duo_awaiting_text() -> bool:
    with _duo_lock:
        return _duo["flow"] == "startzeit"

# 3h-Modus (Block): eigener Auswahl-Flow über ZWEI Accounts (wie Duo), zusätzlich
# mit Court-Wahl. Acc1 schiebt bis Wunschanfang, Acc2 blitzt den Anschluss-Slot.
_block = {"flow": None, "acc_a": None, "acc_b": None,
          "datum": None, "ziel": None, "court": None}
_block_lock = threading.Lock()

def _block_reset():
    with _block_lock:
        _block.update(flow=None, acc_a=None, acc_b=None,
                      datum=None, ziel=None, court=None)

def _block_awaiting_text() -> bool:
    with _block_lock:
        return _block["flow"] == "startzeit"

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

# PERF: EINE gemeinsame Session für alle Telegram-Calls → Keep-Alive,
# spart pro senden/Button/getUpdates den TLS-Handshake (urllib3-Pool ist
# thread-safe, daher unbedenklich aus Polling- und Schiebe-Threads).
_TG_SESSION = _neue_session()

def tg(method: str, payload: dict) -> dict:
    # FIX v12: Bei langer Idle-Phase (z.B. ~80 Min zwischen Schiebe-Schritten)
    # schließt Telegram die Keep-Alive-Verbindung im _TG_SESSION-Pool. Der erste
    # POST darauf scheitert dann mit RemoteDisconnected ("Connection aborted").
    # urllib3 wiederholt POSTs nicht automatisch → daher hier 1× manueller Retry
    # mit frischer Verbindung. Verlorene Nachrichten (z.B. "⚡ Schiebe jetzt!")
    # werden so vermieden; das Buchen war ohnehin nie betroffen.
    for versuch in range(2):
        try:
            r = _TG_SESSION.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}",
                                 json=payload, timeout=10)
            return r.json()
        except Exception as e:
            if versuch == 0:
                log.warning(f"Telegram {method}: {e} → Retry mit frischer Verbindung")
                continue
            log.error(f"Telegram {method}: {e}")
            return {}
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
        r = _TG_SESSION.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
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
        return (f"🔴 {k} – {datum_str} "
                f"{aktiv.get('fromTime','?')}–{aktiv.get('toTime','?')} "
                f"C{aktiv.get('court','?')}")
    elif schiebe:
        datum_str = _datum_mit_tag(snap["schiebe_datum"] or "?")
        return f"🟡 {k} – Schiebe {datum_str}"
    elif sniper:
        datum_str = _datum_mit_tag(snap["sniper_datum"] or "?")
        return f"🔵 {k} – Sniper {datum_str}"
    return f"✅ {k} – frei"

def _account_frei(k: str) -> bool:
    """True, wenn der Account keine aktive Buchung/Schiebe/Sniper hat (für Duo-Auswahl)."""
    snap = az_snap(k, "aktive_buchung", "schiebe_aktiv", "sniper_aktiv")
    return not (snap["aktive_buchung"] or snap["schiebe_aktiv"] or snap["sniper_aktiv"])

def _account_sort_key(k: str):
    """Sortierung der Account-Liste: Buchungen/Schiebe/Sniper aufsteigend
    nach Datum (und Uhrzeit), freie Accounts danach."""
    snap  = az_snap(k, "aktive_buchung", "schiebe_aktiv", "schiebe_datum",
                    "sniper_aktiv", "sniper_datum")
    aktiv = snap["aktive_buchung"]
    if aktiv:
        try:
            d = datetime.strptime(aktiv.get("datum_de", ""), "%d.%m.%Y").date()
            t = datetime.strptime(aktiv.get("fromTime", "00:00"), "%H:%M").time()
            return (0, datetime.combine(d, t), k)
        except Exception:
            return (0, datetime.max, k)
    if snap["schiebe_aktiv"] and snap["schiebe_datum"]:
        try:
            d = datetime.strptime(snap["schiebe_datum"], "%d.%m.%Y").date()
            return (0, datetime.combine(d, datetime.min.time()), k)
        except Exception:
            return (0, datetime.max, k)
    if snap["sniper_aktiv"] and snap["sniper_datum"]:
        try:
            d = datetime.strptime(snap["sniper_datum"], "%d.%m.%Y").date()
            return (0, datetime.combine(d, datetime.min.time()), k)
        except Exception:
            return (0, datetime.max, k)
    return (1, datetime.max, k)

def _sync_safe(k: str):
    try:
        sync_buchung_vom_server(k)
    except Exception as e:
        log.warning(f"[{k}] Sync: {e}")

def zeige_account_auswahl():
    set_flow_account(None)
    # PERF: Account-Syncs PARALLEL statt seriell. Jeder Account hat eigene
    # http-Session + eigenen Lock → unbedenklich. Ergebnis identisch, aber
    # statt Summe der Wartezeiten nur noch die des langsamsten Accounts.
    if len(ACCOUNTS) > 1:
        sync_threads = [threading.Thread(target=_sync_safe, args=(k,), daemon=True)
                        for k in ACCOUNTS]
        for t in sync_threads:
            t.start()
        for t in sync_threads:
            t.join()
    else:
        for k in ACCOUNTS:
            _sync_safe(k)

    anzahl     = len(ACCOUNTS)
    modus_label = "Dual-Account" if anzahl > 1 else "Einzel-Account"
    sorted_accounts = sorted(ACCOUNTS, key=_account_sort_key)
    buttons = []
    for k in sorted_accounts:
        buttons.append([{"text": account_status_label(k), "callback_data": f"acc_{k}"}])
    buttons.append([{"text": "🔄 Aktualisieren", "callback_data": "refresh_accounts"}])
    if len(ACCOUNTS) >= 2:
        buttons.append([{"text": "👥 Duo-Modus (2 Accounts parallel)",
                         "callback_data": "duo_start"}])
        buttons.append([{"text": "🔗 3h-Modus (Block, 2 Accounts)",
                         "callback_data": "block_start"}])

    status_zeilen = ""
    for k in sorted_accounts:
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
        f"Bot wartet bis 17:30, bucht dann und schiebt zur Wunschzeit.",
        buttons=[
            [{"text": "🌅 Früh-Methode  (07:00 Dauerbeschuss + Fallback)",
              "callback_data": f"schiebe_modus_frueh_{k}"}],
            [{"text": "🕐 Spät-Taktik  (spätester freier Slot jetzt)",
              "callback_data": f"schiebe_modus_spaet_{k}"}],
            [{"text": "🎯 Direkte Taktik  (bekannte Startzeit)",
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

def datum_de_zu_api(datum_de: str) -> str:
    return datetime.strptime(datum_de, "%d.%m.%Y").strftime("%m/%d/%Y")

def dauer_minuten(from_t: str, to_t: str) -> int:
    return int((datetime.strptime(to_t, "%H:%M") -
                datetime.strptime(from_t, "%H:%M")).seconds / 60)

def _baue_slot_dict(court: int, from_t: str, to_t: str,
                    datum_de: str, datum_api: str, dauer: int) -> dict:
    return {
        "court":     court,
        "fromTime":  from_t,
        "toTime":    to_t,
        "dauer":     dauer,
        "datum_api": datum_api,
        "datum_de":  datum_de,
        "key":       f"{datum_api}_{court}_{from_t}_{dauer}",
    }

def _ajax_header(csrf_t: str, *, accept: str = "*/*",
                 referer: str | None = None) -> dict:
    h = {"accept":           accept,
         "x-ajax-call":      "true",
         "x-csrf-token":     csrf_t,
         "x-requested-with": "XMLHttpRequest"}
    if referer:
        h["referer"] = referer
    return h

_RE_DATUM_DE     = re.compile(r"(\d{2}\.\d{2}\.\d{4})")
_RE_ZEIT_RANGE   = re.compile(
    r"(?:von\s+)?(\d{1,2}:\d{2})\s*(?:Uhr\s+)?(?:bis|–|-)\s*(\d{1,2}:\d{2})", re.I)
_RE_COURT        = re.compile(r"[Cc]ourt\s*(\d+)")
_RE_BOOKING_ID   = re.compile(r"/bookings/(\d+)")
_RE_BOOKING_PATH = re.compile(r"/bookings/\d+")

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
                freie.append(_baue_slot_dict(
                    court, t.strftime("%H:%M"), t_bis.strftime("%H:%M"),
                    datum_de, datum_api, dauer_min))
            t += timedelta(minutes=30)
    return freie

# ══════════════════════════════════════════════
# BUCHUNG
# ══════════════════════════════════════════════

def buche_slot(k: str, slot: dict, verify_person_id: bool = True) -> bool:
    """
    verify_person_id=True  (STRIKT, R10): Verifiziert via /padel-Reservierungen.
                                         Bei leerem personId-Feld oder Exception → False.
                                         Genutzt für Sniper Phase 1, normales Buchen.
    verify_person_id=False (SPEED,  R10): Vertraut r3 wenn Status 200/302 ohne Fehler-Indiz.
                                         Caller MUSS sync_buchung_vom_server(expected_slot)
                                         als Sicherheitsnetz aufrufen.
                                         Genutzt für Multi-Shot Bursts (Direkt-Blitz, Sniper Phase 2).
    """
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
    h  = _ajax_header(csrf_t, referer=f"{BASE_URL}/padel?currentDate={datum_api}")
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

        # SPEED-Modus: kein /padel-Verifikations-Sleep, Caller macht Sicherheitsnetz.
        if not verify_person_id:
            az_set(k, "aktive_buchung",
                   {**slot, "court": int(court), "booking_id": booking_id})
            log.info(f"⚡ [{k}] SPEED-Buchung r3 OK – ID: {booking_id} (Sync folgt vom Caller)")
            return True

        # Verifizierung: keine Falsch-Positive, kein Fallback auf True.
        time.sleep(1.0)
        verifiziert = False
        try:
            server_res = hole_reservierungen(k, datum_api)
            for res in server_res:
                if (res["court"] == int(court) and
                        res["fromTime"] == from_t and res["toTime"] == to_t):
                    res_bid = res.get("booking") or res.get("bookingOrBlockingId")
                    if booking_id and res_bid and res_bid == booking_id:
                        verifiziert = True
                        break
                    elif not booking_id and res_bid:
                        booking_id  = res_bid
                        verifiziert = True
                        break
        except Exception as ve1:
            log.warning(f"[{k}] Verifikations-Versuch 1 fehlgeschlagen: {ve1}")

        # Zweiter Versuch falls erster fehlgeschlagen (1.5s später)
        if not verifiziert:
            try:
                time.sleep(1.5)
                server_res2 = hole_reservierungen(k, datum_api)
                for res in server_res2:
                    if (res["court"] == int(court) and
                            res["fromTime"] == from_t and res["toTime"] == to_t):
                        res_bid = res.get("booking") or res.get("bookingOrBlockingId")
                        if res_bid:
                            booking_id  = res_bid
                        verifiziert = True
                        break
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
# STORNIERUNG
# ══════════════════════════════════════════════

def storniere_buchung(k: str, booking_id: int, datum_api: str) -> bool:
    log.info(f"🗑️ [{k}] Storniere ID {booking_id}")
    snap   = az_snap(k, "csrf_token", "http")
    csrf_t = snap["csrf_token"]
    http   = snap["http"]
    h = _ajax_header(csrf_t, accept="text/html, */*; q=0.01",
                     referer=f"{BASE_URL}/padel?currentDate={datum_api}")
    try:
        r1 = http.get(f"{BASE_URL}/court-module/{MODULE}/bookings/{booking_id}/cancel",
                      headers=h, timeout=10)
        r2 = http.get(f"{BASE_URL}/court-module/{MODULE}/bookings/{booking_id}/cancel",
                      params={"button_confirm": CONFIRM_KEY},
                      headers={**h, "accept": "*/*"}, timeout=10)
        if r2.status_code in [200, 302]:
            az_set(k, "aktive_buchung", None)
            log.info(f"✅ [{k}] Stornierung OK")
            return True
        # DIAGNOSE: warum schlug der Cancel fehl? (Statuscode + Body-Anfang beider Schritte)
        body2 = (r2.text or "")[:300].replace("\n", " ")
        log.warning(f"[{k}] Storno FAIL ID {booking_id}: "
                    f"r1={r1.status_code} r2={r2.status_code} | body2={body2!r}")
        return False
    except Exception as e:
        log.error(f"[{k}] Stornierung: {e}")
        return False

# ══════════════════════════════════════════════
# SERVER-SYNC
# ══════════════════════════════════════════════

def sync_buchung_vom_server(k: str, debug_telegram: bool = False):
    if az_get(k, "schiebe_aktiv"):
        thread = acc[k].get("schiebe_thread")
        if thread and not thread.is_alive():
            log.warning(f"[{k}] Sync: Schiebe-Thread tot → schiebe_aktiv=False")
            az_set(k, "schiebe_aktiv", False)
        else:
            return

    if az_get(k, "sniper_aktiv"):
        return

    http_sess = acc[k]["http"]
    csrf_t    = az_get(k, "csrf_token")
    jetzt     = jetzt_lokal()
    gefunden  = None

    h = _ajax_header(csrf_t, referer=f"{BASE_URL}/")

    sync_erfolgreich = False

    for login_versuch in range(2):
        try:
            r_pages = http_sess.get(
                f"{BASE_URL}/user/my-bookings/total-pages",
                params={"size": "50", "sort": ["serviceDate,desc", "id,desc"]},
                headers={**h, "accept": "application/json, text/javascript, */*; q=0.01"},
                timeout=10)
            if r_pages.status_code == 401:
                log.warning(f"[{k}] Sync: 401 – logge neu ein...")
                if einloggen(k):
                    http_sess = acc[k]["http"]
                    csrf_t    = az_get(k, "csrf_token")
                    h["x-csrf-token"] = csrf_t
                    continue
                else:
                    return
            total_pages = 1
            try:
                raw = r_pages.json()
                if isinstance(raw, (int, float)):
                    total_pages = int(raw)
                elif isinstance(raw, str):
                    total_pages = int(raw)
                elif isinstance(raw, dict):
                    for key in ("totalPages", "total_pages", "pages", "total"):
                        if key in raw:
                            val = raw[key]
                            total_pages = int(val) if isinstance(val, (int, float, str)) else 1
                            break
            except Exception:
                total_pages = 1
            total_pages = max(1, min(total_pages, 5))
            sync_erfolgreich = True
            break
        except Exception as e:
            log.error(f"[{k}] Sync total-pages: {e}")
            return

    if not sync_erfolgreich:
        return

    try:
        for page in range(total_pages):
            if gefunden:
                break
            r_page = http_sess.get(
                f"{BASE_URL}/user/my-bookings/page",
                params={"page": str(page), "size": "50",
                        "sort": ["serviceDate,desc", "id,desc"]},
                headers=h, timeout=10)
            if r_page.status_code != 200:
                break

            soup   = BeautifulSoup(r_page.text, "html.parser")
            karten = soup.find_all("div", class_=lambda c: c and
                                   "col-12" in c and "col-sm-6" in c)
            if not karten:
                karten = list({
                    tag.find_parent("div") for tag in
                    soup.find_all(attrs={"href": _RE_BOOKING_PATH}) +
                    soup.find_all(attrs={"data-target": _RE_BOOKING_PATH})
                    if tag.find_parent("div")
                })
            if not karten:
                karten = [soup]

            for karte in karten:
                if karte.find(class_=lambda c: c and
                              ("badge-danger" in c or "cancelled" in c or "storniert" in c)):
                    continue
                text        = karte.get_text(" ", strip=True)
                datum_match = _RE_DATUM_DE.search(text)
                if not datum_match:
                    continue
                datum_de  = datum_match.group(1)
                datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
                if datum_obj.date() < jetzt.date():
                    continue
                zeit_match = _RE_ZEIT_RANGE.search(text)
                if not zeit_match:
                    continue
                from_str = zeit_match.group(1).zfill(5)
                to_str   = zeit_match.group(2).zfill(5)
                slot_dt  = datetime.combine(datum_obj.date(),
                                            datetime.strptime(from_str, "%H:%M").time())
                if slot_dt < jetzt:
                    continue
                court_match = _RE_COURT.search(text)
                court = int(court_match.group(1)) if court_match else 1
                bid   = None
                for pa in ["data-target", "href", "data-url", "action"]:
                    for tag in karte.find_all(attrs={pa: _RE_BOOKING_PATH}):
                        m2 = _RE_BOOKING_ID.search(tag.get(pa, ""))
                        if m2:
                            bid = int(m2.group(1))
                            break
                    if bid:
                        break
                datum_api_s = datum_obj.strftime("%m/%d/%Y")
                gefunden = {
                    "court":      court,
                    "fromTime":   from_str,
                    "toTime":     to_str,
                    "datum_de":   datum_de,
                    "datum_api":  datum_api_s,
                    "dauer":      dauer_minuten(from_str, to_str),
                    "booking_id": bid,
                    "key":        f"{datum_api_s}_{court}_{from_str}",
                }
                log.info(f"[{k}] Sync OK: {datum_de} {from_str}–{to_str} Court {court} ID={bid}")
                break
    except Exception as e:
        log.error(f"[{k}] Sync Fehler: {e}")

    aktuell = az_get(k, "aktive_buchung")
    if gefunden:
        az_set(k, "aktive_buchung", gefunden)
    elif sync_erfolgreich:
        if aktuell and not az_get(k, "schiebe_aktiv"):
            log.info(f"[{k}] Keine aktive Buchung auf dem Server.")
        az_set(k, "aktive_buchung", None)


def verifiziere_slot_via_my_bookings(k: str, expected_slot: dict) -> dict | None:
    """
    R10/R11/R12-konformer Verifikations-Helper für Multi-Shot-Bursts.
    Fragt /user/my-bookings ab und sucht NUR den expected_slot (court, fromTime, toTime, datum_de).
    Liefert verifiziertes Buchungs-Dict (inkl. booking_id) oder None.
    Hat KEINE Seiteneffekte (verändert aktive_buchung nicht).
    """
    http_sess = acc[k]["http"]
    csrf_t    = az_get(k, "csrf_token")
    h = _ajax_header(csrf_t, referer=f"{BASE_URL}/")

    exp_court    = int(expected_slot["court"])
    exp_from     = expected_slot["fromTime"]
    exp_to       = expected_slot["toTime"]
    exp_datum_de = expected_slot["datum_de"]

    try:
        r_pages = http_sess.get(
            f"{BASE_URL}/user/my-bookings/total-pages",
            params={"size": "50", "sort": ["serviceDate,desc", "id,desc"]},
            headers={**h, "accept": "application/json, text/javascript, */*; q=0.01"},
            timeout=10)
        if r_pages.status_code == 401:
            if not einloggen(k):
                return None
            csrf_t = az_get(k, "csrf_token")
            h["x-csrf-token"] = csrf_t

        total_pages = 1
        try:
            raw = r_pages.json()
            if isinstance(raw, (int, float, str)):
                total_pages = int(raw)
            elif isinstance(raw, dict):
                for key in ("totalPages", "total_pages", "pages", "total"):
                    if key in raw:
                        total_pages = int(raw[key])
                        break
        except Exception:
            total_pages = 1
        total_pages = max(1, min(total_pages, 5))

        for page in range(total_pages):
            r_page = http_sess.get(
                f"{BASE_URL}/user/my-bookings/page",
                params={"page": str(page), "size": "50",
                        "sort": ["serviceDate,desc", "id,desc"]},
                headers=h, timeout=10)
            if r_page.status_code != 200:
                continue
            soup   = BeautifulSoup(r_page.text, "html.parser")
            karten = soup.find_all("div", class_=lambda c: c and
                                   "col-12" in c and "col-sm-6" in c) or [soup]
            for karte in karten:
                if karte.find(class_=lambda c: c and
                              ("badge-danger" in c or "cancelled" in c or "storniert" in c)):
                    continue
                text = karte.get_text(" ", strip=True)
                d_m  = _RE_DATUM_DE.search(text)
                if not d_m or d_m.group(1) != exp_datum_de:
                    continue
                z_m = _RE_ZEIT_RANGE.search(text)
                if not z_m:
                    continue
                from_str = z_m.group(1).zfill(5)
                to_str   = z_m.group(2).zfill(5)
                if from_str != exp_from or to_str != exp_to:
                    continue
                c_m = _RE_COURT.search(text)
                court = int(c_m.group(1)) if c_m else -1
                if court != exp_court:
                    continue
                bid = None
                for pa in ["data-target", "href", "data-url", "action"]:
                    for tag in karte.find_all(attrs={pa: _RE_BOOKING_PATH}):
                        m2 = _RE_BOOKING_ID.search(tag.get(pa, ""))
                        if m2:
                            bid = int(m2.group(1))
                            break
                    if bid:
                        break
                datum_api = datum_de_zu_api(exp_datum_de)
                return {
                    "court":      exp_court,
                    "fromTime":   exp_from,
                    "toTime":     exp_to,
                    "datum_de":   exp_datum_de,
                    "datum_api":  datum_api,
                    "dauer":      dauer_minuten(exp_from, exp_to),
                    "booking_id": bid,
                    "key":        f"{datum_api}_{exp_court}_{exp_from}",
                }
    except Exception as e:
        log.warning(f"[{k}] verifiziere_slot_via_my_bookings Fehler: {e}")
    return None

# ══════════════════════════════════════════════
# AGGRESSIVE BUCHUNG
# ══════════════════════════════════════════════

def _aggressiv_buchen_07(k: str, datum_de: str, datum_api: str, dauer_min: int) -> bool:
    oeffnung = datetime.strptime(ANLAGE_OEFFNUNG, "%H:%M")
    to_07    = (oeffnung + timedelta(minutes=dauer_min)).strftime("%H:%M")
    deadline = time.time() + AGGRESSIVE_TIMEOUT
    versuch  = 0

    while time.time() < deadline:
        if not az_get(k, "schiebe_aktiv"):
            return False

        if versuch > 0 and versuch % 50 == 0:
            if not ist_eingeloggt(k):
                log.warning(f"[{k}] Dauerbeschuss: Session abgelaufen bei Versuch {versuch}")
                senden(f"🔑 [{k}] Session im Dauerbeschuss abgelaufen – logge neu ein...")
                if not einloggen(k):
                    senden(f"❌ [{k}] Neu-Login fehlgeschlagen!")
                    return False
                senden(f"✅ [{k}] Neu eingeloggt – Dauerbeschuss läuft weiter...")

        if versuch < FRUEH_EXKLUSIV_VERSUCHE:
            court_v = [2, 1][versuch % 2]
            slot    = _baue_slot_dict(court_v, "07:00", to_07,
                                      datum_de, datum_api, dauer_min)
            if buche_slot(k, slot):
                log.info(f"[{k}] 07:00 nach {versuch+1} Versuchen gebucht (Court {court_v})")
                return True
            versuch += 1
            time.sleep(AGGRESSIVE_INTERVAL)
            continue

        if versuch == FRUEH_EXKLUSIV_VERSUCHE:
            senden(f"⚠️ [{k}] 07:00 Uhr nicht buchbar nach ~2s.\n"
                   f"🔄 Wechsle auf frühesten freien Slot...")

        freie = berechne_freie_slots(k, datum_de, dauer_min)
        if freie:
            fallback = freie[0]
            log.info(f"[{k}] Fallback: {fallback['fromTime']} Court {fallback['court']}")
            if buche_slot(k, fallback):
                senden(f"✅ [{k}] Fallback-Slot gebucht: "
                       f"{fallback['fromTime']} Uhr Court {fallback['court']}")
                return True

        versuch += 1
        time.sleep(AGGRESSIVE_INTERVAL)

    return False

def _aggressiv_buchen_ab(k: str, datum_de: str, datum_api: str, dauer_min: int,
                         ab_dt: datetime, bis_dt: datetime,
                         bevorzugter_court: int = 0) -> bool:
    schluss  = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")
    deadline = time.time() + AGGRESSIVE_TIMEOUT
    versuch  = 0

    while time.time() < deadline:
        if not az_get(k, "schiebe_aktiv"):
            return False

        if versuch > 0 and versuch % 50 == 0:
            if not ist_eingeloggt(k):
                senden(f"🔑 [{k}] Session im Dauerbeschuss abgelaufen – logge neu ein...")
                if not einloggen(k):
                    senden(f"❌ [{k}] Neu-Login fehlgeschlagen!")
                    return False
                senden(f"✅ [{k}] Neu eingeloggt – Dauerbeschuss läuft weiter...")

        freie      = berechne_freie_slots(k, datum_de, dauer_min)
        kandidaten = [s for s in freie
                      if datetime.strptime(s["fromTime"], "%H:%M") >= ab_dt
                      and datetime.strptime(s["fromTime"], "%H:%M") < bis_dt
                      and datetime.strptime(s["toTime"], "%H:%M") <= schluss]
        if bevorzugter_court in (1, 2):
            prio     = [s for s in kandidaten if s["court"] == bevorzugter_court]
            fallback = [s for s in kandidaten if s["court"] != bevorzugter_court]
            kandidaten = prio + fallback
        if kandidaten and buche_slot(k, kandidaten[0]):
            return True

        versuch += 1
        time.sleep(AGGRESSIVE_INTERVAL)
    return False

# ══════════════════════════════════════════════
# BLITZ-PFAD: Pre-Warm + Burst
# ══════════════════════════════════════════════

def pre_warm_r1(k: str, court: int, datum_api: str, from_t: str, to_t: str) -> str | None:
    """
    R5/R15: Sendet NUR r1 (GET /court-single-booking-flow), liefert execution=eXs1 Token.
    NIEMALS r2 vorab feuern – Pre-Warm cached nur den Token.
    """
    snap   = az_snap(k, "csrf_token", "http")
    csrf_t = snap["csrf_token"]
    http   = snap["http"]
    h = _ajax_header(csrf_t, referer=f"{BASE_URL}/padel?currentDate={datum_api}")
    try:
        r1 = http.get(f"{BASE_URL}/court-single-booking-flow", headers=h,
                      params={"module": MODULE, "court": str(court), "courts": "1,2",
                              "fromTime": from_t, "toTime": to_t, "date": datum_api},
                      timeout=10)
        m = re.search(r"execution=(e\d+s\d+)", r1.text)
        if m:
            # Falls personId hier auftaucht, gleich cachen
            if not az_get(k, "person_id"):
                pid = extrahiere_person_id(r1.text)
                if pid:
                    az_set(k, "person_id", pid)
            return m.group(1)
    except Exception as e:
        log.warning(f"[{k}] pre_warm_r1 Court {court}: {e}")
    return None


def burst_r2_r3(k: str, court: int, execution: str, slot: dict) -> tuple[bool, dict | None]:
    """
    R5: Feuert r2 (_eventId=next) und sofort r3 (_eventId=commit) mit gecachter execution.
    SPEED-Modus (R10): keine /padel-Verifikation, Caller MUSS Sicherheitsnetz via
    verifiziere_slot_via_my_bookings() durchführen.
    Liefert (success, parsed_booking_dict_or_None).
    """
    from_t    = slot["fromTime"]
    to_t      = slot["toTime"]
    datum_de  = slot["datum_de"]
    datum_api = slot["datum_api"]
    snap      = az_snap(k, "csrf_token", "person_id", "http")
    csrf_t    = snap["csrf_token"]
    person_id = snap["person_id"]
    http      = snap["http"]
    if not person_id:
        log.warning(f"[{k}] burst Court {court}: Person-ID fehlt!")
        return False, None

    hp = {**_ajax_header(csrf_t, referer=f"{BASE_URL}/padel?currentDate={datum_api}"),
          "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
          "origin": BASE_URL}
    try:
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
        if any(w in r2.text.lower() for w in ["fehler", "error", "nicht möglich"]):
            return False, None

        r3 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                       params={"execution": exec2, "_eventId": "commit"},
                       data=f"purchaseTemplate.comment=&_csrf={csrf_t}",
                       timeout=10)
        if r3.status_code not in [200, 302]:
            return False, None
        if any(w in r3.text.lower() for w in ["fehler", "error", "nicht möglich"]):
            return False, None

        booking_id = None
        for pat in [r'"bookingId"\s*:\s*(\d+)', r'/bookings/(\d+)', r'booking[=_](\d+)']:
            mid = re.search(pat, r3.text)
            if mid:
                booking_id = int(mid.group(1))
                break
        return True, {**slot, "court": int(court), "booking_id": booking_id}
    except Exception as e:
        log.warning(f"[{k}] burst_r2_r3 Court {court}: {e}")
        return False, None


def _direkt_blitz(k: str, datum_de: str, datum_api: str, dauer_min: int,
                  buchbar_dt: datetime, courts_zu_versuchen: list[int],
                  bevorzugter_court: int = 0) -> bool:
    """
    R15–R18: Pre-Warm bei T-10s, Burst bei T-0 parallel auf bis zu 2 Courts.
    Bei Miss: bis zu MULTI_SHOT_COUNT weitere Bursts mit MULTI_SHOT_GAP_MS Pause.
    Nach jedem Treffer Sicherheitsnetz via verifiziere_slot_via_my_bookings() (R10).
    R1: Bei Doppel-Treffer (Server-Race) wird nicht-bevorzugter Court storniert.
    """
    buchbar_zeit = buchbar_dt.time()
    from_t       = buchbar_zeit.strftime("%H:%M")
    to_t         = (buchbar_dt + timedelta(minutes=dauer_min)).time().strftime("%H:%M")

    treffer      = {}      # court -> verifizierte Buchung
    treffer_lock = threading.Lock()

    def warte_bis_genau(ziel_dt: datetime):
        """Schläft präzise bis ziel_dt (lokale Berlin-Zeit, naiv)."""
        while True:
            rest = (ziel_dt - jetzt_lokal()).total_seconds()
            if rest <= 0:
                return
            if rest > 0.5:
                time.sleep(rest - 0.2)
            else:
                # letzte 200ms busy-loop für Millisekunden-Präzision
                while (ziel_dt - jetzt_lokal()).total_seconds() > 0:
                    pass
                return

    def court_worker(court: int):
        slot = _baue_slot_dict(court, from_t, to_t, datum_de, datum_api, dauer_min)

        # Pre-Warm bei T-10s
        prewarm_dt = buchbar_dt - timedelta(seconds=BLITZ_PREWARM_SECONDS)
        warte_bis_genau(prewarm_dt)
        if not az_get(k, "schiebe_aktiv"):
            return
        execution = pre_warm_r1(k, court, datum_api, from_t, to_t)
        if execution:
            log.info(f"⚡ [{k}] Pre-Warm Court {court} OK → {execution}")
        else:
            log.warning(f"[{k}] Pre-Warm Court {court} fehlgeschlagen")

        # Burst-Wellen bei T-0, T+gap, T+2*gap, ...
        for burst in range(MULTI_SHOT_COUNT + 1):
            with treffer_lock:
                if treffer:
                    return
            if not az_get(k, "schiebe_aktiv"):
                return
            fire_dt = buchbar_dt + timedelta(milliseconds=BLITZ_FIRE_OFFSET_MS
                                                          + burst * MULTI_SHOT_GAP_MS)
            warte_bis_genau(fire_dt)
            if not execution:
                execution = pre_warm_r1(k, court, datum_api, from_t, to_t)
                if not execution:
                    continue

            t0 = time.perf_counter()
            ok, parsed = burst_r2_r3(k, court, execution, slot)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            log.info(f"⚡ [{k}] Burst {burst+1}/{MULTI_SHOT_COUNT+1} Court {court}: "
                     f"ok={ok} ({dt_ms:.0f}ms)")
            if ok:
                # Sicherheitsnetz: my-bookings verifizieren
                verifiziert = verifiziere_slot_via_my_bookings(k, slot)
                if verifiziert:
                    with treffer_lock:
                        if not treffer:
                            treffer[court] = verifiziert
                    return
                else:
                    log.warning(f"[{k}] Burst Court {court}: r3 OK aber NICHT in my-bookings "
                                f"→ ignoriere (False-Positive verhindert)")
            # Neuer Pre-Warm für nächste Welle (execution ist verbraucht)
            execution = pre_warm_r1(k, court, datum_api, from_t, to_t)

    threads = [threading.Thread(target=court_worker, args=(c,), daemon=True)
               for c in courts_zu_versuchen]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if not treffer:
        return False

    # R1: Doppel-Treffer auflösen
    if len(treffer) == 2:
        nicht_bevorzugt = 1 if bevorzugter_court == 2 else 2
        if bevorzugter_court not in (1, 2):
            nicht_bevorzugt = 1   # Default Court 2 (R4) → Court 1 wird storniert
        if nicht_bevorzugt in treffer:
            other = treffer[nicht_bevorzugt]
            log.warning(f"[{k}] Doppel-Treffer! Storniere Court {nicht_bevorzugt} "
                        f"(ID {other.get('booking_id')})")
            if other.get("booking_id"):
                storniere_buchung(k, other["booking_id"], datum_api)
            del treffer[nicht_bevorzugt]

    gewinner_court = next(iter(treffer))
    az_set(k, "aktive_buchung", treffer[gewinner_court])
    return True


# ══════════════════════════════════════════════
# SCHIEBE PHASE 3
# ══════════════════════════════════════════════

def _schiebe_phase3(k: str, datum_de: str, datum_api: str, dauer_min: int, ziel_str: str):
    """
    Phase 3: Schrittweise schieben bis Zielzeit.
    Wird sowohl von _schiebe_intern als auch vom Sniper nach Treffer aufgerufen.

    FIX 2a: aktiv()-Check im Storno-Retry → stoppt sofort bei "Stopp".
    FIX 2b: Rebook nach Storno: 30 Versuche, 0.1s für erste 15, dann 0.5s.
    FIX 2c: Bestätigung nur nach verifiziertem aktive_buchung.
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

        # Schiebe-Zeitpunkt: HEUTE um (Slot-Ende - RANDOM Minuten)
        jetzt = jetzt_lokal()
        # Duo-Modus setzt ein eigenes Offset-Band pro Account (versetztes Schieben).
        # Sonst (None) das normale 5–20-Min-Random – Verhalten unverändert.
        off_min = az_get(k, "schiebe_offset_min") or SCHIEBE_MINUTEN_VOR_MIN
        off_max = az_get(k, "schiebe_offset_max") or SCHIEBE_MINUTEN_VOR_MAX
        random_offset  = random.randint(off_min, off_max)
        schiebe_moment = datetime.combine(
            jetzt.date(),                                  # ← HEUTE, nicht datum_obj!
            (ende_dt - timedelta(minutes=random_offset)).time())

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

        # Erzwungener Session-Refresh VOR Stornierung
        log.info(f"[{k}] Erzwungener Login vor Stornierung (Schiebe-Loop)...")
        if not _session_refresh_vor_aktion(k, f"Stornierung {aktive_b['fromTime']}"):
            senden(f"❌ [{k}] Session vor Stornierung fehlgeschlagen – retry in 10s.")
            if not schlafe(10):
                return
            continue

        # ── BLITZ-SCHIEBEN, Schritt 1: PRE-WARM r1 VOR dem Storno ─────────────
        # Holt den r1-Formular-/execution-Token, solange die alte Buchung noch
        # hält (kein Risiko – Slot bleibt belegt). Im kritischen Fenster NACH dem
        # Storno feuern dann nur noch r2+r3 (burst_r2_r3) → kleinstmögliches
        # Klau-Fenster. Nur aktueller Court (bzw. fester Duo-Court).
        # Leerer Token → Fallback auf klassischen buche_slot-Loop (kein Risiko).
        duo_court    = az_get(k, "duo_court")
        blitz_court  = duo_court if duo_court in (1, 2) else aktive_b["court"]
        ziel_slot    = _baue_slot_dict(blitz_court, naechster_von, naechster_bis,
                                       datum_de, datum_api, dauer_min)
        prewarm_exec = pre_warm_r1(k, blitz_court, datum_api,
                                   naechster_von, naechster_bis)
        if prewarm_exec:
            log.info(f"⚡ [{k}] Schiebe-Prewarm Court {blitz_court} OK → {prewarm_exec}")
        else:
            log.warning(f"[{k}] Schiebe-Prewarm Court {blitz_court} leer "
                        f"→ Fallback buche_slot")

        storno_ok = False
        for storno_versuch in range(6):
            if not aktiv():
                return
            if storniere_buchung(k, booking_id, datum_api):
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

        gerade_court = aktive_b["court"]   # für eff_court-Fallback weiter unten

        # ── BLITZ-SCHIEBEN, Schritt 2: SPEED-Burst r2+r3 mit vorgewärmtem Token ──
        # Genau wie _direkt_blitz, nur ausgelöst durch "nach Storno" statt
        # "bei Freischaltung". Nur EIN Court (aktueller/Duo-Court), Multi-Shot,
        # SPEED-Verifikation per my-bookings (kein 1–2,5s Verify-Sleep pro Schuss).
        ok = False
        if prewarm_exec:
            execution = prewarm_exec
            for welle in range(MULTI_SHOT_COUNT + 1):
                if not aktiv():
                    return
                if not execution:
                    execution = pre_warm_r1(k, blitz_court, datum_api,
                                            naechster_von, naechster_bis)
                    if not execution:
                        time.sleep(MULTI_SHOT_GAP_MS / 1000.0)
                        continue
                t0 = time.perf_counter()
                erfolg, _ = burst_r2_r3(k, blitz_court, execution, ziel_slot)
                dt_ms = (time.perf_counter() - t0) * 1000.0
                log.info(f"⚡ [{k}] Schiebe-Burst {welle+1}/{MULTI_SHOT_COUNT+1} "
                         f"Court {blitz_court}: ok={erfolg} ({dt_ms:.0f}ms)")
                if erfolg:
                    verifiziert = verifiziere_slot_via_my_bookings(k, ziel_slot)
                    if verifiziert:
                        az_set(k, "aktive_buchung", verifiziert)
                        ok = True
                        break
                    log.warning(f"[{k}] Schiebe-Burst r3 OK aber nicht in "
                                f"my-bookings → nächste Welle")
                # Token ist verbraucht → für die nächste Welle neu vorwärmen
                execution = pre_warm_r1(k, blitz_court, datum_api,
                                        naechster_von, naechster_bis)
                time.sleep(MULTI_SHOT_GAP_MS / 1000.0)

        # ── Fallback: klassischer buche_slot-Loop (nur aktueller Court) ──
        # Greift, wenn der Prewarm-Token leer war oder alle Blitz-Wellen daneben
        # lagen. Verhält sich dann exakt wie bisher – nur ohne Court-Alternieren
        # (User-Vorgabe: nur aktueller Court).
        if not ok:
            for versuch in range(30):
                if not aktiv():
                    return
                if buche_slot(k, ziel_slot):
                    ok = True
                    break
                time.sleep(0.1 if versuch < 15 else 0.5)

        # Sicherheitsnetz: r3 kann serverseitig gebucht haben, während die
        # Verifikation knapp daneben lag. Vor dem Aufgeben einmal die eigenen
        # Buchungen prüfen (seiteneffektfrei).
        if not ok:
            verifiziert = verifiziere_slot_via_my_bookings(k, ziel_slot)
            if verifiziert:
                az_set(k, "aktive_buchung", verifiziert)
                log.info(f"[{k}] Schiebe: Neubuchung per my-bookings bestätigt "
                         f"(verzögerte Verifikation).")
                ok = True

        letzter_session_check = time.time()

        if ok:
            gebuchter = az_get(k, "aktive_buchung")
            if not gebuchter:
                # Fallback: expliziter Sync
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
# SCHIEBE-TAKTIK
# ══════════════════════════════════════════════

def schiebe_loop(k: str):
    try:
        _schiebe_intern(k)
    except Exception as e:
        log.error(f"[{k}] SCHIEBE CRASH: {e}", exc_info=True)
        senden(f"💥 <b>[{k}] Schiebe-Taktik abgestürzt!</b>\n{e}")
        az_set(k, "schiebe_aktiv", False)
        zeige_account_menue(k)

def _schiebe_intern(k: str):
    log.info(f"🔄 [{k}] Schiebe-Loop gestartet")
    datum_de   = az_get(k, "schiebe_datum")
    ziel_str   = az_get(k, "schiebe_ziel")
    dauer_min  = az_get(k, "schiebe_dauer") or 90
    modus      = az_get(k, "schiebe_modus") or "frueh"
    buchbar_ab = az_get(k, "schiebe_buchbar_ab")

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

    # ── Phase 1: Warten auf 7-Tage-Fenster ───────────────────────────────────
    if modus in ("frueh", "direkt"):
        fenster_tag = (datum_obj - timedelta(days=7)).date()
        if modus == "direkt" and buchbar_ab:
            # Echte Freischaltung: 7×24h vor dem Slot, zur gewählten Buchungszeit.
            unlock_dt = datetime.combine(fenster_tag,
                                         datetime.strptime(buchbar_ab, "%H:%M").time())
            # Kurz davor aufwachen – Phase 2 macht Login + Pre-Warm + präzisen Blitz.
            ziel_wach = unlock_dt - timedelta(seconds=PHASE1_HANDOFF_MARGIN)
        else:
            # Früh-Methode: fix auf 07:00 (der 07:00-Slot wird dann freigeschaltet).
            unlock_dt = datetime.combine(fenster_tag,
                                         datetime.strptime("07:00", "%H:%M").time())
            ziel_wach = unlock_dt
        while aktiv():
            jetzt = jetzt_lokal()
            if jetzt >= ziel_wach:
                break
            sek_bis = (unlock_dt - jetzt).total_seconds()   # Countdown zur echten Freischaltung

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
                   f"🔓 Buchbar ab: {unlock_dt.strftime('%d.%m.%Y um %H:%M Uhr')}\n"
                   f"⏱️ Noch {warte_str_w}")

            sek_bis_wach = (ziel_wach - jetzt).total_seconds()
            schlaf = min(sek_bis_wach - 30, 23 * 3600)
            if schlaf > 1:
                if not schlafe(schlaf):
                    return
            else:
                if not schlafe(max(0, sek_bis_wach)):
                    return
                break

    if not aktiv():
        return

    # ── Phase 2: Ersten Slot buchen ───────────────────────────────────────────
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

        if not _aggressiv_buchen_07(k, datum_de, datum_api, dauer_min):
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
        ok = False
        for versuch in range(30):
            if not aktiv():
                return
            datum_api_z    = datetime.strptime(datum_de, "%d.%m.%Y").strftime("%m/%d/%Y")
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
                ok = True
                break
            if not schlafe(3):
                return
        if not ok:
            beende(f"❌ [{k}] Kein buchbarer Slot gefunden.")
            return

    elif modus == "direkt":
        if not buchbar_ab:
            beende(f"❌ [{k}] Keine Startzeit angegeben.")
            return

        jetzt        = jetzt_lokal()
        buchbar_zeit = datetime.strptime(buchbar_ab, "%H:%M").time()
        buchbar_dt   = datetime.combine(jetzt.date(), buchbar_zeit)
        direkt_court = az_get(k, "schiebe_court") or 0
        # max 2 Threads/Account – bei "Egal" beide Courts parallel, sonst nur gewählter
        if direkt_court in (1, 2):
            courts_zu_versuchen = [direkt_court]
        else:
            courts_zu_versuchen = [2, 1]   # R4: Court 2 zuerst

        if jetzt < buchbar_dt:
            sek_wait = (buchbar_dt - jetzt).total_seconds()
            senden(f"🎯 <b>[{k}] Direkte Taktik – Blitz-Modus</b>\n"
                   f"📅 {datum_de} | Buchbar ab heute {buchbar_ab} Uhr\n"
                   f"🎯 Ziel: {ziel_str} Uhr | {dauer_min} Min\n"
                   f"⚡ Courts: {', '.join(map(str, courts_zu_versuchen))} parallel\n"
                   f"⏳ Noch {int(sek_wait/60)} Min bis {buchbar_ab} Uhr...")
            # R14: 90s Marge bis Login-Refresh
            if not schlafe(max(0, sek_wait - 90)):
                return
            senden(f"🔑 [{k}] Frischer Login 90s vor {buchbar_ab} Uhr...")
            if not _session_refresh_vor_aktion(k, f"Direkt {buchbar_ab}"):
                beende(f"❌ [{k}] Login vor {buchbar_ab} fehlgeschlagen!")
                return
            senden(f"✅ [{k}] Eingeloggt – Pre-Warm bei T-{BLITZ_PREWARM_SECONDS}s, "
                   f"Burst bei {buchbar_ab}:00.000")
        else:
            if not _session_refresh_vor_aktion(k, f"Direkt sofort ab {buchbar_ab}"):
                beende(f"❌ [{k}] Login fehlgeschlagen!")
                return
            # Wenn buchbar_dt schon vorbei: feuere sofort als ab_dt = jetzt
            buchbar_dt = jetzt_lokal() + timedelta(seconds=1)

        # ── BLITZ-PFAD ──────────────────────────────────────────────────────────
        erfolg = _direkt_blitz(k, datum_de, datum_api, dauer_min,
                               buchbar_dt, courts_zu_versuchen,
                               bevorzugter_court=direkt_court)

        # ── Fallback: Klassischer Dauerbeschuss falls Blitz versagt ─────────────
        if not erfolg:
            senden(f"⚠️ [{k}] Blitz verfehlt – wechsle auf klassischen Dauerbeschuss...")
            ab_dt = datetime.strptime(buchbar_ab, "%H:%M")
            if not _aggressiv_buchen_ab(k, datum_de, datum_api, dauer_min,
                                        ab_dt, ziel_dt, bevorzugter_court=direkt_court):
                beende(f"❌ [{k}] Kein Slot ab {buchbar_ab} Uhr buchbar.")
                return

        buchung = az_get(k, "aktive_buchung")
        senden(f"✅ <b>[{k}] Direkt-Slot gebucht!</b>\n"
               f"🕐 {buchung['fromTime']}–{buchung['toTime']} | Court {buchung['court']}\n"
               f"🔄 Schiebe Richtung {ziel_str} Uhr...")

    # ── Phase 3: Schrittweise schieben ───────────────────────────────────────
    _schiebe_phase3(k, datum_de, datum_api, dauer_min, ziel_str)

# ══════════════════════════════════════════════
# SNIPER
# ══════════════════════════════════════════════

def sniper_loop(k: str):
    try:
        _sniper_intern(k)
    except Exception as e:
        log.error(f"[{k}] SNIPER CRASH: {e}", exc_info=True)
        senden(f"💥 <b>[{k}] Sniper abgestürzt!</b>\n{e}")
        az_set(k, "sniper_aktiv", False)
        zeige_account_menue(k)

def _sniper_intern(k: str):
    """
    Smart-Sniper (R20–R23) – v11:

    Phase 0 (Schlaf-Phase):
      - lauer_start    = fremder_bis - SNIPER_PRE_END_MINUTES
      - login_refresh  = lauer_start - SNIPER_LOGIN_BUFFER
      - Schlaf bis login_refresh, dann Session-Refresh, Schlaf bis lauer_start

    Phase 1 (Lauern, lauer_start bis fremder_bis):
      - Ziel-Slot: fremder_bis - 30min bis +dauer (R21: bei fremder Startzeit-Position,
        d.h. überlappt mit den letzten 30 Min der fremden Buchung).
      - Hämmere alle SNIPER_PHASE1_INTERVAL (0.1s) mit verify_person_id=True (STRIKT)
      - R23: Nur 1 Court (Court des Fremden).

    Phase 2 (Blitz, ab fremder_bis):
      - Ziel-Slot: fremder_bis bis +dauer (direkt anschließend, durch 7-Tage-Regel
        frisch freigeschaltet).
      - Pre-Warm bei T-BLITZ_PREWARM_SECONDS, Burst bei T-0 + Multi-Shot.
      - R23: NUR Court des Fremden (paralleler 2. Court könnte blockieren).
      - SPEED-Modus + Sicherheitsnetz via verifiziere_slot_via_my_bookings (R10).

    Deadline (R22): fremder_bis + SNIPER_DEADLINE_BUFFER (60s nach fremder Endzeit).
    Tag der Hammer-/Blitz-Phase: sniper_datum − 7 Tage (7-Tage-Regel). Bei näherem
    Ziel fällt der Unlock-Tag auf heute oder davor → läuft ab heute.

    Beispiel: Fremder Court 2, 17:00–18:30, Ziel 20:00 Uhr, Dauer 90 Min
      → Lauer-Start  : 18:00
      → Login-Refresh: 17:55
      → Phase 1      : 18:00–18:30 hämmert Slot 18:00–19:30 Court 2 (verify=True)
      → Phase 2      : ab 18:30 Blitz auf Slot 18:30–20:00 Court 2 (verify=False+Sync)
      → Deadline     : 18:31:00
    """
    datum_de    = az_get(k, "sniper_datum")
    fremder_bis = az_get(k, "sniper_fremder_bis")
    court       = az_get(k, "sniper_court")
    dauer_min   = az_get(k, "sniper_dauer")
    ziel_str    = az_get(k, "sniper_ziel")

    datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
    datum_api = datum_obj.strftime("%m/%d/%Y")

    # 7-Tage-Regel: Unlock-Tag = Buchungs-Tag − 7. Bei knapperem Zielzeitraum
    # (Slot bereits vor heute freigeschaltet) hämmert der Sniper ab heute auf
    # fremde Stornierung — Phase 2 läuft dann ins Leere, ist aber unschädlich.
    jetzt = jetzt_lokal()
    fremder_bis_time = datetime.strptime(fremder_bis, "%H:%M").time()
    unlock_day = max((datum_obj - timedelta(days=7)).date(), jetzt.date())
    fremder_bis_dt = datetime.combine(unlock_day, fremder_bis_time)

    lauer_start_dt   = fremder_bis_dt - timedelta(minutes=SNIPER_PRE_END_MINUTES)
    login_refresh_dt = lauer_start_dt - timedelta(minutes=SNIPER_LOGIN_BUFFER)
    deadline_dt      = fremder_bis_dt + timedelta(seconds=SNIPER_DEADLINE_BUFFER)

    # Phase-1-Ziel: überlappt mit letzten 30 Min der fremden Buchung
    p1_von_dt = fremder_bis_dt - timedelta(minutes=SNIPER_PRE_END_MINUTES)
    p1_bis_dt = p1_von_dt + timedelta(minutes=dauer_min)
    p1_von    = p1_von_dt.time().strftime("%H:%M")
    p1_bis    = p1_bis_dt.time().strftime("%H:%M")

    # Phase-2-Ziel: direkt nach fremder Endzeit
    p2_von_dt = fremder_bis_dt
    p2_bis_dt = p2_von_dt + timedelta(minutes=dauer_min)
    p2_von    = p2_von_dt.time().strftime("%H:%M")
    p2_bis    = p2_bis_dt.time().strftime("%H:%M")

    p1_slot = _baue_slot_dict(court, p1_von, p1_bis, datum_de, datum_api, dauer_min)
    p2_slot = _baue_slot_dict(court, p2_von, p2_bis, datum_de, datum_api, dauer_min)

    tag_hinweis = "" if unlock_day == jetzt.date() else f" am {unlock_day.strftime('%d.%m.')}"
    senden(f"🎯 <b>[{k}] Smart-Sniper aktiv!</b>\n"
           f"📅 {_datum_mit_tag(datum_de)}\n"
           f"🏟️ Court {court} | Fremde endet: {fremder_bis} Uhr{tag_hinweis}\n"
           f"💤 Schlafe bis {login_refresh_dt.strftime('%H:%M')}{tag_hinweis} "
           f"(Login {SNIPER_LOGIN_BUFFER}min vor Lauer-Start)\n"
           f"👀 Phase 1 Lauern: {lauer_start_dt.strftime('%H:%M')}–{fremder_bis} "
           f"auf {p1_von}–{p1_bis}\n"
           f"⚡ Phase 2 Blitz : ab {fremder_bis} auf {p2_von}–{p2_bis}\n"
           f"⏱️ Deadline       : {deadline_dt.strftime('%H:%M:%S')}{tag_hinweis}\n"
           f"🔄 Nach Treffer → Schiebe bis {ziel_str} Uhr")

    def aktiv() -> bool:
        return az_get(k, "sniper_aktiv")

    def schlafe_bis(ziel_dt: datetime) -> bool:
        """Schläft in Chunks bis ziel_dt. Liefert False wenn abgebrochen."""
        while aktiv():
            rest = (ziel_dt - jetzt_lokal()).total_seconds()
            if rest <= 0:
                return True
            time.sleep(min(rest, 1.0))
        return False

    def trigger_phase3(treffer: dict, phase_label: str, versuche: int):
        wetter_str = hole_wetter(datum_de, treffer.get("fromTime", ""))
        senden(f"🎯 <b>[{k}] SNIPER TREFFER ({phase_label})!</b>\n"
               f"📅 {_datum_mit_tag(datum_de)}\n"
               f"🕐 {treffer['fromTime']}–{treffer['toTime']} | Court {treffer['court']}\n"
               f"🏆 Nach {versuche} Versuchen!\n"
               f"🔄 Schiebe weiter → {ziel_str} Uhr..."
               + wetter_str)
        az_set(k, "sniper_aktiv", False)
        az_set(k, "aktive_buchung", treffer)
        az_set_multi(k,
            schiebe_aktiv=True,
            schiebe_datum=datum_de,
            schiebe_ziel=ziel_str,
            schiebe_dauer=dauer_min,
            schiebe_modus="sniper",
        )
        _schiebe_phase3(k, datum_de, datum_api, dauer_min, ziel_str)

    # ── Phase 0: Schlafen bis Login-Refresh ─────────────────────────────────
    if jetzt_lokal() < login_refresh_dt:
        if not schlafe_bis(login_refresh_dt):
            senden(f"⏹️ [{k}] Sniper gestoppt (Phase 0).")
            az_set(k, "sniper_aktiv", False)
            zeige_account_menue(k)
            return

    if not aktiv():
        az_set(k, "sniper_aktiv", False)
        zeige_account_menue(k)
        return

    senden(f"🔑 [{k}] Frischer Login vor Lauer-Start...")
    if not _session_refresh_vor_aktion(k, "Sniper Lauer-Start"):
        senden(f"❌ [{k}] Sniper: Login fehlgeschlagen!")
        az_set(k, "sniper_aktiv", False)
        zeige_account_menue(k)
        return

    # Warten bis Lauer-Start
    if jetzt_lokal() < lauer_start_dt:
        if not schlafe_bis(lauer_start_dt):
            senden(f"⏹️ [{k}] Sniper gestoppt (vor Lauer-Start).")
            az_set(k, "sniper_aktiv", False)
            zeige_account_menue(k)
            return

    # ── Phase 1: Lauern (STRIKT) ────────────────────────────────────────────
    # Phase 1 stoppt bei prewarm_dt (= fremder_bis − BLITZ_PREWARM_SECONDS),
    # damit Phase 2 in Ruhe pre-warmen und ms-präzise auf fremder_bis blitzen kann.
    prewarm_dt = fremder_bis_dt - timedelta(seconds=BLITZ_PREWARM_SECONDS)
    # Ein buche_slot-Versuch dauert ~3s (r1+r2+r3 + 1s Verify-Sleep). Bei knapper
    # Restzeit lieber sauber stoppen, statt in den Pre-Warm-Bereich reinzulaufen.
    MIN_REST_FOR_BUCHE = 3.5

    senden(f"👀 [{k}] Phase 1 LAUERN auf {p1_von}–{p1_bis} Court {court}\n"
           f"   Hammer bis {prewarm_dt.strftime('%H:%M:%S')}, dann Blitz-Vorbereitung")
    versuche      = 0
    letzter_login = time.time()
    while aktiv() and jetzt_lokal() < prewarm_dt:
        # Session-Refresh alle 60s
        if versuche > 0 and time.time() - letzter_login > 60:
            if not ist_eingeloggt(k):
                if not einloggen(k):
                    senden(f"❌ [{k}] Sniper P1: Login fehlgeschlagen.")
                    az_set(k, "sniper_aktiv", False)
                    zeige_account_menue(k)
                    return
            letzter_login = time.time()

        # Kein neuer Versuch, wenn er in den Pre-Warm-Bereich hineinlaufen würde.
        if (prewarm_dt - jetzt_lokal()).total_seconds() < MIN_REST_FOR_BUCHE:
            break

        if buche_slot(k, p1_slot, verify_person_id=True):
            treffer = az_get(k, "aktive_buchung")
            if treffer:
                trigger_phase3(treffer, "Phase 1 Lauer", versuche + 1)
                return

        versuche += 1
        time.sleep(SNIPER_PHASE1_INTERVAL)

    if not aktiv():
        senden(f"⏹️ [{k}] Sniper gestoppt nach Phase 1 ({versuche} Versuche).")
        az_set(k, "sniper_aktiv", False)
        zeige_account_menue(k)
        return

    # ── Phase 2: Pre-Warm bei T-10s, Burst exakt bei T-0 (ms-Präzision) ────
    def warte_bis_genau(ziel_dt: datetime):
        """Präzises Warten bis ziel_dt. Letzte 200ms busy-loop für ms-Genauigkeit."""
        while True:
            rest = (ziel_dt - jetzt_lokal()).total_seconds()
            if rest <= 0:
                return
            if rest > 0.5:
                time.sleep(rest - 0.2)
            else:
                while (ziel_dt - jetzt_lokal()).total_seconds() > 0:
                    pass
                return

    senden(f"⚡ [{k}] Phase 2 Blitz-Vorbereitung auf {p2_von}–{p2_bis} Court {court}\n"
           f"   Pre-Warm jetzt → Burst exakt um {fremder_bis_dt.strftime('%H:%M:%S')}")
    p2_versuche = 0

    # Pre-Warm sofort (T-~10s). Cached execution-Token vor dem Burst-Zeitpunkt.
    execution = pre_warm_r1(k, court, datum_api, p2_von, p2_bis)
    if execution:
        log.info(f"⚡ [{k}] Sniper P2 Pre-Warm OK → {execution}")
    else:
        log.warning(f"[{k}] Sniper P2 Pre-Warm fehlgeschlagen – Burst-Schleife holt nach.")

    # Präzise warten bis fremder_bis_dt (= buchbar_dt für p2_slot)
    warte_bis_genau(fremder_bis_dt)

    # Burst-Wellen: T+0, T+gap, T+2*gap, …
    for burst in range(MULTI_SHOT_COUNT + 1):
        if not aktiv() or jetzt_lokal() > deadline_dt:
            break
        fire_dt = fremder_bis_dt + timedelta(milliseconds=BLITZ_FIRE_OFFSET_MS
                                                          + burst * MULTI_SHOT_GAP_MS)
        warte_bis_genau(fire_dt)

        if not execution:
            execution = pre_warm_r1(k, court, datum_api, p2_von, p2_bis)
            if not execution:
                continue

        t0 = time.perf_counter()
        ok, parsed = burst_r2_r3(k, court, execution, p2_slot)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        log.info(f"⚡ [{k}] Sniper P2 Burst {burst+1}: ok={ok} ({dt_ms:.0f}ms)")
        p2_versuche += 1
        if ok:
            verifiziert = verifiziere_slot_via_my_bookings(k, p2_slot)
            if verifiziert:
                trigger_phase3(verifiziert, "Phase 2 Blitz",
                               versuche + p2_versuche)
                return
            else:
                log.warning(f"[{k}] Sniper P2 Burst r3 OK aber nicht in my-bookings.")
        # Verbrauchten Token sofort erneuern für die nächste Welle.
        execution = pre_warm_r1(k, court, datum_api, p2_von, p2_bis)

    senden(f"❌ [{k}] Sniper-Deadline erreicht. Fremder hat nicht storniert und "
           f"Blitz hat den frisch freigeschalteten Slot nicht erwischt.\n"
           f"   Phase 1: {versuche} Versuche, Phase 2: {p2_versuche} Bursts.")
    az_set(k, "sniper_aktiv", False)
    zeige_account_menue(k)

# ══════════════════════════════════════════════
# FREITEXT-HANDLER
# ══════════════════════════════════════════════

def handle_text(k: str, text: str):
    flow = az_get(k, "flow") if k else None
    if flow != "direkte_startzeit":
        zeige_account_auswahl()
        return

    m = re.match(r"^(\d{1,2}):(\d{2})$", text.strip())
    if not m:
        senden("❌ Ungültiges Format. Bitte als <b>HH:MM</b> eingeben, z.B. <b>13:00</b>")
        return

    stunde, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= stunde <= 21 and minute in [0, 30]):
        senden("❌ Zeit muss auf 30-Min-Raster liegen (z.B. 13:00 oder 13:30)")
        return

    buchbar_ab = f"{stunde:02d}:{minute:02d}"
    az_set_multi(k, schiebe_buchbar_ab=buchbar_ab, schiebe_aktiv=True, flow=None)

    datum     = az_get(k, "schiebe_datum")
    dauer     = az_get(k, "schiebe_dauer")
    ziel      = az_get(k, "schiebe_ziel")
    datum_obj = datetime.strptime(datum, "%d.%m.%Y")
    tage_bis  = (datum_obj.date() - jetzt_lokal().date()).days
    jetzt     = jetzt_lokal()
    # Echte Freischaltung: 7×24h vor dem Slot, zur gewählten Buchungszeit.
    unlock_dt = datetime.combine((datum_obj - timedelta(days=7)).date(),
                                 datetime.strptime(buchbar_ab, "%H:%M").time())
    if unlock_dt <= jetzt:
        frei_txt = "🚀 Slot bereits freigeschaltet – Blitz startet sofort!"
    else:
        rest = unlock_dt - jetzt
        h = rest.seconds // 3600
        m = (rest.seconds % 3600) // 60
        rest_str = (f"{rest.days}T {h}h {m}min" if rest.days > 0
                    else f"{h}h {m}min" if h > 0 else f"{m}min")
        frei_txt = f"⏳ Freischaltung in {rest_str}"

    senden(f"🎯 <b>[{k}] Direkte Taktik konfiguriert!</b>\n"
           f"📅 {datum} (in {tage_bis} Tagen)\n"
           f"🔓 Buchbar ab: {unlock_dt.strftime('%d.%m.%Y um %H:%M Uhr')}\n"
           f"🎯 Schiebe-Ziel: {ziel} Uhr ({dauer} Min)\n"
           f"{frei_txt}")

    t = threading.Thread(target=schiebe_loop, args=(k,), daemon=True)
    t.start()
    az_set(k, "schiebe_thread", t)
    zeige_account_auswahl()

# ══════════════════════════════════════════════
# DUO-MODUS (2 Accounts parallel, Basis = Direkte Taktik)
# ══════════════════════════════════════════════

def handle_duo_callback(data: str):
    """Verarbeitet alle 'duo_*'-Callbacks (Account-Auswahl → Datum → Ziel)."""
    if data == "duo_start":
        frei = [k for k in ACCOUNTS if _account_frei(k)]
        if len(frei) < 2:
            senden("👥 <b>Duo-Modus</b> braucht <b>2 freie Accounts</b> "
                   "(ohne aktive Buchung/Schiebe/Sniper).")
            zeige_account_auswahl()
            return
        _duo_reset()
        btns = [[{"text": account_status_label(k), "callback_data": f"duo_pa_{k}"}]
                for k in frei]
        btns.append([{"text": "❌ Abbrechen", "callback_data": "duo_cancel"}])
        senden("👥 <b>Duo-Modus</b> – 2 Accounts parallel auf Court 1 + Court 2\n\n"
               "Wähle den <b>1. Account</b> → 🏟️ <b>Court 1</b>:", buttons=btns)
        return

    if data == "duo_cancel":
        _duo_reset()
        senden("↩️ Duo-Modus abgebrochen.")
        zeige_account_auswahl()
        return

    if data.startswith("duo_pa_"):
        k = data[len("duo_pa_"):]
        if k not in acc or not _account_frei(k):
            senden("❌ Account nicht (mehr) frei. Bitte Duo neu starten.")
            _duo_reset()
            zeige_account_auswahl()
            return
        with _duo_lock:
            _duo["acc_a"] = k
        rest = [x for x in ACCOUNTS if x != k and _account_frei(x)]
        if not rest:
            senden("❌ Kein zweiter freier Account verfügbar.")
            _duo_reset()
            zeige_account_auswahl()
            return
        btns = [[{"text": account_status_label(x), "callback_data": f"duo_pb_{x}"}]
                for x in rest]
        btns.append([{"text": "❌ Abbrechen", "callback_data": "duo_cancel"}])
        senden(f"👥 Duo | 🏟️ Court 1: <b>{k}</b>\n\n"
               f"Wähle den <b>2. Account</b> → 🏟️ <b>Court 2</b>:", buttons=btns)
        return

    if data.startswith("duo_pb_"):
        k = data[len("duo_pb_"):]
        with _duo_lock:
            a = _duo["acc_a"]
        if not a:
            senden("❌ Duo-Flow unterbrochen – bitte neu starten.")
            _duo_reset()
            zeige_account_auswahl()
            return
        if k == a or k not in acc or not _account_frei(k):
            senden("❌ Bitte einen ANDEREN freien Account wählen.")
            return
        with _duo_lock:
            _duo["acc_b"] = k
        senden(f"👥 Duo | 🏟️ C1: <b>{a}</b> | 🏟️ C2: <b>{k}</b>\n\n"
               f"📅 Für welches <b>Datum</b>?",
               buttons=erstelle_datum_buttons("duo_datum"))
        return

    if data.startswith("duo_datum_"):
        datum = data[len("duo_datum_"):]
        with _duo_lock:
            _duo["datum"] = datum
            a, b = _duo["acc_a"], _duo["acc_b"]
        if not (a and b):
            senden("❌ Duo-Flow unterbrochen – bitte neu starten.")
            _duo_reset()
            zeige_account_auswahl()
            return
        senden(f"👥 Duo | 📅 {datum} | 90 Min\n\n"
               f"🎯 <b>Bis wohin soll geschoben werden?</b> (Zielzeit)",
               buttons=zielzeit_buttons("duo_ziel", DUO_DAUER_MIN))
        return

    if data.startswith("duo_ziel_"):
        ziel = data[len("duo_ziel_"):]
        with _duo_lock:
            _duo["ziel"] = ziel
            a, b, datum  = _duo["acc_a"], _duo["acc_b"], _duo["datum"]
            if a and b and datum:
                _duo["flow"] = "startzeit"
        if not (a and b and datum):
            senden("❌ Duo-Flow unterbrochen – bitte neu starten.")
            _duo_reset()
            zeige_account_auswahl()
            return
        senden(f"👥 <b>Duo-Modus</b>\n"
               f"🏟️ C1: {a} | 🏟️ C2: {b}\n"
               f"📅 {datum} | 🎯 Ziel: {ziel} Uhr | 90 Min\n\n"
               f"⏰ <b>Ab wann ist der Slot buchbar?</b>\n"
               f"Bitte Uhrzeit tippen (30-Min-Raster, z.B. <b>17:30</b>):\n\n"
               f"<i>Beide Accounts blitzen dann gleichzeitig auf ihren Court.</i>")
        return

    senden("❓ Unbekannte Duo-Aktion.")
    _duo_reset()
    zeige_account_auswahl()


def handle_duo_text(text: str):
    """Verarbeitet die getippte Buchbar-ab-Zeit und startet beide Duo-Accounts."""
    m = re.match(r"^(\d{1,2}):(\d{2})$", text.strip())
    if not m:
        senden("❌ Ungültiges Format. Bitte als <b>HH:MM</b> eingeben, z.B. <b>17:30</b>")
        return
    stunde, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= stunde <= 21 and minute in (0, 30)):
        senden("❌ Zeit muss auf 30-Min-Raster liegen (z.B. 17:00 oder 17:30)")
        return
    buchbar_ab = f"{stunde:02d}:{minute:02d}"
    with _duo_lock:
        a     = _duo["acc_a"]
        b     = _duo["acc_b"]
        datum = _duo["datum"]
        ziel  = _duo["ziel"]
        _duo["flow"] = None
    if not (a and b and datum and ziel):
        senden("❌ Duo-Konfiguration unvollständig – bitte neu starten.")
        _duo_reset()
        zeige_account_auswahl()
        return
    if not _account_frei(a) or not _account_frei(b):
        senden("⚠️ Einer der beiden Accounts ist nicht mehr frei – Duo abgebrochen.")
        _duo_reset()
        zeige_account_auswahl()
        return
    _starte_duo(a, b, datum, ziel, buchbar_ab)
    _duo_reset()


def _starte_duo(a: str, b: str, datum: str, ziel: str, buchbar_ab: str):
    """Konfiguriert beide Accounts als Direkt-Schiebe (Court 1 / Court 2) mit
    versetztem Schiebe-Offset-Band und startet beide Threads gleichzeitig."""
    konfig = [
        (a, 1, DUO_COURT1_OFFSET_MIN, DUO_COURT1_OFFSET_MAX),
        (b, 2, DUO_COURT2_OFFSET_MIN, DUO_COURT2_OFFSET_MAX),
    ]
    for (k, court, omin, omax) in konfig:
        az_set_multi(k,
            schiebe_modus="direkt",
            schiebe_datum=datum,
            schiebe_ziel=ziel,
            schiebe_dauer=DUO_DAUER_MIN,
            schiebe_court=court,
            schiebe_buchbar_ab=buchbar_ab,
            schiebe_offset_min=omin,
            schiebe_offset_max=omax,
            duo_court=court,          # fester Court im Schiebe-Rebook (kein Alternieren)
            schiebe_aktiv=True,
            flow=None,
        )

    datum_obj = datetime.strptime(datum, "%d.%m.%Y")
    unlock_dt = datetime.combine((datum_obj - timedelta(days=7)).date(),
                                 datetime.strptime(buchbar_ab, "%H:%M").time())
    jetzt = jetzt_lokal()
    if unlock_dt <= jetzt:
        frei_txt = "🚀 Slot bereits freigeschaltet – beide blitzen sofort!"
    else:
        rest = unlock_dt - jetzt
        h  = rest.seconds // 3600
        mi = (rest.seconds % 3600) // 60
        rest_str = (f"{rest.days}T {h}h {mi}min" if rest.days > 0
                    else f"{h}h {mi}min" if h > 0 else f"{mi}min")
        frei_txt = f"⏳ Freischaltung in {rest_str}"

    senden(
        f"👥 <b>Duo-Modus gestartet!</b>\n"
        f"📅 {_datum_mit_tag(datum)} | 🎯 Ziel: {ziel} Uhr | 90 Min\n"
        f"🔓 Buchbar ab: {unlock_dt.strftime('%d.%m.%Y um %H:%M Uhr')}\n\n"
        f"🏟️ <b>Court 1</b>: {a}  (schiebt {DUO_COURT1_OFFSET_MIN}–{DUO_COURT1_OFFSET_MAX} Min vor Ende)\n"
        f"🏟️ <b>Court 2</b>: {b}  (schiebt {DUO_COURT2_OFFSET_MIN}–{DUO_COURT2_OFFSET_MAX} Min vor Ende)\n\n"
        f"⚡ Beide blitzen gleichzeitig, schieben aber versetzt (~5–6 Min Abstand).\n"
        f"{frei_txt}")

    for (k, court, omin, omax) in konfig:
        t = threading.Thread(target=schiebe_loop, args=(k,), daemon=True)
        t.start()
        az_set(k, "schiebe_thread", t)

    zeige_account_auswahl()


# ══════════════════════════════════════════════
# 3h-MODUS (Block: Acc1 schiebt bis Wunschanfang → Acc2 blitzt Anschluss)
# ══════════════════════════════════════════════

def handle_block_callback(data: str):
    """Verarbeitet alle 'block_*'-Callbacks (Account-Auswahl → Datum → Court →
    Wunschanfang). Acc1 = Schieber (Direkte Taktik bis Wunschanfang),
    Acc2 = Anschluss-Blitz auf den direkt folgenden 90-Min-Slot.
    Baut nur auf bestehenden Bausteinen auf – KERN-CODE unverändert."""
    if data == "block_start":
        frei = [k for k in ACCOUNTS if _account_frei(k)]
        if len(frei) < 2:
            senden("🔗 <b>3h-Modus</b> braucht <b>2 freie Accounts</b> "
                   "(ohne aktive Buchung/Schiebe/Sniper).")
            zeige_account_auswahl()
            return
        _block_reset()
        btns = [[{"text": account_status_label(k), "callback_data": f"block_pa_{k}"}]
                for k in frei]
        btns.append([{"text": "❌ Abbrechen", "callback_data": "block_cancel"}])
        senden("🔗 <b>3h-Modus</b> – durchgehender 3-Stunden-Block (2× 90 Min)\n\n"
               "Wähle den <b>1. Account</b> = 🏃 <b>Schieber</b>\n"
               "<i>(schiebt bis zum Wunschanfang, z.B. 10:30 → 10:30–12:00):</i>",
               buttons=btns)
        return

    if data == "block_cancel":
        _block_reset()
        senden("↩️ 3h-Modus abgebrochen.")
        zeige_account_auswahl()
        return

    if data.startswith("block_pa_"):
        k = data[len("block_pa_"):]
        if k not in acc or not _account_frei(k):
            senden("❌ Account nicht (mehr) frei. Bitte 3h-Modus neu starten.")
            _block_reset()
            zeige_account_auswahl()
            return
        with _block_lock:
            _block["acc_a"] = k
        rest = [x for x in ACCOUNTS if x != k and _account_frei(x)]
        if not rest:
            senden("❌ Kein zweiter freier Account verfügbar.")
            _block_reset()
            zeige_account_auswahl()
            return
        btns = [[{"text": account_status_label(x), "callback_data": f"block_pb_{x}"}]
                for x in rest]
        btns.append([{"text": "❌ Abbrechen", "callback_data": "block_cancel"}])
        senden(f"🔗 3h | 🏃 Schieber: <b>{k}</b>\n\n"
               f"Wähle den <b>2. Account</b> = ⚡ <b>Anschluss-Blitzer</b>:",
               buttons=btns)
        return

    if data.startswith("block_pb_"):
        k = data[len("block_pb_"):]
        with _block_lock:
            a = _block["acc_a"]
        if not a:
            senden("❌ 3h-Flow unterbrochen – bitte neu starten.")
            _block_reset()
            zeige_account_auswahl()
            return
        if k == a or k not in acc or not _account_frei(k):
            senden("❌ Bitte einen ANDEREN freien Account wählen.")
            return
        with _block_lock:
            _block["acc_b"] = k
        senden(f"🔗 3h | 🏃 {a} | ⚡ {k}\n\n"
               f"📅 Für welches <b>Datum</b>?",
               buttons=erstelle_datum_buttons("block_datum"))
        return

    if data.startswith("block_datum_"):
        datum = data[len("block_datum_"):]
        with _block_lock:
            _block["datum"] = datum
            a, b = _block["acc_a"], _block["acc_b"]
        if not (a and b):
            senden("❌ 3h-Flow unterbrochen – bitte neu starten.")
            _block_reset()
            zeige_account_auswahl()
            return
        senden(f"🔗 3h | 🏃 {a} | ⚡ {b} | 📅 {datum}\n\n"
               f"🏟️ <b>Welcher Court?</b>\n"
               f"<i>Fester Court = durchgehend ein Platz für alle 3 Stunden.</i>",
               buttons=court_buttons("block_court"))
        return

    if data.startswith("block_court_"):
        court_val = data[len("block_court_"):]
        try:
            court_int = int(court_val)
        except ValueError:
            court_int = 0
        with _block_lock:
            _block["court"] = court_int
            a, b, datum = _block["acc_a"], _block["acc_b"], _block["datum"]
        if not (a and b and datum):
            senden("❌ 3h-Flow unterbrochen – bitte neu starten.")
            _block_reset()
            zeige_account_auswahl()
            return
        court_label = {0: "Egal (Court 2 bevorzugt)", 1: "Court 1",
                       2: "Court 2"}.get(court_int, "?")
        senden(f"🔗 3h | 🏟️ {court_label} | 📅 {datum} | je 90 Min\n\n"
               f"🎯 <b>Wunschanfang</b> des Blocks?\n"
               f"<i>Acc1 schiebt bis hierhin (z.B. 10:30 → 10:30–12:00), "
               f"Acc2 blitzt den Anschluss (12:00–13:30).</i>",
               buttons=zielzeit_buttons("block_ziel", BLOCK_DAUER_MIN * 2))
        return

    if data.startswith("block_ziel_"):
        ziel = data[len("block_ziel_"):]
        with _block_lock:
            _block["ziel"] = ziel
            a, b      = _block["acc_a"], _block["acc_b"]
            datum     = _block["datum"]
            court     = _block["court"]
            if a and b and datum and court is not None:
                _block["flow"] = "startzeit"
        if not (a and b and datum and court is not None):
            senden("❌ 3h-Flow unterbrochen – bitte neu starten.")
            _block_reset()
            zeige_account_auswahl()
            return
        ziel_dt       = datetime.strptime(ziel, "%H:%M")
        anschluss_von = (ziel_dt + timedelta(minutes=BLOCK_DAUER_MIN)).strftime("%H:%M")
        block_bis     = (ziel_dt + timedelta(minutes=BLOCK_DAUER_MIN * 2)).strftime("%H:%M")
        senden(f"🔗 <b>3h-Modus</b>\n"
               f"🏃 {a} | ⚡ {b}\n"
               f"📅 {datum} | 🎯 Block: {ziel}–{block_bis} Uhr (3 Std.)\n\n"
               f"⏰ <b>Ab wann startet der Schieber ({a})?</b>\n"
               f"Buchbar-ab-Zeit tippen (30-Min-Raster, z.B. <b>{ziel}</b> oder früher):\n\n"
               f"<i>Acc1 blitzt diesen Start-Slot und schiebt bis {ziel}.\n"
               f"Acc2 blitzt {anschluss_von}–{block_bis} bei Freischaltung um {anschluss_von}.</i>")
        return

    senden("❓ Unbekannte 3h-Aktion.")
    _block_reset()
    zeige_account_auswahl()


def handle_block_text(text: str):
    """Verarbeitet die getippte Buchbar-ab-Zeit (Start des Schiebers) und
    startet beide Accounts (Schieber + Anschluss-Blitzer)."""
    m = re.match(r"^(\d{1,2}):(\d{2})$", text.strip())
    if not m:
        senden("❌ Ungültiges Format. Bitte als <b>HH:MM</b> eingeben, z.B. <b>17:30</b>")
        return
    stunde, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= stunde <= 21 and minute in (0, 30)):
        senden("❌ Zeit muss auf 30-Min-Raster liegen (z.B. 17:00 oder 17:30)")
        return
    buchbar_ab = f"{stunde:02d}:{minute:02d}"
    with _block_lock:
        a, b   = _block["acc_a"], _block["acc_b"]
        datum  = _block["datum"]
        ziel   = _block["ziel"]
        court  = _block["court"]
        _block["flow"] = None
    if not (a and b and datum and ziel and court is not None):
        senden("❌ 3h-Konfiguration unvollständig – bitte neu starten.")
        _block_reset()
        zeige_account_auswahl()
        return
    # Man schiebt vorwärts → Start darf nicht NACH dem Wunschanfang liegen.
    if datetime.strptime(buchbar_ab, "%H:%M") > datetime.strptime(ziel, "%H:%M"):
        senden(f"❌ Startzeit ({buchbar_ab}) liegt nach dem Wunschanfang ({ziel}).\n"
               f"Bitte eine Zeit ≤ {ziel} tippen.")
        with _block_lock:
            _block["flow"] = "startzeit"      # Eingabe erneut erwarten
        return
    if not _account_frei(a) or not _account_frei(b):
        senden("⚠️ Einer der beiden Accounts ist nicht mehr frei – 3h-Modus abgebrochen.")
        _block_reset()
        zeige_account_auswahl()
        return
    _starte_block(a, b, datum, ziel, court, buchbar_ab)
    _block_reset()


def _starte_block(a: str, b: str, datum: str, ziel: str, court: int, buchbar_ab: str):
    """Konfiguriert beide Accounts und startet sie über den UNVERÄNDERTEN
    schiebe_loop:
      • Acc1 (Schieber)  = Direkte Taktik, Start ab 'buchbar_ab', Ziel 'ziel'
                           → landet auf ziel … ziel+90 (z.B. 10:30–12:00).
      • Acc2 (Anschluss) = Direkte Taktik, Start = Ziel = ziel+90
                           → blitzt ziel+90 … ziel+180 (z.B. 12:00–13:30) bei
                             Freischaltung; Ziel == Start ⇒ Phase 3 endet sofort
                             (kein Schieben, reiner Blitz / "bekannte Startzeit").
    Zusammen = durchgehender 3-Stunden-Block."""
    dauer         = BLOCK_DAUER_MIN
    ziel_dt       = datetime.strptime(ziel, "%H:%M")
    anschluss_von = (ziel_dt + timedelta(minutes=dauer)).strftime("%H:%M")        # Acc2 from
    anschluss_bis = (ziel_dt + timedelta(minutes=2 * dauer)).strftime("%H:%M")    # Acc2 to
    fester_court  = court if court in (1, 2) else None

    # Account 1 = Schieber (Direkte Taktik bis 'ziel')
    az_set_multi(a,
        schiebe_modus="direkt",
        schiebe_datum=datum,
        schiebe_ziel=ziel,
        schiebe_dauer=dauer,
        schiebe_court=court,
        schiebe_buchbar_ab=buchbar_ab,
        schiebe_offset_min=None,
        schiebe_offset_max=None,
        duo_court=fester_court,        # fester Court → kein Alternieren beim Schieben
        schiebe_aktiv=True,
        flow=None,
    )
    # Account 2 = Anschluss-Blitzer (Direkte Taktik, Start == Ziel == Anschluss-Slot)
    az_set_multi(b,
        schiebe_modus="direkt",
        schiebe_datum=datum,
        schiebe_ziel=anschluss_von,    # Ziel == Start → Phase 3 endet sofort (kein Schieben)
        schiebe_dauer=dauer,
        schiebe_court=court,
        schiebe_buchbar_ab=anschluss_von,  # Blitz exakt bei Freischaltung des Anschluss-Slots
        schiebe_offset_min=None,
        schiebe_offset_max=None,
        duo_court=fester_court,
        schiebe_aktiv=True,
        flow=None,
    )

    datum_obj   = datetime.strptime(datum, "%d.%m.%Y")
    fenster_tag = (datum_obj - timedelta(days=7)).date()
    unlock_a    = datetime.combine(fenster_tag, datetime.strptime(buchbar_ab, "%H:%M").time())
    unlock_b    = datetime.combine(fenster_tag, datetime.strptime(anschluss_von, "%H:%M").time())
    court_label = {0: "Egal (Court 2 bevorzugt)", 1: "Court 1",
                   2: "Court 2"}.get(court, "?")

    jetzt = jetzt_lokal()
    if unlock_a <= jetzt:
        frei_txt = "🚀 Start-Slot bereits freigeschaltet – Schieber blitzt sofort!"
    else:
        rest = unlock_a - jetzt
        h  = rest.seconds // 3600
        mi = (rest.seconds % 3600) // 60
        rest_str = (f"{rest.days}T {h}h {mi}min" if rest.days > 0
                    else f"{h}h {mi}min" if h > 0 else f"{mi}min")
        frei_txt = f"⏳ Schieber-Freischaltung in {rest_str}"

    senden(
        f"🔗 <b>3h-Modus gestartet!</b>\n"
        f"📅 {_datum_mit_tag(datum)} | 🏟️ {court_label} | je 90 Min\n"
        f"🎯 <b>Block: {ziel}–{anschluss_bis} Uhr</b> (3 Std.)\n\n"
        f"1️⃣ 🏃 <b>{a}</b> – Schieber (Direkte Taktik)\n"
        f"   ⏰ Start ab {buchbar_ab} → schiebt bis 🎯 {ziel}  (Slot {ziel}–{anschluss_von})\n"
        f"   🔓 {unlock_a.strftime('%d.%m. %H:%M')} Uhr\n\n"
        f"2️⃣ ⚡ <b>{b}</b> – Anschluss-Blitz\n"
        f"   💥 blitzt {anschluss_von}–{anschluss_bis} bei Freischaltung\n"
        f"   🔓 {unlock_b.strftime('%d.%m. %H:%M')} Uhr\n\n"
        f"{frei_txt}\n"
        f"<i>Acc2 blitzt eigenständig zur Anschluss-Freischaltung – läuft auch, "
        f"falls Acc1 den Zielslot knapp verpasst.</i>")

    for k in (a, b):
        t = threading.Thread(target=schiebe_loop, args=(k,), daemon=True)
        t.start()
        az_set(k, "schiebe_thread", t)

    zeige_account_auswahl()


# ══════════════════════════════════════════════
# TELEGRAM CALLBACKS
# ══════════════════════════════════════════════

def handle_callback(cb: dict):
    cid  = cb["id"]
    data = cb.get("data", "")
    beantworte_callback(cid)
    log.info(f"Callback: {data}")

    # Jeder Klick auf einen Nicht-Duo-Button verlässt einen offenen Duo-Eingabeschritt
    if not data.startswith("duo_") and _duo_awaiting_text():
        _duo_reset()
    # Dasselbe für den 3h-Modus-Eingabeschritt
    if not data.startswith("block_") and _block_awaiting_text():
        _block_reset()

    if data in ("zurueck_accounts", "refresh_accounts"):
        zeige_account_auswahl()
        return

    if data.startswith("acc_"):
        k = data[4:]
        if k not in acc:
            senden("❌ Unbekannter Account.")
            return
        set_flow_account(k)
        try:
            sync_buchung_vom_server(k)
        except Exception as e:
            log.warning(f"[{k}] Sync: {e}")
        zeige_account_menue(k)
        return

    # ── Duo-Modus (eigener Flow über 2 Accounts) – früh abfangen ──────────────
    if data.startswith("duo_"):
        handle_duo_callback(data)
        return

    # ── 3h-Modus (Block, eigener Flow über 2 Accounts) – früh abfangen ────────
    if data.startswith("block_"):
        handle_block_callback(data)
        return

    k = get_flow_account()
    for ak in ACCOUNTS:
        if data.endswith(f"_{ak}"):
            k    = ak
            data = data[:-(len(ak) + 1)]
            break

    if not k:
        senden("❓ Bitte zuerst einen Account wählen.")
        zeige_account_auswahl()
        return

    # ── Klassische Buchung ────────────────────────────────────────────────────
    if data == "menu_slots":
        az_set(k, "flow", "slots_anfrage")
        senden(f"📅 <b>[{k}] Klassisch buchen</b>\nWelches Datum?",
               buttons=erstelle_datum_buttons("slots_datum"))

    # ── Schiebe-Taktik ────────────────────────────────────────────────────────
    elif data == "menu_schiebe":
        if az_get(k, "schiebe_aktiv") or az_get(k, "sniper_aktiv"):
            senden(f"⚠️ [{k}] Prozess läuft bereits! Erst stoppen.")
            zeige_account_menue(k)
            return
        if az_get(k, "aktive_buchung"):
            senden(f"⚠️ [{k}] Aktive Buchung vorhanden.\nSchiebe nur ohne aktive Buchung.")
            zeige_account_menue(k)
            return
        # Normaler Schiebe-Modus → eventuelles Duo-Offset-Band zurücksetzen
        az_set_multi(k, schiebe_offset_min=None, schiebe_offset_max=None, duo_court=None)
        zeige_schiebe_modus_auswahl(k)

    # ── Sniper-Modus ──────────────────────────────────────────────────────────
    elif data == "menu_sniper":
        if az_get(k, "schiebe_aktiv") or az_get(k, "sniper_aktiv"):
            senden(f"⚠️ [{k}] Prozess läuft bereits! Erst stoppen.")
            zeige_account_menue(k)
            return
        if az_get(k, "aktive_buchung"):
            senden(f"⚠️ [{k}] Aktive Buchung vorhanden.\nSniper nur ohne aktive Buchung.")
            zeige_account_menue(k)
            return
        # Sniper nutzt nach Treffer ebenfalls _schiebe_phase3 → Duo-Offset zurücksetzen
        az_set_multi(k, schiebe_offset_min=None, schiebe_offset_max=None, duo_court=None)
        az_set(k, "flow", "sniper_datum")
        senden(
            f"🎯 <b>[{k}] Sniper-Modus</b>\n\n"
            f"Jemand schiebt manuell und du willst dazwischenfunken.\n\n"
            f"<b>Beispiel:</b>\n"
            f"Fremder hat Court 2 | 08:00–09:30\n"
            f"→ Sniper zielt auf Court 2 | 09:00–10:30\n"
            f"→ Hämmert sekündlich bis der Fremde storniert\n"
            f"→ Danach: Schiebe bis Zielzeit\n\n"
            f"📅 <b>Für welches Datum?</b>",
            buttons=erstelle_datum_buttons("sniper_datum", nur_im_fenster=True))

    elif data == "menu_status":
        snap    = az_snap(k, "aktive_buchung", "schiebe_aktiv", "schiebe_ziel",
                          "schiebe_datum", "schiebe_dauer", "schiebe_modus",
                          "schiebe_buchbar_ab", "person_id",
                          "sniper_aktiv", "sniper_datum", "sniper_ziel",
                          "sniper_fremder_bis", "sniper_court")
        aktiv   = snap["aktive_buchung"]
        schiebe = snap["schiebe_aktiv"]
        sniper  = snap["sniper_aktiv"]
        modus   = snap["schiebe_modus"] or ""
        modus_l = {"frueh": "Früh", "spaet": "Spät", "direkt": "Direkt", "sniper": "Sniper-Fortsetzung"}.get(modus, "?")
        pid     = snap["person_id"] or "⚠️ NICHT GEFUNDEN"

        if aktiv:
            extra = ""
            if schiebe:
                extra = (f"🔄 Schiebe ({modus_l}) → Ziel {snap['schiebe_ziel']} | "
                         f"{snap['schiebe_dauer']} Min"
                         + (f"\n⏰ Buchbar ab: {snap['schiebe_buchbar_ab']}"
                            if modus == "direkt" else ""))
            wetter_str = hole_wetter(aktiv["datum_de"], aktiv["fromTime"])
            senden(f"📊 <b>[{k}] Aktive Buchung:</b>\n"
                   f"📅 {_datum_mit_tag(aktiv['datum_de'])}\n"
                   f"🕐 {aktiv['fromTime']}–{aktiv['toTime']} Uhr\n"
                   f"🏟️ Court {aktiv['court']}\n"
                   f"🔖 ID: {aktiv.get('booking_id','?')}\n"
                   f"👤 Person: {pid}\n\n"
                   + (extra if extra else "ℹ️ Keine Schiebe aktiv.")
                   + wetter_str)
        elif sniper:
            senden(f"📊 <b>[{k}] Sniper aktiv:</b>\n"
                   f"📅 {_datum_mit_tag(snap['sniper_datum'] or '?')}\n"
                   f"🏟️ Court {snap['sniper_court']} | Fremdes Ende: {snap['sniper_fremder_bis']}\n"
                   f"🎯 Ziel nach Treffer: {snap['sniper_ziel']} Uhr\n"
                   f"👤 Person: {pid}")
        else:
            senden(f"📊 <b>[{k}] Keine Buchung.</b>\n"
                   f"👤 Person: {pid}\n"
                   + (f"🔄 Schiebe ({modus_l}) läuft..." if schiebe else "Bot wartet."))
        zeige_account_menue(k)

    elif data == "menu_stopp":
        stopped = []
        if az_get(k, "schiebe_aktiv"):
            az_set(k, "schiebe_aktiv", False)
            stopped.append("Schiebe")
        if az_get(k, "sniper_aktiv"):
            az_set(k, "sniper_aktiv", False)
            stopped.append("Sniper")
        if stopped:
            senden(f"⏹️ [{k}] {' & '.join(stopped)} gestoppt.")
        else:
            senden("ℹ️ Kein aktiver Prozess.")
        zeige_account_menue(k)

    elif data == "menu_storno":
        aktiv = az_get(k, "aktive_buchung")
        if not aktiv:
            senden(f"🗑️ [{k}] Keine Buchung vorhanden.")
            zeige_account_menue(k)
            return
        bid = aktiv.get("booking_id")
        senden(f"❓ <b>[{k}] Buchung wirklich stornieren?</b>\n\n"
               f"📅 {aktiv['datum_de']}\n"
               f"🕐 {aktiv['fromTime']}–{aktiv['toTime']} Uhr\n"
               f"🏟️ Court {aktiv['court']}\n"
               f"🔖 ID: {bid or '?'}\n\n"
               f"⚠️ Nicht rückgängig machbar!",
               buttons=[[
                   {"text": "✅ Ja, stornieren!",
                    "callback_data": f"storno_bestaetigt_{k}"},
                   {"text": "❌ Abbrechen", "callback_data": "abbrechen"},
               ]])

    elif data == "storno_bestaetigt":
        aktiv = az_get(k, "aktive_buchung")
        if not aktiv:
            senden(f"🗑️ [{k}] Keine Buchung mehr.")
            zeige_account_menue(k)
            return
        bid       = aktiv.get("booking_id")
        datum_api = aktiv.get("datum_api")
        if not bid:
            senden(f"❌ Keine ID – manuell: {BASE_URL}/padel")
            zeige_account_menue(k)
            return
        if az_get(k, "schiebe_aktiv"):
            az_set(k, "schiebe_aktiv", False)
            senden("⏹️ Schiebe ebenfalls gestoppt.")
        if az_get(k, "sniper_aktiv"):
            az_set(k, "sniper_aktiv", False)
            senden("⏹️ Sniper ebenfalls gestoppt.")
        if not stelle_session_sicher(k):
            return
        senden("⏳ Storniere...")
        ok = storniere_buchung(k, bid, datum_api)
        if ok:
            senden(f"✅ <b>[{k}] Storniert!</b>\n"
                   f"📅 {aktiv['datum_de']}\n"
                   f"🕐 {aktiv['fromTime']}–{aktiv['toTime']} | Court {aktiv['court']}")
        else:
            senden(f"❌ Stornierung fehlgeschlagen!\nManuell: {BASE_URL}/padel")
        zeige_account_auswahl()

    # ── Slot-Buchung Callbacks ────────────────────────────────────────────────
    elif data.startswith("slots_datum_"):
        datum = data.replace("slots_datum_", "")
        az_set_multi(k, flow_datum=datum, flow="slots_dauer")
        senden(f"📅 [{k}] {datum}\nWie lange möchtest du spielen?",
               buttons=dauer_buttons("slots_dauer"))

    elif data.startswith("slots_dauer_"):
        dauer = int(data.replace("slots_dauer_", ""))
        datum = az_get(k, "flow_datum")
        if not datum:
            senden("❌ Fehler – nochmal starten.")
            zeige_account_menue(k)
            return
        az_set_multi(k, flow_dauer=dauer, flow=None)
        if not stelle_session_sicher(k):
            zeige_account_menue(k)
            return
        slots = berechne_freie_slots(k, datum, dauer)
        if not slots:
            senden(f"😔 [{k}] Keine freien {dauer}-Min-Slots am {datum}.")
            zeige_account_menue(k)
            return
        gesamt       = len(slots)
        slot_buttons = []
        for s in slots[:10]:
            label = f"🏟️ Court {s['court']} | {s['fromTime']}–{s['toTime']}"
            key   = (f"buch_{s['datum_api'].replace('/', '-')}_"
                     f"{s['court']}_{s['fromTime']}_{dauer}")
            slot_buttons.append([{"text": label, "callback_data": key}])
        slot_buttons.append([{"text": "❌ Abbrechen", "callback_data": "abbrechen"}])
        extra = f"\n<i>(+{gesamt-10} weitere)</i>" if gesamt > 10 else ""
        senden(f"✅ [{k}] Freie {dauer}-Min-Slots am {datum}:{extra}\n"
               f"<i>Court 2 zuerst angezeigt</i>",
               buttons=slot_buttons)

    elif data.startswith("buch_"):
        parts = data.split("_")
        try:
            datum_api = parts[1].replace("-", "/")
            court     = int(parts[2])
            from_t    = parts[3]
            dauer     = int(parts[4])
            datum_obj = datetime.strptime(datum_api, "%m/%d/%Y")
            datum_de  = datum_obj.strftime("%d.%m.%Y")
            to_t      = (datetime.strptime(from_t, "%H:%M") +
                         timedelta(minutes=dauer)).strftime("%H:%M")
        except Exception as e:
            log.error(f"buch_ parse: {e} | {data}")
            senden("❌ Fehler – nochmal versuchen.")
            return
        senden(f"❓ <b>[{k}] Buchung bestätigen?</b>\n"
               f"📅 {datum_de}\n"
               f"🕐 {from_t}–{to_t} Uhr ({dauer} Min)\n"
               f"🏟️ Court {court}",
               buttons=[[
                   {"text": "✅ Ja, buchen!", "callback_data": f"confirm_{data}"},
                   {"text": "❌ Nein",        "callback_data": "abbrechen"},
               ]])

    elif data.startswith("confirm_buch_"):
        original = data.replace("confirm_", "")
        parts    = original.split("_")
        try:
            datum_api = parts[1].replace("-", "/")
            court     = int(parts[2])
            from_t    = parts[3]
            dauer     = int(parts[4])
            datum_obj = datetime.strptime(datum_api, "%m/%d/%Y")
            datum_de  = datum_obj.strftime("%d.%m.%Y")
            to_t      = (datetime.strptime(from_t, "%H:%M") +
                         timedelta(minutes=dauer)).strftime("%H:%M")
        except Exception as e:
            log.error(f"confirm_ parse: {e}")
            senden("❌ Fehler – nochmal.")
            return
        slot = _baue_slot_dict(court, from_t, to_t, datum_de, datum_api, dauer)
        if not stelle_session_sicher(k):
            senden(f"❌ [{k}] Session-Fehler.")
            zeige_account_menue(k)
            return
        senden("⏳ Buche...")
        ok = buche_slot(k, slot)
        if ok:
            wetter_str = hole_wetter(datum_de, from_t)
            senden(f"✅ <b>[{k}] Gebucht!</b>\n"
                   f"📅 {_datum_mit_tag(datum_de)}\n"
                   f"🕐 {from_t}–{to_t} Uhr ({dauer} Min)\n"
                   f"🏟️ Court {court}\n\nViel Spaß! 🎾"
                   + wetter_str)
        else:
            senden(f"❌ [{k}] Buchung fehlgeschlagen.",
                   buttons=[[
                       {"text": "🔄 Nochmal",   "callback_data": original},
                       {"text": "↩️ Abbrechen", "callback_data": "abbrechen"},
                   ]])
        zeige_account_auswahl()

    # ── Schiebe-Setup Callbacks ───────────────────────────────────────────────
    elif data.startswith("schiebe_modus_"):
        modus = data.replace("schiebe_modus_", "")
        az_set_multi(k, schiebe_modus=modus, flow="schiebe_setup_datum",
                     schiebe_buchbar_ab=None)
        modus_name  = {"frueh": "Früh-Methode", "spaet": "Spät-Taktik",
                       "direkt": "Direkte Taktik"}.get(modus, modus)
        nur_fenster = (modus == "spaet")
        senden(f"🔄 [{k}] <b>{modus_name}</b>\nFür welches Datum?",
               buttons=erstelle_datum_buttons("schiebe_datum", nur_im_fenster=nur_fenster))

    elif data.startswith("schiebe_datum_"):
        datum = data.replace("schiebe_datum_", "")
        az_set_multi(k, schiebe_datum=datum, flow="schiebe_setup_dauer")
        senden(f"📅 [{k}] {datum}\nWie lange möchtest du spielen?",
               buttons=dauer_buttons("schiebe_dauer"))

    elif data.startswith("schiebe_dauer_"):
        dauer = int(data.replace("schiebe_dauer_", ""))
        az_set_multi(k, schiebe_dauer=dauer, flow="schiebe_setup_ziel")
        senden(f"🕒 [{k}] Welche <b>Wunschzeit</b>? ({dauer} Min)\n"
               f"<i>Bis hierhin soll geschoben werden</i>",
               buttons=zielzeit_buttons("schiebe_ziel", dauer))

    elif data.startswith("schiebe_court_"):
        court_val = data.replace("schiebe_court_", "")
        try:
            court_int = int(court_val)
        except ValueError:
            court_int = 0
        az_set_multi(k, schiebe_court=court_int, flow="direkte_startzeit")
        datum = az_get(k, "schiebe_datum")
        dauer = az_get(k, "schiebe_dauer")
        ziel  = az_get(k, "schiebe_ziel")
        court_label = {0: "Court 2 bevorzugt", 1: "Court 1", 2: "Court 2"}.get(court_int, "?")
        senden(f"🎯 <b>[{k}] Direkte Taktik</b>\n"
               f"📅 {datum} | {dauer} Min | Ziel: {ziel} Uhr | 🏟️ {court_label}\n\n"
               f"⏰ <b>Ab wann ist der Slot buchbar?</b>\n"
               f"Bitte Uhrzeit tippen (30-Min-Raster, z.B. <b>17:30</b>):\n\n"
               f"<i>Bot wartet bis heute {court_label} frei wird, bucht dann und schiebt.</i>")

    elif data.startswith("schiebe_ziel_"):
        ziel  = data.replace("schiebe_ziel_", "")
        modus = az_get(k, "schiebe_modus") or "frueh"
        az_set(k, "schiebe_ziel", ziel)

        if modus == "direkt":
            az_set(k, "flow", "direkte_court")
            datum = az_get(k, "schiebe_datum")
            dauer = az_get(k, "schiebe_dauer")
            senden(f"🎯 <b>[{k}] Direkte Taktik</b>\n"
                   f"📅 {datum} | {dauer} Min | Ziel: {ziel} Uhr\n\n"
                   f"🏟️ <b>Welchen Court möchtest du?</b>",
                   buttons=court_buttons("schiebe_court"))
        else:
            az_set_multi(k, schiebe_aktiv=True, flow=None)
            datum     = az_get(k, "schiebe_datum")
            dauer     = az_get(k, "schiebe_dauer")
            datum_obj = datetime.strptime(datum, "%d.%m.%Y")
            tage_bis  = (datum_obj.date() - jetzt_lokal().date()).days
            modus_name = "🌅 Früh-Methode" if modus == "frueh" else "🕐 Spät-Taktik"
            senden(f"🔄 <b>[{k}] {modus_name} konfiguriert!</b>\n"
                   f"📅 {datum}\n"
                   f"🎯 Ziel: {ziel} Uhr ({dauer} Min)\n"
                   f"📆 Datum in {tage_bis} Tagen\n\n"
                   + (f"⏳ Warte noch {tage_bis-7} Tag(e) bis 7-Tage-Fenster..."
                      if tage_bis > 7 else "🚀 Starte jetzt!"))
            t = threading.Thread(target=schiebe_loop, args=(k,), daemon=True)
            t.start()
            az_set(k, "schiebe_thread", t)
            zeige_account_auswahl()

    # ── Sniper-Setup Callbacks ────────────────────────────────────────────────
    elif data.startswith("sniper_datum_"):
        datum = data.replace("sniper_datum_", "")
        az_set_multi(k, sniper_datum=datum, flow="sniper_dauer")
        senden(f"📅 [{k}] Sniper | {datum}\nWie lang soll deine Buchung sein?",
               buttons=dauer_buttons("sniper_dauer"))

    elif data.startswith("sniper_dauer_"):
        dauer = int(data.replace("sniper_dauer_", ""))
        az_set_multi(k, sniper_dauer=dauer, flow="sniper_court")
        senden(f"🏟️ [{k}] Auf welchem <b>Court</b> spielt die fremde Person?",
               buttons=[[
                   {"text": "🏟️ Court 1", "callback_data": f"sniper_court_1"},
                   {"text": "🏟️ Court 2", "callback_data": f"sniper_court_2"},
               ]])

    elif data.startswith("sniper_court_"):
        court_val = data.replace("sniper_court_", "")
        try:
            court_int = int(court_val)
        except ValueError:
            court_int = 2
        az_set_multi(k, sniper_court=court_int, flow="sniper_fremder_end")
        dauer = az_get(k, "sniper_dauer")
        senden(
            f"⏰ [{k}] Court {court_int} | {dauer} Min\n\n"
            f"🕐 <b>Wann endet die fremde Buchung?</b>\n"
            f"<i>Beispiel: Fremder hat 08:00–09:30 → wähle 09:30</i>\n"
            f"Bot zielt dann auf: <b>{dauer} Min ab 30 Min vor dieser Zeit</b>",
            buttons=sniper_endzeit_buttons("sniper_end"))

    elif data.startswith("sniper_end_"):
        fremder_bis = data.replace("sniper_end_", "")
        az_set_multi(k, sniper_fremder_bis=fremder_bis, flow="sniper_ziel")
        dauer  = az_get(k, "sniper_dauer")
        court  = az_get(k, "sniper_court")
        datum  = az_get(k, "sniper_datum")
        # Berechne Ziel-Slot für Anzeige
        fremder_bis_dt = datetime.strptime(fremder_bis, "%H:%M")
        target_von_dt  = fremder_bis_dt - timedelta(minutes=30)
        target_bis_dt  = target_von_dt + timedelta(minutes=dauer)
        senden(
            f"🎯 [{k}] Sniper-Ziel berechnet:\n"
            f"📅 {datum} | Court {court}\n"
            f"💥 Hämmere auf: <b>{target_von_dt.strftime('%H:%M')}–{target_bis_dt.strftime('%H:%M')}</b>\n\n"
            f"🔄 <b>Bis wohin schieben nach Treffer?</b>",
            buttons=zielzeit_buttons("sniper_ziel", dauer))

    elif data.startswith("sniper_ziel_"):
        ziel   = data.replace("sniper_ziel_", "")
        datum  = az_get(k, "sniper_datum")
        dauer  = az_get(k, "sniper_dauer")
        court  = az_get(k, "sniper_court")
        fremder_bis = az_get(k, "sniper_fremder_bis")

        fremder_bis_dt = datetime.strptime(fremder_bis, "%H:%M")
        target_von_dt  = fremder_bis_dt - timedelta(minutes=30)
        target_bis_dt  = target_von_dt + timedelta(minutes=dauer)

        az_set_multi(k,
            sniper_ziel=ziel,
            sniper_aktiv=True,
            flow=None,
        )

        senden(
            f"🎯 <b>[{k}] Sniper konfiguriert!</b>\n"
            f"📅 {_datum_mit_tag(datum)}\n"
            f"🏟️ Court {court} | Fremdes Ende: {fremder_bis} Uhr\n"
            f"💥 Sniper-Ziel: <b>{target_von_dt.strftime('%H:%M')}–{target_bis_dt.strftime('%H:%M')}</b>\n"
            f"🔄 Nach Treffer → Schiebe bis {ziel} Uhr\n\n"
            f"🚀 Sniper startet jetzt!")

        t = threading.Thread(target=sniper_loop, args=(k,), daemon=True)
        t.start()
        az_set(k, "sniper_thread", t)
        zeige_account_auswahl()

    # ── Abbrechen ─────────────────────────────────────────────────────────────
    elif data == "abbrechen":
        if k:
            az_set_multi(k, flow=None, flow_datum=None, flow_dauer=None)
        senden("↩️ Abgebrochen.")
        zeige_account_auswahl()

    else:
        log.warning(f"Unbekannter Callback: {data}")
        zeige_account_auswahl()

# ══════════════════════════════════════════════
# TELEGRAM POLLING
# ══════════════════════════════════════════════

def telegram_loop():
    log.info("📡 Telegram-Listener gestartet")
    while True:
        try:
            for update in hole_updates():
                if "message" in update:
                    msg     = update["message"]
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    if chat_id != str(TELEGRAM_CHAT_ID):
                        continue
                    text   = msg.get("text", "").strip()
                    if _duo_awaiting_text():
                        handle_duo_text(text)
                    elif _block_awaiting_text():
                        handle_block_text(text)
                    else:
                        k_flow = get_flow_account()
                        if k_flow and az_get(k_flow, "flow") in ("direkte_startzeit",):
                            handle_text(k_flow, text)
                        else:
                            zeige_account_auswahl()

                elif "callback_query" in update:
                    cb      = update["callback_query"]
                    chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                    if chat_id == str(TELEGRAM_CHAT_ID):
                        handle_callback(cb)
        except Exception as e:
            log.error(f"Telegram-Loop: {e}")
            # PERF: kein festes time.sleep(1) mehr im Normalfall – getUpdates
            # pollt bereits serverseitig bis zu 5s (kein Busy-Loop). Nur im
            # Fehlerfall kurz pausieren, um Hot-Looping zu vermeiden.
            time.sleep(1)

# ══════════════════════════════════════════════
# START
# ══════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("🎾 Padel Bot v10.0.0 – Fixes: Verifikation | Schiebe-Speed | Sniper")
    log.info("   FIX 1: buche_slot() kein False-Positiv mehr (kein verifiziert=True Fallback)")
    log.info("   FIX 2: Rebook nach Storno: 30× mit 0.1s | Storno-Retry: aktiv()-Check")
    log.info("   NEU 3: Sniper-Modus – sekündlicher Dauerhammer + Schiebe nach Treffer")
    log.info("   Schiebe-Logik: Storno/Neubuchung passiert HEUTE (nicht am Buchungstag!)")
    for k in ACCOUNTS:
        log.info(f"   [{k}] {ACCOUNTS[k]['email']}")
    log.info(f"   Court-Priorität : 2 → 1 (automatisch)")
    log.info(f"   Früh exklusiv   : {FRUEH_EXKLUSIV_VERSUCHE} × {AGGRESSIVE_INTERVAL}s")
    log.info(f"   Schiebe         : {SCHIEBE_MINUTEN_VOR_MIN}–{SCHIEBE_MINUTEN_VOR_MAX} Min vor Slot-Ende (random)")
    log.info("=" * 60)

    for k in ACCOUNTS:
        thread = acc[k].get("schiebe_thread")
        if az_get(k, "schiebe_aktiv") and (not thread or not thread.is_alive()):
            log.warning(f"[{k}] Startup: schiebe_aktiv korrigiert.")
            az_set(k, "schiebe_aktiv", False)

    fehler        = []
    pid_warnungen = []
    for k in ACCOUNTS:
        if not einloggen(k):
            fehler.append(k)
            log.error(f"❌ Login [{k}] fehlgeschlagen!")
        else:
            pid = az_get(k, "person_id")
            if pid:
                log.info(f"   [{k}] PERSON_ID: {pid} ✅")
            else:
                log.warning(f"   [{k}] PERSON_ID: ⚠️ NICHT GEFUNDEN")
                pid_warnungen.append(k)

    if len(fehler) == len(ACCOUNTS):
        log.error("❌ Alle Accounts fehlgeschlagen – Bot beendet.")
        exit(1)
    elif fehler:
        senden(f"⚠️ Login für {', '.join(fehler)} fehlgeschlagen!")

    anzahl      = len(ACCOUNTS)
    modus_label = "Dual-Account" if anzahl > 1 else "Einzel-Account"
    startup_msg = (
        f"🎾 <b>Padel Bot v10.0.0 gestartet!</b>\n\n"
        f"{modus_label}  |  3 Schiebe-Modi  |  🎯 Sniper-Modus\n\n"
        f"<b>NEU v10:</b>\n"
        f"🔒 Buchung nur bestätigt wenn Server-Sync OK (kein False-Positiv)\n"
        f"⚡ Rebook nach Storno: 30× mit 0.1s (statt langsamer Backoff)\n"
        f"🛑 Stopp-Button bricht Storno-Retry sofort ab\n"
        f"🎯 Sniper: hämmert sekündlich → Treffer → Schiebe bis Ziel\n\n"
        f"<b>Sniper-Beispiel:</b>\n"
        f"Fremder: Court 2 | 08:00–09:30\n"
        f"→ Bot zielt: Court 2 | 09:00–10:30\n"
        f"→ Hämmert sekündlich bis Treffer\n"
        f"→ Danach: Schiebe bis Wunschzeit"
    )

    if pid_warnungen:
        startup_msg += (f"\n\n⚠️ <b>Person-ID fehlt für: {', '.join(pid_warnungen)}</b>\n"
                        f"Buchungen lösen beim ersten Versuch einen Neu-Login aus.")

    senden(startup_msg)
    zeige_account_auswahl()

    threading.Thread(target=telegram_loop, daemon=True).start()

    log.info("✅ Bot läuft. Strg+C zum Beenden.")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        log.info("Bot beendet.")
        senden("⏹️ Padel Bot v10.0.0 wurde beendet.")
