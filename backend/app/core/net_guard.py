"""Zentraler SSRF-Egress-Guard für alle serverseitigen HTTP-Aufrufe zu FREMD-URLs
(REST-Connector/API-Studio, Web-Proxy). Da Nutzer beliebige URLs eingeben können,
verhindert dieser Guard, dass Datenmonster als Sprungbrett auf interne Infrastruktur
missbraucht wird (SSRF).

Politik (Default):
  - IMMER blockiert: Cloud-Metadata-Endpunkte (169.254.169.254 u. a.) + Link-Local.
  - Default blockiert: Loopback (127.0.0.1/::1)  – per Allowlist freigebbar.
  - Erlaubt + protokolliert: private/interne Netze (10/172.16/192.168 …) – für On-Prem.
  - Öffentliche Ziele: erlaubt.
Admin-Policy (Settings): Allowlist (übersteuert Blocks) + Blocklist (immer blockiert).

Wird VOR jedem ausgehenden Request aufgerufen (inkl. jedem Redirect-Hop), damit auch
DNS-Rebinding/Redirect-Umleitungen auf interne Ziele erkannt werden."""
import ipaddress
import socket
import time
import logging
from urllib.parse import urlparse, urljoin

log = logging.getLogger("datenmonster")

# Bekannte Cloud-Metadata-Endpunkte (AWS/GCP/Azure IMDS, Alibaba) – nie erreichbar machen.
_METADATA_IPS = {"169.254.169.254", "100.100.100.200", "fd00:ec2::254"}

_MAX_REDIRECTS = 5
_policy_cache: dict = {"ts": 0.0, "data": None}


class EgressBlocked(Exception):
    """Ausgehender Request auf ein nicht erlaubtes Ziel wurde blockiert."""


def _load_policy() -> dict:
    """Admin-Policy aus den Settings lesen (kurz gecacht, damit nicht jeder Request
    die DB trifft). Eigene Session, weil die Aufrufer (rest_service) kein db-Handle haben."""
    now = time.time()
    if _policy_cache["data"] is not None and _policy_cache["ts"] + 30 > now:
        return _policy_cache["data"]
    allow, block, allow_loopback = [], [], False
    try:
        from app.core.database import SessionLocal
        from app.api.settings import get_setting
        db = SessionLocal()
        try:
            allow = _split(get_setting(db, "api_egress_allowlist", ""))
            block = _split(get_setting(db, "api_egress_blocklist", ""))
            allow_loopback = (get_setting(db, "api_egress_allow_loopback", "false") == "true")
        finally:
            db.close()
    except Exception:
        pass
    data = {"allow": allow, "block": block, "allow_loopback": allow_loopback}
    _policy_cache.update(ts=now, data=data)
    return data


def _split(raw: str) -> list:
    return [x.strip() for x in (raw or "").replace("\n", ",").split(",") if x.strip()]


def _entry_matches(entry: str, host: str, ips: set) -> bool:
    """Ob ein Allow-/Block-Eintrag (Host, Bare-IP oder CIDR) auf Ziel-Host/IPs passt."""
    entry = entry.strip().lower()
    if not entry:
        return False
    if "/" in entry:  # CIDR
        try:
            net = ipaddress.ip_network(entry, strict=False)
            return any(ipaddress.ip_address(ip) in net for ip in ips)
        except ValueError:
            return False
    # Bare-IP
    try:
        target = ipaddress.ip_address(entry)
        return any(ipaddress.ip_address(ip) == target for ip in ips)
    except ValueError:
        pass
    # Hostname (exakt oder Subdomain)
    h = (host or "").lower()
    return h == entry or h.endswith("." + entry)


def assert_url_allowed(url: str) -> set:
    """Prüft, ob `url` als ausgehendes Ziel erlaubt ist. Wirft EgressBlocked, wenn nicht.
    Gibt die aufgelösten IPs zurück (Debug/Logging)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise EgressBlocked(f"Nicht erlaubtes Schema: {parsed.scheme or '(leer)'}")
    host = parsed.hostname
    if not host:
        raise EgressBlocked("URL ohne Host")

    # DNS auflösen (alle A/AAAA); scheitert die Auflösung, wird der Request gar nicht erst gesendet.
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise EgressBlocked(f"Host nicht auflösbar: {host} ({e})")
    ips = {info[4][0] for info in infos}
    if not ips:
        raise EgressBlocked(f"Keine IP für Host: {host}")

    policy = _load_policy()
    allow, block, allow_loopback = policy["allow"], policy["block"], policy["allow_loopback"]

    # Explizite Allowlist übersteuert alle folgenden Blocks (z. B. eine interne API).
    if any(_entry_matches(e, host, ips) for e in allow):
        return ips

    for ip in ips:
        addr = ipaddress.ip_address(ip)
        if str(addr) in _METADATA_IPS or addr.is_link_local:
            raise EgressBlocked(f"Cloud-Metadata/Link-Local-Ziel blockiert: {host} → {ip}")
        if addr.is_loopback and not allow_loopback:
            raise EgressBlocked(f"Loopback-Ziel blockiert: {host} → {ip}")

    if any(_entry_matches(e, host, ips) for e in block):
        raise EgressBlocked(f"Ziel steht auf der Blockliste: {host}")

    # Private/interne Ziele sind erlaubt (On-Prem), werden aber protokolliert.
    for ip in ips:
        addr = ipaddress.ip_address(ip)
        if addr.is_private and not addr.is_loopback:
            log.info("Egress zu internem/privatem Ziel erlaubt: %s → %s", host, ip)
            break
    return ips


def guarded_request(session, method: str, url: str, allow_redirects: bool = True,
                    **kwargs):
    """Wie session.request(), aber SSRF-geprüft – auch für jeden Redirect-Hop. Folgt
    Redirects manuell (max. 5), damit ein 30x nicht unbemerkt auf ein internes Ziel führt."""
    assert_url_allowed(url)
    resp = session.request(method.upper(), url, allow_redirects=False, **kwargs)
    if not allow_redirects:
        return resp
    hops = 0
    # Body/Params nur beim ersten Request senden; Redirects als GET folgen (wie Browser/requests
    # bei 301/302/303). 307/308 würden Methode/Body erhalten – hier bewusst konservativ.
    while resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
        loc = resp.headers.get("Location")
        if not loc or hops >= _MAX_REDIRECTS:
            break
        next_url = urljoin(url, loc)
        assert_url_allowed(next_url)
        follow_method = method if resp.status_code in (307, 308) else "GET"
        follow_kwargs = kwargs if resp.status_code in (307, 308) else {
            k: v for k, v in kwargs.items() if k not in ("json", "data", "files")}
        resp = session.request(follow_method.upper(), next_url, allow_redirects=False, **follow_kwargs)
        url = next_url
        hops += 1
    return resp
