import logging
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.core.security import get_current_user
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/plugins/web", tags=["web-proxy"])

# Interne Hosts dürfen nicht proxied werden
_BLOCKED_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}

# ── Visual-Selektor Script ────────────────────────────────────────────────────
_SELECTOR_SCRIPT = """
<script id="__dm_selector__">
(function() {
  var _mode = null;   // 'field' | 'row' | null
  var _hover = null;

  /* Highlight-Overlay */
  var ov = document.createElement('div');
  ov.style.cssText = [
    'position:fixed','pointer-events:none','z-index:2147483647',
    'border:2px solid #fce499','background:rgba(252,228,153,0.12)',
    'box-sizing:border-box','display:none','transition:none',
    'border-radius:2px'
  ].join(';');
  document.documentElement.appendChild(ov);

  function showOverlay(el) {
    var r = el.getBoundingClientRect();
    ov.style.left   = r.left + 'px';
    ov.style.top    = r.top  + 'px';
    ov.style.width  = r.width  + 'px';
    ov.style.height = r.height + 'px';
    ov.style.borderColor = _mode === 'row' ? '#6ee7b7' : '#fce499';
    ov.style.background  = _mode === 'row'
      ? 'rgba(110,231,183,0.1)' : 'rgba(252,228,153,0.1)';
    ov.style.display = 'block';
  }

  /* CSS-Pfad-Berechnung */
  function cssPath(el) {
    var parts = []; var cur = el; var depth = 0;
    while (cur && cur.tagName && cur !== document.body && depth < 8) {
      var tag = cur.tagName.toLowerCase();
      /* ID reicht als eindeutiger Selektor */
      if (cur.id && /^[a-zA-Z][\w-]*$/.test(cur.id)) {
        parts.unshift('#' + cur.id); break;
      }
      /* Semantische Klassen (keine generierten Hash-Klassen) */
      var cls = [];
      for (var i = 0; i < cur.classList.length && cls.length < 2; i++) {
        var c = cur.classList[i];
        if (/^[a-z][a-z0-9_-]{1,40}$/i.test(c)) cls.push(c);
      }
      var part = cls.length ? tag + '.' + cls.join('.') : tag;
      /* nth-of-type wenn Geschwister vorhanden */
      if (cur.parentElement) {
        var sibs = [].filter.call(cur.parentElement.children,
          function(s){ return s.tagName === cur.tagName; });
        if (sibs.length > 1)
          part += ':nth-of-type(' + (sibs.indexOf(cur) + 1) + ')';
      }
      parts.unshift(part); cur = cur.parentElement; depth++;
    }
    return parts.join(' > ');
  }

  function countMatches(sel) {
    try { return document.querySelectorAll(sel).length; } catch(e) { return 0; }
  }

  /* Events */
  document.addEventListener('mouseover', function(e) {
    if (!_mode) return;
    _hover = e.target; showOverlay(e.target); e.stopPropagation();
  }, true);

  document.addEventListener('mouseout', function(e) {
    if (!_mode) return;
    ov.style.display = 'none';
  }, true);

  document.addEventListener('click', function(e) {
    if (!_mode) return;
    e.preventDefault(); e.stopPropagation();
    var el  = e.target;
    var sel = cssPath(el);
    var txt = (el.innerText || el.getAttribute('src') || el.getAttribute('href') || '')
                .trim().slice(0, 120);
    window.parent.postMessage({
      type:     'dm_element_selected',
      mode:     _mode,
      selector: sel,
      sample:   txt,
      tagName:  el.tagName.toLowerCase(),
      matches:  countMatches(sel),
    }, '*');
  }, true);

  /* Befehle vom Parent empfangen */
  window.addEventListener('message', function(e) {
    if (!e.data || e.data.source !== 'datenmonster') return;
    if (e.data.cmd === 'set_mode') {
      _mode = e.data.mode;
      document.body.style.cursor = _mode ? 'crosshair' : '';
      ov.style.display = 'none';
    }
  });

  /* Bereit-Signal an Parent */
  window.parent.postMessage({ type: 'dm_ready' }, '*');
})();
</script>
"""


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _validate_url(url: str) -> None:
    try:
        p = urlparse(url)
    except Exception:
        raise HTTPException(400, "Ungültige URL")
    if p.scheme not in ("http", "https"):
        raise HTTPException(400, "Nur HTTP/HTTPS-URLs erlaubt")
    host = p.hostname or ""
    if (host in _BLOCKED_HOSTS
            or host.startswith("192.168.")
            or host.startswith("10.")
            or host.startswith("172.")):
        raise HTTPException(403, "Interne URLs sind nicht erlaubt")


def _fetch_html(url: str) -> tuple[str, str]:
    """Gibt (html_text, effective_url) zurück."""
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Datenmonster/1.0)"},
            timeout=20,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise HTTPException(502, f"HTTP-Fehler: {e}")
    except Exception as e:
        raise HTTPException(502, f"Seite nicht erreichbar: {e}")

    charset = resp.apparent_encoding or "utf-8"
    html = resp.content.decode(charset, errors="replace")
    return html, resp.url


def _inject(html: str, base_url: str) -> str:
    """
    Fügt <base href> und das Selektor-Script in die Seite ein.
    BeautifulSoup wird nur für das strukturierte Einfügen genutzt –
    die komplette Seite wird als String zurückgegeben.
    """
    soup = BeautifulSoup(html, "lxml")

    # <base href> setzt alle relativen URLs automatisch richtig
    if not soup.head:
        head_tag = soup.new_tag("head")
        if soup.html:
            soup.html.insert(0, head_tag)
    existing_base = soup.find("base")
    if existing_base:
        existing_base["href"] = base_url
    else:
        base_tag = soup.new_tag("base", href=base_url)
        soup.head.insert(0, base_tag)

    # Selektor-Script vor </body> einbetten
    script_soup = BeautifulSoup(_SELECTOR_SCRIPT, "lxml")
    script_tag  = script_soup.find("script")
    if script_tag:
        if not soup.body:
            body_tag = soup.new_tag("body")
            soup.html.append(body_tag)
        soup.body.append(script_tag)

    return str(soup)


# ── Endpunkte ─────────────────────────────────────────────────────────────────

@router.get("/proxy", response_class=HTMLResponse)
def proxy_page(
    url: str = Query(..., description="URL der zu ladenden Webseite"),
    user: User = Depends(get_current_user),
):
    """
    Lädt eine externe Webseite, strippt blocking-Header und injiziert
    das Datenmonster Visual-Selektor-Script.
    Frontend holt das HTML per API-Call (mit Auth-Header) und erstellt
    einen Blob-URL für den iframe – kein Cookie/Token-Problem im iframe.
    """
    _validate_url(url)
    html, effective_url = _fetch_html(url)
    modified = _inject(html, effective_url)
    return HTMLResponse(content=modified)


class PreviewBody(BaseModel):
    config: dict
    limit: int = 20


@router.post("/preview")
def preview_extraction(
    body: PreviewBody,
    user: User = Depends(get_current_user),
):
    """Führt eine Extraktion durch und gibt Zeilen + Spalten zurück (für Vorschau im Visual Selektor)."""
    from app.plugins.registry import registry
    plugin = registry.get_source("doc_html")
    if not plugin:
        raise HTTPException(503, "HTML-Plugin nicht geladen")
    try:
        rows = plugin.fetch(dict(body.config, limit=body.limit))
        columns = list(rows[0].keys()) if rows else []
        return {"rows": rows, "columns": columns, "total": len(rows)}
    except NotImplementedError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Extraktion fehlgeschlagen: {e}")
