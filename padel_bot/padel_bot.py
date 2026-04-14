#!/usr/bin/env python3
"""Padel Bot v8.4 – Dual-Account | 3 Schiebe-Modi | Court-2-Präferenz
=====================================================================
MENÜ-STRUKTUR:
  Ebene 1 → Account-Auswahl (SB / KS mit Live-Status + Aktualisieren)
  Ebene 2 → Klassisch buchen | Schiebe-Taktik | Stornieren | Status
  Ebene 3 → Schiebe-Modi:
    🌅 Früh-Methode   – Wartet auf 07:00 am 7-Tage-Tag, aggressiver Dauerbeschuss
    🕐 Spät-Taktik    – Bucht sofort den spätesten noch freien Slot, schiebt weiter
    🎯 Direkte Taktik – User gibt "buchbar ab" per Text ein (z.B. "13:00" bei Wartung)

COURT-PRIORITÄT: Court 2 immer zuerst, Court 1 als Fallback (automatisch, kein Button)

AGGRESSIVE BUCHUNG (Früh + Direkt):
  Dauerbeschuss alle 0.3s, Court-Rotation 2↔1, max 300 Sekunden.
"""

import re
import json
import requests
import threading
import time
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

# ─────────────────────────────────────────────
#  ZEITZONE (HA-Container läuft auf UTC, Bot braucht Berliner Zeit)
# ─────────────────────────────────────────────
_BERLIN = ZoneInfo("Europe/Berlin")

def jetzt_lokal() -> datetime:
    """Gibt die aktuelle Berliner Ortszeit als naive datetime zurück."""
    return datetime.now(_BERLIN).replace(tzinfo=None)

# ─────────────────────────────────────────────
#  KONFIGURATION – aus Home Assistant options.json laden
#  Die Werte werden in der HA-UI eingetragen und lokal in
#  /data/options.json gespeichert. Niemals im Code hardcoden!
# ─────────────────────────────────────────────
_OPTIONS_PATH = "/data/options.json"

def _lade_options() -> dict:
    try:
        with open(_OPTIONS_PATH, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"❌ {_OPTIONS_PATH} nicht gefunden – Add-on-Optionen in HA eintragen!")
    except json.JSONDecodeError as e:
        raise SystemExit(f"❌ Fehler beim Lesen von {_OPTIONS_PATH}: {e}")

_cfg = _lade_options()

def _required(key: str) -> str:
    val = _cfg.get(key, "").strip()
    if not val:
        raise SystemExit(f"❌ Option '{key}' ist leer – bitte in der HA Add-on-Konfiguration ausfüllen!")
    return val

TELEGRAM_BOT_TOKEN   = _required("telegram_bot_token")
TELEGRAM_CHAT_ID     = _required("telegram_chat_id")

ANLAGE_OEFFNUNG      = "07:00"
ANLAGE_SCHLUSS       = "22:00"

SCHIEBE_MINUTEN_VOR  = 10     # Minuten vor Slot-Ende → schieben
LOGIN_CHECK_COOLDOWN = 30     # Sekunden zwischen Session-Checks
AGGRESSIVE_TIMEOUT   = 300    # Sekunden Dauerbeschuss bei Früh/Direkt
AGGRESSIVE_INTERVAL  = 0.3    # Sekunden zwischen Buchungsversuchen

# ─────────────────────────────────────────────
#  KONSTANTEN
# ─────────────────────────────────────────────
BASE_URL     = "https://bsbb.ebusy.de"
MODULE       = "4"
BOOKING_TYPE = "4"
CONFIRM_KEY  = "de.productiveweb.ebusy.model.tenant.general.booking.UserBookingCancelConfirm"
PERSON_ID_FALLBACK = {"SB": "2748", "KS": "2929"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  ACCOUNT-DEFINITIONEN – aus HA-Optionen
# ─────────────────────────────────────────────
ACCOUNTS = {
    "SB": {"email": _required("sb_email"),  "passwort": _required("sb_passwort")},
    "KS": {"email": _required("ks_email"),  "passwort": _required("ks_passwort")},
}

# ─────────────────────────────────────────────
#  ACCOUNT-ZUSTAND
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
        "person_id":          PERSON_ID_FALLBACK.get(kuerzel, ""),
        "letzter_logincheck": 0.0,
        "lock":               threading.Lock(),
        # Buchung
        "aktive_buchung":     None,   # dict: court/fromTime/toTime/datum_de/datum_api/booking_id
        # Schiebe
        "schiebe_aktiv":      False,
        "schiebe_modus":      None,   # "frueh" | "spaet" | "direkt"
        "schiebe_datum":      None,   # "DD.MM.YYYY"
        "schiebe_ziel":       None,   # "HH:MM"
        "schiebe_dauer":      None,   # 60 oder 90
        "schiebe_buchbar_ab": None,   # "HH:MM" – nur Direkt-Modus
        "schiebe_thread":     None,
        # Flow-Kontext (mehrstufige Buttons)
        "flow":               None,
        "flow_datum":         None,
        "flow_dauer":         None,
    }

acc = {k: neuer_account_zustand(k) for k in ACCOUNTS}

# Welcher Account ist gerade im Telegram-Flow aktiv
_flow_account = {"kuerzel": None}
_flow_lock    = threading.Lock()
telegram_offset = 0

# ─────────────────────────────────────────────
#  ACCOUNT-HELFER (thread-sicher)
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
#  TELEGRAM HELPERS
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
#  MENÜ-FUNKTIONEN
# ══════════════════════════════════════════════

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

def account_status_label(k: str) -> str:
    snap    = az_snap(k, "aktive_buchung", "schiebe_aktiv", "schiebe_datum", "schiebe_ziel")
    aktiv   = snap["aktive_buchung"]
    schiebe = snap["schiebe_aktiv"]
    thread  = acc[k].get("schiebe_thread")
    if schiebe and thread and not thread.is_alive():
        az_set(k, "schiebe_aktiv", False)
        schiebe = False
    if aktiv:
        return (f"🔴 {k} – {aktiv.get('datum_de','?')[:5]} "
                f"{aktiv.get('fromTime','?')}–{aktiv.get('toTime','?')}")
    elif schiebe:
        return f"🟡 {k} – Schiebe {(snap['schiebe_datum'] or '?')[:5]}"
    return f"✅ {k} – frei"

def zeige_account_auswahl():
    set_flow_account(None)
    for k in ACCOUNTS:
        try:
            sync_buchung_vom_server(k)
        except Exception as e:
            log.warning(f"[{k}] Sync: {e}")
    senden("🎾 <b>Padel Bot – Account wählen</b>\n\n"
           "✅ frei  |  🔴 Buchung  |  🟡 Schiebe",
           buttons=[
               [{"text": account_status_label("SB"), "callback_data": "acc_SB"}],
               [{"text": account_status_label("KS"), "callback_data": "acc_KS"}],
               [{"text": "🔄 Aktualisieren",          "callback_data": "refresh_accounts"}],
           ])

