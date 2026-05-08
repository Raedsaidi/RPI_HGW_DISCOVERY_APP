// TopologyPage.jsx
import React, { useEffect, useRef, useState, useCallback } from 'react'
import * as d3 from 'd3'
import {
  RefreshCw,
  GitBranch,
  Network,
  Cpu,
  Wifi,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Minimize2,
  AlertCircle,
  LayoutGrid,
  Filter,
} from 'lucide-react'
import Button from '@/components/common/Button'
import Spinner from '@/components/common/Spinner'
import { topologyApi, discoveryApi } from '@/api/endpoints'
import { useNotification } from '@/context/NotificationContext'
import { useAuth } from '@/context/AuthContext'
import { getFriendlyMessage } from '@/utils/messageHelper'
import dayjs from 'dayjs'
import './TopologyPage.css'

/* ─────────────────────────────────────────
   Constants
───────────────────────────────────────── */
const NODE_COLORS = {
  switch: { fill: '#1890ff', light: '#e6f7ff', border: '#91d5ff' },
  rpi: { fill: '#722ed1', light: '#f9f0ff', border: '#d3adf7' },
  hgw: { fill: '#13c2c2', light: '#e6fffb', border: '#87e8de' },
  unknown: { fill: '#8c8c8c', light: '#fafafa', border: '#d9d9d9' },
}

const FAILED_COLOR = '#f5222d'
const NODE_RADIUS = { switch: 28, rpi: 22, hgw: 18, unknown: 16 }
const ICONS = { switch: '⇄', rpi: '◉', hgw: '⊙' }

// Roles that can see the full topology / switch view
const FULL_ACCESS_ROLES = ['SUPER_ADMIN', 'ADMIN']

// ✅ NEW: reserved identifier (backend)
const ALL_HGW_IDENTIFIER = 'ALL'

// All 3 view modes
const VIEW_ALL = 'all'
const VIEW_SWITCH = 'switch'
const VIEW_HGW = 'hgw'

/* ─────────────────────────────────────────
   Helpers
───────────────────────────────────────── */
const shortKey = (k) => {
  if (!k) return ''
  return k.length > 14 ? `${k.slice(0, 6)}…${k.slice(-4)}` : k
}

/**
 * Key used to deduplicate HGW nodes in the graph.
 * Priority:
 *  - serial_number (best)
 *  - instance_key  (our new stable key for HGW instances)
 *  - fallback legacy: ip|via:rpi
 */
const getHgwGraphKey = (hgw, rpi) => {
  if (!hgw) return null
  if (hgw.serial_number) return `serial:${hgw.serial_number}`
  if (hgw.instance_key) return `inst:${hgw.instance_key}`
  if (hgw.ip) return `ip:${hgw.ip}|via:${rpi?.ip_mgmt || 'unknown'}`
  return null
}

/**
 * Dropdown options for "By Gateway" selector.
 * The backend still filters by hgw_identifier (serial or IP),
 * so we group multiple instances that share the same identifier (e.g., same IP).
 */
const normalizeHgwsForSelector = (list) => {
  const map = new Map()
  ;(list || []).forEach((h) => {
    const id = h?.hgw_identifier
    if (!id) return
    const g = map.get(id) || { value: id, instances: [] }
    g.instances.push(h)
    map.set(id, g)
  })

  return Array.from(map.values()).map((g) => {
    const first = g.instances[0] || {}
    const model = first.model_name || first.ip || g.value
    const serial = first.serial_number
    const count = g.instances.length
    const instKeys = [
      ...new Set(g.instances.map((x) => x.instance_key).filter(Boolean)),
    ]

    const instLabel = instKeys.length
      ? ` [${instKeys
          .slice(0, 2)
          .map(shortKey)
          .join(', ')}${instKeys.length > 2 ? '…' : ''}]`
      : ''

    const label = serial
      ? `${model} (${serial})`
      : `${model}${count > 1 ? ` (${count} instances)` : ''}${instLabel}`

    return { value: g.value, label, instances: g.instances }
  })
}

