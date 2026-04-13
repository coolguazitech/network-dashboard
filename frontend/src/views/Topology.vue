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
          @click="fetchTopology(true)"
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

      <!-- 搜尋框 -->
      <div v-if="chartOption" class="absolute top-3 right-3 z-10 flex flex-col items-end gap-1">
        <div class="flex items-center gap-1.5 bg-slate-900/90 backdrop-blur border border-slate-600/50 rounded-lg px-2.5 py-1.5 shadow-lg">
          <svg class="w-3.5 h-3.5 text-slate-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
          </svg>
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜尋 hostname / IP"
            class="w-44 bg-transparent text-sm text-slate-200 placeholder-slate-500 focus:outline-none"
            @keydown.enter="applySearch"
            @keydown.esc="clearSearch"
          />
          <button
            v-if="searchQuery"
            @click="clearSearch"
            class="text-slate-500 hover:text-slate-300 transition"
          >
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>
        <div v-if="searchMatches.length > 0" class="text-[10px] text-cyan-400/70 pr-1">
          找到 {{ searchMatches.length }} 個節點
        </div>
        <div v-else-if="searchQuery && searchQuery.length >= 2" class="text-[10px] text-slate-500 pr-1">
          無符合結果
        </div>
      </div>

      <!-- 迷你地圖提示 -->
      <div v-if="chartOption" class="absolute bottom-3 right-3 text-[10px] text-slate-600 select-none pointer-events-none">
        滾輪縮放 · 拖曳平移 · 懸停高亮鄰居 · 點擊選取節點 · 「僅選取」顯示介面詳情
      </div>
    </div>

    <!-- 圖例 -->
    <div v-if="topology && topology.nodes.length > 0" class="mt-3 bg-slate-800/40 border border-slate-700/40 rounded-xl px-5 py-2.5">
      <div class="flex items-center gap-5 text-xs flex-wrap">
        <span class="text-slate-500 font-medium">節點：</span>
        <span class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-green-500 inline-block"></span>
          <span class="text-slate-300">正常</span>
        </span>
        <span class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-yellow-500 inline-block"></span>
          <span class="text-slate-300">驗收異常</span>
        </span>
        <span class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-red-500 inline-block"></span>
          <span class="text-slate-300">Ping 不可達</span>
        </span>
        <span class="flex items-center gap-1.5">
          <span class="w-2.5 h-2.5 rounded-full bg-slate-500 inline-block"></span>
          <span class="text-slate-300">外部設備</span>
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
import { ref, computed, inject, watch, onMounted, onBeforeUnmount, onActivated, onDeactivated, nextTick, defineOptions } from 'vue'
import api from '@/utils/api'

defineOptions({ name: 'TopologyView' })

const selectedMaintenanceId = inject('maintenanceId')

const loading = ref(false)
const fetchError = ref(null)
const topology = ref(null)
const chartRef = ref(null)
const showManagement = ref(false)
const showExternal = ref(false)     // 保留但不再顯示 UI，預設關閉
const pinnedNodes = ref(new Set())  // 已鎖定的節點集合（累加探索）
const pinnedOnly = ref(false)       // 僅顯示選取節點之間的連線
const userPositions = ref({})       // 使用者拖曳後的節點座標 { name: [x, y] }
const searchQuery = ref('')         // 搜尋框輸入
let _currentZoom = 1                // 目前縮放倍率（非 reactive，避免觸發 chart 重建）
let _roamCenter = null              // 保存 roam 中心點 [x%, y%]
let _roamZoom = null                // 保存 roam 縮放倍率

// ── 狀態持久化 ──
const STORAGE_PREFIX = 'topo_state_'

function saveUiState() {
  const mid = selectedMaintenanceId.value
  if (!mid) return
  try {
    localStorage.setItem(`${STORAGE_PREFIX}${mid}`, JSON.stringify({
      pinnedNodes: [...pinnedNodes.value],
      pinnedOnly: pinnedOnly.value,
      showManagement: showManagement.value,
      showExternal: showExternal.value,
      zoom: _currentZoom,
      roamCenter: _roamCenter,
      roamZoom: _roamZoom,
      userPositions: userPositions.value,
      searchQuery: searchQuery.value,
    }))
  } catch (_) { /* localStorage full */ }
}

