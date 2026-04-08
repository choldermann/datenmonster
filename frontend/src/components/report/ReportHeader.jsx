import { useState } from "react";
import { ArrowLeft, Save, Eye, EyeOff, Loader2, FileDown, Mail, X, Check } from "lucide-react";
import { S } from "./constants";
import api from "../../api/client";

function EmailModal({ reportId, onClose }) {
  const [to, setTo]         = useState("");
  const [cc, setCc]         = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody]     = useState("");
  const [sending, setSending] = useState(false);
  const [sent, setSent]     = useState(false);
  const [error, setError]   = useState(null);

  const iS = {
    backgroundColor: S.bgEl, border: `1px solid ${S.border}`,
    borderRadius: 4, color: S.textBright, fontSize: 11,
    padding: "6px 10px", outline: "none", width: "100%", boxSizing: "border-box",
  };

  const handleSend = async () => {
    if (!to.trim()) { setError("Empfänger erforderlich"); return; }
    setSending(true); setError(null);
    try {
      await api.post(`/api/reports/${reportId}/email`, { to, cc: cc || undefined, subject: subject || undefined, body: body || undefined });
      setSent(true);
      setTimeout(onClose, 1500);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally { setSending(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.7)" }} onClick={onClose}>
      <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 8, padding: 24, width: 420, boxShadow: "0 24px 60px rgba(0,0,0,0.6)" }} onClick={e => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
          <div>
            <p style={{ fontSize: 13, fontWeight: 700, color: S.textBright, margin: 0 }}>Report per E-Mail senden</p>
            <p style={{ fontSize: 10, color: S.textDim, margin: "2px 0 0" }}>Report wird als PDF angehängt</p>
          </div>
          <button onClick={onClose} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer" }}><X size={14} /></button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div>
            <label style={{ fontSize: 10, color: S.textDim, display: "block", marginBottom: 4 }}>Empfänger *</label>
            <input style={iS} value={to} onChange={e => setTo(e.target.value)} placeholder="empfaenger@beispiel.de" />
          </div>
          <div>
            <label style={{ fontSize: 10, color: S.textDim, display: "block", marginBottom: 4 }}>CC</label>
            <input style={iS} value={cc} onChange={e => setCc(e.target.value)} placeholder="optional" />
          </div>
          <div>
            <label style={{ fontSize: 10, color: S.textDim, display: "block", marginBottom: 4 }}>Betreff</label>
            <input style={iS} value={subject} onChange={e => setSubject(e.target.value)} placeholder="Wird automatisch befüllt" />
          </div>
          <div>
            <label style={{ fontSize: 10, color: S.textDim, display: "block", marginBottom: 4 }}>Nachricht</label>
            <textarea style={{ ...iS, height: 70, resize: "vertical", fontFamily: "inherit" }} value={body} onChange={e => setBody(e.target.value)} placeholder="Optionaler Begleittext..." />
          </div>
        </div>

        {error && <p style={{ fontSize: 10, color: "#e07070", margin: "10px 0 0" }}>⚠ {error}</p>}

        <div style={{ display: "flex", gap: 8, marginTop: 16, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{ padding: "7px 14px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: S.textDim, fontSize: 11, cursor: "pointer" }}>Abbrechen</button>
          <button onClick={handleSend} disabled={sending || sent}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 16px", borderRadius: 4, border: "none", backgroundColor: sent ? "#22c55e" : "var(--accent)", color: "#111", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
            {sent ? <><Check size={13} /> Gesendet!</> : sending ? <><Loader2 size={13} className="animate-spin" /> Sende…</> : <><Mail size={13} /> Senden</>}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ReportHeader({ name, onNameChange, onBack, onSave, saving, preview, onTogglePreview, widgetCount, reportId }) {
  const [exporting, setExporting] = useState(false);
  const [showEmail, setShowEmail] = useState(false);

  const handlePdfDownload = async () => {
    if (!reportId || exporting) return;
    setExporting(true);
    try {
      const resp = await api.post(`/api/reports/${reportId}/pdf`, {}, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([resp.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${name || "report"}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert("PDF-Export fehlgeschlagen: " + (e.response?.data?.detail || e.message));
    } finally { setExporting(false); }
  };

  return (
    <>
      <div style={{ height: 52, flexShrink: 0, backgroundColor: S.bgCard, borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", padding: "0 16px", gap: 10 }}>
        <button onClick={onBack}
          style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: 5, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 11 }}
          onMouseEnter={e => e.currentTarget.style.color = S.textBright}
          onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
          <ArrowLeft size={13} /> Dashboard
        </button>

        <input value={name} onChange={e => onNameChange(e.target.value)} placeholder="Report Name"
          style={{ flex: 1, maxWidth: 300, backgroundColor: "transparent", border: "none", borderBottom: `1px solid ${S.border}`, color: S.textBright, fontSize: 14, fontWeight: 600, outline: "none", padding: "4px 0" }} />

        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 10, color: S.textDim }}>{widgetCount} Widget{widgetCount !== 1 ? "s" : ""}</span>

        {/* PDF-Export */}
        {reportId && (
          <button onClick={handlePdfDownload} disabled={exporting} title="Als PDF exportieren"
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: 5, border: `1px solid ${S.border}`, background: "none", color: exporting ? "var(--accent)" : S.textDim, cursor: "pointer", fontSize: 11 }}
            onMouseEnter={e => { if (!exporting) e.currentTarget.style.color = S.textBright; }}
            onMouseLeave={e => { if (!exporting) e.currentTarget.style.color = S.textDim; }}>
            {exporting ? <Loader2 size={13} className="animate-spin" /> : <FileDown size={13} />}
            PDF
          </button>
        )}

        {/* E-Mail senden */}
        {reportId && (
          <button onClick={() => setShowEmail(true)} title="Per E-Mail senden"
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: 5, border: `1px solid ${S.border}`, background: "none", color: S.textDim, cursor: "pointer", fontSize: 11 }}
            onMouseEnter={e => e.currentTarget.style.color = S.textBright}
            onMouseLeave={e => e.currentTarget.style.color = S.textDim}>
            <Mail size={13} /> Senden
          </button>
        )}

        <button onClick={onTogglePreview}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 5, border: `1px solid ${S.border}`, backgroundColor: preview ? "rgba(252,228,153,0.1)" : "transparent", color: preview ? "var(--accent)" : S.textDim, cursor: "pointer", fontSize: 11 }}>
          {preview ? <EyeOff size={13} /> : <Eye size={13} />}
          {preview ? "Bearbeiten" : "Vorschau"}
        </button>

        <button onClick={onSave} disabled={saving}
          style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 16px", borderRadius: 5, border: "none", backgroundColor: "var(--accent)", color: "#111", cursor: "pointer", fontSize: 12, fontWeight: 700 }}>
          {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
          Speichern
        </button>
      </div>

      {showEmail && reportId && (
        <EmailModal reportId={reportId} onClose={() => setShowEmail(false)} />
      )}
    </>
  );
}
