import { writeFileSync, mkdirSync } from 'fs'

const files = {

// ─────────────────────────────────────────
'src/pages/Users/UsersPage.css': `
.users-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.users-page__header-actions {
  display: flex;
  gap: 8px;
}
.users-page__role-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}
.users-page__role-card {
  background: var(--card-bg);
  border-radius: var(--radius-lg);
  border: 1px solid var(--neutral-5);
  box-shadow: var(--shadow-card);
  padding: 16px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  transition: box-shadow var(--transition-base), transform var(--transition-base);
}
.users-page__role-card:hover {
  box-shadow: var(--shadow-card-hover);
  transform: translateY(-1px);
}
.users-page__role-card-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.users-page__role-card-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.users-page__role-card-count {
  font-size: 24px;
  font-weight: 700;
  color: var(--neutral-10);
  line-height: 1.2;
}
.users-page__role-card-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--neutral-7);
}
.users-page__filters {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--neutral-4);
  flex-wrap: wrap;
}
.users-page__filter-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.users-page__filter-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--neutral-7);
  white-space: nowrap;
}
.users-page__role-btns {
  display: flex;
  gap: 4px;
}
.users-page__role-btn {
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid var(--neutral-5);
  border-radius: 100px;
  background: var(--neutral-1);
  color: var(--neutral-7);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font-family);
  white-space: nowrap;
}
.users-page__role-btn:hover {
  border-color: var(--primary-4);
  color: var(--primary-6);
}
.users-page__role-btn--active {
  background: var(--primary-6);
  border-color: var(--primary-6);
  color: #fff;
}
.users-page__role-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 100px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.users-table__id {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--neutral-6);
}
.users-table__name-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.users-table__avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  background: var(--primary-1);
  border: 1px solid var(--primary-2);
  color: var(--primary-7);
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.users-table__name-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.users-table__full-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--neutral-10);
}
.users-table__username {
  font-size: 11px;
  color: var(--neutral-6);
  font-family: var(--font-mono);
}
.users-table__email {
  font-size: 13px;
  color: var(--neutral-8);
}
.users-table__date {
  font-size: 12px;
  color: var(--neutral-7);
}
.users-table__null {
  color: var(--neutral-5);
  font-size: 12px;
}
.users-table__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}
.users-table__action-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  background: transparent;
}
.users-table__action-btn--edit {
  color: var(--warning-main);
}
.users-table__action-btn--edit:hover {
  background: var(--warning-light);
}
.users-table__action-btn--delete {
  color: var(--error-main);
}
.users-table__action-btn--delete:hover {
  background: var(--error-light);
}
@media (max-width: 1100px) {
  .users-page__role-cards {
    grid-template-columns: repeat(2, 1fr);
  }
}
`.trim(),

// ─────────────────────────────────────────
'src/pages/Users/UserModal.css': `
.user-modal__body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.user-modal__api-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--error-light);
  border: 1px solid var(--error-border);
  border-radius: var(--radius-md);
  color: var(--error-dark);
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 8px;
}
.user-modal__grid {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.user-modal__field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.user-modal__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--neutral-9);
}
.user-modal__required {
  color: var(--error-main);
  margin-left: 3px;
}
.user-modal__input {
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--neutral-5);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-family: var(--font-family);
  color: var(--neutral-10);
  background: var(--neutral-1);
  outline: none;
  transition: all var(--transition-fast);
  width: 100%;
}
.user-modal__input:focus {
  border-color: var(--primary-5);
  box-shadow: 0 0 0 2px var(--primary-1);
}
.user-modal__input--error {
  border-color: var(--error-main);
}
.user-modal__input--error:focus {
  box-shadow: 0 0 0 2px var(--error-light);
}
.user-modal__input--password {
  padding-right: 38px;
}
.user-modal__input-wrap {
  position: relative;
}
.user-modal__eye {
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--neutral-6);
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: color var(--transition-fast);
  padding: 2px;
}
.user-modal__eye:hover {
  color: var(--neutral-9);
}
.user-modal__select {
  height: 36px;
  padding: 0 12px;
  border: 1px solid var(--neutral-5);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-family: var(--font-family);
  color: var(--neutral-10);
  background: var(--neutral-1);
  outline: none;
  transition: all var(--transition-fast);
  width: 100%;
  cursor: pointer;
}
.user-modal__select:focus {
  border-color: var(--primary-5);
  box-shadow: 0 0 0 2px var(--primary-1);
}
.user-modal__select:disabled {
  background: var(--neutral-3);
  cursor: not-allowed;
  color: var(--neutral-7);
}
.user-modal__hint {
  font-size: 11px;
  color: var(--neutral-6);
}
.user-modal__field-error {
  font-size: 12px;
  color: var(--error-main);
}
.user-modal__toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.user-modal__toggle {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
  cursor: pointer;
}
.user-modal__toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}
.user-modal__toggle-slider {
  position: absolute;
  inset: 0;
  background: var(--neutral-5);
  border-radius: 22px;
  transition: background var(--transition-fast);
}
.user-modal__toggle-slider::before {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: white;
  left: 3px;
  top: 3px;
  transition: transform var(--transition-fast);
  box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}
.user-modal__toggle input:checked + .user-modal__toggle-slider {
  background: var(--primary-6);
}
.user-modal__toggle input:checked + .user-modal__toggle-slider::before {
  transform: translateX(18px);
}
.user-modal__toggle-label {
  font-size: 13px;
  color: var(--neutral-8);
  font-weight: 500;
}
`.trim(),

// ─────────────────────────────────────────
'src/pages/Users/DeleteUserModal.css': `
.del-user-modal__body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  text-align: center;
}
.del-user-modal__icon {
  width: 56px;
  height: 56px;
  background: var(--error-light);
  border: 1px solid var(--error-border);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.del-user-modal__user-card {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  background: var(--neutral-3);
  border: 1px solid var(--neutral-5);
  border-radius: var(--radius-lg);
  text-align: left;
}
.del-user-modal__avatar {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background: var(--error-light);
  border: 1px solid var(--error-border);
  color: var(--error-dark);
  font-size: 14px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.del-user-modal__user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.del-user-modal__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--neutral-10);
}
.del-user-modal__username {
  font-size: 12px;
  color: var(--neutral-6);
  font-family: var(--font-mono);
}
.del-user-modal__email {
  font-size: 12px;
  color: var(--neutral-7);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.del-user-modal__role {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: var(--neutral-7);
  background: var(--neutral-4);
  padding: 4px 10px;
  border-radius: 100px;
  white-space: nowrap;
  flex-shrink: 0;
}
.del-user-modal__desc {
  font-size: 13px;
  color: var(--neutral-7);
  line-height: 1.6;
  max-width: 320px;
  margin: 0;
}
.del-user-modal__desc strong {
  color: var(--error-dark);
}
.del-user-modal__error {
  width: 100%;
  padding: 10px 14px;
  background: var(--error-light);
  border: 1px solid var(--error-border);
  border-radius: var(--radius-md);
  color: var(--error-dark);
  font-size: 13px;
  font-weight: 500;
}
`.trim(),

// ─────────────────────────────────────────
'src/pages/Users/DeleteUserModal.jsx': `
import React, { useState } from 'react'
import { AlertTriangle, ShieldOff } from 'lucide-react'
import Modal from '@/components/common/Modal'
import Button from '@/components/common/Button'
import { usersApi } from '@/api/endpoints'
import './DeleteUserModal.css'

const ROLE_LABELS = {
  SUPER_ADMIN: 'Super Admin',
  ADMIN: 'Admin',
  PROJECT_MANAGER: 'Project Manager',
  USER: 'User',
}

const DeleteUserModal = ({ open, onClose, onSuccess, user }) => {
  const [loading, setLoading] = useState(false)
  const [apiError, setApiError] = useState('')

  const handleDelete = async () => {
    if (!user) return
    setLoading(true)
    setApiError('')
    try {
      await usersApi.delete(user.id)
      onSuccess()
    } catch (err) {
      setApiError(
        err.response?.data?.detail || 'Failed to delete user.'
      )
    } finally {
      setLoading(false)
    }
  }

  if (!user) return null

  const initials = user.full_name
    ? user.full_name.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2)
    : user.username.slice(0, 2).toUpperCase()

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Delete User"
      width={420}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant="primary"
            danger
            onClick={handleDelete}
            loading={loading}
          >
            Delete User
          </Button>
        </>
      }
    >
      <div className="del-user-modal__body">
        <div className="del-user-modal__icon">
          <AlertTriangle size={26} color="var(--error-main)" />
        </div>
        <div className="del-user-modal__user-card">
          <div className="del-user-modal__avatar">{initials}</div>
          <div className="del-user-modal__user-info">
            <span className="del-user-modal__name">
              {user.full_name || user.username}
            </span>
            <span className="del-user-modal__username">
              @{user.username}
            </span>
            <span className="del-user-modal__email">{user.email}</span>
          </div>
          <div className="del-user-modal__role">
            <ShieldOff size={13} />
            {ROLE_LABELS[user.role] || user.role}
          </div>
        </div>
        <p className="del-user-modal__desc">
          This action is <strong>permanent</strong> and cannot be undone.
          The user will lose all access to the platform immediately.
        </p>
        {apiError && (
          <div className="del-user-modal__error">{apiError}</div>
        )}
      </div>
    </Modal>
  )
}

export default DeleteUserModal
`.trim(),

}

