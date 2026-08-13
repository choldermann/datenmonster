"""
OpenAPI/Swagger einlesen und in Studio-Requests übersetzen.

Unterstützt OpenAPI 3.x und Swagger 2.0 – letzteres, weil in der Praxis noch
genug Häuser eine 2.0-Datei ausliefern und ein „wird nicht unterstützt" dort
den ganzen Import wertlos machen würde.

Übersetzt wird in die Begriffe, die das Studio ohnehin kennt:
  Server-URL      → Basis-URL der Sammlung
  Security-Schema → auth_type der Sammlung
  Pfad-Parameter  → {{platzhalter}} (damit Umgebungen sie füllen können)
  Query-Parameter → query_params mit Beispiel- bzw. Standardwerten
  RequestBody     → ein aus dem Schema erzeugtes JSON-Gerüst

Was hier NICHT passiert: raten. Fehlt eine Angabe in der Datei, bleibt das Feld
leer – lieber eine Lücke, die auffällt, als ein erfundener Wert, der stillschweigend
falsch ist.
"""

import json
import re
from typing import Any, Optional

import yaml

MAX_TIEFE = 6          # Schachtelungstiefe bei der Beispiel-Erzeugung
MAX_ENDPUNKTE = 500


def lade_spec(inhalt: str) -> dict:
    """JSON oder YAML einlesen – das Format wird am Inhalt erkannt."""
    inhalt = (inhalt or "").strip()
    if not inhalt:
        raise ValueError("Die Datei ist leer")
    if inhalt.startswith("{"):
        try:
            return json.loads(inhalt)
        except json.JSONDecodeError as e:
            raise ValueError(f"Ungültiges JSON: {e}")
    try:
        daten = yaml.safe_load(inhalt)
    except yaml.YAMLError as e:
        raise ValueError(f"Weder gültiges JSON noch YAML: {str(e)[:200]}")
    if not isinstance(daten, dict):
        raise ValueError("Die Datei enthält keine OpenAPI-Beschreibung")
    return daten


# ── $ref auflösen ─────────────────────────────────────────────────────────────

def _aufloesen(knoten: Any, spec: dict, gesehen: Optional[set] = None, tiefe: int = 0) -> Any:
    """
    `$ref`-Verweise innerhalb des Dokuments ersetzen.

    Externe Verweise (andere Dateien, URLs) werden bewusst NICHT verfolgt: das
    wäre ein Netzzugriff aus dem Parser heraus und damit ein SSRF-Einfallstor.
    """
    if tiefe > MAX_TIEFE or not isinstance(knoten, (dict, list)):
        return knoten
    gesehen = gesehen or set()

    if isinstance(knoten, dict):
        ref = knoten.get("$ref")
        if isinstance(ref, str):
            if not ref.startswith("#/") or ref in gesehen:
                return {}          # extern oder im Kreis → aufgeben
            ziel: Any = spec
            for teil in ref[2:].split("/"):
                teil = teil.replace("~1", "/").replace("~0", "~")
                if isinstance(ziel, dict):
                    ziel = ziel.get(teil)
                else:
                    return {}
                if ziel is None:
                    return {}
            return _aufloesen(ziel, spec, gesehen | {ref}, tiefe + 1)
        return {k: _aufloesen(v, spec, gesehen, tiefe + 1) for k, v in knoten.items()}
    return [_aufloesen(v, spec, gesehen, tiefe + 1) for v in knoten]


# ── Beispielwerte aus einem Schema ────────────────────────────────────────────

def beispiel_aus_schema(schema: dict, tiefe: int = 0) -> Any:
    """
    Ein Gerüst aus einem JSON-Schema bauen. Bevorzugt werden Angaben aus der
    Datei selbst (example, default, enum); sonst ein neutraler Platzhalter,
    der als solcher erkennbar ist.
    """
    if not isinstance(schema, dict) or tiefe > MAX_TIEFE:
        return None
    for schluessel in ("example", "default"):
        if schluessel in schema:
            return schema[schluessel]
    if schema.get("enum"):
        return schema["enum"][0]
    for kombi in ("allOf", "oneOf", "anyOf"):
        if schema.get(kombi):
            if kombi == "allOf":
                zusammen = {}
                for teil in schema[kombi]:
                    wert = beispiel_aus_schema(teil, tiefe + 1)
                    if isinstance(wert, dict):
                        zusammen.update(wert)
                return zusammen
            return beispiel_aus_schema(schema[kombi][0], tiefe + 1)

    typ = schema.get("type")
    if typ == "object" or "properties" in schema:
        pflicht = set(schema.get("required") or [])
        out = {}
        for name, unter in (schema.get("properties") or {}).items():
            # Große Schemata würden das Gerüst unlesbar machen: Pflichtfelder
            # zuerst, der Rest bis zu einer sinnvollen Grenze.
            if len(out) >= 25 and name not in pflicht:
                continue
            out[name] = beispiel_aus_schema(unter, tiefe + 1)
        return out
    if typ == "array":
        return [beispiel_aus_schema(schema.get("items") or {}, tiefe + 1)]
    if typ == "integer":
        return 0
    if typ == "number":
        return 0.0
    if typ == "boolean":
        return False
    fmt = schema.get("format")
    if fmt == "date":
        return "{{heute}}"
    if fmt in ("date-time", "datetime"):
        return "{{iso_heute}}"
    return ""


