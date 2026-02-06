<template>
  <div class="px-3 py-3">
    <!-- 頁面標題 -->
    <div class="flex justify-between items-center mb-3">
      <div>
        <h1 class="text-xl font-bold text-white">客戶端比較</h1>
        <p class="text-xs text-slate-400">依照 Checkpoint 比較 MAC 設備在不同時間點的變化</p>
      </div>
      <div v-if="currentTime" class="text-xs text-slate-400">
        最後更新: {{ formatTimeLabel(currentTime) }}
        <span class="text-cyan-400 ml-1">(每分鐘自動更新)</span>
      </div>
    </div>

    <!-- Checkpoint 選擇區 (可收合) -->
    <div class="bg-slate-800/80 rounded border border-slate-600 mb-3">
      <!-- 標題列（點擊可收合/展開） -->
      <div
        @click="checkpointPanelExpanded = !checkpointPanelExpanded"
        class="flex justify-between items-center p-3 cursor-pointer hover:bg-slate-700/30 transition"
      >
        <div class="flex items-center gap-2">
          <span class="text-slate-400 transition-transform" :class="checkpointPanelExpanded ? 'rotate-90' : ''">▶</span>
          <h2 class="text-base font-bold text-white">📅 選擇比較基準</h2>
        </div>
        <div v-if="selectedCheckpoint" class="text-sm text-slate-300">
          已選擇: <span class="text-cyan-400 font-medium">{{ formatCheckpointLabel(selectedCheckpoint) }}</span>
        </div>
      </div>

      <!-- 可收合內容 -->
      <div v-show="checkpointPanelExpanded" class="px-3 pb-3">
        <div v-if="checkpoints.length > 0">
          <!-- 日期分頁標籤 -->
          <div class="flex gap-1 mb-3 border-b border-slate-600 pb-2">
            <button
              v-for="dateKey in sortedDateKeys"
              :key="dateKey"
              @click.stop="selectedDateTab = dateKey"
              class="px-3 py-1.5 text-sm font-medium rounded-t transition"
              :class="selectedDateTab === dateKey
                ? 'bg-cyan-900/60 text-cyan-300 border-b-2 border-cyan-400'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'"
            >
              {{ formatDateTabLabel(dateKey) }}
              <span v-if="isToday(dateKey)" class="ml-1 text-xs text-yellow-400">(今日)</span>
            </button>
          </div>

          <!-- 小時網格（固定大小、全等矩形） -->
          <div class="grid grid-cols-6 gap-3">
            <button
              v-for="cp in checkpointsByDate[selectedDateTab] || []"
              :key="cp.timestamp"
              @click.stop="selectCheckpoint(cp.timestamp)"
              class="h-16 flex flex-col items-center justify-center text-sm font-mono rounded transition border"
              :class="selectedCheckpoint === cp.timestamp
                ? 'bg-cyan-900/60 border-cyan-500 text-cyan-300 ring-1 ring-cyan-400'
                : 'bg-slate-700/40 border-slate-600 text-slate-300 hover:bg-slate-700 hover:border-slate-500'"
            >
              <!-- 時間 + 預設標記 -->
              <span class="font-medium">
                {{ formatHourLabel(cp.timestamp) }}
                <span v-if="isDefaultCheckpoint(cp.timestamp)" class="text-yellow-400 text-xs ml-1">預設</span>
              </span>
              <!-- 異常摘要：異常數/總數 -->
              <span
                class="text-xs mt-1"
                :class="getCheckpointBadgeClass(cp.timestamp)"
                :title="getCheckpointTooltip(cp.timestamp)"
              >
                {{ getCheckpointBadgeText(cp.timestamp) }}
              </span>
            </button>
          </div>
        </div>
        <div v-else class="text-center py-4 text-slate-400 text-sm">
          暫無 Checkpoint 資料
        </div>
      </div>
    </div>

    <!-- 異常趨勢折線圖 -->
    <div class="bg-slate-800/80 rounded border border-slate-600 mb-3 p-3">
      <div class="flex justify-between items-center mb-2">
        <h3 class="text-sm font-bold text-white">📈 異常趨勢</h3>
        <span class="text-xs text-slate-400">每小時更新</span>
      </div>
      <div v-if="trendChartOption" style="height: 200px;">
        <v-chart :option="trendChartOption" autoresize />
      </div>
      <div v-else class="flex items-center justify-center h-32 text-slate-400 text-sm">
        載入中...
      </div>
    </div>

    <!-- 快速統計卡片（按種類） -->
    <div v-if="categoryStats.length > 0" class="grid grid-cols-5 gap-2 mb-3">
      <div
        v-for="stat in categoryStats"
        :key="stat.category_id"
        @click="toggleCategoryFilter(stat.category_id)"
        class="bg-slate-800/80 rounded cursor-pointer transition overflow-hidden hover:bg-slate-700/80 border border-slate-600"
        :style="{ borderLeft: `4px solid ${stat.color}` }"
      >
        <div class="px-2.5 py-2">
          <!-- 頂部：標題 + 星星 -->
          <div class="flex justify-between items-center mb-1">
            <p class="text-white font-semibold text-sm truncate">{{ stat.category_name }}</p>
            <span
              class="text-sm cursor-pointer flex-shrink-0"
              :class="selectedCategories.includes(stat.category_id) ? 'text-yellow-400' : 'text-slate-500 hover:text-yellow-400'"
            >
              {{ selectedCategories.includes(stat.category_id) ? '★' : '☆' }}
            </span>
          </div>

          <!-- 數據行：異常數（左）+ 總數（右） -->
          <div class="flex justify-between items-end">
            <div>
              <p class="text-2xl font-black leading-none" :class="getIssueCountClass(stat)">{{ stat.issue_count }}</p>
              <p class="text-xs text-slate-400 mt-0.5">異常</p>
            </div>
            <div class="text-right">
              <p class="text-lg font-bold text-slate-300">{{ stat.total_count }}</p>
              <p class="text-xs text-slate-400">總數</p>
            </div>
          </div>

          <!-- 未偵測提示 -->
          <p v-if="stat.undetected_count > 0" class="text-xs text-orange-400 text-right mt-0.5">({{ stat.undetected_count }} 未偵測)</p>
        </div>
      </div>
    </div>

    <!-- 對比結果摘要 -->
    <div v-if="summary" class="bg-slate-800/80 rounded border border-slate-600 p-3 mb-3">
      <div class="flex items-center gap-4">
        <div class="text-sm text-slate-300">
          <span class="text-slate-400">Before:</span>
          <span class="text-cyan-400 font-mono">{{ formatTimeLabel(selectedCheckpoint) }}</span>
        </div>
        <span class="text-slate-500">→</span>
        <div class="text-sm text-slate-300">
          <span class="text-slate-400">Current:</span>
          <span class="text-green-400 font-mono">{{ formatTimeLabel(currentTime) }}</span>
        </div>
        <div class="ml-auto flex items-center gap-4 text-sm">
          <span class="text-slate-400">總數: <span class="text-white font-bold">{{ summary.total }}</span></span>
          <span class="text-red-400">異常: <span class="font-bold">{{ summary.has_issues }}</span></span>
          <span class="text-green-400">正常: <span class="font-bold">{{ summary.normal }}</span></span>
        </div>
      </div>
    </div>

    <!-- 詳細列表 -->
    <div class="bg-slate-800/80 rounded border border-slate-600 p-3">
      <div class="flex flex-wrap items-center gap-2 mb-3">
        <input
          v-model="searchText"
          @input="onSearchChange"
          type="text"
          placeholder="🔍 搜尋 MAC / IP"
          class="flex-1 min-w-[180px] px-2.5 py-1.5 bg-slate-900 border border-slate-500 rounded text-sm text-white placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-cyan-400"
        />
        <select
          v-model="severityFilter"
          @change="saveState"
          class="px-2.5 py-1.5 bg-slate-900 border border-slate-500 rounded text-sm text-white"
        >
          <option value="all">全部狀態</option>
          <option value="has_issues">有異常</option>
          <option value="critical">重大問題</option>
          <option value="warning">警告</option>
        </select>
        <button
          @click="exportCSV"
          :disabled="filteredComparisons.length === 0"
          class="px-2.5 py-1.5 bg-green-600 hover:bg-green-500 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed text-white rounded transition text-sm font-medium"
        >
          📥 匯出
        </button>
        <div class="flex items-center gap-1.5 text-sm text-slate-300 ml-auto">
          <span>每頁</span>
          <select v-model.number="pageSize" @change="currentPage = 1; saveState()" class="px-1.5 py-1 bg-slate-900 border border-slate-500 rounded text-white text-sm">
            <option :value="10">10</option>
            <option :value="25">25</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
          <span class="text-slate-400">共 <span class="text-white font-medium">{{ filteredComparisons.length }}</span> 筆</span>
        </div>
      </div>

      <!-- 列表 -->
      <div v-if="paginatedComparisons.length === 0" class="text-center py-6 text-slate-400 bg-slate-900/50 rounded text-sm">
        無資料，請調整篩選條件。
      </div>

      <div v-else class="space-y-1.5">
        <div
          v-for="comparison in paginatedComparisons"
          :key="comparison.mac_address"
          class="bg-slate-900/60 rounded hover:bg-slate-900/90 transition px-3 py-2 border-l-4"
          :class="getBorderClass(comparison)"
        >
          <div class="flex justify-between items-center">
            <div class="flex items-center gap-2">
              <h3 class="text-base font-bold text-white font-mono">{{ comparison.mac_address }}</h3>
              <span
                v-if="getCategoryName(comparison.mac_address)"
                class="px-1.5 py-0.5 rounded text-xs font-medium"
                :style="{ backgroundColor: getCategoryColor(comparison.mac_address) + '40', color: getCategoryColor(comparison.mac_address) }"
              >
                {{ getCategoryName(comparison.mac_address) }}
              </span>
              <!-- 簡要差異 inline（最多顯示3項） -->
              <div v-if="comparison.differences && Object.keys(comparison.differences).length > 0" class="flex flex-wrap gap-1.5 ml-2">
                <div
                  v-for="(change, field) in getLimitedDifferences(comparison.differences, 3)"
                  :key="field"
                  class="text-xs bg-slate-800 px-1.5 py-0.5 rounded border"
                  :class="isExpectedChange(comparison) ? 'border-green-700/50' : 'border-amber-700/50'"
                >
                  <span class="text-slate-300">{{ getFieldLabel(field) }}:</span>
                  <span class="text-slate-400">{{ formatValue(change.old) }}</span>
                  <span :class="isExpectedChange(comparison) ? 'text-green-500' : 'text-amber-500'">→</span>
                  <span :class="isExpectedChange(comparison) ? 'text-green-300' : 'text-amber-300'">{{ formatValue(change.new) }}</span>
                </div>
                <span
                  v-if="Object.keys(comparison.differences).length > 3"
                  class="text-xs px-1.5 py-0.5"
                  :class="isExpectedChange(comparison) ? 'text-green-400' : 'text-amber-400'"
                >
                  +{{ Object.keys(comparison.differences).length - 3 }} 項變化
                </span>
              </div>
              <span v-else-if="comparison.severity !== 'undetected'" class="text-xs text-slate-500 ml-2">✓ 無變化</span>
            </div>
            <div class="flex gap-1.5 items-center">
              <!-- 手動覆蓋標記 -->
              <span v-if="comparison.is_overridden"
                class="text-xs text-purple-400 cursor-help"
                :title="`原始判斷: ${getAutoSeverityText(comparison.auto_severity)}\n${comparison.override_note || '無備註'}`"
              >
                🔧
              </span>
              <!-- 嚴重程度按鈕（可點擊修改） -->
              <button
                @click.stop="openOverrideMenu(comparison, $event)"
                :class="getSeverityBadgeClass(comparison)"
                class="cursor-pointer hover:opacity-80 transition"
                :title="comparison.is_overridden ? '點擊修改或恢復自動' : '點擊手動修改標籤'"
              >
                {{ getSeverityText(comparison) }}
              </button>
              <button
                @click="selectComparison(comparison)"
                class="px-2 py-1 text-xs bg-slate-700 hover:bg-slate-600 text-slate-200 rounded transition"
              >
                詳情
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 分頁 -->
      <div v-if="totalPages > 1" class="flex justify-center items-center gap-2 mt-3">
        <button
          @click="currentPage = Math.max(1, currentPage - 1)"
          :disabled="currentPage === 1"
          class="px-2.5 py-1 border border-slate-500 rounded text-sm text-slate-200 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-700"
        >
          上一頁
        </button>
        <span class="text-sm text-slate-300">{{ currentPage }} / {{ totalPages }}</span>
        <button
          @click="currentPage = Math.min(totalPages, currentPage + 1)"
          :disabled="currentPage === totalPages"
          class="px-2.5 py-1 border border-slate-500 rounded text-sm text-slate-200 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-700"
        >
          下一頁
        </button>
      </div>
    </div>

    <!-- 種類管理 Modal -->
    <CategoryModal
      v-if="showCategoryModal"
      :categories="categories"
      :maintenance-id="selectedMaintenanceId"
      @close="showCategoryModal = false"
      @refresh="loadCategories"
    />


    <!-- 詳情 Modal -->
    <div
      v-if="selectedComparison"
      class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4"
      @click.self="selectedComparison = null"
    >
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto p-6">
        <div class="flex justify-between items-start mb-4">
          <div>
            <h2 class="text-xl font-bold text-slate-100">{{ selectedComparison.mac_address }}</h2>
            <p class="text-sm text-slate-400">完整對比詳情</p>
          </div>
          <button @click="selectedComparison = null" class="text-slate-500 hover:text-slate-300 text-2xl">✕</button>
        </div>

        <div class="grid grid-cols-2 gap-6">
          <div>
            <h3 class="font-semibold text-slate-100 mb-3 pb-2 border-b border-slate-700">📋 Before (Checkpoint)</h3>
            <dl class="space-y-2 text-sm">
              <div v-for="(value, key) in selectedComparison.before" :key="key">
                <dt class="text-slate-500">{{ getFieldLabel(key) }}</dt>
                <dd
                  class="font-mono"
                  :class="isFieldChanged(key) ? 'text-rose-400 font-bold' : 'text-slate-200'"
                >
                  {{ formatValue(value) }}
                </dd>
              </div>
            </dl>
          </div>
          <div>
            <h3 class="font-semibold text-slate-100 mb-3 pb-2 border-b border-slate-700">📋 Current (Latest)</h3>
            <dl class="space-y-2 text-sm">
              <div v-for="(value, key) in selectedComparison.current" :key="key">
                <dt class="text-slate-500">{{ getFieldLabel(key) }}</dt>
                <dd
                  class="font-mono"
                  :class="isFieldChanged(key) ? 'text-rose-400 font-bold' : 'text-slate-200'"
                >
                  {{ formatValue(value) }}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </div>

    <!-- 嚴重程度覆蓋選單 -->
    <div
      v-if="overrideMenuTarget"
      class="fixed z-50 bg-slate-800 border border-slate-600 rounded shadow-xl py-1 min-w-[140px]"
      :style="{ top: overrideMenuPos.y + 'px', left: overrideMenuPos.x + 'px' }"
    >
      <div class="px-3 py-1 text-xs text-slate-400 border-b border-slate-700 mb-1">修改標籤</div>
      <button
        @click="setOverride('critical')"
        class="w-full px-3 py-1.5 text-left text-sm hover:bg-slate-700 text-rose-400"
      >🔴 重大</button>
      <button
        @click="setOverride('warning')"
        class="w-full px-3 py-1.5 text-left text-sm hover:bg-slate-700 text-amber-400"
      >🟡 警告</button>
      <button
        @click="setOverride('info')"
        class="w-full px-3 py-1.5 text-left text-sm hover:bg-slate-700 text-emerald-400"
      >✓ 正常</button>
      <div v-if="overrideMenuTarget.is_overridden" class="border-t border-slate-700 mt-1 pt-1">
        <button
          @click="clearOverride()"
          class="w-full px-3 py-1.5 text-left text-sm hover:bg-slate-700 text-purple-400"
        >🔄 恢復自動</button>
      </div>
    </div>
    <!-- 點擊其他地方關閉選單 -->
    <div v-if="overrideMenuTarget" class="fixed inset-0 z-40" @click="overrideMenuTarget = null"></div>

    <!-- Loading -->
    <div v-if="loading" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
      <div class="bg-slate-800 border border-slate-700 rounded-lg p-6">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400 mx-auto mb-2"></div>
        <p class="text-slate-300">載入中...</p>
      </div>
    </div>
  </div>
