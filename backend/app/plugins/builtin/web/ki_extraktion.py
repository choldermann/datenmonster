"""
KI-Extraktion: Felder aus dem sichtbaren Text einer Seite lesen lassen.

Für Seiten ohne maschinenlesbare Produktdaten. Drei Sicherungen:
- Nur was im Text steht: jeder Wert muss (ohne Leerraum) im Seitentext
  vorkommen, sonst wird er verworfen – eine erfundene Lieferzeit ist schlimmer
  als eine fehlende.
- Zwischenspeicher: gleicher Seitentext + gleiche Felder → gespeichertes
  Ergebnis, kein neuer KI-Aufruf. Tägliche Abrufe kosten so nur bei Änderungen.
- Text wird gekürzt (MAX_ZEICHEN), damit eine Riesenseite nicht das Guthaben frisst.
"""
import asyncio
import hashlib
import json
import os
import re
import time
from typing import List

from bs4 import BeautifulSoup

MAX_ZEICHEN = 15000
CACHE_TAGE = 30
_ARTIG = re.compile(r"[^\w]+", re.UNICODE)

SYSTEM = (
    "Du liest Daten aus dem Text einer Webseite (z.B. Shop-Produktseite oder Liste). "
    "Gib NUR Werte zurück, die wörtlich im Text stehen – nichts ergänzen, schätzen oder "
    "umrechnen. Fehlt ein Wert, null. Preise genau so, wie sie im Text stehen (z.B. "
    "'12,90'). Eine Zeile je Produkt bzw. Datensatz; bei einer einzelnen Produktseite "
    "genau eine Zeile für das Hauptprodukt (keine Zubehör-/Empfehlungsartikel)."
)


def seitentext(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"]):
        tag.decompose()
    zeilen = [z.strip() for z in soup.get_text("\n").splitlines()]
    text = "\n".join(z for z in zeilen if z)
    return text[:MAX_ZEICHEN]


def _kompakt(s: str) -> str:
    return _ARTIG.sub("", str(s)).lower()


def nur_belegte_werte(zeilen: List[dict], text: str) -> List[dict]:
    """Werte, die nicht im Text stehen, werden None (gegen erfundene Angaben)."""
    k_text = _kompakt(text)
    out = []
    for z in zeilen:
        neu = {}
        for feld, wert in z.items():
            if wert is None or str(wert).strip() == "":
                neu[feld] = None
                continue
            w = str(wert).strip()
            varianten = {w, w.replace(".", ","), w.replace(",", ".")}
            neu[feld] = w if any(_kompakt(v) and _kompakt(v) in k_text for v in varianten) else None
        if any(v is not None for v in neu.values()):
            out.append(neu)
    return out


def _cache_pfad(schluessel: str) -> str:
    from app.core.config import UPLOAD_DIR
    ordner = os.path.join(UPLOAD_DIR, "web_ki_cache")
    os.makedirs(ordner, exist_ok=True)
    return os.path.join(ordner, f"{schluessel}.json")


def ki_extrahieren(html: str, felder: List[str], hinweis: str = "") -> List[dict]:
    felder = [f.strip() for f in felder if f and f.strip()]
    if not felder:
        raise ValueError("KI-Extraktion: bitte die gewünschten Felder angeben (z.B. name, preis, lieferzeit)")
    text = seitentext(html)
    if len(text) < 20:
        return []
    schluessel = hashlib.sha256(json.dumps([text, felder, hinweis], ensure_ascii=False).encode()).hexdigest()[:32]
    pfad = _cache_pfad(schluessel)
    if os.path.exists(pfad) and time.time() - os.path.getmtime(pfad) < CACHE_TAGE * 86400:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)

    schema = {
        "type": "object",
        "properties": {"zeilen": {"type": "array", "items": {
            "type": "object",
            "properties": {f: {"type": ["string", "null"]} for f in felder},
        }}},
    }
    auftrag = f"Gesuchte Felder: {', '.join(felder)}."
    if hinweis:
        auftrag += f"\nHinweis: {hinweis}"
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": f"{auftrag}\n\nSEITENTEXT:\n{text}"}]

    from app.core.database import SessionLocal
    from app.services.ai_service import build_ai_service
    db = SessionLocal()
    try:
        svc = build_ai_service(db)
        if svc is None:
            raise ValueError("KI-Extraktion braucht die KI-Integration (Systemeinstellungen → KI)")
        antwort = asyncio.run(svc.complete_json(messages, schema, temperature=0.0,
                                                request_type="TRANSFORMATION", max_tokens=4000))
    finally:
        db.close()
    zeilen = [{f: (z or {}).get(f) for f in felder} for z in (antwort.get("zeilen") or [])]
    zeilen = nur_belegte_werte(zeilen, text)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(zeilen, f, ensure_ascii=False)
    return zeilen