# ── Server / Basis-URL ────────────────────────────────────────────────────────

def _basis_url(spec: dict, quelle_url: Optional[str] = None) -> str:
    """
    Basis-URL bestimmen. Server-Einträge dürfen relativ sein („/api/v3") – sie
    beziehen sich dann auf den Ort, an dem die Beschreibung liegt. Ohne diese
    Auflösung bekäme die Sammlung eine Basis-URL, mit der kein Request läuft.
    """
    server = (spec.get("servers") or [{}])[0]
    url = (server.get("url") or "").strip()
    if url:
        # Server-Variablen mit ihrem Standardwert füllen: {region} → eu
        for name, var in (server.get("variables") or {}).items():
            url = url.replace("{" + name + "}", str(var.get("default", "")))
        if not url.lower().startswith(("http://", "https://")) and quelle_url:
            from urllib.parse import urljoin
            url = urljoin(quelle_url, url)
        return url.rstrip("/")
    # Swagger 2.0
    host = spec.get("host")
    if host:
        schema = (spec.get("schemes") or ["https"])[0]
        return f"{schema}://{host}{spec.get('basePath', '')}".rstrip("/")
    if quelle_url and spec.get("basePath"):
        from urllib.parse import urljoin
        return urljoin(quelle_url, spec["basePath"]).rstrip("/")
    # Gar keine Server-Angabe: OpenAPI schreibt dann selbst den Ort der
    # Beschreibung als Bezugspunkt vor („servers" fehlt ⇒ Server ist „/").
    # Das ist also keine Annahme, sondern die Vorgabe – und ohne sie bekämen
    # alle Requests nur relative Pfade und liefen nirgendwohin.
    if quelle_url:
        from urllib.parse import urljoin
        return urljoin(quelle_url, "/").rstrip("/")
    return ""


# ── Security → auth_type ──────────────────────────────────────────────────────

# Je höher, desto lieber – wir wählen nur Verfahren, die die Engine auch kann.
_AUTH_RANG = {"bearer": 4, "apikey": 3, "basic": 2, "oauth2_cc": 1}


def _auth_aus_spec(spec: dict) -> dict:
    """
    Das am besten passende Security-Schema in unsere Auth-Begriffe übersetzen.

    Nicht das erstbeste: viele Beschreibungen führen mehrere Verfahren auf, und
    ein OAuth2-Implicit-Flow (den wir bewusst nicht unterstützen, siehe
    Entscheidung zu Phase 1) würde sonst ein brauchbares API-Key-Verfahren
    verdrängen und eine leere Token-URL hinterlassen.
    """
    schemata = ((spec.get("components") or {}).get("securitySchemes")
                or spec.get("securityDefinitions") or {})
    kandidaten = []
    for name, s in schemata.items():
        if not isinstance(s, dict):
            continue
        typ = (s.get("type") or "").lower()
        if typ == "http":
            verfahren = (s.get("scheme") or "").lower()
            if verfahren == "bearer":
                kandidaten.append({"auth_type": "bearer", "auth_config": {}, "schema": name})
            elif verfahren == "basic":
                kandidaten.append({"auth_type": "basic", "auth_config": {}, "schema": name})
        elif typ in ("apikey", "api_key"):
            kandidaten.append({"auth_type": "apikey", "schema": name,
                               "auth_config": {"key": s.get("name") or "X-Api-Key",
                                               "location": "query" if s.get("in") == "query" else "header"}})
        elif typ == "basic":                       # Swagger 2.0
            kandidaten.append({"auth_type": "basic", "auth_config": {}, "schema": name})
        elif typ == "oauth2":
            fluesse = s.get("flows") or {}
            cc = fluesse.get("clientCredentials") or {}
            token_url = cc.get("tokenUrl") or (s.get("tokenUrl") if s.get("flow") == "application" else "")
            if not token_url:
                continue    # nur Implicit/Auth-Code beschrieben → können wir nicht bedienen
            kandidaten.append({"auth_type": "oauth2_cc", "schema": name,
                               "auth_config": {"token_url": token_url,
                                               "scope": " ".join(list((cc.get("scopes") or {}).keys())[:5])}})
    if not kandidaten:
        return {"auth_type": "none", "auth_config": {}, "schema": None}
    return max(kandidaten, key=lambda k: _AUTH_RANG.get(k["auth_type"], 0))