/* ─────────────────────────────────────────
   parseTopology
───────────────────────────────────────── */
const parseTopology = (data) => {
  if (!data) return { nodes: [], links: [] }

  const nodes = []
  const links = []
  const nodeMap = new Map()

  const switches = Array.isArray(data.switches) ? data.switches : []

  switches.forEach((sw) => {
    const id = `sw-${sw.ip}`
    nodes.push({
      id,
      ip: sw.ip,
      label: sw.name || sw.ip,
      type: 'switch',
      data: sw,
    })
    nodeMap.set(sw.ip, id)
  })

  // Collect all RPis (assigned + unassigned)
  const rpiByIp = new Map()
  switches.forEach((sw) => {
    ;(sw.rpis || []).forEach((rpi) => {
      if (!rpi?.ip_mgmt) return
      rpiByIp.set(rpi.ip_mgmt, { ...rpi, switch_ip: sw.ip })
    })
  })

  ;(data.unassigned_rpis || []).forEach((rpi) => {
    if (!rpi?.ip_mgmt) return
    if (!rpiByIp.has(rpi.ip_mgmt)) rpiByIp.set(rpi.ip_mgmt, rpi)
  })

  // HGW nodes by stable key
  const hgwNodeIdByKey = new Map()
  const hgwNodeById = new Map()

  Array.from(rpiByIp.values()).forEach((rpi) => {
    const id = `rpi-${rpi.ip_mgmt}`
    const sshSuccess = rpi.ssh_success ?? rpi.last_ssh_success ?? true

    nodes.push({
      id,
      ip: rpi.ip_mgmt,
      label: rpi.label || rpi.ip_mgmt,
      type: 'rpi',
      data: { ...rpi, ssh_success: sshSuccess },
    })
    nodeMap.set(rpi.ip_mgmt, id)

    if (rpi.switch_ip && nodeMap.has(rpi.switch_ip)) {
      links.push({
        source: nodeMap.get(rpi.switch_ip),
        target: id,
        type: 'switch-rpi',
      })
    }

    // HGW (shared for N RPis if same instance_key)
    if (rpi.hgw?.ip) {
      const hgw = rpi.hgw
      const hgwKey = getHgwGraphKey(hgw, rpi)
      if (!hgwKey) return

      let hgwNodeId = hgwNodeIdByKey.get(hgwKey)

      if (!hgwNodeId) {
        const base = hgw.model_name || hgw.ip
        const label = hgw.serial_number
          ? `${base} (${hgw.serial_number})`
          : `${base}${hgw.instance_key ? ` [${shortKey(hgw.instance_key)}]` : ''}`

        hgwNodeId = `hgw-${hgwKey}`
        hgwNodeIdByKey.set(hgwKey, hgwNodeId)

        const nodeObj = {
          id: hgwNodeId,
          ip: hgw.ip,
          label,
          type: 'hgw',
          data: {
            ...hgw,
            // Since node is shared, keep list of RPis pointing to it
            via_rpi_ips: [rpi.ip_mgmt],
          },
        }
        nodes.push(nodeObj)
        hgwNodeById.set(hgwNodeId, nodeObj)
      } else {
        const existing = hgwNodeById.get(hgwNodeId)
        if (existing) {
          const arr = existing.data?.via_rpi_ips || []
          if (!arr.includes(rpi.ip_mgmt)) arr.push(rpi.ip_mgmt)
          existing.data = { ...(existing.data || {}), via_rpi_ips: arr }
        }
      }

      links.push({ source: id, target: hgwNodeId, type: 'rpi-hgw' })
    }
  })

  return { nodes, links }
}

const isFailedNode = (node) => {
  if (!node) return false
  const d = node.data || {}
  if (node.type === 'rpi') {
    return !!(
      d.ssh_success === false ||
      d.last_ssh_success === false ||
      d.ssh_error ||
      d.last_ssh_error
    )
  }
  if (node.type === 'hgw') return !!(d.ssh_success === false || d.ssh_error)
  if (node.type === 'switch') return !!d.ssh_error
  return false
}

