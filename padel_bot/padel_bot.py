#!/usr/bin/env python3
"""Padel Bot V17 SPAM-COMMIT ÜBERALL

NEU V17 (Spam-Commit in ALLE Renn-Pfade – gemeinsamer, getesteter Kern):
        Der V16-Spam-Commit (Weiter-Dauerfeuer → beim Aufspringen sofort buchen)
        steckte nur im Freischaltungs-Blitz. V17 zieht ihn in den gemeinsamen
        Kern _spam_weiter_commit() und wendet ihn zusätzlich an:
          • SNIPER PHASE 1 (Lauern): statt alle 0,25 s eine VOLLE Buchung (schwer,
            Bann-Risiko) jetzt leichtes "Weiter"-Antippen auf demselben Token –
            solange der Fremde drin ist bleibt es auf s1 (= deine "belegter Slot"-
            Aufnahme!), storniert er → s2 → sofort buchen. Schneller UND schonender.
          • SNIPER PHASE 2 (Blitz aufs frei werdende Feld): wie der 07:00-Blitz.
          • SCHIEBE-REBOOK (Storno→Neubuchung): Spam bis der Selbst-Konflikt mit
            der gerade stornierten eigenen Buchung weg ist. Der komplette bewährte
            Ablauf inkl. ROLLBACK bleibt als Fallback unverändert.
          • SAFE-ÜBERGABE (_safe_grab): Spam nach dem Storno des Partners.
        Jede Stelle fällt bei Token/Flow-Problem AUTOMATISCH auf ihren bisherigen
        Weg zurück → kann nie schlechter sein. Schalter SPAM_COMMIT_AKTIV=False
        gibt exakt das V15/klassische Verhalten. Direkt/Duo/3h/Safe-Initial liefen
        schon über den Freischaltungs-Blitz (unverändert). Kern durch Realdaten
        (HAR) + Unit-/Ablauf-Tests abgesichert.

NEU V16 (SPAM-COMMIT – belegt durch HAR-Aufnahme freier/belegter Slot 10.07.):
        Kern-Erkenntnis aus den echten Server-Antworten: Der "Weiter"-Schritt
        (_eventId=next) lässt sich auf demselben Token eXs1 BELIEBIG OFT feuern.
        Der Server antwortet mit einem 302-Redirect, dessen Ziel verrät alles:
          • Slot ZU / belegt → Location …execution=eXs1  (bleibt auf Schritt 1)
          • Slot AUF/buchbar  → Location …execution=eXs2  (Bestätigungsseite)
        NEUE TAKTIK (_direkt_blitz, Freischaltungs-Blitz): Token EINMAL holen,
        dann "Weiter" im Dauerfeuer. Der Redirect wird NICHT verfolgt (nur die
        Location gelesen → die 6–15 KB-Seite wird im kritischen Fenster nie
        geladen). In der Millisekunde, in der die Location auf eXs2 springt,
        feuert sofort der Commit. KEIN r1-Neuladen mehr pro Welle → viel mehr
        Buchungs-Schüsse in der ersten Sekunde nach Freischaltung.
        SICHER: Bei jedem unerwarteten Ergebnis (Token tot, komische Antwort,
        Timeout) fällt der Court automatisch auf den bewährten V15-Burst zurück
        → kann nie schlechter als V15 sein. Konflikt-Stopp (3× fremd vergeben)
        bleibt als DoS-Schutz. Schalter SPAM_COMMIT_AKTIV=False = exakt V15.
        Zeitsync bleibt AUS (V15). Betrifft nur den Freischaltungs-Blitz; Schiebe,
        Sniper, Safe, Telegram unverändert.

NEU V15 (BLITZ-SPEED – reagiert auf Log 10.07. 07:00, Slot an Rival verloren):
        Anlass: Der Commit landete am Freischalt-Punkt (07:00:00) minimal ZU
        SPÄT und der Slot war schon weg ("Konflikt mit bestehendem Termin").
        Im Log zwei messbare Bremsen:
          1. Das r2-Prefire startete bei T-250ms, brauchte aber ~292ms → es kam
             erst ~40ms NACH dem Freischalt-Punkt zurück und verzögerte dadurch
             den eigentlichen Commit um ~40ms. FIX: R2_PREFIRE_MS 250 → 350, das
             r2 ist damit VOR T-0 fertig und der Commit feuert exakt auf T-0.
          2. Die Serveruhr-Messung meldete einen einzelnen, sehr großen Offset
             von -606ms → der Bot feuerte über eine halbe Sekunde SPÄTER. Bei
             zwei internet-synchronisierten Uhren (HA + eBusy) ist so ein Wert
             praktisch unmöglich = Mess-Rauschen (Date-Header hat nur Sekunden-
             Auflösung). ENTSCHEIDUNG: Zeitsync ist jetzt standardmäßig AUS
             (ZEITSYNC_AKTIV=False) → der Blitz feuert auf die lokale, per NTP
             genaue Uhr (wie vor v12, lief problemlos). Die Messung selbst wurde
             trotzdem robuster gemacht (Median aus MEHREREN Sekundensprüngen,
             Verwerfen bei Streuung >350ms, alle Roh-Samples ins Log) – falls
             man sie je testen will, genügt ZEITSYNC_AKTIV=True.
          3. BLITZ_FIRE_OFFSET_MS ist weiter 0 (Commit feuert AUF T-0). Wer den
             letzten Tick gegen einen sehr schnellen Rival gewinnen will, kann
             ihn EXPERIMENTELL leicht negativ setzen (z.B. -60), dann feuert der
             Commit knapp vor T-0 und ARRIVIERT ~zur Freischaltung. Risiko: zu
             früh → Server lehnt ab. Default bleibt 0 (kein Risiko).
        Sonst KEINE Änderung – alle V14-Fixes/Struktur + gleiche Request-Zahl.

NEU V14 (SAUBER-REFACTOR – Verhalten & Timing IDENTISCH zu V13 GODMODE 2.1):
        Reines Aufräumen: jede duplizierte Logik hat jetzt EINE Quelle. Kein
        Feature geändert, kein Request mehr oder weniger im Happy-Path.
        DEDUP 1 – r2-Payload: der Form-Body des r2-Requests stand 3× identisch
           im Code (buche_slot, burst_r2_r3, pre_fire_r2) → _r2_data(). Auch
           execution-Parsing (_parse_execution), Buchungs-ID-Parsing
           (_parse_booking_id), Fehlerindiz-Check (_hat_fehler_indiz) und
           POST-Header (_post_header) sind jetzt je EINE Funktion.
        DEDUP 2 – my-bookings-Parser: Sync + Verify hatten je eine eigene Kopie
           von total-pages-Parsing, Karten-Suche und Karten-Parsing →
           _mb_hole_karten() + _parse_buchungskarte() + _parse_total_pages() +
           _karte_booking_id(). Sync/Verify sind nur noch dünne Filter darüber.
           frueh_stopp-Callback erhält das alte Verhalten "beim Treffer
           aufhören zu blättern" (keine zusätzlichen Requests).
        DEDUP 3 – Wizard-Bausteine: Duo/Safe/3h hatten die 2-Account-Auswahl
           (Start/Abbrechen/Account A/Account B) 3× kopiert → _paar_start,
           _paar_cancel, _paar_pa, _paar_pb. Die HH:MM-Startzeit-Validierung
           stand 4× im Code → _parse_startzeit(). Die flow-spezifischen
           Schritte (Datum/Court/Ziel/Strategie) bleiben bewusst getrennt.
        DEDUP 4 – Kleinkram: warte_bis_genau (2× Closure → Modul-Funktion),
           schlafe/beende-Closures (→ _schlafe_solange/_schiebe_beende),
           Sniper-Stopp-Block (7× → _sniper_stopp), Restzeit-Formatierung
           (5× → _format_restzeit), WOCHENTAGE_LANG = Alias statt Kopie.
        TOTER CODE RAUS: buche_slot verify_person_id=False (SPEED-Zweig) wurde
           nirgends mehr aufgerufen (Bursts laufen über burst_r2_r3) → entfernt.
           Ungenutzte Variablen entfernt (pyflakes ist jetzt komplett sauber).

NEU V13-GODMODE-2.1 (Stabilitäts-Fixes – Happy-Path & Timing UNVERÄNDERT):
        FIX A (Sniper→Schiebe stirbt still): trigger_phase3 übernimmt jetzt den
           laufenden Thread als schiebe_thread. Vorher konnte ein toter ALTER
           Schiebe-Thread auf dem Account dazu führen, dass Account-Sync bzw.
           Statuslabel ("🔄 Aktualisieren") schiebe_aktiv=False setzten → die
           Sniper-Fortsetzung (Phase 3) stoppte kommentarlos mitten im Schieben.
        FIX B (booking_id=None): Vor jedem Schiebe-Storno wird eine fehlende
           booking_id aus my-bookings nachgeladen. Vorher galt die EIGENE alte
           Buchung im Ziel-Check als "fremd" (Ziel überlappt die eigene immer →
           falscher Abbruch "fremd belegt") bzw. der Storno lief gegen
           /bookings/None/cancel. Klappt das Nachladen nicht: Buchung BEHALTEN
           und sauber stoppen.
        FIX C (Storno-Falsch-Positiv): Der Server kann beim Cancel 200 liefern,
           OHNE wirklich zu stornieren (Status-Code allein ist kein Beweis).
           Schlägt die Neubuchung danach komplett fehl, wird VOR dem Rollback
           geprüft, ob die alte Buchung noch in my-bookings steht. Steht sie
           noch: Zustand wiederherstellen + stoppen, statt sinnlosem Rollback-
           Selbst-Konflikt und Fehlalarm. Gleiches Netz im Safe-Übergabe-Pfad.
        FIX D (Safe-Modus): _safe_storno ohne booking_id meldet jetzt Fehlschlag
           statt Erfolg (vorher blitzte der Partner in den Konflikt, während die
           alte Buchung noch stand); vorher wird die ID nachzuladen versucht.
           _safe_blitz_hartnaeckig bestätigt am Ende den KONKRETEN Ziel-Slot per
           my-bookings (vorher zählte irgendeine aktive Buchung als Erfolg).
        FIX E (Telegram): hole_updates() pausiert 1s bei Netzwerkfehler (vorher
           Hot-Loop ohne Sleep bei totem Netz). Callback-Routing strippt das
           Account-Suffix nur noch bei echten Account-Menü-Buttons (vorher
           kollidierten numerische Account-Labels wie "1"/"90" mit Callbacks wie
           "schiebe_court_1" → falsches Routing).
        FIX F (Verify nach 401): verifiziere_slot_via_my_bookings holt
           total-pages nach dem Re-Login frisch (vorher wurde die 401-Antwort
           geparst → immer nur Seite 1 durchsucht).
        TUNING 1: SNIPER_PHASE1_INTERVAL 0.1s → 0.25s (Server-Schonung; ein
           fremdes Storno passiert nicht auf die Millisekunde, Bann-Risiko sinkt).
        TUNING 2: Wetter-Fehlversuche werden 10 Min negativ gecacht → kein
           8s-Hänger pro Menü-Render mehr, wenn die Wetter-API klemmt.

NEU V13-GODMODE-2.0 (Schiebe "bekannte Uhrzeit": Lücke Storno→Neubuchung ~halbiert):
        Anlass: Wunsch, das offene Fenster zwischen Storno und Neubuchung beim
        Schieben so klein zu machen, dass kein fremder Sniper reingrätscht.
        HEBEL 1 – r2-PREFIRE VOR DEM STORNO: Bisher wurde vor dem Storno nur r1
           (Formular/Token) vorgewärmt; nach dem Storno mussten r2+r3 raus
           (~270ms). Jetzt wird auch r2 schon gefeuert, SOLANGE DIE ALTE BUCHUNG
           NOCH HÄLT (Server lässt den Flow trotz Überlappung mit der eigenen
           Altbuchung bis zum Commit laufen). Nach dem Storno fehlt nur noch das
           r3-Commit (~100ms). Lehnt der Server das frühe r2 ab → frischer Token
           + voller r2+r3-Burst wie bisher (kein Risiko).
        HEBEL 2 – STORNO-DIALOG VORLADEN: Der Storno besteht aus 2 GETs (Dialog
           laden + bestätigen). Der Dialog wird jetzt VOR dem kritischen Moment
           geladen; im Fenster bleibt nur der eine Bestätigungs-Request. Der
           Confirm ist stateless (fester CONFIRM_KEY). Storno-Retries nutzen
           weiter den vollen, robusten Storniere-Ablauf.
        ERGEBNIS: kritisches Fenster ~4 Requests → ~2 Requests (~300–500ms →
           ~100–150ms). Betrifft NUR den Blitz-Schiebe-Pfad (_schiebe_phase3);
           Safe-Modus, Sniper, Direkt-Blitz, Telegram unverändert.
        SCHUTZ 1 – ZIEL-CHECK VOR STORNO: Vor jedem Schiebe-Storno wird der
           Court-Plan geprüft. Liegt im Ziel-Slot eine FREMDE Buchung (eigene
           alte zählt nicht), wird NICHT storniert → alte Buchung bleibt sicher,
           statt am Ende mit nichts dazustehen. Fail-open: Check-Fehler
           blockieren das Schieben nie.
        SCHUTZ 2 – ROLLBACK: Scheitert die Neubuchung trotz allem, holt der Bot
           sofort die gerade stornierte alte Buchung zurück (10 Versuche),
           bevor er "manuell buchen!" ruft. Nie mehr mit leeren Händen.
        SCHUTZ 3 – SESSION-HÄRTUNG (Kinderkrankheiten): my-bookings liefert bei
           toter Session 200 OHNE Karten statt 401 → Verify/Sync meldeten
           fälschlich "nicht gebucht"/"Keine aktive Buchung" (siehe 08.07.
           13:02). Jetzt: leeres Ergebnis ohne sichtbare Buchungskarten →
           Login-Check → Re-Login → 1× wiederholen; Sync löscht den lokalen
           Buchungs-Status dann NICHT mehr.
        HINWEIS Selbst-Konflikt: Direkt nach eigenem Storno kann der Server die
           alte (überlappende) Buchung noch ~0,3–1s "sehen" → Welle 1 kann mit
           "Konflikt mit bestehendem Termin" abblitzen (Log 08.07. 16:16). Das
           ist normal; die Wellen 2–6 + buche_slot-Fallback laufen im
           Schiebe-Pfad bei Konflikt bewusst WEITER (kein Abbruch wie beim
           Freischaltungs-Blitz, wo Konflikt = fremd-vergeben bedeutet).
        Baut auf V12 GODMODE auf (r2-Prefire-Baustein, Konflikt-Erkennung,
        Zeitsync, Diagnose-Log) inkl. V11-Stornofix.

NEU V12-GODMODE (Anti-Rival-Blitz – Kern: schneller committen als fremde Bots):
        Anlass: 08.07. 13:00 – fremder Bot hat den Slot innerhalb von <350ms
        nach Freischaltung weggeschnappt (unser r2+r3 brauchte ~350–500ms).
        1. r2-PREFIRE: r2 (_eventId=next) wird bereits R2_PREFIRE_MS vor T-0
           gefeuert (gleiche Idee wie Pre-Warm r1 bei T-10s). Welle 0 schickt
           bei T-0 nur noch das r3-Commit → Commit landet ~50–150ms nach
           Freischaltung statt ~350–500ms. Lehnt der Server das frühe r2 ab:
           automatischer Fallback auf den bewährten vollen r2+r3-Burst.
        2. ZEITSYNC: Serveruhr-Offset wird vor jedem Blitz über den Date-Header
           gemessen (12 leichte Requests, ~2s). Geht die Serveruhr vor/nach,
           verschiebt sich der Feuerzeitpunkt entsprechend (Clamp ±2s,
           unplausible Messungen werden ignoriert → Verhalten wie bisher).
        3. KONFLIKT-ERKENNUNG: "Konflikt mit einem bestehenden Termin" gilt
           jetzt als harter Fehlschlag (vorher ok=True → 2 Minuten sinnloses
           Nachfeuern, siehe Log 08.07. 13:00–13:02). Burst-Wellen brechen nach
           2 Konflikten ab, der Hartnäckig-Loop nach 3 in Folge – mit
           Telegram-Meldung "Slot wurde von jemand anderem gebucht".
        4. ERFOLGS-TEXT: "Ihre Buchung war erfolgreich" in r3 wird erkannt; bei
           Erfolgstext + my-bookings-Miss wird die Verifikation 2× kurz
           wiederholt (my-bookings-Lag ≠ verlorener Slot). Eigentums-Check
           via my-bookings bleibt in jedem Fall Pflicht.
        5. DIAGNOSE: Burst-r3-Log ohne <style>-Blöcke und mit 1200 Zeichen →
           Modal-Titel ist künftig immer lesbar.
        Enthält den V11-Stornofix (Session-Refresh vor Safe-Storno).

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
from email.utils import parsedate_to_datetime
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
            # V2.1: Fehlversuch negativ cachen – sonst hängt jeder Menü-Render
            # erneut bis zu 8s, wenn die Wetter-API klemmt.
            with _wetter_cache_lock:
                _wetter_cache[_cache_key] = (_now, "")
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
        with _wetter_cache_lock:
            _wetter_cache[_cache_key] = (_now, "")
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
SNIPER_PHASE1_INTERVAL = 0.25    # s: Hammer-Intervall Phase 1. V2.1: 0.1→0.25 (Server-Schonung, Bann-Risiko)
SNIPER_DEADLINE_BUFFER = 60      # s: Abbruch X Sek nach fremder Endzeit

# Direkt-Blitz
BLITZ_PREWARM_SECONDS  = 10      # s: Pre-Warm r1 bei T-10s, Token cachen
BLITZ_FIRE_OFFSET_MS   = 0       # ms: Feuer-Offset relativ buchbar_dt. 0 = Commit AUF T-0.
                                 # V15: darf EXPERIMENTELL leicht negativ sein (z.B. -60),
                                 # dann feuert der Commit knapp VOR T-0 und arriviert ~zur
                                 # Freischaltung → gegen sehr schnelle Rivalen. Zu früh =
                                 # Server lehnt ab → Fallback-Wellen. Nur bewusst testen!
MULTI_SHOT_COUNT       = 5       # Anzahl Burst-Wellen nach erstem Miss
MULTI_SHOT_GAP_MS      = 150     # ms: Pause zwischen Bursts
PHASE1_HANDOFF_MARGIN  = 180     # s: Direkt-Modus wacht so viel vor Freischaltung auf (Phase 2 macht Login+Pre-Warm+Blitz)

# V16 SPAM-COMMIT (belegt durch HAR-Aufnahme 10.07.):
#   "Weiter" (_eventId=next) auf demselben eXs1-Token beliebig oft feuerbar:
#     - Slot ZU / belegt  → 302 Redirect zurück auf …execution=eXs1 (bleibt hängen)
#     - Slot AUF/buchbar   → 302 Redirect auf …execution=eXs2 (Bestätigungsseite)
#   → Token EINMAL holen, "Weiter" im Dauerfeuer, beim Sprung auf s2 SOFORT commit.
#   Kein r1-Neuladen pro Welle. Bei jedem Problem automatischer Rückfall auf den
#   bewährten V15-Burst (kann nie schlechter sein). Redirect wird NICHT verfolgt
#   (nur Location gelesen) → kein Laden der 6–15 KB-Seite im kritischen Fenster.
SPAM_COMMIT_AKTIV      = True    # False = exakt V15-Verhalten (klassischer Burst)
SPAM_FENSTER_VOR_MS    = 800     # ms: so früh vor T-0 mit dem "Weiter"-Dauerfeuer beginnen
SPAM_NEXT_INTERVAL     = 0.05    # s: Pause zwischen "Weiter"-Versuchen, solange der Slot zu ist
SPAM_DEADLINE_S        = 8       # s: nach T-0 so lange spammen, dann Rückfall/Abbruch
SPAM_KONFLIKT_STOP     = 3       # commit-Konflikte in Folge (fremd vergeben) → stoppen (DoS-Schutz)

# GODMODE-Blitz (V12): schneller als fremde Bots, ohne mehr Requests zu feuern
R2_PREFIRE_MS          = 350     # ms: r2 SO VIEL vor T-0 feuern → Welle 0 = nur r3-Commit. 0 = aus.
                                 # V15: 250→350, damit das r2 (~290ms Laufzeit, Log 10.07.) VOR
                                 # T-0 fertig ist und den Commit nicht mehr verzögert.
# V15: Serveruhr-Sync ist standardmäßig AUS. Die Date-Header-Messung hat nur
# Sekunden-Auflösung und streute im Log 10.07. bis -606ms (bei NTP-Uhren = HA +
# eBusy praktisch unmöglich → Mess-Rauschen), was den Blitz 0,6s ausbremste.
# Ohne Sync feuert der Bot auf die lokale, per NTP genaue Uhr (wie vor v12).
# Wer die (jetzt robustere, median-basierte) Messung testen will: auf True stellen
# und die "Zeitsync-Samples"-Logzeilen über mehrere Tage beobachten.
ZEITSYNC_AKTIV         = False   # Serveruhr-Offset messen+korrigieren? (V15: AUS, siehe oben)
ZEITSYNC_MAX_OFFSET_S  = 2.0     # s: größere Messwerte gelten als unplausibel → keine Korrektur
ZEITSYNC_MAX_STREUUNG_S = 0.35   # s: streuen die Einzelmessungen weiter → Messung verworfen (V15)
KONFLIKT_TEXT          = "konflikt mit einem bestehenden termin"  # exakter Server-Text (lowercase)
ERFOLG_TEXTE           = ("buchung war erfolgreich", "aktion erfolgreich")
KONFLIKT_STOP_N        = 3       # Hartnäckig-Loop: nach so vielen Konflikten in Folge stoppen

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

# Safe-Modus: ZWEI Accounts wechseln sich EINEN Slot auf EINEM Court ab.
# Nie bucht der Account neu, der gerade storniert hat – immer der freie Partner.
_safe = {"flow": None, "acc_a": None, "acc_b": None, "court": None,
         "datum": None, "ziel": None, "strategie": None}
_safe_lock = threading.Lock()
SAFE_UEBERLAPP_MIN = 30    # Übergabe: Überlappung des nächsten Slots (wie klassisch)
SAFE_CANCEL_DELAY_SEC = 300  # Leapfrog: Wartezeit, bevor der alte Halter storniert (kein Stress)

def _safe_reset():
    with _safe_lock:
        _safe.update(flow=None, acc_a=None, acc_b=None, court=None,
                     datum=None, ziel=None, strategie=None)

def _safe_awaiting_text() -> bool:
    with _safe_lock:
        return _safe["flow"] == "startzeit"

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
        # V2.1 FIX E: kurz pausieren – sonst dreht telegram_loop bei totem Netz
        # als Hot-Loop (der Fehler wird hier geschluckt, außen gibt es kein sleep).
        time.sleep(1)
        return []

# ══════════════════════════════════════════════
# MENÜ-FUNKTIONEN
# ══════════════════════════════════════════════

WOCHENTAGE      = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
WOCHENTAGE_LANG = WOCHENTAGE   # V14: identischer Inhalt – Alias statt Kopie

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
        buttons.append([{"text": "🛡️ Safe-Modus (2 Accounts, 1 Slot)",
                         "callback_data": "safe_start"}])

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

# ══════════════════════════════════════════════
# V14: GEMEINSAME BAUSTEINE (eine Quelle statt Kopien)
# ══════════════════════════════════════════════

FEHLER_INDIZIEN = ("fehler", "error", "nicht möglich")

def _hat_fehler_indiz(text_lower: str) -> bool:
    """True, wenn der (lowercase) Antwort-Body ein Server-Fehlerindiz enthält."""
    return any(w in text_lower for w in FEHLER_INDIZIEN)

def _post_header(csrf_t: str, datum_api: str) -> dict:
    """AJAX-POST-Header für den Buchungs-Flow (r2/r3) – vorher 4× dupliziert."""
    return {**_ajax_header(csrf_t, referer=f"{BASE_URL}/padel?currentDate={datum_api}"),
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "origin": BASE_URL}

def _r2_data(slot: dict, court, person_id: str, csrf_t: str) -> str:
    """Form-Body des r2-Requests (_eventId=next) – EINE Quelle für buche_slot,
    burst_r2_r3 und pre_fire_r2 (vorher 3× identisch dupliziert)."""
    return (f"purchaseTemplate.repetition.date={slot['datum_de']}"
            f"&purchaseTemplate.repetition.fromTime={slot['fromTime'].replace(':', '%3A')}"
            f"&purchaseTemplate.repetition.toTime={slot['toTime'].replace(':', '%3A')}"
            f"&bookingModel.courts%5B0%5D={court}"
            f"&purchaseTemplate.court={court}"
            f"&purchaseTemplate.person={person_id}"
            f"&purchaseTemplate.bookingType={BOOKING_TYPE}"
            f"&_csrf={csrf_t}")

def _parse_execution(text: str, default: str) -> str:
    """execution-Token (eXsY) aus einer Flow-Antwort ziehen, sonst default."""
    m = re.search(r"execution=(e\d+s\d+)", text)
    return m.group(1) if m else default

_BOOKING_ID_PATTERNS = (r'"bookingId"\s*:\s*(\d+)', r'/bookings/(\d+)', r'booking[=_](\d+)')

def _parse_booking_id(text: str) -> int | None:
    """Buchungs-ID aus einer r3-Antwort ziehen (drei bekannte Muster)."""
    for pat in _BOOKING_ID_PATTERNS:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return None

def _format_restzeit(sek: float) -> str:
    """Sekunden → 'xT xh xmin' / 'xh xmin' / 'xmin' (vorher 5× dupliziert)."""
    sek  = max(0, int(sek))
    tage = sek // 86400
    std  = (sek % 86400) // 3600
    minu = (sek % 3600) // 60
    if tage > 0:
        return f"{tage}T {std}h {minu}min"
    if std > 0:
        return f"{std}h {minu}min"
    return f"{minu}min"

def warte_bis_genau(ziel_dt: datetime):
    """Schläft präzise bis ziel_dt (lokale Berlin-Zeit, naiv); die letzten
    ~200ms Busy-Loop für Millisekunden-Präzision (vorher 2× als Closure)."""
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

def _schlafe_solange(aktiv_fn, sek: float) -> bool:
    """Schläft in 1s-Häppchen; bricht ab, sobald aktiv_fn() False liefert.
    True = voll geschlafen, False = abgebrochen (vorher 4× als Closure)."""
    ende = time.time() + sek
    while time.time() < ende:
        if not aktiv_fn():
            return False
        time.sleep(min(1, max(0, ende - time.time())))
    return True

def _parse_startzeit(text: str) -> str | None:
    """Getippte Buchbar-ab-Zeit validieren (HH:MM, 30-Min-Raster). Sendet bei
    ungültiger Eingabe selbst die Fehlermeldung (vorher 4× dupliziert)."""
    m = re.match(r"^(\d{1,2}):(\d{2})$", text.strip())
    if not m:
        senden("❌ Ungültiges Format. Bitte als <b>HH:MM</b> eingeben, z.B. <b>17:30</b>")
        return None
    stunde, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= stunde <= 21 and minute in (0, 30)):
        senden("❌ Zeit muss auf 30-Min-Raster liegen (z.B. 17:00 oder 17:30)")
        return None
    return f"{stunde:02d}:{minute:02d}"

def _schiebe_beende(k: str, msg: str = ""):
    """Schiebe-Ende: Flag aus, optionale Meldung, Account-Menü (vorher 2× Closure)."""
    az_set(k, "schiebe_aktiv", False)
    if msg:
        senden(msg)
    zeige_account_menue(k)

def _sniper_stopp(k: str, msg: str = ""):
    """Sniper-Ende: optionale Meldung, Flag aus, Account-Menü (vorher 7× Block)."""
    if msg:
        senden(msg)
    az_set(k, "sniper_aktiv", False)
    zeige_account_menue(k)

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


def _ziel_slot_fremd_belegt(k: str, court: int, von: str, bis: str,
                            datum_api: str, eigene_booking_id: int | None) -> str | None:
    """GODMODE2 (Schutz): prüft den Court-Plan, ob im Ziel-Slot [von,bis] auf
    `court` eine FREMDE Buchung/Blockung liegt (die eigene alte Buchung wird per
    booking_id ignoriert). Liefert die Fremd-Zeiten als Text oder None (= frei).
    Fail-open: bei Fehler/leerem Plan None → ein kaputter Check darf das
    Schieben niemals blockieren, nur eine POSITIVE Fremd-Belegung stoppt es."""
    try:
        res = hole_reservierungen(k, datum_api)
        for r in res:
            if r.get("court") != court:
                continue
            if eigene_booking_id and (r.get("booking") == eigene_booking_id
                                      or r.get("bookingOrBlockingId") == eigene_booking_id):
                continue
            if _slots_ueberlappen(r.get("fromTime", "00:00"),
                                  r.get("toTime", "00:00"), von, bis):
                return f"{r.get('fromTime')}–{r.get('toTime')}"
    except Exception as e:
        log.warning(f"[{k}] Ziel-Slot-Check: {e}")
    return None

# ══════════════════════════════════════════════
# BUCHUNG
# ══════════════════════════════════════════════

def buche_slot(k: str, slot: dict) -> bool:
    """
    STRIKT (R10): bucht über den 3-Schritte-Flow (r1 Formular → r2 next →
    r3 commit) und verifiziert das EIGENTUM ausschließlich über
    /user/my-bookings. Genutzt für Sniper Phase 1, normales Buchen, Fallbacks.
    (V14: der tote SPEED-Zweig verify_person_id=False wurde entfernt – Bursts
    laufen über burst_r2_r3/burst_commit_only mit Caller-Verifikation.)
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
    _KONFLIKT_FLAG.pop(f"{k}:{court}", None)
    h  = _ajax_header(csrf_t, referer=f"{BASE_URL}/padel?currentDate={datum_api}")
    hp = _post_header(csrf_t, datum_api)
    try:
        r1 = http.get(f"{BASE_URL}/court-single-booking-flow", headers=h,
                      params={"module": MODULE, "court": court, "courts": "1,2",
                              "fromTime": from_t, "toTime": to_t, "date": datum_api},
                      timeout=10)
        execution = _parse_execution(r1.text, "e1s1")

        if not person_id:
            person_id = extrahiere_person_id(r1.text)
            if person_id:
                az_set(k, "person_id", person_id)

        r2 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                       params={"execution": execution, "_eventId": "next"},
                       data=_r2_data(slot, court, person_id, csrf_t),
                       timeout=10)
        exec2 = _parse_execution(r2.text, execution.replace("s1", "s2"))

        r3 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                       params={"execution": exec2, "_eventId": "commit"},
                       data=f"purchaseTemplate.comment=&_csrf={csrf_t}",
                       timeout=10)

        if r3.status_code not in [200, 302]:
            return False
        low3 = r3.text.lower()
        if KONFLIKT_TEXT in low3:
            _KONFLIKT_FLAG[f"{k}:{court}"] = True
            log.warning(f"⛔ [{k}] Court {court} {from_t}–{to_t}: Konflikt mit "
                        f"bestehendem Termin – Slot vergeben.")
            return False
        if _hat_fehler_indiz(low3):
            log.warning(f"[{k}] Buchung: Server-Fehler")
            return False

        booking_id = _parse_booking_id(r3.text)

        # Verifizierung NUR über my-bookings (EIGENTUM!), NICHT über den Court-Plan.
        # hole_reservierungen()/​/padel liefert ALLE Buchungen+Blockungen des Courts –
        # ein fremd belegter Slot ginge dort als "verifiziert" durch und dessen FREMDE
        # booking_id würde als unsere gespeichert (→ späteres Storno = 403-Endlosschleife,
        # siehe Fehler1.log ID 19811). /user/my-bookings enthält ausschließlich EIGENE
        # Buchungen. Kurzer Retry gegen my-bookings-Lag (verhindert Falsch-Negativ).
        expected = {**slot, "court": int(court), "fromTime": from_t, "toTime": to_t}
        verifiziert_dict = None
        for _vv in range(3):
            verifiziert_dict = verifiziere_slot_via_my_bookings(k, expected)
            if verifiziert_dict:
                break
            time.sleep(1.0)

        if not verifiziert_dict:
            log.warning(f"[{k}] ⚠️ Buchung NICHT in eigenen my-bookings – "
                        f"fremder Slot oder Fehlschlag (r3-ID war {booking_id}).")
            az_set(k, "aktive_buchung", None)
            return False

        az_set(k, "aktive_buchung", verifiziert_dict)
        log.info(f"✅ [{k}] Buchung OK + verifiziert (eigen) – "
                 f"ID: {verifiziert_dict.get('booking_id')}")
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


