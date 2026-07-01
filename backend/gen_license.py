#!/usr/bin/env python3
"""
Datenmonster — Offline-Key-Generator (Entwicklung / Demo)

Nur verwenden wenn monstersuite.de noch nicht für Datenmonster freigeschaltet ist.
Setzt LICENSE_SECRET in der .env voraus.

Aufruf:
    python backend/gen_license.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# LICENSE_SECRET aus Umgebung lesen (falls dotenv nicht greift)
LICENSE_SECRET = os.getenv("LICENSE_SECRET", "")

if not LICENSE_SECRET:
    print("FEHLER: LICENSE_SECRET ist nicht gesetzt.")
    print("Tipp: In .env eintragen: LICENSE_SECRET=<dein-secret>")
    print("Produktive Lizenzen werden von monstersuite.de ausgestellt.")
    sys.exit(1)

# Direkt importieren ohne FastAPI-Kontext
from app.api.license import generate_offline_key, ALL_FEATURES

PRO_FEATURES = [f["id"] for f in ALL_FEATURES if not f["free"]]

PLANS = {
    "1": ("pro",        PRO_FEATURES),
    "2": ("enterprise", PRO_FEATURES),
}

if __name__ == "__main__":
    print("─" * 60)
    print("  Datenmonster — Offline-Key-Generator (Dev/Demo)")
    print("  Produktive Lizenzen → monstersuite.de")
    print("─" * 60)

    email = input("E-Mail des Kunden: ").strip()
    if not email:
        print("Fehler: E-Mail darf nicht leer sein"); sys.exit(1)

    print("\nPlan:")
    print("  1 → Pro        (alle Premium-Features)")
    print("  2 → Enterprise (alle Premium-Features)")
    plan_choice = input("Plan [1]: ").strip() or "1"
    plan_name, features = PLANS.get(plan_choice, PLANS["1"])

    expires = input("Ablaufdatum YYYY-MM-DD (leer = kein Ablauf): ").strip() or None

    key = generate_offline_key(email, features, plan_name, expires)

    print("\n" + "─" * 60)
    print(f"  Plan     : {plan_name.capitalize()}")
    print(f"  E-Mail   : {email}")
    print(f"  Ablauf   : {expires or 'unbegrenzt'}")
    print(f"  Typ      : Offline (HMAC) — nur für Dev/Demo")
    print("─" * 60)
    print("\nSchlüssel:\n")
    print(key)
    print()