function loadUiState() {
  const mid = selectedMaintenanceId.value
  if (!mid) return
  try {
    const raw = localStorage.getItem(`${STORAGE_PREFIX}${mid}`)
    if (!raw) return
    const s = JSON.parse(raw)
    if (Array.isArray(s.pinnedNodes)) pinnedNodes.value = new Set(s.pinnedNodes)
    if (s.pinnedOnly !== undefined) pinnedOnly.value = s.pinnedOnly
    if (s.showManagement !== undefined) showManagement.value = s.showManagement
    if (s.showExternal !== undefined) showExternal.value = s.showExternal
    if (s.zoom != null) _currentZoom = s.zoom
    if (s.roamCenter != null) _roamCenter = s.roamCenter
    if (s.roamZoom != null) _roamZoom = s.roamZoom
    if (s.userPositions) userPositions.value = s.userPositions
    if (s.searchQuery) searchQuery.value = s.searchQuery
  } catch (_) { /* corrupt data */ }
}

// ── 動態輪詢（30s 更新節點驗收狀態） ──
let _pollTimer = null

function startPolling() {
  stopPolling()
  _pollTimer = setInterval(() => {
    if (selectedMaintenanceId.value && !loading.value) {
      refreshTopologyQuiet()
    }
  }, 30000)
}

function stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null }
}

// 保存拖曳位置（polling 前呼叫，避免 node 回到原位）
function captureNodePositions() {
  const chart = chartRef.value?.chart
  if (!chart) return
  try {
    const graph = chart.getModel().getSeries()[0]?.getGraph()
    if (!graph) return
    const newPos = {}
    graph.eachNode(node => {
      const layout = node.getLayout()
      if (layout) newPos[node.name || node.id] = [layout[0], layout[1]]
    })
    if (Object.keys(newPos).length > 0) userPositions.value = newPos
  } catch (_) { /* not ready */ }
}

// 介面名稱正規化：長格式 → 縮寫
const _IF_PREFIX = [
  // 25G — HPE (hyphen) + Cisco (no hyphen) + abbreviated forms
  [/^Twenty-FiveGigabitEthernet/i, 'WGE'], [/^Twenty-FiveGigE/i, 'WGE'],
  [/^TwentyFiveGigabitEthernet/i, 'Twe'], [/^TwentyFiveGigE/i, 'Twe'],
  // 100G+
  [/^FourHundredGigE/i, 'FourHu'], [/^TwoHundredGigE/i, 'TwoHu'],
  [/^HundredGigabitEthernet/i, 'Hu'], [/^HundredGigE/i, 'HGE'],
  // 10G/40G
  [/^Ten-GigabitEthernet/i, 'XGE'], [/^FortyGigabitEthernet/i, 'Fo'],
  [/^FortyGigE/i, 'FGE'], [/^TenGigabitEthernet/i, 'TE'],
  // 1G and below
  [/^GigabitEthernet/i, 'GE'], [/^FastEthernet/i, 'FE'],
  // LAG / management / virtual
  [/^Bridge-Aggregation/i, 'BAGG'], [/^M-GigabitEthernet/i, 'MGE'],
  [/^Port-[Cc]hannel/i, 'Po'], [/^Bundle-Ether/i, 'BE'],
  [/^Management/i, 'Mgmt'], [/^Loopback/i, 'Lo'],
  [/^Ethernet/i, 'Eth'], [/^Vlan-interface\s*/i, 'Vlan'],
]
function shortIf(name) {
  if (!name) return name
  for (const [re, prefix] of _IF_PREFIX) {
    const m = name.match(re)
    if (m) return prefix + name.slice(m[0].length)
  }
  return name
}

// hostname hash — 用於定義 edge 一致性方向
function hashHostname(name) {
  let h = 0
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) | 0
  }
  return h >>> 0
}

