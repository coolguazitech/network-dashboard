<template>
  <div class="px-6 py-5">
    <div class="flex justify-between items-center mb-4">
      <h1 class="text-2xl font-bold text-white">網路拓樸</h1>
      <div class="flex items-center gap-3">
        <!-- 管理介面 toggle -->
        <label class="flex items-center gap-1.5 cursor-pointer select-none">
          <span
            class="relative inline-block w-8 h-[18px] rounded-full transition-colors duration-200"
            :class="showManagement ? 'bg-cyan-600' : 'bg-slate-600'"
            @click="showManagement = !showManagement"
          >
            <span
              class="absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white shadow transition-transform duration-200"
              :class="showManagement ? 'translate-x-[14px]' : 'translate-x-0'"
            ></span>
          </span>
          <span class="text-xs text-slate-400">管理介面</span>
        </label>

        <!-- 外部設備 toggle -->
        <label class="flex items-center gap-1.5 cursor-pointer select-none">
          <span
            class="relative inline-block w-8 h-[18px] rounded-full transition-colors duration-200"
            :class="showExternal ? 'bg-cyan-600' : 'bg-slate-600'"
            @click="showExternal = !showExternal"
          >
            <span
              class="absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white shadow transition-transform duration-200"
              :class="showExternal ? 'translate-x-[14px]' : 'translate-x-0'"
            ></span>
          </span>
          <span class="text-xs text-slate-400">外部設備</span>
        </label>

        <!-- 僅選取 toggle（鎖定模式才有意義） -->
        <label v-if="pinnedNodes.size > 0" class="flex items-center gap-1.5 cursor-pointer select-none">
          <span
            class="relative inline-block w-8 h-[18px] rounded-full transition-colors duration-200"
            :class="pinnedOnly ? 'bg-amber-500' : 'bg-slate-600'"
            @click="pinnedOnly = !pinnedOnly"
          >
            <span
              class="absolute top-[2px] left-[2px] w-[14px] h-[14px] rounded-full bg-white shadow transition-transform duration-200"
              :class="pinnedOnly ? 'translate-x-[14px]' : 'translate-x-0'"
            ></span>
          </span>
          <span class="text-xs text-slate-400">僅選取</span>
        </label>

        <div class="h-5 w-px bg-slate-700"></div>

        <button
          v-if="pinnedNodes.size > 0"
          @click="resetPins"
          class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm transition"
        >清除選取</button>
        <button
          @click="fetchTopology"
          :disabled="loading"
          class="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-sm transition disabled:opacity-50"
        >{{ loading ? '載入中...' : '重新整理' }}</button>
      </div>
    </div>

    <!-- 統計摘要 -->
    <div v-if="topology" class="grid grid-cols-5 gap-2.5 mb-4">
      <div class="bg-slate-800/60 border border-slate-600/40 rounded-xl px-3 py-2.5">
        <div class="text-xl font-bold text-cyan-400 tabular-nums">{{ topology.stats.total_nodes }}</div>
        <div class="text-[11px] text-slate-400 mt-0.5">總設備</div>
      </div>
      <div class="bg-slate-800/60 border border-slate-600/40 rounded-xl px-3 py-2.5">
        <div class="text-xl font-bold text-slate-300 tabular-nums">{{ topology.stats.device_list_nodes }}</div>
        <div class="text-[11px] text-slate-400 mt-0.5">清單設備</div>
      </div>
      <div class="bg-slate-800/60 border border-slate-600/40 rounded-xl px-3 py-2.5">
        <div class="text-xl font-bold text-green-400 tabular-nums">{{ topology.stats.expected_pass }}</div>
        <div class="text-[11px] text-slate-400 mt-0.5">期望通過</div>
      </div>
      <div class="bg-slate-800/60 border border-slate-600/40 rounded-xl px-3 py-2.5">
        <div class="text-xl font-bold text-red-400 tabular-nums">{{ topology.stats.expected_fail }}</div>
        <div class="text-[11px] text-slate-400 mt-0.5">期望未通過</div>
      </div>
      <div class="bg-slate-800/60 border border-slate-600/40 rounded-xl px-3 py-2.5">
        <div class="text-xl font-bold text-slate-500 tabular-nums">{{ topology.stats.discovered }}</div>
        <div class="text-[11px] text-slate-400 mt-0.5">無期望連線</div>
      </div>
    </div>

    <!-- 拓樸圖 -->
    <div class="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-600/40 overflow-hidden relative" style="height: 75vh; min-height: 500px;">
      <v-chart
        v-if="chartOption"
        ref="chartRef"
        :option="chartOption"
        :update-options="{ notMerge: true }"
        autoresize
        style="width: 100%; height: 100%;"
        @click="onChartClick"
      />
      <div v-else-if="loading" class="flex items-center justify-center h-full">
        <div class="text-center">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400 mx-auto mb-3"></div>
          <p class="text-slate-400">載入拓樸資料...</p>
        </div>
      </div>
      <div v-else-if="fetchError" class="flex items-center justify-center h-full">
        <div class="text-center">
          <div class="text-4xl mb-2">⚠️</div>
          <p class="text-red-400 mb-3">{{ fetchError }}</p>
          <button @click="fetchTopology" class="px-4 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm transition">重試</button>
        </div>
      </div>
      <div v-else class="flex items-center justify-center h-full">
        <div class="text-center">
          <div class="text-5xl mb-3">🗺️</div>
          <p class="text-slate-400 text-lg">{{ selectedMaintenanceId ? '尚無拓樸資料' : '請先在頂部選擇歲修 ID' }}</p>
          <p v-if="selectedMaintenanceId" class="text-slate-500 text-sm mt-1">需要設備清單和 LLDP/CDP 採集資料</p>
        </div>
      </div>

      <!-- 迷你地圖提示 -->
      <div v-if="chartOption" class="absolute bottom-3 right-3 text-[10px] text-slate-600 select-none pointer-events-none">
        滾輪縮放 · 拖曳平移 · 點擊節點探索鄰居 · 再點取消選取
      </div>
    </div>

    <!-- 圖例 -->
    <div v-if="topology && topology.nodes.length > 0" class="mt-3 bg-slate-800/40 border border-slate-700/40 rounded-xl px-5 py-2.5">
      <div class="flex items-center gap-5 text-xs flex-wrap">
        <span class="text-slate-500 font-medium">節點：</span>
        <span class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-cyan-500 inline-block"></span>
          <span class="text-slate-300">設備清單</span>
        </span>
        <span class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-slate-500 inline-block"></span>
          <span class="text-slate-300">外部設備</span>
        </span>
        <span class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-red-500 inline-block"></span>
          <span class="text-slate-300">驗收失敗</span>
        </span>

        <span class="h-3 w-px bg-slate-700"></span>
        <span class="text-slate-500 font-medium">連線：</span>
        <span class="flex items-center gap-1.5">
          <span class="w-4 h-0.5 bg-green-500 inline-block rounded"></span>
          <span class="text-slate-300">期望通過</span>
        </span>
        <span class="flex items-center gap-1.5">
          <span class="w-4 h-0.5 bg-red-500 inline-block rounded"></span>
          <span class="text-slate-300">期望未通過</span>
        </span>
        <span class="flex items-center gap-1.5">
          <span class="w-4 h-0.5 bg-slate-600 inline-block rounded"></span>
          <span class="text-slate-300">無期望 (已發現)</span>
        </span>

        <span class="text-slate-600 ml-auto">
          節點 {{ filteredCounts.nodes }} / 連線 {{ filteredCounts.links }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, inject, watch, onMounted } from 'vue'
