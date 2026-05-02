import React, { useState, useEffect, useCallback } from 'react'
import {
  Users,
  Plus,
  RefreshCw,
  Pencil,
  Trash2,
  ShieldCheck,
  Shield,
  User,
  FolderKanban,
} from 'lucide-react'
import Card from '@/components/common/Card'
import Button from '@/components/common/Button'
import Table from '@/components/common/Table'
import SearchBar from '@/components/common/SearchBar'
import Pagination from '@/components/common/Pagination'
import { StatusBadge } from '@/components/common/Badge'
import Spinner from '@/components/common/Spinner'
import UserModal from './UserModal'
import DeleteUserModal from './DeleteUserModal'
import { usersApi } from '@/api/endpoints'
import { useAuth } from '@/context/AuthContext'
import { useNotification, NOTIFICATION_MESSAGES } from '@/context/NotificationContext'
import { getFriendlyMessage } from '@/utils/messageHelper'
import dayjs from 'dayjs'
import './UsersPage.css'

/* ── Role config ── */
const ROLE_CONFIG = {
  SUPER_ADMIN: {
    label: 'Super Admin',
    icon: ShieldCheck,
    color: '#f5222d',
    bg: '#fff1f0',
    border: '#ffa39e',
  },
  ADMIN: {
    label: 'Admin',
    icon: Shield,
    color: '#722ed1',
    bg: '#f9f0ff',
    border: '#d3adf7',
  },
  PROJECT_MANAGER: {
    label: 'Project Manager',
    icon: FolderKanban,
    color: '#1890ff',
    bg: '#e6f7ff',
    border: '#91d5ff',
  },
  USER: {
    label: 'User',
    icon: User,
    color: '#52c41a',
    bg: '#f6ffed',
    border: '#b7eb8f',
  },
}

const RoleBadge = ({ role }) => {
  const cfg = ROLE_CONFIG[role] || ROLE_CONFIG.USER
  const Icon = cfg.icon
  return (
    <span
      className="users-page__role-badge"
      style={{
        background: cfg.bg,
        color: cfg.color,
        border: `1px solid ${cfg.border}`,
      }}
    >
      <Icon size={11} strokeWidth={2.5} />
      {cfg.label}
    </span>
  )
}