</template>

<script>
import CategoryModal from '../components/CategoryModal.vue';
import { getAuthHeaders } from '@/utils/auth';

export default {
  name: "Comparison",
  inject: ['maintenanceId'],
  components: { CategoryModal },
  data() {
    return {
      loading: false,
      showCategoryModal: false,

      // 種類相關
      categories: [],
      categoryStats: [],
      categoryMembers: {},

      // 篩選
      selectedCategories: [-1], // -1 = 全部
      searchText: '',
      severityFilter: 'all',

      // Checkpoint 相關
      checkpoints: [],
      checkpointSummaries: {}, // 每個 checkpoint 的異常摘要
      trendChartCategories: [], // 折線圖的類別資訊
      selectedCheckpoint: null,
      selectedDateTab: null, // 當前選中的日期分頁
      checkpointPanelExpanded: false, // 控制 Checkpoint 選擇區收合狀態
      currentTime: null,
      summary: null,

      // 資料
      allComparisons: [],
      selectedComparison: null,

      // 分頁
      currentPage: 1,
      pageSize: 25,

      // 嚴重程度覆蓋選單
      overrideMenuTarget: null,
      overrideMenuPos: { x: 0, y: 0 },

      // Polling
      pollingInterval: null,
      pollingIntervalMs: 60000, // 預設 60 秒，會從後端 config 更新
    };
  },
  computed: {
    selectedMaintenanceId() {
      return this.maintenanceId;
    },

    // 將 checkpoints 按日期分組
    checkpointsByDate() {
      const grouped = {};
      for (const cp of this.checkpoints) {
        // 解析時間戳並轉換為本地日期
        let ts = cp.timestamp;
        if (!ts.endsWith('Z') && !ts.includes('+')) {
          ts = ts + 'Z';
        }
        const date = new Date(ts);
        const dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

        if (!grouped[dateKey]) {
          grouped[dateKey] = [];
        }
        grouped[dateKey].push(cp);
      }

      // 每個日期內按時間排序（早 → 晚）
      for (const dateKey in grouped) {
        grouped[dateKey].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
      }

      return grouped;
    },

    // 日期標籤列表（按日期排序，最新在前）
    sortedDateKeys() {
      return Object.keys(this.checkpointsByDate).sort((a, b) => b.localeCompare(a));
    },

    // 篩選後的比較結果
    filteredComparisons() {
      let result = this.allComparisons;

      // 種類篩選（-1 = 全部，null = 未分類）
      if (!this.selectedCategories.includes(-1)) {
        result = result.filter(c => {
          // 標準化 MAC 格式（全部轉大寫）
          const normalizedMac = c.mac_address?.toUpperCase();
          const catIds = this.categoryMembers[normalizedMac] || [];

          // 如果該 MAC 有任一分類在選擇的分類中，就顯示
          if (catIds.length === 0) {
            // 未分類的 MAC，檢查是否選擇了 null
            return this.selectedCategories.includes(null);
          }
          return catIds.some(id => this.selectedCategories.includes(id));
        });
      }

      // 嚴重程度篩選（只有 critical、warning、undetected 才算異常，info 不算）
      if (this.severityFilter === 'critical') {
        result = result.filter(c => c.severity === 'critical');
      } else if (this.severityFilter === 'warning') {
        result = result.filter(c => c.severity === 'warning');
      } else if (this.severityFilter === 'has_issues') {
        // 只有 critical、warning、undetected 才算異常
        // severity='info' 表示預期變化或無變化，不算異常
        result = result.filter(c =>
          c.severity === 'critical' ||
          c.severity === 'warning' ||
          c.severity === 'undetected'
        );
      }

      // 搜尋篩選
      if (this.searchText) {
        const search = this.searchText.toLowerCase();
        result = result.filter(c =>
          (c.mac_address && c.mac_address.toLowerCase().includes(search)) ||
          (c.before?.ip_address && c.before.ip_address.toLowerCase().includes(search)) ||
          (c.current?.ip_address && c.current.ip_address.toLowerCase().includes(search))
        );
      }

      // 排序：重大問題 > 警告 > 其他
      const order = { critical: 1, warning: 2, info: 3 };
      result.sort((a, b) => {
        const oa = a.is_changed ? (order[a.severity] || 3) : 4;
        const ob = b.is_changed ? (order[b.severity] || 3) : 4;
        return oa - ob;
      });

      return result;
    },

    totalPages() {
      return Math.ceil(this.filteredComparisons.length / this.pageSize);
    },

    paginatedComparisons() {
      const start = (this.currentPage - 1) * this.pageSize;
      return this.filteredComparisons.slice(start, start + this.pageSize);
    },

    // 折線圖設定
    trendChartOption() {
      if (!this.checkpointSummaries || Object.keys(this.checkpointSummaries).length === 0) {
        return null;
      }

      // 按時間排序的 checkpoint keys
      const sortedKeys = Object.keys(this.checkpointSummaries).sort();

      // X 軸標籤（時間）
      const xAxisData = sortedKeys.map(ts => {
        let timestamp = ts;
        if (!timestamp.endsWith('Z') && !timestamp.includes('+')) {
          timestamp = timestamp + 'Z';
        }
        const date = new Date(timestamp);
        return `${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:00`;
      });

      // 總體異常數系列
      const totalSeries = {
        name: '全部',
        type: 'line',
        data: sortedKeys.map(ts => this.checkpointSummaries[ts]?.issue_count || 0),
        smooth: true,
        lineStyle: { width: 2, color: '#6B7280' },
        itemStyle: { color: '#6B7280' },
        symbol: 'circle',
        symbolSize: 6,
      };

      // 類別系列
      const categorySeries = [];
      if (this.trendChartCategories && this.trendChartCategories.length > 0) {
        for (const cat of this.trendChartCategories) {
          categorySeries.push({
            name: cat.name,
            type: 'line',
            data: sortedKeys.map(ts => {
              const byCategory = this.checkpointSummaries[ts]?.by_category;
              return byCategory ? (byCategory[cat.id] || 0) : 0;
            }),
            smooth: true,
            lineStyle: { width: 2, color: cat.color },
            itemStyle: { color: cat.color },
            symbol: 'circle',
            symbolSize: 6,
          });
        }
      }

      return {
        tooltip: {
          trigger: 'axis',
          backgroundColor: 'rgba(30, 41, 59, 0.95)',
          borderColor: '#475569',
          textStyle: { color: '#E2E8F0', fontSize: 12 },
        },
        legend: {
          data: ['全部', ...this.trendChartCategories.map(c => c.name)],
          textStyle: { color: '#94A3B8', fontSize: 11 },
          top: 0,
          itemWidth: 16,
          itemHeight: 10,
        },
        grid: {
          left: '3%',
          right: '3%',
          bottom: '3%',
          top: '40px',
          containLabel: true,
        },
        xAxis: {
          type: 'category',
          data: xAxisData,
          axisLine: { lineStyle: { color: '#475569' } },
          axisLabel: { color: '#94A3B8', fontSize: 10, rotate: 30 },
        },
        yAxis: {
          type: 'value',
          minInterval: 1,
          axisLine: { lineStyle: { color: '#475569' } },
          axisLabel: { color: '#94A3B8', fontSize: 10 },
          splitLine: { lineStyle: { color: '#334155' } },
        },
        series: [totalSeries, ...categorySeries],
      };
    },
  },
  watch: {
    selectedMaintenanceId(newId, oldId) {
      if (newId && newId !== oldId) {
        // 重置所有狀態，避免顯示舊數據
        this.allComparisons = [];
        this.categoryStats = [];
        this.checkpoints = [];
        this.selectedCheckpoint = null;
        this.currentTime = null;
        this.summary = null;
        this.currentPage = 1;
        // 清除該維護ID的localStorage狀態
        localStorage.removeItem(`comparison_state_${oldId}`);
        // 重新初始化
        this.initialize();
      }
    },
  },
  mounted() {
    if (this.selectedMaintenanceId) this.initialize();
  },
  beforeUnmount() {
    // 清理 polling
    this.stopPolling();
  },
  methods: {
    async initialize() {
      this.loading = true;
      try {
        // 先載入前端配置
        await this.loadFrontendConfig();

        await Promise.all([
          this.loadCategories(),
          this.loadCheckpoints(),
          this.loadCheckpointSummaries(),
        ]);

        this.restoreState();

        // 驗證恢復的 checkpoint 是否在當前列表中
        const isValidCheckpoint = this.selectedCheckpoint &&
          this.checkpoints.some(cp => cp.timestamp === this.selectedCheckpoint);

        // 如果沒有選中的 checkpoint 或選中的不在列表中，使用第一個（預設）
        if (!isValidCheckpoint && this.checkpoints.length > 0) {
          this.selectedCheckpoint = this.checkpoints[0].timestamp;
        }

        // 設置預設的日期分頁（選中的 checkpoint 所在日期，或最新日期）
        this.initializeDateTab();

        await this.loadDiff();
        await this.loadCategoryStats();

        // 啟動 polling（每 60 秒）
        this.startPolling();
      } finally {
        this.loading = false;
      }
    },

    // ===== Config =====
    async loadFrontendConfig() {
      try {
        const res = await apiFetch('/api/v1/config/frontend');
        if (res.ok) {
          const config = await res.json();
          this.pollingIntervalMs = (config.polling_interval_seconds || 60) * 1000;
        }
      } catch (e) {
        console.warn('Failed to load frontend config, using defaults:', e);
      }
    },

    // ===== Polling =====
    startPolling() {
      this.stopPolling(); // 確保沒有重複的 interval
      this.pollingInterval = setInterval(() => {
        this.refreshData();
      }, this.pollingIntervalMs);
    },

    stopPolling() {
      if (this.pollingInterval) {
        clearInterval(this.pollingInterval);
        this.pollingInterval = null;
      }
    },

    async refreshData() {
      // 靜默更新數據（不顯示 loading）
      try {
        await Promise.all([
          this.loadDiff(),
          this.loadCategoryStats(),
          this.loadCheckpointSummaries(),
        ]);
      } catch (e) {
        console.error('Polling refresh failed:', e);
      }
    },

    // ===== Checkpoints =====
    async loadCheckpoints() {
      if (!this.selectedMaintenanceId) return;
      try {
        const res = await fetch(`/api/v1/comparisons/checkpoints/${this.selectedMaintenanceId}`, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          const data = await res.json();
          this.checkpoints = data.checkpoints || [];
          // 預設值設定在 initialize() 中處理，這裡只負責載入資料
        }
      } catch (e) {
        console.error('載入 Checkpoints 失敗:', e);
      }
    },

    async loadCheckpointSummaries() {
      if (!this.selectedMaintenanceId) return;
      try {
        // 加入 include_categories=true 以取得類別分組統計（用於折線圖）
        const res = await fetch(`/api/v1/comparisons/checkpoints/${this.selectedMaintenanceId}/summaries?include_categories=true`, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          const data = await res.json();
          this.checkpointSummaries = data.summaries || {};
          this.trendChartCategories = data.categories || [];
        }
      } catch (e) {
        console.error('載入 Checkpoint 摘要失敗:', e);
      }
    },

    async onCheckpointChange() {
      this.saveState();
      this.loading = true;
      try {
        await this.loadDiff();
        await this.loadCategoryStats();
      } finally {
        this.loading = false;
      }
    },

    selectCheckpoint(timestamp) {
      this.selectedCheckpoint = timestamp;
      this.onCheckpointChange();
    },

    formatCheckpointLabel(timestamp) {
      const cp = this.checkpoints.find(c => c.timestamp === timestamp);
      return cp ? cp.label : this.formatTimeLabel(timestamp);
    },

    formatDateTabLabel(dateKey) {
      // dateKey 格式: "2026-02-02"
      const parts = dateKey.split('-');
      return `${parts[1]}/${parts[2]}`;
    },

    formatHourLabel(timestamp) {
      // 顯示小時:分鐘
      let ts = timestamp;
      if (!ts.endsWith('Z') && !ts.includes('+')) {
        ts = ts + 'Z';
      }
      const date = new Date(ts);
      const hour = String(date.getHours()).padStart(2, '0');
      const min = String(date.getMinutes()).padStart(2, '0');
      return `${hour}:${min}`;
    },

    isToday(dateKey) {
      const today = new Date();
      const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
      return dateKey === todayKey;
    },

    isDefaultCheckpoint(timestamp) {
      // 第一個 checkpoint 是預設
      return this.checkpoints.length > 0 && this.checkpoints[0].timestamp === timestamp;
    },

    initializeDateTab() {
      // 設置預設的日期分頁
      if (this.selectedCheckpoint && this.sortedDateKeys.length > 0) {
        // 找出 selectedCheckpoint 所在的日期
        let ts = this.selectedCheckpoint;
        if (!ts.endsWith('Z') && !ts.includes('+')) {
          ts = ts + 'Z';
        }
        const date = new Date(ts);
        const dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

        if (this.checkpointsByDate[dateKey]) {
          this.selectedDateTab = dateKey;
        } else {
          // 預設使用最新日期
          this.selectedDateTab = this.sortedDateKeys[0];
        }
      } else if (this.sortedDateKeys.length > 0) {
        this.selectedDateTab = this.sortedDateKeys[0];
      }
    },

    getCheckpointSummary(timestamp) {
      // 獲取特定 checkpoint 的摘要
      return this.checkpointSummaries[timestamp] || null;
    },

    getCheckpointBadgeClass(timestamp) {
      const summary = this.getCheckpointSummary(timestamp);
      if (!summary) return 'text-slate-500';
      if (summary.issue_count > 0) return 'text-red-400'; // 有異常
      return 'text-green-400'; // 無異常
    },

    getCheckpointBadgeText(timestamp) {
      const summary = this.getCheckpointSummary(timestamp);
      if (!summary) return '—';
      // 顯示格式：異常數/總數（與「全部」卡片一致）
      return `${summary.issue_count}/${summary.total}`;
    },

    getCheckpointTooltip(timestamp) {
      const summary = this.getCheckpointSummary(timestamp);
      if (!summary) return '無摘要資料';
      if (summary.issue_count > 0) {
        return `與現在相比有 ${summary.issue_count} 個異常（共 ${summary.total} 個設備）`;
      }
      return `與現在相比無異常（共 ${summary.total} 個設備）`;
    },

    // ===== Diff (Checkpoint vs Current) =====
    async loadDiff() {
      if (!this.selectedMaintenanceId || !this.selectedCheckpoint) return;
      try {
        const params = new URLSearchParams();
        params.append('checkpoint', this.selectedCheckpoint);

        const res = await fetch(`/api/v1/comparisons/diff/${this.selectedMaintenanceId}?${params}`, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          const data = await res.json();
          this.currentTime = data.current_time;
          this.summary = data.summary;
          this.allComparisons = data.results || [];

          // 更新分類統計（從 by_category）
          // 這裡可以使用 diff API 返回的分類統計，但為了和原有邏輯一致，仍然呼叫 loadCategoryStats
        }
      } catch (e) {
        console.error('載入 Diff 失敗:', e);
      }
    },

    // ===== 種類 =====
    async loadCategories() {
      if (!this.selectedMaintenanceId) return;
      try {
        // 查詢該歲修專屬的分類
        const res = await fetch(`/api/v1/categories?maintenance_id=${encodeURIComponent(this.selectedMaintenanceId)}`, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          this.categories = await res.json();

          // 重新載入成員對應（一對多：一個 MAC 可屬於多個分類）
          this.categoryMembers = {};
          for (const cat of this.categories) {
            const memberRes = await fetch(`/api/v1/categories/${cat.id}/members`, {
              headers: getAuthHeaders()
            });
            if (memberRes.ok) {
              const members = await memberRes.json();
              members.forEach(m => {
                // 標準化 MAC 格式（全部轉大寫）
                const normalizedMac = m.mac_address?.toUpperCase();
                if (!this.categoryMembers[normalizedMac]) {
                  this.categoryMembers[normalizedMac] = [];
                }
                this.categoryMembers[normalizedMac].push(cat.id);
              });
            }
          }
        }
      } catch (e) {
        console.error('載入種類失敗:', e);
      }
    },

    async loadCategoryStats() {
      if (!this.selectedMaintenanceId) return;
      try {
        // 使用當前選擇的 checkpoint，確保卡片和列表數據一致
        const params = new URLSearchParams();
        if (this.selectedCheckpoint) {
          params.append('before_time', this.selectedCheckpoint);
        }
        const url = `/api/v1/categories/stats/${this.selectedMaintenanceId}?${params}`;
        const res = await fetch(url, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          this.categoryStats = await res.json();
        }
      } catch (e) {
        console.error('載入種類統計失敗:', e);
      }
    },

    getMacCategoryIds(mac) {
      // 標準化 MAC 格式（全部轉大寫）以確保匹配
      // 返回陣列（一個 MAC 可屬於多個分類）
      const normalizedMac = mac?.toUpperCase();
      return this.categoryMembers[normalizedMac] || [];
    },

    getCategoryName(mac) {
      // 返回所有分類名稱，用逗號分隔
      const catIds = this.getMacCategoryIds(mac);
      if (catIds.length === 0) return null;
      const names = catIds
        .map(id => this.categories.find(c => c.id === id))
        .filter(c => c)
        .map(c => c.name);
      return names.length > 0 ? names.join(', ') : null;
    },

    getCategoryColor(mac) {
      // 返回第一個分類的顏色
      const catIds = this.getMacCategoryIds(mac);
      if (catIds.length === 0) return '#6B7280';
      const cat = this.categories.find(c => c.id === catIds[0]);
      return cat ? cat.color : '#6B7280';
    },

    toggleCategoryFilter(catId) {
      if (catId === -1) {
        this.selectedCategories = [-1];
      } else {
        this.selectedCategories = this.selectedCategories.filter(id => id !== -1);
        const idx = this.selectedCategories.indexOf(catId);
        if (idx >= 0) {
          this.selectedCategories.splice(idx, 1);
          if (this.selectedCategories.length === 0) {
            this.selectedCategories = [-1];
          }
        } else {
          this.selectedCategories.push(catId);
        }
      }
      this.currentPage = 1;
      this.saveState();
    },

    // ===== 狀態保存 =====
    saveState() {
      const state = {
        selectedCheckpoint: this.selectedCheckpoint,
        selectedCategories: this.selectedCategories,
        searchText: this.searchText,
        severityFilter: this.severityFilter,
        pageSize: this.pageSize,
      };
      localStorage.setItem(`comparison_state_${this.selectedMaintenanceId}`, JSON.stringify(state));
    },

    restoreState() {
      const saved = localStorage.getItem(`comparison_state_${this.selectedMaintenanceId}`);
      if (saved) {
        const state = JSON.parse(saved);
        this.selectedCheckpoint = state.selectedCheckpoint || this.selectedCheckpoint;
        this.selectedCategories = state.selectedCategories || [-1];
        this.searchText = state.searchText || '';
        this.severityFilter = state.severityFilter || 'all';
        this.pageSize = state.pageSize || 25;
      }
    },

    onSearchChange() {
      this.currentPage = 1;
      this.saveState();
    },

    formatTimeLabel(timestamp) {
      // 格式化時間標籤為更簡短的格式（後端傳來的是 UTC 時間）
      if (!timestamp) return '';
      try {
        // 後端傳來的時間是 UTC，需要加上 Z 後綴讓 JS 正確解析並轉換為本地時間
        let ts = timestamp;
        if (!ts.endsWith('Z') && !ts.includes('+')) {
          ts = ts + 'Z';
        }
        const date = new Date(ts);
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hour = String(date.getHours()).padStart(2, '0');
        const min = String(date.getMinutes()).padStart(2, '0');
        const sec = String(date.getSeconds()).padStart(2, '0');
        return `${month}/${day} ${hour}:${min}:${sec}`;
      } catch {
        return timestamp;
      }
    },

    // ===== 輔助 =====
    getLimitedDifferences(differences, limit) {
      // 只返回前 N 個差異項
      if (!differences) return {};
      const keys = Object.keys(differences);
      if (keys.length <= limit) return differences;
      const limited = {};
      keys.slice(0, limit).forEach(k => {
        limited[k] = differences[k];
      });
      return limited;
    },

    getFieldLabel(field) {
      const labels = {
        switch_hostname: '交換機',
        interface_name: '連接埠',
        link_status: '連接狀態',
        ping_reachable: 'Ping',
        acl_passes: 'ACL',
        speed: '速率',
        duplex: '雙工',
        vlan_id: 'VLAN',
        ip_address: 'IP',
        _status: '偵測狀態',
      };
      return labels[field] || field;
    },

    formatValue(v) {
      if (v === null || v === undefined) return '無';
      if (typeof v === 'boolean') return v ? '✓' : '✗';
      return String(v);
    },

    getBorderClass(c) {
      if (c.severity === 'undetected') return 'border-gray-400';
      if (c.severity === 'critical') return 'border-red-500';
      if (c.severity === 'warning') return 'border-yellow-500';
      // severity=info 視為正常（綠色邊框）
      if (c.severity === 'info') return 'border-green-500';
      if (c.is_changed) return 'border-blue-500';
      return 'border-green-500';
    },

    getSeverityBadgeClass(c) {
      if (c.severity === 'undetected') return 'px-2 py-1 bg-slate-600 text-slate-300 rounded text-xs font-semibold';
      if (c.severity === 'critical') return 'px-2 py-1 bg-rose-900/50 text-rose-400 rounded text-xs font-semibold';
      if (c.severity === 'warning') return 'px-2 py-1 bg-amber-900/50 text-amber-400 rounded text-xs font-semibold';
      // severity=info 且有變化 = 預期變化 → 顯示綠色（正常）
      if (c.severity === 'info') return 'px-2 py-1 bg-emerald-900/50 text-emerald-400 rounded text-xs font-semibold';
      if (c.is_changed) return 'px-2 py-1 bg-sky-900/50 text-sky-400 rounded text-xs font-semibold';
      return 'px-2 py-1 bg-emerald-900/50 text-emerald-400 rounded text-xs font-semibold';
    },

    getSeverityText(c) {
      if (c.severity === 'undetected') {
        // 顯示哪個階段未偵測
        if (!c.before_detected && !c.current_detected) return '⚫ 未偵測';
        if (!c.before_detected) return '⚫ Before未偵測';
        if (!c.current_detected) return '⚫ Current未偵測';
        return '⚫ 未偵測';
      }
      if (c.severity === 'critical') return '🔴 重大';
      if (c.severity === 'warning') return '🟡 警告';
      // severity=info 且有變化 = 預期變化 → 顯示「正常」
      if (c.severity === 'info') return '✓ 正常';
      if (c.is_changed) return 'ℹ️ 變化';
      return '✓ 正常';
    },

    getIssueCountClass(stat) {
      // 如果全部都是未偵測，顯示灰色
      if (stat.total_count > 0 && stat.total_count === stat.undetected_count) {
        return 'text-slate-400';
      }
      // 有異常顯示紅色，否則顯示綠色 - 使用更鮮明的顏色
      return stat.issue_count > 0 ? 'text-red-400' : 'text-green-400';
    },

    selectComparison(c) {
      this.selectedComparison = c;
    },

    isFieldChanged(field) {
      // 檢查該欄位是否有變化
      if (!this.selectedComparison || !this.selectedComparison.differences) {
        return false;
      }
      return field in this.selectedComparison.differences;
    },

    isExpectedChange(comparison) {
      // 檢查是否為預期變化（有設備對應的 switch/interface 變化）
      // 當 is_changed=true 但 severity=info 時，表示變化是預期的
      return comparison.is_changed && comparison.severity === 'info';
    },

    exportCSV() {
      const rows = this.filteredComparisons;
      if (!rows.length) return;

      // 完整欄位：包含 Before 和 Current 所有資料
      const headers = [
        'MAC', '種類',
        'Before_IP', 'Before_交換機', 'Before_連接埠', 'Before_速率', 'Before_雙工', 'Before_連接狀態', 'Before_Ping', 'Before_ACL',
        'Current_IP', 'Current_交換機', 'Current_連接埠', 'Current_速率', 'Current_雙工', 'Current_連接狀態', 'Current_Ping', 'Current_ACL',
        '狀態', '嚴重程度', '差異說明',
      ];

      const csv = [
        headers.join(','),
        ...rows.map(c => {
          // 狀態：未偵測顯示「未偵測」，有變化顯示「有變化」，否則顯示「正常」
          let status = '正常';
          if (c.severity === 'undetected') {
            status = '未偵測';
          } else if (c.is_changed) {
            status = '有變化';
          }

          // 嚴重程度翻譯
          const severityMap = {
            critical: '重大',
            warning: '警告',
            info: '正常',
            undetected: '未偵測'
          };
          const severityText = severityMap[c.severity] || c.severity || '';

          // 差異說明：將 _status 改為更易懂的名稱
          const diffKeys = Object.keys(c.differences || {});
          const diffExplain = diffKeys.map(k => {
            if (k === '_status') return '偵測狀態變化';
            return this.getFieldLabel(k);
          }).join('; ');

          return [
            c.mac_address,
            this.getCategoryName(c.mac_address) || '未分類',
            // Before 資料
            c.before?.ip_address || '',
            c.before?.switch_hostname || '',
            c.before?.interface_name || '',
            c.before?.speed || '',
            c.before?.duplex || '',
            c.before?.link_status || '',
            c.before?.ping_reachable === true ? '✓' : c.before?.ping_reachable === false ? '✗' : '',
            c.before?.acl_passes === true ? '✓' : c.before?.acl_passes === false ? '✗' : '',
            // Current 資料
            c.current?.ip_address || '',
            c.current?.switch_hostname || '',
            c.current?.interface_name || '',
            c.current?.speed || '',
            c.current?.duplex || '',
            c.current?.link_status || '',
            c.current?.ping_reachable === true ? '✓' : c.current?.ping_reachable === false ? '✗' : '',
            c.current?.acl_passes === true ? '✓' : c.current?.acl_passes === false ? '✗' : '',
            // 狀態
            status,
            severityText,
            diffExplain,
          ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(',');
        })
      ].join('\n');

      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `comparison_${this.selectedMaintenanceId}_${new Date().toISOString().slice(0,10)}.csv`;
      link.click();
    },

    // ===== 嚴重程度覆蓋 =====
    openOverrideMenu(comparison, event) {
      this.overrideMenuTarget = comparison;
      // 定位選單
      const rect = event.target.getBoundingClientRect();
      const menuHeight = 150; // 選單大約高度

      // 判斷是否接近底部，如果是則向上彈出
      const spaceBelow = window.innerHeight - rect.bottom;
      const showAbove = spaceBelow < menuHeight;

      this.overrideMenuPos = {
        x: Math.min(rect.left, window.innerWidth - 160),
        y: showAbove ? rect.top - menuHeight : rect.bottom + 4,
      };
    },

    async setOverride(severity) {
      if (!this.overrideMenuTarget) return;
      const mac = this.overrideMenuTarget.mac_address;
      // 確保正確獲取原始嚴重程度（未覆蓋時使用當前 severity）
      const original = this.overrideMenuTarget.is_overridden
        ? this.overrideMenuTarget.auto_severity
        : this.overrideMenuTarget.severity;

      try {
        const res = await fetch(`/api/v1/comparisons/overrides/${this.selectedMaintenanceId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
          body: JSON.stringify({
            mac_address: mac,
            override_severity: severity,
            original_severity: original,
          }),
        });

        if (res.ok) {
          // 更新本地數據
          const idx = this.allComparisons.findIndex(c => c.mac_address === mac);
          if (idx >= 0) {
            this.allComparisons[idx].severity = severity;
            this.allComparisons[idx].is_overridden = true;
            this.allComparisons[idx].original_severity = original;
          }
          // 重新載入統計數據（更新卡片異常數和 Checkpoint 摘要）
          await Promise.all([
            this.loadCategoryStats(),
            this.loadCheckpointSummaries(),
          ]);
        }
      } catch (e) {
        console.error('設置覆蓋失敗:', e);
      }

      this.overrideMenuTarget = null;
    },

    async clearOverride() {
      if (!this.overrideMenuTarget) return;
      const mac = this.overrideMenuTarget.mac_address;

      try {
        const res = await fetch(`/api/v1/comparisons/overrides/${this.selectedMaintenanceId}/${encodeURIComponent(mac)}`, {
          method: 'DELETE',
          headers: getAuthHeaders()
        });

        if (res.ok) {
          const data = await res.json();
          // 更新本地數據，恢復原始嚴重程度
          const idx = this.allComparisons.findIndex(c => c.mac_address === mac);
          if (idx >= 0) {
            const original = data.original_severity || this.allComparisons[idx].auto_severity;
            this.allComparisons[idx].severity = original;
            this.allComparisons[idx].is_overridden = false;
            this.allComparisons[idx].original_severity = null;
          }
          // 重新載入統計數據（更新卡片異常數和 Checkpoint 摘要）
          await Promise.all([
            this.loadCategoryStats(),
            this.loadCheckpointSummaries(),
          ]);
        }
      } catch (e) {
        console.error('清除覆蓋失敗:', e);
      }

      this.overrideMenuTarget = null;
    },

    getAutoSeverityText(severity) {
      const map = {
        critical: '🔴 重大',
        warning: '🟡 警告',
        info: '✓ 正常',
        undetected: '⚫ 未偵測',
      };
      return map[severity] || severity || '未知';
    },
  },
};
</script>
