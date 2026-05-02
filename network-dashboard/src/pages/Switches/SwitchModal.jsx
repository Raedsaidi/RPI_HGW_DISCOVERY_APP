import React, { useState, useEffect } from 'react'
import Modal from '@/components/common/Modal'
import Button from '@/components/common/Button'
import { switchesApi } from '@/api/endpoints'
import './SwitchModal.css'

const DEFAULT_FORM = {
  ip: '',
  name: '',
  telnet_port: 60000,
  telnet_user: 'admin',
  telnet_pass: '',
  enabled: true,
}

const Field = ({ label, error, required, children }) => (
  <div className="sw-modal__field">
    <label className="sw-modal__label">
      {label}
      {required && <span className="sw-modal__required">*</span>}
    </label>
    {children}
    {error && <span className="sw-modal__error">{error}</span>}
  </div>
)

const SwitchModal = ({ open, onClose, onSuccess, mode = 'create', initial }) => {
  const [form, setForm] = useState(DEFAULT_FORM)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const [apiError, setApiError] = useState('')

  useEffect(() => {
    if (open) {
      if (mode === 'edit' && initial) {
        setForm({
          ip: initial.ip || '',
          name: initial.name || '',
          telnet_port: initial.telnet_port ?? 60000,
          telnet_user: initial.telnet_user || 'admin',
          telnet_pass: '',
          enabled: initial.enabled ?? true,
        })
      } else {
        setForm(DEFAULT_FORM)
      }
      setErrors({})
      setApiError('')
    }
  }, [open, mode, initial])

  const set = (key, val) => {
    setForm((prev) => ({ ...prev, [key]: val }))
    setErrors((prev) => ({ ...prev, [key]: '' }))
    setApiError('')
  }

  /* ── Validation ── */
  const validate = () => {
    const errs = {}
    if (mode === 'create') {
      if (!form.ip.trim()) errs.ip = 'IP address is required.'
      else if (
        !/^(\d{1,3}\.){3}\d{1,3}$/.test(form.ip.trim())
      )
        errs.ip = 'Enter a valid IP address.'
    }
    if (!form.telnet_port || form.telnet_port < 1 || form.telnet_port > 65535)
      errs.telnet_port = 'Port must be between 1 and 65535.'
    if (!form.telnet_user.trim())
      errs.telnet_user = 'Telnet user is required.'
    return errs
  }

  /* ── Submit ── */
  const handleSubmit = async () => {
    const errs = validate()
    if (Object.keys(errs).length) {
      setErrors(errs)
      return
    }

    setLoading(true)
    setApiError('')

    try {
      if (mode === 'create') {
        await switchesApi.create({
          ip: form.ip.trim(),
          name: form.name.trim() || undefined,
          telnet_port: Number(form.telnet_port),
          telnet_user: form.telnet_user.trim(),
          telnet_pass: form.telnet_pass,
          enabled: form.enabled,
        })
      } else {
        const payload = {}
        if (form.name !== initial.name) payload.name = form.name.trim() || null
        if (Number(form.telnet_port) !== initial.telnet_port)
          payload.telnet_port = Number(form.telnet_port)
        if (form.telnet_user !== initial.telnet_user)
          payload.telnet_user = form.telnet_user.trim()
        if (form.telnet_pass) payload.telnet_pass = form.telnet_pass
        if (form.enabled !== initial.enabled) payload.enabled = form.enabled
        await switchesApi.update(initial.id, payload)
      }
      onSuccess()
    } catch (err) {
      setApiError(
        err.response?.data?.detail || 'An error occurred. Please try again.'
      )
    } finally {
      setLoading(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={mode === 'create' ? 'Add New Switch' : `Edit Switch — ${initial?.ip}`}
      width={500}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>
            {mode === 'create' ? 'Add Switch' : 'Save Changes'}
          </Button>
        </>
      }
    >
      <div className="sw-modal__body">
        {apiError && (
          <div className="sw-modal__api-error">{apiError}</div>
        )}

        <div className="sw-modal__grid">
          {/* IP */}
          {mode === 'create' && (
            <Field label="IP Address" required error={errors.ip}>
              <input
                className={`sw-modal__input ${errors.ip ? 'sw-modal__input--error' : ''}`}
                value={form.ip}
                onChange={(e) => set('ip', e.target.value)}
                placeholder="e.g. 172.16.55.238"
              />
            </Field>
          )}

          {/* Name */}
          <Field label="Name" error={errors.name}>
            <input
              className="sw-modal__input"
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              placeholder="e.g. Switch Floor 2"
            />
          </Field>

          {/* Telnet Port */}
          <Field label="Telnet Port" required error={errors.telnet_port}>
            <input
              className={`sw-modal__input ${errors.telnet_port ? 'sw-modal__input--error' : ''}`}
              type="number"
              value={form.telnet_port}
              onChange={(e) => set('telnet_port', e.target.value)}
              placeholder="60000"
            />
          </Field>

          {/* Telnet User */}
          <Field label="Telnet User" required error={errors.telnet_user}>
            <input
              className={`sw-modal__input ${errors.telnet_user ? 'sw-modal__input--error' : ''}`}
              value={form.telnet_user}
              onChange={(e) => set('telnet_user', e.target.value)}
              placeholder="admin"
            />
          </Field>

          {/* Telnet Pass */}
          <Field
            label={mode === 'edit' ? 'Telnet Password (leave blank to keep)' : 'Telnet Password'}
            error={errors.telnet_pass}
          >
            <input
              className="sw-modal__input"
              type="password"
              value={form.telnet_pass}
              onChange={(e) => set('telnet_pass', e.target.value)}
              placeholder="••••••••"
            />
          </Field>

          {/* Enabled */}
          <Field label="Status" error={errors.enabled}>
            <div className="sw-modal__toggle-row">
              <label className="sw-modal__toggle">
                <input
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(e) => set('enabled', e.target.checked)}
                />
                <span className="sw-modal__toggle-slider" />
              </label>
              <span className="sw-modal__toggle-label">
                {form.enabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
          </Field>
        </div>
      </div>
    </Modal>
  )
}

export default SwitchModal