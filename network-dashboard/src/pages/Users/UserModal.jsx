import React, { useState, useEffect } from 'react'
import { Eye, EyeOff, AlertCircle } from 'lucide-react'
import Modal from '@/components/common/Modal'
import Button from '@/components/common/Button'
import { usersApi } from '@/api/endpoints'
import './UserModal.css'

/* ── available roles per current user role ── */
const ROLES_FOR = {
  SUPER_ADMIN: ['SUPER_ADMIN', 'ADMIN', 'PROJECT_MANAGER', 'USER'],
  ADMIN: ['ADMIN', 'PROJECT_MANAGER', 'USER'],
}

const ROLE_LABELS = {
  SUPER_ADMIN: 'Super Admin',
  ADMIN: 'Admin',
  PROJECT_MANAGER: 'Project Manager',
  USER: 'User',
}

const DEFAULT_FORM = {
  username: '',
  email: '',
  full_name: '',
  password: '',
  role: 'USER',
  is_active: true,
}

const Field = ({ label, error, required, children, hint }) => (
  <div className="user-modal__field">
    <label className="user-modal__label">
      {label}
      {required && <span className="user-modal__required">*</span>}
    </label>
    {children}
    {hint && !error && (
      <span className="user-modal__hint">{hint}</span>
    )}
    {error && (
      <span className="user-modal__field-error">{error}</span>
    )}
  </div>
)

