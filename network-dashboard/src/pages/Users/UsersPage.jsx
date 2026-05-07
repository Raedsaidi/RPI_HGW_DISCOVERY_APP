import React, { useState, useEffect, useCallback, useMemo } from 'react'
import {
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
import { usersApi, hgwsApi } from '@/api/endpoints'
import { useAuth } from '@/context/AuthContext'
import { useNotification } from '@/context/NotificationContext'
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

/**
 * Charge toutes les pages HGWs et construit:
 * - options: pour la sélection
 * - index: identifier -> hgw (identifier = serial_number sinon ip)
 */
async function fetchAllHgws() {
  const PAGE_SIZE = 100
  let page = 1
  let totalPages = 1
  const all = []

  while (page <= totalPages) {
    const res = await hgwsApi.list({ page, page_size: PAGE_SIZE })
    const chunk = res?.data?.data || []
    all.push(...chunk)
    totalPages = res?.data?.total_pages || 1
    page += 1
  }

  // Construire options + index
  const index = {}
  const options = []

  for (const h of all) {
    const identifier = h?.serial_number || h?.ip
    if (!identifier) continue

    // index par identifiant unique (serial)
    if (h?.serial_number) index[h.serial_number] = h
    // fallback index par ip (compat / anciens)
    if (h?.ip) index[h.ip] = h

    options.push({
      value: identifier,
      label: `${h.model_name || h.manufacturer || 'HGW'} — ${h.ip}${h.serial_number ? ` (${h.serial_number})` : ''}`,
      ip: h.ip,
      model_name: h.model_name,
      serial_number: h.serial_number,
    })
  }

  // tri stable
  options.sort((a, b) => a.label.localeCompare(b.label))

  return { options, index }
}

const UsersPage = () => {
  const { user: currentUser } = useAuth()
  const { notify } = useNotification()

  const [data, setData] = useState([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [loading, setLoading] = useState(true)

  /* HGWs data (loaded once here, shared with modals + table render) */
  const [hgwOptions, setHgwOptions] = useState([])
  const [hgwIndex, setHgwIndex] = useState({})
  const [hgwsLoading, setHgwsLoading] = useState(false)

  /* filters */
  const [search, setSearch] = useState('')
  const [filterRole, setFilterRole] = useState('')
  const [page, setPage] = useState(1)
  const PAGE_SIZE = 25

  /* modals */
  const [createOpen, setCreateOpen] = useState(false)
  const [editTarget, setEditTarget] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)

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
      notify?.('error', 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }, [page, search, filterRole, notify])

  const loadHgws = useCallback(async () => {
    setHgwsLoading(true)
    try {
      const { options, index } = await fetchAllHgws()
      setHgwOptions(options)
      setHgwIndex(index)
    } catch (e) {
      console.error(e)
      setHgwOptions([])
      setHgwIndex({})
      // pas bloquant
    } finally {
      setHgwsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchUsers()
  }, [fetchUsers])

  useEffect(() => {
    loadHgws()
  }, [loadHgws])

  const handleSearch = (val) => {
    setSearch(val)
    setPage(1)
  }
  const handleRoleFilter = (val) => {
    setFilterRole(val)
    setPage(1)
  }

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

  const columns = useMemo(() => ([
    {
      key: 'id',
      title: '#',
      width: 60,
      render: (val) => <span className="users-table__id">#{val}</span>,
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
      render: (val) => <span className="users-table__email">{val}</span>,
    },
    {
      key: 'role',
      title: 'Role',
      width: 160,
      render: (val) => <RoleBadge role={val} />,
    },

    // ✅ 0..n HGWs
    {
      key: 'project_hgws',
      title: 'Projects (HGW)',
      width: 340,
      render: (val, row) => {
        const list = Array.isArray(row.project_hgws) ? row.project_hgws : []
        if (list.length === 0) return <span className="users-table__null">—</span>

        const max = 2
        const shown = list.slice(0, max)
        const rest = list.length - shown.length

        return (
          <div className="users-table__project-list">
            {shown.map((identifier, idx) => {
              const h = hgwIndex[identifier]
              const name = h?.model_name || h?.manufacturer || h?.serial_number || 'HGW'
              const ip = h?.ip || identifier

              return (
                <div key={`${identifier}-${idx}`} className="users-table__project-item">
                  <div className="users-table__project-name">{name}</div>
                  <div className="users-table__project-ip">{ip}</div>
                </div>
              )
            })}

            {rest > 0 && <div className="users-table__project-more">+{rest} more</div>}
            {hgwsLoading && <div className="users-table__project-loading">(loading HGWs...)</div>}
          </div>
        )
      },
    },

    {
      key: 'is_active',
      title: 'Status',
      width: 100,
      align: 'center',
      render: (val) => <StatusBadge status={val ? 'active' : 'disabled'} />,
    },
    {
      key: 'created_at',
      title: 'Created',
      render: (val) =>
        val ? (
          <span className="users-table__date">{dayjs(val).format('MMM D, YYYY')}</span>
        ) : (
          <span className="users-table__null">—</span>
        ),
    },
    {
      key: 'last_login_at',
      title: 'Last Login',
      render: (val) =>
        val ? (
          <span className="users-table__date">{dayjs(val).format('MMM D, HH:mm')}</span>
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
  ]), [canDelete, canEdit, hgwIndex, hgwsLoading])

  const roleStats = Object.entries(ROLE_CONFIG).map(([key, cfg]) => ({
    role: key,
    count: data.filter((u) => u.role === key).length,
    ...cfg,
  }))

  return (
    <div className="users-page">
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
            onClick={() => {
              fetchUsers()
              loadHgws()
            }}
          >
            Refresh
          </Button>

          {(currentUser?.role === 'SUPER_ADMIN' || currentUser?.role === 'ADMIN') && (
            <Button variant="primary" icon={Plus} size="md" onClick={() => setCreateOpen(true)}>
              Add User
            </Button>
          )}
        </div>
      </div>

      <div className="users-page__role-cards">
        {roleStats.map((rs) => {
          const Icon = rs.icon
          return (
            <div
              key={rs.role}
              className="users-page__role-card"
              style={{ borderTop: `3px solid ${rs.color}` }}
            >
              <div
                className="users-page__role-card-icon"
                style={{ background: rs.bg, color: rs.color }}
              >
                <Icon size={18} strokeWidth={2} />
              </div>
              <div className="users-page__role-card-content">
                <span className="users-page__role-card-count">{rs.count}</span>
                <span className="users-page__role-card-label">{rs.label}</span>
              </div>
            </div>
          )
        })}
      </div>

      <Card padding={false}>
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
                  className={`users-page__role-btn ${filterRole === opt.val ? 'users-page__role-btn--active' : ''}`}
                  onClick={() => handleRoleFilter(opt.val)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {loading ? (
          <Spinner centered text="Loading users..." />
        ) : (
          <>
            <Table columns={columns} data={data} rowKey="id" emptyText="No users found" />
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

      <UserModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSuccess={() => { setCreateOpen(false); fetchUsers() }}
        mode="create"
        currentUserRole={currentUser?.role}
        hgwOptions={hgwOptions}
        hgwsLoading={hgwsLoading}
      />

      <UserModal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        onSuccess={() => { setEditTarget(null); fetchUsers() }}
        mode="edit"
        initial={editTarget}
        currentUserRole={currentUser?.role}
        hgwOptions={hgwOptions}
        hgwsLoading={hgwsLoading}
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