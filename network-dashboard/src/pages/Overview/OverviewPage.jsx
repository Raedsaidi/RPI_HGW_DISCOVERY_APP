import React, { useEffect, useState } from 'react'
import {
  Network,
  Cpu,
  Wifi,
  Radio,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Play,
  RefreshCw,
} from 'lucide-react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
} from 'recharts'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import StatCard from '@/components/common/StatCard'
import Card from '@/components/common/Card'
import { StatusBadge } from '@/components/common/Badge'
import Button from '@/components/common/Button'
import Spinner from '@/components/common/Spinner'
import { switchesApi, rpisApi, hgwsApi, discoveryApi } from '@/api/endpoints'
import './OverviewPage.css'

dayjs.extend(relativeTime)

/* ── helpers ── */
const safe = (val, fallback = 0) => (val == null ? fallback : val)

const OverviewPage = () => {
  const [stats, setStats] = useState(null)
  const [runs, setRuns] = useState([])
  const [chartData, setChartData] = useState([])
  const [deviceChart, setDeviceChart] = useState([])
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)

  /* ── fetch all ── */
  const fetchAll = async () => {
    setLoading(true)
    try {
      const [swRes, rpiRes, hgwRes, runsRes] = await Promise.allSettled([
        switchesApi.list({ page: 1, page_size: 1 }),
        rpisApi.list({ page: 1, page_size: 1 }),
        hgwsApi.list({ page: 1, page_size: 1 }),
        discoveryApi.listRuns({ page: 1, page_size: 10 }),
      ])

      const swTotal = swRes.status === 'fulfilled' ? swRes.value.data.total : 0
      const rpiTotal = rpiRes.status === 'fulfilled' ? rpiRes.value.data.total : 0
      const hgwTotal = hgwRes.status === 'fulfilled' ? hgwRes.value.data.total : 0
      const runsData = runsRes.status === 'fulfilled' ? runsRes.value.data : { data: [] }

      const latestRuns = runsData.data || []
      setRuns(latestRuns.slice(0, 6))

      /* aggregate stats from latest run */
      const latest = latestRuns[0] || {}

      setStats({
        switches: swTotal,
        rpis: rpiTotal,
        hgws: hgwTotal,
        runs: runsData.total || 0,
        switches_ok: safe(latest.switches_ok),
        switches_err: safe(latest.switches_err),
        rpis_ok: safe(latest.rpis_ok),
        rpis_err: safe(latest.rpis_err),
        hgws_ok: safe(latest.hgws_ok),
        hgws_err: safe(latest.hgws_err),
      })

      /* chart — last 10 runs reversed */
      const reversed = [...latestRuns].reverse()
      setChartData(
        reversed.map((r) => ({
          name: dayjs(r.started_at).format('MM/DD HH:mm'),
          ok: safe(r.rpis_ok) + safe(r.switches_ok) + safe(r.hgws_ok),
          err: safe(r.rpis_err) + safe(r.switches_err) + safe(r.hgws_err),
        }))
      )

      /* device breakdown for bar chart */
      setDeviceChart([
        {
          name: 'Switches',
          Online: safe(latest.switches_ok),
          Error: safe(latest.switches_err),
        },
        {
          name: 'RPis',
          Online: safe(latest.rpis_ok),
          Error: safe(latest.rpis_err),
        },
        {
          name: 'Gateways',
          Online: safe(latest.hgws_ok),
          Error: safe(latest.hgws_err),
        },
      ])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchAll()
  }, [])

  /* ── trigger discovery ── */
  const handleTrigger = async () => {
    setTriggering(true)
    try {
      await discoveryApi.trigger()
      setTimeout(fetchAll, 1500)
    } catch (e) {
      console.error(e)
    } finally {
      setTriggering(false)
    }
  }

  if (loading) return <Spinner centered size="lg" text="Loading dashboard..." />

  const totalOnline =
    safe(stats?.switches_ok) + safe(stats?.rpis_ok) + safe(stats?.hgws_ok)
  const totalError =
    safe(stats?.switches_err) + safe(stats?.rpis_err) + safe(stats?.hgws_err)
  const totalDevices =
    safe(stats?.switches) + safe(stats?.rpis) + safe(stats?.hgws)

  return (
    <div className="overview">
      {/* ── Page Header ── */}
      <div className="page-header">
        <div>
          <h2 className="page-title">Overview</h2>
          <p className="page-subtitle">
            Network infrastructure summary — last updated{' '}
            {dayjs().format('HH:mm')}
          </p>
        </div>
        <div className="overview__header-actions">
          <Button
            variant="secondary"
            icon={RefreshCw}
            size="md"
            onClick={fetchAll}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            icon={Play}
            size="md"
            loading={triggering}
            onClick={handleTrigger}
          >
            Run Discovery
          </Button>
        </div>
      </div>

      {/* ── Stat Cards ── */}
      <div className="overview__stats">
        <StatCard
          title="Total Switches"
          value={stats?.switches}
          icon={Network}
          color="#1890ff"
          bg="#e6f7ff"
        />
        <StatCard
          title="Raspberry Pis"
          value={stats?.rpis}
          icon={Cpu}
          color="#722ed1"
          bg="#f9f0ff"
        />
        <StatCard
          title="Gateways (HGW)"
          value={stats?.hgws}
          icon={Wifi}
          color="#13c2c2"
          bg="#e6fffb"
        />
        <StatCard
          title="Discovery Runs"
          value={stats?.runs}
          icon={Radio}
          color="#fa8c16"
          bg="#fff7e6"
        />
      </div>

      {/* ── Status Summary ── */}
      <div className="overview__status-row">
        <div className="overview__status-card overview__status-card--online">
          <CheckCircle size={20} />
          <div>
            <span className="overview__status-val">{totalOnline}</span>
            <span className="overview__status-label">Devices Online</span>
          </div>
        </div>
        <div className="overview__status-card overview__status-card--error">
          <XCircle size={20} />
          <div>
            <span className="overview__status-val">{totalError}</span>
            <span className="overview__status-label">Devices with Errors</span>
          </div>
        </div>
        <div className="overview__status-card overview__status-card--total">
          <AlertTriangle size={20} />
          <div>
            <span className="overview__status-val">{totalDevices}</span>
            <span className="overview__status-label">Total Managed</span>
          </div>
        </div>
      </div>

      {/* ── Charts Row ── */}
      <div className="overview__charts">
        {/* Area chart */}
        <Card
          title="Discovery Results"
          subtitle="Success vs errors across last 10 runs"
          className="overview__chart-card"
        >
          {chartData.length === 0 ? (
            <div className="overview__chart-empty">No run data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart
                data={chartData}
                margin={{ top: 8, right: 16, left: -16, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="gradOk" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#52c41a" stopOpacity={0.18} />
                    <stop offset="95%" stopColor="#52c41a" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradErr" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f5222d" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#f5222d" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#f0f0f0"
                  vertical={false}
                />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11, fill: '#8c8c8c' }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#8c8c8c' }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 8,
                    border: '1px solid #f0f0f0',
                    fontSize: 12,
                    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                />
                <Area
                  type="monotone"
                  dataKey="ok"
                  name="Online"
                  stroke="#52c41a"
                  strokeWidth={2}
                  fill="url(#gradOk)"
                  dot={false}
                />
                <Area
                  type="monotone"
                  dataKey="err"
                  name="Errors"
                  stroke="#f5222d"
                  strokeWidth={2}
                  fill="url(#gradErr)"
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </Card>

        {/* Bar chart */}
        <Card
          title="Device Breakdown"
          subtitle="Latest run results by device type"
          className="overview__chart-card"
        >
          {deviceChart.every((d) => d.Online === 0 && d.Error === 0) ? (
            <div className="overview__chart-empty">No run data yet</div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={deviceChart}
                margin={{ top: 8, right: 16, left: -16, bottom: 0 }}
                barSize={28}
              >
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="#f0f0f0"
                  vertical={false}
                />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 12, fill: '#8c8c8c' }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: '#8c8c8c' }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: 8,
                    border: '1px solid #f0f0f0',
                    fontSize: 12,
                    boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
                  }}
                />
                <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                <Bar
                  dataKey="Online"
                  fill="#52c41a"
                  radius={[4, 4, 0, 0]}
                />
                <Bar
                  dataKey="Error"
                  fill="#f5222d"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* ── Recent Runs ── */}
      <Card
        title="Recent Discovery Runs"
        subtitle="Last 6 discovery executions"
        extra={
          <Button
            variant="text"
            size="sm"
            onClick={() => (window.location.href = '/discovery')}
          >
            View all →
          </Button>
        }
      >
        {runs.length === 0 ? (
          <div className="overview__empty">
            <Radio size={32} color="#d9d9d9" />
            <p>No discovery runs yet. Start your first scan.</p>
            <Button
              variant="primary"
              icon={Play}
              onClick={handleTrigger}
              loading={triggering}
            >
              Run Discovery
            </Button>
          </div>
        ) : (
          <div className="overview__runs">
            {runs.map((run) => (
              <div key={run.id} className="overview__run-item">
                <div className="overview__run-left">
                  <div className="overview__run-id">#{run.id}</div>
                  <div className="overview__run-meta">
                    <span className="overview__run-time">
                      {dayjs(run.started_at).format('MMM D, YYYY HH:mm')}
                    </span>
                    <span className="overview__run-by">
                      by {run.triggered_by || 'system'}
                    </span>
                  </div>
                </div>

                <div className="overview__run-stats">
                  <span className="overview__run-stat overview__run-stat--sw">
                    <Network size={12} />
                    {safe(run.switches_ok)}/{safe(run.switches_ok) + safe(run.switches_err)}
                  </span>
                  <span className="overview__run-stat overview__run-stat--rpi">
                    <Cpu size={12} />
                    {safe(run.rpis_ok)}/{safe(run.rpis_ok) + safe(run.rpis_err)}
                  </span>
                  <span className="overview__run-stat overview__run-stat--hgw">
                    <Wifi size={12} />
                    {safe(run.hgws_ok)}/{safe(run.hgws_ok) + safe(run.hgws_err)}
                  </span>
                </div>

                <StatusBadge status={run.status} />
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

export default OverviewPage