import api from '@/utils/api'

const selectedMaintenanceId = inject('maintenanceId')

const loading = ref(false)
const fetchError = ref(null)
const topology = ref(null)
const chartRef = ref(null)
const showManagement = ref(false)
const showExternal = ref(false)
const pinnedNodes = ref(new Set())  // 已鎖定的節點集合（累加探索）
const pinnedOnly = ref(false)       // 僅顯示選取節點之間的連線

const LINK_COLORS = {
  expected_pass: '#22c55e',
  expected_fail: '#ef4444',
  discovered: '#475569',
}

const NODE_COLORS = {
  device_list: '#06b6d4',
  external: '#64748b',
}

// ── 階層顏色：level 越高顏色越淡 ──
const LEVEL_PALETTE = [
  '#06b6d4', // level 0 — cyan-500 (Core)
  '#0ea5e9', // level 1 — sky-500
  '#3b82f6', // level 2 — blue-500
  '#6366f1', // level 3 — indigo-500
  '#8b5cf6', // level 4 — violet-500
  '#a78bfa', // level 5+
]

function getLevelColor(level) {
  return LEVEL_PALETTE[Math.min(level, LEVEL_PALETTE.length - 1)]
}

// ── 階層佈局座標計算（支援多排） ──
function computeHierarchyPositions(nodes, links) {
  const levelGroups = {}
  nodes.forEach(n => {
    const lv = n.level ?? 0
    if (!levelGroups[lv]) levelGroups[lv] = []
    levelGroups[lv].push(n.name)
  })

  const levels = Object.keys(levelGroups).map(Number).sort((a, b) => a - b)
  if (levels.length === 0) return {}

  // 建立鄰接表
  const adj = {}
  links.forEach(l => {
    if (!adj[l.source]) adj[l.source] = new Set()
    if (!adj[l.target]) adj[l.target] = new Set()
    adj[l.source].add(l.target)
    adj[l.target].add(l.source)
  })

  // 每排最多放 MAX_PER_ROW 個節點，避免擠在一起
  const MAX_PER_ROW = 40
  const CANVAS_W = 2000
  const NODE_GAP_X = 45   // 同排節點最小水平間距
  const ROW_GAP_Y = 80    // 同 level 不同排的間距
  const LEVEL_GAP_Y = 120 // 不同 level 之間的間距
  const PADDING_X = 30

  const positions = {}
  let currentY = 40

  levels.forEach((lv, levelIdx) => {
    const levelNodes = [...levelGroups[lv]]

    // 按照上層鄰居中心 X 排序，減少交叉
    if (levelIdx > 0) {
      levelNodes.sort((a, b) => {
        return getParentCenter(a, adj, positions) - getParentCenter(b, adj, positions)
      })
    }

    // 切成多排
    const rows = []
    for (let i = 0; i < levelNodes.length; i += MAX_PER_ROW) {
      rows.push(levelNodes.slice(i, i + MAX_PER_ROW))
    }

    rows.forEach((rowNodes, rowIdx) => {
      const count = rowNodes.length
      const usableW = CANVAS_W - 2 * PADDING_X
      const actualGap = Math.max(NODE_GAP_X, usableW / Math.max(1, count))
      const totalW = actualGap * Math.max(1, count - 1)
      const startX = (CANVAS_W - totalW) / 2

      rowNodes.forEach((name, i) => {
        const x = count === 1 ? CANVAS_W / 2 : startX + i * actualGap
        positions[name] = [x, currentY]
      })

      if (rowIdx < rows.length - 1) {
        currentY += ROW_GAP_Y
      }
    })

    currentY += LEVEL_GAP_Y
  })

  return positions
}