def storno_dialog_vorladen(k: str, booking_id: int, datum_api: str) -> None:
    """GODMODE2 (Hebel 2): lädt die Storno-Bestätigungsseite VOR – nur der erste
    GET, storniert NICHT. Wärmt Verbindung/Server-State, damit im kritischen
    Storno→Rebook-Fenster nur noch der Bestätigungs-Request nötig ist.
    Best effort – Fehler werden ignoriert (der volle Storno-Retry fängt alles ab)."""
    snap = az_snap(k, "csrf_token", "http")
    h = _ajax_header(snap["csrf_token"], accept="text/html, */*; q=0.01",
                     referer=f"{BASE_URL}/padel?currentDate={datum_api}")
    try:
        snap["http"].get(
            f"{BASE_URL}/court-module/{MODULE}/bookings/{booking_id}/cancel",
            headers=h, timeout=10)
    except Exception as e:
        log.warning(f"[{k}] Storno-Dialog-Vorladen ID {booking_id}: {e}")


def storno_bestaetigen(k: str, booking_id: int, datum_api: str) -> bool:
    """GODMODE2 (Hebel 2): feuert NUR den Bestätigungs-Request des Stornos
    (button_confirm) – ein einziger GET statt Dialog+Bestätigen. Der Confirm ist
    stateless (fester CONFIRM_KEY), funktioniert also auch ohne vorgeladenen
    Dialog; storno_dialog_vorladen() macht ihn nur schneller. Für den kritischen
    Storno→Rebook-Moment im Blitz-Schiebe. Rückgabe wie storniere_buchung()."""
    snap = az_snap(k, "csrf_token", "http")
    h = _ajax_header(snap["csrf_token"], accept="*/*",
                     referer=f"{BASE_URL}/padel?currentDate={datum_api}")
    try:
        r = snap["http"].get(
            f"{BASE_URL}/court-module/{MODULE}/bookings/{booking_id}/cancel",
            params={"button_confirm": CONFIRM_KEY}, headers=h, timeout=10)
        if r.status_code in [200, 302]:
            az_set(k, "aktive_buchung", None)
            log.info(f"✅ [{k}] Stornierung OK (Schnell-Bestätigung)")
            return True
        log.warning(f"[{k}] Storno-Bestätigung FAIL ID {booking_id}: "
                    f"r={r.status_code} | body={_modal_debug(r.text, 300)!r}")
        return False
    except Exception as e:
        log.error(f"[{k}] Storno-Bestätigung: {e}")
        return False

