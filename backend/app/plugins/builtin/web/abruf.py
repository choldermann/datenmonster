"""
Höflicher Seitenabruf für viele Seiten in einem Lauf.

- Pause zwischen zwei Abrufen (Vorgabe 1,5 s) – kein Dauerfeuer auf fremde Shops
- robots.txt wird beachtet (abschaltbar, z.B. für die eigene Seite)
- Obergrenze an Abrufen je Lauf
- jeder Abruf über den SSRF-Schutz (net_guard): nie ins interne Netz
"""
import logging
import time
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

logger = logging.getLogger(__name__)

STANDARD_USER_AGENT = "Datenmonster/1.0 (Preisbeobachtung; +https://monstersuite.de)"


class AbrufGrenze(Exception):
    pass


class Abrufer:
    def __init__(self, headers: dict, timeout: int = 30, pause_ms: int = 1500,
                 max_abrufe: int = 200, robots_beachten: bool = True):
        self.headers = dict(headers or {})
        if not self.headers.get("User-Agent") or self.headers["User-Agent"] == "Datenmonster/1.0":
            self.headers["User-Agent"] = STANDARD_USER_AGENT
        self.timeout = timeout
        self.pause = max(0, int(pause_ms or 0)) / 1000.0
        self.max_abrufe = max(1, int(max_abrufe or 200))
        self.robots_beachten = robots_beachten
        self.session = requests.Session()
        self.abrufe = 0
        self._letzter = 0.0
        self._robots: Dict[str, Optional[RobotFileParser]] = {}
        self.uebersprungen = []   # (url, grund)

    def _robots_fuer(self, url: str) -> Optional[RobotFileParser]:
        teile = urlparse(url)
        basis = f"{teile.scheme}://{teile.netloc}"
        if basis in self._robots:
            return self._robots[basis]
        rp = None
        try:
            from app.core.net_guard import guarded_request
            r = guarded_request(self.session, "GET", urljoin(basis, "/robots.txt"),
                                headers=self.headers, timeout=min(self.timeout, 10),
                                allow_redirects=True)
            if r.status_code == 200:
                rp = RobotFileParser()
                rp.parse(r.text.splitlines())
        except Exception as e:  # keine robots.txt erreichbar = keine Einschränkung
            logger.info(f"robots.txt {basis}: {e}")
        self._robots[basis] = rp
        return rp

    def erlaubt(self, url: str) -> bool:
        if not self.robots_beachten:
            return True
        rp = self._robots_fuer(url)
        return rp is None or rp.can_fetch(self.headers["User-Agent"], url)

    def holen(self, url: str) -> Optional[str]:
        """HTML der Seite – oder None, wenn robots.txt den Abruf verbietet.
        Wirft AbrufGrenze, wenn die Obergrenze erreicht ist."""
        if not self.erlaubt(url):
            self.uebersprungen.append((url, "robots.txt verbietet den Abruf"))
            return None
        if self.abrufe >= self.max_abrufe:
            raise AbrufGrenze(f"Obergrenze von {self.max_abrufe} Abrufen erreicht")
        warten = self.pause - (time.monotonic() - self._letzter)
        if self.abrufe and warten > 0:
            time.sleep(warten)
        from app.core.net_guard import guarded_request
        self.abrufe += 1
        self._letzter = time.monotonic()
        r = guarded_request(self.session, "GET", url, headers=self.headers,
                            timeout=self.timeout, allow_redirects=True)
        if r.status_code == 429:
            # Seite bittet um Pause: einmal warten und neu versuchen
            time.sleep(min(int(r.headers.get("Retry-After", "10") or 10), 60))
            r = guarded_request(self.session, "GET", url, headers=self.headers,
                                timeout=self.timeout, allow_redirects=True)
        r.raise_for_status()
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding
        return r.text