# ── Endpunkte ─────────────────────────────────────────────────────────────────

_METHODEN = ("get", "post", "put", "patch", "delete", "head", "options")


def _parameter_sammeln(liste, spec) -> dict:
    """Parameter nach Ort sortieren und dabei Beispielwerte mitnehmen."""
    raus = {"path": [], "query": [], "header": []}
    for p in (liste or []):
        p = _aufloesen(p, spec)
        if not isinstance(p, dict) or not p.get("name"):
            continue
        ort = p.get("in")
        if ort not in raus:
            continue
        schema = p.get("schema") or {}
        beispiel = p.get("example", schema.get("example", schema.get("default")))
        if beispiel is None and schema.get("enum"):
            beispiel = schema["enum"][0]
        raus[ort].append({
            "name": p["name"],
            "pflicht": bool(p.get("required")),
            "beschreibung": (p.get("description") or "").strip()[:300],
            "typ": schema.get("type") or p.get("type") or "string",
            "beispiel": "" if beispiel is None else str(beispiel),
        })
    return raus


def _body_aus_operation(op: dict, spec: dict) -> tuple:
    """(body_typ, body_inhalt) aus requestBody (3.x) bzw. body-Parameter (2.0)."""
    rb = _aufloesen(op.get("requestBody") or {}, spec)
    inhalte = (rb.get("content") or {}) if isinstance(rb, dict) else {}
    for medientyp, eintrag in inhalte.items():
        schema = (eintrag or {}).get("schema") or {}
        beispiel = (eintrag or {}).get("example")
        if beispiel is None:
            beispiel = beispiel_aus_schema(schema)
        if "json" in medientyp:
            return "json", json.dumps(beispiel, indent=2, ensure_ascii=False)
        if "xml" in medientyp:
            return "xml", ""
        if "form" in medientyp or "urlencoded" in medientyp:
            if isinstance(beispiel, dict):
                return "form", "\n".join(f"{k}={v}" for k, v in beispiel.items())
            return "form", ""
    # Swagger 2.0: Body steckt als Parameter mit in="body"
    for p in (op.get("parameters") or []):
        p = _aufloesen(p, spec)
        if isinstance(p, dict) and p.get("in") == "body":
            return "json", json.dumps(beispiel_aus_schema(p.get("schema") or {}),
                                      indent=2, ensure_ascii=False)
    return "none", None


def _antwort_hinweis(op: dict, spec: dict) -> str:
    for code in ("200", "201", 200, 201, "default"):
        r = (op.get("responses") or {}).get(code)
        if r:
            r = _aufloesen(r, spec)
            beschr = (r.get("description") or "").strip()
            return f"{code}: {beschr}"[:200] if beschr else str(code)
    return ""