const UsersPage = () => {
  const { user: currentUser } = useAuth()
  const { notify } = useNotification()

  const [data, setData] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)

  /* filters */
  const [search, setSearch] = useState('')
  const [filterRole, setFilterRole] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 25

  /* modals */
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)

  /* ── fetch ── */
  const fetchUsers = useCallback(async () => {
    setLoading(true)
    try {
      const params = { page, page_size: PAGE_SIZE }
      if (search.trim()) params.search = search.trim()
      if (filterRole && filterRole !== 'ALL') params.role = filterRole

      const res = await usersApi.list(params)
      setData(res.data.users || [])
      setTotal(res.data.total || 0)
      setTotalPages(res.data.total_pages || 1)
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [page, search, filterRole])

  useEffect(() => {
    fetchUsers()
  }, [fetchUsers])

  const handleSearch = (val) => { setSearch(val); setPage(1) }
  const handleRoleFilter = (val) => { setFilterRole(val); setPage(1) }

  /* ── can edit/delete ── */
  const canEdit = (row) => {
    if (currentUser?.role === 'SUPER_ADMIN') return row.role !== 'SUPER_ADMIN' || row.id === currentUser.id
    if (currentUser?.role === 'ADMIN') return row.role === 'USER'
    return false
  }

  const canDelete = (row) => {
    if (row.id === currentUser?.id) return false
    if (row.role === 'SUPER_ADMIN') return false
    if (currentUser?.role === 'SUPER_ADMIN') return true
    if (currentUser?.role === 'ADMIN') return row.role === 'USER'
    return false
  }

  /* ── columns ── */
  const columns = [
    {
      key: 'id',
      title: '#',
      width: 60,
      render: (val) => (
        <span className="users-table__id">#{val}</span>
      ),
    },
    {
      key: 'full_name',
      title: 'Full Name',
      render: (val, row) => (
        <div className="users-table__name-cell">
          <div className="users-table__avatar">
            {val
              ? val.split(' ').map((w) => w[0]).join('').toUpperCase().slice(0, 2)
              : row.username.slice(0, 2).toUpperCase()}
          </div>
          <div className="users-table__name-info">
            <span className="users-table__full-name">{val || '—'}</span>
            <span className="users-table__username">@{row.username}</span>
          </div>
        </div>
      ),
    },
    {
      key: 'email',
      title: 'Email',
      render: (val) => (
        <span className="users-table__email">{val}</span>
      ),
    },
    {
      key: 'role',
      title: 'Role',
      width: 160,
      render: (val) => <RoleBadge role={val} />,
    },
    {
      key: 'is_active',
      title: 'Status',
      width: 100,
      align: 'center',
      render: (val) => (
        <StatusBadge status={val ? 'active' : 'disabled'} />
      ),
    },
    {
      key: 'created_at',
      title: 'Created',
      render: (val) =>
        val ? (
          <span className="users-table__date">
            {dayjs(val).format('MMM D, YYYY')}
          </span>
        ) : (
          <span className="users-table__null">—</span>
        ),
    },
    {
      key: 'last_login_at',
      title: 'Last Login',
      render: (val) =>
        val ? (
          <span className="users-table__date">
            {dayjs(val).format('MMM D, HH:mm')}
          </span>
        ) : (
          <span className="users-table__null">Never</span>
        ),
    },
    {
      key: 'actions',
      title: '',
      width: 80,
      align: 'right',
      render: (_, row) => (
        <div className="users-table__actions">
          {canEdit(row) && (
            <button
              className="users-table__action-btn users-table__action-btn--edit"
              title="Edit user"
              onClick={() => setEditTarget(row)}
            >
              <Pencil size={15} />
            </button>
          )}
          {canDelete(row) && (
            <button
              className="users-table__action-btn users-table__action-btn--delete"
              title="Delete user"
              onClick={() => setDeleteTarget(row)}
            >
              <Trash2 size={15} />
            </button>
          )}
        </div>
      ),
    },
  ]

  /* ── role stats ── */
  const roleStats = Object.entries(ROLE_CONFIG).map(([key, cfg]) => ({
    role: key,
    count: data.filter((u) => u.role === key).length,
    ...cfg,
  }))

  return (
    <div className="users-page">
      {/* ── Header ── */}
      <div className="page-header">
        <div>
          <h2 className="page-title">User Management</h2>
          <p className="page-subtitle">
            {total} user{total !== 1 ? 's' : ''} registered
          </p>
        </div>
        <div className="users-page__header-actions">
          <Button
            variant="secondary"
            icon={RefreshCw}
            size="md"
            onClick={fetchUsers}
          >
            Refresh
          </Button>
          {(currentUser?.role === 'SUPER_ADMIN' ||
            currentUser?.role === 'ADMIN') && (
            <Button
              variant="primary"
              icon={Plus}
              size="md"
              onClick={() => setCreateOpen(true)}
            >
              Add User
            </Button>
          )}
        </div>
      </div>

      {/* ── Role summary cards ── */}
      <div className="users-page__role-cards">
        {roleStats.map((rs) => {
          const Icon = rs.icon
          return (
            <div
              key={rs.role}
              className="users-page__role-card"
              style={{
                borderTop: `3px solid ${rs.color}`,
              }}
            >
              <div
                className="users-page__role-card-icon"
                style={{ background: rs.bg, color: rs.color }}
              >
                <Icon size={18} strokeWidth={2} />
              </div>
              <div className="users-page__role-card-content">
                <span className="users-page__role-card-count">
                  {rs.count}
                </span>
                <span className="users-page__role-card-label">
                  {rs.label}
                </span>
              </div>
            </div>
          )
        })}
      </div>

      {/* ── Table card ── */}
      <Card padding={false}>
        {/* Filters */}
        <div className="users-page__filters">
          <SearchBar
            value={search}
            onChange={handleSearch}
            placeholder="Search by name, email or username..."
            width={300}
          />
          <div className="users-page__filter-row">
            <label className="users-page__filter-label">Role</label>
            <div className="users-page__role-btns">
              {[
                { val: '', label: 'All' },
                { val: 'SUPER_ADMIN', label: 'Super Admin' },
                { val: 'ADMIN', label: 'Admin' },
                { val: 'PROJECT_MANAGER', label: 'PM' },
                { val: 'USER', label: 'User' },
              ].map((opt) => (
                <button
                  key={opt.val}
                  className={`users-page__role-btn ${
                    filterRole === opt.val
                      ? 'users-page__role-btn--active'
                      : ''
                  }`}
                  onClick={() => handleRoleFilter(opt.val)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Table */}
        {loading ? (
          <Spinner centered text="Loading users..." />
        ) : (
          <>
            <Table
              columns={columns}
              data={data}
              rowKey="id"
              emptyText="No users found"
            />
            {total > 0 && (
              <Pagination
                page={page}
                totalPages={totalPages}
                total={total}
                pageSize={PAGE_SIZE}
                onChange={setPage}
              />
            )}
          </>
        )}
      </Card>

      {/* ── Modals ── */}
      <UserModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={() => { setCreateOpen(false); fetchUsers() }}
        mode="create"
        currentUserRole={currentUser?.role}
      />

      <UserModal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        onSuccess={() => { setEditTarget(null); fetchUsers() }}
        mode="edit"
        initial={editTarget}
        currentUserRole={currentUser?.role}
      />

      <DeleteUserModal
        open={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onSuccess={() => { setDeleteTarget(null); fetchUsers() }}
        user={deleteTarget}
      />
    </div>
  )
}

export default UsersPage