def zeige_account_menue(k: str):
    snap    = az_snap(k, "aktive_buchung", "schiebe_aktiv",
                      "schiebe_ziel", "schiebe_datum", "schiebe_dauer", "schiebe_modus")
    aktiv   = snap["aktive_buchung"]
    schiebe = snap["schiebe_aktiv"]
    modus_l = {"frueh": "Früh", "spaet": "Spät", "direkt": "Direkt"}.get(snap["schiebe_modus"] or "", "")

    if aktiv:
        status = (f"🔴 <b>Aktive Buchung:</b>\n"
                  f"   {aktiv['datum_de']} | {aktiv['fromTime']}–{aktiv['toTime']} | Court {aktiv['court']}")
        if schiebe:
            status += f"\n🟡 Schiebe ({modus_l}) → Ziel {snap['schiebe_ziel']} Uhr ({snap['schiebe_dauer']} Min)"
    elif schiebe:
        status = (f"🟡 Schiebe-Taktik ({modus_l}) läuft\n"
                  f"   Ziel: {(snap['schiebe_datum'] or '')[:5]} {snap['schiebe_ziel']} Uhr ({snap['schiebe_dauer']} Min)")
    else:
        status = "✅ Kein aktiver Prozess"

    senden(f"🎾 <b>Account: {k}</b>\n\n{status}\n\nWas möchtest du tun?",
           buttons=[
               [{"text": "📅 Klassisch buchen",   "callback_data": f"menu_slots_{k}"}],
               [{"text": "🔄 Schiebe-Taktik",      "callback_data": f"menu_schiebe_{k}"}],
               [{"text": "📊 Status",              "callback_data": f"menu_status_{k}"}],
               [{"text": "⏹️ Schiebe stoppen",     "callback_data": f"menu_stopp_{k}"}],
               [{"text": "🗑️ Buchung stornieren",  "callback_data": f"menu_storno_{k}"}],
               [{"text": "↩️ Account-Auswahl",      "callback_data": "zurueck_accounts"}],
           ])

def zeige_schiebe_modus_auswahl(k: str):
    senden(
        f"🔄 <b>[{k}] Schiebe-Taktik – Modus wählen</b>\n\n"
        f"🌅 <b>Früh-Methode:</b>\nWartet auf 07:00 am 7-Tage-Tag, bucht sofort per Dauerbeschuss (Court 2 bevorzugt), schiebt zur Wunschzeit.\n\n"
        f"🕐 <b>Spät-Taktik:</b>\nDu hast 07:00 verpasst → Bot bucht sofort den spätesten noch freien Slot und schiebt weiter zur Wunschzeit.\n\n"
        f"🎯 <b>Direkte Taktik:</b>\nDu kennst die genaue Startzeit (z.B. 13:00 nach Wartung). Bot wartet präzise, dann Dauerbeschuss + Schiebe-Taktik.",
        buttons=[
            [{"text": "🌅 Früh-Methode  (07:00 Uhr Dauerbeschuss)",   "callback_data": f"schiebe_modus_frueh_{k}"}],
            [{"text": "🕐 Spät-Taktik  (spätester freier Slot jetzt)", "callback_data": f"schiebe_modus_spaet_{k}"}],
            [{"text": "🎯 Direkte Taktik  (bekannte Startzeit)",        "callback_data": f"schiebe_modus_direkt_{k}"}],
            [{"text": "↩️ Zurück",                                       "callback_data": f"acc_{k}"}],
        ])

# ══════════════════════════════════════════════
#  BUTTON-HELFER
# ══════════════════════════════════════════════

def erstelle_datum_buttons(prefix: str, nur_im_fenster: bool = False) -> list:
    """
    nur_im_fenster=True: Nur Tage anzeigen die bereits im 7-Tage-Buchungsfenster sind.
    """
    heute = jetzt_lokal()
    buttons, reihe = [], []
    for i in range(1, 11):
        tag      = heute + timedelta(days=i)
        tage_dif = (tag.date() - heute.date()).days
        if nur_im_fenster and tage_dif > 7:
            continue
        wt    = WOCHENTAGE[tag.weekday()]
        label = f"{wt} {tag.strftime('%d.%m.')}"
        reihe.append({"text": label, "callback_data": f"{prefix}_{tag.strftime('%d.%m.%Y')}"})
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

def zielzeit_buttons(prefix: str, dauer_min: int) -> list:
    schluss  = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")
    letzter  = schluss - timedelta(minutes=dauer_min)
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

# ══════════════════════════════════════════════
#  LOGIN & SESSION
# ══════════════════════════════════════════════

def hole_csrf(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in [soup.find("meta", {"name": "_csrf"}), soup.find("input", {"name": "_csrf"})]:
        if tag:
            val = tag.get("content") or tag.get("value")
            if val:
                return val
    m = re.search(r'"_csrf"\s*:\s*"([a-f0-9\-]{30,})"', html)
    return m.group(1) if m else ""

def extrahiere_person_id(html: str) -> str:
    for p in [r'purchaseTemplate\.person["\s]*[=:]["\s]*(\d+)',
              r'"personId"\s*:\s*(\d+)',
              r'data-person[="\s]+(\d+)',
              r'<option[^>]+value="(\d{3,6})"[^>]*selected',
              r'person.*?value="(\d{3,6})"']:
        m = re.search(p, html, re.IGNORECASE)
        if m:
            return m.group(1)
    return ""

def einloggen(k: str) -> bool:
    cfg  = ACCOUNTS[k]
    http = acc[k]["http"]
    log.info(f"🔑 [{k}] Login...")
    try:
        r    = http.get(f"{BASE_URL}/login", timeout=15)
        csrf = hole_csrf(r.text)
        r2   = http.post(f"{BASE_URL}/login",
                         data={"username": cfg["email"], "password": cfg["passwort"], "_csrf": csrf},
                         headers={"content-type": "application/x-www-form-urlencoded",
                                  "origin": BASE_URL, "referer": f"{BASE_URL}/login"},
                         allow_redirects=True, timeout=15)
        ok = ("logout" in r2.text.lower() or "abmelden" in r2.text.lower()
              or "/login" not in r2.url)
        if ok:
            r3 = http.get(f"{BASE_URL}/padel", timeout=10)
            csrf_t    = hole_csrf(r3.text) or http.cookies.get("XSRF-TOKEN", "")
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
                person_id = PERSON_ID_FALLBACK.get(k, "")
                log.warning(f"[{k}] PERSON_ID Fallback: {person_id}")
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
    jetzt = time.time()
    if jetzt - az_get(k, "letzter_logincheck") < LOGIN_CHECK_COOLDOWN:
        return True
    try:
        r = acc[k]["http"].get(f"{BASE_URL}/padel", timeout=10,
                                headers={"accept": "text/html,*/*",
                                         "x-requested-with": "XMLHttpRequest"})
        ok = r.status_code == 200 and ("logout" in r.text.lower() or "abmelden" in r.text.lower())
        if ok:
            az_set(k, "letzter_logincheck", time.time())
        return ok
    except Exception:
        return False

def stelle_session_sicher(k: str) -> bool:
    if not ist_eingeloggt(k):
        senden(f"🔑 [{k}] Session abgelaufen, logge neu ein...")
        ok = einloggen(k)
        senden(f"✅ [{k}] Neu eingeloggt!" if ok else f"❌ [{k}] Login fehlgeschlagen!")
        return ok
    return True

# ══════════════════════════════════════════════
#  SLOT-BERECHNUNG (Court 2 zuerst)
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
    """
    Gibt freie Slots zurück. Court 2 erscheint zuerst (Präferenz).
    Slots innerhalb des 7-Tage-Buchungsfensters.
    """
    datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
    datum_api = datum_obj.strftime("%m/%d/%Y")
    jetzt     = jetzt_lokal()
    res       = hole_reservierungen(k, datum_api)

    if ignoriere_booking_id:
        res = [r for r in res if r.get("booking") != ignoriere_booking_id
               and r.get("bookingOrBlockingId") != ignoriere_booking_id]

    schluss       = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")
    letzter_start = schluss - timedelta(minutes=dauer_min)
    # 7-Tage-Grenze auf Tages-Ebene (verhindert Off-by-seconds-Fehler)
    grenze = datetime.combine((jetzt + timedelta(days=7)).date(), schluss.time())

    freie = []
    for court in [2, 1]:   # ← Court 2 zuerst (Präferenz)
        belegt = [(datetime.strptime(r["fromTime"], "%H:%M"),
                   datetime.strptime(r["toTime"],   "%H:%M"))
                  for r in res if r["court"] == court]
        t = datetime.strptime(ANLAGE_OEFFNUNG, "%H:%M")
        while t <= letzter_start:
            t_bis = t + timedelta(minutes=dauer_min)
            if t_bis > schluss:
                t += timedelta(minutes=30); continue
            if datetime.combine(datum_obj.date(), t.time()) > grenze:
                t += timedelta(minutes=30); continue
            if not any(not (t_bis <= bv or t >= bb) for bv, bb in belegt):
                freie.append({
                    "court":    court,
                    "fromTime": t.strftime("%H:%M"),
                    "toTime":   t_bis.strftime("%H:%M"),
                    "dauer":    dauer_min,
                    "datum_api": datum_api,
                    "datum_de":  datum_de,
                    "key":       f"{datum_api}_{court}_{t.strftime('%H:%M')}_{dauer_min}",
                })
            t += timedelta(minutes=30)
    return freie

# ══════════════════════════════════════════════
#  BUCHUNG
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

    log.info(f"🎾 [{k}] Buche Court {court} | {datum_de} | {from_t}–{to_t}")
    h  = {"accept": "*/*", "x-ajax-call": "true", "x-csrf-token": csrf_t,
           "x-requested-with": "XMLHttpRequest",
           "referer": f"{BASE_URL}/padel?currentDate={datum_api}"}
    hp = {**h, "content-type": "application/x-www-form-urlencoded; charset=UTF-8", "origin": BASE_URL}
    try:
        r1 = http.get(f"{BASE_URL}/court-single-booking-flow", headers=h,
                      params={"module": MODULE, "court": court, "courts": "1,2",
                              "fromTime": from_t, "toTime": to_t, "date": datum_api},
                      timeout=10)
        execution = "e1s1"
        m = re.search(r"execution=(e\d+s\d+)", r1.text)
        if m: execution = m.group(1)

        if not person_id:
            person_id = extrahiere_person_id(r1.text) or PERSON_ID_FALLBACK.get(k, "")
            if person_id: az_set(k, "person_id", person_id)

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
        if m2: exec2 = m2.group(1)

        r3 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                       params={"execution": exec2, "_eventId": "commit"},
                       data=f"purchaseTemplate.comment=&_csrf={csrf_t}",
                       timeout=10)

        if r3.status_code not in [200, 302]: return False
        if any(w in r3.text.lower() for w in ["fehler", "error", "nicht möglich"]):
            log.warning(f"[{k}] Buchung: Server-Fehler")
            return False

        booking_id = None
        for pat in [r'"bookingId"\s*:\s*(\d+)', r'/bookings/(\d+)', r'booking[=_](\d+)']:
            mid = re.search(pat, r3.text)
            if mid: booking_id = int(mid.group(1)); break

        if not booking_id:
            for res in hole_reservierungen(k, datum_api):
                if (res["court"] == int(court) and res["fromTime"] == from_t and res["toTime"] == to_t):
                    booking_id = res.get("booking") or res.get("bookingOrBlockingId"); break

        az_set(k, "aktive_buchung", {**slot, "court": int(court), "booking_id": booking_id})
        log.info(f"✅ [{k}] Buchung OK – ID: {booking_id}")
        return True
    except Exception as e:
        log.error(f"[{k}] Buchungsfehler: {e}")
        return False

