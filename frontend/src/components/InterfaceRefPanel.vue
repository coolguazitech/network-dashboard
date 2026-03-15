<template>
  <!-- 觸發按鈕 — 固定在右側邊緣，hover 滑出標籤 -->
  <div class="ref-trigger" :class="{ active: open }" @click="toggle">
    <div class="ref-tab">
      <svg class="ref-tab-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="3" width="20" height="18" rx="2" />
        <path d="M9 3v18" />
        <path d="M13 8h4" />
        <path d="M13 12h4" />
        <path d="M13 16h2" />
      </svg>
      <span class="ref-tab-text">介面格式參考</span>
    </div>
  </div>

  <!-- 滑出面板 -->
  <Transition name="panel-slide">
    <div v-if="open" class="ref-overlay" @click.self="toggle">
      <div class="ref-panel">
        <!-- 標題列 -->
        <div class="panel-header">
          <h3 class="panel-title">介面格式參考</h3>
          <button @click="toggle" class="close-btn">&times;</button>
        </div>

        <p class="panel-desc">
          介面名稱會自動正規化為標準縮寫。填入長格式或短格式皆可。
        </p>

        <!-- 內容 -->
        <div class="panel-body">
          <div v-if="loading" class="text-slate-500 text-sm py-4 text-center">載入中...</div>
          <div v-else-if="byCategory">
            <div v-for="(types, cat) in byCategory" :key="cat" class="cat-section">
              <div class="cat-title">{{ catLabel(cat) }}</div>
              <table class="ref-table">
                <thead>
                  <tr>
                    <th class="w-16">縮寫</th>
                    <th class="w-14">速率</th>
                    <th class="w-44">說明</th>
                    <th class="w-28">適用廠商</th>
                    <th>輸入範例</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="t in types" :key="t.canonical">
                    <td class="font-mono text-cyan-400">{{ t.canonical }}</td>
                    <td class="text-slate-400">{{ t.speed || '-' }}</td>
                    <td class="text-slate-300">{{ t.description }}</td>
                    <td class="text-slate-400">{{ t.vendors }}</td>
                    <td class="font-mono text-slate-500">{{ t.examples.join(', ') }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref } from 'vue'
import api from '@/utils/api'

const open = ref(false)
const loading = ref(false)
const byCategory = ref(null)

const catLabel = (cat) => ({
  physical: '實體介面',
  lag: '鏈路聚合 (LAG)',
  management: '管理介面',
  virtual: '虛擬介面',
  loopback: 'Loopback',
  tunnel: 'Tunnel',
}[cat] || cat)

const toggle = async () => {
  open.value = !open.value
  if (open.value && !byCategory.value) {
    loading.value = true
    try {
      const { data } = await api.get('/switches/interface-types')
      byCategory.value = data.by_category
    } catch {
      byCategory.value = {}
    } finally {
      loading.value = false
    }
  }
}
</script>

<style scoped>
/* ── 觸發標籤 ── */
.ref-trigger {
  position: fixed;
  right: 0;
  top: calc(50% + 7.5rem);
  z-index: 40;
}

.ref-tab {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  background: rgba(15, 23, 42, 0.92);
  border: 1px solid #334155;
  border-right: none;
  border-radius: 0.5rem 0 0 0.5rem;
  padding: 0.5rem 0.625rem;
  cursor: pointer;
  transition: all 0.25s ease;
  transform: translateX(calc(100% - 2.25rem));
}

.ref-trigger:hover .ref-tab,
.ref-trigger.active .ref-tab {
  transform: translateX(0);
  border-color: #22d3ee;
  background: rgba(15, 23, 42, 0.97);
}

.ref-tab-icon {
  width: 1rem;
  height: 1rem;
  color: #94a3b8;
  flex-shrink: 0;
  transition: color 0.2s;
}

.ref-trigger:hover .ref-tab-icon,
.ref-trigger.active .ref-tab-icon {
  color: #22d3ee;
}

.ref-tab-text {
  font-size: 0.75rem;
  font-weight: 600;
  color: #94a3b8;
  white-space: nowrap;
  transition: color 0.2s;
}

.ref-trigger:hover .ref-tab-text,
.ref-trigger.active .ref-tab-text {
  color: #e2e8f0;
}

/* ── 遮罩 ── */
.ref-overlay {
  position: fixed;
  inset: 0;
  z-index: 45;
  background: rgba(0, 0, 0, 0.35);
}

/* ── 滑出面板 ── */
.ref-panel {
  position: fixed;
  right: 0;
  top: 0;
  bottom: 0;
  width: min(52rem, 90vw);
  background: #0f172a;
  border-left: 1px solid #334155;
  display: flex;
  flex-direction: column;
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.4);
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid #1e293b;
  flex-shrink: 0;
}

.panel-title {
  font-size: 1rem;
  font-weight: 700;
  color: #e2e8f0;
}

.close-btn {
  width: 2rem;
  height: 2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.25rem;
  color: #64748b;
  border-radius: 0.375rem;
  transition: all 0.15s;
}

.close-btn:hover {
  color: #e2e8f0;
  background: #1e293b;
}

.panel-desc {
  padding: 0.75rem 1.25rem;
  font-size: 0.8rem;
  color: #94a3b8;
  border-bottom: 1px solid #1e293b;
  flex-shrink: 0;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 1rem 1.25rem;
}

/* ── 分類區塊 ── */
.cat-section {
  margin-bottom: 1.25rem;
}

.cat-section:last-child {
  margin-bottom: 0;
}

.cat-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: #cbd5e1;
  margin-bottom: 0.5rem;
  padding-bottom: 0.25rem;
  border-bottom: 1px solid #1e293b;
}

/* ── 表格 ── */
.ref-table {
  width: 100%;
  font-size: 0.75rem;
}

.ref-table th {
  text-align: left;
  padding: 0.25rem 0.75rem 0.25rem 0;
  font-weight: 500;
  color: #64748b;
}

.ref-table td {
  padding: 0.3rem 0.75rem 0.3rem 0;
}

.ref-table tbody tr {
  border-top: 1px solid rgba(30, 41, 59, 0.6);
}

/* ── 動畫 ── */
.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: all 0.25s ease;
}

.panel-slide-enter-active .ref-panel,
.panel-slide-leave-active .ref-panel {
  transition: transform 0.25s ease;
}

.panel-slide-enter-from,
.panel-slide-leave-to {
  background: rgba(0, 0, 0, 0);
}

.panel-slide-enter-from .ref-panel,
.panel-slide-leave-to .ref-panel {
  transform: translateX(100%);
}
</style>