function getParentCenter(nodeName, adj, positions) {
  const neighbors = adj[nodeName]
  if (!neighbors) return 1000
  let sum = 0
  let count = 0
  neighbors.forEach(n => {
    if (positions[n]) {
      sum += positions[n][0]
      count++
    }
  })
  return count > 0 ? sum / count : 1000
}

// ── 過濾後的節點和連線（快取計算） ──
const filteredData = computed(() => {
  if (!topology.value || topology.value.nodes.length === 0) return null

  let filteredLinks = topology.value.links
  if (!showManagement.value) {
    filteredLinks = filteredLinks.filter(l => !l.is_management)
  }

  const linkedNodes = new Set()
  filteredLinks.forEach(l => {
    linkedNodes.add(l.source)
    linkedNodes.add(l.target)
  })

  let filteredNodes = topology.value.nodes
  if (!showExternal.value) {
    filteredNodes = filteredNodes.filter(n => n.in_device_list)
    const nodeNames = new Set(filteredNodes.map(n => n.name))
    filteredLinks = filteredLinks.filter(l =>
      nodeNames.has(l.source) && nodeNames.has(l.target)
    )
  } else {
    filteredNodes = filteredNodes.filter(n =>
      n.in_device_list || linkedNodes.has(n.name)
    )
  }

  const nodeNames = new Set(filteredNodes.map(n => n.name))
  filteredLinks = filteredLinks.filter(l =>
    nodeNames.has(l.source) && nodeNames.has(l.target)
  )

  return { nodes: filteredNodes, links: filteredLinks }
})