/* ─────────────────────────────────────────
   Component
───────────────────────────────────────── */
const TopologyPage = () => {
  const svgRef = useRef(null)
  const containerRef = useRef(null)
  const zoomRef = useRef(null)
  const { notify } = useNotification()
  const { user } = useAuth()

  const graphRef = useRef({
    inited: false,
    svg: null,
    g: null,
    linkGroup: null,
    nodeGroup: null,
    simulation: null,
  })

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [topology, setTopology] = useState(null)
  const [runId, setRunId] = useState(null)
  const [runs, setRuns] = useState([])
  const [selectedNode, setSelectedNode] = useState(null)
  const [stats, setStats] = useState({ switches: 0, rpis: 0, hgws: 0 })
  const [expanded, setExpanded] = useState(false)

  // ── View mode state ──

  const hasAllAssigned = (user?.project_hgws || []).includes(ALL_HGW_IDENTIFIER)
  const isFullAccess = FULL_ACCESS_ROLES.includes(user?.role) || hasAllAssigned

  const [viewMode, setViewMode] = useState(isFullAccess ? VIEW_ALL : VIEW_HGW)
  const [selectedSwitchIp, setSelectedSwitchIp] = useState('')
  const [selectedHgwId, setSelectedHgwId] = useState('')

  const [availableSwitches, setAvailableSwitches] = useState([])
  // NEW: we store normalized options: [{value, label, instances}]
  const [availableHgws, setAvailableHgws] = useState([])
  const [hgwsLoading, setHgwsLoading] = useState(false)

  /* ── derive available switches from UNFILTERED topology ── */
  useEffect(() => {
    if (!topology) return
    if (topology.filter) return

    const list = (topology.switches || []).map((sw) => ({
      ip: sw.ip,
      name: sw.name || sw.ip,
    }))
    setAvailableSwitches(list)

    if (viewMode === VIEW_SWITCH && !selectedSwitchIp && list.length > 0) {
      setSelectedSwitchIp(list[0].ip)
    }
  }, [topology, viewMode, selectedSwitchIp])

  useEffect(() => {
    setViewMode(isFullAccess ? VIEW_ALL : VIEW_HGW)
  }, [isFullAccess])

  /* ── fetch available HGWs for this run ── */
  const fetchMyHgws = useCallback(
    async (rid) => {
      if (!rid) return
      setHgwsLoading(true)
      try {
        const res = await topologyApi.getMyHgws(rid)
        const list = res.data || []
        const options = normalizeHgwsForSelector(list)
        setAvailableHgws(options)

        // auto-select first HGW for restricted users
        if (!isFullAccess && options.length > 0 && !selectedHgwId) {
          setSelectedHgwId(options[0].value)
        }
      } catch {
        setAvailableHgws([])
      } finally {
        setHgwsLoading(false)
      }
    },
    [isFullAccess, selectedHgwId]
  )

  /* ── fetch runs list ── */
  const fetchRuns = useCallback(async () => {
    try {
      const res = await discoveryApi.listRuns({ page: 1, page_size: 20 })
      const list = res.data.data || []
      setRuns(list)
      return list
    } catch {
      return []
    }
  }, [])

  /* ── core fetch topology based on current view mode ── */
  const fetchTopology = useCallback(
    async (rid, { silent = false } = {}) => {
      if (!silent) {
        setLoading(true)
        setError('')
        setSelectedNode(null)
      }

      try {
        let res
        if (!rid) {
          res = await topologyApi.getLatest()
        } else if (viewMode === VIEW_SWITCH && selectedSwitchIp && isFullAccess) {
          res = await topologyApi.getForSwitch(rid, selectedSwitchIp)
        } else if (viewMode === VIEW_HGW && selectedHgwId) {
          res = await topologyApi.getForHgw(rid, selectedHgwId)
        } else {
          res = await topologyApi.getForRun(rid)
        }

        const data = res.data
        setTopology(data)

        let totalRpis = 0
        const hgwSet = new Set()
        ;(data.switches || []).forEach((sw) => {
          totalRpis += (sw.rpis || []).length
          ;(sw.rpis || []).forEach((rpi) => {
            if (rpi?.hgw?.ip) {
              const key = getHgwGraphKey(rpi.hgw, rpi)
              if (key) hgwSet.add(key)
            }
          })
        })
        totalRpis += (data.unassigned_rpis || []).length

        setStats({
          switches: (data.switches || []).length,
          rpis: totalRpis,
          hgws: hgwSet.size,
        })

        if (!silent) notify('success', 'Topology loaded successfully')
      } catch (e) {
        const msg = getFriendlyMessage(
          'error',
          e.response?.data?.detail || 'Failed to load topology'
        )
        setError(msg)
        notify('error', msg)
        setTopology(null)
      } finally {
        if (!silent) setLoading(false)
      }
    },
    [notify, viewMode, selectedSwitchIp, selectedHgwId, isFullAccess]
  )

  /* ── initial load ── */
  useEffect(() => {
    fetchRuns().then((list) => {
      if (list.length > 0) setRunId(list[0].id)
    })
  }, [fetchRuns])

  /* ── fetch HGWs when run changes ── */
  useEffect(() => {
    if (runId) fetchMyHgws(runId)
  }, [runId, fetchMyHgws])

  /* ── Reset D3 graph when run changes ── */
  useEffect(() => {
    if (!svgRef.current) return
    if (graphRef.current.simulation) graphRef.current.simulation.stop()
    graphRef.current = {
      inited: false,
      svg: null,
      g: null,
      linkGroup: null,
      nodeGroup: null,
      simulation: null,
    }
    d3.select(svgRef.current).selectAll('*').remove()
    zoomRef.current = null
  }, [runId])

  /* ── Re-fetch when view mode / filter changes ── */
  useEffect(() => {
    if (!runId) return
    if (graphRef.current.simulation) graphRef.current.simulation.stop()
    graphRef.current = {
      inited: false,
      svg: null,
      g: null,
      linkGroup: null,
      nodeGroup: null,
      simulation: null,
    }
    if (svgRef.current) d3.select(svgRef.current).selectAll('*').remove()
    zoomRef.current = null
    fetchTopology(runId)
  }, [viewMode, selectedSwitchIp, selectedHgwId]) // eslint-disable-line

  useEffect(() => {
    fetchTopology(runId)
  }, [runId, fetchTopology])

  /* ── live polling while run is in progress ── */
  useEffect(() => {
    if (!topology?.run_id || topology.run_status !== 'running') return
    const t = setInterval(() => fetchTopology(topology.run_id, { silent: true }), 1500)
    return () => clearInterval(t)
  }, [topology?.run_id, topology?.run_status, fetchTopology])

  /* ─────────────────────────────────────────
     D3 render (persistent graph + data join)
  ────────────────────────────────────────── */
  useEffect(() => {
    if (loading || !topology || !svgRef.current) return

    const { nodes: parsedNodes, links: parsedLinks } = parseTopology(topology)
    if (parsedNodes.length === 0) return

    const container = containerRef.current
    const W = container?.clientWidth || 900
    const H = container?.clientHeight || 600

    if (!graphRef.current.inited) {
      const svg = d3.select(svgRef.current).attr('width', W).attr('height', H)
      svg.selectAll('*').remove()

      const defs = svg.append('defs')
      const glow = defs.append('filter').attr('id', 'topo-glow')
      glow.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'coloredBlur')
      const merge = glow.append('feMerge')
      merge.append('feMergeNode').attr('in', 'coloredBlur')
      merge.append('feMergeNode').attr('in', 'SourceGraphic')

      ;['switch-rpi', 'rpi-hgw'].forEach((type) => {
        const color = type === 'switch-rpi' ? '#1890ff' : '#722ed1'
        defs
          .append('marker')
          .attr('id', `arrow-${type}`)
          .attr('viewBox', '0 -5 10 10')
          .attr('refX', 28)
          .attr('refY', 0)
          .attr('markerWidth', 6)
          .attr('markerHeight', 6)
          .attr('orient', 'auto')
          .append('path')
          .attr('d', 'M0,-5L10,0L0,5')
          .attr('fill', color)
          .attr('opacity', 0.6)
      })

      const g = svg.append('g')
      const zoom = d3
        .zoom()
        .scaleExtent([0.15, 3])
        .on('zoom', (event) => g.attr('transform', event.transform))
      svg.call(zoom)
      zoomRef.current = { zoom, svg }

      const linkGroup = g.append('g').attr('class', 'topo-links')
      const nodeGroup = g.append('g').attr('class', 'topo-nodes')

      const simulation = d3
        .forceSimulation([])
        .force(
          'link',
          d3
            .forceLink([])
            .id((d) => d.id)
            .distance((d) => (d.type === 'switch-rpi' ? 150 : 110))
            .strength(0.85)
        )
        .force('charge', d3.forceManyBody().strength(-520))
        .force('center', d3.forceCenter(W / 2, H / 2))
        .force('x', d3.forceX(W / 2).strength(0.04))
        .force('y', d3.forceY(H / 2).strength(0.04))
        .force(
          'collision',
          d3.forceCollide().radius((d) => NODE_RADIUS[d.type] + 22)
        )

      svg.on('click', () => setSelectedNode(null))

      graphRef.current = {
        inited: true,
        svg,
        g,
        linkGroup,
        nodeGroup,
        simulation,
      }
    }

    const { svg, linkGroup, nodeGroup, simulation } = graphRef.current
    svg.attr('width', W).attr('height', H)
    simulation.force('center', d3.forceCenter(W / 2, H / 2))
    simulation.force('x', d3.forceX(W / 2).strength(0.04))
    simulation.force('y', d3.forceY(H / 2).strength(0.04))

    const prevNodes = new Map((simulation.nodes() || []).map((n) => [n.id, n]))
    const nodes = parsedNodes.map((n) => {
      const prev = prevNodes.get(n.id)
      if (!prev) return n
      const { x, y, vx, vy, fx, fy } = prev
      Object.assign(prev, n)
      prev.x = x
      prev.y = y
      prev.vx = vx
      prev.vy = vy
      prev.fx = fx
      prev.fy = fy
      return prev
    })

    const linkKey = (d) => {
      const s = typeof d.source === 'object' ? d.source.id : d.source
      const t = typeof d.target === 'object' ? d.target.id : d.target
      return `${d.type}:${s}->${t}`
    }

    let linkSel = linkGroup.selectAll('line.topo-link').data(parsedLinks, linkKey)
    linkSel.exit().transition().duration(150).attr('stroke-opacity', 0).remove()
    const linkEnter = linkSel
      .enter()
      .append('line')
      .attr('class', 'topo-link')
      .attr('stroke', (d) => (d.type === 'switch-rpi' ? '#1890ff' : '#722ed1'))
      .attr('stroke-width', (d) => (d.type === 'switch-rpi' ? 2 : 1.5))
      .attr('stroke-dasharray', (d) => (d.type === 'rpi-hgw' ? '4,3' : null))
      .attr('marker-end', (d) => `url(#arrow-${d.type})`)
      .attr('stroke-opacity', 0)
    linkEnter.transition().duration(400).attr('stroke-opacity', 0.5)
    linkSel = linkEnter.merge(linkSel).attr('stroke-opacity', 0.5)

    let nodeSel = nodeGroup.selectAll('g.topo-node').data(nodes, (d) => d.id)
    nodeSel.exit().transition().duration(150).attr('opacity', 0).remove()

    const nodeEnter = nodeSel
      .enter()
      .append('g')
      .attr('class', 'topo-node')
      .attr('opacity', 0)
      .style('cursor', 'pointer')
      .call(
        d3
          .drag()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.25).restart()
            d.fx = d.x
            d.fy = d.y
          })
          .on('drag', (event, d) => {
            d.fx = event.x
            d.fy = event.y
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0)
            d.fx = null
            d.fy = null
          })
      )
      .on('click', (event, d) => {
        event.stopPropagation()
        setSelectedNode(d)
      })

    nodeEnter
      .append('circle')
      .attr('class', 'topo-node__pulse')
      .attr('r', (d) => NODE_RADIUS[d.type] + 6)
      .attr('fill', 'none')
      .attr('stroke', (d) => (isFailedNode(d) ? FAILED_COLOR : NODE_COLORS[d.type].fill))
      .attr('stroke-width', 1.5)
      .attr('opacity', 0.18)

    nodeEnter
      .append('circle')
      .attr('class', 'topo-node__circle')
      .attr('r', (d) => NODE_RADIUS[d.type])
      .attr('fill', (d) => (isFailedNode(d) ? FAILED_COLOR : NODE_COLORS[d.type].fill))
      .attr('stroke', '#fff')
      .attr('stroke-width', 3)
      .attr('filter', 'url(#topo-glow)')
      .on('mouseover', function (event, d) {
        d3.select(this).transition().duration(160).attr('r', NODE_RADIUS[d.type] + 5).attr('stroke-width', 4)
      })
      .on('mouseout', function (event, d) {
        d3.select(this).transition().duration(160).attr('r', NODE_RADIUS[d.type]).attr('stroke-width', 3)
      })

    nodeEnter
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('dominant-baseline', 'central')
      .attr('font-size', (d) => (d.type === 'switch' ? '16px' : '13px'))
      .attr('fill', '#fff')
      .attr('pointer-events', 'none')
      .attr('font-weight', '600')
      .text((d) => ICONS[d.type] || '●')

    nodeEnter.append('rect').attr('rx', 4).attr('ry', 4).attr('fill', '#fff').attr('stroke', (d) => NODE_COLORS[d.type].border).attr('stroke-width', 1).attr('opacity', 0.92)

    nodeEnter
      .append('text')
      .attr('class', 'topo-node__label')
      .attr('text-anchor', 'middle')
      .attr('font-size', '11px')
      .attr('font-weight', '600')
      .attr('fill', '#262626')
      .attr('pointer-events', 'none')
      .attr('dy', (d) => NODE_RADIUS[d.type] + 14)
      .text((d) => {
        const txt = d.label || ''
        return txt.length > 18 ? txt.slice(0, 18) + '…' : txt
      })

    nodeEnter
      .append('text')
      .attr('text-anchor', 'middle')
      .attr('font-size', '10px')
      .attr('fill', '#8c8c8c')
      .attr('pointer-events', 'none')
      .attr('font-family', 'monospace')
      .attr('dy', (d) => NODE_RADIUS[d.type] + 26)
      .text((d) => (d.label !== d.ip ? d.ip : ''))

    nodeEnter.transition().duration(450).attr('opacity', 1)

    nodeSel = nodeEnter.merge(nodeSel)
    nodeSel.select('circle.topo-node__pulse').attr('stroke', (d) => (isFailedNode(d) ? FAILED_COLOR : NODE_COLORS[d.type].fill))
    nodeSel.select('circle.topo-node__circle').attr('fill', (d) => (isFailedNode(d) ? FAILED_COLOR : NODE_COLORS[d.type].fill))

    nodeSel.each(function () {
      const textEl = d3.select(this).select('.topo-node__label').node()
      if (!textEl) return
      const bbox = textEl.getBBox()
      d3.select(this)
        .select('rect')
        .attr('x', bbox.x - 5)
        .attr('y', bbox.y - 2)
        .attr('width', bbox.width + 10)
        .attr('height', bbox.height + 4)
    })

    simulation.nodes(nodes)
    simulation.force('link').links(parsedLinks)
    simulation.on('tick', () => {
      linkSel
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y)
      nodeSel.attr('transform', (d) => `translate(${d.x},${d.y})`)
    })
    simulation.alpha(0.6).restart()
  }, [topology, loading, expanded])

  useEffect(
    () => () => {
      if (graphRef.current.simulation) graphRef.current.simulation.stop()
    },
    []
  )

  /* ── zoom controls ── */
  const handleZoomIn = () => {
    if (!zoomRef.current) return
    zoomRef.current.svg.transition().duration(300).call(zoomRef.current.zoom.scaleBy, 1.4)
  }
  const handleZoomOut = () => {
    if (!zoomRef.current) return
    zoomRef.current.svg.transition().duration(300).call(zoomRef.current.zoom.scaleBy, 0.7)
  }
  const handleFit = () => {
    if (!zoomRef.current) return
    zoomRef.current.svg.transition().duration(500).call(zoomRef.current.zoom.transform, d3.zoomIdentity)
  }

  /* ── handle view mode change ── */
  const handleViewMode = (mode) => {
    if (!isFullAccess && mode !== VIEW_HGW) return
    setViewMode(mode)
    setSelectedNode(null)
    if (mode === VIEW_SWITCH && availableSwitches.length > 0 && !selectedSwitchIp) {
      setSelectedSwitchIp(availableSwitches[0].ip)
    }
    if (mode === VIEW_HGW && availableHgws.length > 0 && !selectedHgwId) {
      setSelectedHgwId(availableHgws[0].value)
    }
  }

  /* ── empty state message ── */
  const emptyMessage = () => {
    if (viewMode === VIEW_SWITCH) {
      return selectedSwitchIp
        ? `No devices found on switch ${selectedSwitchIp}`
        : 'Select a switch to view its topology'
    }
    if (viewMode === VIEW_HGW) {
      return selectedHgwId ? 'No devices found for this gateway' : 'Select a gateway to view its topology'
    }
    return 'No topology data available'
  }

  const { nodes: parsedNodes } = topology ? parseTopology(topology) : { nodes: [] }
  const isEmpty = !loading && !error && parsedNodes.length === 0

  return (
    <div className="topology-page">
      {expanded && (
        <div className="topology-page__backdrop" onClick={() => setExpanded(false)} />
      )}

      {/* ── Header ── */}
      <div className="page-header">
        <div>
          <h2 className="page-title">Network Topology</h2>
          <p className="page-subtitle">Interactive network diagram — drag nodes, scroll to zoom</p>
        </div>

        <div className="topology-page__header-actions">
          <select
            className="topology-page__run-select"
            value={runId || ''}
            onChange={(e) => setRunId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Latest run</option>
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                Run #{r.id} — {dayjs(r.started_at).format('MMM D HH:mm')}
              </option>
            ))}
          </select>

          <Button variant="secondary" icon={RefreshCw} size="md" onClick={() => fetchTopology(runId)}>
            Refresh
          </Button>
        </div>
      </div>

      {/* ── Stats strip ── */}
      <div className="topology-page__stats">
        <div className="topology-page__stat topology-page__stat--switch">
          <Network size={15} />
          <span className="topology-page__stat-val">{stats.switches}</span>
          <span className="topology-page__stat-label">Switches</span>
        </div>
        <div className="topology-page__stat-sep" />
        <div className="topology-page__stat topology-page__stat--rpi">
          <Cpu size={15} />
          <span className="topology-page__stat-val">{stats.rpis}</span>
          <span className="topology-page__stat-label">RPis</span>
        </div>
        <div className="topology-page__stat-sep" />
        <div className="topology-page__stat topology-page__stat--hgw">
          <Wifi size={15} />
          <span className="topology-page__stat-val">{stats.hgws}</span>
          <span className="topology-page__stat-label">Gateways</span>
        </div>
        <div className="topology-page__stat-sep" />
        <div className="topology-page__stat">
          <GitBranch size={15} />
          <span className="topology-page__stat-val">{stats.switches + stats.rpis + stats.hgws}</span>
          <span className="topology-page__stat-label">Total Nodes</span>
        </div>
      </div>

      {/* ── View mode bar ── */}
      <div className="topology-page__viewbar">
        {isFullAccess && (
          <div className="topology-page__view-toggle">
            <button
              className={`topology-page__view-btn ${viewMode === VIEW_ALL ? 'topology-page__view-btn--active' : ''}`}
              onClick={() => handleViewMode(VIEW_ALL)}
              type="button"
            >
              <LayoutGrid size={14} />
              All
            </button>
            <button
              className={`topology-page__view-btn ${viewMode === VIEW_SWITCH ? 'topology-page__view-btn--active' : ''}`}
              onClick={() => handleViewMode(VIEW_SWITCH)}
              type="button"
            >
              <Network size={14} />
              By Switch
            </button>
            <button
              className={`topology-page__view-btn ${viewMode === VIEW_HGW ? 'topology-page__view-btn--active' : ''}`}
              onClick={() => handleViewMode(VIEW_HGW)}
              type="button"
            >
              <Wifi size={14} />
              By Gateway
            </button>
          </div>
        )}

        {/* Switch selector */}
        {viewMode === VIEW_SWITCH && isFullAccess && (
          <div className="topology-page__filter-group">
            <Filter size={13} className="topology-page__filter-icon" />
            <select
              className="topology-page__filter-select"
              value={selectedSwitchIp}
              onChange={(e) => setSelectedSwitchIp(e.target.value)}
            >
              <option value="">— Select a switch —</option>
              {availableSwitches.map((sw) => (
                <option key={sw.ip} value={sw.ip}>
                  {sw.name} ({sw.ip})
                </option>
              ))}
            </select>
          </div>
        )}

        {/* HGW selector */}
        {viewMode === VIEW_HGW && (
          <div className="topology-page__filter-group">
            <Filter size={13} className="topology-page__filter-icon" />
            {hgwsLoading ? (
              <span className="topology-page__filter-loading">Loading gateways…</span>
            ) : (
              <select
                className="topology-page__filter-select"
                value={selectedHgwId}
                onChange={(e) => setSelectedHgwId(e.target.value)}
              >
                {!isFullAccess && availableHgws.length === 0 && (
                  <option value="">No gateways assigned</option>
                )}
                {isFullAccess && <option value="">— Select a gateway —</option>}
                {availableHgws.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        {/* Badge showing active filter */}
        {topology?.filter && (
          <div className="topology-page__filter-badge">
            {topology.filter.type === 'switch' && (
              <>
                <Network size={11} /> Switch: {topology.filter.switch_ip}
              </>
            )}
            {(topology.filter.type === 'hgw' || topology.filter.type === 'user_hgw') && (
              <>
                <Wifi size={11} /> Gateway filter active
              </>
            )}
          </div>
        )}
      </div>

      {/* ── Main canvas ── */}
      <div className={`topology-page__canvas-wrap ${expanded ? 'topology-page__canvas-wrap--expanded' : ''}`}>
        {/* Expand */}
        <div className="topology-page__expand-controls">
          <button
            className="topology-page__zoom-btn"
            onClick={() => setExpanded((v) => !v)}
            title={expanded ? 'Reduce' : 'Expand'}
            type="button"
          >
            {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>

        {/* Zoom */}
        <div className="topology-page__zoom-controls">
          <button className="topology-page__zoom-btn" onClick={handleZoomIn} title="Zoom in" type="button">
            <ZoomIn size={16} />
          </button>
          <button className="topology-page__zoom-btn" onClick={handleZoomOut} title="Zoom out" type="button">
            <ZoomOut size={16} />
          </button>
          <button className="topology-page__zoom-btn" onClick={handleFit} title="Reset view" type="button">
            <Maximize2 size={16} />
          </button>
        </div>

        {/* Legend */}
        <div className="topology-page__legend">
          <div className="topology-page__legend-title">Legend</div>
          {[
            { type: 'switch', label: 'Switch', color: NODE_COLORS.switch.fill },
            { type: 'rpi', label: 'Raspberry Pi', color: NODE_COLORS.rpi.fill },
            { type: 'hgw', label: 'Gateway', color: NODE_COLORS.hgw.fill },
          ].map((item) => (
            <div key={item.type} className="topology-page__legend-item">
              <span className="topology-page__legend-dot" style={{ background: item.color }} />
              <span>{item.label}</span>
            </div>
          ))}
          <div className="topology-page__legend-divider" />
          <div className="topology-page__legend-item">
            <span className="topology-page__legend-dot" style={{ background: FAILED_COLOR }} />
            <span>Device Failed</span>
          </div>
          <div className="topology-page__legend-divider" />
          <div className="topology-page__legend-link">
            <span className="topology-page__legend-line topology-page__legend-line--solid" />
            <span>Switch → RPi</span>
          </div>
          <div className="topology-page__legend-link">
            <span className="topology-page__legend-line topology-page__legend-line--dashed" />
            <span>RPi → Gateway</span>
          </div>
        </div>

        {/* SVG canvas */}
        <div ref={containerRef} className="topology-page__canvas">
          {loading ? (
            <Spinner centered size="lg" text="Loading topology..." />
          ) : error ? (
            <div className="topology-page__error">
              <AlertCircle size={32} color="var(--neutral-5)" />
              <p>{error}</p>
            </div>
          ) : isEmpty ? (
            <div className="topology-page__empty">
              <Network size={40} color="var(--neutral-5)" />
              <p>{emptyMessage()}</p>
            </div>
          ) : (
            <svg ref={svgRef} className="topology-page__svg" />
          )}
        </div>

        {/* ── Node detail panel ── */}
        {selectedNode && (
          <div className="topology-page__detail">
            <div className="topology-page__detail-header">
              <div
                className="topology-page__detail-icon"
                style={{
                  background: NODE_COLORS[selectedNode.type]?.light,
                  border: `1px solid ${NODE_COLORS[selectedNode.type]?.border}`,
                  color: isFailedNode(selectedNode) ? FAILED_COLOR : NODE_COLORS[selectedNode.type]?.fill,
                }}
              >
                {selectedNode.type === 'switch' && <Network size={16} />}
                {selectedNode.type === 'rpi' && <Cpu size={16} />}
                {selectedNode.type === 'hgw' && <Wifi size={16} />}
              </div>
              <div>
                <div className="topology-page__detail-type">{selectedNode.type.toUpperCase()}</div>
                <div className="topology-page__detail-ip mono">{selectedNode.ip}</div>
              </div>
              <button className="topology-page__detail-close" onClick={() => setSelectedNode(null)} type="button">
                ×
              </button>
            </div>

            <div className="topology-page__detail-body">
              {selectedNode.label !== selectedNode.ip && (
                <div className="topology-page__detail-row">
                  <span>Label</span>
                  <span>{selectedNode.label}</span>
                </div>
              )}

              {/* Switch fields */}
              {selectedNode.type === 'switch' && (
                <>
                  <div className="topology-page__detail-row">
                    <span>Model</span>
                    <span>{selectedNode.data?.model || '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>MAC</span>
                    <span className="mono">{selectedNode.data?.mac_address || '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Firmware</span>
                    <span>
                      {selectedNode.data?.firmware_version || selectedNode.data?.firmware || '—'}
                    </span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>RPis</span>
                    <span>{selectedNode.data?.rpi_count ?? '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Status</span>
                    <span
                      style={{
                        color: isFailedNode(selectedNode) ? FAILED_COLOR : 'var(--success-dark)',
                        fontWeight: 600,
                      }}
                    >
                      {isFailedNode(selectedNode) ? 'Failed' : 'OK'}
                    </span>
                  </div>
                  {selectedNode.data?.ssh_error && (
                    <div className="topology-page__detail-row">
                      <span>Error</span>
                      <span>{selectedNode.data.ssh_error}</span>
                    </div>
                  )}
                </>
              )}

              {/* RPi fields */}
              {selectedNode.type === 'rpi' && (
                <>
                  <div className="topology-page__detail-row">
                    <span>MAC</span>
                    <span className="mono">{selectedNode.data?.mac || '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>SSH</span>
                    <span
                      style={{
                        color:
                          (selectedNode.data?.ssh_success ?? selectedNode.data?.last_ssh_success) === false
                            ? FAILED_COLOR
                            : 'var(--success-dark)',
                        fontWeight: 600,
                      }}
                    >
                      {(selectedNode.data?.ssh_success ?? selectedNode.data?.last_ssh_success) === false
                        ? 'Failed'
                        : 'Success'}
                    </span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Switch</span>
                    <span className="mono">{selectedNode.data?.switch_ip || '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Port</span>
                    <span>{selectedNode.data?.switch_port || '—'}</span>
                  </div>
                  {selectedNode.data?.hostname && (
                    <div className="topology-page__detail-row">
                      <span>Hostname</span>
                      <span>{selectedNode.data.hostname}</span>
                    </div>
                  )}
                  {selectedNode.data?.temp_celsius != null && (
                    <div className="topology-page__detail-row">
                      <span>Temp</span>
                      <span>{selectedNode.data.temp_celsius}°C</span>
                    </div>
                  )}
                  {(selectedNode.data?.ssh_error || selectedNode.data?.last_ssh_error) && (
                    <div className="topology-page__detail-row">
                      <span>Error</span>
                      <span>{selectedNode.data?.ssh_error || selectedNode.data?.last_ssh_error}</span>
                    </div>
                  )}
                </>
              )}

              {/* HGW fields */}
              {selectedNode.type === 'hgw' && (
                <>
                  <div className="topology-page__detail-row">
                    <span>Manufacturer</span>
                    <span>{selectedNode.data?.manufacturer || '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Model</span>
                    <span>{selectedNode.data?.model_name || '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Serial</span>
                    <span className="mono">{selectedNode.data?.serial_number || '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Instance Key</span>
                    <span className="mono">{selectedNode.data?.instance_key || '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Via RPis</span>
                    <span className="mono">
                      {(selectedNode.data?.via_rpi_ips || []).length
                        ? selectedNode.data.via_rpi_ips.join(', ')
                        : '—'}
                    </span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Ext IP</span>
                    <span className="mono">{selectedNode.data?.external_ip || '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Network</span>
                    <span className="mono">{selectedNode.data?.network || '—'}</span>
                  </div>
                  <div className="topology-page__detail-row">
                    <span>Status</span>
                    <span
                      style={{
                        color: isFailedNode(selectedNode) ? FAILED_COLOR : 'var(--success-dark)',
                        fontWeight: 600,
                      }}
                    >
                      {isFailedNode(selectedNode) ? 'Failed' : 'OK'}
                    </span>
                  </div>
                  {selectedNode.data?.ssh_error && (
                    <div className="topology-page__detail-row">
                      <span>Error</span>
                      <span>{selectedNode.data.ssh_error}</span>
                    </div>
                  )}
                </>
              )}

              {selectedNode.data?.last_seen && (
                <div className="topology-page__detail-row">
                  <span>Last Seen</span>
                  <span>{dayjs(selectedNode.data.last_seen).format('MMM D, HH:mm')}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default TopologyPage