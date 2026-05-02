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