const filteredCounts = computed(() => {
  if (!filteredData.value) return { nodes: 0, links: 0 }
  return { nodes: filteredData.value.nodes.length, links: filteredData.value.links.length }
})

const chartOption = computed(() => {
  if (!filteredData.value) return null

  const { nodes: allNodes, links: allLinks } = filteredData.value
  if (allNodes.length === 0) return null

  const pinned = pinnedNodes.value

  // ── 鄰居數 + 失敗節點（基於完整資料，保持 symbolSize 一致） ──
  const neighborCount = {}
  const failNodes = new Set()
  allLinks.forEach(l => {
    neighborCount[l.source] = (neighborCount[l.source] || 0) + 1
    neighborCount[l.target] = (neighborCount[l.target] || 0) + 1
    if (l.status === 'expected_fail') {
      failNodes.add(l.source)
      failNodes.add(l.target)
    }
  })

  // ── 依鎖定狀態過濾顯示子集 ──
  let displayNodes, displayLinks
  const onlyMode = pinnedOnly.value
  if (pinned.size > 0) {
    if (onlyMode) {
      // 僅選取模式：只顯示 pinned 節點 + 它們之間的連線
      displayNodes = allNodes.filter(n => pinned.has(n.name))
      displayLinks = allLinks.filter(l => pinned.has(l.source) && pinned.has(l.target))
    } else {
      // 探索模式：pinned 節點 + 鄰居
      const visible = new Set(pinned)
      allLinks.forEach(l => {
        if (pinned.has(l.source) || pinned.has(l.target)) {
          visible.add(l.source)
          visible.add(l.target)
        }
      })
      displayNodes = allNodes.filter(n => visible.has(n.name))
      displayLinks = allLinks.filter(l => pinned.has(l.source) || pinned.has(l.target))
    }
  } else {
    displayNodes = allNodes
    displayLinks = allLinks
  }

  const isLarge = displayNodes.length > 150
  const isVeryLarge = displayNodes.length > 300

  // ── symbolSize：鄰居越多越大 ──
  const maxNeighbors = Math.max(1, ...Object.values(neighborCount))
  const getSymbolSize = (n) => {
    const count = neighborCount[n.name] || 0
    const max = isVeryLarge ? 28 : 36
    const min = isVeryLarge ? 6 : 8
    return Math.round(min + (max - min) * Math.sqrt(count / maxNeighbors))
  }

  // ── 階層佈局：預計算座標 ──
  const hierPositions = computeHierarchyPositions(displayNodes, displayLinks)

  // ── 鎖定模式：將子集座標置中 ──
  if (pinned.size > 0 && Object.keys(hierPositions).length > 0) {
    const xs = Object.values(hierPositions).map(p => p[0])
    const ys = Object.values(hierPositions).map(p => p[1])
    const minX = Math.min(...xs), maxX = Math.max(...xs)
    const minY = Math.min(...ys), maxY = Math.max(...ys)
    const cx = (minX + maxX) / 2
    const cy = (minY + maxY) / 2
    const targetCx = 1000, targetCy = 400
    const dx = targetCx - cx, dy = targetCy - cy
    for (const name of Object.keys(hierPositions)) {
      hierPositions[name] = [hierPositions[name][0] + dx, hierPositions[name][1] + dy]
    }
  }

  // ── 連線樣式：大圖降低線寬和透明度 ──
  const linkWidth = isVeryLarge ? 0.5 : isLarge ? 0.8 : 1.2
  const linkOpacity = isVeryLarge ? 0.35 : isLarge ? 0.5 : 0.8
  const failWidth = isVeryLarge ? 1.2 : 2

  // ── 鎖定模式的 label 策略 ──
  const isPinMode = pinned.size > 0

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      confine: true,
      backgroundColor: 'rgba(15, 23, 42, 0.95)',
      borderColor: 'rgba(100, 116, 139, 0.4)',
      textStyle: { color: '#e2e8f0', fontSize: 12 },
      formatter: (params) => {
        if (params.dataType === 'node') {
          const d = params.data
          const type = d.in_device_list ? '設備清單' : '外部設備'
          let html = `<div style="font-weight:600;margin-bottom:4px;font-size:13px;">${d.name}</div>`
          html += `<div style="color:#94a3b8;">類型: <span style="color:#e2e8f0;">${type}</span></div>`
          html += `<div style="color:#94a3b8;">階層: <span style="color:#e2e8f0;">Level ${d.level}</span></div>`
          if (d.ip_address) html += `<div style="color:#94a3b8;">IP: <span style="color:#e2e8f0;">${d.ip_address}</span></div>`
          if (d.vendor) html += `<div style="color:#94a3b8;">廠商: <span style="color:#e2e8f0;">${d.vendor}</span></div>`
          html += `<div style="color:#94a3b8;">鄰居: <span style="color:#e2e8f0;">${neighborCount[d.name] || 0}</span></div>`
          if (d.hasFail) html += `<div style="color:#ef4444;margin-top:2px;font-weight:600;">有驗收失敗連線</div>`
          return html
        }
        if (params.dataType === 'edge') {
          const d = params.data
          const statusLabels = {
            expected_pass: '<span style="color:#22c55e;">期望通過</span>',
            expected_fail: '<span style="color:#ef4444;">期望未通過</span>',
            discovered: '<span style="color:#94a3b8;">無期望 (已發現)</span>',
          }
          let html = `<div style="font-weight:600;margin-bottom:4px;">${d.source} ↔ ${d.target}</div>`
          // 合併模式下 value 是多行介面文字，非合併模式下有 local_interface/remote_interface
          if (d.value) {
            const lines = d.value.split('\n')
            lines.forEach(line => {
              html += `<div style="color:#94a3b8;">${line}</div>`
            })
          } else if (d.local_interface) {
            html += `<div style="color:#94a3b8;">${d.local_interface} ↔ ${d.remote_interface}</div>`
          }
          html += `<div style="margin-top:4px;">${statusLabels[d.status] || d.status}</div>`
          if (d.is_management) html += `<div style="color:#f59e0b;margin-top:2px;">管理介面</div>`
          return html
        }
        return ''
      },
    },
    legend: { show: false },
    animationDuration: 0,
    animationDurationUpdate: 0,
    series: [{
      type: 'graph',
      layout: 'none',
      roam: true,
      draggable: !isVeryLarge,
      progressive: isVeryLarge ? 400 : isLarge ? 200 : 0,
      progressiveThreshold: 200,
      label: {
        show: isPinMode || !isLarge,
        position: 'bottom',
        fontSize: isPinMode ? 11 : 9,
        color: '#94a3b8',
        formatter: '{b}',
        overflow: 'truncate',
        width: 70,
      },
      edgeLabel: {
        show: false,
      },
      emphasis: {
        focus: 'adjacency',
        label: { show: true, fontSize: 12, fontWeight: 'bold', color: '#fff' },
        lineStyle: { width: 3, opacity: 1 },
        itemStyle: { borderWidth: 2, borderColor: '#fff' },
        scale: 1.6,
      },
      blur: {
        itemStyle: { opacity: 0.08 },
        lineStyle: { opacity: 0.02 },
        label: { show: false },
      },
      categories: [
        { name: '設備清單', itemStyle: { color: NODE_COLORS.device_list } },
        { name: '外部設備', itemStyle: { color: NODE_COLORS.external } },
      ],
      nodes: displayNodes.map(n => {
        const pos = hierPositions[n.name]
        const isFail = failNodes.has(n.name)
        const isPinnedNode = pinned.has(n.name)
        const color = isFail ? '#ef4444' : n.in_device_list ? getLevelColor(n.level ?? 0) : NODE_COLORS.external
        return {
          name: n.name,
          category: n.category,
          symbolSize: getSymbolSize(n),
          in_device_list: n.in_device_list,
          ip_address: n.ip_address,
          vendor: n.vendor,
          level: n.level,
          hasFail: isFail,
          ...(pos ? { x: pos[0], y: pos[1], fixed: true } : {}),
          itemStyle: {
            color,
            borderColor: isPinnedNode ? '#fff' : isFail ? '#991b1b' : 'rgba(0,0,0,0.3)',
            borderWidth: isPinnedNode ? 2 : isFail ? 1.5 : 0.5,
          },
          label: isPinMode ? {
            show: true,
            fontSize: isPinnedNode ? 13 : 10,
            fontWeight: isPinnedNode ? 'bold' : 'normal',
            color: isPinnedNode ? '#fff' : '#94a3b8',
          } : undefined,
        }
      }),
      links: isPinMode
        ? (() => {
            // 合併同對節點的平行線（ECharts multigraph bug workaround）
            const pairMap = {}
            displayLinks.forEach(l => {
              const key = [l.source, l.target].sort().join('|')
              if (!pairMap[key]) pairMap[key] = { source: l.source, target: l.target, interfaces: [], statuses: [], is_management: false }
              pairMap[key].interfaces.push(`${l.local_interface} ↔ ${l.remote_interface}`)
              pairMap[key].statuses.push(l.status)
              if (l.is_management) pairMap[key].is_management = true
            })
            return Object.values(pairMap).map(p => {
              // 優先取最嚴重的狀態
              const status = p.statuses.includes('expected_fail') ? 'expected_fail'
                : p.statuses.includes('expected_pass') ? 'expected_pass' : 'discovered'
              const labelText = p.interfaces.join('\n')
              return {
                source: p.source, target: p.target,
                value: labelText,
                status, is_management: p.is_management,
                label: {
                  show: true,
                  fontSize: 11,
                  color: '#cbd5e1',
                  backgroundColor: 'rgba(15, 23, 42, 0.75)',
                  padding: [2, 6],
                  borderRadius: 3,
                  formatter: () => labelText,
                },
                lineStyle: {
                  color: LINK_COLORS[status] || LINK_COLORS.discovered,
                  width: status === 'expected_fail' ? failWidth : Math.max(linkWidth, p.interfaces.length * 0.8),
                  type: status === 'expected_fail' ? 'dashed' : 'solid',
                  opacity: 0.9,
                },
              }
            })
          })()
        : displayLinks.map(l => ({
            source: l.source, target: l.target,
            local_interface: l.local_interface, remote_interface: l.remote_interface,
            status: l.status, is_management: l.is_management,
            silent: isLarge,
            lineStyle: {
              color: LINK_COLORS[l.status] || LINK_COLORS.discovered,
              width: l.status === 'expected_fail' ? failWidth : linkWidth,
              type: l.status === 'expected_fail' ? 'dashed' : 'solid',
              opacity: l.is_management ? linkOpacity * 0.5 : linkOpacity,
              curveness: 0,
            },
          })),
    }],
  }
})