# ══════════════════════════════════════════════
# SERVER-SYNC
# ══════════════════════════════════════════════

def _parse_total_pages(r_pages) -> int:
    """total-pages-Antwort robust zu int parsen (Zahl/String/Dict), Clamp 1..5."""
    total_pages = 1
    try:
        raw = r_pages.json()
        if isinstance(raw, (int, float, str)):
            total_pages = int(raw)
        elif isinstance(raw, dict):
            for key in ("totalPages", "total_pages", "pages", "total"):
                if key in raw:
                    val = raw[key]
                    total_pages = int(val) if isinstance(val, (int, float, str)) else 1
                    break
    except Exception:
        total_pages = 1
    return max(1, min(total_pages, 5))


def _karte_booking_id(karte) -> int | None:
    """Buchungs-ID aus den Links/Attributen einer my-bookings-Karte ziehen."""
    for pa in ["data-target", "href", "data-url", "action"]:
        for tag in karte.find_all(attrs={pa: _RE_BOOKING_PATH}):
            m2 = _RE_BOOKING_ID.search(tag.get(pa, ""))
            if m2:
                return int(m2.group(1))
    return None


def _parse_buchungskarte(karte) -> tuple[bool, dict | None]:
    """Parst EINE my-bookings-Karte → (hat_datum, dict|None).
    hat_datum=True heißt: die (nicht stornierte) Karte trägt ein Datum – das
    Signal 'echte Buchungskarten sichtbar' für die Session-Härtung (GODMODE2
    Schutz 3). dict=None bei stornierten/unvollständigen Karten.
    court/booking_id können None sein, wenn nicht erkennbar."""
    if karte.find(class_=lambda c: c and
                  ("badge-danger" in c or "cancelled" in c or "storniert" in c)):
        return False, None
    text = karte.get_text(" ", strip=True)
    d_m  = _RE_DATUM_DE.search(text)
    if not d_m:
        return False, None
    z_m = _RE_ZEIT_RANGE.search(text)
    if not z_m:
        return True, None
    c_m      = _RE_COURT.search(text)
    datum_de = d_m.group(1)
    return True, {
        "datum_de":   datum_de,
        "datum_obj":  datetime.strptime(datum_de, "%d.%m.%Y"),
        "fromTime":   z_m.group(1).zfill(5),
        "toTime":     z_m.group(2).zfill(5),
        "court":      int(c_m.group(1)) if c_m else None,
        "booking_id": _karte_booking_id(karte),
    }


def _mb_hole_karten(k: str, frueh_stopp=None) -> tuple[list[dict], bool] | None:
    """V14: EINE Quelle für Sync + Verify (vorher 2× dupliziert). Lädt die
    my-bookings-Seiten und parst alle Buchungskarten.
    Liefert (karten, karten_mit_datum) oder None, wenn schon der
    total-pages-Abruf scheitert (inkl. fehlgeschlagenem Re-Login bei 401).
    frueh_stopp(karte)→True beendet das Blättern vorzeitig (Performance wie
    vorher: Sync/Verify hörten beim Treffer auf).
    KEINE Seiteneffekte auf aktive_buchung."""
    http_sess = acc[k]["http"]
    csrf_t    = az_get(k, "csrf_token")
    h = _ajax_header(csrf_t, referer=f"{BASE_URL}/")

    r_pages = None
    for versuch in range(2):
        try:
            r_pages = http_sess.get(
                f"{BASE_URL}/user/my-bookings/total-pages",
                params={"size": "50", "sort": ["serviceDate,desc", "id,desc"]},
                headers={**h, "accept": "application/json, text/javascript, */*; q=0.01"},
                timeout=10)
        except Exception as e:
            log.error(f"[{k}] my-bookings total-pages: {e}")
            return None
        if r_pages.status_code == 401 and versuch == 0:
            log.warning(f"[{k}] my-bookings: 401 – logge neu ein...")
            if not einloggen(k):
                return None
            csrf_t = az_get(k, "csrf_token")
            h["x-csrf-token"] = csrf_t
            continue
        break

    karten: list[dict] = []
    karten_mit_datum = False
    try:
        for page in range(_parse_total_pages(r_pages)):
            r_page = http_sess.get(
                f"{BASE_URL}/user/my-bookings/page",
                params={"page": str(page), "size": "50",
                        "sort": ["serviceDate,desc", "id,desc"]},
                headers=h, timeout=10)
            if r_page.status_code != 200:
                continue
            soup     = BeautifulSoup(r_page.text, "html.parser")
            elemente = soup.find_all("div", class_=lambda c: c and
                                     "col-12" in c and "col-sm-6" in c)
            if not elemente:
                elemente = list({
                    tag.find_parent("div") for tag in
                    soup.find_all(attrs={"href": _RE_BOOKING_PATH}) +
                    soup.find_all(attrs={"data-target": _RE_BOOKING_PATH})
                    if tag.find_parent("div")
                })
            if not elemente:
                elemente = [soup]
            for el in elemente:
                hat_datum, karte = _parse_buchungskarte(el)
                if hat_datum:
                    karten_mit_datum = True
                if not karte:
                    continue
                karten.append(karte)
                if frueh_stopp and frueh_stopp(karte):
                    return karten, karten_mit_datum
    except Exception as e:
        log.error(f"[{k}] my-bookings Karten-Parse: {e}")
    return karten, karten_mit_datum


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

    jetzt = jetzt_lokal()

    def _ist_zukuenftig(karte: dict) -> bool:
        if karte["datum_obj"].date() < jetzt.date():
            return False
        slot_dt = datetime.combine(
            karte["datum_obj"].date(),
            datetime.strptime(karte["fromTime"], "%H:%M").time())
        return slot_dt >= jetzt

    # V14: gemeinsamer my-bookings-Parser; frueh_stopp = beim ersten
    # zukünftigen Treffer aufhören zu blättern (Request-Zahl wie vorher).
    res = _mb_hole_karten(k, frueh_stopp=_ist_zukuenftig)
    if res is None:
        return
    karten, karten_mit_datum = res

    gefunden = None
    for karte in karten:
        if not _ist_zukuenftig(karte):
            continue
        court       = karte["court"] or 1
        datum_api_s = karte["datum_obj"].strftime("%m/%d/%Y")
        gefunden = {
            "court":      court,
            "fromTime":   karte["fromTime"],
            "toTime":     karte["toTime"],
            "datum_de":   karte["datum_de"],
            "datum_api":  datum_api_s,
            "dauer":      dauer_minuten(karte["fromTime"], karte["toTime"]),
            "booking_id": karte["booking_id"],
            "key":        f"{datum_api_s}_{court}_{karte['fromTime']}",
        }
        log.info(f"[{k}] Sync OK: {karte['datum_de']} {karte['fromTime']}–"
                 f"{karte['toTime']} Court {court} ID={karte['booking_id']}")
        break

    aktuell = az_get(k, "aktive_buchung")
    if gefunden:
        az_set(k, "aktive_buchung", gefunden)
    else:
        # GODMODE2 (Schutz 3 – Session-Härtung): bei toter Session liefert
        # my-bookings 200 OHNE Karten statt 401 → "Keine aktive Buchung" wäre
        # ein Falsch-Negativ (siehe 08.07. 13:02, AB/NH/MH). Dann Ergebnis
        # verwerfen, neu einloggen und aktive_buchung NICHT löschen – der
        # nächste Sync liefert das korrekte Bild.
        if not karten_mit_datum and not ist_eingeloggt(k):
            log.warning(f"[{k}] Sync verworfen: my-bookings leer + Session tot → Re-Login")
            einloggen(k)
            return
        if aktuell and not az_get(k, "schiebe_aktiv"):
            log.info(f"[{k}] Keine aktive Buchung auf dem Server.")
        az_set(k, "aktive_buchung", None)


def verifiziere_slot_via_my_bookings(k: str, expected_slot: dict,
                                     _zweiter_versuch: bool = False) -> dict | None:
    """
    R10/R11/R12-konformer Verifikations-Helper für Multi-Shot-Bursts.
    Fragt /user/my-bookings ab und sucht NUR den expected_slot (court, fromTime, toTime, datum_de).
    Liefert verifiziertes Buchungs-Dict (inkl. booking_id) oder None.
    Hat KEINE Seiteneffekte (verändert aktive_buchung nicht).
    GODMODE2: erkennt stille tote Sessions (200 ohne Karten statt 401) und
    wiederholt dann EINMAL mit frischem Login (_zweiter_versuch verhindert Schleife).
    """
    exp_court    = int(expected_slot["court"])
    exp_from     = expected_slot["fromTime"]
    exp_to       = expected_slot["toTime"]
    exp_datum_de = expected_slot["datum_de"]

    def _passt(karte: dict) -> bool:
        return (karte["datum_de"] == exp_datum_de
                and karte["fromTime"] == exp_from
                and karte["toTime"]   == exp_to
                and karte["court"]    == exp_court)

    # V14: gemeinsamer my-bookings-Parser; frueh_stopp = beim Treffer aufhören
    # zu blättern (Request-Zahl wie vorher). 401→Re-Login macht der Parser.
    res = _mb_hole_karten(k, frueh_stopp=_passt)
    if res is None:
        return None
    karten, karten_mit_datum = res
    for karte in karten:
        if _passt(karte):
            datum_api = datum_de_zu_api(exp_datum_de)
            return {
                "court":      exp_court,
                "fromTime":   exp_from,
                "toTime":     exp_to,
                "datum_de":   exp_datum_de,
                "datum_api":  datum_api,
                "dauer":      dauer_minuten(exp_from, exp_to),
                "booking_id": karte["booking_id"],
                "key":        f"{datum_api}_{exp_court}_{exp_from}",
            }
    # GODMODE2 (Schutz 3 – Session-Härtung): my-bookings liefert bei toter
    # Session 200 OHNE Karten statt 401 → ein leeres Ergebnis wäre dann ein
    # Falsch-Negativ (Buchung existiert, wird aber nicht gesehen). Waren gar
    # keine Buchungskarten sichtbar: Login prüfen, neu einloggen, 1× wiederholen.
    if not karten_mit_datum and not _zweiter_versuch and not ist_eingeloggt(k):
        log.warning(f"[{k}] Verify leer + Session tot → Re-Login + zweiter Versuch")
        if einloggen(k):
            return verifiziere_slot_via_my_bookings(k, expected_slot,
                                                    _zweiter_versuch=True)
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

_RE_STYLE_BLOCK = re.compile(r"<style[^>]*>.*?</style>", re.S | re.I)

# f"{k}:{court}" → True, wenn der letzte buche_slot-Versuch ein Server-Konflikt
# ("Slot fremd belegt") war. Wird vom Hartnäckig-Loop gelesen (Schnellabbruch).
_KONFLIKT_FLAG: dict[str, bool] = {}

def _modal_debug(text: str, n: int = 1200) -> str:
    """Antwort-Body für Diagnose-Logs: <style>-Blöcke raus, Whitespace eindampfen,
    damit der Modal-Titel (Erfolg/Konflikt/Reload) im Log immer lesbar ist."""
    t = _RE_STYLE_BLOCK.sub("", text or "")
    return re.sub(r"\s+", " ", t).strip()[:n]

def _messe_server_offset(k: str) -> float | None:
    """GODMODE-Zeitsync v2 (V15): schätzt (Serverzeit − lokale Zeit) in Sekunden
    über die Sekundensprünge des Date-Headers. Sammelt MEHRERE Sprünge (nicht nur
    den ersten) und nimmt den MEDIAN → ein einzelner Ausreißer (z.B. -600ms durch
    Netz-Jitter) kippt die Messung nicht mehr. Streuen die Einzelmessungen zu
    stark (> ZEITSYNC_MAX_STREUUNG_S), wird NICHT korrigiert (None) → dann Feuer
    auf die lokale (per NTP genaue) T-0. Positiv = Serveruhr geht vor → Slot
    schaltet LOKAL entsprechend früher frei.
    Alle Roh-Samples werden geloggt, damit über mehrere Tage sichtbar wird, ob
    ein großer Offset echt (stabil) oder Zufall (springt) ist."""
    snap = az_snap(k, "csrf_token", "http")
    http = snap["http"]
    h = {**_ajax_header(snap["csrf_token"], referer=f"{BASE_URL}/"),
         "accept": "application/json, text/javascript, */*; q=0.01"}
    prev_sec = prev_mid = None
    schaetzungen: list[float] = []
    try:
        for _ in range(20):            # ~5s Messdauer, fängt mehrere Sekundensprünge
            t0 = time.time()
            r = http.get(f"{BASE_URL}/user/my-bookings/total-pages",
                         params={"size": "50"}, headers=h, timeout=3)
            t1 = time.time()
            dh = r.headers.get("Date")
            if not dh:
                break
            sec = parsedate_to_datetime(dh).timestamp()
            mid = (t0 + t1) / 2.0
            if (t1 - t0) <= 0.35:      # nur Samples mit kleiner RTT verwerten
                if (prev_sec is not None and sec - prev_sec == 1
                        and (mid - prev_mid) < 0.6):
                    # Date-Header ist zwischen zwei Requests umgesprungen:
                    # Server stand bei sec.000, lokal war es ~Mitte der Lücke
                    schaetzungen.append(sec - (prev_mid + mid) / 2.0)
                prev_sec, prev_mid = sec, mid
            time.sleep(0.1)
    except Exception as e:
        log.warning(f"[{k}] Zeitsync-Messung: {e}")

    if not schaetzungen:
        return None
    schaetzungen.sort()
    median = schaetzungen[len(schaetzungen) // 2]
    streuung = schaetzungen[-1] - schaetzungen[0]
    log.info(f"[{k}] Zeitsync-Samples (ms): {[round(x * 1000) for x in schaetzungen]} "
             f"→ Median {median * 1000:+.0f}ms, Streuung {streuung * 1000:.0f}ms")
    if len(schaetzungen) >= 3 and streuung > ZEITSYNC_MAX_STREUUNG_S:
        log.info(f"[{k}] Zeitsync: Messungen zu uneinig "
                 f"(Streuung {streuung * 1000:.0f}ms) → keine Korrektur")
        return None
    return median


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
        execution = _parse_execution(r1.text, "")
        if execution:
            # Falls personId hier auftaucht, gleich cachen
            if not az_get(k, "person_id"):
                pid = extrahiere_person_id(r1.text)
                if pid:
                    az_set(k, "person_id", pid)
            return execution
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
    datum_api = slot["datum_api"]
    snap      = az_snap(k, "csrf_token", "person_id", "http")
    csrf_t    = snap["csrf_token"]
    person_id = snap["person_id"]
    http      = snap["http"]
    if not person_id:
        log.warning(f"[{k}] burst Court {court}: Person-ID fehlt!")
        return False, None

    hp = _post_header(csrf_t, datum_api)
    try:
        r2 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                       params={"execution": execution, "_eventId": "next"},
                       data=_r2_data(slot, court, person_id, csrf_t),
                       timeout=10)
        exec2 = _parse_execution(r2.text, execution.replace("s1", "s2"))
        low2 = r2.text.lower()
        if KONFLIKT_TEXT in low2:
            log.warning(f"⛔ [{k}] Court {court}: Konflikt bereits in r2 – Slot vergeben.")
            return False, {"konflikt": True}
        if _hat_fehler_indiz(low2):
            return False, None

        return _feuer_r3_commit(k, court, http, hp, csrf_t, exec2, slot)
    except Exception as e:
        log.warning(f"[{k}] burst_r2_r3 Court {court}: {e}")
        return False, None


