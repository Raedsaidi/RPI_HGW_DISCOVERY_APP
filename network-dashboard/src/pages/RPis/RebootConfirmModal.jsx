import React, { useEffect, useRef } from 'react'
import { PowerOff, AlertTriangle, X } from 'lucide-react'
import './RebootConfirmModal.css'

/**
 * RebootConfirmModal
 *
 * Props:
 *   open      {boolean}  — afficher / cacher
 *   ip        {string}   — IP du RPi ciblé
 *   onConfirm {function} — appelé quand l'user confirme
 *   onCancel  {function} — appelé quand l'user annule / ferme
 */
const RebootConfirmModal = ({ open, ip, onConfirm, onCancel }) => {
  const confirmBtnRef = useRef(null)

  /* focus le bouton Cancel par défaut (safer UX) */
  useEffect(() => {
    if (open) {
      const t = setTimeout(() => confirmBtnRef.current?.focus(), 50)
      return () => clearTimeout(t)
    }
  }, [open])

  /* fermeture sur Escape */
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onCancel() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open, onCancel])

  if (!open) return null

  return (
    <div className="rcm-overlay" onClick={onCancel}>
      <div
        className="rcm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="rcm-title"
        aria-describedby="rcm-desc"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ── Close ── */}
        <button className="rcm-close" onClick={onCancel} aria-label="Cancel">
          <X size={16} />
        </button>

        {/* ── Icon ── */}
        <div className="rcm-icon-wrap">
          <div className="rcm-icon-ring" />
          <PowerOff size={28} className="rcm-icon" />
        </div>

        {/* ── Content ── */}
        <h2 className="rcm-title" id="rcm-title">Reboot RPi</h2>

        <p className="rcm-desc" id="rcm-desc">
          You are about to hard-reboot
        </p>
        <div className="rcm-target">{ip}</div>

        <div className="rcm-warning">
          <AlertTriangle size={13} />
          <span>The device will lose power for several seconds via PoE cycle.</span>
        </div>

        {/* ── Actions ── */}
        <div className="rcm-actions">
          <button className="rcm-btn rcm-btn--cancel" onClick={onCancel}>
            Cancel
          </button>
          <button
            ref={confirmBtnRef}
            className="rcm-btn rcm-btn--confirm"
            onClick={onConfirm}
          >
            <PowerOff size={14} />
            Reboot
          </button>
        </div>
      </div>
    </div>
  )
}

export default RebootConfirmModal