const fetchTopology = async () => {
  if (!selectedMaintenanceId.value) return

  loading.value = true
  fetchError.value = null
  try {
    const response = await api.get(`/topology/${selectedMaintenanceId.value}`)
    topology.value = response.data
  } catch (error) {
    console.error('Failed to fetch topology:', error)
    fetchError.value = '無法載入拓樸資料'
    topology.value = null
  } finally {
    loading.value = false
  }
}

watch(selectedMaintenanceId, (newId) => {
  if (newId) {
    fetchTopology()
  } else {
    topology.value = null
  }
})

onMounted(() => {
  if (selectedMaintenanceId.value) {
    fetchTopology()
  }
})

// ── 累加式探索（reactive：pinnedNodes 變化觸發 chartOption 重算） ──
let _nodeClickedFlag = false

function onChartClick(params) {
  if (params.dataType === 'node') {
    _nodeClickedFlag = true
    const next = new Set(pinnedNodes.value)
    if (next.has(params.name)) {
      next.delete(params.name)
    } else {
      next.add(params.name)
    }
    pinnedNodes.value = next
  }
}

function resetPins() {
  pinnedNodes.value = new Set()
}

// 資料來源變化時清除鎖定
watch(topology, () => { pinnedNodes.value = new Set(); pinnedOnly.value = false })
watch(pinnedNodes, (v) => { if (v.size === 0) pinnedOnly.value = false })

</script>
