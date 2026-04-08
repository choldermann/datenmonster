import { useState } from "react";
import { Check, KeyRound, Loader2, X } from "lucide-react";
import api from "../../../api/client";
import { S } from "../constants";

function ChangePasswordModal({ onClose }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const handleSave = async () => {
    setError("");
    if (next.length < 6) { setError("Neues Passwort mindestens 6 Zeichen"); return; }
    if (next !== confirm) { setError("Passwörter stimmen nicht überein"); return; }
    setSaving(true);
    try {
      await api.post("/api/auth/change-password", { current_password: current, new_password: next });
      setDone(true);
      setTimeout(onClose, 1500);
    } catch (e) {
      setError(e.response?.data?.detail || "Fehler beim Ändern");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Passwort ändern" onClose={onClose}>
      <div className="flex flex-col gap-4">
        {done ? (
          <div className="flex items-center gap-2 text-sm" style={{ color: "#6ee7b7" }}>
            <Check size={16} /> Passwort erfolgreich geändert
          </div>
        ) : (
          <>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: S.textDim }}>Aktuelles Passwort</label>
              <input type="password" className="input" value={current}
                onChange={(e) => setCurrent(e.target.value)} autoFocus />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: S.textDim }}>Neues Passwort</label>
              <input type="password" className="input" value={next}
                onChange={(e) => setNext(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs" style={{ color: S.textDim }}>Neues Passwort bestätigen</label>
              <input type="password" className="input" value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSave()} />
            </div>
            {error && <p className="text-xs" style={{ color: "#e07070" }}>{error}</p>}
            <div className="flex gap-3 justify-end">
              <button onClick={onClose} className="btn-ghost text-xs">Abbrechen</button>
              <button onClick={handleSave} disabled={saving || !current || !next || !confirm}
                className="btn-primary text-xs">
                {saving && <Loader2 size={12} className="animate-spin" />} Speichern
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}

// ─── Active Project Banner ────────────────────────────────────────────────────

export default ChangePasswordModal;
