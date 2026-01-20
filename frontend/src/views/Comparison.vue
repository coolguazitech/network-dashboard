<template>
  <div class="container mx-auto px-4 py-4">
    <!-- 頁面標題 -->
    <div class="mb-4">
      <h1 class="text-2xl font-bold text-gray-900 mb-1">客戶端歲修前後比較</h1>
      <p class="text-sm text-gray-600">
        快速查看哪些客戶端在歲修前後有變化，包括連接埠口、速率、連線狀態等關鍵項目
      </p>
    </div>

    <!-- 快速統計 -->
    <div v-if="summary" class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
      <div class="bg-white rounded shadow p-3 border-l-4 border-blue-500">
        <p class="text-gray-600 text-xs font-medium">追蹤總數</p>
        <p class="text-2xl font-bold text-gray-900">{{ summary.total }}</p>
      </div>

      <div class="bg-white rounded shadow p-3 border-l-4 border-green-500">
        <p class="text-gray-600 text-xs font-medium">正常 ✓</p>
        <p class="text-2xl font-bold text-green-600">{{ summary.unchanged }}</p>
      </div>

      <div class="bg-white rounded shadow p-3 border-l-4 border-red-500">
        <p class="text-gray-600 text-xs font-medium">重大問題</p>
        <p class="text-2xl font-bold text-red-600">{{ summary.critical }}</p>
      </div>

      <div class="bg-white rounded shadow p-3 border-l-4 border-yellow-500">
        <p class="text-gray-600 text-xs font-medium">警告</p>
        <p class="text-2xl font-bold text-yellow-600">{{ summary.warning }}</p>
      </div>
    </div>

    <!-- 控制面板 -->
    <div class="bg-white rounded shadow-md p-4 mb-4">
      <div class="grid grid-cols-1 md:grid-cols-5 gap-3">
        <!-- 維護 ID 選擇 -->
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">維護 ID</label>
          <select
            v-model="selectedMaintenanceId"
            @change="onMaintenanceIdChange"
            class="w-full px-3 py-1.5 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">-- 請選擇 --</option>
            <option value="TEST-100">TEST-100 (100筆測試資料)</option>
            <option value="2026Q1-ANNUAL">2026Q1-ANNUAL</option>
            <option value="maintenance_001">maintenance_001</option>
          </select>
        </div>

        <!-- 快速篩選按鈕 -->
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">問題篩選</label>
          <div class="flex gap-1">
            <button
              @click="quickFilter('all')"
              :class="[
                'px-2 py-1.5 rounded text-xs font-medium transition',
                filterMode === 'all' ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              ]"
            >
              全部
            </button>
            <button
              @click="quickFilter('critical')"
              :class="[
                'px-2 py-1.5 rounded text-xs font-medium transition',
                filterMode === 'critical' ? 'bg-red-600 text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              ]"
            >
              🔴
            </button>
            <button
              @click="quickFilter('warning')"
              :class="[
                'px-2 py-1.5 rounded text-xs font-medium transition',
                filterMode === 'warning' ? 'bg-yellow-600 text-white' : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
              ]"
            >
              🟡
            </button>
          </div>
        </div>

        <!-- 搜尋 -->
        <div class="md:col-span-2">
          <label class="block text-sm font-medium text-gray-700 mb-2">
            搜尋 MAC 或 IP <span class="text-xs text-gray-500">（支援部分匹配）</span>
          </label>
          <input
            v-model="searchText"
            @input="loadComparisons"
            type="text"
            placeholder="例如: 192.168.0.1 或 00:11:22"
            class="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <!-- 導出按鈕 -->
        <div class="flex items-end">
          <button
            @click="exportToCSV"
            :disabled="!comparisons || comparisons.length === 0"
            class="w-full px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white rounded-lg transition font-medium"
          >
            📥 導出 CSV
          </button>
        </div>
      </div>
    </div>

    <!-- 比較結果 - 卡片式展示 -->
    <div v-if="!loading && allComparisons.length > 0">
      <div class="mb-3 flex justify-between items-center">
        <h2 class="text-xl font-bold text-gray-900">
          比較結果 <span class="text-gray-500 text-base">(共 {{ allComparisons.length }} 筆，顯示 {{ paginatedComparisons.length }} 筆)</span>
        </h2>
        <div class="flex items-center gap-3">
          <label class="text-xs text-gray-700">
            每頁顯示:
            <select
              v-model.number="pageSize"
              @change="currentPage = 1"
              class="ml-2 px-2 py-1 text-sm border border-gray-300 rounded"
            >
              <option :value="10">10</option>
              <option :value="25">25</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
            </select>
          </label>
        </div>
      </div>

      <!-- 客戶端卡片 -->
      <div class="space-y-2">
        <div
          v-for="comparison in paginatedComparisons"
          :key="comparison.mac_address"
          class="bg-white rounded shadow hover:shadow-lg transition"
          :class="{
            'border-l-4 border-red-500': comparison.severity === 'critical',
            'border-l-4 border-yellow-500': comparison.severity === 'warning',
            'border-l-4 border-green-500': !comparison.is_changed,
            'border-l-4 border-blue-500': comparison.is_changed && comparison.severity === 'info'
          }"
        >
          <div class="p-4">
            <div class="flex justify-between items-start mb-4">
              <div>
                <h3 class="text-lg font-bold text-gray-900 font-mono">{{ comparison.mac_address }}</h3>
                <p class="text-sm text-gray-600 mt-1">
                  {{ comparison.pre_hostname || comparison.pre_ip_address || '未知主機' }}
                </p>
              </div>
              <div class="flex gap-2">
                <span
                  v-if="comparison.severity === 'critical'"
                  class="px-3 py-1 bg-red-100 text-red-800 rounded-full text-sm font-semibold"
                >
                  🔴 重大問題
                </span>
                <span
                  v-else-if="comparison.severity === 'warning'"
                  class="px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm font-semibold"
                >
                  🟡 警告
                </span>
                <span
                  v-else-if="comparison.is_changed"
                  class="px-3 py-1 bg-blue-100 text-blue-800 rounded-full text-sm font-semibold"
                >
                  ℹ️ 已變化
                </span>
                <span
                  v-else
                  class="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-semibold"
                >
                  ✓ 正常
                </span>
              </div>
            </div>

            <!-- 變化項目列表 -->
            <div v-if="comparison.differences && Object.keys(comparison.differences).length > 0" class="space-y-3">
              <div
                v-for="(change, field) in comparison.differences"
                :key="field"
                class="bg-gray-50 rounded-lg p-4"
              >
                <div class="flex items-center justify-between">
                  <div class="flex-1">
                    <h4 class="font-semibold text-gray-900 mb-2">
                      {{ getFieldLabel(field) }}
                    </h4>
                    <div class="flex items-center gap-4">
                      <div class="flex-1">
                        <p class="text-xs text-gray-500 mb-1">歲修前</p>
                        <p class="text-sm font-mono text-gray-900">
                          {{ formatValue(change.pre) }}
                        </p>
                      </div>
                      <div class="text-gray-400">→</div>
                      <div class="flex-1">
                        <p class="text-xs text-gray-500 mb-1">歲修後</p>
                        <p class="text-sm font-mono text-gray-900">
                          {{ formatValue(change.post) }}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 無變化提示 -->
            <div v-else class="text-center py-4 text-gray-500">
              ✓ 該客戶端在歲修前後保持一致
            </div>

            <!-- 查看詳情按鈕 -->
            <div class="mt-4 flex justify-end">
              <button
                @click="selectComparison(comparison)"
                class="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition font-medium"
              >
                查看完整對比
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 分頁控制 -->
      <div class="mt-6 flex justify-center items-center space-x-2">
        <button
          @click="currentPage = 1"
          :disabled="currentPage === 1"
          class="px-3 py-2 border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          ⏮️ 首頁
        </button>
        <button
          @click="currentPage--"
          :disabled="currentPage === 1"
          class="px-3 py-2 border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          ⬅️ 上一頁
        </button>
        <span class="px-4 py-2 text-sm text-gray-700">
          第 {{ currentPage }} / {{ totalPages }} 頁
        </span>
        <button
          @click="currentPage++"
          :disabled="currentPage === totalPages"
          class="px-3 py-2 border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          下一頁 ➡️
        </button>
        <button
          @click="currentPage = totalPages"
          :disabled="currentPage === totalPages"
          class="px-3 py-2 border rounded hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          末頁 ⏭️
        </button>
      </div>
    </div>

    <!-- 無數據提示 -->
    <div v-if="!loading && comparisons.length === 0 && selectedMaintenanceId" class="bg-gray-100 rounded-lg p-8 text-center">
      <p class="text-gray-600 text-lg">無比較結果</p>
      <p class="text-gray-500 text-sm mt-2">請先生成比較或檢查篩選條件</p>
    </div>

    <!-- 詳情模態框 -->
    <div
      v-if="selectedComparison"
      class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
      @click.self="selectedComparison = null"
    >
      <div class="bg-white rounded-lg shadow-lg max-w-4xl w-full max-h-96 overflow-y-auto p-8">
        <!-- 頭部 -->
        <div class="flex justify-between items-start mb-6">
          <div>
            <h2 class="text-2xl font-bold text-gray-900">{{ selectedComparison.mac_address }}</h2>
            <p class="text-sm text-gray-600 mt-1">
              <span
                v-if="selectedComparison.severity === 'critical'"
                class="text-red-600 font-semibold"
              >
                🔴 Critical
              </span>
              <span v-else-if="selectedComparison.severity === 'warning'" class="text-yellow-600 font-semibold">
                🟡 Warning
              </span>
              <span v-else class="text-blue-600 font-semibold">🔵 Info</span>
            </p>
          </div>
          <button
            @click="selectedComparison = null"
            class="text-gray-400 hover:text-gray-600 text-2xl font-bold"
          >
            ✕
          </button>
        </div>

        <!-- 比較差異 -->
        <div v-if="selectedComparison.differences && Object.keys(selectedComparison.differences).length > 0" class="mb-6">
          <h3 class="text-lg font-semibold text-gray-900 mb-4">🔄 變化詳情</h3>
          <div class="space-y-3">
            <div
              v-for="(change, field) in selectedComparison.differences"
              :key="field"
              class="bg-gray-50 border border-gray-200 rounded-lg p-4"
            >
              <p class="font-semibold text-gray-900 text-sm">{{ field }}</p>
              <div class="flex items-center justify-between mt-2 text-sm">
                <div>
                  <p class="text-gray-600">修改前</p>
                  <p class="font-mono text-gray-900">{{ change.pre }}</p>
                </div>
                <div class="text-gray-400">→</div>
                <div>
                  <p class="text-gray-600">修改後</p>
                  <p class="font-mono text-gray-900">{{ change.post }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 比對比詳細信息 -->
        <div class="grid grid-cols-2 gap-8">
          <!-- PRE 階段 -->
          <div>
            <h3 class="text-lg font-semibold text-gray-900 mb-4 pb-2 border-b">📋 歲修前 (PRE)</h3>
            <dl class="space-y-3 text-sm">
              <div v-if="selectedComparison.pre.hostname">
                <dt class="font-medium text-gray-700">主機名</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.pre.hostname }}</dd>
              </div>
              <div v-if="selectedComparison.pre.ip_address">
                <dt class="font-medium text-gray-700">IP 地址</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.pre.ip_address }}</dd>
              </div>
              <div v-if="selectedComparison.pre.switch_hostname">
                <dt class="font-medium text-gray-700">交換機</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.pre.switch_hostname }}</dd>
              </div>
              <div v-if="selectedComparison.pre.interface_name">
                <dt class="font-medium text-gray-700">埠口</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.pre.interface_name }}</dd>
              </div>
              <div v-if="selectedComparison.pre.topology_role">
                <dt class="font-medium text-gray-700">拓樸角色</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.pre.topology_role }}</dd>
              </div>
              <div v-if="selectedComparison.pre.vlan_id">
                <dt class="font-medium text-gray-700">VLAN ID</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.pre.vlan_id }}</dd>
              </div>
              <div v-if="selectedComparison.pre.speed">
                <dt class="font-medium text-gray-700">速率</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.pre.speed }}</dd>
              </div>
              <div v-if="selectedComparison.pre.duplex">
                <dt class="font-medium text-gray-700">雙工</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.pre.duplex }}</dd>
              </div>
              <div v-if="selectedComparison.pre.link_status">
                <dt class="font-medium text-gray-700">連接狀態</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.pre.link_status }}</dd>
              </div>
              <div v-if="selectedComparison.pre.ping_reachable !== null">
                <dt class="font-medium text-gray-700">Ping 可達性</dt>
                <dd class="text-gray-900">
                  {{ selectedComparison.pre.ping_reachable ? "✓ 可達" : "✗ 不可達" }}
                </dd>
              </div>
              <div v-if="selectedComparison.pre.ping_latency_ms !== null">
                <dt class="font-medium text-gray-700">Ping 延遲</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.pre.ping_latency_ms }} ms</dd>
              </div>
              <div v-if="selectedComparison.pre.acl_passes !== null">
                <dt class="font-medium text-gray-700">ACL 檢查</dt>
                <dd class="text-gray-900">{{ selectedComparison.pre.acl_passes ? "✓ 通過" : "✗ 未通過" }}</dd>
              </div>
            </dl>
          </div>

          <!-- POST 階段 -->
          <div>
            <h3 class="text-lg font-semibold text-gray-900 mb-4 pb-2 border-b">📋 歲修後 (POST)</h3>
            <dl class="space-y-3 text-sm">
              <div v-if="selectedComparison.post.hostname">
                <dt class="font-medium text-gray-700">主機名</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.post.hostname }}</dd>
              </div>
              <div v-if="selectedComparison.post.ip_address">
                <dt class="font-medium text-gray-700">IP 地址</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.post.ip_address }}</dd>
              </div>
              <div v-if="selectedComparison.post.switch_hostname">
                <dt class="font-medium text-gray-700">交換機</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.post.switch_hostname }}</dd>
              </div>
              <div v-if="selectedComparison.post.interface_name">
                <dt class="font-medium text-gray-700">埠口</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.post.interface_name }}</dd>
              </div>
              <div v-if="selectedComparison.post.topology_role">
                <dt class="font-medium text-gray-700">拓樸角色</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.post.topology_role }}</dd>
              </div>
              <div v-if="selectedComparison.post.vlan_id">
                <dt class="font-medium text-gray-700">VLAN ID</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.post.vlan_id }}</dd>
              </div>
              <div v-if="selectedComparison.post.speed">
                <dt class="font-medium text-gray-700">速率</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.post.speed }}</dd>
              </div>
              <div v-if="selectedComparison.post.duplex">
                <dt class="font-medium text-gray-700">雙工</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.post.duplex }}</dd>
              </div>
              <div v-if="selectedComparison.post.link_status">
                <dt class="font-medium text-gray-700">連接狀態</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.post.link_status }}</dd>
              </div>
              <div v-if="selectedComparison.post.ping_reachable !== null">
                <dt class="font-medium text-gray-700">Ping 可達性</dt>
                <dd class="text-gray-900">
                  {{ selectedComparison.post.ping_reachable ? "✓ 可達" : "✗ 不可達" }}
                </dd>
              </div>
              <div v-if="selectedComparison.post.ping_latency_ms !== null">
                <dt class="font-medium text-gray-700">Ping 延遲</dt>
                <dd class="text-gray-900 font-mono">{{ selectedComparison.post.ping_latency_ms }} ms</dd>
              </div>
              <div v-if="selectedComparison.post.acl_passes !== null">
                <dt class="font-medium text-gray-700">ACL 檢查</dt>
                <dd class="text-gray-900">{{ selectedComparison.post.acl_passes ? "✓ 通過" : "✗ 未通過" }}</dd>
              </div>
            </dl>
          </div>
        </div>

        <!-- 備註 -->
        <div v-if="selectedComparison.notes" class="mt-6 pt-6 border-t">
          <h4 class="font-semibold text-gray-900 mb-2">📝 備註</h4>
          <p class="text-gray-600 text-sm">{{ selectedComparison.notes }}</p>
        </div>
      </div>
    </div>

    <!-- 加載指示器 -->
    <div v-if="loading" class="flex justify-center items-center py-12">
      <div class="text-center">
        <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <p class="text-gray-600">加載中...</p>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: "Comparison",
  data() {
    return {
      selectedMaintenanceId: "",
      severityFilter: "",
      changedOnly: false,  // 顯示全部資料
      searchText: "",
      filterMode: "all",
      allComparisons: [],  // 所有比較結果
      summary: null,
      selectedComparison: null,
      loading: false,
      currentPage: 1,
      pageSize: 25,
    };
  },
  computed: {
    // 排序：重大問題 → 警告 → 正常
    sortedComparisons() {
      const severityOrder = { critical: 1, warning: 2, info: 3, unchanged: 4 };
      return [...this.allComparisons].sort((a, b) => {
        const orderA = a.is_changed ? (severityOrder[a.severity] || 3) : 4;
        const orderB = b.is_changed ? (severityOrder[b.severity] || 3) : 4;
        return orderA - orderB;
      });
    },
    // 分頁後的資料
    paginatedComparisons() {
      const start = (this.currentPage - 1) * this.pageSize;
      const end = start + this.pageSize;
      return this.sortedComparisons.slice(start, end);
    },
    // 總頁數
    totalPages() {
      return Math.ceil(this.sortedComparisons.length / this.pageSize) || 1;
    },
    // 用於顯示的所有比較結果（別名）
    comparisons() {
      return this.sortedComparisons;
    },
  },
  watch: {
    // 監聽頁碼變化，自動滾動到頂部
    currentPage() {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },
  },
  mounted() {
    // 自動選擇第一個 maintenance ID 並載入數據
    this.selectedMaintenanceId = "maintenance_001";
    this.onMaintenanceIdChange();
  },
  methods: {
    async onMaintenanceIdChange() {
      await this.loadSummary();
      await this.loadComparisons();
    },

    quickFilter(mode) {
      this.filterMode = mode;
      this.currentPage = 1;  // 重置到第一頁
      if (mode === 'all') {
        this.severityFilter = "";
      } else if (mode === 'critical') {
        this.severityFilter = "critical";
      } else if (mode === 'warning') {
        this.severityFilter = "warning";
      }
      this.loadComparisons();
    },

    getFieldLabel(field) {
      const labels = {
        switch_hostname: "🔌 交換機",
        interface_name: "🔌 連接埠口",
        topology_role: "🏗️ 拓樸角色",
        link_status: "🔗 連接狀態",
        ping_reachable: "📡 Ping 可達性",
        acl_passes: "🔒 ACL 檢查",
        speed: "⚡ 連接速率",
        duplex: "🔄 雙工模式",
        vlan_id: "🏷️ VLAN ID",
        ping_latency_ms: "⏱️ Ping 延遲",
        ip_address: "🌐 IP 地址",
        hostname: "💻 主機名",
      };
      return labels[field] || field;
    },

    formatValue(value) {
      if (value === null || value === undefined) return "無";
      if (typeof value === "boolean") return value ? "✓ 是" : "✗ 否";
      return String(value);
    },
    async onMaintenanceIdChange() {
      await this.loadSummary();
      await this.loadComparisons();
    },

    async generateComparisons() {
      if (!this.selectedMaintenanceId) return;

      this.loading = true;
      try {
        const response = await fetch(`/api/v1/comparisons/generate/${this.selectedMaintenanceId}`, {
          method: "POST",
        });

        if (!response.ok) throw new Error("生成失敗");

        const data = await response.json();
        console.log("生成結果:", data);

        await this.loadSummary();
        await this.loadComparisons();
      } catch (error) {
        console.error("生成比較失敗:", error);
        alert("生成比較失敗：" + error.message);
      } finally {
        this.loading = false;
      }
    },

    async loadSummary() {
      if (!this.selectedMaintenanceId) return;

      try {
        const response = await fetch(
          `/api/v1/comparisons/summary/${this.selectedMaintenanceId}`
        );

        if (!response.ok) throw new Error("加載摘要失敗");

        const data = await response.json();
        this.summary = data.summary;
      } catch (error) {
        console.error("加載摘要失敗:", error);
      }
    },

    async loadComparisons() {
      if (!this.selectedMaintenanceId) return;

      this.loading = true;
      try {
        const params = new URLSearchParams({
          changed_only: this.changedOnly,
        });

        if (this.severityFilter) {
          params.append("severity", this.severityFilter);
        }

        if (this.searchText) {
          params.append("search_text", this.searchText);
        }

        const response = await fetch(
          `/api/v1/comparisons/list/${this.selectedMaintenanceId}?${params.toString()}`
        );

        if (!response.ok) throw new Error("加載失敗");

        const data = await response.json();
        this.allComparisons = data.results || [];
        this.currentPage = 1;  // 重置到第一頁
      } catch (error) {
        console.error("加載比較結果失敗:", error);
        this.allComparisons = [];
      } finally {
        this.loading = false;
      }
    },

    // 導出 CSV
    exportToCSV() {
      if (!this.allComparisons || this.allComparisons.length === 0) {
        alert('沒有資料可導出');
        return;
      }

      // CSV 標題
      const headers = [
        'MAC 地址',
        '主機名稱',
        'IP 地址',
        '狀態',
        '嚴重程度',
        '歲修前_交換機',
        '歲修前_連接埠',
        '歲修前_速率',
        '歲修前_雙工',
        '歲修前_VLAN',
        '歲修前_連接狀態',
        '歲修前_Ping可達',
        '歲修後_交換機',
        '歲修後_連接埠',
        '歲修後_速率',
        '歲修後_雙工',
        '歲修後_VLAN',
        '歲修後_連接狀態',
        '歲修後_Ping可達',
        '不一致項目'
      ];

      // 轉換資料
      const rows = this.sortedComparisons.map(c => {
        // 提取不一致項目
        let differences = [];
        if (c.differences && typeof c.differences === 'object') {
          differences = Object.keys(c.differences).map(key => {
            const diff = c.differences[key];
            const label = this.getFieldLabel(key);
            return `${label}: ${this.formatValue(diff.pre)} → ${this.formatValue(diff.post)}`;
          });
        }

        // 安全地訪問巢狀資料
        const pre = c.pre || {};
        const post = c.post || {};

        return [
          c.mac_address || '',
          pre.hostname || post.hostname || '',
          pre.ip_address || post.ip_address || '',
          c.is_changed ? '有變化' : '無變化',
          c.severity === 'critical' ? '重大問題' : c.severity === 'warning' ? '警告' : c.is_changed ? '資訊' : '正常',
          pre.switch_hostname || '',
          pre.interface_name || '',
          pre.speed || '',
          pre.duplex || '',
          pre.vlan_id || '',
          pre.link_status || '',
          pre.ping_reachable !== null && pre.ping_reachable !== undefined ? (pre.ping_reachable ? '是' : '否') : '',
          post.switch_hostname || '',
          post.interface_name || '',
          post.speed || '',
          post.duplex || '',
          post.vlan_id || '',
          post.link_status || '',
          post.ping_reachable !== null && post.ping_reachable !== undefined ? (post.ping_reachable ? '是' : '否') : '',
          differences.join('; ')
        ];
      });

      // 組合 CSV
      const csvContent = [
        headers.join(','),
        ...rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      ].join('\n');

      // 加入 BOM 以支持 Excel 正確顯示中文
      const BOM = '\uFEFF';
      const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      
      link.setAttribute('href', url);
      link.setAttribute('download', `client_comparison_${this.selectedMaintenanceId}_${new Date().toISOString().slice(0, 10)}.csv`);
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    },

    selectComparison(comparison) {
      this.selectedComparison = comparison;
    },
  },
};
</script>

<style scoped>
/* 加載動畫 */
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.animate-spin {
  animation: spin 1s linear infinite;
}

/* 表格懸停效果 */
tbody tr:hover {
  background-color: rgba(0, 0, 0, 0.02);
}
</style>
