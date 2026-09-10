"""
Echtheitsprüfung für ausgelieferte Vorlagen.

Eine kostenpflichtige Vorlage trägt einen Signaturblock, den monstersuite beim
Herunterladen erzeugt. Signiert wird mit einem privaten Ed25519-Schlüssel, den nur
der Herausgeber hat; hier steckt ausschließlich der öffentliche Gegenpart. Damit
lässt sich eine Vorlage weder fälschen noch nachträglich verändern.

Die Signatur bindet die Vorlage zusätzlich an den **Lizenzschlüssel des Käufers**:
eine an Dritte weitergereichte Datei ist auf deren Installation wertlos, weil dort
ein anderer Lizenzschlüssel steht.

Kein Kopierschutz im harten Sinn — der Prüfcode läuft beim Kunden und ist lesbar.
Es geht um die Hürde und darum, dass Weitergabe nicht beiläufig passiert.
"""
import base64
import hashlib
import json
from typing import Optional, Tuple

# Öffentlicher Schlüssel des Herausgebers. Der private Gegenpart liegt ausschließlich
# auf monstersuite (Env TEMPLATE_SIGNING_KEY) und beim Herausgeber selbst.
# Bewusst ohne Env-Override: eine Zeile in der .env soll die Prüfung nicht aushebeln.
HERAUSGEBER_PUBKEY = "7mx9M728W90Wr5sNo32On0HweFpBdsFJ4NeFuYFfoN0="

# Vorlagen, die eine gültige Signatur brauchen. Alles andere — Eigenbau, Vorlagen
# aus fremder Quelle, Testvorlagen — bleibt unberührt einspielbar.
# PFLEGEHINWEIS: Wird eine neue Vorlage verkauft, gehört ihre template_id hierher.
GESCHUETZTE_VORLAGEN = {
    "jtl_gf_cockpit",
    "jtl_vertrieb_cockpit",
    "jtl_einkauf_cockpit",
    "jtl_versand_cockpit",
    "jtl_lager_cockpit",
    "jtl_health_check",
    "jtl_intrastat",
    "jtl_datev",
    "jtl_eingangsrechnung",
    "jtl_monitor",
    "jtl_wissen_paket",
    "jtl_preis_cockpit",
}

SIGNATUR_SCHLUESSEL = "signatur"
SIGNATUR_VERSION = 1


def _kanonisch(obj) -> bytes:
    """Byte-genau reproduzierbare Darstellung — beide Seiten müssen exakt dasselbe sehen."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def inhalt_hash(data: dict) -> str:
    """SHA-256 über die Vorlage ohne ihren Signaturblock."""
    ohne = {k: v for k, v in data.items() if k != SIGNATUR_SCHLUESSEL}
    return hashlib.sha256(_kanonisch(ohne)).hexdigest()


def signatur_payload(template_id: str, lizenz: str, hash_hex: str, erstellt_am: str) -> dict:
    """Das, was tatsächlich signiert wird. Reihenfolge egal — kanonisch serialisiert."""
    return {
        "version": SIGNATUR_VERSION,
        "template_id": template_id,
        "lizenz": lizenz,
        "inhalt_hash": hash_hex,
        "erstellt_am": erstellt_am,
    }


def braucht_signatur(template_id: str) -> bool:
    return template_id in GESCHUETZTE_VORLAGEN


def pruefe(data: dict, lizenzschluessel: str,
           pubkey_b64: Optional[str] = None) -> Tuple[bool, str]:
    """
    Prüft die Signatur einer Vorlage.

    Rückgabe (ok, grund). `grund` ist bei ok=True leer und sonst ein Satz, der dem
    Anwender gesagt werden kann.
    """
    tid = (data.get("template_id") or "").strip()
    if not braucht_signatur(tid):
        return True, ""

    block = data.get(SIGNATUR_SCHLUESSEL)
    if not isinstance(block, dict):
        return False, ("Diese Vorlage ist kostenpflichtig und trägt keine Signatur. "
                       "Hole sie über den Template-Store, dann wird sie beim Herunterladen "
                       "für deine Lizenz signiert.")

    if not lizenzschluessel:
        return False, ("Ohne aktivierte Lizenz lässt sich die Signatur nicht prüfen. "
                       "Aktiviere zuerst die Lizenz unter Systemeinstellungen.")

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        # Ohne cryptography ist keine Prüfung möglich. Durchwinken wäre die Hintertür,
        # auf die jeder zuerst schaut – also ablehnen.
        return False, ("Signatur kann nicht geprüft werden: das Paket 'cryptography' fehlt "
                       "in dieser Installation.")

    if block.get("version") != SIGNATUR_VERSION:
        return False, f"Unbekannte Signaturfassung ({block.get('version')})."

    if (block.get("template_id") or "") != tid:
        return False, "Die Signatur gehört zu einer anderen Vorlage."

    if (block.get("lizenz") or "") != lizenzschluessel:
        return False, ("Diese Vorlage ist für eine andere Lizenz signiert. Eine gekaufte "
                       "Vorlage lässt sich nicht auf eine fremde Installation übertragen — "
                       "hole sie dort über den Template-Store.")

    ist = inhalt_hash(data)
    if (block.get("inhalt_hash") or "") != ist:
        return False, "Die Vorlage wurde nach dem Signieren verändert."

    payload = signatur_payload(tid, block.get("lizenz", ""), block.get("inhalt_hash", ""),
                               block.get("erstellt_am", ""))
    try:
        pub = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(pubkey_b64 or HERAUSGEBER_PUBKEY))
        pub.verify(base64.b64decode(block.get("sig") or ""), _kanonisch(payload))
    except InvalidSignature:
        return False, "Die Signatur der Vorlage ist ungültig."
    except Exception as e:
        return False, f"Signatur nicht prüfbar: {e}"

    return True, ""
