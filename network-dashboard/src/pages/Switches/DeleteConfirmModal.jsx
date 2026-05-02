import React from 'react'
import { AlertTriangle } from 'lucide-react'
import Modal from '@/components/common/Modal'
import Button from '@/components/common/Button'
import './DeleteConfirmModal.css'

const DeleteConfirmModal = ({
  open,
  onClose,
  onConfirm,
  loading = false,
  title = 'Confirm Delete',
  description = 'Are you sure you want to delete this item? This action cannot be undone.',
}) => {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      width={420}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant="primary"
            danger
            onClick={onConfirm}
            loading={loading}
          >
            Delete
          </Button>
        </>
      }
    >
      <div className="del-modal__body">
        <div className="del-modal__icon">
          <AlertTriangle size={28} color="var(--error-main)" />
        </div>
        <p className="del-modal__desc">{description}</p>
      </div>
    </Modal>
  )
}

export default DeleteConfirmModal