#!/usr/bin/env python3
"""
Erzeugt das Ed25519-Schlüsselpaar für die Vorlagen-Signatur.

Einmalig. Der private Schlüssel gehört auf monstersuite (Env TEMPLATE_SIGNING_KEY)
und in eine Sicherung; der öffentliche in
backend/app/services/template_signatur.py → HERAUSGEBER_PUBKEY.

Achtung: Ein neues Paar entwertet alle bereits ausgestellten Signaturen.
"""
import base64
import os
import pathlib

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

ZIEL = pathlib.Path.home() / ".config/datenmonster/vorlagen_signaturschluessel"


def main():
    if ZIEL.exists():
        raise SystemExit(f"Es gibt schon einen Schlüssel: {ZIEL}\n"
                         f"Zum bewussten Ersetzen die Datei vorher wegsichern und löschen.")
    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    sk = Ed25519PrivateKey.generate()
    roh = sk.private_bytes(serialization.Encoding.Raw,
                           serialization.PrivateFormat.Raw,
                           serialization.NoEncryption())
    ZIEL.write_text(base64.b64encode(roh).decode() + "\n")
    os.chmod(ZIEL, 0o600)
    pub = sk.public_key().public_bytes(serialization.Encoding.Raw,
                                       serialization.PublicFormat.Raw)
    print(f"Privater Schlüssel: {ZIEL} (nicht weitergeben, nicht ins Repo)")
    print(f"Öffentlicher Schlüssel für HERAUSGEBER_PUBKEY:\n  {base64.b64encode(pub).decode()}")


if __name__ == "__main__":
    main()
