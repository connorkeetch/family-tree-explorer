import { useRef } from "react";
import { useFocusTrap } from "../lib/useFocusTrap";

/**
 * Themed confirmation dialog — replaces native window.confirm for destructive
 * actions so they match the app's dark theme. Closes on Escape or backdrop
 * click (treated as cancel); the confirm button can be styled as a danger action.
 */
export default function ConfirmDialog({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  error,
  onConfirm,
  onCancel,
}: {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, onCancel);

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div
        ref={ref}
        tabIndex={-1}
        className="modal confirm"
        role="alertdialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="modal-title" style={{ fontSize: 18 }}>
          {title}
        </h2>
        <p className="sub" style={{ marginBottom: 18 }}>
          {message}
        </p>
        {error && <div className="err" role="alert">{error}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onCancel}>{cancelLabel}</button>
          <button className={danger ? "btn-danger" : "btn-primary"} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