const UserModal = ({
  open,
  onClose,
  onSuccess,
  mode = 'create',
  initial,
  currentUserRole = 'ADMIN',
}) => {
  const [form, setForm] = useState(DEFAULT_FORM)
  const [errors, setErrors] = useState({})
  const [apiError, setApiError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPass, setShowPass] = useState(false)

  const availableRoles = ROLES_FOR[currentUserRole] || ROLES_FOR.ADMIN

  useEffect(() => {
    if (!open) return
    setErrors({})
    setApiError('')
    setShowPass(false)

    if (mode === 'edit' && initial) {
      setForm({
        username: initial.username || '',
        email: initial.email || '',
        full_name: initial.full_name || '',
        password: '',
        role: initial.role || 'USER',
        is_active: initial.is_active ?? true,
      })
    } else {
      setForm(DEFAULT_FORM)
    }
  }, [open, mode, initial])

  const set = (key, val) => {
    setForm((p) => ({ ...p, [key]: val }))
    setErrors((p) => ({ ...p, [key]: '' }))
    setApiError('')
  }

  /* ── Validate ── */
  const validate = () => {
    const errs = {}

    if (mode === 'create') {
      if (!form.username.trim())
        errs.username = 'Username is required.'
      else if (form.username.trim().length < 3)
        errs.username = 'Minimum 3 characters.'
      else if (form.username.trim().length > 32)
        errs.username = 'Maximum 32 characters.'

      if (!form.password)
        errs.password = 'Password is required.'
      else if (form.password.length < 8)
        errs.password = 'Minimum 8 characters.'
      else if (!/[a-z]/.test(form.password))
        errs.password = 'Must contain a lowercase letter.'
      else if (!/[A-Z]/.test(form.password))
        errs.password = 'Must contain an uppercase letter.'
      else if (!/\d/.test(form.password))
        errs.password = 'Must contain a digit.'
      else if (!/[^a-zA-Z0-9]/.test(form.password))
        errs.password = 'Must contain a special character.'
    } else {
      /* edit mode — password optional */
      if (form.password) {
        if (form.password.length < 8)
          errs.password = 'Minimum 8 characters.'
        else if (!/[a-z]/.test(form.password))
          errs.password = 'Must contain a lowercase letter.'
        else if (!/[A-Z]/.test(form.password))
          errs.password = 'Must contain an uppercase letter.'
        else if (!/\d/.test(form.password))
          errs.password = 'Must contain a digit.'
        else if (!/[^a-zA-Z0-9]/.test(form.password))
          errs.password = 'Must contain a special character.'
      }
    }

    if (!form.email.trim())
      errs.email = 'Email is required.'
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email))
      errs.email = 'Enter a valid email address.'

    if (!form.full_name.trim())
      errs.full_name = 'Full name is required.'
    else if (form.full_name.trim().length < 2)
      errs.full_name = 'Minimum 2 characters.'

    return errs
  }

  /* ── Submit ── */
  const handleSubmit = async () => {
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }

    setLoading(true)
    setApiError('')

    try {
      if (mode === 'create') {
        await usersApi.create({
          username: form.username.trim(),
          email: form.email.trim().toLowerCase(),
          full_name: form.full_name.trim(),
          password: form.password,
          role: form.role,
        })
      } else {
        const payload = {}
        if (form.email !== initial.email)
          payload.email = form.email.trim().toLowerCase()
        if (form.full_name !== initial.full_name)
          payload.full_name = form.full_name.trim()
        if (form.role !== initial.role)
          payload.role = form.role
        if (form.is_active !== initial.is_active)
          payload.is_active = form.is_active
        if (form.password)
          payload.password = form.password

        if (Object.keys(payload).length === 0) {
          onClose()
          return
        }
        await usersApi.update(initial.id, payload)
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

  const title =
    mode === 'create'
      ? 'Create New User'
      : `Edit User — ${initial?.username}`

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      width={520}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit} loading={loading}>
            {mode === 'create' ? 'Create User' : 'Save Changes'}
          </Button>
        </>
      }
    >
      <div className="user-modal__body">
        {/* API error */}
        {apiError && (
          <div className="user-modal__api-error">
            <AlertCircle size={14} />
            <span>{apiError}</span>
          </div>
        )}

        <div className="user-modal__grid">
          {/* Username — create only */}
          {mode === 'create' && (
            <Field
              label="Username"
              required
              error={errors.username}
              hint="3–32 characters"
            >
              <input
                className={`user-modal__input ${
                  errors.username ? 'user-modal__input--error' : ''
                }`}
                value={form.username}
                onChange={(e) => set('username', e.target.value)}
                placeholder="e.g. john.doe"
                autoComplete="off"
              />
            </Field>
          )}

          {/* Full name */}
          <Field
            label="Full Name"
            required
            error={errors.full_name}
          >
            <input
              className={`user-modal__input ${
                errors.full_name ? 'user-modal__input--error' : ''
              }`}
              value={form.full_name}
              onChange={(e) => set('full_name', e.target.value)}
              placeholder="e.g. John Doe"
            />
          </Field>

          {/* Email */}
          <Field label="Email" required error={errors.email}>
            <input
              className={`user-modal__input ${
                errors.email ? 'user-modal__input--error' : ''
              }`}
              type="email"
              value={form.email}
              onChange={(e) => set('email', e.target.value)}
              placeholder="e.g. john@company.com"
              autoComplete="off"
            />
          </Field>

          {/* Password */}
          <Field
            label={
              mode === 'edit'
                ? 'New Password (leave blank to keep)'
                : 'Password'
            }
            required={mode === 'create'}
            error={errors.password}
            hint={
              mode === 'create'
                ? 'Min 8 chars, upper + lower + digit + special'
                : undefined
            }
          >
            <div className="user-modal__input-wrap">
              <input
                className={`user-modal__input user-modal__input--password ${
                  errors.password ? 'user-modal__input--error' : ''
                }`}
                type={showPass ? 'text' : 'password'}
                value={form.password}
                onChange={(e) => set('password', e.target.value)}
                placeholder="••••••••"
                autoComplete="new-password"
              />
              <button
                type="button"
                className="user-modal__eye"
                onClick={() => setShowPass((v) => !v)}
                tabIndex={-1}
              >
                {showPass ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </Field>

          {/* Role */}
          <Field label="Role" required error={errors.role}>
            <select
              className="user-modal__select"
              value={form.role}
              onChange={(e) => set('role', e.target.value)}
              disabled={
                mode === 'edit' &&
                currentUserRole !== 'SUPER_ADMIN'
              }
            >
              {availableRoles.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABELS[r]}
                </option>
              ))}
            </select>
            {mode === 'edit' && currentUserRole !== 'SUPER_ADMIN' && (
              <span className="user-modal__hint">
                Only Super Admins can change roles.
              </span>
            )}
          </Field>

          {/* Active toggle — edit only */}
          {mode === 'edit' && (
            <Field label="Account Status" error={errors.is_active}>
              <div className="user-modal__toggle-row">
                <label className="user-modal__toggle">
                  <input
                    type="checkbox"
                    checked={form.is_active}
                    onChange={(e) => set('is_active', e.target.checked)}
                  />
                  <span className="user-modal__toggle-slider" />
                </label>
                <span className="user-modal__toggle-label">
                  {form.is_active ? 'Active' : 'Disabled'}
                </span>
              </div>
            </Field>
          )}
        </div>
      </div>
    </Modal>
  )
}

export default UserModal