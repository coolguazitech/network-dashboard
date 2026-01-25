<template>
  <div class="px-3 py-3">
    <!-- 頁面標題 -->
    <div class="flex justify-between items-center mb-3">
      <div>
        <h1 class="text-xl font-bold text-white">客戶端比較</h1>
        <p class="text-xs text-slate-400">依照機台分類查看 OLD / NEW 階段的變化（分類管理請到 Settings → MAC 清單）</p>
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

    <!-- 異常趨勢圖（整合時間選擇器） -->
    <div class="bg-slate-800/80 rounded border border-slate-600 p-3 mb-3">
      <div class="flex justify-between items-center mb-2">
        <div class="flex items-center gap-3">
          <h2 class="text-base font-bold text-white">📊 異常趨勢圖</h2>
          <!-- 當前選擇的時間顯示 -->
          <div v-if="selectedBeforeTime" class="flex items-center gap-1.5 px-2 py-0.5 bg-slate-700 border border-slate-500 rounded text-sm">
            <span class="text-cyan-300 font-medium">📅</span>
            <span class="text-white font-medium">{{ formatTimeLabel(selectedBeforeTime) }}</span>
            <span class="text-slate-400">→</span>
            <span class="text-green-400 font-medium">最新</span>
          </div>
        </div>
        <p class="text-xs text-cyan-400/80">💡 點擊折線圖任意時間點選擇比較基準</p>
      </div>
      <div v-if="chartOptions" class="rounded bg-slate-900/60">
        <v-chart 
          ref="trendChart"
          :option="chartOptions" 
          style="height: 280px" 
          @click="handleChartClick"
          @datazoom="handleDataZoom"
        />
      </div>
      <div v-else class="text-center py-6 text-slate-400 rounded bg-slate-900/60 text-sm">
        暫無時間點統計數據
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
            <h3 class="font-semibold text-slate-100 mb-3 pb-2 border-b border-slate-700">📋 OLD 階段</h3>
            <dl class="space-y-2 text-sm">
              <div v-for="(value, key) in selectedComparison.old" :key="key">
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
            <h3 class="font-semibold text-slate-100 mb-3 pb-2 border-b border-slate-700">📋 NEW 階段</h3>
            <dl class="space-y-2 text-sm">
              <div v-for="(value, key) in selectedComparison.new" :key="key">
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
      chartCategories: [],
      searchText: '',
      severityFilter: 'all',
      
      // 時間
      timepoints: [],
      selectedBeforeTime: null,
      statistics: [],
      
      // 資料
      allComparisons: [],
      selectedComparison: null,
      
      // 分頁
      currentPage: 1,
      pageSize: 25,
      
      // 圖表
      chartOptions: null,
      
      // 嚴重程度覆蓋選單
      overrideMenuTarget: null,
      overrideMenuPos: { x: 0, y: 0 },
    };
  },
  computed: {
    selectedMaintenanceId() {
      return this.maintenanceId;
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
          (c.old?.ip_address && c.old.ip_address.toLowerCase().includes(search)) ||
          (c.new?.ip_address && c.new.ip_address.toLowerCase().includes(search))
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
  },
  watch: {
    selectedMaintenanceId(newId, oldId) {
      if (newId && newId !== oldId) {
        // 重置所有狀態，避免顯示舊數據
        this.allComparisons = [];
        this.categoryStats = [];
        this.statistics = [];
        this.timepoints = [];
        this.selectedBeforeTime = null;
        this.chartOptions = null;
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
  methods: {
    async initialize() {
      this.loading = true;
      try {
        await Promise.all([
          this.loadCategories(),
          this.loadTimepoints(),
          this.loadStatistics(),
        ]);
        
        this.restoreState();
        
        await this.loadCategoryStats();
        await this.loadComparisons();
        this.updateChart();
      } finally {
        this.loading = false;
      }
    },
    
    // ===== 種類 =====
    async loadCategories() {
      if (!this.selectedMaintenanceId) return;
      try {
        // 查詢該歲修專屬的分類
        const res = await fetch(`/api/v1/categories?maintenance_id=${encodeURIComponent(this.selectedMaintenanceId)}`);
        if (res.ok) {
          this.categories = await res.json();
          // 初始化圖表種類選擇（包含所有分類ID + null未分類）
          this.chartCategories = this.categories.map(c => c.id);
          this.chartCategories.push(null); // 未分類
          
          // 重新載入成員對應（一對多：一個 MAC 可屬於多個分類）
          this.categoryMembers = {};
          for (const cat of this.categories) {
            const memberRes = await fetch(`/api/v1/categories/${cat.id}/members`);
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
        
        // 重新載入統計數據、卡片、圖表和列表
        await this.loadStatistics();  // 重新獲取圖表統計數據
        await this.loadCategoryStats();
        await this.loadComparisons();
        this.updateChart();
      } catch (e) {
        console.error('載入種類失敗:', e);
      }
    },
    
    async loadCategoryStats() {
      if (!this.selectedMaintenanceId) return;
      try {
        // 使用當前選擇的 before_time，確保卡片和列表數據一致
        const params = new URLSearchParams();
        if (this.selectedBeforeTime) {
          params.append('before_time', this.selectedBeforeTime);
        }
        const url = `/api/v1/categories/stats/${this.selectedMaintenanceId}?${params}`;
        const res = await fetch(url);
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
    
    toggleChartCategory(catId) {
      const idx = this.chartCategories.indexOf(catId);
      if (idx >= 0) {
        this.chartCategories.splice(idx, 1);
      } else {
        this.chartCategories.push(catId);
      }
      this.updateChart();
      this.saveState();
    },
    
    // ===== 時間 =====
    async loadTimepoints() {
      if (!this.selectedMaintenanceId) return;
      try {
        const res = await fetch(`/api/v1/comparisons/timepoints/${this.selectedMaintenanceId}`);
        if (res.ok) {
          const data = await res.json();
          this.timepoints = data.timepoints || [];
          if (this.timepoints.length > 0 && !this.selectedBeforeTime) {
            this.selectedBeforeTime = this.timepoints[0].timestamp;
          }
        }
      } catch (e) {
        console.error('載入時間點失敗:', e);
      }
    },
    
    async onBeforeTimeChange() {
      this.saveState();
      // 同時更新卡片統計和列表，確保數據一致
      await Promise.all([
        this.loadCategoryStats(),
        this.loadComparisons(),
      ]);
      // 更新圖表以移動虛線
      this.updateChart();
    },
    
    // ===== 統計 =====
    async loadStatistics() {
      if (!this.selectedMaintenanceId) return;
      try {
        const res = await fetch(`/api/v1/comparisons/statistics/${this.selectedMaintenanceId}`);
        if (res.ok) {
          const data = await res.json();
          this.statistics = data.statistics || [];
        }
      } catch (e) {
        console.error('載入統計失敗:', e);
      }
    },
    
    // ===== 比較資料 =====
    async loadComparisons() {
      if (!this.selectedMaintenanceId) return;
      this.loading = true;
      try {
        const params = new URLSearchParams();
        if (this.selectedBeforeTime) {
          params.append('before_time', this.selectedBeforeTime);
        }
        const res = await fetch(`/api/v1/comparisons/list/${this.selectedMaintenanceId}?${params}`);
        if (res.ok) {
          const data = await res.json();
          this.allComparisons = data.results || [];
        }
      } catch (e) {
        console.error('載入比較結果失敗:', e);
      } finally {
        this.loading = false;
      }
    },
    
    // ===== 圖表 =====
    updateChart() {
      // 折線時間趨勢圖：橫軸時間，縱軸異常數，每個機台種類一條折線
      if (this.statistics.length === 0) {
        this.chartOptions = null;
        return;
      }
      
      // 時間標籤
      const timeLabels = this.statistics.map(s => s.label);
      
      // 從第一個時間點獲取所有分類
      const firstStat = this.statistics[0];
      const byUserCategory = firstStat.by_user_category || {};
      
      // 建立每個分類的折線數據
      const series = [];
      const legendData = [];
      
      for (const [catKey, catData] of Object.entries(byUserCategory)) {
        const catName = catData.name || (catKey === 'null' ? '未分類' : `分類${catKey}`);
        const catColor = catData.color || '#6B7280';
        
        // 該分類在每個時間點的異常數
        const issueData = this.statistics.map(stat => {
          const byCat = stat.by_user_category || {};
          const thisCat = byCat[catKey] || {};
          return thisCat.has_issues || 0;
        });
        
        // 顯示所有分類的折線（包含 total=0 的分類）
        legendData.push(catName);
        series.push({
          name: catName,
          type: 'line',
          smooth: true,
          symbol: 'circle',
          symbolSize: 6,
          data: issueData,
          itemStyle: { color: catColor },
          lineStyle: { color: catColor, width: 2 },
        });
      }
      
      if (series.length === 0) {
        this.chartOptions = null;
        return;
      }
      
      // 簡化的時間標籤（只顯示 MM/DD HH:mm）
      const shortTimeLabels = this.statistics.map(s => {
        const ts = s.timestamp;
        return this.formatTimeLabel(ts);
      });
      
      // 找到當前選中時間點的索引
      const selectedIndex = this.statistics.findIndex(s => s.timestamp === this.selectedBeforeTime);
      
      this.chartOptions = {
        tooltip: {
          trigger: 'axis',
          formatter: params => {
            // 使用完整時間標籤
            const idx = params[0].dataIndex;
            const stat = this.statistics[idx];
            const fullLabel = stat?.label || params[0].axisValue;
            let html = `<b>${fullLabel}</b><br/>`;
            params.forEach(p => {
              // 從統計數據中獲取該分類的詳細信息
              const catKey = Object.keys(stat?.by_user_category || {}).find(k => {
                const cat = stat.by_user_category[k];
                return cat.name === p.seriesName;
              });
              const catData = catKey ? stat.by_user_category[catKey] : null;
              const undetected = catData?.undetected || 0;
              const total = catData?.total || 0;
              // 使用後端計算的 normal 值
              const normalCount = catData?.normal || 0;
              
              html += `<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${p.color};margin-right:5px;"></span>`;
              html += `${p.seriesName}: <b>${p.value}</b> 異常`;
              if (undetected > 0) {
                html += ` / <span style="color:#999">${undetected} 未偵測</span>`;
              }
              html += ` / ${normalCount} 正常 (共 ${total})<br/>`;
            });
            return html;
          },
        },
        legend: {
          show: true,
          top: 0,
          data: legendData,
          textStyle: { color: '#94A3B8' },
        },
        grid: { left: '3%', right: '4%', bottom: '40px', top: '40px', containLabel: true },
        xAxis: {
          type: 'category',
          boundaryGap: false,
          data: shortTimeLabels,
          axisLabel: { 
            rotate: 0,
            fontSize: 11,
            color: '#64748B',
          },
          axisLine: { lineStyle: { color: '#334155' } },
        },
        yAxis: {
          type: 'value',
          name: '異常數',
          minInterval: 1,
          nameTextStyle: { color: '#94A3B8' },
          axisLabel: { color: '#64748B' },
          axisLine: { lineStyle: { color: '#334155' } },
          splitLine: { lineStyle: { color: '#1E293B' } },
        },
        // 標記當前選中的時間點（加粗虛線）
        series: series.map(s => ({
          ...s,
          markLine: selectedIndex >= 0 ? {
            silent: true,
            symbol: 'none',
            data: [{ xAxis: selectedIndex }],
            lineStyle: { color: '#3B82F6', type: 'dashed', width: 4 },
            label: { show: false },
          } : undefined,
        })),
      };
    },
    
    handleChartClick(e) {
      if (e.dataIndex !== undefined && this.statistics[e.dataIndex]) {
        this.selectedBeforeTime = this.statistics[e.dataIndex].timestamp;
        this.onBeforeTimeChange();
      }
    },
    
    handleDataZoom(e) {
      // 當滑塊拖動時，選擇對應的時間點
      if (e.batch && e.batch[0]) {
        const startValue = e.batch[0].startValue;
        if (startValue !== undefined && this.statistics[startValue]) {
          this.selectedBeforeTime = this.statistics[startValue].timestamp;
          this.onBeforeTimeChange();
        }
      }
    },
    
    formatTimeLabel(timestamp) {
      // 格式化時間標籤為更簡短的格式
      if (!timestamp) return '';
      try {
        const date = new Date(timestamp);
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hour = String(date.getHours()).padStart(2, '0');
        const min = String(date.getMinutes()).padStart(2, '0');
        return `${month}/${day} ${hour}:${min}`;
      } catch {
        return timestamp;
      }
    },
    
    // ===== 狀態保存 =====
    saveState() {
      const state = {
        selectedBeforeTime: this.selectedBeforeTime,
        selectedCategories: this.selectedCategories,
        chartCategories: this.chartCategories,
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
        this.selectedBeforeTime = state.selectedBeforeTime || this.selectedBeforeTime;
        this.selectedCategories = state.selectedCategories || [-1];
        // 不恢復 chartCategories，讓它使用 loadCategories 中初始化的值（包含所有分類）
        this.searchText = state.searchText || '';
        this.severityFilter = state.severityFilter || 'all';
        this.pageSize = state.pageSize || 25;
      }
    },
    
    onSearchChange() {
      this.currentPage = 1;
      this.saveState();
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
        if (!c.old_detected && !c.new_detected) return '⚫ 未偵測';
        if (!c.old_detected) return '⚫ OLD未偵測';
        if (!c.new_detected) return '⚫ NEW未偵測';
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
      
      // 完整欄位：包含 OLD 和 NEW 所有資料
      const headers = [
        'MAC', '種類',
        'OLD_IP', 'OLD_交換機', 'OLD_連接埠', 'OLD_VLAN', 'OLD_速率', 'OLD_雙工', 'OLD_連接狀態', 'OLD_Ping', 'OLD_ACL',
        'NEW_IP', 'NEW_交換機', 'NEW_連接埠', 'NEW_VLAN', 'NEW_速率', 'NEW_雙工', 'NEW_連接狀態', 'NEW_Ping', 'NEW_ACL',
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
            // OLD 資料
            c.old?.ip_address || '',
            c.old?.switch_hostname || '',
            c.old?.interface_name || '',
            c.old?.vlan_id || '',
            c.old?.speed || '',
            c.old?.duplex || '',
            c.old?.link_status || '',
            c.old?.ping_reachable === true ? '是' : (c.old?.ping_reachable === false ? '否' : ''),
            c.old?.acl_passes === true ? '是' : (c.old?.acl_passes === false ? '否' : ''),
            // NEW 資料
            c.new?.ip_address || '',
            c.new?.switch_hostname || '',
            c.new?.interface_name || '',
            c.new?.vlan_id || '',
            c.new?.speed || '',
            c.new?.duplex || '',
            c.new?.link_status || '',
            c.new?.ping_reachable === true ? '是' : (c.new?.ping_reachable === false ? '否' : ''),
            c.new?.acl_passes === true ? '是' : (c.new?.acl_passes === false ? '否' : ''),
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
          headers: { 'Content-Type': 'application/json' },
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
          // 重新載入統計數據（更新卡片異常數）
          await this.loadCategoryStats();
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
          // 重新載入統計數據（更新卡片異常數）
          await this.loadCategoryStats();
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