// ── Write all files ──
for (const [filePath, content] of Object.entries(files)) {
  const dir = filePath.substring(0, filePath.lastIndexOf('/'))
  mkdirSync(dir, { recursive: true })
  writeFileSync(filePath, content, 'utf8')
  console.log(`✅ Written: ${filePath}`)
}

// ── Verify no CSS has JSX ──
import { readFileSync, readdirSync, statSync } from 'fs'
import { join } from 'path'

const getAllCss = (dir) => {
  let results = []
  for (const file of readdirSync(dir)) {
    const full = join(dir, file)
    if (statSync(full).isDirectory()) {
      results = results.concat(getAllCss(full))
    } else if (file.endsWith('.css')) {
      results.push(full)
    }
  }
  return results
}

console.log('\n── Verification ──')
let allOk = true
for (const cssFile of getAllCss('src')) {
  const content = readFileSync(cssFile, 'utf8')
  if (content.includes('import React') || content.includes('import {')) {
    console.log(`❌ CORRUPTED: ${cssFile}`)
    allOk = false
  } else {
    console.log(`✅ OK: ${cssFile}`)
  }
}

if (allOk) {
  console.log('\n✅ All CSS files are clean. Run: npm run build')
} else {
  console.log('\n❌ Some files still corrupted. Check manually.')
}