async function refreshTopologyQuiet() {
  if (!selectedMaintenanceId.value) return
  captureNodePositions()
  try {
    const { data } = await api.get(`/topology/${selectedMaintenanceId.value}`)
    topology.value = data   // watcher 會保留 pinnedNodes
  } catch (_) { /* silent */ }
}

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

  // 管理介面連線涉及的節點（開啟管理介面時需包含）
  const mgmtLinkedNodes = new Set()
  if (showManagement.value) {
    topology.value.links.forEach(l => {
      if (l.is_management) {
        mgmtLinkedNodes.add(l.source)
        mgmtLinkedNodes.add(l.target)
      }
    })
  }

  let filteredNodes = topology.value.nodes.filter(n =>
    n.in_device_list || mgmtLinkedNodes.has(n.name)
  )

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

  // ── 鄰居數 + 失敗節點 ──
  const neighborCount = {}
  allLinks.forEach(l => {
    neighborCount[l.source] = (neighborCount[l.source] || 0) + 1
    neighborCount[l.target] = (neighborCount[l.target] || 0) + 1
  })

  // 節點狀態分類：ping 不到=紅, 其他驗收失敗=橘, 正常=綠
  const pingFailNodes = new Set()
  const otherFailNodes = new Set()
  allNodes.forEach(n => {
    if (n.ping_failed) {
      pingFailNodes.add(n.name)
    } else if (n.indicator_failures && n.indicator_failures.length > 0) {
      otherFailNodes.add(n.name)
    }
  })

  // uplink 驗收失敗的 link
  const failLinks = new Set()
  allLinks.forEach(l => {
    if (l.status === 'expected_fail') {
      failLinks.add(`${l.source}|${l.target}`)
    }
  })

  // ── 依鎖定狀態決定顯示 ──
  // Bug 4 修復：點選 node 不改變顯示集合，只調整視覺樣式（opacity）
  // 只有「僅選取」模式才過濾節點
  let displayNodes, displayLinks
  const onlyMode = pinnedOnly.value
  if (pinned.size > 0 && onlyMode) {
    displayNodes = allNodes.filter(n => pinned.has(n.name))
    displayLinks = allLinks.filter(l => pinned.has(l.source) && pinned.has(l.target))
  } else {
    displayNodes = allNodes
    displayLinks = allLinks
  }

  // 計算 pinned 相關節點（用於視覺高亮）
  const highlightNodes = new Set(pinned)
  if (pinned.size > 0 && !onlyMode) {
    allLinks.forEach(l => {
      if (pinned.has(l.source) || pinned.has(l.target)) {
        highlightNodes.add(l.source)
        highlightNodes.add(l.target)
      }
    })
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

  // ── 連線樣式：大圖降低線寬和透明度 ──
  const linkWidth = isVeryLarge ? 0.5 : isLarge ? 0.8 : 1.2
  const linkOpacity = isVeryLarge ? 0.35 : isLarge ? 0.5 : 0.8
  const failWidth = isVeryLarge ? 1.2 : 2

  // ── label 策略 ──
  const isPinMode = pinned.size > 0

  // ── 預先建構 links 與中點標籤節點（避免 edge label 旋轉問題）──
  let builtLinks

  if (onlyMode) {
    const pairMap = {}
    displayLinks.forEach(l => {
      // 用 hash 值決定 canonical 方向（小 hash → 大 hash）
      const hSrc = hashHostname(l.source)
      const hTgt = hashHostname(l.target)
      const srcFirst = hSrc < hTgt || (hSrc === hTgt && l.source < l.target)
      const sorted = srcFirst ? [l.source, l.target] : [l.target, l.source]
      const key = sorted.join('|')
      if (!pairMap[key]) pairMap[key] = { source: sorted[0], target: sorted[1], interfaces: [], src_interfaces: [], tgt_interfaces: [], per_link_status: [], statuses: [], is_management: false }
      if (l.source === sorted[0]) {
        pairMap[key].src_interfaces.push(l.local_interface)
        pairMap[key].tgt_interfaces.push(l.remote_interface)
      } else {
        pairMap[key].src_interfaces.push(l.remote_interface)
        pairMap[key].tgt_interfaces.push(l.local_interface)
      }
      pairMap[key].interfaces.push(`${l.local_interface} ↔ ${l.remote_interface}`)
      pairMap[key].per_link_status.push(l.status)
      pairMap[key].statuses.push(l.status)
      if (l.is_management) pairMap[key].is_management = true
    })

    builtLinks = Object.values(pairMap).map(p => {
      const status = p.statuses.includes('expected_fail') ? 'expected_fail'
        : p.statuses.includes('expected_pass') ? 'expected_pass' : 'discovered'

      // 讓每個介面名稱靠近對應的節點：
      // ECharts edge label 文字起始端靠近 source（dx≥0）或 target（dx<0，文字翻轉）
      // dx<0 時交換順序，讓 target 介面寫在前面（文字起始端 = target 側）
      const srcPos = userPositions.value[p.source] || hierPositions[p.source]
      const tgtPos = userPositions.value[p.target] || hierPositions[p.target]
      let needSwap = false
      if (srcPos && tgtPos) {
        needSwap = (tgtPos[0] - srcPos[0]) < 0
      }

      const _STATUS_TAG = { expected_pass: '✓', expected_fail: '✗ 期望', discovered: '實際' }
      const hasMultiStatus = new Set(p.per_link_status).size > 1
      const labelText = p.src_interfaces.map((s, i) => {
        const si = shortIf(s), ti = shortIf(p.tgt_interfaces[i]) || '?'
        const ifPart = needSwap ? `${ti} ↔ ${si}` : `${si} ↔ ${ti}`
        if (!hasMultiStatus) return ifPart
        const tag = _STATUS_TAG[p.per_link_status[i]] || ''
        return tag ? `${ifPart}  [${tag}]` : ifPart
      }).join('\n')

      return {
        source: p.source, target: p.target,
        value: labelText,
        _srcIf: p.src_interfaces,
        _tgtIf: p.tgt_interfaces,
        status, is_management: p.is_management,
        label: {
          show: true,
          formatter: (params) => params.data.value || '',
          fontSize: 14,
          color: '#cbd5e1',
          backgroundColor: 'rgba(15, 23, 42, 0.75)',
          padding: [4, 10],
          borderRadius: 3,
        },
        lineStyle: {
          color: LINK_COLORS[status] || LINK_COLORS.discovered,
          width: status === 'expected_fail' ? failWidth : Math.max(linkWidth, p.interfaces.length * 0.8),
          type: status === 'expected_fail' ? 'dashed' : 'solid',
          opacity: 0.9,
        },
      }
    })
  } else {
    builtLinks = displayLinks.map(l => {
      const isLinkHighlighted = pinned.size === 0 || pinned.has(l.source) || pinned.has(l.target)
      return {
        source: l.source, target: l.target,
        local_interface: l.local_interface, remote_interface: l.remote_interface,
        status: l.status, is_management: l.is_management,
        silent: isLarge,
        lineStyle: {
          color: LINK_COLORS[l.status] || LINK_COLORS.discovered,
          width: l.status === 'expected_fail' ? failWidth : linkWidth,
          type: l.status === 'expected_fail' ? 'dashed' : 'solid',
          opacity: isLinkHighlighted
            ? (l.is_management ? linkOpacity * 0.5 : linkOpacity)
            : 0.05,
          curveness: 0,
        },
      }
    })
  }

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
          const type = d.in_device_list ? '設備清單' : '管理設備'
          let html = `<div style="font-weight:600;margin-bottom:4px;font-size:13px;">${d.name}</div>`
          html += `<div style="color:#94a3b8;">類型: <span style="color:#e2e8f0;">${type}</span></div>`
          html += `<div style="color:#94a3b8;">階層: <span style="color:#e2e8f0;">Level ${d.level}</span></div>`
          if (d.ip_address) html += `<div style="color:#94a3b8;">IP: <span style="color:#e2e8f0;">${d.ip_address}</span></div>`
          if (d.vendor) html += `<div style="color:#94a3b8;">廠商: <span style="color:#e2e8f0;">${d.vendor}</span></div>`
          html += `<div style="color:#94a3b8;">鄰居: <span style="color:#e2e8f0;">${neighborCount[d.name] || 0}</span></div>`
          if (d.indicator_failures && d.indicator_failures.length > 0) {
            html += `<div style="border-top:1px solid rgba(100,116,139,0.3);margin-top:4px;padding-top:4px;">`
            html += `<div style="color:#ef4444;font-weight:600;margin-bottom:2px;">驗收失敗項目:</div>`
            d.indicator_failures.forEach(f => {
              html += `<div style="color:#fca5a5;font-size:11px;padding-left:6px;">• ${f}</div>`
            })
            html += `</div>`
          }
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
          if (d._srcIf) {
            d._srcIf.forEach((s, i) => {
              const t = d._tgtIf[i] || '?'
              html += `<div style="color:#e2e8f0;">${shortIf(s)} ↔ ${shortIf(t)}</div>`
            })
          } else if (d.local_interface) {
            html += `<div style="color:#e2e8f0;">${shortIf(d.local_interface)} ↔ ${shortIf(d.remote_interface)}</div>`
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
      scaleLimit: { min: 0.3, max: 8 },
      ...(_roamCenter ? { center: _roamCenter } : {}),
      ...(_roamZoom ? { zoom: _roamZoom } : {}),
      draggable: !isVeryLarge,
      progressive: isVeryLarge ? 400 : isLarge ? 200 : 0,
      progressiveThreshold: 200,
      label: {
        show: onlyMode || _currentZoom >= 2,
        position: 'bottom',
        fontSize: onlyMode ? 12 : 10,
        color: '#94a3b8',
        formatter: '{b}',
      },
      edgeLabel: {
        show: false,
      },
      emphasis: {
        focus: 'adjacency',
        label: { show: true, fontSize: 13, fontWeight: 'bold', color: '#fff' },
        lineStyle: { width: 3, opacity: 1 },
        itemStyle: { borderWidth: 2, borderColor: '#fff' },
        scale: 1.4,
      },
      categories: [
        { name: '設備清單', itemStyle: { color: NODE_COLORS.device_list } },
        { name: '管理設備', itemStyle: { color: NODE_COLORS.external } },
      ],
      nodes: [...displayNodes.map(n => {
        const pos = hierPositions[n.name]
        const isPingFail = pingFailNodes.has(n.name)
        const isOtherFail = otherFailNodes.has(n.name)
        const isFail = isPingFail || isOtherFail
        const isPinnedNode = pinned.has(n.name)
        const isHighlighted = highlightNodes.has(n.name)
        const isDimmed = pinned.size > 0 && !isHighlighted
        // 顏色邏輯：紅=ping不到, 黃=其他驗收失敗, 綠=正常, 灰=外部設備
        const color = isPingFail ? '#dc2626'
          : isOtherFail ? '#eab308'
          : n.in_device_list ? '#22c55e'
          : NODE_COLORS.external
        return {
          name: n.name,
          category: n.category,
          symbolSize: getSymbolSize(n),
          in_device_list: n.in_device_list,
          ip_address: n.ip_address,
          vendor: n.vendor,
          level: n.level,
          indicator_failures: n.indicator_failures,
          hasFail: isFail,
          ...((userPositions.value[n.name] || pos) ? { x: (userPositions.value[n.name] || pos)[0], y: (userPositions.value[n.name] || pos)[1], fixed: true } : {}),
          itemStyle: {
            color,
            opacity: isDimmed ? 0.15 : 1,
            borderColor: isPinnedNode ? '#fff' : isPingFail ? '#fca5a5' : isOtherFail ? '#a16207' : 'rgba(0,0,0,0.3)',
            borderWidth: isPinnedNode ? 2 : isPingFail ? 2.5 : isFail ? 1.5 : 0.5,
          },
          label: {
            show: isDimmed ? false : (onlyMode || isPinnedNode || _currentZoom >= 2),
            fontSize: onlyMode ? 13 : (isPinnedNode ? 12 : 10),
            fontWeight: (onlyMode || isPinnedNode) ? 'bold' : 'normal',
            color: (onlyMode || isPinnedNode) ? '#fff' : '#94a3b8',
          },
        }
      })],
      links: builtLinks,
    }],
  }
})