def _feuer_r3_commit(k: str, court: int, http, hp: dict, csrf_t: str,
                     exec2: str, slot: dict) -> tuple[bool, dict | None]:
    """Gemeinsames r3-Commit für burst_r2_r3 und burst_commit_only (GODMODE).
    Erkennt Konflikt ("Slot fremd belegt") und Erfolgs-Text explizit."""
    r3 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                   params={"execution": exec2, "_eventId": "commit"},
                   data=f"purchaseTemplate.comment=&_csrf={csrf_t}",
                   timeout=10)
    if r3.status_code not in [200, 302]:
        return False, None

    booking_id = _parse_booking_id(r3.text)
    # DIAGNOSE: r3-Status + geparste ID + Body (ohne <style>) → Erfolgs-,
    # Konflikt- oder Reload-Modal ist im Log im Klartext erkennbar.
    log.info(f"🔎 [{k}] Burst-r3 Court {court}: status={r3.status_code} "
             f"parsed_id={booking_id} | body={_modal_debug(r3.text)!r}")

    low = r3.text.lower()
    if KONFLIKT_TEXT in low:
        log.warning(f"⛔ [{k}] Court {court}: Konflikt mit bestehendem Termin – Slot vergeben.")
        return False, {"konflikt": True}
    if _hat_fehler_indiz(low):
        return False, None
    erfolg_text = any(t in low for t in ERFOLG_TEXTE)
    return True, {**slot, "court": int(court), "booking_id": booking_id,
                  "erfolg_text": erfolg_text}


def pre_fire_r2(k: str, court: int, execution: str, slot: dict) -> str | None:
    """GODMODE: feuert NUR r2 (_eventId=next) kurz VOR der Freischaltung mit dem
    Pre-Warm-Token. Bei T-0 fehlt dann nur noch das r3-Commit → ~halbe Latenz im
    Rennen gegen fremde Bots. Liefert exec2 (eXs2) oder None → Caller fällt auf
    den bewährten vollen r2+r3-Burst zurück (kein Risiko, wie Prewarm-Fallback)."""
    datum_api = slot["datum_api"]
    snap      = az_snap(k, "csrf_token", "person_id", "http")
    csrf_t    = snap["csrf_token"]
    person_id = snap["person_id"]
    http      = snap["http"]
    if not person_id:
        log.warning(f"[{k}] r2-Prefire Court {court}: Person-ID fehlt!")
        return None
    hp = _post_header(csrf_t, datum_api)
    try:
        r2 = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                       params={"execution": execution, "_eventId": "next"},
                       data=_r2_data(slot, court, person_id, csrf_t),
                       timeout=10)
        low2 = r2.text.lower()
        if (r2.status_code not in [200, 302] or KONFLIKT_TEXT in low2
                or _hat_fehler_indiz(low2)):
            log.warning(f"[{k}] r2-Prefire Court {court} abgelehnt: "
                        f"status={r2.status_code} | body={_modal_debug(r2.text, 300)!r}")
            return None
        exec2 = _parse_execution(r2.text, execution.replace("s1", "s2"))
        return exec2
    except Exception as e:
        log.warning(f"[{k}] pre_fire_r2 Court {court}: {e}")
        return None


def burst_commit_only(k: str, court: int, exec2: str, slot: dict) -> tuple[bool, dict | None]:
    """GODMODE Welle 0: nur noch r3-Commit (r2 wurde bereits per pre_fire_r2
    vorgefeuert). Gleiche Verifikations-Pflichten wie burst_r2_r3 (R10)."""
    snap   = az_snap(k, "csrf_token", "http")
    csrf_t = snap["csrf_token"]
    http   = snap["http"]
    hp = _post_header(csrf_t, slot["datum_api"])
    try:
        return _feuer_r3_commit(k, court, http, hp, csrf_t, exec2, slot)
    except Exception as e:
        log.warning(f"[{k}] burst_commit_only Court {court}: {e}")
        return False, None


# ══════════════════════════════════════════════
# V16: SPAM-COMMIT (Weiter-Dauerfeuer → beim Aufspringen sofort buchen)
# ══════════════════════════════════════════════

_RE_EXEC_STEP = re.compile(r"execution=e\d+s(\d+)")

