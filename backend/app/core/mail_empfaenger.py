"""Wer darf an wen Mails aus Datenmonster schicken?

Über das SMTP-Konto der Firma geht jede Mail mit deren Absender raus. Ohne
Grenze konnte jeder angemeldete Benutzer – auch ein Portal-Benutzer – beliebige
Inhalte an beliebige Adressen schicken (Spam, Phishing im Namen der Firma) oder
Cockpit-Daten per Zeitplan an eine private Adresse umleiten.

Regel: Administratoren frei. Alle anderen nur an die Domain der Absender-Adresse
(smtp_from) und an Domains, die ein Admin unter Einstellungen → E-Mail freigibt
(smtp_empfaenger_domains, kommagetrennt). Dazu Obergrenzen für Sofort-Mails.
"""
import re
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

MAX_EMPFAENGER = 10
MAX_MAILS_PRO_STUNDE = 30

_ADRESSE = re.compile(r"^[^@\s,;<>]+@([^@\s,;<>]+\.[^@\s,;<>]+)$")
_verlauf: dict = defaultdict(deque)
_sperre = threading.Lock()


def adressen(text) -> list:
    if isinstance(text, (list, tuple)):
        text = ",".join(str(t) for t in text)
    return [a.strip() for a in re.split(r"[,;\s]+", text or "") if a.strip()]


def erlaubte_domains(db) -> set:
    from app.api.settings import get_setting
    domains = set()
    absender = get_setting(db, "smtp_from", "") or get_setting(db, "smtp_user", "") or ""
    if "@" in absender:
        domains.add(absender.rsplit("@", 1)[1].strip().lower())
    for d in (get_setting(db, "smtp_empfaenger_domains", "") or "").replace(";", ",").split(","):
        d = d.strip().lower().lstrip("@")
        if d:
            domains.add(d)
    return domains


def pruefe_neue(db, user, neu, alt=None) -> None:
    """Beim Ändern gespeicherter Empfänger nur die neu hinzugekommenen prüfen –
    ein bestehender Zeitplan mit freigegebener Fremdadresse soll sich weiter
    bearbeiten lassen, ohne dass sie wieder herausfällt."""
    vorher = {a.lower() for a in adressen(alt)}
    dazu = [a for a in adressen(neu) if a.lower() not in vorher]
    if dazu:
        pruefe_empfaenger(db, user, dazu)


def pruefe_empfaenger(db, user, empfaenger, sofort: bool = False) -> list:
    """Wirft 400/403/429, gibt sonst die bereinigte Adressliste zurück.

    sofort=True: es geht jetzt eine Mail raus → Mengen- und Stundengrenze zählen.
    Für gespeicherte Zeitpläne (sofort=False) zählt nur, an wen.
    """
    liste = adressen(empfaenger)
    for a in liste:
        if not _ADRESSE.match(a):
            raise HTTPException(400, f"Ungültige E-Mail-Adresse: {a}")
    if getattr(user, "is_admin", False):
        return liste

    if sofort and len(liste) > MAX_EMPFAENGER:
        raise HTTPException(400, f"Höchstens {MAX_EMPFAENGER} Empfänger pro Mail")
    erlaubt = erlaubte_domains(db)
    fremd = [a for a in liste if a.rsplit("@", 1)[1].lower() not in erlaubt]
    if fremd:
        if erlaubt:
            hinweis = "erlaubt: " + ", ".join(f"@{d}" for d in sorted(erlaubt))
        else:
            hinweis = "es ist noch keine Absender-Adresse eingerichtet"
        raise HTTPException(
            403,
            f"Nicht erlaubter Empfänger: {', '.join(fremd)} ({hinweis}). "
            "Weitere Domains gibt ein Administrator unter Einstellungen → E-Mail frei.",
        )

    if sofort:
        jetzt = time.time()
        with _sperre:
            q = _verlauf[getattr(user, "id", None)]
            while q and q[0] < jetzt - 3600:
                q.popleft()
            if len(q) >= MAX_MAILS_PRO_STUNDE:
                raise HTTPException(429, "Zu viele Mails in der letzten Stunde – bitte später erneut versuchen")
            q.append(jetzt)
    return liste
