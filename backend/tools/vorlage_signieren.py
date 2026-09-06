#!/usr/bin/env python3
"""
Eine Vorlage von Hand für eine bestimmte Kundenlizenz signieren.

Wozu: Kostenpflichtige Vorlagen nimmt Datenmonster nur mit gültiger Signatur an.
Im Normalfall signiert monstersuite beim Herunterladen. Für den Support — Store
nicht erreichbar, Vorprüfung beim Kunden, Sonderfassung einer Auswertung —
entsteht die Signatur hiermit.

    python backend/tools/vorlage_signieren.py templates/jtl_gf_cockpit.json \
        --lizenz DM-XXXX-XXXX-XXXX \
        --ausgabe /tmp/jtl_gf_cockpit-signiert.json

Der private Schlüssel wird erwartet in ~/.config/datenmonster/vorlagen_signaturschluessel
(oder über --schluessel bzw. TEMPLATE_SIGNING_KEY). Er gehört NICHT ins Repository
und nicht auf eine Kundeninstallation.
"""
import argparse
import base64
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.services.template_signatur import (  # noqa: E402
    SIGNATUR_SCHLUESSEL, _kanonisch, inhalt_hash, signatur_payload, braucht_signatur,
)

STANDARD_SCHLUESSEL = pathlib.Path.home() / ".config/datenmonster/vorlagen_signaturschluessel"


def privaten_schluessel_lesen(pfad: str | None) -> bytes:
    roh = os.getenv("TEMPLATE_SIGNING_KEY", "").strip()
    if not roh:
        p = pathlib.Path(pfad) if pfad else STANDARD_SCHLUESSEL
        if not p.is_file():
            raise SystemExit(f"Kein privater Schlüssel gefunden: {p}\n"
                             f"Erzeugen mit: python backend/tools/vorlagen_schluessel.py")
        roh = p.read_text().strip()
    return base64.b64decode(roh)


def main():
    ap = argparse.ArgumentParser(description="Vorlage für eine Lizenz signieren")
    ap.add_argument("datei", help="Template-JSON")
    ap.add_argument("--lizenz", required=True, help="Lizenzschlüssel der Zielinstallation")
    ap.add_argument("--ausgabe", help="Zieldatei (Vorgabe: <datei>-signiert.json)")
    ap.add_argument("--schluessel", help="Pfad zum privaten Schlüssel")
    args = ap.parse_args()

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    data = json.loads(pathlib.Path(args.datei).read_text(encoding="utf-8"))
    tid = (data.get("template_id") or "").strip()
    if not tid:
        raise SystemExit("Die Datei hat keine template_id.")
    if not braucht_signatur(tid):
        print(f"Hinweis: '{tid}' steht nicht in GESCHUETZTE_VORLAGEN — "
              f"Datenmonster würde sie auch ohne Signatur annehmen.")

    data.pop(SIGNATUR_SCHLUESSEL, None)      # eine alte Signatur nie mitsignieren
    erstellt = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = signatur_payload(tid, args.lizenz, inhalt_hash(data), erstellt)

    sk = Ed25519PrivateKey.from_private_bytes(privaten_schluessel_lesen(args.schluessel))
    sig = base64.b64encode(sk.sign(_kanonisch(payload))).decode()

    data[SIGNATUR_SCHLUESSEL] = {**payload, "sig": sig}
    ziel = pathlib.Path(args.ausgabe or (args.datei.rsplit(".json", 1)[0] + "-signiert.json"))
    ziel.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Signiert für Lizenz {args.lizenz}\n  → {ziel}")


if __name__ == "__main__":
    main()