# ══════════════════════════════════════════════
#  STORNIERUNG
# ══════════════════════════════════════════════

def storniere_buchung(k: str, booking_id: int, datum_api: str) -> bool:
    log.info(f"🗑️ [{k}] Storniere ID {booking_id}")
    snap  = az_snap(k, "csrf_token", "http")
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
#  SERVER-SYNC (erkennt auch Browser-Buchungen)
# ══════════════════════════════════════════════

def sync_buchung_vom_server(k: str, debug_telegram: bool = False):
    """
    Holt eigene aktive Buchungen via /user/my-bookings/page.
    Erkennt auch manuell (nicht über Bot) gebuchte Slots.
    Liefert die nächste zukünftige, nicht stornierte Buchung.
    1:1 aus V6 übernommen – bewährt und stabil.
    """
    # Prüfe ob Schiebe-Thread noch lebt bevor wir abbrechen.
    # Ohne das: abgestürzter Thread → schiebe_aktiv=True bleibt ewig →
    # Sync überspringt immer → Account zeigt "frei" obwohl Buchung existiert.
    if az_get(k, "schiebe_aktiv"):
        thread = acc[k].get("schiebe_thread")
        if thread and not thread.is_alive():
            log.warning(f"[{k}] Sync: Schiebe-Thread tot, korrigiere schiebe_aktiv=False")
            az_set(k, "schiebe_aktiv", False)
        else:
            return  # Schiebe-Loop verwaltet aktive_buchung selbst

    http_sess = acc[k]["http"]
    csrf_t    = az_get(k, "csrf_token")
    jetzt     = jetzt_lokal()
    gefunden  = None

    h = {
        "accept":           "*/*",
        "x-ajax-call":      "true",
        "x-csrf-token":     csrf_t,
        "x-requested-with": "XMLHttpRequest",
        "referer":          f"{BASE_URL}/",
    }

    sync_erfolgreich = False

    # Bei 401: Session neu einloggen und nochmal versuchen
    for login_versuch in range(2):
        try:
            r_pages = http_sess.get(
                f"{BASE_URL}/user/my-bookings/total-pages",
                params={"size": "50", "sort": ["serviceDate,desc", "id,desc"]},
                headers={**h, "accept": "application/json, text/javascript, */*; q=0.01"},
                timeout=10
            )
            if r_pages.status_code == 401:
                log.warning(f"[{k}] Sync: 401 – logge neu ein...")
                if einloggen(k):
                    http_sess = acc[k]["http"]
                    csrf_t    = az_get(k, "csrf_token")
                    h["x-csrf-token"] = csrf_t
                    continue
                else:
                    log.error(f"[{k}] Re-Login fehlgeschlagen beim Sync.")
                    return
            total_pages = 0
            try:
                raw = r_pages.json()
                log.debug(f"[{k}] total-pages raw response: {raw!r}")
                if isinstance(raw, (int, float)):
                    total_pages = int(raw)
                elif isinstance(raw, str):
                    total_pages = int(raw)
                elif isinstance(raw, dict):
                    # API gibt dict zurück z.B. {"totalPages": 2} oder {"totalPages": {"value": 2}}
                    for key in ("totalPages", "total_pages", "pages", "total"):
                        if key in raw:
                            val = raw[key]
                            if isinstance(val, (int, float)):
                                total_pages = int(val)
                            elif isinstance(val, str):
                                total_pages = int(val)
                            else:
                                # z.B. {"totalPages": {"value": 2}} – nested dict → Fallback 1
                                total_pages = 1
                                log.warning(f"[{k}] total-pages[{key}] ist kein Scalar: {val!r} → Fallback 1")
                            break
                    else:
                        total_pages = 1
                        log.warning(f"[{k}] total-pages dict unbekannt: {raw}")
                else:
                    total_pages = 1
            except Exception:
                total_pages = 1
            total_pages = max(1, min(total_pages, 5))
            sync_erfolgreich = True
            break
        except Exception as e:
            log.error(f"[{k}] Sync total-pages Fehler: {e}")
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
                headers=h,
                timeout=10
            )
            if r_page.status_code != 200:
                log.warning(f"[{k}] my-bookings/page Status: {r_page.status_code}")
                if debug_telegram:
                    senden(f"🔍 [{k}] my-bookings/page → Status {r_page.status_code}")
                break

            raw_html = r_page.text

            if debug_telegram:
                snippet = raw_html[:1500].replace("<", "&lt;").replace(">", "&gt;")
                senden(f"🔍 <b>[{k}] my-bookings HTML (Seite {page}, "
                       f"{len(raw_html)} Zeichen):</b>\n<code>{snippet}</code>")

            soup = BeautifulSoup(raw_html, "html.parser")

            # ── Karten-Erkennung: 3 Fallback-Strategien ──────────────
            # Strategie 1: exakte Bootstrap-Klassen (col-12 + col-sm-6)
            karten = soup.find_all("div", class_=lambda c: c and
                                   "col-12" in c and "col-sm-6" in c)
            # Strategie 2: jede Karte mit Booking-Link (robuster)
            if not karten:
                log.info(f"[{k}] Sync: Strategie 1 leer, versuche Strategie 2 (booking-links)")
                karten = list({
                    tag.find_parent("div") for tag in
                    soup.find_all(attrs={"href":        re.compile(r"/bookings/\d+")}) +
                    soup.find_all(attrs={"data-target": re.compile(r"/bookings/\d+")})
                    if tag.find_parent("div")
                })
            # Strategie 3: Volltext-Suche auf gesamter Seite (letzter Ausweg)
            if not karten:
                log.info(f"[{k}] Sync: Strategie 2 leer, versuche Volltext-Suche")
                karten = [soup]
            # ─────────────────────────────────────────────────────────

            for karte in karten:
                # Stornierte Buchungen überspringen
                if karte.find(class_=lambda c: c and
                              ("badge-danger" in c or "cancelled" in c or "storniert" in c)):
                    continue

                text = karte.get_text(" ", strip=True)

                # Datum: DD.MM.YYYY
                datum_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
                if not datum_match:
                    continue
                datum_de  = datum_match.group(1)
                datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
                if datum_obj.date() < jetzt.date():
                    continue  # vergangene Buchung

                # Zeit-Regex: deckt alle Formate ab
                zeit_match = re.search(
                    r"(?:von\s+)?(\d{1,2}:\d{2})\s*(?:Uhr\s+)?(?:bis|–|-)\s*(\d{1,2}:\d{2})",
                    text, re.I
                )
                if not zeit_match:
                    continue
                from_str = zeit_match.group(1).zfill(5)
                to_str   = zeit_match.group(2).zfill(5)

                slot_dt = datetime.combine(datum_obj.date(),
                                           datetime.strptime(from_str, "%H:%M").time())
                if slot_dt < jetzt:
                    continue

                # Court
                court_match = re.search(r"[Cc]ourt\s*(\d+)", text)
                court = int(court_match.group(1)) if court_match else 1

                # Booking-ID
                bid = None
                for pattern_attr in ["data-target", "href", "data-url", "action"]:
                    for tag in karte.find_all(attrs={pattern_attr: re.compile(r"/bookings/\d+")}):
                        m = re.search(r"/bookings/(\d+)", tag.get(pattern_attr, ""))
                        if m:
                            bid = int(m.group(1))
                            break
                    if bid:
                        break

                datum_api = datum_obj.strftime("%m/%d/%Y")
                gefunden = {
                    "court":      court,
                    "fromTime":   from_str,
                    "toTime":     to_str,
                    "datum_de":   datum_de,
                    "datum_api":  datum_api,
                    "dauer":      int((datetime.strptime(to_str, "%H:%M") -
                                      datetime.strptime(from_str, "%H:%M")).seconds / 60),
                    "booking_id": bid,
                    "key":        f"{datum_api}_{court}_{from_str}",
                }
                log.info(f"[{k}] Sync OK: {datum_de} {from_str}–{to_str} "
                         f"Court {court} ID={bid}")
                break

    except Exception as e:
        log.error(f"[{k}] my-bookings Sync Fehler: {e}")
        if debug_telegram:
            senden(f"❌ [{k}] Sync Exception: {e}")

    # Zustand aktualisieren
    # WICHTIG: aktive_buchung nur auf None setzen wenn sync_erfolgreich=True
    aktuell = az_get(k, "aktive_buchung")
    if gefunden:
        if not aktuell or aktuell.get("booking_id") != gefunden.get("booking_id"):
            log.info(f"[{k}] Buchung erkannt: "
                     f"{gefunden['datum_de']} {gefunden['fromTime']} Court {gefunden['court']}")
        az_set(k, "aktive_buchung", gefunden)
    elif sync_erfolgreich:
        if aktuell and not az_get(k, "schiebe_aktiv"):
            log.info(f"[{k}] Keine aktive Buchung auf dem Server.")
        az_set(k, "aktive_buchung", None)
    else:
        log.warning(f"[{k}] Sync fehlgeschlagen – behalte bisherigen Buchungsstatus.")