const fetchTopology = async (resetView = false) => {
  if (!selectedMaintenanceId.value) return

  loading.value = true
  fetchError.value = null
  if (resetView) {
    userPositions.value = {}
    _currentZoom = 1
    _roamCenter = null
    _roamZoom = null
  }
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
  stopPolling()
  if (newId) {
    loadUiState()
    fetchTopology().then(startPolling)
  } else {
    topology.value = null
    pinnedNodes.value = new Set()
    pinnedOnly.value = false
  }
})

onMounted(() => {
  loadUiState()
  if (selectedMaintenanceId.value) {
    fetchTopology().then(startPolling)
  }
})

// keep-alive：切走時暫停輪詢，切回時恢復
onActivated(() => {
  if (selectedMaintenanceId.value && !_pollTimer) startPolling()
})

onDeactivated(() => {
  stopPolling()
})

onBeforeUnmount(() => {
  saveUiState()
  stopPolling()
  _zrBound = false
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

// ── 搜尋節點 ──
const searchMatches = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q || q.length < 2 || !topology.value) return []
  return topology.value.nodes.filter(n =>
    n.name.toLowerCase().includes(q) ||
    (n.ip_address && n.ip_address.includes(q))
  )
})

function applySearch() {
  const matches = searchMatches.value
  if (matches.length === 0) return
  const next = new Set(pinnedNodes.value)
  matches.forEach(n => next.add(n.name))
  pinnedNodes.value = next
}

