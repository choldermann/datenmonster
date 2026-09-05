import { useState, useRef } from "react";
import { Mail, Send, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import api, { fehlerText } from "../../api/client";

/**
 * Wiederverwendbarer "E-Mail"-Button + Popover-Panel: verschickt die aktuell
 * angezeigte Tabelle (columns + rows) als CSV-Anhang samt HTML-Vorschau an
 * Mitarbeiter. Wird überall neben einem CSV-Download-Button eingesetzt
 * (TableWidget, DrilldownModal, PortalRunner). Das Panel ist position:fixed,
 * damit es nicht von overflow:hidden-Containern (z.B. Modal) abgeschnitten wird.
 */
export default function EmailTableButton({ columns = [], rows = [], title = "Tabelle", disabled = false }) {
  const btnRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const [recipients, setRecipients] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState(null);   // { ok, text }

  const PANEL_W = 340;
  const toggle = () => {
    if (!open && btnRef.current) {
      const r = btnRef.current.getBoundingClientRect();
      setPos({
        top: r.bottom + 6,
        left: Math.max(8, Math.min(r.right - PANEL_W, window.innerWidth - PANEL_W - 8)),
      });
    }
    setMsg(null);
    setOpen(o => !o);
  };

  const send = async () => {
    if (!recipients.trim()) { setMsg({ ok: false, text: "Bitte mindestens einen Empfänger angeben." }); return; }
    setSending(true); setMsg(null);
    try {
      const { data } = await api.post("/api/forms/email-table", {
        recipients, subject: subject || null, message: message || null,
        title: title || "Tabelle", columns, rows,
      });
      setMsg({ ok: true, text: `Gesendet an ${data.recipients.join(", ")} (${data.rows} Zeilen).` });
      setTimeout(() => { setOpen(false); setMsg(null); }, 2500);
    } catch (e) {
      setMsg({ ok: false, text: fehlerText(e, "Versand fehlgeschlagen.") });
    } finally { setSending(false); }
  };

  const inputStyle = {
    width: "100%", padding: "6px 9px", fontSize: 12, borderRadius: 5,
    border: "1px solid var(--border)", backgroundColor: "var(--bg-elevated)",
    color: "var(--text-main)", boxSizing: "border-box",
  };

  return (
    <div style={{ display: "inline-block" }}>
      <button ref={btnRef} onClick={toggle} disabled={disabled}
        title="Tabelle per E-Mail an Mitarbeiter senden"
        style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11,
          color: open ? "var(--accent)" : "var(--text-main)", background: open ? "rgba(255,255,255,0.05)" : "none",
          border: `1px solid ${open ? "var(--accent)" : "var(--border)"}`, borderRadius: 5,
          padding: "4px 10px", cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1 }}>
        <Mail size={11} /> E-Mail
      </button>

      {open && (
        <>
          <div onClick={() => setOpen(false)}
            style={{ position: "fixed", inset: 0, zIndex: 3000 }} />
          <div style={{ position: "fixed", top: pos.top, left: pos.left, width: PANEL_W, zIndex: 3001,
            backgroundColor: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 8,
            boxShadow: "0 12px 40px rgba(0,0,0,0.45)", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "var(--text-bright)", display: "flex", alignItems: "center", gap: 6 }}>
              <Mail size={13} /> Tabelle per E-Mail senden
            </div>
            <input value={recipients} onChange={e => setRecipients(e.target.value)}
              placeholder="Empfänger (mehrere mit Komma trennen)" style={inputStyle} />
            <input value={subject} onChange={e => setSubject(e.target.value)}
              placeholder={`Betreff (Standard: „Cockpit: ${title}")`} style={inputStyle} />
            <textarea value={message} onChange={e => setMessage(e.target.value)} rows={3}
              placeholder="Nachricht an die Mitarbeiter (optional)"
              style={{ ...inputStyle, resize: "vertical", fontFamily: "inherit" }} />
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <button onClick={send} disabled={sending || !rows.length}
                style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 5,
                  fontSize: 12, fontWeight: 700, cursor: sending ? "wait" : "pointer", border: "none",
                  backgroundColor: "var(--accent)", color: "#1a1a1a" }}>
                {sending ? <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} /> : <Send size={13} />}
                {sending ? "Sende…" : `Senden (${rows.length})`}
              </button>
              {msg && (
                <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11.5,
                  color: msg.ok ? "#5cb85c" : "#e07070" }}>
                  {msg.ok ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />} {msg.text}
                </span>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