def parse_spec(spec: dict, quelle_url: Optional[str] = None) -> dict:
    """Eine eingelesene Datei in Sammlung + Endpunktliste übersetzen.

    `quelle_url` ist der Ort, von dem die Datei stammt – nötig, um relative
    Server-Angaben aufzulösen."""
    if not isinstance(spec, dict):
        raise ValueError("Die Datei enthält keine OpenAPI-Beschreibung")
    version = str(spec.get("openapi") or spec.get("swagger") or "")
    if not version:
        raise ValueError("Kein openapi- oder swagger-Feld gefunden – ist das wirklich eine API-Beschreibung?")
    if not spec.get("paths"):
        raise ValueError("Die Beschreibung enthält keine Endpunkte (paths)")

    info = spec.get("info") or {}
    auth = _auth_aus_spec(spec)
    endpunkte = []

    for pfad, eintrag in (spec.get("paths") or {}).items():
        if not isinstance(eintrag, dict):
            continue
        gemeinsame = eintrag.get("parameters") or []
        for methode in _METHODEN:
            op = eintrag.get(methode)
            if not isinstance(op, dict) or len(endpunkte) >= MAX_ENDPUNKTE:
                continue
            params = _parameter_sammeln(list(gemeinsame) + list(op.get("parameters") or []), spec)
            body_typ, body_inhalt = _body_aus_operation(op, spec)

            # Pfad-Platzhalter in unsere Template-Syntax: {owner} → {{owner}}
            url_vorlage = re.sub(r"\{([^{}]+)\}", r"{{\1}}", pfad)

            endpunkte.append({
                "id": f"{methode}_{re.sub(r'[^a-zA-Z0-9]+', '_', pfad).strip('_')}",
                "methode": methode.upper(),
                "pfad": pfad,
                "url_vorlage": url_vorlage,
                "titel": (op.get("summary") or op.get("operationId")
                          or f"{methode.upper()} {pfad}").strip()[:160],
                "beschreibung": (op.get("description") or "").strip()[:600],
                "tags": [str(t) for t in (op.get("tags") or [])][:5] or ["Allgemein"],
                "veraltet": bool(op.get("deprecated")),
                "pfad_parameter": params["path"],
                "query_parameter": params["query"],
                "header_parameter": params["header"],
                "body_typ": body_typ,
                "body_inhalt": body_inhalt,
                "antwort": _antwort_hinweis(op, spec),
            })

    return {
        "version": version,
        "titel": (info.get("title") or "API").strip()[:160],
        "api_version": str(info.get("version") or ""),
        "beschreibung": (info.get("description") or "").strip()[:1200],
        "basis_url": _basis_url(spec, quelle_url),
        "auth_type": auth["auth_type"],
        "auth_config": auth["auth_config"],
        "auth_schema": auth["schema"],
        "endpunkte": endpunkte,
        "abgeschnitten": len(endpunkte) >= MAX_ENDPUNKTE,
    }


def request_aus_endpunkt(ep: dict, name_praefix: str = "") -> dict:
    """
    Einen Endpunkt in die Felder eines Studio-Requests übersetzen.
    Die Auth bleibt bewusst auf „erben" – sie gehört an die Sammlung.
    """
    query = {}
    for p in ep.get("query_parameter") or []:
        # Nur Pflichtfelder und solche mit Beispielwert vorbelegen; alles andere
        # würde die Anfrage mit leeren Parametern zumüllen.
        if p["pflicht"] or p["beispiel"]:
            query[p["name"]] = p["beispiel"] or f"{{{{{p['name']}}}}}"
    headers = {}
    for p in ep.get("header_parameter") or []:
        if p["pflicht"]:
            headers[p["name"]] = p["beispiel"] or f"{{{{{p['name']}}}}}"

    return {
        "name": f"{name_praefix}{ep['titel']}"[:160],
        "description": ep.get("beschreibung") or "",
        "url": ep["url_vorlage"],
        "method": ep["methode"],
        "query_params": query,
        "headers": headers,
        "body_type": ep.get("body_typ") or "none",
        "body_content": ep.get("body_inhalt"),
        "auth_type": "inherit",
        "auth_config": {},
    }


def doku_ablegen(endpunkte: list, titel: str = "", beschreibung: str = "",
                 basis_url: str = "", auth_type: str = "") -> dict:
    """
    Die Beschreibung der importierten Endpunkte für den Doku-Assistenten
    aufbewahren – in Textform, wie sie in der Datei stand.

    Abgelegt wird nur, was tatsächlich importiert wurde. Über Endpunkte, die
    der Nutzer abgewählt hat, soll der Assistent auch nichts erzählen: sie
    stehen in keiner Sammlung, ein Hinweis auf sie ginge ins Leere.

    Bewusst keine Antwortdaten und keine Auth-Werte – das hier ist Doku und
    wird als solche später an ein Sprachmodell gegeben.
    """
    def _param(p: dict) -> dict:
        return {"name": p.get("name"), "pflicht": bool(p.get("pflicht")),
                "typ": p.get("typ"), "beschreibung": (p.get("beschreibung") or "")[:300]}

    return {
        "titel": titel, "beschreibung": (beschreibung or "")[:1200],
        "basis_url": basis_url, "auth_type": auth_type,
        "endpunkte": [{
            "methode": e.get("methode"), "pfad": e.get("pfad"),
            "titel": e.get("titel"), "beschreibung": (e.get("beschreibung") or "")[:600],
            "tags": e.get("tags") or [],
            "veraltet": bool(e.get("veraltet")),
            "pfad_parameter": [_param(p) for p in (e.get("pfad_parameter") or [])],
            "query_parameter": [_param(p) for p in (e.get("query_parameter") or [])],
            "header_parameter": [_param(p) for p in (e.get("header_parameter") or [])],
            "body": (e.get("body_inhalt") or "")[:800],
            "antwort": e.get("antwort") or "",
        } for e in endpunkte],
    }