function clearSearch() {
  searchQuery.value = ''
}

// ── 拖曳偵測：拖曳結束後重新擷取座標，觸發 label 方向修正 ──
let _dragStart = null
let _zrBound = false

function bindDragEvents() {
  const chart = chartRef.value?.chart
  if (!chart || _zrBound) return
  const zr = chart.getZr()
  zr.on('mousedown', (e) => {
    _dragStart = { x: e.offsetX, y: e.offsetY }
  })
  zr.on('mouseup', (e) => {
    if (!_dragStart) return
    const ddx = e.offsetX - _dragStart.x
    const ddy = e.offsetY - _dragStart.y
    if (ddx * ddx + ddy * ddy > 25) {  // 超過 5px 才算拖曳
      captureNodePositions()
    }
    _dragStart = null
  })
  // 監聽 roam 事件：保存位置/縮放（下次 polling 重繪時套用）
  chart.on('graphroam', () => {
    const opt = chart.getOption()
    const s = opt.series?.[0]
    if (s) {
      if (s.center) _roamCenter = s.center
      if (s.zoom) { _roamZoom = s.zoom; _currentZoom = s.zoom }
      saveUiState()
    }
  })
  _zrBound = true
}

watch(chartOption, async (val) => {
  if (!val) return
  await nextTick()
  if (!_zrBound) bindDragEvents()
})

// 資料更新時保留選取狀態，只清理不存在的節點
watch(topology, (newTopo) => {
  if (!newTopo || newTopo.nodes.length === 0) {
    pinnedNodes.value = new Set()
    pinnedOnly.value = false
    return
  }
  const nodeNames = new Set(newTopo.nodes.map(n => n.name))
  const cleaned = new Set([...pinnedNodes.value].filter(n => nodeNames.has(n)))
  if (cleaned.size !== pinnedNodes.value.size) {
    pinnedNodes.value = cleaned
  }
  if (cleaned.size === 0) pinnedOnly.value = false
})

// 切換 onlyMode 或改變 pin 時清除拖曳座標，避免用到全圖舊座標算出錯誤方向
// 只在切換 onlyMode 時清除拖曳座標（佈局完全改變）
watch(pinnedOnly, () => {
  userPositions.value = {}
  saveUiState()
})
watch(pinnedNodes, (v) => { if (v.size === 0) pinnedOnly.value = false; saveUiState() })
watch([showManagement, showExternal], saveUiState)

</script>
