#!/usr/bin/env python3
"""Padel Bot v10.0.0

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
AGGRESSIVE_TIMEOUT      = 300
AGGRESSIVE_INTERVAL     = 0.1
FRUEH_EXKLUSIV_VERSUCHE = 8

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

    # Account 1 (Pflicht)
    email1 = _optional("account_1_email")
    pw1    = _optional("account_1_passwort")

    if not email1 or not pw1:
        raise SystemExit("❌ account_1_email / account_1_passwort fehlen in options.json!")

    label1 = _optional("account_1_label") or "ACC1"
    accounts[label1] = {"email": email1, "passwort": pw1}

    # Account 2
    email2 = _optional("account_2_email")
    pw2    = _optional("account_2_passwort")

    if email2 and pw2:
        label2 = _optional("account_2_label") or "ACC2"

        if label2 in accounts:
            label2 += "_2"

        accounts[label2] = {"email": email2, "passwort": pw2}

    # Account 3
    email3 = _optional("account_3_email")
    pw3    = _optional("account_3_passwort")

    if email3 and pw3:
        label3 = _optional("account_3_label") or "ACC3"

        if label3 in accounts:
            label3 += "_3"

        accounts[label3] = {"email": email3, "passwort": pw3}

    # Account 4
    email4 = _optional("account_4_email")
    pw4    = _optional("account_4_passwort")

    if email4 and pw4:
        label4 = _optional("account_4_label") or "ACC4"

        if label4 in accounts:
            label4 += "_4"

        accounts[label4] = {"email": email4, "passwort": pw4}

    # Account 5
    email5 = _optional("account_5_email")
    pw5    = _optional("account_5_passwort")

    if email5 and pw5:
        label5 = _optional("account_5_label") or "ACC5"

        if label5 in accounts:
            label5 += "_5"

        accounts[label5] = {"email": email5, "passwort": pw5}

    # Account 6
    email6 = _optional("account_6_email")
    pw6    = _optional("account_6_passwort")

    if email6 and pw6:
        label6 = _optional("account_6_label") or "ACC6"

        if label6 in accounts:
            label6 += "_6"

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
        # Sniper (NEU)
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
        return (f"🔴 {k} – {datum_str} "
                f"{aktiv.get('fromTime','?')}–{aktiv.get('toTime','?')}")
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
# BUCHUNG  –  FIX 1: Kein verifiziert=True Fallback mehr!
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

        # ── FIX 1: Verifizierung ohne Exception-Fallback ──────────────────────
        # Erster Versuch nach 1s
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
                # KEIN Fallback auf True mehr! Nur False zurückgeben.

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
    h = {"accept": "text/html, */*; q=0.01", "x-ajax-call": "true",
         "x-csrf-token": csrf_t, "x-requested-with": "XMLHttpRequest",
         "referer": f"{BASE_URL}/padel?currentDate={datum_api}"}
    try:
        http.get(f"{BASE_URL}/court-module/{MODULE}/bookings/{booking_id}/cancel",
                 headers=h, timeout=10)
        r2 = http.get(f"{BASE_URL}/court-module/{MODULE}/bookings/{booking_id}/cancel",
                      params={"button_confirm": CONFIRM_KEY},
                      headers={**h, "accept": "*/*"}, timeout=10)
        if r2.status_code in [200, 302]:
            az_set(k, "aktive_buchung", None)
            log.info(f"✅ [{k}] Stornierung OK")
            return True
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

    h = {"accept": "*/*", "x-ajax-call": "true", "x-csrf-token": csrf_t,
         "x-requested-with": "XMLHttpRequest", "referer": f"{BASE_URL}/"}

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
                    soup.find_all(attrs={"href": re.compile(r"/bookings/\d+")}) +
                    soup.find_all(attrs={"data-target": re.compile(r"/bookings/\d+")})
                    if tag.find_parent("div")
                })
            if not karten:
                karten = [soup]

            for karte in karten:
                if karte.find(class_=lambda c: c and
                              ("badge-danger" in c or "cancelled" in c or "storniert" in c)):
                    continue
                text        = karte.get_text(" ", strip=True)
                datum_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
                if not datum_match:
                    continue
                datum_de  = datum_match.group(1)
                datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
                if datum_obj.date() < jetzt.date():
                    continue
                zeit_match = re.search(
                    r"(?:von\s+)?(\d{1,2}:\d{2})\s*(?:Uhr\s+)?(?:bis|–|-)\s*(\d{1,2}:\d{2})",
                    text, re.I)
                if not zeit_match:
                    continue
                from_str = zeit_match.group(1).zfill(5)
                to_str   = zeit_match.group(2).zfill(5)
                slot_dt  = datetime.combine(datum_obj.date(),
                                            datetime.strptime(from_str, "%H:%M").time())
                if slot_dt < jetzt:
                    continue
                court_match = re.search(r"[Cc]ourt\s*(\d+)", text)
                court = int(court_match.group(1)) if court_match else 1
                bid   = None
                for pa in ["data-target", "href", "data-url", "action"]:
                    for tag in karte.find_all(attrs={pa: re.compile(r"/bookings/\d+")}):
                        m2 = re.search(r"/bookings/(\d+)", tag.get(pa, ""))
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
                    "dauer":      int((datetime.strptime(to_str, "%H:%M") -
                                      datetime.strptime(from_str, "%H:%M")).seconds / 60),
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

# ══════════════════════════════════════════════
# AGGRESSIVE BUCHUNG
# ══════════════════════════════════════════════

def _aggressiv_buchen_07(k: str, datum_de: str, datum_api: str, dauer_min: int) -> bool:
    oeffnung = datetime.strptime(ANLAGE_OEFFNUNG, "%H:%M")
    slot_07  = {
        "fromTime":  "07:00",
        "toTime":    (oeffnung + timedelta(minutes=dauer_min)).strftime("%H:%M"),
        "dauer":     dauer_min,
        "datum_api": datum_api,
        "datum_de":  datum_de,
    }
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
            slot    = {**slot_07, "court": court_v,
                       "key": f"{datum_api}_{court_v}_07:00_{dauer_min}"}
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
# SCHIEBE PHASE 3 – ausgelagert für Sniper-Wiederverwendung
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
        random_offset  = random.randint(SCHIEBE_MINUTEN_VOR_MIN, SCHIEBE_MINUTEN_VOR_MAX)
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

        # FIX 2a: Storno-Retry prüft jetzt aktiv() → Sofort-Stopp möglich
        storno_ok = False
        for storno_versuch in range(6):
            if not aktiv():
                return                              # ← NEU: sofortiger Abbruch
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

        # FIX 2b: Sofort-Rebook nach Storno – 30 Versuche, 0.1s für erste 15
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
            # Erste 15 Versuche: 0.1s – danach 0.5s
            time.sleep(0.1 if versuch < 15 else 0.5)

        letzter_session_check = time.time()

        if ok:
            # FIX 2c: Bestätigung nur nach verifiziertem aktive_buchung
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
            senden(f"✅ [{k}] Eingeloggt – warte auf exakt {buchbar_ab} Uhr...")
            restzeit = (buchbar_dt - jetzt_lokal()).total_seconds()
            if restzeit > 0:
                time.sleep(restzeit)
        else:
            if not _session_refresh_vor_aktion(k, f"Direkt sofort ab {buchbar_ab}"):
                beende(f"❌ [{k}] Login fehlgeschlagen!")
                return

        senden(f"🎯 <b>[{k}] Direkte Taktik – Dauerbeschuss startet!</b>\n"
               f"⏰ Es ist {buchbar_ab} Uhr!\n"
               f"🎯 Buche {datum_de} ab {buchbar_ab} Uhr | Court 2 bevorzugt")

        ab_dt        = datetime.strptime(buchbar_ab, "%H:%M")
        direkt_court = az_get(k, "schiebe_court") or 0
        if not _aggressiv_buchen_ab(k, datum_de, datum_api, dauer_min, ab_dt, ziel_dt,
                                    bevorzugter_court=direkt_court):
            beende(f"❌ [{k}] Kein Slot ab {buchbar_ab} Uhr buchbar nach {AGGRESSIVE_TIMEOUT}s.")
            return

        buchung = az_get(k, "aktive_buchung")
        senden(f"✅ <b>[{k}] Direkt-Slot gebucht!</b>\n"
               f"🕐 {buchung['fromTime']}–{buchung['toTime']} | Court {buchung['court']}\n"
               f"🔄 Schiebe Richtung {ziel_str} Uhr...")

    # ── Phase 3: Schrittweise schieben ───────────────────────────────────────
    _schiebe_phase3(k, datum_de, datum_api, dauer_min, ziel_str)

# ══════════════════════════════════════════════
# SNIPER  –  NEU in v10.0.0
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
    Sniper-Modus: Zielt auf den Slot 30 Min vor Ende einer fremden Buchung.
    Hämmert sekündlich – sobald der Fremde storniert, schlägt der Bot zu.
    Danach: normaler Schiebe-Loop (_schiebe_phase3) bis zur Zielzeit.

    Beispiel:
      Fremder hat Court 2 | 08:00–09:30
      Sniper zielt auf:   Court 2 | 09:00–10:30  (= fremdes Ende - 30 Min)
      Nach Treffer:       Schiebe weiter bis 18:00 Uhr
    """
    datum_de    = az_get(k, "sniper_datum")
    fremder_bis = az_get(k, "sniper_fremder_bis")   # z.B. "09:30"
    court       = az_get(k, "sniper_court")          # Court des Fremden
    dauer_min   = az_get(k, "sniper_dauer")
    ziel_str    = az_get(k, "sniper_ziel")

    datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
    datum_api = datum_obj.strftime("%m/%d/%Y")

    fremder_bis_dt = datetime.strptime(fremder_bis, "%H:%M")
    target_von_dt  = fremder_bis_dt - timedelta(minutes=30)
    target_bis_dt  = target_von_dt + timedelta(minutes=dauer_min)
    target_von     = target_von_dt.strftime("%H:%M")
    target_bis     = target_bis_dt.strftime("%H:%M")

    target_slot = {
        "court":     court,
        "fromTime":  target_von,
        "toTime":    target_bis,
        "dauer":     dauer_min,
        "datum_api": datum_api,
        "datum_de":  datum_de,
        "key":       f"{datum_api}_{court}_{target_von}_{dauer_min}",
    }

    senden(f"🎯 <b>[{k}] Sniper gestartet!</b>\n"
           f"📅 {_datum_mit_tag(datum_de)}\n"
           f"🏟️ Court {court} | Fremde Buchung endet: {fremder_bis} Uhr\n"
           f"💥 Sniper-Ziel: <b>{target_von}–{target_bis}</b>\n"
           f"🔄 Nach Treffer → Schiebe bis {ziel_str} Uhr\n"
           f"⚡ Hämmere sekündlich auf {target_von} Uhr...")

    versuche      = 0
    letzter_login = time.time()

    if not _session_refresh_vor_aktion(k, f"Sniper start"):
        az_set(k, "sniper_aktiv", False)
        senden(f"❌ [{k}] Sniper: Login fehlgeschlagen!")
        zeige_account_menue(k)
        return

    while az_get(k, "sniper_aktiv"):
        # Session-Refresh alle 60 Sekunden
        if versuche > 0 and time.time() - letzter_login > 60:
            if not ist_eingeloggt(k):
                log.info(f"[{k}] Sniper: Session-Refresh nach {versuche} Versuchen...")
                if einloggen(k):
                    letzter_login = time.time()
                    log.info(f"[{k}] Sniper: Neu eingeloggt.")
                else:
                    senden(f"❌ [{k}] Sniper: Login fehlgeschlagen – stoppe.")
                    az_set(k, "sniper_aktiv", False)
                    zeige_account_menue(k)
                    return
            else:
                letzter_login = time.time()

        if buche_slot(k, target_slot):
            buchung = az_get(k, "aktive_buchung")
            if buchung:
                wetter_str = hole_wetter(datum_de, target_von)
                senden(f"🎯 <b>[{k}] SNIPER TREFFER!</b>\n"
                       f"📅 {_datum_mit_tag(datum_de)}\n"
                       f"🕐 {buchung['fromTime']}–{buchung['toTime']} | Court {buchung['court']}\n"
                       f"🏆 Nach {versuche+1} Versuchen!\n"
                       f"🔄 Schiebe weiter → {ziel_str} Uhr..."
                       + wetter_str)
            else:
                senden(f"🎯 <b>[{k}] SNIPER TREFFER!</b> (nach {versuche+1} Versuchen)\n"
                       f"🔄 Schiebe weiter → {ziel_str} Uhr...")

            az_set(k, "sniper_aktiv", False)

            # Schiebe-Zustand setzen und Phase 3 starten
            az_set_multi(k,
                schiebe_aktiv=True,
                schiebe_datum=datum_de,
                schiebe_ziel=ziel_str,
                schiebe_dauer=dauer_min,
                schiebe_modus="sniper",
            )
            _schiebe_phase3(k, datum_de, datum_api, dauer_min, ziel_str)
            return

        versuche += 1
        # 1 Sekunde zwischen Versuchen – schnell genug um den Slot zu erwischen
        time.sleep(1.0)

    senden(f"⏹️ [{k}] Sniper gestoppt nach {versuche} Versuchen.")
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
    buchbar_dt = datetime.combine(jetzt.date(), datetime.strptime(buchbar_ab, "%H:%M").time())
    min_bis   = int((buchbar_dt - jetzt).total_seconds() / 60) if buchbar_dt > jetzt else 0

    senden(f"🎯 <b>[{k}] Direkte Taktik konfiguriert!</b>\n"
           f"📅 {datum}\n"
           f"⏰ Buchbar ab heute: {buchbar_ab} Uhr "
           f"{'(in ' + str(min_bis) + ' Min)' if min_bis > 0 else '(sofort)'}\n"
           f"🎯 Ziel: {ziel} Uhr ({dauer} Min)\n"
           f"📆 Datum in {tage_bis} Tagen\n\n"
           + (f"⏳ Warte noch {tage_bis-7} Tag(e) bis 7-Tage-Fenster, "
              f"dann auf {buchbar_ab} Uhr..." if tage_bis > 7
              else f"🚀 Warte auf {buchbar_ab} Uhr heute..."))

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
        zeige_schiebe_modus_auswahl(k)

    # ── Sniper-Modus (NEU) ────────────────────────────────────────────────────
    elif data == "menu_sniper":
        if az_get(k, "schiebe_aktiv") or az_get(k, "sniper_aktiv"):
            senden(f"⚠️ [{k}] Prozess läuft bereits! Erst stoppen.")
            zeige_account_menue(k)
            return
        if az_get(k, "aktive_buchung"):
            senden(f"⚠️ [{k}] Aktive Buchung vorhanden.\nSniper nur ohne aktive Buchung.")
            zeige_account_menue(k)
            return
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
        slot = {"court": court, "fromTime": from_t, "toTime": to_t,
                "dauer": dauer, "datum_api": datum_api, "datum_de": datum_de,
                "key": f"{datum_api}_{court}_{from_t}_{dauer}"}
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

    # ── Sniper-Setup Callbacks (NEU) ──────────────────────────────────────────
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