# Die Füllwortliste steht in app/services/stichworte.py — sie wird auch von der
# AI-Memory-Auswahl gebraucht, und zwei Kopien driften auseinander.
from app.services.stichworte import FUELLWOERTER as _FUELLWOERTER


def doku_suchen(doku: dict, frage: str, grenze: int = 12) -> tuple:
    """
    Die zur Frage passenden Endpunkte heraussuchen.

    Nötig, weil eine Beschreibung mit hunderten Endpunkten jeden Prompt
    sprengt. Gewertet wird schlicht nach Treffern in Pfad, Titel, Beschreibung
    und Parameternamen – kein Modell, damit die Auswahl nachvollziehbar bleibt
    und auch ohne KI funktioniert.

    Gibt (endpunkte, getroffen) zurück. Findet sich nichts, gehen die ersten
    Endpunkte als Auszug hinaus, aber `getroffen` ist dann False – das gehört
    in den Prompt, sonst hält das Modell einen beliebigen Auszug für die
    Antwort auf die Frage.
    """
    endpunkte = (doku or {}).get("endpunkte") or []
    woerter = [w for w in re.split(r"[^\wäöüß]+", (frage or "").lower())
               if len(w) > 2 and w not in _FUELLWOERTER]
    if not woerter:
        return endpunkte[:grenze], False

    bewertet = []
    for e in endpunkte:
        pfad = (e.get("pfad") or "").lower()
        titel = (e.get("titel") or "").lower()
        text = (e.get("beschreibung") or "").lower()
        params = " ".join(p.get("name") or "" for art in
                          ("pfad_parameter", "query_parameter", "header_parameter")
                          for p in (e.get(art) or [])).lower()
        tags = " ".join(e.get("tags") or []).lower()
        punkte = 0
        for w in woerter:
            if w in pfad:   punkte += 3      # der Pfad ist das aussagekräftigste Merkmal
            if w in titel:  punkte += 2
            if w in tags:   punkte += 2
            if w in params: punkte += 1
            if w in text:   punkte += 1
        # Ein einzelner Treffer irgendwo im Fließtext ist noch kein Fund –
        # sonst zieht jedes Allerweltswort zwölf beliebige Endpunkte herbei.
        if punkte >= 2:
            bewertet.append((punkte, e))
    if not bewertet:
        return endpunkte[:grenze], False
    bewertet.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in bewertet[:grenze]], True


def doku_als_text(endpunkte: list) -> str:
    """Endpunkt-Doku als Klartext für den Prompt."""
    teile = []
    for e in endpunkte:
        zeilen = [f"{e.get('methode')} {e.get('pfad')} — {e.get('titel') or ''}"]
        if e.get("veraltet"):
            zeilen.append("  (als veraltet gekennzeichnet)")
        if e.get("beschreibung"):
            zeilen.append(f"  {e['beschreibung']}")
        for art, bezeichnung in (("pfad_parameter", "Pfad"),
                                 ("query_parameter", "Query"),
                                 ("header_parameter", "Header")):
            for p in (e.get(art) or []):
                pflicht = "Pflicht" if p.get("pflicht") else "optional"
                beschr = f" – {p['beschreibung']}" if p.get("beschreibung") else ""
                zeilen.append(f"  [{bezeichnung}] {p.get('name')} ({p.get('typ')}, {pflicht}){beschr}")
        if e.get("body"):
            zeilen.append(f"  Body: {e['body'][:400]}")
        if e.get("antwort"):
            zeilen.append(f"  Antwort: {e['antwort']}")
        teile.append("\n".join(zeilen))
    return "\n\n".join(teile)


def platzhalter_sammeln(endpunkte: list) -> list:
    """
    Alle {{platzhalter}} aus den gewählten Endpunkten – daraus lässt sich eine
    Umgebung vorschlagen, statt den Nutzer jeden Pfad einzeln füllen zu lassen.
    """
    namen = {}
    for ep in endpunkte:
        for p in ep.get("pfad_parameter") or []:
            namen.setdefault(p["name"], p.get("beschreibung") or "")
        for p in (ep.get("query_parameter") or []) + (ep.get("header_parameter") or []):
            if p["pflicht"] and not p["beispiel"]:
                namen.setdefault(p["name"], p.get("beschreibung") or "")
    return [{"key": k, "value": "", "secret": False, "beschreibung": v}
            for k, v in sorted(namen.items())]