# ══════════════════════════════════════════════
#  SCHIEBE-TAKTIK (3 Modi)
# ══════════════════════════════════════════════

def schiebe_loop(k: str):
    """Crash-gesicherter Wrapper."""
    try:
        _schiebe_intern(k)
    except Exception as e:
        log.error(f"[{k}] SCHIEBE CRASH: {e}", exc_info=True)
        senden(f"💥 <b>[{k}] Schiebe-Taktik abgestürzt!</b>\n{e}")
        az_set(k, "schiebe_aktiv", False)
        zeige_account_menue(k)


def _aggressiv_buchen_07(k: str, datum_de: str, datum_api: str, dauer_min: int) -> bool:
    """
    Aggressiver Dauerbeschuss für 07:00-Slot (Früh-Methode).
    Court-Rotation: 2 → 1 → 2 → 1 …
    """
    oeffnung = datetime.strptime(ANLAGE_OEFFNUNG, "%H:%M")
    slot_basis = {
        "fromTime": "07:00",
        "toTime":   (oeffnung + timedelta(minutes=dauer_min)).strftime("%H:%M"),
        "dauer":    dauer_min,
        "datum_api": datum_api,
        "datum_de":  datum_de,
    }
    deadline = time.time() + AGGRESSIVE_TIMEOUT
    versuch  = 0
    while time.time() < deadline:
        if not az_get(k, "schiebe_aktiv"): return False
        court_v = [2, 1][versuch % 2]
        slot    = {**slot_basis, "court": court_v,
                   "key": f"{datum_api}_{court_v}_07:00_{dauer_min}"}
        if buche_slot(k, slot):
            log.info(f"[{k}] 07:00-Slot nach {versuch+1} Versuchen gebucht (Court {court_v})")
            return True
        versuch += 1
        time.sleep(AGGRESSIVE_INTERVAL)
    return False