def _weiter_status(k: str, court: int, execution: str, slot: dict) -> tuple[str, str | None]:
    """V16-Kern: feuert EIN "Weiter" (_eventId=next) auf `execution` und liest NUR
    den Redirect (folgt ihm NICHT → lädt die 6–15 KB-Seite nicht). Belegt durch
    HAR 10.07.:
      Slot ZU/belegt → 302 Location …execution=eXs1  (bleibt auf Schritt 1)
      Slot AUF        → 302 Location …execution=eXs2  (Bestätigungsseite)
    Rückgabe:
      ("OPEN",   "eXs2") → buchbar, exec2 = commit-Token
      ("LOCKED", None)   → noch zu / belegt – DERSELBE Token bleibt nutzbar
      ("ERROR",  None)   → unerwartet → Caller fällt auf klassischen Burst zurück
    """
    snap      = az_snap(k, "csrf_token", "person_id", "http")
    csrf_t    = snap["csrf_token"]
    person_id = snap["person_id"]
    http      = snap["http"]
    if not person_id:
        return "ERROR", None
    hp = _post_header(csrf_t, slot["datum_api"])
    try:
        r = http.post(f"{BASE_URL}/court-single-booking-flow", headers=hp,
                      params={"execution": execution, "_eventId": "next"},
                      data=_r2_data(slot, court, person_id, csrf_t),
                      timeout=10, allow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get("Location", "")
            m = _RE_EXEC_STEP.search(loc)
            if m:
                step = int(m.group(1))
                if step >= 2:
                    # Sprung auf Bestätigungsseite → exec2 aus der Location
                    exec2 = re.search(r"execution=(e\d+s\d+)", loc).group(1)
                    return "OPEN", exec2
                return "LOCKED", None      # zurück auf s1 → noch zu
            return "ERROR", None
        # Kein Redirect (200 o.ä.): Body prüfen (Konflikt/Commit-Formular)
        low = r.text.lower()
        if KONFLIKT_TEXT in low:
            return "LOCKED", None
        if "_eventid=commit" in low or "sind alle angaben" in low:
            exec2 = _parse_execution(r.text, execution.replace("s1", "s2"))
            return "OPEN", exec2
        return "ERROR", None
    except Exception as e:
        log.warning(f"[{k}] Weiter-Status Court {court}: {e}")
        return "ERROR", None


def _spam_weiter_commit(k: str, court: int, slot: dict, deadline_ts: float,
                        aktiv_fn, execution: str | None = None,
                        konflikt_stop: int = SPAM_KONFLIKT_STOP,
                        label: str = "Spam") -> tuple[str, dict | None]:
    """V17-KERN (gemeinsam für alle Modi): hält EINEN eXs1-Token und feuert
    "Weiter" im Dauerfeuer, bis der Slot aufspringt (Redirect → s2), dann SOFORT
    commit. Kein r1-Neuladen pro Versuch. Spammt bis `deadline_ts`
    (time.time()-Basis). `execution` = optional schon vorgewärmter Token.
    Rückgabe:
      ("HIT",      buchung_dict) → verifizierte EIGENE Buchung
      ("CONFLICT", None)         → Slot fremd vergeben (nach konflikt_stop)
      ("FALLBACK", None)         → Token/Flow-Problem/Timeout → Caller macht klassisch
    """
    datum_api = slot["datum_api"]
    from_t, to_t = slot["fromTime"], slot["toTime"]
    if not execution:
        execution = pre_warm_r1(k, court, datum_api, from_t, to_t)
        if not execution:
            log.warning(f"[{k}] {label} Court {court}: Pre-Warm leer → Fallback")
            return "FALLBACK", None

    konflikte = 0
    weiter_versuche = 0
    while aktiv_fn() and time.time() < deadline_ts:
        status, exec2 = _weiter_status(k, court, execution, slot)
        weiter_versuche += 1

        if status == "LOCKED":
            time.sleep(SPAM_NEXT_INTERVAL)      # noch zu → gleicher Token, weiter
            continue

        if status == "ERROR":
            log.warning(f"[{k}] {label} Court {court}: unerwartete Antwort nach "
                        f"{weiter_versuche} Weiter → Fallback")
            return "FALLBACK", None

        # status == OPEN → Slot ist auf, sofort committen
        t0 = time.perf_counter()
        ok, parsed = burst_commit_only(k, court, exec2, slot)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        log.info(f"⚡ [{k}] {label}-Commit Court {court} nach {weiter_versuche} Weiter: "
                 f"ok={ok} ({dt_ms:.0f}ms)")

        if ok:
            verifiziert = verifiziere_slot_via_my_bookings(k, slot)
            if not verifiziert and parsed and parsed.get("erfolg_text"):
                for _lag in range(2):
                    time.sleep(0.5)
                    verifiziert = verifiziere_slot_via_my_bookings(k, slot)
                    if verifiziert:
                        break
            if verifiziert:
                return "HIT", verifiziert
            log.warning(f"[{k}] {label} Court {court}: commit OK aber nicht in "
                        f"my-bookings → neuer Token, weiter")
        elif parsed and parsed.get("konflikt"):
            konflikte += 1
            if konflikte >= konflikt_stop:
                log.warning(f"⛔ [{k}] {label} Court {court}: {konflikte}× Konflikt "
                            f"in Folge – Slot fremd vergeben.")
                return "CONFLICT", None
        # commit verbraucht den Flow (→ s3) → frischen Token holen und weiter spammen
        execution = pre_warm_r1(k, court, datum_api, from_t, to_t)
        if not execution:
            return "FALLBACK", None

    return "FALLBACK", None


def spam_commit_blitz(k: str, court: int, slot: dict, basis_dt: datetime,
                      aktiv_fn) -> tuple[str, dict | None]:
    """Freischaltungs-Blitz (Direkt/Duo/3h/Safe): Token holen, kurz vor T-0 mit
    dem "Weiter"-Dauerfeuer beginnen, bei Aufspringen sofort commit. Dünner
    Wrapper um den gemeinsamen Kern _spam_weiter_commit."""
    execution = pre_warm_r1(k, court, slot["datum_api"], slot["fromTime"], slot["toTime"])
    if not execution:
        log.warning(f"[{k}] Spam Court {court}: Pre-Warm leer → Fallback")
        return "FALLBACK", None
    log.info(f"⚡ [{k}] Spam Court {court}: Token {execution} → warte auf Freischaltung")
    # "Weiter"-Dauerfeuer erst kurz vor T-0 starten (davor eh nur LOCKED).
    warte_bis_genau(basis_dt - timedelta(milliseconds=SPAM_FENSTER_VOR_MS))
    deadline = time.time() + SPAM_DEADLINE_S + SPAM_FENSTER_VOR_MS / 1000.0
    return _spam_weiter_commit(k, court, slot, deadline, aktiv_fn,
                               execution=execution, label="Spam")


def _direkt_blitz(k: str, datum_de: str, datum_api: str, dauer_min: int,
                  buchbar_dt: datetime, courts_zu_versuchen: list[int],
                  bevorzugter_court: int = 0,
                  von: str | None = None, bis: str | None = None) -> bool:
    """
    R15–R18: Pre-Warm bei T-10s, Burst bei T-0 parallel auf bis zu 2 Courts.
    Bei Miss: bis zu MULTI_SHOT_COUNT weitere Bursts mit MULTI_SHOT_GAP_MS Pause.
    Nach jedem Treffer Sicherheitsnetz via verifiziere_slot_via_my_bookings() (R10).
    R1: Bei Doppel-Treffer (Server-Race) wird nicht-bevorzugter Court storniert.

    von/bis: expliziter Slot (statt aus buchbar_dt abgeleitet) – für Safe-Modus
    (z.B. 30-Min-Füller). buchbar_dt bleibt der EXAKTE Feuer-Zeitpunkt (T-0).
    """
    if von and bis:
        from_t, to_t = von, bis
    else:
        buchbar_zeit = buchbar_dt.time()
        from_t       = buchbar_zeit.strftime("%H:%M")
        to_t         = (buchbar_dt + timedelta(minutes=dauer_min)).time().strftime("%H:%M")

    treffer      = {}      # court -> verifizierte Buchung
    treffer_lock = threading.Lock()

    # GODMODE-Zeitsync (V15: standardmäßig AUS – siehe ZEITSYNC_AKTIV). Feuer auf
    # die lokale, per NTP genaue Uhr. Bei ZEITSYNC_AKTIV=True wird der Offset
    # gemessen (robuster Median) und angewandt; unplausible/fehlende Messung →
    # Verhalten exakt wie ohne Korrektur.
    zeit_korr = 0.0
    if ZEITSYNC_AKTIV and (buchbar_dt - jetzt_lokal()).total_seconds() > BLITZ_PREWARM_SECONDS + 5:
        _off = _messe_server_offset(k)
        if _off is not None and 0.05 <= abs(_off) <= ZEITSYNC_MAX_OFFSET_S:
            zeit_korr = _off
            log.info(f"⏱️ [{k}] Serveruhr-Offset {_off*1000:+.0f}ms → Blitz feuert "
                     f"entsprechend {'früher' if _off > 0 else 'später'}")
        elif _off is not None:
            log.info(f"⏱️ [{k}] Serveruhr-Offset {_off*1000:+.0f}ms → keine Korrektur "
                     f"({'vernachlässigbar' if abs(_off) < 0.05 else 'unplausibel'})")
        else:
            log.info(f"⏱️ [{k}] Zeitsync: keine verwertbare Messung → keine Korrektur")
    else:
        log.info(f"⏱️ [{k}] Zeitsync AUS → Blitz feuert auf lokale Uhr (T-0 = {buchbar_dt.strftime('%H:%M:%S')})")
    basis_dt = buchbar_dt - timedelta(seconds=zeit_korr)

    def court_worker(court: int):
        slot = _baue_slot_dict(court, from_t, to_t, datum_de, datum_api, dauer_min)

        # Pre-Warm bei T-10s
        prewarm_dt = basis_dt - timedelta(seconds=BLITZ_PREWARM_SECONDS)
        warte_bis_genau(prewarm_dt)
        if not az_get(k, "schiebe_aktiv"):
            return
        execution = pre_warm_r1(k, court, datum_api, from_t, to_t)
        if execution:
            log.info(f"⚡ [{k}] Pre-Warm Court {court} OK → {execution}")
        else:
            log.warning(f"[{k}] Pre-Warm Court {court} fehlgeschlagen")

        # ── V16: SPAM-COMMIT ZUERST ("Weiter"-Dauerfeuer → beim Aufspringen
        #    sofort buchen). HIT/CONFLICT beenden diesen Court; nur bei FALLBACK
        #    läuft der bewährte V15-Burst unten weiter (kann nie schlechter sein).
        if SPAM_COMMIT_AKTIV:
            with treffer_lock:
                if treffer:
                    return
            ausgang, buchung = spam_commit_blitz(
                k, court, slot, basis_dt, lambda: az_get(k, "schiebe_aktiv"))
            if ausgang == "HIT":
                with treffer_lock:
                    if not treffer:
                        treffer[court] = buchung
                return
            if ausgang == "CONFLICT":
                return
            # FALLBACK: frisch in den klassischen Burst (basis_dt liegt jetzt in
            # der Vergangenheit → Burst feuert sofort, wie ein verspäteter Blitz).
            execution = None
            log.info(f"[{k}] Spam Court {court} → Fallback auf klassischen Burst")

        # GODMODE: r2 schon bei T−R2_PREFIRE_MS feuern → Welle 0 muss bei T-0
        # nur noch committen. Lehnt der Server das frühe r2 ab, holt der
        # Fallback sofort einen frischen Token (alter Flow evtl. verbrannt)
        # und Welle 0 feuert wie bisher den vollen r2+r3-Burst.
        exec2 = None
        if execution and R2_PREFIRE_MS > 0:
            warte_bis_genau(basis_dt - timedelta(milliseconds=R2_PREFIRE_MS))
            if not az_get(k, "schiebe_aktiv"):
                return
            exec2 = pre_fire_r2(k, court, execution, slot)
            if exec2:
                log.info(f"⚡ [{k}] r2-Prefire Court {court} OK → {exec2}")
            else:
                execution = pre_warm_r1(k, court, datum_api, from_t, to_t)

        # Burst-Wellen bei T-0, T+gap, T+2*gap, ...
        konflikte = 0
        for burst in range(MULTI_SHOT_COUNT + 1):
            with treffer_lock:
                if treffer:
                    return
            if not az_get(k, "schiebe_aktiv"):
                return
            fire_dt = basis_dt + timedelta(milliseconds=BLITZ_FIRE_OFFSET_MS
                                                        + burst * MULTI_SHOT_GAP_MS)
            warte_bis_genau(fire_dt)

            t0 = time.perf_counter()
            if burst == 0 and exec2:
                ok, parsed = burst_commit_only(k, court, exec2, slot)
                art = "Commit-Blitz"
            else:
                if not execution:
                    execution = pre_warm_r1(k, court, datum_api, from_t, to_t)
                    if not execution:
                        continue
                ok, parsed = burst_r2_r3(k, court, execution, slot)
                art = "Burst"
            dt_ms = (time.perf_counter() - t0) * 1000.0
            log.info(f"⚡ [{k}] {art} {burst+1}/{MULTI_SHOT_COUNT+1} Court {court}: "
                     f"ok={ok} ({dt_ms:.0f}ms)")
            if ok:
                # Sicherheitsnetz: my-bookings verifizieren
                verifiziert = verifiziere_slot_via_my_bookings(k, slot)
                if not verifiziert and parsed and parsed.get("erfolg_text"):
                    # Server meldete explizit Erfolg → my-bookings-Lag abfedern
                    for _lag in range(2):
                        time.sleep(0.5)
                        verifiziert = verifiziere_slot_via_my_bookings(k, slot)
                        if verifiziert:
                            break
                if verifiziert:
                    with treffer_lock:
                        if not treffer:
                            treffer[court] = verifiziert
                    return
                log.warning(f"[{k}] Burst Court {court}: r3 OK aber NICHT in my-bookings "
                            f"→ ignoriere (False-Positive verhindert)")
            elif parsed and parsed.get("konflikt"):
                konflikte += 1
                if konflikte >= 2:
                    log.warning(f"⛔ [{k}] Court {court}: {konflikte}× Konflikt – "
                                f"Slot fremd vergeben, Burst-Wellen abgebrochen.")
                    return
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
    ziel_dt   = datetime.strptime(ziel_str, "%H:%M")
    schluss   = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")

    def aktiv() -> bool:
        return az_get(k, "schiebe_aktiv")

    def schlafe(sek: float) -> bool:
        return _schlafe_solange(aktiv, sek)

    def beende(msg: str = ""):
        _schiebe_beende(k, msg)

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
            warte_str = _format_restzeit(sek)

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

        # V2.1 FIX B: Ohne booking_id kann der Fremd-Check die EIGENE Buchung
        # nicht ignorieren (das Ziel überlappt die eigene immer → falscher
        # Abbruch "fremd belegt") und der Storno liefe gegen
        # /bookings/None/cancel. Daher: ID aus my-bookings nachladen; klappt
        # das nicht → Buchung BEHALTEN und sauber stoppen.
        if not booking_id:
            nachgeladen = verifiziere_slot_via_my_bookings(k, aktive_b)
            if nachgeladen and nachgeladen.get("booking_id"):
                aktive_b   = nachgeladen
                booking_id = nachgeladen["booking_id"]
                az_set(k, "aktive_buchung", nachgeladen)
                log.info(f"[{k}] booking_id nachgeladen: {booking_id}")
            else:
                beende(f"⚠️ [{k}] Buchungs-ID unbekannt und nicht nachladbar – "
                       f"Schieben gestoppt.\n"
                       f"✅ Buchung {aktive_b['fromTime']}–{aktive_b['toTime']} "
                       f"bleibt unangetastet.\n"
                       f"🆘 Bitte manuell prüfen: {BASE_URL}/padel?currentDate={datum_api}")
                return

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

        # GODMODE2 (Schutz 1): NIEMALS ins Verderben stornieren. Liegt im
        # Ziel-Slot eine FREMDE Buchung (eigene alte zählt nicht), würde die
        # Neubuchung sicher am Konflikt scheitern → alte Buchung BEHALTEN,
        # statt am Ende mit NICHTS dazustehen.
        fremd = _ziel_slot_fremd_belegt(k, blitz_court, naechster_von,
                                        naechster_bis, datum_api, booking_id)
        if fremd:
            beende(f"⛔ [{k}] Ziel-Slot {naechster_von}–{naechster_bis} "
                   f"(Court {blitz_court}) ist fremd belegt ({fremd}) – "
                   f"Storno abgebrochen.\n"
                   f"✅ Behalte {aktive_b['fromTime']}–{aktive_b['toTime']}.\n"
                   f"💡 Tipp: Sniper auf das fremde Buchungsende ansetzen.")
            return

        prewarm_exec = pre_warm_r1(k, blitz_court, datum_api,
                                   naechster_von, naechster_bis)
        # GODMODE2 (Hebel 1): r2 schon VOR dem Storno feuern, solange die alte
        # Buchung noch hält. Der Server lässt den Flow trotz Slot-Überlappung mit
        # der EIGENEN Altbuchung bis zum Commit laufen (v12-Blitzschiebe live
        # bestätigt). Nach dem Storno fehlt dann nur noch das r3-Commit → halbes
        # Klau-Fenster. Lehnt der Server das frühe r2 ab (prewarm_exec2 leer):
        # frischer r1-Token, danach normaler r2+r3-Burst – exakt wie bisher.
        prewarm_exec2 = None
        if prewarm_exec:
            log.info(f"⚡ [{k}] Schiebe-Prewarm r1 Court {blitz_court} OK → {prewarm_exec}")
            if R2_PREFIRE_MS > 0:
                prewarm_exec2 = pre_fire_r2(k, blitz_court, prewarm_exec, ziel_slot)
                if prewarm_exec2:
                    log.info(f"⚡ [{k}] Schiebe-Prefire r2 Court {blitz_court} OK → "
                             f"{prewarm_exec2} (nach Storno nur noch Commit)")
                else:
                    # frühes r2 abgelehnt → Flow evtl. verbrannt, frisch vorwärmen
                    prewarm_exec = pre_warm_r1(k, blitz_court, datum_api,
                                               naechster_von, naechster_bis)
        else:
            log.warning(f"[{k}] Schiebe-Prewarm Court {blitz_court} leer "
                        f"→ Fallback buche_slot")

        # GODMODE2 (Hebel 2): Storno-Bestätigungsseite vorladen → im kritischen
        # Moment bleibt nur der eine Bestätigungs-Request (statt Dialog+Bestätigen).
        storno_dialog_vorladen(k, booking_id, datum_api)

        storno_ok = False
        for storno_versuch in range(6):
            if not aktiv():
                return
            # Versuch 0 = Schnellpfad (Dialog vorgeladen → nur Bestätigen).
            # Retries = voller Storno (Dialog neu laden + bestätigen), robust.
            if storno_versuch == 0:
                storniert = storno_bestaetigen(k, booking_id, datum_api)
            else:
                storniert = storniere_buchung(k, booking_id, datum_api)
            if storniert:
                storno_ok = True
                break
            log.warning(f"[{k}] Storno-Retry {storno_versuch+1}/6 (kein Telegram-Spam)")
            time.sleep(10)

        if not storno_ok:
            # 403 = Server verweigert den Cancel. Häufigste Ursache: die lokal
            # gemerkte Buchung gehört gar nicht (mehr) zu diesem Account
            # (Phantom-/Fremdbuchung, bereits storniert). Dann ist Weiter-Retry
            # sinnlos → würde ewig gegen den Server hämmern. Erst prüfen, ob die
            # Buchung überhaupt noch in my-bookings steht.
            noch_meins = verifiziere_slot_via_my_bookings(k, aktive_b)
            if not noch_meins:
                log.warning(f"[{k}] Storno unmöglich: ID {booking_id} nicht in "
                            f"my-bookings → gehört nicht (mehr) zu diesem Account.")
                az_set(k, "aktive_buchung", None)
                beende(f"⛔ [{k}] Buchung {booking_id} ist nicht (mehr) in deinem "
                       f"Konto (Storno 403) – Schiebe gestoppt.\n"
                       f"🆘 Bitte manuell prüfen:\n"
                       f"{BASE_URL}/padel?currentDate={datum_api}")
                return
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

        # ── V17: SPAM-COMMIT zuerst (Weiter-Dauerfeuer, bis der Selbst-Konflikt
        #    mit der gerade stornierten eigenen Buchung weg ist → sofort buchen).
        #    Kein Treffer → EXAKT der bewährte v12-Ablauf unten (Prefire-Commit +
        #    Burst + buche_slot + ROLLBACK) läuft unverändert weiter. ──────────
        if SPAM_COMMIT_AKTIV:
            spam_deadline = time.time() + SPAM_DEADLINE_S
            ausgang, buchung = _spam_weiter_commit(
                k, blitz_court, ziel_slot, spam_deadline, aktiv,
                label="Schiebe-Spam")
            if ausgang == "HIT":
                az_set(k, "aktive_buchung", buchung)
                ok = True
            else:
                log.info(f"[{k}] Schiebe-Spam Court {blitz_court} kein Treffer "
                         f"({ausgang}) → bewährter Ablauf")

        if not ok and (prewarm_exec2 or prewarm_exec):
            # Nach erfolgreichem Prefire ist der r1-Token verbraucht → Welle 1+
            # wärmt frisch vor (execution=None). Ohne Prefire = alter Ablauf.
            execution = None if prewarm_exec2 else prewarm_exec
            for welle in range(MULTI_SHOT_COUNT + 1):
                if not aktiv():
                    return
                t0 = time.perf_counter()
                if welle == 0 and prewarm_exec2:
                    # GODMODE2: r2 lief schon vor dem Storno → nur noch Commit.
                    erfolg, burst_dict = burst_commit_only(k, blitz_court,
                                                           prewarm_exec2, ziel_slot)
                    art = "Schiebe-Commit-Blitz"
                else:
                    if not execution:
                        execution = pre_warm_r1(k, blitz_court, datum_api,
                                                naechster_von, naechster_bis)
                        if not execution:
                            time.sleep(MULTI_SHOT_GAP_MS / 1000.0)
                            continue
                    erfolg, burst_dict = burst_r2_r3(k, blitz_court, execution, ziel_slot)
                    art = "Schiebe-Burst"
                dt_ms = (time.perf_counter() - t0) * 1000.0
                log.info(f"⚡ [{k}] {art} {welle+1}/{MULTI_SHOT_COUNT+1} "
                         f"Court {blitz_court}: ok={erfolg} ({dt_ms:.0f}ms)")
                if erfolg:
                    verifiziert = verifiziere_slot_via_my_bookings(k, ziel_slot)
                    if not verifiziert and burst_dict and burst_dict.get("erfolg_text"):
                        # Server meldete Erfolg → my-bookings-Lag abfedern
                        for _lag in range(2):
                            time.sleep(0.5)
                            verifiziert = verifiziere_slot_via_my_bookings(k, ziel_slot)
                            if verifiziert:
                                break
                    if verifiziert:
                        az_set(k, "aktive_buchung", verifiziert)
                        ok = True
                        break
                    _pid = burst_dict.get("booking_id") if burst_dict else None
                    log.warning(f"[{k}] Schiebe-Burst r3 OK aber nicht in "
                                f"my-bookings → nächste Welle (parsed_id={_pid})")
                # Token ist verbraucht → für die nächste Welle neu vorwärmen
                execution = pre_warm_r1(k, blitz_court, datum_api,
                                        naechster_von, naechster_bis)
                time.sleep(MULTI_SHOT_GAP_MS / 1000.0)

        # ── Fallback: klassischer buche_slot-Loop (nur aktueller Court) ──
        # Greift, wenn der Prewarm-Token leer war oder alle Blitz-Wellen daneben
        # lagen. Verhält sich dann exakt wie bisher – nur ohne Court-Alternieren
        # (User-Vorgabe: nur aktueller Court).
        if not ok:
            konflikte = 0
            for versuch in range(30):
                if not aktiv():
                    return
                if buche_slot(k, ziel_slot):
                    ok = True
                    break
                # GODMODE2: Dauerkonflikt = Ziel ist fest vergeben (Log 08.07.
                # 16:16: alle Wellen + 30 Fallback-Versuche konfliktet, Slot
                # war weg). Dann nicht minutenlang hämmern, sondern SOFORT zum
                # Rollback – nur so ist die alte Buchung evtl. noch zu retten.
                # Die Storno-Propagation (~1s) ist hier längst vorbei (die
                # Burst-Wellen liefen bereits davor).
                if _KONFLIKT_FLAG.get(f"{k}:{blitz_court}"):
                    konflikte += 1
                    if konflikte >= 3:
                        log.warning(f"⛔ [{k}] Schiebe-Fallback: {konflikte}× Konflikt "
                                    f"in Folge – Ziel fest vergeben → Rollback.")
                        break
                else:
                    konflikte = 0
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
            # V2.1 FIX C: Der Server kann beim Storno 200 liefern, OHNE wirklich
            # zu stornieren (Status-Code allein ist kein Beweis). Dann würde der
            # Rollback unten ewig am Selbst-Konflikt scheitern. Erst prüfen, ob
            # die alte Buchung noch in my-bookings steht → dann einfach behalten.
            noch_da = verifiziere_slot_via_my_bookings(k, aktive_b)
            if noch_da:
                az_set(k, "aktive_buchung", noch_da)
                beende(f"⚠️ [{k}] Neubuchung {naechster_von}–{naechster_bis} "
                       f"fehlgeschlagen, aber der Storno hatte NICHT gegriffen – "
                       f"alte Buchung {aktive_b['fromTime']}–{aktive_b['toTime']} "
                       f"besteht noch.\n"
                       f"✅ Zustand wiederhergestellt, Schieben gestoppt.")
                return
            # GODMODE2 (Schutz 2) – ROLLBACK: nie mit leeren Händen dastehen.
            # Der alte Slot wurde gerade erst storniert und ist sehr
            # wahrscheinlich noch frei → sofort zurückholen.
            senden(f"⚠️ [{k}] Neubuchung {naechster_von}–{naechster_bis} fehlgeschlagen – "
                   f"hole alte Buchung {aktive_b['fromTime']}–{aktive_b['toTime']} zurück...")
            alter_slot = _baue_slot_dict(
                gerade_court, aktive_b["fromTime"], aktive_b["toTime"],
                datum_de, datum_api,
                dauer_minuten(aktive_b["fromTime"], aktive_b["toTime"]))
            rollback = False
            for _rb in range(10):
                if not aktiv():
                    break
                if buche_slot(k, alter_slot):
                    rollback = True
                    break
                time.sleep(1)
            if rollback:
                beende(f"🛟 [{k}] Rollback OK: {aktive_b['fromTime']}–{aktive_b['toTime']} "
                       f"(Court {gerade_court}) wieder gebucht – Schieben gestoppt.")
            else:
                beende(f"❌ [{k}] Neubuchung UND Rollback fehlgeschlagen!\n"
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
        return _schlafe_solange(aktiv, sek)

    def beende(msg: str = ""):
        _schiebe_beende(k, msg)

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

            warte_str_w = _format_restzeit(sek_bis)

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
      - Hämmere alle SNIPER_PHASE1_INTERVAL (0.25s) mit buche_slot (STRIKT)
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
            # V2.1 FIX A: laufenden Sniper-Thread als schiebe_thread übernehmen.
            # Sonst hält acc[k] evtl. noch einen TOTEN alten Schiebe-Thread und
            # Sync/Statuslabel setzen schiebe_aktiv=False → Phase 3 stirbt still.
            schiebe_thread=threading.current_thread(),
        )
        _schiebe_phase3(k, datum_de, datum_api, dauer_min, ziel_str)

    # ── Phase 0: Schlafen bis Login-Refresh ─────────────────────────────────
    if jetzt_lokal() < login_refresh_dt:
        if not schlafe_bis(login_refresh_dt):
            _sniper_stopp(k, f"⏹️ [{k}] Sniper gestoppt (Phase 0).")
            return

    if not aktiv():
        _sniper_stopp(k)
        return

    senden(f"🔑 [{k}] Frischer Login vor Lauer-Start...")
    if not _session_refresh_vor_aktion(k, "Sniper Lauer-Start"):
        _sniper_stopp(k, f"❌ [{k}] Sniper: Login fehlgeschlagen!")
        return

    # Warten bis Lauer-Start
    if jetzt_lokal() < lauer_start_dt:
        if not schlafe_bis(lauer_start_dt):
            _sniper_stopp(k, f"⏹️ [{k}] Sniper gestoppt (vor Lauer-Start).")
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
                    _sniper_stopp(k, f"❌ [{k}] Sniper P1: Login fehlgeschlagen.")
                    return
            letzter_login = time.time()

        # Kein neuer Versuch, wenn er in den Pre-Warm-Bereich hineinlaufen würde.
        if (prewarm_dt - jetzt_lokal()).total_seconds() < MIN_REST_FOR_BUCHE:
            break

        if SPAM_COMMIT_AKTIV:
            # V17: leichtes "Weiter"-Antippen statt schwerer Voll-Buchung. Solange
            # der Fremde drin ist → bleibt auf s1 (belegt); storniert er → springt
            # auf s2 → sofort buchen. Schneller UND server-schonender. In Chunks
            # (~50s), damit der 60s-Session-Refresh oben dazwischen greift.
            rest = (prewarm_dt - jetzt_lokal()).total_seconds()
            chunk_deadline = time.time() + min(50.0, max(0.0, rest))
            ausgang, buchung = _spam_weiter_commit(
                k, court, p1_slot, chunk_deadline, aktiv, label="Sniper-P1")
            versuche += 1
            if ausgang == "HIT":
                az_set(k, "aktive_buchung", buchung)
                trigger_phase3(buchung, "Phase 1 Lauer", versuche)
                return
            if ausgang == "FALLBACK":
                # evtl. Token/Session-Problem → einmal frisch prüfen, dann weiter lauern
                if not ist_eingeloggt(k):
                    einloggen(k)
                    letzter_login = time.time()
                time.sleep(SNIPER_PHASE1_INTERVAL)
            # CONFLICT → gerade fremd geschnappt; weiter lauern (kann wieder frei werden)
            continue

        if buche_slot(k, p1_slot):
            treffer = az_get(k, "aktive_buchung")
            if treffer:
                trigger_phase3(treffer, "Phase 1 Lauer", versuche + 1)
                return

        versuche += 1
        time.sleep(SNIPER_PHASE1_INTERVAL)

    if not aktiv():
        _sniper_stopp(k, f"⏹️ [{k}] Sniper gestoppt nach Phase 1 ({versuche} Versuche).")
        return

    # ── Phase 2: Pre-Warm bei T-10s, Burst exakt bei T-0 (ms-Präzision) ────
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

    # ── V17: SPAM-COMMIT ZUERST (Weiter-Dauerfeuer bis der Anschluss-Slot
    #    aufspringt → sofort buchen). Gleiche Mechanik wie 07:00-Blitz. ──────
    if SPAM_COMMIT_AKTIV:
        spam_deadline = time.time() + max(0.0, (deadline_dt - jetzt_lokal()).total_seconds())
        ausgang, buchung = _spam_weiter_commit(
            k, court, p2_slot, spam_deadline, aktiv, execution=execution,
            label="Sniper-P2")
        if ausgang == "HIT":
            trigger_phase3(buchung, "Phase 2 Blitz", versuche + 1)
            return
        if ausgang == "CONFLICT":
            _sniper_stopp(k, f"⛔ [{k}] Sniper Phase 2: Anschluss-Slot {p2_von}–{p2_bis} "
                             f"(Court {court}) wurde von jemand anderem gebucht.")
            return
        # FALLBACK → klassische Burst-Wellen unten (execution evtl. verbraucht → neu)
        execution = None
        log.info(f"[{k}] Sniper P2 Spam → Fallback auf klassische Bursts")

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

    _sniper_stopp(k, f"❌ [{k}] Sniper-Deadline erreicht. Fremder hat nicht storniert und "
                     f"Blitz hat den frisch freigeschalteten Slot nicht erwischt.\n"
                     f"   Phase 1: {versuche} Versuche, Phase 2: {p2_versuche} Bursts.")

# ══════════════════════════════════════════════
# FREITEXT-HANDLER
# ══════════════════════════════════════════════

def handle_text(k: str, text: str):
    flow = az_get(k, "flow") if k else None
    if flow != "direkte_startzeit":
        zeige_account_auswahl()
        return

    buchbar_ab = _parse_startzeit(text)
    if not buchbar_ab:
        return
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
        frei_txt = ("⏳ Freischaltung in "
                    f"{_format_restzeit((unlock_dt - jetzt).total_seconds())}")

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
# V14: GEMEINSAME 2-ACCOUNT-AUSWAHL (Duo/Safe/3h – vorher 3× dupliziert)
# ══════════════════════════════════════════════

def _paar_start(prefix: str, modus_name: str, intro: str, frage_a: str,
                reset_fn) -> None:
    """Schritt 1 der 2-Account-Flows: braucht 2 freie Accounts, zeigt die
    Auswahl-Liste für Account A ({prefix}_pa_...)."""
    frei = [k for k in ACCOUNTS if _account_frei(k)]
    if len(frei) < 2:
        senden(f"{modus_name} braucht <b>2 freie Accounts</b> "
               "(ohne aktive Buchung/Schiebe/Sniper).")
        zeige_account_auswahl()
        return
    reset_fn()
    btns = [[{"text": account_status_label(k), "callback_data": f"{prefix}_pa_{k}"}]
            for k in frei]
    btns.append([{"text": "❌ Abbrechen", "callback_data": f"{prefix}_cancel"}])
    senden(f"{intro}\n\n{frage_a}", buttons=btns)


def _paar_cancel(reset_fn, msg: str) -> None:
    reset_fn()
    senden(msg)
    zeige_account_auswahl()


def _paar_pa(prefix: str, modus_kurz: str, k: str, lock, state: dict,
             reset_fn, frage_b_fn) -> None:
    """Schritt 2: Account A validieren/speichern, Auswahl-Liste für Account B.
    frage_b_fn(k) liefert den Fragetext für die B-Auswahl."""
    if k not in acc or not _account_frei(k):
        senden(f"❌ Account nicht (mehr) frei. Bitte {modus_kurz} neu starten.")
        reset_fn()
        zeige_account_auswahl()
        return
    with lock:
        state["acc_a"] = k
    rest = [x for x in ACCOUNTS if x != k and _account_frei(x)]
    if not rest:
        senden("❌ Kein zweiter freier Account verfügbar.")
        reset_fn()
        zeige_account_auswahl()
        return
    btns = [[{"text": account_status_label(x), "callback_data": f"{prefix}_pb_{x}"}]
            for x in rest]
    btns.append([{"text": "❌ Abbrechen", "callback_data": f"{prefix}_cancel"}])
    senden(frage_b_fn(k), buttons=btns)


def _paar_pb(modus_kurz: str, k: str, lock, state: dict, reset_fn) -> str | None:
    """Schritt 3: Account B validieren/speichern. Liefert acc_a oder None
    (die Fehlermeldung wurde dann bereits gesendet)."""
    with lock:
        a = state["acc_a"]
    if not a:
        senden(f"❌ {modus_kurz}-Flow unterbrochen – bitte neu starten.")
        reset_fn()
        zeige_account_auswahl()
        return None
    if k == a or k not in acc or not _account_frei(k):
        senden("❌ Bitte einen ANDEREN freien Account wählen.")
        return None
    with lock:
        state["acc_b"] = k
    return a


# ══════════════════════════════════════════════
# DUO-MODUS (2 Accounts parallel, Basis = Direkte Taktik)
# ══════════════════════════════════════════════

def handle_duo_callback(data: str):
    """Verarbeitet alle 'duo_*'-Callbacks (Account-Auswahl → Datum → Ziel)."""
    if data == "duo_start":
        _paar_start("duo", "👥 <b>Duo-Modus</b>",
                    "👥 <b>Duo-Modus</b> – 2 Accounts parallel auf Court 1 + Court 2",
                    "Wähle den <b>1. Account</b> → 🏟️ <b>Court 1</b>:", _duo_reset)
        return

    if data == "duo_cancel":
        _paar_cancel(_duo_reset, "↩️ Duo-Modus abgebrochen.")
        return

    if data.startswith("duo_pa_"):
        _paar_pa("duo", "Duo", data[len("duo_pa_"):], _duo_lock, _duo, _duo_reset,
                 lambda ka: (f"👥 Duo | 🏟️ Court 1: <b>{ka}</b>\n\n"
                             f"Wähle den <b>2. Account</b> → 🏟️ <b>Court 2</b>:"))
        return

    if data.startswith("duo_pb_"):
        k = data[len("duo_pb_"):]
        a = _paar_pb("Duo", k, _duo_lock, _duo, _duo_reset)
        if a is None:
            return
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
    buchbar_ab = _parse_startzeit(text)
    if not buchbar_ab:
        return
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
        frei_txt = ("⏳ Freischaltung in "
                    f"{_format_restzeit((unlock_dt - jetzt).total_seconds())}")

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
# SAFE-MODUS (2 Accounts wechseln sich EINEN Court-Slot ab)
# ══════════════════════════════════════════════
# Zwei Accounts halten EINEN gemeinsamen Slot auf EINEM Court und schieben ihn
# abwechselnd Richtung Ziel. Immer der FREIE Partner blitzt drauf, nie der, der
# gerade storniert hat. Zwei Strategien:
#   "uebergabe": Halter storniert → Partner blitzt sofort auf den (überlappenden)
#                nächsten Slot. Kurzes ~0,3s-Fenster, immer möglich.
#   "leapfrog" : Partner bucht den ANSCHLIESSENDEN (nicht überlappenden) Slot
#                ZUERST (sobald er im 7-Tage-Fenster öffnet = zur alten Slot-Ende-
#                Zeit), DANN storniert der Halter. Nie eine Lücke.
# Bei Fehlschlag probiert NUR der freie Account (Bursts+Fallback), sonst Alarm+Stop.

def _slots_ueberlappen(von1: str, bis1: str, von2: str, bis2: str) -> bool:
    a1 = datetime.strptime(von1, "%H:%M"); a2 = datetime.strptime(bis1, "%H:%M")
    b1 = datetime.strptime(von2, "%H:%M"); b2 = datetime.strptime(bis2, "%H:%M")
    return a1 < b2 and b1 < a2

def _safe_next_slot(from_t: str, to_t: str, dauer_min: int,
                    ziel_dt: datetime, schluss: datetime, strategie: str):
    """Nächster Slot Richtung Ziel. leapfrog = anschließend (keine Überlappung),
    uebergabe = 30-Min-Überlappung wie klassisch. None wenn nach Schluss."""
    ende_dt = datetime.strptime(to_t, "%H:%M")
    if strategie == "leapfrog":
        neuer_start = ende_dt
    else:
        neuer_start = ende_dt - timedelta(minutes=SAFE_UEBERLAPP_MIN)
    if neuer_start >= ziel_dt:
        neuer_start = ziel_dt
    neues_ende = neuer_start + timedelta(minutes=dauer_min)
    if neues_ende > schluss:
        return None
    return neuer_start.strftime("%H:%M"), neues_ende.strftime("%H:%M")

def _safe_grab(k: str, court: int, datum_api: str, von: str, bis: str,
               ziel_slot: dict, prewarm: str | None) -> bool:
    """Freier Account schnappt den Slot: Blitz-Burst (vorgewärmt) + Multi-Shot,
    dann Fallback buche_slot. True nur nach my-bookings-Verifikation (Eigentum)."""
    # V17: Spam-Commit zuerst (Weiter-Dauerfeuer bis der überlappende Slot nach
    # dem Storno frei ist → sofort buchen). Kein Treffer → bewährter Ablauf unten.
    if SPAM_COMMIT_AKTIV:
        spam_deadline = time.time() + SPAM_DEADLINE_S
        ausgang, buchung = _spam_weiter_commit(
            k, court, ziel_slot, spam_deadline,
            lambda: az_get(k, "schiebe_aktiv"), execution=prewarm, label="Safe-Spam")
        if ausgang == "HIT":
            az_set(k, "aktive_buchung", buchung)
            return True
        prewarm = None   # Prewarm-Token ist nach dem Spam verbraucht
    execution = prewarm
    for _welle in range(MULTI_SHOT_COUNT + 1):
        if not az_get(k, "schiebe_aktiv"):
            return False
        if not execution:
            execution = pre_warm_r1(k, court, datum_api, von, bis)
            if not execution:
                time.sleep(MULTI_SHOT_GAP_MS / 1000.0)
                continue
        erfolg, _bd = burst_r2_r3(k, court, execution, ziel_slot)
        if erfolg:
            v = verifiziere_slot_via_my_bookings(k, ziel_slot)
            if v:
                az_set(k, "aktive_buchung", v)
                return True
        execution = pre_warm_r1(k, court, datum_api, von, bis)
        time.sleep(MULTI_SHOT_GAP_MS / 1000.0)
    # Fallback: klassischer buche_slot (verifiziert selbst über my-bookings)
    for _v in range(20):
        if not az_get(k, "schiebe_aktiv"):
            return False
        if buche_slot(k, ziel_slot):
            return True
        time.sleep(0.2)
    return bool(az_get(k, "aktive_buchung"))

def _safe_storno(k: str, booking_id, datum_api: str) -> bool:
    # V2.1 FIX D: fehlende booking_id ist KEIN Erfolg (vorher return True →
    # der Partner blitzte auf den überlappenden Slot, während die alte Buchung
    # noch stand). Erst versuchen, die ID aus my-bookings nachzuladen.
    if not booking_id:
        ab = az_get(k, "aktive_buchung")
        v  = verifiziere_slot_via_my_bookings(k, ab) if ab else None
        if v and v.get("booking_id"):
            booking_id = v["booking_id"]
            az_set(k, "aktive_buchung", v)
            log.info(f"[{k}] Safe-Storno: booking_id nachgeladen: {booking_id}")
        else:
            log.warning(f"[{k}] Safe-Storno: keine booking_id ermittelbar → Fehlschlag.")
            return False
    # WICHTIG: Frische Session ERZWINGEN vor dem Storno – genau wie der klassische
    # Schiebe-Storno ("Erzwungener Login vor Stornierung"). Zwischen Blitz und Storno
    # liegen im Safe-/3h-Modus oft >1h → die alte Session ist tot → sonst 401
    # Unauthorized (INVALID_REQUEST), egal wie oft man retryt.
    _session_refresh_vor_aktion(k, "Safe-Storno")
    for _v in range(6):
        if not az_get(k, "schiebe_aktiv"):
            return False
        if storniere_buchung(k, booking_id, datum_api):
            az_set(k, "aktive_buchung", None)
            return True
        # Bei erneutem Fehlschlag Session nochmal auffrischen (könnte wieder abgelaufen sein)
        if _v == 2:
            _session_refresh_vor_aktion(k, "Safe-Storno-Retry")
        time.sleep(2)
    return False

def _safe_blitz_hartnaeckig(k: str, court: int, datum_de: str, datum_api: str,
                            dauer_min: int, race_dt: datetime, von: str, bis: str,
                            weiter_sec: int = 120) -> bool:
    """Nutzt EXAKT den bewährten Direkt-Blitz `_direkt_blitz` (Pre-Warm r1 @T-10s,
    millisekundengenauer Burst r2+r3 @T-0, Multi-Shot, my-bookings-Verifikation) –
    hier auf 1 Court und für den EXPLIZITEN Slot [von,bis] (z.B. 30-Min-Füller).
    race_dt = exakter Feuer-Zeitpunkt (T-0); liegt er in der Vergangenheit, feuert
    _direkt_blitz sofort. Verfehlt der Blitz, wird HARTNÄCKIG weiter versucht
    (buche_slot) bis Treffer oder weiter_sec. True nur bei verifizierter EIGENER Buchung."""
    if (_direkt_blitz(k, datum_de, datum_api, dauer_min, race_dt, [court],
                      bevorzugter_court=court, von=von, bis=bis)
            and az_get(k, "aktive_buchung")):
        return True
    ziel_slot = _baue_slot_dict(court, von, bis, datum_de, datum_api, dauer_min)
    ende = time.time() + weiter_sec
    konflikte = 0
    while time.time() < ende:
        if not az_get(k, "schiebe_aktiv"):
            return False
        if buche_slot(k, ziel_slot):
            return True
        # GODMODE: Server-Konflikt = Slot gehört jemand anderem → nicht 2 Min
        # sinnlos weiterhämmern (DoS-Gefahr!), sondern nach N Konflikten stoppen.
        if _KONFLIKT_FLAG.get(f"{k}:{court}"):
            konflikte += 1
            if konflikte >= KONFLIKT_STOP_N:
                log.warning(f"⛔ [{k}] {von}–{bis} Court {court}: {konflikte}× Konflikt "
                            f"in Folge – Slot fremd vergeben, Dauerversuche gestoppt.")
                senden(f"⛔ [{k}] Slot {von}–{bis} (Court {court}, {datum_de}) wurde "
                       f"von jemand anderem gebucht – Versuche gestoppt.")
                # V2.1 FIX D: nur der KONKRETE Ziel-Slot zählt als Erfolg
                # (vorher reichte irgendeine aktive Buchung des Accounts).
                v = verifiziere_slot_via_my_bookings(k, ziel_slot)
                if v:
                    az_set(k, "aktive_buchung", v)
                    return True
                return False
        else:
            konflikte = 0
        time.sleep(1)
    # V2.1 FIX D: Erfolg nur bei verifiziertem ZIEL-Slot (siehe oben).
    v = verifiziere_slot_via_my_bookings(k, ziel_slot)
    if v:
        az_set(k, "aktive_buchung", v)
        return True
    return False

def _safe_schiebe_loop(a: str, b: str, court: int, datum_de: str, ziel_str: str,
                       dauer_min: int, buchbar_ab: str, strategie: str):
    datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
    datum_api = datum_obj.strftime("%m/%d/%Y")
    ziel_dt   = datetime.strptime(ziel_str, "%H:%M")
    schluss   = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")
    strat_lbl = "Leapfrog" if strategie == "leapfrog" else "Übergabe"

    def aktiv() -> bool:
        return bool(az_get(a, "schiebe_aktiv") and az_get(b, "schiebe_aktiv"))

    def schlafe(sek: float) -> bool:
        return _schlafe_solange(aktiv, sek)

    try:
        # ── Phase 1: warten auf Freischaltung, dann A blitzt Initial-Slot ──
        fenster_tag = (datum_obj - timedelta(days=7)).date()
        unlock_dt   = datetime.combine(fenster_tag,
                                       datetime.strptime(buchbar_ab, "%H:%M").time())
        ziel_wach   = unlock_dt - timedelta(seconds=PHASE1_HANDOFF_MARGIN)
        while aktiv() and jetzt_lokal() < ziel_wach:
            if not schlafe(30):
                return
        if not aktiv():
            return

        senden(f"🛡️ <b>Safe-Modus – Start ({strat_lbl})</b>\n"
               f"🏟️ Court {court} | 📅 {_datum_mit_tag(datum_de)} | 🎯 {ziel_str} Uhr\n"
               f"🔓 Buchbar ab {unlock_dt.strftime('%d.%m. %H:%M')} – {a} blitzt zuerst.")

        for k in (a, b):
            if not _session_refresh_vor_aktion(k, f"Safe-Init {buchbar_ab}"):
                senden(f"❌ Safe: Login {k} vor Start fehlgeschlagen.")
                return

        jetzt = jetzt_lokal()
        buchbar_dt = unlock_dt if unlock_dt > jetzt else jetzt + timedelta(seconds=1)
        erfolg = _direkt_blitz(a, datum_de, datum_api, dauer_min,
                               buchbar_dt, [court], bevorzugter_court=court)
        if not erfolg or not az_get(a, "aktive_buchung"):
            senden(f"❌ Safe-Modus: Initial-Buchung durch {a} fehlgeschlagen.\n"
                   f"🆘 {BASE_URL}/padel?currentDate={datum_api}")
            return

        halter, frei = a, b
        hb0 = az_get(a, "aktive_buchung")
        senden(f"🛡️ <b>Safe-Modus läuft</b> ({strat_lbl})\n"
               f"🔴 Hält: {halter} ({hb0['fromTime']}–{hb0['toTime']}) | Court {court}\n"
               f"🟢 Frei: {frei}\n🎯 Ziel: {ziel_str} Uhr")

        # ── Phase 2: abwechselnd schieben ──
        while aktiv():
            hb = az_get(halter, "aktive_buchung")
            if not hb:
                senden(f"❌ Safe: {halter} hält keine Buchung mehr – gestoppt.")
                return

            if datetime.strptime(hb["fromTime"], "%H:%M") >= ziel_dt:
                wetter = hole_wetter(hb["datum_de"], hb["fromTime"]) or ""
                senden(f"🎯 <b>Safe-Modus: Ziel erreicht!</b>\n"
                       f"🔴 {halter} hält {hb['fromTime']}–{hb['toTime']} | Court {court}\n"
                       f"📅 {_datum_mit_tag(hb['datum_de'])}\n\nViel Spaß! 🎾" + wetter)
                return

            nxt = _safe_next_slot(hb["fromTime"], hb["toTime"], dauer_min,
                                  ziel_dt, schluss, strategie)
            if nxt is None:
                senden(f"⚠️ Safe: nächster Slot würde nach {ANLAGE_SCHLUSS} enden.\n"
                       f"✅ {halter} behält {hb['fromTime']}–{hb['toTime']}.")
                return
            von, bis  = nxt
            ziel_slot = _baue_slot_dict(court, von, bis, datum_de, datum_api, dauer_min)
            ueberlappt = _slots_ueberlappen(hb["fromTime"], hb["toTime"], von, bis)
            # Leapfrog nur ohne Überlappung; sonst (z.B. letzter Hop ans Ziel) Übergabe.
            leapfrog = (strategie == "leapfrog" and not ueberlappt)

            # ── LEAPFROG: der freie Account blitzt den anschließenden Slot mit
            #    EXAKTEM Timing – echter _direkt_blitz (Pre-Warm r1 bei T-10s, Burst
            #    exakt bei T-0), GENAU wie "Direkt-Modus bekannte Uhrzeit". Dieser
            #    Slot öffnet erst zu SEINER Startzeit heute → echtes T-0-Rennen.
            #    Erst wenn der freie ihn SICHER hat, storniert der alte Halter. ────
            if leapfrog:
                unlock_next = datetime.combine(jetzt_lokal().date(),
                                               datetime.strptime(von, "%H:%M").time())
                senden(f"⏳ [Safe-Leapfrog] {frei} blitzt {von}–{bis} exakt um {von} Uhr\n"
                       f"🔴 {halter} hält solange {hb['fromTime']}–{hb['toTime']}")
                # bis kurz vor Slot-Öffnung warten (Session am Leben halten)
                while aktiv():
                    rest = (unlock_next - jetzt_lokal()).total_seconds()
                    if rest <= PHASE1_HANDOFF_MARGIN:
                        break
                    if not schlafe(min(rest - PHASE1_HANDOFF_MARGIN, 30)):
                        return
                if not aktiv():
                    return
                if not _session_refresh_vor_aktion(frei, f"Safe-Leapfrog {von}"):
                    senden(f"❌ Safe (Leapfrog): Login {frei} fehlgeschlagen – "
                           f"{halter} hält weiter {hb['fromTime']}–{hb['toTime']} – gestoppt.")
                    return
                # Exakt der Blitz-Pfad der Direkt-Buchung (Pre-Warm r1 @T-10s, Burst @T-0)
                # + hartnäckig dranbleiben, falls der erste Burst verfehlt.
                erfolg = _safe_blitz_hartnaeckig(frei, court, datum_de, datum_api,
                                                 dauer_min, unlock_next, von, bis)
                if not erfolg or not az_get(frei, "aktive_buchung"):
                    senden(f"❌ Safe (Leapfrog): {frei} bekam {von}–{bis} nicht.\n"
                           f"✅ {halter} hält weiter {hb['fromTime']}–{hb['toTime']} – gestoppt.\n"
                           f"🆘 {BASE_URL}/padel?currentDate={datum_api}")
                    return
                # Freier hat den neuen Slot SICHER. Kein Stress: der alte Slot hat
                # noch ~90 Min. Erst nach kurzer Wartezeit stornieren – solange
                # halten BEIDE ihren Block (kurzzeitig 3h Abdeckung).
                senden(f"⏸️ [Safe-Leapfrog] {frei} hat {von}–{bis} sicher.\n"
                       f"{halter} storniert {hb['fromTime']}–{hb['toTime']} in "
                       f"~{SAFE_CANCEL_DELAY_SEC // 60} Min.")
                if not schlafe(SAFE_CANCEL_DELAY_SEC):
                    return   # gestoppt → beide behalten ihren Block (kein Storno)
                if not _safe_storno(halter, hb.get("booking_id"), datum_api):
                    senden(f"⚠️ Safe (Leapfrog): Storno des alten Slots ({halter}, "
                           f"{hb['fromTime']}–{hb['toTime']}) fehlgeschlagen – bitte manuell "
                           f"löschen. Neuer Slot läuft weiter.")

            # ── ÜBERGABE: Halter storniert ZUERST, dann Freier blitzt auf den
            #    (überlappenden, längst offenen) Slot. Kurzes ~0,3s-Fenster. ──────
            else:
                off = random.randint(SCHIEBE_MINUTEN_VOR_MIN, SCHIEBE_MINUTEN_VOR_MAX)
                ende_dt = datetime.strptime(hb["toTime"], "%H:%M")
                schiebe_moment = datetime.combine(
                    jetzt_lokal().date(), (ende_dt - timedelta(minutes=off)).time())
                if (schiebe_moment - jetzt_lokal()).total_seconds() > 0:
                    senden(f"⏳ [Safe-Übergabe] Nächster Schub um "
                           f"{schiebe_moment.strftime('%H:%M')} Uhr\n"
                           f"🔴 {halter}: {hb['fromTime']}–{hb['toTime']} → "
                           f"🟢 {frei}: {von}–{bis}")
                    while aktiv():
                        rest = (schiebe_moment - jetzt_lokal()).total_seconds()
                        if rest <= 2:
                            break
                        if not schlafe(min(rest - 1, 30)):
                            return
                if not aktiv():
                    return
                for k in (halter, frei):
                    _session_refresh_vor_aktion(k, f"Safe-Übergabe {von}")
                prewarm = pre_warm_r1(frei, court, datum_api, von, bis)
                if not _safe_storno(halter, hb.get("booking_id"), datum_api):
                    if not verifiziere_slot_via_my_bookings(halter, hb):
                        az_set(halter, "aktive_buchung", None)
                    senden(f"❌ Safe (Übergabe): Storno von {halter} fehlgeschlagen – gestoppt.\n"
                           f"🆘 {BASE_URL}/padel?currentDate={datum_api}")
                    return
                if not _safe_grab(frei, court, datum_api, von, bis, ziel_slot, prewarm):
                    # V2.1 FIX C: prüfen, ob der Storno überhaupt gegriffen hat –
                    # steht die alte Buchung noch, hält der Halter sie einfach weiter.
                    noch_da = verifiziere_slot_via_my_bookings(halter, hb)
                    if noch_da:
                        az_set(halter, "aktive_buchung", noch_da)
                        senden(f"⚠️ Safe (Übergabe): {frei} bekam {von}–{bis} nicht, "
                               f"aber der Storno hatte NICHT gegriffen – {halter} hält "
                               f"weiter {hb['fromTime']}–{hb['toTime']}. Gestoppt.")
                        return
                    senden(f"❌ Safe (Übergabe): {frei} bekam {von}–{bis} nach Storno NICHT.\n"
                           f"🆘 SOFORT manuell: {BASE_URL}/padel?currentDate={datum_api}")
                    return

            # Rollen tauschen: der freie hält jetzt, der alte Halter wird frei
            halter, frei = frei, halter
            nb = az_get(halter, "aktive_buchung")
            senden(f"✅ <b>Safe: {'Gesprungen' if leapfrog else 'Übergeben'}!</b>\n"
                   f"🔴 Hält jetzt: {halter} ({nb['fromTime']}–{nb['toTime']}) | Court {court}\n"
                   f"🟢 Frei: {frei}\n🔄 Weiter → {ziel_str} Uhr")

    except Exception as e:
        log.error(f"[Safe {a}/{b}] CRASH: {e}", exc_info=True)
        senden(f"💥 <b>Safe-Modus abgestürzt!</b>\n{e}")
    finally:
        az_set(a, "schiebe_aktiv", False)
        az_set(b, "schiebe_aktiv", False)
        zeige_account_auswahl()


def _safe3h_loop(a: str, b: str, court: int, datum_de: str, ziel_str: str,
                 buchbar_ab: str):
    """3-Std-Block: zwei Accounts halten zwei ANEINANDER anschließende 90-Min-Blöcke
    (= 3h) und wandern als 'Fließband' Richtung Ziel-Fenster [ziel, ziel+180].
    Der jeweils unterste Account blitzt den neu öffnenden obersten Block (präzise
    + hartnäckig), erst danach (nach kurzer Wartezeit) storniert er seinen alten
    untersten Block → nie eine Lücke. Stopp, sobald beide Ziel-Blöcke gehalten werden.
    Startblock wird automatisch rückwärts vom Ziel eingerastet."""
    datum_obj = datetime.strptime(datum_de, "%d.%m.%Y")
    datum_api = datum_obj.strftime("%m/%d/%Y")
    ziel_dt   = datetime.strptime(ziel_str, "%H:%M")
    buch_dt   = datetime.strptime(buchbar_ab, "%H:%M")
    schluss   = datetime.strptime(ANLAGE_SCHLUSS, "%H:%M")
    fenster_tag = (datum_obj - timedelta(days=7)).date()

    def aktiv() -> bool:
        return bool(az_get(a, "schiebe_aktiv") and az_get(b, "schiebe_aktiv"))

    def schlafe(sek: float) -> bool:
        return _schlafe_solange(aktiv, sek)

    def hhmm(dt: datetime) -> str:
        return dt.strftime("%H:%M")

    def unlock(dt: datetime) -> datetime:
        return datetime.combine(fenster_tag, dt.time())

    def warte_bis(ziel_dt2: datetime) -> bool:
        """Bis ~PHASE1_HANDOFF_MARGIN vor ziel_dt2 warten (Session am Leben halten)."""
        while aktiv():
            rest = (ziel_dt2 - jetzt_lokal()).total_seconds()
            if rest <= PHASE1_HANDOFF_MARGIN:
                return True
            if not schlafe(min(rest - PHASE1_HANDOFF_MARGIN, 30)):
                return False
        return False

    def blitz(k: str, von: str, bis: str, open_dt: datetime) -> bool:
        if not aktiv():
            return False
        if not _session_refresh_vor_aktion(k, f"Safe3h {von}"):
            return False
        return _safe_blitz_hartnaeckig(k, court, datum_de, datum_api,
                                       dauer_minuten(von, bis), open_dt, von, bis)

    try:
        if ziel_dt + timedelta(minutes=180) > schluss:
            senden(f"⚠️ Safe-3h: Ziel {ziel_str}–{hhmm(ziel_dt + timedelta(minutes=180))} "
                   f"läge nach {ANLAGE_SCHLUSS}. Bitte früheres Ziel wählen.")
            return

        # ── Blockfolge bauen: Sprungbrett-Blöcke (auch 30/60 Min!) von buchbar_ab
        #    bis zum Ziel, sodass der LETZTE Sprungbrett-Block EXAKT auf {ziel}
        #    endet → danach sauber (ohne Überlappung) in die zwei 90-Min-Ziel-Blöcke
        #    [ziel..+90] und [ziel+90..+180]. Nur die letzten ZWEI bleiben (= 3h);
        #    alle davor sind Sprungbretter und werden beim Weiterwandern storniert.
        blocks = []
        cur = buch_dt
        while cur < ziel_dt:
            end = min(cur + timedelta(minutes=90), ziel_dt)
            blocks.append((cur, end))
            cur = end
        t2_ende = ziel_dt + timedelta(minutes=180)
        blocks.append((ziel_dt, ziel_dt + timedelta(minutes=90)))            # Ziel-Block 1
        blocks.append((ziel_dt + timedelta(minutes=90), t2_ende))            # Ziel-Block 2

        plan = " → ".join(f"{hhmm(s)}-{hhmm(e)}" for s, e in blocks)
        senden(f"🧱 <b>Safe 3-Std-Block – Start</b>\n"
               f"🏟️ Court {court} | 📅 {_datum_mit_tag(datum_de)}\n"
               f"🎯 Ziel-Fenster: {ziel_str}–{hhmm(t2_ende)} (2×90 Min)\n"
               f"🪜 Plan: {plan}\n"
               f"(nur die letzten zwei Blöcke bleiben – der Rest sind Sprungbretter)")

        # ── Block 0: Initial-Blitz durch A ─────────────────────────────────────
        s0, e0 = blocks[0]
        if not warte_bis(unlock(s0)):
            return
        if not blitz(a, hhmm(s0), hhmm(e0), unlock(s0)) or not az_get(a, "aktive_buchung"):
            senden(f"❌ Safe-3h: {a} bekam Startblock {hhmm(s0)}–{hhmm(e0)} nicht – gestoppt.")
            return
        holder, frei = a, b
        prev_buchung = az_get(a, "aktive_buchung")   # zuletzt gegriffener Block (vom holder)

        # ── Durch die Blockfolge: der FREIE Account blitzt den nächsten Block bei
        #    dessen Öffnung, dann (nach ~5 Min) storniert der bisherige seinen alten
        #    Block. Beim ALLERLETZTEN Block wird NICHT storniert → die beiden
        #    Ziel-Blöcke bleiben gehalten (= 3h). Nie >1 Buchung pro Account. ──────
        for i in range(1, len(blocks)):
            si, ei = blocks[i]
            is_last = (i == len(blocks) - 1)
            if not warte_bis(unlock(si)):
                return
            if not blitz(frei, hhmm(si), hhmm(ei), unlock(si)) or not az_get(frei, "aktive_buchung"):
                senden(f"❌ Safe-3h: {frei} bekam {hhmm(si)}–{hhmm(ei)} nicht.\n"
                       f"✅ {holder} hält weiter {prev_buchung['fromTime']}–{prev_buchung['toTime']} "
                       f"– gestoppt.\n🆘 {BASE_URL}/padel?currentDate={datum_api}")
                return
            neu_buchung = az_get(frei, "aktive_buchung")
            if not is_last:
                # kein Stress: kurz halten beide, dann Vorgänger-Block freigeben
                senden(f"⏸️ Safe-3h: {frei} hat {hhmm(si)}–{hhmm(ei)}. "
                       f"{holder} gibt {prev_buchung['fromTime']}–{prev_buchung['toTime']} "
                       f"in ~{SAFE_CANCEL_DELAY_SEC // 60} Min frei.")
                if not schlafe(SAFE_CANCEL_DELAY_SEC):
                    return
                if not _safe_storno(holder, prev_buchung.get("booking_id"), datum_api):
                    senden(f"⚠️ Safe-3h: Storno {prev_buchung['fromTime']}–{prev_buchung['toTime']} "
                           f"({holder}) fehlgeschlagen – bitte ggf. manuell löschen.")
            holder, frei = frei, holder   # der freie hält jetzt den neuesten Block
            prev_buchung = neu_buchung

        if aktiv():
            hold_t1 = az_get(frei, "aktive_buchung")     # vorletzter Block = Ziel-Block 1
            hold_t2 = az_get(holder, "aktive_buchung")   # letzter Block   = Ziel-Block 2
            senden(f"🎯 <b>Safe-3h: Ziel-Fenster erreicht!</b>\n"
                   f"🔴 {frei}: {hold_t1['fromTime']}–{hold_t1['toTime']}\n"
                   f"🔴 {holder}: {hold_t2['fromTime']}–{hold_t2['toTime']}\n"
                   f"📅 {_datum_mit_tag(datum_de)} | Court {court}\n"
                   f"= {ziel_str}–{hhmm(t2_ende)} 🎾")
    except Exception as e:
        log.error(f"[Safe3h {a}/{b}] CRASH: {e}", exc_info=True)
        senden(f"💥 <b>Safe-3h abgestürzt!</b>\n{e}")
    finally:
        az_set(a, "schiebe_aktiv", False)
        az_set(b, "schiebe_aktiv", False)
        zeige_account_auswahl()


def _starte_safe(a: str, b: str, court: int, datum: str, ziel: str,
                 strategie: str, buchbar_ab: str):
    for k in (a, b):
        az_set_multi(k, schiebe_aktiv=True, duo_court=court, flow=None,
                     schiebe_datum=datum, schiebe_ziel=ziel, schiebe_court=court,
                     schiebe_dauer=DUO_DAUER_MIN, schiebe_modus="safe")
    if strategie == "block3h":
        ziel_dt = datetime.strptime(ziel, "%H:%M")
        senden(f"🧱 <b>Safe 3-Std-Block gestartet!</b>\n"
               f"🏟️ Court {court} | 📅 {_datum_mit_tag(datum)}\n"
               f"🎯 Ziel-Fenster: {ziel}–"
               f"{(ziel_dt + timedelta(minutes=180)).strftime('%H:%M')} Uhr\n"
               f"🔴 {a} + {b} halten am Ende 2 Blöcke (je 90 Min).\n"
               f"🔓 Buchbar ab {buchbar_ab} Uhr.")
        t = threading.Thread(target=_safe3h_loop,
                             args=(a, b, court, datum, ziel, buchbar_ab),
                             daemon=True)
    else:
        strat_lbl = "Leapfrog" if strategie == "leapfrog" else "Übergabe"
        senden(f"🛡️ <b>Safe-Modus gestartet!</b> ({strat_lbl})\n"
               f"🏟️ Court {court} | 📅 {_datum_mit_tag(datum)} | 🎯 {ziel} Uhr | 90 Min\n"
               f"🔴 {a} blitzt zuerst, danach wechseln sich {a} + {b} ab.\n"
               f"🔓 Buchbar ab {buchbar_ab} Uhr.")
        t = threading.Thread(target=_safe_schiebe_loop,
                             args=(a, b, court, datum, ziel, DUO_DAUER_MIN, buchbar_ab, strategie),
                             daemon=True)
    t.start()
    az_set(a, "schiebe_thread", t)
    az_set(b, "schiebe_thread", t)
    zeige_account_auswahl()


def handle_safe_callback(data: str):
    """Verarbeitet alle 'safe_*'-Callbacks (Account-Auswahl → Court → Datum →
    Ziel → Strategie)."""
    if data == "safe_start":
        _paar_start("safe", "🛡️ <b>Safe-Modus</b>",
                    "🛡️ <b>Safe-Modus</b> – 2 Accounts wechseln sich EINEN Slot ab.",
                    "Wähle den <b>1. Account</b> (blitzt zuerst):", _safe_reset)
        return

    if data == "safe_cancel":
        _paar_cancel(_safe_reset, "↩️ Safe-Modus abgebrochen.")
        return

    if data.startswith("safe_pa_"):
        _paar_pa("safe", "Safe", data[len("safe_pa_"):], _safe_lock, _safe, _safe_reset,
                 lambda ka: (f"🛡️ Safe | 1. Account: <b>{ka}</b>\n\n"
                             f"Wähle den <b>2. Account</b>:"))
        return

    if data.startswith("safe_pb_"):
        k = data[len("safe_pb_"):]
        a = _paar_pb("Safe", k, _safe_lock, _safe, _safe_reset)
        if a is None:
            return
        btns = [[{"text": "🏟️ Court 1", "callback_data": "safe_court_1"},
                 {"text": "🏟️ Court 2", "callback_data": "safe_court_2"}],
                [{"text": "❌ Abbrechen", "callback_data": "safe_cancel"}]]
        senden(f"🛡️ Safe | {a} + <b>{k}</b>\n\nAuf welchem <b>Court</b>?", buttons=btns)
        return

    if data.startswith("safe_court_"):
        c = int(data[len("safe_court_"):])
        with _safe_lock:
            _safe["court"] = c
            a, b = _safe["acc_a"], _safe["acc_b"]
        if not (a and b):
            senden("❌ Safe-Flow unterbrochen – bitte neu starten.")
            _safe_reset()
            zeige_account_auswahl()
            return
        senden(f"🛡️ Safe | Court {c}\n\n📅 Für welches <b>Datum</b>?",
               buttons=erstelle_datum_buttons("safe_datum"))
        return

    if data.startswith("safe_datum_"):
        d = data[len("safe_datum_"):]
        with _safe_lock:
            _safe["datum"] = d
        senden(f"🛡️ Safe | 📅 {d} | 90 Min\n\n🎯 <b>Bis wohin schieben?</b> (Zielzeit)",
               buttons=zielzeit_buttons("safe_ziel", DUO_DAUER_MIN))
        return

    if data.startswith("safe_ziel_"):
        z = data[len("safe_ziel_"):]
        with _safe_lock:
            _safe["ziel"] = z
        btns = [[{"text": "🤝 Übergabe (1 Block · Storno → Partner blitzt)",
                  "callback_data": "safe_strat_uebergabe"}],
                [{"text": "🐸 Leapfrog (1 Block · Partner sichert vor, dann Storno)",
                  "callback_data": "safe_strat_leapfrog"}],
                [{"text": "🧱 3-Std-Block (2 Accounts halten 2 Blöcke)",
                  "callback_data": "safe_strat_block3h"}],
                [{"text": "❌ Abbrechen", "callback_data": "safe_cancel"}]]
        senden(f"🛡️ Safe | 🎯 {z} Uhr\n\nWelche <b>Strategie</b>?", buttons=btns)
        return

    if data.startswith("safe_strat_"):
        s = data[len("safe_strat_"):]
        with _safe_lock:
            _safe["strategie"] = s
            a, b     = _safe["acc_a"], _safe["acc_b"]
            court    = _safe["court"]
            datum    = _safe["datum"]
            ziel     = _safe["ziel"]
            if a and b and court and datum and ziel:
                _safe["flow"] = "startzeit"
        if not (a and b and court and datum and ziel):
            senden("❌ Safe-Flow unterbrochen – bitte neu starten.")
            _safe_reset()
            zeige_account_auswahl()
            return
        s_lbl = {"block3h": "3-Std-Block", "leapfrog": "Leapfrog"}.get(s, "Übergabe")
        ziel_hint = ""
        if s == "block3h":
            zdt = datetime.strptime(ziel, "%H:%M")
            ziel_hint = (f"\n🧱 Ziel-Fenster: {ziel}–"
                         f"{(zdt + timedelta(minutes=180)).strftime('%H:%M')} Uhr (2×90 Min)")
        senden(f"🛡️ <b>Safe-Modus</b>\n"
               f"{a} + {b} | 🏟️ Court {court}\n"
               f"📅 {datum} | 🎯 {ziel} Uhr | {s_lbl}{ziel_hint}\n\n"
               f"⏰ <b>Ab wann ist der Slot buchbar?</b>\n"
               f"Bitte Uhrzeit tippen (30-Min-Raster, z.B. <b>17:30</b>):")
        return

    senden("❓ Unbekannte Safe-Aktion.")
    _safe_reset()
    zeige_account_auswahl()


def handle_safe_text(text: str):
    """Verarbeitet die getippte Buchbar-ab-Zeit und startet den Safe-Modus."""
    buchbar_ab = _parse_startzeit(text)
    if not buchbar_ab:
        return
    with _safe_lock:
        a         = _safe["acc_a"]
        b         = _safe["acc_b"]
        court     = _safe["court"]
        datum     = _safe["datum"]
        ziel      = _safe["ziel"]
        strategie = _safe["strategie"]
        _safe["flow"] = None
    if not (a and b and court and datum and ziel and strategie):
        senden("❌ Safe-Konfiguration unvollständig – bitte neu starten.")
        _safe_reset()
        zeige_account_auswahl()
        return
    if not _account_frei(a) or not _account_frei(b):
        senden("⚠️ Einer der beiden Accounts ist nicht mehr frei – Safe abgebrochen.")
        _safe_reset()
        zeige_account_auswahl()
        return
    _starte_safe(a, b, court, datum, ziel, strategie, buchbar_ab)
    _safe_reset()


# ══════════════════════════════════════════════
# 3h-MODUS (Block: Acc1 schiebt bis Wunschanfang → Acc2 blitzt Anschluss)
# ══════════════════════════════════════════════

def handle_block_callback(data: str):
    """Verarbeitet alle 'block_*'-Callbacks (Account-Auswahl → Datum → Court →
    Wunschanfang). Acc1 = Schieber (Direkte Taktik bis Wunschanfang),
    Acc2 = Anschluss-Blitz auf den direkt folgenden 90-Min-Slot.
    Baut nur auf bestehenden Bausteinen auf – KERN-CODE unverändert."""
    if data == "block_start":
        _paar_start("block", "🔗 <b>3h-Modus</b>",
                    "🔗 <b>3h-Modus</b> – durchgehender 3-Stunden-Block (2× 90 Min)",
                    "Wähle den <b>1. Account</b> = 🏃 <b>Schieber</b>\n"
                    "<i>(schiebt bis zum Wunschanfang, z.B. 10:30 → 10:30–12:00):</i>",
                    _block_reset)
        return

    if data == "block_cancel":
        _paar_cancel(_block_reset, "↩️ 3h-Modus abgebrochen.")
        return

    if data.startswith("block_pa_"):
        _paar_pa("block", "3h-Modus", data[len("block_pa_"):], _block_lock, _block,
                 _block_reset,
                 lambda ka: (f"🔗 3h | 🏃 Schieber: <b>{ka}</b>\n\n"
                             f"Wähle den <b>2. Account</b> = ⚡ <b>Anschluss-Blitzer</b>:"))
        return

    if data.startswith("block_pb_"):
        k = data[len("block_pb_"):]
        a = _paar_pb("3h", k, _block_lock, _block, _block_reset)
        if a is None:
            return
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
    buchbar_ab = _parse_startzeit(text)
    if not buchbar_ab:
        return
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
        frei_txt = ("⏳ Schieber-Freischaltung in "
                    f"{_format_restzeit((unlock_a - jetzt).total_seconds())}")

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
    # Dasselbe für den Safe-Modus-Eingabeschritt
    if not data.startswith("safe_") and _safe_awaiting_text():
        _safe_reset()

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

    # ── Safe-Modus (eigener Flow über 2 Accounts) – früh abfangen ─────────────
    if data.startswith("safe_"):
        handle_safe_callback(data)
        return

    # V2.1 FIX E: Account-Suffix nur bei echten Account-Menü-Buttons strippen.
    # Vorher kollidierten numerische Account-Labels (z.B. "1", "90") mit
    # Callbacks wie "schiebe_court_1" oder "slots_dauer_90" → falsches Routing.
    _ACC_SUFFIX_PREFIXES = ("menu_", "schiebe_modus_", "storno_bestaetigt")
    k = get_flow_account()
    for ak in ACCOUNTS:
        if data.endswith(f"_{ak}"):
            rest = data[:-(len(ak) + 1)]
            if rest.startswith(_ACC_SUFFIX_PREFIXES):
                k    = ak
                data = rest
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
                   {"text": "🏟️ Court 1", "callback_data": "sniper_court_1"},
                   {"text": "🏟️ Court 2", "callback_data": "sniper_court_2"},
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
                    elif _safe_awaiting_text():
                        handle_safe_text(text)
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
    log.info("🎾 Padel Bot V17 SPAM-COMMIT ÜBERALL – Weiter-Dauerfeuer auch in Sniper + Schiebe-Rebook + Safe")
    log.info("   FIX 1: buche_slot() kein False-Positiv mehr (kein verifiziert=True Fallback)")
    log.info("   FIX 2: Rebook nach Storno: 30× mit 0.1s | Storno-Retry: aktiv()-Check")
    log.info("   NEU 3: Sniper-Modus – sekündlicher Dauerhammer + Schiebe nach Treffer")
    log.info("   Schiebe-Logik: Storno/Neubuchung passiert HEUTE (nicht am Buchungstag!)")
    for k in ACCOUNTS:
        log.info(f"   [{k}] {ACCOUNTS[k]['email']}")
    log.info("   Court-Priorität : 2 → 1 (automatisch)")
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
        f"🎾 <b>Padel Bot V17 SPAM-COMMIT ÜBERALL gestartet!</b>\n\n"
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
        senden("⏹️ Padel Bot V17 SPAM-COMMIT ÜBERALL wurde beendet.")
