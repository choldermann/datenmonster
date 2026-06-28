import { X } from "lucide-react";
import { S } from "../constants";

function Modal({ title, onClose, children, width = "max-w-md" }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ backgroundColor: "rgba(0,0,0,0.75)", backdropFilter: "blur(4px)" }}>
      <div className={`w-full ${width} rounded-2xl flex flex-col`}
        style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}` }}>
        <div className="flex items-center justify-between px-6 py-4"
          style={{ borderBottom: `1px solid ${S.border}` }}>
          <h2 className="text-sm font-semibold" style={{ color: S.textBright }}>{title}</h2>
          <button onClick={onClose} style={{ color: S.textDim }} className="hover:text-white transition-colors">
            <X size={15} />
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

// ─── New Project Tile ─────────────────────────────────────────────────────────

export default Modal;