def _aggressiv_buchen_ab(k: str, datum_de: str, datum_api: str, dauer_min: int,
                          ab_dt: datetime, bis_dt: datetime) -> bool:
    """
    Aggressiver Dauerbeschuss für frühesten freien Slot ab ab_dt (Direkt-Modus).
    Court 2 bevorzugt.
    """
    schluss  = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")
    deadline = time.time() + AGGRESSIVE_TIMEOUT
    while time.time() < deadline:
        if not az_get(k, "schiebe_aktiv"): return False
        freie = berechne_freie_slots(k, datum_de, dauer_min)
        # Court 2 bevorzugt (dank Sortierung in berechne_freie_slots bereits zuerst)
        kandidaten = [s for s in freie
                      if datetime.strptime(s["fromTime"], "%H:%M") >= ab_dt
                      and datetime.strptime(s["fromTime"], "%H:%M") < bis_dt
                      and datetime.strptime(s["toTime"], "%H:%M") <= schluss]
        if kandidaten and buche_slot(k, kandidaten[0]):
            return True
        time.sleep(AGGRESSIVE_INTERVAL)
    return False


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
            if not aktiv(): return False
            time.sleep(min(1, max(0, ende - time.time())))
        return True

    def beende(msg: str = ""):
        az_set(k, "schiebe_aktiv", False)
        if msg: senden(msg)
        zeige_account_menue(k)

    # ══════════════════════════════════════════
    # Phase 1: Warten auf 7-Tage-Fenster (Früh + Direkt)
    # ══════════════════════════════════════════
    if modus in ("frueh", "direkt"):
        while aktiv():
            jetzt    = jetzt_lokal()
            tage_bis = (datum_obj.date() - jetzt.date()).days
            if tage_bis < 7: break
            fenster  = datetime.combine((datum_obj - timedelta(days=7)).date(),
                                        datetime.strptime("07:00", "%H:%M").time())
            sek_bis  = (fenster - jetzt).total_seconds()
            if sek_bis <= 0: break
            senden(f"⏳ <b>[{k}] Wartet auf 7-Tage-Fenster</b>\n"
                   f"📅 {datum_de}\n"
                   f"🔓 Buchbar ab: {fenster.strftime('%d.%m.%Y um 07:00 Uhr')}\n"
                   f"⏱️ Noch {tage_bis - 7} Tag(e) {int((sek_bis % 86400) // 3600)}h")
            schlaf   = min(sek_bis - 30, 23 * 3600)
            if schlaf > 1:
                if not schlafe(schlaf): return
            else:
                if not schlafe(max(0, sek_bis)): return
                break

    if not aktiv(): return

    if not stelle_session_sicher(k):
        beende(f"❌ [{k}] Login fehlgeschlagen.")
        return

    # ══════════════════════════════════════════
    # Phase 2: Ersten Slot buchen (modus-abhängig)
    # ══════════════════════════════════════════

    # ── 🌅 FRÜH-MODUS ─────────────────────────────────────────────────
    if modus == "frueh":
        jetzt    = jetzt_lokal()
        start_07 = datetime.combine(jetzt.date(), datetime.strptime("07:00", "%H:%M").time())
        if jetzt < start_07:
            sek07 = (start_07 - jetzt).total_seconds()
            senden(f"⏳ [{k}] Warte bis 07:00 Uhr (noch {int(sek07/60)} Min)...")
            if not schlafe(max(0, sek07 - 2)): return
            restzeit = (start_07 - jetzt_lokal()).total_seconds()
            if restzeit > 0: time.sleep(restzeit)

        senden(f"🌅 <b>[{k}] Früh-Methode – Dauerbeschuss startet!</b>\n"
               f"📅 {datum_de} | 07:00 Uhr | {dauer_min} Min\n"
               f"🔫 Court 2 bevorzugt, Court 1 Fallback | max {AGGRESSIVE_TIMEOUT}s")

        if not _aggressiv_buchen_07(k, datum_de, datum_api, dauer_min):
            beende(f"❌ [{k}] 07:00-Slot nach {AGGRESSIVE_TIMEOUT}s nicht buchbar.\nBitte manuell versuchen.")
            return

        buchung = az_get(k, "aktive_buchung")
        senden(f"✅ <b>[{k}] Früh-Slot gebucht!</b>\n"
               f"🕐 {buchung['fromTime']}–{buchung['toTime']} | Court {buchung['court']}\n"
               f"🔄 Schiebe Richtung {ziel_str} Uhr...")

    # ── 🕐 SPÄT-MODUS ─────────────────────────────────────────────────
    elif modus == "spaet":
        jetzt = jetzt_lokal()
        senden(f"🕐 <b>[{k}] Spät-Taktik – suche spätesten freien Slot!</b>\n"
               f"📅 {datum_de} | Ziel: {ziel_str} Uhr | {dauer_min} Min\n"
               f"🏟️ Court 2 bevorzugt")

        ok = False
        for versuch in range(30):
            if not aktiv(): return
            freie = berechne_freie_slots(k, datum_de, dauer_min)
            # Spätesten Slot VOR Zielzeit nehmen, Court 2 bevorzugt (schon sortiert)
            # Sortiere: erst nach fromTime absteigend, bei gleicher Zeit Court 2 vor 1
            kandidaten = sorted(
                [s for s in freie
                 if datetime.strptime(s["fromTime"], "%H:%M") < ziel_dt
                 and datetime.strptime(s["toTime"], "%H:%M") <= schluss],
                key=lambda s: (s["fromTime"], 0 if s["court"] == 2 else 1),
                reverse=True
            )
            if kandidaten:
                if buche_slot(k, kandidaten[0]):
                    buchung = az_get(k, "aktive_buchung")
                    senden(f"✅ <b>[{k}] Spätester Slot gebucht!</b>\n"
                           f"🕐 {buchung['fromTime']}–{buchung['toTime']} | Court {buchung['court']}\n"
                           f"🔄 Schiebe Richtung {ziel_str} Uhr...")
                    ok = True
                    break
            log.info(f"[{k}] Spät: Kein Slot, Versuch {versuch+1}/30 – retry in 3s")
            if not schlafe(3): return

        if not ok:
            beende(f"❌ [{k}] Kein buchbarer Slot gefunden. Bitte manuell prüfen.")
            return

    # ── 🎯 DIREKT-MODUS ───────────────────────────────────────────────
    elif modus == "direkt":
        if not buchbar_ab:
            beende(f"❌ [{k}] Keine Startzeit angegeben.")
            return

        jetzt        = jetzt_lokal()
        # FIX: buchbar_dt als vollständiges datetime kombinieren (nicht 1900-Datum lassen)
        # damit der Vergleich jetzt < ziel_buchbar korrekt funktioniert
        buchbar_zeit = datetime.strptime(buchbar_ab, "%H:%M").time()
        buchbar_dt   = datetime.combine(jetzt.date(), buchbar_zeit)   # heute HH:MM
        ziel_buchbar = buchbar_dt  # identisch, sauber

        if jetzt < ziel_buchbar:
            sek_wait = (ziel_buchbar - jetzt).total_seconds()
            senden(f"🎯 <b>[{k}] Direkte Taktik – warte auf Startzeit</b>\n"
                   f"📅 {datum_de} | Buchbar ab: {buchbar_ab} Uhr | Ziel: {ziel_str} Uhr\n"
                   f"⏳ Noch {int(sek_wait/60)} Min bis {buchbar_ab} Uhr...")
            if not schlafe(max(0, sek_wait - 2)): return
            restzeit = (buchbar_dt - jetzt_lokal()).total_seconds()
            if restzeit > 0: time.sleep(restzeit)

        senden(f"🎯 <b>[{k}] Direkte Taktik – Dauerbeschuss startet!</b>\n"
               f"⏰ Es ist {buchbar_ab} Uhr!\n"
               f"🔫 Court 2 bevorzugt | max {AGGRESSIVE_TIMEOUT}s")

        if not _aggressiv_buchen_ab(k, datum_de, datum_api, dauer_min,
                                     datetime.strptime(buchbar_ab, "%H:%M"), ziel_dt):
            beende(f"❌ [{k}] Kein Slot ab {buchbar_ab} Uhr buchbar nach {AGGRESSIVE_TIMEOUT}s.")
            return

        buchung = az_get(k, "aktive_buchung")
        senden(f"✅ <b>[{k}] Direkt-Slot gebucht!</b>\n"
               f"🕐 {buchung['fromTime']}–{buchung['toTime']} | Court {buchung['court']}\n"
               f"🔄 Schiebe Richtung {ziel_str} Uhr...")

    # ══════════════════════════════════════════
    # Phase 3: Schrittweise schieben (alle Modi gleich)
    # Regel: SCHIEBE_MINUTEN_VOR vor Ende → stornieren → neuen Slot buchen
    # Neuer Start: Ende - 30 Min (vorwärts schieben)
    # Court 2 immer bevorzugt, Court 1 Fallback
    # ══════════════════════════════════════════
    stuck_zaehler = {}  # {naechster_von: count}

    while aktiv():
        aktive_b = az_get(k, "aktive_buchung")
        if not aktive_b:
            log.warning(f"[{k}] Keine aktive Buchung mehr.")
            break

        start_dt = datetime.strptime(aktive_b["fromTime"], "%H:%M")
        ende_dt  = datetime.strptime(aktive_b["toTime"],   "%H:%M")

        # Zielzeit erreicht?
        if start_dt >= ziel_dt:
            beende(f"🎯 <b>[{k}] Zielzeit erreicht!</b>\n"
                   f"📅 {aktive_b['datum_de']}\n"
                   f"🕐 {aktive_b['fromTime']}–{aktive_b['toTime']} Uhr\n"
                   f"🏟️ Court {aktive_b['court']}\n\nViel Spaß! 🎾")
            return

        # Schiebe-Moment berechnen:
        # WICHTIG: Das Schieben passiert 7 Tage VOR dem eigentlichen Termin,
        # also HEUTE zur entsprechenden Uhrzeit – NICHT am Buchungsdatum selbst!
        # Wir können nur 7 Tage im Voraus buchen, also stornieren+neu buchen
        # passiert am heutigen Tag (dem Tag, an dem das 7-Tage-Fenster offen ist).
        jetzt = jetzt_lokal()
        schiebe_moment = datetime.combine(
            jetzt.date(),   # ← HEUTE, nicht datum_obj (das wäre in 7 Tagen!)
            (ende_dt - timedelta(minutes=SCHIEBE_MINUTEN_VOR)).time()
        )
        sek   = (schiebe_moment - jetzt).total_seconds()

        if sek > 0:
            tage_rest = int(sek // 86400)
            std_rest  = int((sek % 86400) // 3600)
            min_rest  = int((sek % 3600) // 60)
            if tage_rest > 0:
                warte_str = f"{tage_rest}T {std_rest}h {min_rest}min"
            elif std_rest > 0:
                warte_str = f"{std_rest}h {min_rest}min"
            else:
                warte_str = f"{min_rest}min"
            log.info(f"[{k}] Warte {sek:.0f}s ({warte_str}) bis {schiebe_moment.strftime('%d.%m. %H:%M:%S')}")
            senden(f"⏳ [{k}] Schiebe am <b>{schiebe_moment.strftime('%d.%m.%Y um %H:%M')} Uhr</b>\n"
                   f"   📅 Buchung: {aktive_b['datum_de']} | {aktive_b['fromTime']}–{aktive_b['toTime']} | Court {aktive_b['court']}\n"
                   f"   ⏱️ Noch {warte_str}")
            # Bei sehr langen Wartezeiten: in Tages-Chunks schlafen + täglich Status senden
            while aktiv():
                restzeit = (schiebe_moment - jetzt_lokal()).total_seconds()
                if restzeit <= 60: break
                chunk = min(restzeit - 60, 3600)  # max 1h pro Chunk
                if not schlafe(chunk): return
                # Jede Stunde Status-Update wenn noch > 2h verbleiben
                restzeit2 = (schiebe_moment - jetzt_lokal()).total_seconds()
                if restzeit2 > 7200 and int(restzeit2) % 3600 < int(chunk):
                    tage2 = int(restzeit2 // 86400)
                    std2  = int((restzeit2 % 86400) // 3600)
                    log.info(f"[{k}] Warte noch {tage2}T {std2}h bis Schiebe-Moment")
            restzeit = (schiebe_moment - jetzt_lokal()).total_seconds()
            if restzeit > 2:
                if not schlafe(restzeit - 2): return
            restzeit = (schiebe_moment - jetzt_lokal()).total_seconds()
            if restzeit > 0: time.sleep(restzeit)

        if not aktiv(): return

        # Neuer Slot: Ende - 30 Min vorwärts
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

        # Verfügbarkeit prüfen – Court 2 bevorzugt
        freie     = berechne_freie_slots(k, datum_de, dauer_min, ignoriere_booking_id=booking_id)
        court_neu = next((c for c in [2, 1]
                          if any(s["fromTime"] == naechster_von and s["court"] == c for s in freie)),
                         None)

        if court_neu is None:
            cnt = stuck_zaehler.get(naechster_von, 0) + 1
            stuck_zaehler[naechster_von] = cnt
            if cnt >= 20:
                stuck_zaehler.pop(naechster_von, None)
                beende(f"❌ [{k}] {naechster_von} Uhr dauerhaft belegt (20 Versuche).\n"
                       f"🆘 Manuell: {BASE_URL}/padel?currentDate={datum_api}")
                return
            senden(f"⏳ [{k}] {naechster_von} Uhr belegt ({cnt}/20) – retry in 15s...")
            if not schlafe(15): return
            continue
        stuck_zaehler.pop(naechster_von, None)

        neuer_slot = {
            "court":    court_neu,
            "fromTime": naechster_von,
            "toTime":   naechster_bis,
            "dauer":    dauer_min,
            "datum_api": datum_api,
            "datum_de":  datum_de,
            "key":       f"{datum_api}_{court_neu}_{naechster_von}_{dauer_min}",
        }

        senden(f"⚡ <b>[{k}] Schiebe jetzt!</b>\n"
               f"🗑️ {aktive_b['fromTime']}–{aktive_b['toTime']} → {naechster_von}–{naechster_bis}")

        # Stornieren
        if not (booking_id and storniere_buchung(k, booking_id, datum_api)):
            senden(f"❌ [{k}] Stornierung fehlgeschlagen – retry in 10s.")
            if not schlafe(10): return
            continue

        time.sleep(2.0)

        # Neu buchen mit Court-Rotation im Retry
        ok = False
        for versuch in range(5):
            court_v = [2, 1][versuch % 2]
            neuer_slot["court"] = court_v
            if buche_slot(k, neuer_slot):
                ok = True
                break
            time.sleep(0.3 * (2 ** versuch))  # 0.3 → 0.6 → 1.2 → 2.4s

        if ok:
            gebuchter = az_get(k, "aktive_buchung")
            ist_ziel  = (neuer_start >= ziel_dt)
            senden(f"✅ <b>[{k}] {'🎯 Ziel erreicht!' if ist_ziel else 'Verschoben!'}</b>\n"
                   f"🕐 {naechster_von}–{naechster_bis} | Court {gebuchter['court'] if gebuchter else court_v}\n"
                   + ("" if ist_ziel else f"🔄 Weiter → {ziel_str} Uhr..."))
            if ist_ziel:
                az_set(k, "schiebe_aktiv", False)
                zeige_account_menue(k)
                return
        else:
            beende(f"❌ [{k}] Neubuchung nach Stornierung fehlgeschlagen!\n"
                   f"🆘 SOFORT manuell buchen:\n{BASE_URL}/padel?currentDate={datum_api}")
            return

    zeige_account_menue(k)

# ══════════════════════════════════════════════
#  FREITEXT-HANDLER (für Direkte Taktik Startzeit)
# ══════════════════════════════════════════════

def handle_text(k: str, text: str):
    """Verarbeitet Freitext – aktuell nur für Direkte Taktik Startzeit."""
    flow = az_get(k, "flow") if k else None
    if flow != "direkte_startzeit":
        zeige_account_auswahl()
        return

    m = re.match(r"^(\d{1,2}):(\d{2})$", text.strip())
    if not m:
        senden(f"❌ Ungültiges Format. Bitte als <b>HH:MM</b> eingeben, z.B. <b>13:00</b> oder <b>13:30</b>")
        return

    stunde, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= stunde <= 21 and minute in [0, 30]):
        senden(f"❌ Zeit muss auf 30-Min-Raster liegen (z.B. 13:00 oder 13:30)")
        return

    buchbar_ab = f"{stunde:02d}:{minute:02d}"
    az_set_multi(k, schiebe_buchbar_ab=buchbar_ab, schiebe_aktiv=True, flow=None)

    datum     = az_get(k, "schiebe_datum")
    dauer     = az_get(k, "schiebe_dauer")
    ziel      = az_get(k, "schiebe_ziel")
    datum_obj = datetime.strptime(datum, "%d.%m.%Y")
    tage_bis  = (datum_obj.date() - jetzt_lokal().date()).days

    senden(f"🎯 <b>[{k}] Direkte Taktik konfiguriert!</b>\n"
           f"📅 {datum}\n"
           f"⏰ Buchbar ab: {buchbar_ab} Uhr\n"
           f"🎯 Ziel: {ziel} Uhr ({dauer} Min)\n"
           f"📆 Datum in {tage_bis} Tagen\n\n"
           + (f"⏳ Warte noch {tage_bis - 7} Tag(e) bis 7-Tage-Fenster..."
              if tage_bis > 7 else f"🚀 Starte! Warte auf {buchbar_ab} Uhr..."))

    t = threading.Thread(target=schiebe_loop, args=(k,), daemon=True)
    t.start()
    az_set(k, "schiebe_thread", t)
    zeige_account_auswahl()

# ══════════════════════════════════════════════
#  TELEGRAM CALLBACKS
# ══════════════════════════════════════════════

def handle_callback(cb: dict):
    cid  = cb["id"]
    data = cb.get("data", "")
    beantworte_callback(cid)
    log.info(f"Callback: {data}")

    # Ebene 1: Account-Navigation
    if data in ("zurueck_accounts", "refresh_accounts"):
        zeige_account_auswahl(); return

    if data.startswith("acc_"):
        k = data[4:]
        if k not in acc:
            senden("❌ Unbekannter Account."); return
        set_flow_account(k)
        try: sync_buchung_vom_server(k)
        except Exception as e: log.warning(f"[{k}] Sync: {e}")
        zeige_account_menue(k); return

    # Account aus Suffix extrahieren (z.B. "menu_slots_SB")
    k = get_flow_account()
    for ak in ACCOUNTS:
        if data.endswith(f"_{ak}"):
            k    = ak
            data = data[:-(len(ak) + 1)]
            break

    if not k:
        senden("❓ Bitte zuerst einen Account wählen.")
        zeige_account_auswahl(); return

    # ── Ebene 2: Account-Menü ────────────────────────────────────────

    if data == "menu_slots":
        az_set(k, "flow", "slots_anfrage")
        senden(f"📅 <b>[{k}] Klassisch buchen</b>\nWelches Datum?",
               buttons=erstelle_datum_buttons("slots_datum"))

    elif data == "menu_schiebe":
        if az_get(k, "schiebe_aktiv"):
            senden(f"⚠️ [{k}] Schiebe-Taktik läuft bereits! Erst stoppen.")
            zeige_account_menue(k); return
        if az_get(k, "aktive_buchung"):
            senden(f"⚠️ [{k}] Aktive Buchung vorhanden.\nSchiebe nur ohne aktive Buchung möglich.")
            zeige_account_menue(k); return
        zeige_schiebe_modus_auswahl(k)

    elif data == "menu_status":
        snap    = az_snap(k, "aktive_buchung", "schiebe_aktiv", "schiebe_ziel",
                          "schiebe_datum", "schiebe_dauer", "schiebe_modus",
                          "schiebe_buchbar_ab", "person_id")
        aktiv   = snap["aktive_buchung"]
        schiebe = snap["schiebe_aktiv"]
        modus   = snap["schiebe_modus"] or ""
        modus_l = {"frueh": "Früh", "spaet": "Spät", "direkt": "Direkt"}.get(modus, "?")
        pid     = snap["person_id"] or "?"
        if aktiv:
            extra = ""
            if schiebe:
                extra = (f"🔄 Schiebe ({modus_l}) → Ziel {snap['schiebe_ziel']} | {snap['schiebe_dauer']} Min"
                         + (f"\n⏰ Buchbar ab: {snap['schiebe_buchbar_ab']}" if modus == "direkt" else ""))
            senden(f"📊 <b>[{k}] Aktive Buchung:</b>\n"
                   f"📅 {aktiv['datum_de']}\n"
                   f"🕐 {aktiv['fromTime']}–{aktiv['toTime']} Uhr\n"
                   f"🏟️ Court {aktiv['court']}\n"
                   f"🔖 ID: {aktiv.get('booking_id','?')}\n"
                   f"👤 Person: {pid}\n\n"
                   + (extra if extra else "ℹ️ Keine Schiebe aktiv."))
        else:
            senden(f"📊 <b>[{k}] Keine Buchung.</b>\n"
                   f"👤 Person: {pid}\n"
                   + (f"🔄 Schiebe ({modus_l}) läuft..." if schiebe else "Bot wartet."))
        zeige_account_menue(k)

    elif data == "menu_stopp":
        if az_get(k, "schiebe_aktiv"):
            az_set(k, "schiebe_aktiv", False)
            senden(f"⏹️ [{k}] Schiebe gestoppt.")
        else:
            senden("ℹ️ Keine Schiebe aktiv.")
        zeige_account_menue(k)

    elif data == "menu_storno":
        aktiv = az_get(k, "aktive_buchung")
        if not aktiv:
            senden(f"🗑️ [{k}] Keine Buchung vorhanden.")
            zeige_account_menue(k); return
        bid = aktiv.get("booking_id")
        senden(f"❓ <b>[{k}] Buchung wirklich stornieren?</b>\n\n"
               f"📅 {aktiv['datum_de']}\n"
               f"🕐 {aktiv['fromTime']}–{aktiv['toTime']} Uhr\n"
               f"🏟️ Court {aktiv['court']}\n"
               f"🔖 ID: {bid or '?'}\n\n"
               f"⚠️ Nicht rückgängig machbar!",
               buttons=[[
                   {"text": "✅ Ja, stornieren!", "callback_data": f"storno_bestaetigt_{k}"},
                   {"text": "❌ Abbrechen",       "callback_data": "abbrechen"},
               ]])

    elif data == "storno_bestaetigt":
        aktiv = az_get(k, "aktive_buchung")
        if not aktiv:
            senden(f"🗑️ [{k}] Keine Buchung mehr."); zeige_account_menue(k); return
        bid       = aktiv.get("booking_id")
        datum_api = aktiv.get("datum_api")
        if not bid:
            senden(f"❌ Keine ID – manuell: {BASE_URL}/padel"); zeige_account_menue(k); return
        if az_get(k, "schiebe_aktiv"):
            az_set(k, "schiebe_aktiv", False)
            senden("⏹️ Schiebe ebenfalls gestoppt.")
        if not stelle_session_sicher(k): return
        senden("⏳ Storniere...")
        ok = storniere_buchung(k, bid, datum_api)
        if ok:
            senden(f"✅ <b>[{k}] Storniert!</b>\n"
                   f"📅 {aktiv['datum_de']}\n"
                   f"🕐 {aktiv['fromTime']}–{aktiv['toTime']} | Court {aktiv['court']}")
        else:
            senden(f"❌ Stornierung fehlgeschlagen!\nManuell: {BASE_URL}/padel")
        zeige_account_auswahl()

    # ── Klassisch: Datum → Dauer → Slot-Auswahl ─────────────────────

    elif data.startswith("slots_datum_"):
        datum = data.replace("slots_datum_", "")
        az_set_multi(k, flow_datum=datum, flow="slots_dauer")
        senden(f"📅 [{k}] {datum}\nWie lange möchtest du spielen?",
               buttons=dauer_buttons("slots_dauer"))

    elif data.startswith("slots_dauer_"):
        dauer = int(data.replace("slots_dauer_", ""))
        datum = az_get(k, "flow_datum")
        if not datum:
            senden("❌ Fehler – nochmal starten."); zeige_account_menue(k); return
        az_set_multi(k, flow_dauer=dauer, flow=None)
        if not stelle_session_sicher(k):
            zeige_account_menue(k); return
        slots = berechne_freie_slots(k, datum, dauer)
        if not slots:
            senden(f"😔 [{k}] Keine freien {dauer}-Min-Slots am {datum}.")
            zeige_account_menue(k); return
        gesamt = len(slots)
        slot_buttons = []
        for s in slots[:10]:
            label = f"🏟️ Court {s['court']} | {s['fromTime']}–{s['toTime']}"
            key   = f"buch_{s['datum_api'].replace('/', '-')}_{s['court']}_{s['fromTime']}_{dauer}"
            slot_buttons.append([{"text": label, "callback_data": key}])
        slot_buttons.append([{"text": "❌ Abbrechen", "callback_data": "abbrechen"}])
        extra = f"\n<i>(+{gesamt-10} weitere)</i>" if gesamt > 10 else ""
        senden(f"✅ [{k}] Freie {dauer}-Min-Slots am {datum}:{extra}\n<i>Court 2 zuerst angezeigt</i>",
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
            to_t      = (datetime.strptime(from_t, "%H:%M") + timedelta(minutes=dauer)).strftime("%H:%M")
        except Exception as e:
            log.error(f"buch_ parse: {e} | {data}")
            senden("❌ Fehler – nochmal versuchen."); return
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
            to_t      = (datetime.strptime(from_t, "%H:%M") + timedelta(minutes=dauer)).strftime("%H:%M")
        except Exception as e:
            log.error(f"confirm_ parse: {e}")
            senden("❌ Fehler – nochmal."); return
        slot = {"court": court, "fromTime": from_t, "toTime": to_t,
                "dauer": dauer, "datum_api": datum_api, "datum_de": datum_de,
                "key": f"{datum_api}_{court}_{from_t}_{dauer}"}
        if not stelle_session_sicher(k):
            senden(f"❌ [{k}] Session-Fehler."); zeige_account_menue(k); return
        senden("⏳ Buche...")
        ok = buche_slot(k, slot)
        if ok:
            senden(f"✅ <b>[{k}] Gebucht!</b>\n"
                   f"📅 {datum_de}\n"
                   f"🕐 {from_t}–{to_t} Uhr ({dauer} Min)\n"
                   f"🏟️ Court {court}\n\nViel Spaß! 🎾")
        else:
            senden(f"❌ [{k}] Buchung fehlgeschlagen.",
                   buttons=[[
                       {"text": "🔄 Nochmal", "callback_data": original},
                       {"text": "↩️ Abbrechen", "callback_data": "abbrechen"},
                   ]])
        zeige_account_auswahl()

    # ── Ebene 3: Schiebe-Modus Setup ────────────────────────────────

    elif data.startswith("schiebe_modus_"):
        modus = data.replace("schiebe_modus_", "")
        az_set_multi(k, schiebe_modus=modus, flow="schiebe_setup_datum",
                     schiebe_buchbar_ab=None)  # Reset bei neuem Modus
        modus_name = {"frueh": "Früh-Methode", "spaet": "Spät-Taktik",
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

    elif data.startswith("schiebe_ziel_"):
        ziel  = data.replace("schiebe_ziel_", "")
        modus = az_get(k, "schiebe_modus") or "frueh"
        az_set(k, "schiebe_ziel", ziel)

        if modus == "direkt":
            # Freitext für Startzeit anfordern
            az_set(k, "flow", "direkte_startzeit")
            datum = az_get(k, "schiebe_datum")
            dauer = az_get(k, "schiebe_dauer")
            senden(f"🎯 <b>[{k}] Direkte Taktik</b>\n"
                   f"📅 {datum} | {dauer} Min | Ziel: {ziel} Uhr\n\n"
                   f"⏰ <b>Ab wann ist buchbar?</b>\n"
                   f"Bitte Uhrzeit tippen (30-Min-Raster, z.B. <b>13:00</b> oder <b>07:30</b>):")
        else:
            # Früh oder Spät: direkt starten
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
                   + (f"⏳ Warte noch {tage_bis - 7} Tag(e) bis 7-Tage-Fenster..."
                      if tage_bis > 7 else "🚀 Starte jetzt!"))
            t = threading.Thread(target=schiebe_loop, args=(k,), daemon=True)
            t.start()
            az_set(k, "schiebe_thread", t)
            zeige_account_auswahl()

    elif data == "abbrechen":
        if k: az_set_multi(k, flow=None, flow_datum=None, flow_dauer=None)
        senden("↩️ Abgebrochen.")
        zeige_account_auswahl()

    else:
        log.warning(f"Unbekannter Callback: {data}")
        zeige_account_auswahl()

# ══════════════════════════════════════════════
#  TELEGRAM POLLING
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
                    text = msg.get("text", "").strip()
                    # Freitext-Handler: Direkte Taktik Startzeit
                    k_flow = get_flow_account()
                    if k_flow and az_get(k_flow, "flow") == "direkte_startzeit":
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
#  START
# ══════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=" * 60)
    log.info("🎾 Padel Bot v8.4 – Dual-Account | 3 Schiebe-Modi | Court-2-Prio")
    log.info(f"   SB : {ACCOUNTS['SB']['email']}")
    log.info(f"   KS : {ACCOUNTS['KS']['email']}")
    log.info(f"   Court-Priorität : 2 → 1 (automatischer Fallback)")
    log.info(f"   Schiebe         : {SCHIEBE_MINUTEN_VOR} Min vor Slot-Ende")
    log.info(f"   Aggressive      : {AGGRESSIVE_TIMEOUT}s @ {AGGRESSIVE_INTERVAL}s Interval")
    log.info("=" * 60)

    # FIX: Beim Start schiebe_aktiv zurücksetzen wenn kein Thread läuft.
    # Verhindert dass nach Neustart der Bot dauerhaft "frei" anzeigt
    # weil schiebe_aktiv=True im Speicher festhängt (was hier nie passiert,
    # da acc neu erstellt wird – aber als Sicherheitsnetz für spätere Persistenz).
    for k in ACCOUNTS:
        thread = acc[k].get("schiebe_thread")
        if az_get(k, "schiebe_aktiv") and (not thread or not thread.is_alive()):
            log.warning(f"[{k}] Startup: schiebe_aktiv=True ohne Thread – korrigiere.")
            az_set(k, "schiebe_aktiv", False)

    fehler = []
    for k in ACCOUNTS:
        if not einloggen(k):
            fehler.append(k)
            log.error(f"❌ Login [{k}] fehlgeschlagen!")
        else:
            pid = az_get(k, "person_id")
            log.info(f"   [{k}] PERSON_ID: {pid or 'NICHT GEFUNDEN'}")

    if len(fehler) == 2:
        log.error("❌ Beide Accounts fehlgeschlagen – Bot beendet.")
        exit(1)
    elif fehler:
        senden(f"⚠️ Login für {', '.join(fehler)} fehlgeschlagen!")

    senden("🎾 <b>Padel Bot v8.4 gestartet!</b>\n\n"
           "Dual-Account  |  3 Schiebe-Modi  |  Court 2 bevorzugt")
    zeige_account_auswahl()

    threading.Thread(target=telegram_loop, daemon=True).start()

    log.info("✅ Bot läuft. Strg+C zum Beenden.")
    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        log.info("Bot beendet.")
        senden("⏹️ Padel Bot v7 wurde beendet.")
