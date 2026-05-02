import React, { useState, useEffect } from 'react'
import { KeyRound, AlertCircle } from 'lucide-react'
import Modal from '@/components/common/Modal'
import Button from '@/components/common/Button'
import { rpisApi } from '@/api/endpoints'
import './CredentialModal.css'

const CredentialModal = ({ open, onClose, rpiData, onSuccess }) => {
  const [form, setForm] = useState({ ssh_user: '', ssh_pass: '' })
  const [errors, setErrors] = useState({})
  const [apiError, setApiError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      setForm({ ssh_user: '', ssh_pass: '' })
      setErrors({})
      setApiError('')
    }
  }, [open])

  const set = (key, val) => {
    setForm((p) => ({ ...p, [key]: val }))
    setErrors((p) => ({ ...p, [key]: '' }))
    setApiError('')
  }

  const validate = () => {
    const errs = {}
    if (!form.ssh_user.trim()) errs.ssh_user = 'SSH user is required.'
    if (!form.ssh_pass) errs.ssh_pass = 'SSH password is required.'
    return errs
  }

  const handleSubmit = async () => {
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }

    setLoading(true)
    setApiError('')
    try {
      await rpisApi.submitCredentials({
        rpi_ip_mgmt: rpiData.ip_mgmt,
        ssh_user: form.ssh_user.trim(),
        ssh_pass: form.ssh_pass,
      })
      onSuccess()
    } catch (err) {
      setApiError(
        err.response?.data?.detail || 'Failed to save credentials.'
      )
    } finally {
      setLoading(false)
    }
  }

  if (!rpiData) return null

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="SSH Credentials"
      width={440}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>
            Save Credentials
          </Button>
        </>
      }
    >
      <div className="cred-modal__body">
        {/* Info banner */}
        <div className="cred-modal__info">
          <KeyRound size={14} />
          <div>
            <div className="cred-modal__info-title">
              Custom credentials for{' '}
              <span className="mono">{rpiData.ip_mgmt}</span>
            </div>
            <div className="cred-modal__info-sub">
              These will override the default credentials for the
              next discovery run.
            </div>
          </div>
        </div>

        {/* API error */}
        {apiError && (
          <div className="cred-modal__error">
            <AlertCircle size={14} />
            <span>{apiError}</span>
          </div>
        )}

        {/* Fields */}
        <div className="cred-modal__fields">
          <div className="cred-modal__field">
            <label className="cred-modal__label">
              SSH User <span className="cred-modal__required">*</span>
            </label>
            <input
              className={`cred-modal__input ${errors.ssh_user ? 'cred-modal__input--error' : ''}`}
              value={form.ssh_user}
              onChange={(e) => set('ssh_user', e.target.value)}
              placeholder="e.g. pi"
              autoComplete="off"
            />
            {errors.ssh_user && (
              <span className="cred-modal__field-error">{errors.ssh_user}</span>
            )}
          </div>

          <div className="cred-modal__field">
            <label className="cred-modal__label">
              SSH Password <span className="cred-modal__required">*</span>
            </label>
            <input
              className={`cred-modal__input ${errors.ssh_pass ? 'cred-modal__input--error' : ''}`}
              type="password"
              value={form.ssh_pass}
              onChange={(e) => set('ssh_pass', e.target.value)}
              placeholder="••••••••"
              autoComplete="new-password"
            />
            {errors.ssh_pass && (
              <span className="cred-modal__field-error">{errors.ssh_pass}</span>
            )}
          </div>
        </div>

        {/* Warning note */}
        <div className="cred-modal__note">
          <AlertCircle size={13} />
          <span>
            Credentials are stored and will be used in the next
            automatic or manual discovery run.
          </span>
        </div>
      </div>
    </Modal>
  )
}

export default CredentialModal