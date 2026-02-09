<template>
  <div class="px-3 py-3">
    <!-- 頁面標題 -->
    <div class="flex justify-between items-center mb-3">
      <div>
        <h1 class="text-xl font-bold text-white">設備管理</h1>
      </div>
    </div>

    <!-- Tab 切換 -->
    <div class="flex gap-1 mb-3 border-b border-slate-700 pb-0">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        @click="activeTab = tab.id"
        class="px-4 py-2 text-sm font-medium rounded-t transition border-b-2 -mb-[2px]"
        :class="activeTab === tab.id
          ? 'text-cyan-400 border-cyan-400 bg-slate-800/80'
          : 'text-slate-400 border-transparent hover:text-slate-200 hover:bg-slate-800/50'"
      >
        <span class="mr-1.5">{{ tab.icon }}</span>
        {{ tab.name }}
      </button>
    </div>

    <!-- Tab 內容 -->
    <div class="bg-slate-800/80 rounded border border-slate-600 p-4">
      <!-- Client 清單 Tab (歲修特定) -->
      <div v-if="activeTab === 'maclist'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h3 class="text-white font-semibold">Client 清單</h3>
          <div class="flex gap-2">
            <button v-if="userCanWrite" @click="showCategoryModal = true" class="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded transition">
              🏷️ 管理分類
            </button>
            <button @click="downloadMacTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded transition">
              📄 下載範本
            </button>
            <label v-if="userCanWrite" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importMacList" />
            </label>
            <button v-if="userCanWrite" @click="showAddMacModal = true" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition">
              ➕ 新增 Client
            </button>
          </div>
        </div>

        <div v-if="!selectedMaintenanceId" class="text-center py-8 text-slate-400">
          請先在頂部選擇歲修 ID
        </div>

        <div v-else>
          <!-- 統計卡片 -->
          <div class="grid grid-cols-7 gap-2 mb-4">
            <div class="bg-slate-900/60 rounded p-2 text-center">
              <div class="text-xl font-bold text-slate-200">{{ macListStats.total }}</div>
              <div class="text-xs text-slate-400">總數</div>
            </div>
            <div class="bg-slate-900/60 rounded p-2 text-center">
              <div class="text-xl font-bold text-green-400">{{ macListStats.detected || 0 }}</div>
              <div class="text-xs text-slate-400">已偵測</div>
            </div>
            <div class="bg-slate-900/60 rounded p-2 text-center">
              <div class="text-xl font-bold text-red-400">{{ macListStats.mismatch || 0 }}</div>
              <div class="text-xs text-slate-400">不匹配</div>
            </div>
            <div class="bg-slate-900/60 rounded p-2 text-center">
              <div class="text-xl font-bold text-slate-500">{{ macListStats.not_detected || 0 }}</div>
              <div class="text-xs text-slate-400">未偵測</div>
            </div>
            <div class="bg-slate-900/60 rounded p-2 text-center">
              <div class="text-xl font-bold text-slate-600">{{ macListStats.not_checked || 0 }}</div>
              <div class="text-xs text-slate-400">未檢查</div>
            </div>
            <div class="bg-slate-900/60 rounded p-2 text-center">
              <div class="text-xl font-bold text-cyan-400">{{ macListStats.categorized }}</div>
              <div class="text-xs text-slate-400">已分類</div>
            </div>
            <div class="bg-slate-900/60 rounded p-2 text-center">
              <div class="text-xl font-bold text-amber-400">{{ macListStats.uncategorized }}</div>
              <div class="text-xs text-slate-400">未分類</div>
            </div>
          </div>

          <!-- 搜尋框 -->
          <div class="mb-3">
            <input
              v-model="macSearch"
              type="text"
              placeholder="搜尋 MAC、IP 或備註..."
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="debouncedLoadMacList"
            />
          </div>

          <!-- 篩選器和批量操作 -->
          <div class="flex justify-between items-center mb-3">
            <div class="flex gap-3">
              <select v-model="macFilterStatus" @change="loadMacList" class="px-3 py-1.5 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm">
                <option value="all">全部狀態</option>
                <option value="detected">🟢 已偵測</option>
                <option value="mismatch">🔴 不匹配</option>
                <option value="not_detected">⚪ 未偵測</option>
                <option value="not_checked">⚙️ 未檢查</option>
              </select>
              <select v-model="macFilterCategory" @change="loadMacList" class="px-3 py-1.5 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm">
                <option value="all">全部分類</option>
                <option value="uncategorized">未分類</option>
                <option v-for="cat in categories" :key="cat.id" :value="String(cat.id)">{{ cat.name }}</option>
              </select>
              <button @click="exportMacCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition">
                📤 匯出 CSV
              </button>
            </div>
            <!-- 批量操作 -->
            <div v-if="selectedMacs.length > 0" class="flex items-center gap-2">
              <span class="text-sm text-slate-400">已選 {{ selectedMacs.length }} 筆</span>
              <button @click="openBatchCategory" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-sm rounded transition">
                📁 批量分類
              </button>
              <button v-if="userCanWrite" @click="batchDeleteMacs" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded transition">
                🗑️ 批量刪除
              </button>
              <button @click="clearSelection" class="px-2 py-1.5 text-slate-400 hover:text-white text-sm">
                ✕ 清除
              </button>
            </div>
          </div>

          <!-- Client 列表 -->
          <div ref="clientScrollContainer" class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="selectAll" @change="toggleSelectAll" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">MAC 地址</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">IP 地址</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">Tenant</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">偵測狀態</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">分類</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="mac in macList" :key="mac.id" class="hover:bg-slate-700/50 transition" :class="{ 'bg-cyan-900/20': selectedMacs.includes(mac.id) }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="mac.id" v-model="selectedMacs" class="rounded border-slate-500" />
                  </td>
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs">{{ mac.mac_address }}</td>
                  <td class="px-3 py-2 font-mono text-slate-300 text-xs">{{ mac.ip_address }}</td>
                  <td class="px-3 py-2">
                    <span class="px-1.5 py-0.5 bg-purple-600/30 text-purple-300 rounded text-xs">{{ mac.tenant_group || 'F18' }}</span>
                  </td>
                  <td class="px-3 py-2">
                    <span v-if="mac.detection_status === 'detected'" class="text-green-400 text-xs">🟢 已偵測</span>
                    <span v-else-if="mac.detection_status === 'mismatch'" class="text-red-400 text-xs">🔴 不匹配</span>
                    <span v-else-if="mac.detection_status === 'not_detected'" class="text-slate-400 text-xs">⚪ 未偵測</span>
                    <span v-else class="text-slate-500 text-xs">⚙️ 未檢查</span>
                  </td>
                  <td class="px-3 py-2">
                    <span v-if="mac.category_name" class="px-2 py-0.5 bg-cyan-600/30 text-cyan-300 rounded text-xs">{{ mac.category_name }}</span>
                    <span v-else class="text-slate-500 text-xs">-</span>
                  </td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ mac.description || '-' }}</td>
                  <td class="px-3 py-2 text-xs whitespace-nowrap">
                    <button v-if="userCanWrite" @click="editClient(mac)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button v-if="userCanWrite" @click="openSetCategory(mac)" class="text-slate-400 hover:text-slate-300 mr-2">分類</button>
                    <button v-if="userCanWrite" @click="deleteMac(mac)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="macList.length === 0">
                  <td colspan="8" class="px-4 py-8 text-center text-slate-500">
                    尚無 Client 資料，請匯入 CSV 或手動新增
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 提示 -->
          <p class="text-xs text-slate-500 mt-2">
            💡 CSV 格式：mac_address,ip_address,tenant_group,description,category（tenant_group: F18/F6/AP/F14/F12，description 和 category 選填，多分類用分號分隔如 "EQP;AMHS"）
          </p>
        </div>
      </div>

      <!-- 設備清單 Tab (歲修特定) -->
      <div v-if="activeTab === 'devices'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h3 class="text-white font-semibold">設備清單與對應</h3>
          <div class="flex gap-2 items-center">
            <button @click="downloadDeviceTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded transition">
              📄 下載範本
            </button>
            <label v-if="userCanWrite" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importDeviceList" />
            </label>
            <button v-if="userCanWrite" @click="showAddDeviceModal = true" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition">
              ➕ 新增設備
            </button>
          </div>
        </div>

        <div v-if="!selectedMaintenanceId" class="text-center py-8 text-slate-400">
          請先在頂部選擇歲修 ID
        </div>

        <div v-else>
          <!-- 統計卡片 -->
          <div class="grid grid-cols-5 gap-3 mb-4">
            <div class="bg-slate-900/60 rounded p-3 text-center">
              <div class="text-2xl font-bold text-slate-200">{{ deviceStats.total }}</div>
              <div class="text-xs text-slate-400">總對應數</div>
            </div>
            <div class="bg-slate-900/60 rounded p-3 text-center">
              <div class="text-2xl font-bold text-cyan-400">{{ deviceStats.replaced || 0 }}</div>
              <div class="text-xs text-slate-400">更換設備</div>
            </div>
            <div class="bg-slate-900/60 rounded p-3 text-center">
              <div class="text-2xl font-bold text-amber-400">{{ deviceStats.same_device || 0 }}</div>
              <div class="text-xs text-slate-400">不更換</div>
            </div>
            <div class="bg-slate-900/60 rounded p-3 text-center">
              <div class="text-2xl font-bold text-green-400">{{ deviceStats.reachable || 0 }}</div>
              <div class="text-xs text-slate-400">可達</div>
            </div>
            <div class="bg-slate-900/60 rounded p-3 text-center">
              <div class="text-2xl font-bold" :class="deviceStats.reachable_rate >= 80 ? 'text-green-400' : deviceStats.reachable_rate >= 50 ? 'text-amber-400' : 'text-red-400'">
                {{ deviceStats.reachable_rate }}%
              </div>
              <div class="text-xs text-slate-400">可達率</div>
            </div>
          </div>

          <!-- 搜尋和篩選 -->
          <div class="flex gap-3 mb-3">
            <input
              v-model="deviceSearch"
              type="text"
              placeholder="搜尋 hostname、IP 或備註..."
              class="flex-1 px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="debouncedLoadDeviceList"
            />
            <select v-model="deviceFilterReachable" @change="loadDeviceList" class="px-3 py-1.5 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm">
              <option value="">全部狀態</option>
              <option value="old_true">🟢 舊設備可達</option>
              <option value="old_false">🔴 舊設備不可達</option>
              <option value="new_true">🟢 新設備可達</option>
              <option value="new_false">🔴 新設備不可達</option>
              <option value="any_true">✓ 任一可達</option>
              <option value="any_false">✗ 任一不可達</option>
            </select>
            <button @click="exportDeviceCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition">
              📤 匯出 CSV
            </button>
          </div>

          <!-- 批量操作 -->
          <div v-if="selectedDevices.length > 0" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded border border-cyan-700">
            <span class="text-sm text-cyan-300">已選 {{ selectedDevices.length }} 筆</span>
            <button v-if="userCanWrite" @click="batchDeleteDevices" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded transition">
              🗑️ 批量刪除
            </button>
            <button @click="clearDeviceSelection" class="px-2 py-1 text-slate-400 hover:text-white text-sm">
              ✕ 清除選擇
            </button>
          </div>

          <!-- 設備列表 -->
          <div ref="deviceScrollContainer" class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="deviceSelectAll" @change="toggleDeviceSelectAll" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase" colspan="3">舊設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase" colspan="3">新設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">Tenant</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">同埠</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">換機</th>
                  <th class="px-3 py-2 text-center text-xs font-medium text-slate-400 uppercase" colspan="2">可達性</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
                <tr class="bg-slate-900/40">
                  <th class="px-2 py-1"></th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">Hostname</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">IP</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">Device Type</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">Hostname</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">IP</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">Device Type</th>
                  <th class="px-2 py-1"></th>
                  <th class="px-2 py-1"></th>
                  <th class="px-2 py-1"></th>
                  <th class="px-2 py-1 text-center text-xs text-red-400">舊</th>
                  <th class="px-2 py-1 text-center text-xs text-green-400">新</th>
                  <th class="px-2 py-1"></th>
                  <th class="px-2 py-1"></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="device in deviceList" :key="device.id" class="hover:bg-slate-700/50 transition" :class="{ 'bg-cyan-900/20': selectedDevices.includes(device.id), 'bg-amber-900/10': device.old_hostname === device.new_hostname }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="device.id" v-model="selectedDevices" class="rounded border-slate-500" />
                  </td>
                  <td class="px-2 py-2 font-mono text-red-300 text-xs">{{ device.old_hostname }}</td>
                  <td class="px-2 py-2 font-mono text-slate-400 text-xs">{{ device.old_ip_address }}</td>
                  <td class="px-2 py-2 text-slate-400 text-xs">{{ device.old_vendor }}</td>
                  <td class="px-2 py-2 font-mono text-green-300 text-xs">{{ device.new_hostname }}</td>
                  <td class="px-2 py-2 font-mono text-slate-400 text-xs">{{ device.new_ip_address }}</td>
                  <td class="px-2 py-2 text-slate-400 text-xs">{{ device.new_vendor }}</td>
                  <td class="px-2 py-2">
                    <span class="px-1.5 py-0.5 bg-purple-600/30 text-purple-300 rounded text-xs">{{ device.tenant_group || 'F18' }}</span>
                  </td>
                  <td class="px-2 py-2">
                    <span :class="device.use_same_port ? 'text-green-400' : 'text-slate-500'" class="text-xs">
                      {{ device.use_same_port ? '✓' : '✗' }}
                    </span>
                  </td>
                  <td class="px-2 py-2">
                    <span :class="device.is_replaced ? 'text-orange-400' : 'text-slate-500'" class="text-xs">
                      {{ device.is_replaced ? '是' : '否' }}
                    </span>
                  </td>
                  <td class="px-2 py-2 text-center">
                    <span v-if="device.old_is_reachable === true" class="text-green-400 text-xs">🟢</span>
                    <span v-else-if="device.old_is_reachable === false" class="text-red-400 text-xs">🔴</span>
                    <span v-else class="text-slate-500 text-xs">⚪</span>
                  </td>
                  <td class="px-2 py-2 text-center">
                    <span v-if="device.is_reachable === true" class="text-green-400 text-xs">🟢</span>
                    <span v-else-if="device.is_reachable === false" class="text-red-400 text-xs">🔴</span>
                    <span v-else class="text-slate-500 text-xs">⚪</span>
                  </td>
                  <td class="px-2 py-2 text-slate-400 text-xs max-w-[150px] truncate" :title="device.description">
                    {{ device.description || '-' }}
                  </td>
                  <td class="px-2 py-2 text-xs whitespace-nowrap">
                    <button v-if="userCanWrite" @click="editDeviceItem(device)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button v-if="userCanWrite" @click="deleteDeviceItem(device)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="deviceList.length === 0">
                  <td colspan="14" class="px-4 py-8 text-center text-slate-500">
                    尚無設備資料，請匯入 CSV 或手動新增
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 提示 -->
          <p class="text-xs text-slate-500 mt-2">
            💡 CSV 格式：old_hostname,old_ip_address,old_vendor,new_hostname,new_ip_address,new_vendor,is_replaced,use_same_port,tenant_group,description（is_replaced: TRUE/FALSE；若不更換設備填 FALSE，新舊填同一台；tenant_group: F18/F6/AP/F14/F12）
          </p>
        </div>
      </div>

      <!-- ARP 來源 Tab (歲修特定) -->
      <div v-if="activeTab === 'arp'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h3 class="text-white font-semibold">ARP 來源設備</h3>
          <div class="flex gap-2">
            <button @click="downloadArpTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded transition">
              📄 下載範本
            </button>
            <label v-if="userCanWrite" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importArpList" />
            </label>
            <button @click="openAddArp" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition">
              ➕ 新增來源
            </button>
          </div>
        </div>

        <div v-if="!selectedMaintenanceId" class="text-center py-8 text-slate-400">
          請先在頂部選擇歲修 ID
        </div>

        <div v-else>
          <p class="text-sm text-slate-400 mb-3">
            指定從哪些 Router/Gateway 獲取 ARP Table，用於對應 MAC → IP
          </p>

          <!-- 搜尋和操作 -->
          <div class="flex gap-3 mb-3">
            <input
              v-model="arpSearch"
              type="text"
              placeholder="搜尋設備或備註..."
              class="flex-1 px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="loadArpList"
            />
            <button @click="exportArpCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition">
              📤 匯出 CSV
            </button>
          </div>

          <!-- 批量操作 -->
          <div v-if="selectedArps.length > 0" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded border border-cyan-700">
            <span class="text-sm text-cyan-300">已選 {{ selectedArps.length }} 筆</span>
            <button v-if="userCanWrite" @click="batchDeleteArps" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded transition">
              🗑️ 批量刪除
            </button>
            <button @click="clearArpSelection" class="px-2 py-1 text-slate-400 hover:text-white text-sm">
              ✕ 清除選擇
            </button>
          </div>

          <div ref="arpScrollContainer" class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="arpSelectAll" @change="toggleArpSelectAll" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">優先級</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="arp in arpSources" :key="arp.id" class="hover:bg-slate-700/50 transition" :class="{ 'bg-cyan-900/20': selectedArps.includes(arp.id) }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="arp.id" v-model="selectedArps" class="rounded border-slate-500" />
                  </td>
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs">{{ arp.hostname }}</td>
                  <td class="px-3 py-2 text-slate-300 text-xs">{{ arp.priority }}</td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ arp.description || '-' }}</td>
                  <td class="px-3 py-2 text-xs whitespace-nowrap">
                    <button v-if="userCanWrite" @click="editArp(arp)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button v-if="userCanWrite" @click="deleteArpSource(arp)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="arpSources.length === 0">
                  <td colspan="5" class="px-4 py-8 text-center text-slate-500">尚無 ARP 來源設備</td>
                </tr>
              </tbody>
            </table>
          </div>

          <p class="text-xs text-slate-500 mt-2">
            💡 CSV 格式：hostname,priority,description（priority 數字越小優先級越高）
          </p>
        </div>
      </div>
    </div>

    <!-- 新增/編輯 ARP 來源 Modal -->
    <div v-if="showAddArpModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="closeArpModal">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-[450px]">
        <h3 class="text-lg font-semibold text-white mb-4">{{ editingArp ? '編輯 ARP 來源' : '新增 ARP 來源' }}</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-slate-400 mb-1">設備 Hostname <span class="text-red-400">*</span></label>
            <input v-model="newArp.hostname" type="text" placeholder="CORE-ROUTER-01" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">優先級</label>
            <input v-model.number="newArp.priority" type="number" min="1" placeholder="100" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
            <p class="text-xs text-slate-500 mt-1">數字越小優先級越高，預設 100</p>
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">備註（選填）</label>
            <input v-model="newArp.description" type="text" placeholder="例如：主要 Gateway" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="closeArpModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">取消</button>
          <button @click="saveArp" :disabled="!newArp.hostname" class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingArp ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 設定分類 Modal（多選） -->
    <div v-if="showSetCategoryModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="showSetCategoryModal = false">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-96">
        <h3 class="text-lg font-semibold text-white mb-4">設定分類（可多選）</h3>
        <p class="text-sm text-slate-400 mb-4">
          MAC: <span class="font-mono text-cyan-300">{{ selectedMacForCategory?.mac_address }}</span>
        </p>
        <div class="space-y-2 max-h-60 overflow-y-auto">
          <label v-for="cat in categories" :key="cat.id" class="flex items-center gap-2 p-2 rounded hover:bg-slate-700 cursor-pointer">
            <input type="checkbox" :value="cat.id" v-model="selectedCategoryIds" class="text-cyan-500 rounded" />
            <span class="text-slate-200">{{ cat.name }}</span>
          </label>
          <p v-if="categories.length === 0" class="text-slate-500 text-sm py-2 text-center">尚無分類，請先至「管理分類」新增</p>
        </div>
        <p class="text-xs text-slate-500 mt-3">不勾選任何分類 = 移除所有分類</p>
        <div class="flex justify-end gap-2 mt-4">
          <button @click="showSetCategoryModal = false" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">
            取消
          </button>
          <button @click="setMacCategory" class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500">
            確定
          </button>
        </div>
      </div>
    </div>

    <!-- 新增/編輯 Client Modal -->
    <div v-if="showAddMacModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="closeClientModal">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-[450px]">
        <h3 class="text-lg font-semibold text-white mb-4">{{ editingClient ? '編輯 Client' : '新增 Client' }}</h3>
        <div class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm text-slate-400 mb-1">MAC 地址 <span class="text-red-400">*</span></label>
              <input
                v-model="newMac.mac_address"
                type="text"
                placeholder="AA:BB:CC:DD:EE:FF"
                :disabled="editingClient"
                :class="[
                  'w-full px-3 py-2 border rounded font-mono uppercase text-sm',
                  editingClient
                    ? 'bg-slate-800 border-slate-700 text-slate-400 cursor-not-allowed'
                    : 'bg-slate-900 border-slate-600 text-slate-200 placeholder-slate-500'
                ]"
              />
              <p v-if="editingClient" class="text-xs text-slate-500 mt-1">MAC 地址不可修改</p>
            </div>
            <div>
              <label class="block text-sm text-slate-400 mb-1">IP 地址 <span class="text-red-400">*</span></label>
              <input
                v-model="newMac.ip_address"
                type="text"
                placeholder="192.168.1.100"
                class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 font-mono text-sm"
              />
            </div>
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">Tenant Group <span class="text-red-400">*</span></label>
            <select
              v-model="newMac.tenant_group"
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm"
            >
              <option v-for="tg in tenantGroupOptions" :key="tg" :value="tg">{{ tg }}</option>
            </select>
            <p class="text-xs text-slate-500 mt-1">用於 GNMS Ping 偵測 Client 可達性</p>
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">備註（選填）</label>
            <input
              v-model="newMac.description"
              type="text"
              placeholder="例如：1號機台"
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
            />
          </div>
          <!-- 分類（僅新增模式顯示，編輯請用「分類」按鈕） -->
          <div v-if="!editingClient">
            <label class="block text-sm text-slate-400 mb-1">分類（選填，可多選）</label>
            <div class="bg-slate-900 border border-slate-600 rounded p-2 max-h-32 overflow-y-auto">
              <label v-for="cat in categories" :key="cat.id" class="flex items-center gap-2 py-1 hover:bg-slate-800 rounded px-1 cursor-pointer">
                <input type="checkbox" :value="cat.id" v-model="newMac.categoryIds" class="text-cyan-500 rounded" />
                <span class="text-slate-200 text-sm">{{ cat.name }}</span>
              </label>
              <p v-if="categories.length === 0" class="text-slate-500 text-sm py-1">尚無分類</p>
            </div>
            <p class="text-xs text-slate-500 mt-1">如需新增分類，請至「管理分類」</p>
          </div>
          <p v-else class="text-xs text-slate-500">💡 如需修改分類，請關閉此視窗後點擊「分類」按鈕</p>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="closeClientModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">
            取消
          </button>
          <button @click="saveClient" :disabled="!newMac.mac_address || !newMac.ip_address" class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingClient ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 批量分類 Modal（多選） -->
    <div v-if="showBatchCategoryModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="showBatchCategoryModal = false">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-96">
        <h3 class="text-lg font-semibold text-white mb-4">批量設定分類（可多選）</h3>
        <p class="text-sm text-slate-400 mb-4">
          將 <span class="text-cyan-300 font-bold">{{ selectedMacs.length }}</span> 個 MAC 設定為：
        </p>
        <div class="space-y-2 max-h-60 overflow-y-auto">
          <label v-for="cat in categories" :key="cat.id" class="flex items-center gap-2 p-2 rounded hover:bg-slate-700 cursor-pointer">
            <input type="checkbox" :value="cat.id" v-model="batchCategoryIds" class="text-cyan-500 rounded" />
            <span class="text-slate-200">{{ cat.name }}</span>
          </label>
          <p v-if="categories.length === 0" class="text-slate-500 text-sm py-2 text-center">尚無分類，請先至「管理分類」新增</p>
        </div>
        <p class="text-xs text-slate-500 mt-3">不勾選任何分類 = 移除所有分類</p>
        <div class="flex justify-end gap-2 mt-4">
          <button @click="showBatchCategoryModal = false" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">
            取消
          </button>
          <button @click="applyBatchCategory" class="px-4 py-2 bg-amber-600 text-white rounded hover:bg-amber-500">
            套用
          </button>
        </div>
      </div>
    </div>

    <!-- 新增/編輯設備對應 Modal -->
    <div v-if="showAddDeviceModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="closeDeviceModal">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-[650px]">
        <h3 class="text-lg font-semibold text-white mb-4">{{ editingDevice ? '編輯設備對應' : '新增設備對應' }}</h3>
        <p class="text-sm text-slate-400 mb-4">💡 若設備不更換，請將新舊設備填寫為同一台</p>

        <div class="grid grid-cols-2 gap-6">
          <!-- 舊設備 -->
          <div class="space-y-3">
            <h4 class="text-sm font-medium text-red-400 border-b border-slate-600 pb-1">舊設備 (OLD)</h4>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Hostname <span class="text-red-400">*</span></label>
              <input v-model="newDevice.old_hostname" type="text" placeholder="OLD-SW-001" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">IP 位址 <span class="text-red-400">*</span></label>
              <input v-model="newDevice.old_ip_address" type="text" placeholder="10.1.1.1" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Device Type <span class="text-red-400">*</span></label>
              <select v-model="newDevice.old_vendor" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm">
                <option value="HPE">HPE</option>
                <option value="Cisco-IOS">Cisco-IOS</option>
                <option value="Cisco-NXOS">Cisco-NXOS</option>
              </select>
            </div>
          </div>

          <!-- 新設備 -->
          <div class="space-y-3">
            <h4 class="text-sm font-medium text-green-400 border-b border-slate-600 pb-1">新設備 (NEW)</h4>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Hostname <span class="text-red-400">*</span></label>
              <input v-model="newDevice.new_hostname" type="text" placeholder="NEW-SW-001" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">IP 位址 <span class="text-red-400">*</span></label>
              <input v-model="newDevice.new_ip_address" type="text" placeholder="10.1.1.101" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Device Type <span class="text-red-400">*</span></label>
              <select v-model="newDevice.new_vendor" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm">
                <option value="HPE">HPE</option>
                <option value="Cisco-IOS">Cisco-IOS</option>
                <option value="Cisco-NXOS">Cisco-NXOS</option>
              </select>
            </div>
          </div>
        </div>

        <!-- 對應設定 -->
        <div class="mt-4 pt-4 border-t border-slate-600 space-y-3">
          <div class="flex items-center gap-4">
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="newDevice.use_same_port" class="rounded border-slate-500" />
              <span class="text-slate-300 text-sm">使用相同 Port 對應</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" v-model="newDevice.is_replaced" class="rounded border-slate-500" />
              <span class="text-slate-300 text-sm">會更換設備</span>
            </label>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs text-slate-400 mb-1">Tenant Group <span class="text-red-400">*</span></label>
              <select v-model="newDevice.tenant_group" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm">
                <option v-for="tg in tenantGroupOptions" :key="tg" :value="tg">{{ tg }}</option>
              </select>
              <p class="text-xs text-slate-500 mt-1">用於 GNMS Ping API</p>
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">備註（選填）</label>
              <input v-model="newDevice.description" type="text" placeholder="例如：1F 機房" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
            </div>
          </div>
        </div>

        <div class="flex justify-end gap-2 mt-6">
          <button @click="closeDeviceModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">取消</button>
          <button @click="saveDevice" :disabled="!canAddDevice" class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingDevice ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 分類管理 Modal -->
    <CategoryModal
      v-if="showCategoryModal"
      :categories="categories"
      :maintenance-id="selectedMaintenanceId"
      @close="showCategoryModal = false"
      @refresh="onCategoryRefresh"
    />

    <!-- 通用訊息 Modal -->
    <div v-if="messageModal.show" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-[60]" @click.self="closeMessageModal">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-96">
        <div class="flex items-start gap-3">
          <span v-if="messageModal.type === 'success'" class="text-2xl text-green-400">✓</span>
          <span v-else-if="messageModal.type === 'error'" class="text-2xl text-red-400">✕</span>
          <span v-else class="text-2xl text-blue-400">ℹ</span>
          <div class="flex-1">
            <h3 class="text-lg font-semibold text-white mb-2">{{ messageModal.title || '提示' }}</h3>
            <p class="text-slate-300 whitespace-pre-line">{{ messageModal.message }}</p>
          </div>
        </div>
        <div class="flex justify-end mt-6">
          <button @click="closeMessageModal" class="px-4 py-2 bg-slate-600 text-white rounded hover:bg-slate-500">
            確定
          </button>
        </div>
      </div>
    </div>

    <!-- 通用確認 Modal -->
    <div v-if="confirmModal.show" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-[60]">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-96">
        <div class="flex items-start gap-3">
          <span class="text-2xl text-amber-400">⚠</span>
          <div class="flex-1">
            <h3 class="text-lg font-semibold text-white mb-2">{{ confirmModal.title || '確認' }}</h3>
            <p class="text-slate-300 whitespace-pre-line">{{ confirmModal.message }}</p>
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="confirmModal.show = false; confirmModal.resolve && confirmModal.resolve(false)" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">
            取消
          </button>
          <button @click="handleConfirm" class="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-500">
            確定
          </button>
        </div>
      </div>
    </div>

    <!-- 匯入結果 Modal -->
    <div v-if="importResultModal.show" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-[60]" @click.self="closeImportResultModal">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-[550px] max-h-[80vh] flex flex-col">
        <div class="flex items-start gap-3 mb-4">
          <span class="text-2xl" :class="importResultModal.totalErrors > 0 ? 'text-amber-400' : 'text-green-400'">
            {{ importResultModal.totalErrors > 0 ? '⚠' : '✓' }}
          </span>
          <div class="flex-1">
            <h3 class="text-lg font-semibold text-white">匯入結果</h3>
          </div>
        </div>

        <!-- 統計摘要 -->
        <div class="grid grid-cols-3 gap-3 mb-4">
          <div class="bg-green-900/30 rounded p-3 text-center">
            <div class="text-2xl font-bold text-green-400">{{ importResultModal.imported }}</div>
            <div class="text-xs text-slate-400">成功匯入</div>
          </div>
          <div class="bg-slate-700/50 rounded p-3 text-center">
            <div class="text-2xl font-bold text-slate-400">{{ importResultModal.skipped }}</div>
            <div class="text-xs text-slate-400">略過（重複）</div>
          </div>
          <div class="bg-red-900/30 rounded p-3 text-center">
            <div class="text-2xl font-bold text-red-400">{{ importResultModal.totalErrors }}</div>
            <div class="text-xs text-slate-400">錯誤</div>
          </div>
        </div>

        <!-- 錯誤詳情列表 -->
        <div v-if="importResultModal.errors.length > 0" class="flex-1 min-h-0">
          <div class="flex justify-between items-center mb-2">
            <h4 class="text-sm font-medium text-red-400">❌ 錯誤詳情（共 {{ importResultModal.totalErrors }} 筆）</h4>
            <button @click="downloadErrorReport" class="px-2 py-1 text-xs bg-slate-600 hover:bg-slate-500 text-white rounded transition">
              📥 下載錯誤報告
            </button>
          </div>
          <div class="bg-slate-900/60 border border-slate-600 rounded overflow-y-auto max-h-[300px]">
            <table class="w-full text-sm">
              <thead class="bg-slate-800 sticky top-0">
                <tr>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 w-20">行號</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400">錯誤原因</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="(error, idx) in importResultModal.errors" :key="idx" class="hover:bg-slate-800/50">
                  <td class="px-3 py-2 text-red-400 font-mono">{{ extractRowNumber(error) }}</td>
                  <td class="px-3 py-2 text-slate-300">{{ extractErrorMessage(error) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="text-xs text-slate-500 mt-2">💡 行號對應 CSV 檔案中的原始行數（含標題行為第 1 行）</p>
        </div>

        <!-- 無錯誤時的提示 -->
        <div v-else class="text-center py-4 text-green-400">
          ✓ 所有資料都已成功處理
        </div>

        <div class="flex justify-end mt-4">
          <button @click="closeImportResultModal" class="px-4 py-2 bg-slate-600 text-white rounded hover:bg-slate-500">
            關閉
          </button>
        </div>
      </div>
    </div>

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
import { apiFetch, formatErrorMessage, ErrorType } from '../utils/api.js';
import { canWrite, getAuthHeaders } from '../utils/auth.js';

export default {
  name: 'Devices',
  inject: ['maintenanceId', 'refreshMaintenanceList'],
  components: { CategoryModal },
  data() {
    return {
      loading: false,
      macLoading: false,
      deviceLoading: false,
      activeTab: 'maclist',
      tabs: [
        { id: 'maclist', name: 'Client 清單', icon: '📋', scope: 'maintenance' },
        { id: 'devices', name: '設備清單', icon: '🖥️', scope: 'maintenance' },
        { id: 'arp', name: 'ARP 來源', icon: '🌐', scope: 'maintenance' },
      ],

      // 新設備清單
      deviceList: [],
      deviceStats: { total: 0, by_role: { old: 0, new: 0, unchanged: 0 }, reachable_rate: 0 },
      deviceSearch: '',
      deviceFilterRole: '',
      deviceFilterReachable: '',
      deviceFilterMapping: '',
      deviceSearchTimeout: null,
      selectedDevices: [],
      deviceSelectAll: false,
      batchTestingReachability: false,  // 正在批量測試可達性
      reachabilityInterval: null,  // 自動測試可達性 interval ID (每10秒)

      // Client 清單 (原 MAC 清單)
      macList: [],
      macListStats: {
        total: 0, categorized: 0, uncategorized: 0,
        detected: 0, mismatch: 0, not_detected: 0, not_checked: 0,
      },
      macSearch: '',
      macFilterStatus: 'all',
      macFilterCategory: 'all',
      showAddMacModal: false,
      editingClient: false,  // 區分新增/編輯模式
      editingClientId: null,  // 編輯中的 Client ID
      newMac: {
        mac_address: '', ip_address: '', tenant_group: 'F18',
        description: '', categoryIds: [],
      },
      detecting: false,  // 偵測中狀態
      clientDetectionInterval: null,  // 自動偵測 Client interval ID (每10秒)
      macSearchTimeout: null,
      categories: [],
      showSetCategoryModal: false,
      selectedMacForCategory: null,
      selectedCategoryIds: [],  // 多選分類 IDs
      // 批量選擇
      selectedMacs: [],
      selectAll: false,
      showBatchCategoryModal: false,
      batchCategoryIds: [],  // 多選分類 IDs

      // ARP 來源
      arpLoading: false,
      arpSources: [],
      arpSearch: '',
      selectedArps: [],
      arpSelectAll: false,
      showAddArpModal: false,
      editingArp: null,
      newArp: { hostname: '', priority: 100, description: '' },

      // 分類管理 Modal
      showCategoryModal: false,

      // Modal 控制
      showAddDeviceModal: false,
      editingDevice: false,  // 區分新增/編輯模式
      tenantGroupOptions: ['F18', 'F6', 'AP', 'F14', 'F12'],  // Tenant Group 選項
      newDevice: {
        id: null,
        old_hostname: '', old_ip_address: '', old_vendor: 'HPE',
        new_hostname: '', new_ip_address: '', new_vendor: 'HPE',
        use_same_port: true, is_replaced: false, tenant_group: 'F18', description: ''
      },

      // 通用訊息 Modal
      messageModal: {
        show: false,
        type: 'info',  // info, success, error
        title: '',
        message: '',
      },

      // 通用確認 Modal
      confirmModal: {
        show: false,
        title: '',
        message: '',
        resolve: null,
        onConfirm: null,
      },

      // 匯入結果 Modal
      importResultModal: {
        show: false,
        imported: 0,
        skipped: 0,
        errors: [],
        totalErrors: 0,
      },
    };
  },
  computed: {
    selectedMaintenanceId() {
      return this.maintenanceId;
    },
    userCanWrite() {
      return canWrite.value;
    },
    canAddDevice() {
      return this.newDevice.old_hostname && this.newDevice.old_ip_address && this.newDevice.old_vendor
          && this.newDevice.new_hostname && this.newDevice.new_ip_address && this.newDevice.new_vendor;
    },
  },
  watch: {
    selectedMaintenanceId(newId) {
      // 切換歲修 ID 時停止所有自動測試
      this.stopReachabilityPolling();
      this.stopClientDetectionPolling();
      if (newId) {
        this.loadMaintenanceData();
      }
    },
    activeTab(newTab) {
      // 保存 Tab 狀態到 localStorage
      localStorage.setItem('devices_active_tab', newTab);
      // 根據 Tab 啟動/停止對應的自動測試
      if (newTab === 'devices') {
        this.stopClientDetectionPolling();
        this.startReachabilityPolling();
      } else if (newTab === 'maclist') {
        this.stopReachabilityPolling();
        this.startClientDetectionPolling();
      } else {
        this.stopReachabilityPolling();
        this.stopClientDetectionPolling();
      }
    },
    // 監聽設備列表變化，有設備時啟動自動測試
    'deviceList.length'(newLen) {
      if (newLen > 0 && this.activeTab === 'devices') {
        this.startReachabilityPolling();
      } else if (newLen === 0) {
        this.stopReachabilityPolling();
      }
    },
    // 監聽 Client 列表變化，有 Client 時啟動自動偵測
    'macList.length'(newLen) {
      if (newLen > 0 && this.activeTab === 'maclist') {
        this.startClientDetectionPolling();
      } else if (newLen === 0) {
        this.stopClientDetectionPolling();
      }
    },
  },
  mounted() {
    // 從 localStorage 恢復 Tab 狀態
    const savedTab = localStorage.getItem('devices_active_tab');
    if (savedTab && this.tabs.some(t => t.id === savedTab)) {
      this.activeTab = savedTab;
    }

    if (this.selectedMaintenanceId) {
      this.loadMaintenanceData();
    }
  },
  beforeUnmount() {
    // 清理所有自動測試計時器
    this.stopReachabilityPolling();
    this.stopClientDetectionPolling();
  },
  methods: {
    async loadMaintenanceData() {
      if (!this.selectedMaintenanceId) return;

      this.loading = true;
      try {
        // 載入分類
        await this.loadCategories();

        // 載入 MAC 清單
        await this.loadMacList();
        await this.loadMacStats();

        // 載入設備清單
        await this.loadDeviceList();
        await this.loadDeviceStats();

        // 載入 ARP 來源
        await this.loadArpList();

        // 根據當前 Tab 啟動對應的自動測試
        if (this.activeTab === 'devices' && this.deviceList.length > 0) {
          this.startReachabilityPolling();
        } else if (this.activeTab === 'maclist' && this.macList.length > 0) {
          this.startClientDetectionPolling();
        }
      } catch (e) {
        console.error('載入歲修數據失敗:', e);
      } finally {
        this.loading = false;
      }
    },

    // ========== MAC 清單方法 ==========
    async loadMacList() {
      if (!this.selectedMaintenanceId) return;

      // 保存當前滾動位置
      const scrollContainer = this.$refs.clientScrollContainer;
      const scrollTop = scrollContainer?.scrollTop || 0;

      this.macLoading = true;
      try {
        // 使用 detailed 端點獲取完整資訊
        const params = new URLSearchParams();
        // 清理搜尋輸入後再發送 API（保留空格）
        const cleanSearch = this.sanitizeSearchInput(this.macSearch);
        if (cleanSearch) params.append('search', cleanSearch);
        if (this.macFilterStatus !== 'all') params.append('filter_status', this.macFilterStatus);
        if (this.macFilterCategory !== 'all') params.append('filter_category', this.macFilterCategory);

        let url = `/api/v1/mac-list/${this.selectedMaintenanceId}/detailed`;
        if (params.toString()) url += '?' + params.toString();

        const res = await fetch(url, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          this.macList = await res.json();
        }

        // 恢復滾動位置
        this.$nextTick(() => {
          if (scrollContainer) {
            scrollContainer.scrollTop = scrollTop;
          }
        });
      } catch (e) {
        console.error('載入 MAC 清單失敗:', e);
      } finally {
        this.macLoading = false;
      }
    },

    async loadCategories() {
      if (!this.selectedMaintenanceId) return;

      try {
        const res = await fetch(`/api/v1/categories?maintenance_id=${this.selectedMaintenanceId}`, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          this.categories = await res.json();
        }
      } catch (e) {
        console.error('載入分類失敗:', e);
      }
    },

    async openSetCategory(mac) {
      this.selectedMacForCategory = mac;
      // 查詢該 MAC 目前屬於哪些分類
      this.selectedCategoryIds = [];
      for (const cat of this.categories) {
        try {
          const res = await fetch(`/api/v1/categories/${cat.id}/members`, {
            headers: getAuthHeaders()
          });
          if (res.ok) {
            const members = await res.json();
            if (members.some(m => m.mac_address === mac.mac_address)) {
              this.selectedCategoryIds.push(cat.id);
            }
          }
        } catch (e) {
          console.error('查詢分類成員失敗:', e);
        }
      }
      this.showSetCategoryModal = true;
    },

    async setMacCategory() {
      if (!this.selectedMacForCategory || !this.selectedMaintenanceId) return;

      try {
        const mac = this.selectedMacForCategory.mac_address;
        const newCategoryIds = new Set(this.selectedCategoryIds);

        // 找出目前 MAC 所屬的所有分類
        const currentCategoryIds = new Set();
        for (const cat of this.categories) {
          try {
            const res = await fetch(`/api/v1/categories/${cat.id}/members`, {
              headers: getAuthHeaders()
            });
            if (res.ok) {
              const members = await res.json();
              if (members.some(m => m.mac_address === mac)) {
                currentCategoryIds.add(cat.id);
              }
            }
          } catch {
            // 查詢失敗時忽略，繼續處理其他分類
          }
        }

        // 移除不再選中的分類
        for (const catId of currentCategoryIds) {
          if (!newCategoryIds.has(catId)) {
            await fetch(`/api/v1/categories/${catId}/members/${encodeURIComponent(mac)}`, {
              method: 'DELETE',
              headers: getAuthHeaders()
            });
          }
        }

        // 添加新選中的分類
        for (const catId of newCategoryIds) {
          if (!currentCategoryIds.has(catId)) {
            await fetch(`/api/v1/categories/${catId}/members`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
              body: JSON.stringify({ mac_address: mac }),
            });
          }
        }

        this.showSetCategoryModal = false;
        await this.loadMacList();
        await this.loadMacStats();
        this.showMessage('分類設定成功', 'success');
      } catch (e) {
        console.error('設定分類失敗:', e);
        this.showMessage(e.message || '設定分類失敗', 'error');
      }
    },

    async loadMacStats() {
      if (!this.selectedMaintenanceId) return;

      try {
        const res = await fetch(`/api/v1/mac-list/${this.selectedMaintenanceId}/stats`, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          this.macListStats = await res.json();
        }
      } catch (e) {
        console.error('載入 MAC 統計失敗:', e);
      }
    },

    // 搜尋輸入驗證與清理（不移除空格，因為空格是搜尋語法的一部分）
    sanitizeSearchInput(input) {
      if (!input) return '';
      let sanitized = input;
      // 限制長度（最多 100 字元）
      if (sanitized.length > 100) {
        sanitized = sanitized.substring(0, 100);
      }
      // 只移除危險字元，保留空格
      sanitized = sanitized.replaceAll(/[<>'"\\]/g, '');
      return sanitized;
    },

    debouncedLoadMacList() {
      if (this.macSearchTimeout) {
        clearTimeout(this.macSearchTimeout);
      }
      // 清理搜尋輸入（不修改原值，避免移除用戶正在輸入的空格）
      this.macSearchTimeout = setTimeout(() => {
        this.loadMacList();
      }, 300);
    },

    // CSV 檔案驗證
    validateCsvFile(file) {
      if (!file) return { valid: false, error: '請選擇檔案' };

      // 檢查副檔名
      const fileName = file.name.toLowerCase();
      if (!fileName.endsWith('.csv')) {
        return { valid: false, error: '請上傳 CSV 格式的檔案（.csv）' };
      }

      // 檢查 MIME 類型（某些瀏覽器可能不準確，所以也接受空的）
      const validTypes = ['text/csv', 'application/vnd.ms-excel', 'text/plain', ''];
      if (!validTypes.includes(file.type)) {
        return { valid: false, error: `不支援的檔案類型: ${file.type}` };
      }

      // 檢查檔案大小（最大 10MB）
      const maxSize = 10 * 1024 * 1024;
      if (file.size > maxSize) {
        return { valid: false, error: '檔案大小超過限制（最大 10MB）' };
      }

      return { valid: true };
    },

    downloadMacTemplate() {
      const csv = `mac_address,ip_address,tenant_group,description,category
AA:BB:CC:DD:EE:01,192.168.1.100,F18,單一分類範例,生產機台
AA:BB:CC:DD:EE:02,192.168.1.101,F6,多分類範例(用分號分隔),EQP;AMHS
AA:BB:CC:DD:EE:03,192.168.1.102,AP,無分類範例,`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'client_list_template.csv';
      link.click();
    },

    async importMacList(event) {
      const file = event.target.files[0];
      if (!file || !this.selectedMaintenanceId) {
        event.target.value = '';
        return;
      }

      // 驗證 CSV 檔案
      const validation = this.validateCsvFile(file);
      if (!validation.valid) {
        this.showMessage(validation.error, 'error');
        event.target.value = '';
        return;
      }

      this.macLoading = true;
      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch(`/api/v1/mac-list/${this.selectedMaintenanceId}/import-csv`, {
          method: 'POST',
          body: formData,
          headers: getAuthHeaders()
        });
        const data = await res.json();

        if (res.ok) {
          await this.loadCategories();  // 可能有新分類
          await this.loadMacList();
          await this.loadMacStats();
          // 使用新的匯入結果 Modal 顯示詳細錯誤
          this.importResultModal = {
            show: true,
            imported: data.imported || 0,
            skipped: data.skipped || 0,
            errors: data.errors || [],
            totalErrors: data.total_errors || 0,
          };
        } else {
          this.showMessage(data.detail || '匯入失敗', 'error');
        }
      } catch (e) {
        console.error('MAC 匯入失敗:', e);
        this.showMessage('匯入失敗，請檢查網路連線', 'error');
      } finally {
        this.macLoading = false;
      }

      event.target.value = '';
    },

    async deleteMac(mac) {
      const confirmed = await this.showConfirm(`確定要刪除 ${mac.mac_address}？`, '刪除確認');
      if (!confirmed) return;

      try {
        const res = await fetch(`/api/v1/mac-list/${this.selectedMaintenanceId}/${encodeURIComponent(mac.mac_address)}`, {
          method: 'DELETE',
          headers: getAuthHeaders()
        });
        if (res.ok) {
          await this.loadMacList();
          await this.loadMacStats();
        }
      } catch (e) {
        console.error('刪除 MAC 失敗:', e);
        this.showMessage('刪除失敗', 'error');
      }
    },

    // 編輯 Client（不處理分類，分類請用「分類」按鈕）
    editClient(mac) {
      this.newMac = {
        mac_address: mac.mac_address || '',
        ip_address: mac.ip_address || '',
        tenant_group: mac.tenant_group || 'F18',
        description: mac.description || '',
        categoryIds: [],  // 編輯模式不處理分類
      };
      this.editingClient = true;
      this.editingClientId = mac.id;
      this.showAddMacModal = true;
    },

    // 關閉 Client Modal 並重置狀態
    closeClientModal() {
      this.showAddMacModal = false;
      this.editingClient = false;
      this.editingClientId = null;
      this.newMac = { mac_address: '', ip_address: '', tenant_group: 'F18', description: '', categoryIds: [] };
    },

    // 儲存 Client（新增或編輯）
    async saveClient() {
      if (!this.newMac.mac_address || !this.newMac.ip_address || !this.selectedMaintenanceId) return;

      // 標準化 MAC 格式並去除空白
      const mac = this.newMac.mac_address.trim().toUpperCase().replace(/-/g, ':');
      const ip = this.newMac.ip_address.trim();

      // MAC format validation (只在新增時驗證格式)
      if (!this.editingClient) {
        const macPattern = /^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/;
        if (!macPattern.test(mac)) {
          this.showMessage('MAC 地址格式錯誤，正確格式：XX:XX:XX:XX:XX:XX（XX 為 0-9, A-F）', 'error');
          return;
        }
      }

      // IP format validation
      const ipPattern = /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
      if (!ipPattern.test(ip)) {
        this.showMessage('IP 地址格式錯誤，正確格式：例如 192.168.1.100', 'error');
        return;
      }

      const description = this.newMac.description?.trim() || null;
      const categoryIds = this.newMac.categoryIds || [];
      const tenantGroup = this.newMac.tenant_group || 'F18';

      const isEdit = this.editingClient && this.editingClientId;

      try {
        let res;
        if (isEdit) {
          // 編輯模式：使用 PUT 請求（不處理分類）
          res = await fetch(`/api/v1/mac-list/${this.selectedMaintenanceId}/${this.editingClientId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
            body: JSON.stringify({
              ip_address: ip,
              tenant_group: tenantGroup,
              description: description,
              // 不傳 category，分類請用「分類」按鈕
            }),
          });
        } else {
          // 新增模式：使用 POST 請求
          res = await fetch(`/api/v1/mac-list/${this.selectedMaintenanceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
            body: JSON.stringify({
              mac_address: mac,
              ip_address: ip,
              tenant_group: tenantGroup,
              description: description,
            }),
          });

          // 新增成功後，添加到選中的分類
          if (res.ok && categoryIds.length > 0) {
            for (const catId of categoryIds) {
              await fetch(`/api/v1/categories/${catId}/members`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
                body: JSON.stringify({ mac_address: mac }),
              });
            }
          }
        }

        if (res.ok) {
          const msg = isEdit ? 'Client 更新成功' : 'Client 新增成功';
          this.closeClientModal();
          await this.loadCategories();  // 重新載入分類（可能有新建的）
          await this.loadMacList();
          await this.loadMacStats();
          this.showMessage(msg, 'success');
        } else {
          const err = await res.json();
          this.showMessage(err.detail || (isEdit ? '更新失敗' : '新增失敗'), 'error');
        }
      } catch (e) {
        console.error(isEdit ? '更新 Client 失敗:' : '新增 Client 失敗:', e);
        this.showMessage(isEdit ? '更新失敗' : '新增失敗', 'error');
      }
    },

    // 舊的 addMac 方法保留給其他地方調用（如果有的話）
    async addMac() {
      await this.saveClient();
    },

    // ========== 批量選擇 ==========
    toggleSelectAll() {
      if (this.selectAll) {
        this.selectedMacs = this.macList.map(m => m.id);
      } else {
        this.selectedMacs = [];
      }
    },

    clearSelection() {
      this.selectedMacs = [];
      this.selectAll = false;
    },

    async batchDeleteMacs() {
      if (this.selectedMacs.length === 0) return;

      const confirmed = await this.showConfirm(
        `確定要刪除選中的 ${this.selectedMacs.length} 個 MAC 地址？`,
        '批量刪除確認'
      );
      if (!confirmed) return;

      try {
        // 將選中的 ID 轉換成整數陣列
        const macIds = this.selectedMacs.map(id => parseInt(id, 10));

        const res = await fetch(`/api/v1/mac-list/${this.selectedMaintenanceId}/batch-delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
          body: JSON.stringify({ mac_ids: macIds }),
        });

        if (res.ok) {
          const data = await res.json();
          this.showMessage(`成功刪除 ${data.deleted_count} 個 MAC 地址`, 'success');
          this.clearSelection();
          await this.loadMacList();
          await this.loadMacStats();
        } else {
          this.showMessage('批量刪除失敗', 'error');
        }
      } catch (e) {
        console.error('批量刪除 MAC 失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    exportMacCsv() {
      const params = new URLSearchParams();
      if (this.macSearch) {
        params.append('search', this.macSearch);
      }
      // 偵測狀態篩選
      if (this.macFilterStatus && this.macFilterStatus !== 'all') {
        params.append('filter_status', this.macFilterStatus);
      }
      // 分類篩選
      if (this.macFilterCategory && this.macFilterCategory !== 'all') {
        params.append('filter_category', this.macFilterCategory);
      }
      const url = `/api/v1/mac-list/${this.selectedMaintenanceId}/export-csv?${params}`;
      window.open(url, '_blank');
    },

    openBatchCategory() {
      this.batchCategoryIds = [];
      this.showBatchCategoryModal = true;
    },

    async applyBatchCategory() {
      if (this.selectedMacs.length === 0) return;

      this.loading = true;
      const newCategoryIds = new Set(this.batchCategoryIds);

      try {
        // 將選中的 ID 轉換成 MAC 地址
        const selectedMacObjects = this.macList.filter(m => this.selectedMacs.includes(m.id));

        for (const macObj of selectedMacObjects) {
          const macAddress = macObj.mac_address;

          // 先從所有分類移除該 MAC
          for (const cat of this.categories) {
            try {
              await fetch(`/api/v1/categories/${cat.id}/members/${encodeURIComponent(macAddress)}`, {
                method: 'DELETE',
                headers: getAuthHeaders()
              });
            } catch {
              // 忽略刪除失敗（可能本來就不在該分類）
            }
          }

          // 添加到選中的分類
          for (const catId of newCategoryIds) {
            await fetch(`/api/v1/categories/${catId}/members`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
              body: JSON.stringify({ mac_address: macAddress }),
            });
          }
        }

        const count = this.selectedMacs.length;
        this.showBatchCategoryModal = false;
        this.clearSelection();
        await this.loadMacList();
        await this.loadMacStats();
        this.showMessage(`已成功為 ${count} 個 MAC 設定分類`, 'success');
      } catch (e) {
        console.error('批量分類失敗:', e);
        this.showMessage('批量分類失敗', 'error');
      } finally {
        this.loading = false;
      }
    },

    // 分類更新後的回調（同時刷新 Client 清單）
    async onCategoryRefresh() {
      await this.loadCategories();
      await this.loadMacList();
      await this.loadMacStats();
    },

    // 偵測 Client 狀態（靜默模式）
    async detectClients() {
      if (!this.selectedMaintenanceId || this.detecting) return;

      this.detecting = true;
      try {
        const result = await apiFetch(
          `/api/v1/mac-list/${this.selectedMaintenanceId}/detect`,
          { method: 'POST' },
          60000  // 偵測可能需要較長時間
        );

        if (result.ok) {
          await this.loadMacList();
          await this.loadMacStats();
        }
      } catch (e) {
        console.error('Client 偵測失敗:', e);
      } finally {
        this.detecting = false;
      }
    },

    // 啟動 Client 狀態輪詢（每 10 秒，只讀取不觸發偵測）
    startClientDetectionPolling() {
      // 已經在執行中就跳過
      if (this.clientDetectionInterval) return;
      // 沒有 Client 就跳過
      if (this.macList.length === 0) return;

      // 每 10 秒重新載入狀態（被動輪詢，不主動觸發偵測）
      this.clientDetectionInterval = setInterval(async () => {
        if (!this.detecting) {
          await this.loadMacList();
          await this.loadMacStats();
        }
      }, 10000);
    },

    // 停止 Client 自動偵測
    stopClientDetectionPolling() {
      if (this.clientDetectionInterval) {
        clearInterval(this.clientDetectionInterval);
        this.clientDetectionInterval = null;
      }
    },

    // ========== 設備清單方法 ==========
    async loadDeviceList() {
      if (!this.selectedMaintenanceId) return;

      // 保存當前滾動位置
      const scrollContainer = this.$refs.deviceScrollContainer;
      const scrollTop = scrollContainer?.scrollTop || 0;

      this.deviceLoading = true;
      try {
        const params = new URLSearchParams();
        // 清理搜尋輸入後再發送 API（保留空格）
        const cleanSearch = this.sanitizeSearchInput(this.deviceSearch);
        if (cleanSearch) params.append('search', cleanSearch);
        if (this.deviceFilterRole) params.append('role', this.deviceFilterRole);
        if (this.deviceFilterReachable) {
          params.append('reachability', this.deviceFilterReachable);
        }
        if (this.deviceFilterMapping) {
          params.append('has_mapping', this.deviceFilterMapping);
        }

        let url = `/api/v1/maintenance-devices/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();

        const res = await fetch(url, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          const data = await res.json();
          this.deviceList = data.devices || [];
        }

        // 恢復滾動位置
        this.$nextTick(() => {
          if (scrollContainer) {
            scrollContainer.scrollTop = scrollTop;
          }
        });
      } catch (e) {
        console.error('載入設備清單失敗:', e);
      } finally {
        this.deviceLoading = false;
      }
    },

    async loadDeviceStats() {
      if (!this.selectedMaintenanceId) return;

      try {
        const res = await fetch(`/api/v1/maintenance-devices/${this.selectedMaintenanceId}/stats`, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          this.deviceStats = await res.json();
        }
      } catch (e) {
        console.error('載入設備統計失敗:', e);
      }
    },

    debouncedLoadDeviceList() {
      if (this.deviceSearchTimeout) clearTimeout(this.deviceSearchTimeout);
      // 不修改原值，避免移除用戶正在輸入的空格
      this.deviceSearchTimeout = setTimeout(() => this.loadDeviceList(), 300);
    },

    downloadDeviceTemplate() {
      const csv = `old_hostname,old_ip_address,old_vendor,new_hostname,new_ip_address,new_vendor,is_replaced,use_same_port,tenant_group,description
OLD-SW-001,10.1.1.1,HPE,NEW-SW-001,10.1.1.101,HPE,TRUE,TRUE,F18,1F機房更換
OLD-SW-002,10.1.1.2,Cisco-IOS,NEW-SW-002,10.1.1.102,Cisco-IOS,TRUE,TRUE,F6,2F機房更換
SW-UNCHANGED,10.1.1.200,Cisco-NXOS,SW-UNCHANGED,10.1.1.200,Cisco-NXOS,FALSE,TRUE,AP,不更換設備`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'device_mapping_template.csv';
      link.click();
    },

    async importDeviceList(event) {
      const file = event.target.files[0];
      if (!file || !this.selectedMaintenanceId) {
        event.target.value = '';
        return;
      }

      // 驗證 CSV 檔案
      const validation = this.validateCsvFile(file);
      if (!validation.valid) {
        this.showMessage(validation.error, 'error');
        event.target.value = '';
        return;
      }

      this.deviceLoading = true;
      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch(`/api/v1/maintenance-devices/${this.selectedMaintenanceId}/import-csv`, {
          method: 'POST',
          body: formData,
          headers: getAuthHeaders()
        });
        const data = await res.json();

        if (res.ok) {
          await this.loadDeviceList();
          await this.loadDeviceStats();
          this.showMessage(`新增: ${data.imported} 筆\n更新: ${data.updated} 筆\n錯誤: ${data.total_errors} 筆`, 'success', '匯入完成');
        } else {
          this.showMessage(data.detail || '匯入失敗', 'error');
        }
      } catch (e) {
        console.error('設備匯入失敗:', e);
        this.showMessage('匯入失敗，請檢查網路連線', 'error');
      } finally {
        this.deviceLoading = false;
      }
      event.target.value = '';
    },

    // 關閉設備 Modal 並重置狀態
    closeDeviceModal() {
      this.showAddDeviceModal = false;
      this.editingDevice = false;
      this.newDevice = {
        id: null,
        old_hostname: '', old_ip_address: '', old_vendor: 'HPE',
        new_hostname: '', new_ip_address: '', new_vendor: 'HPE',
        use_same_port: true, is_replaced: false, tenant_group: 'F18', description: ''
      };
    },

    // 儲存設備（新增或編輯）
    async saveDevice() {
      if (!this.canAddDevice || !this.selectedMaintenanceId) return;

      // IP address format validation
      const ipPattern = /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
      const oldIp = this.newDevice.old_ip_address.trim();
      const newIp = this.newDevice.new_ip_address.trim();

      if (!ipPattern.test(oldIp)) {
        this.showMessage('舊設備 IP 位址格式錯誤，正確格式：例如 192.168.1.1', 'error');
        return;
      }

      if (!ipPattern.test(newIp)) {
        this.showMessage('新設備 IP 位址格式錯誤，正確格式：例如 192.168.1.1', 'error');
        return;
      }

      const payload = {
        old_hostname: this.newDevice.old_hostname.trim(),
        old_ip_address: oldIp,
        old_vendor: this.newDevice.old_vendor,
        new_hostname: this.newDevice.new_hostname.trim(),
        new_ip_address: newIp,
        new_vendor: this.newDevice.new_vendor,
        use_same_port: this.newDevice.use_same_port,
        is_replaced: this.newDevice.is_replaced,
        tenant_group: this.newDevice.tenant_group,
        description: this.newDevice.description?.trim() || null,
      };

      const isEdit = this.editingDevice && this.newDevice.id;
      const url = isEdit
        ? `/api/v1/maintenance-devices/${this.selectedMaintenanceId}/${this.newDevice.id}`
        : `/api/v1/maintenance-devices/${this.selectedMaintenanceId}`;
      const method = isEdit ? 'PUT' : 'POST';

      const result = await apiFetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (result.ok) {
        const msg = isEdit ? '設備對應更新成功' : '設備對應新增成功';
        this.closeDeviceModal();
        await this.loadDeviceList();
        await this.loadDeviceStats();
        this.showMessage(msg, 'success');
      } else {
        const errorMsg = formatErrorMessage(result.error);
        if (result.error?.type === ErrorType.VALIDATION) {
          this.showMessage(`資料驗證失敗：${errorMsg}`, 'error');
        } else if (result.error?.type === ErrorType.NETWORK) {
          this.showMessage('網路連線失敗，請檢查連線狀態', 'error');
        } else {
          this.showMessage(errorMsg || (this.editingDevice ? '更新失敗' : '新增失敗'), 'error');
        }
      }
    },

    editDeviceItem(device) {
      // 填入現有資料到表單
      this.newDevice = {
        id: device.id,
        old_hostname: device.old_hostname || '',
        old_ip_address: device.old_ip_address || '',
        old_vendor: device.old_vendor || 'HPE',
        new_hostname: device.new_hostname || '',
        new_ip_address: device.new_ip_address || '',
        new_vendor: device.new_vendor || 'HPE',
        use_same_port: device.use_same_port ?? true,
        is_replaced: device.is_replaced ?? false,
        tenant_group: device.tenant_group || 'F18',
        description: device.description || '',
      };
      this.editingDevice = true;
      this.showAddDeviceModal = true;
    },

    async deleteDeviceItem(device) {
      const confirmed = await this.showConfirm(`確定要刪除設備對應 ${device.old_hostname} → ${device.new_hostname}？`, '刪除確認');
      if (!confirmed) return;

      try {
        const res = await fetch(`/api/v1/maintenance-devices/${this.selectedMaintenanceId}/${device.id}`, {
          method: 'DELETE',
          headers: getAuthHeaders()
        });
        if (res.ok) {
          await this.loadDeviceList();
          await this.loadDeviceStats();
        }
      } catch (e) {
        console.error('刪除設備對應失敗:', e);
        this.showMessage('刪除失敗', 'error');
      }
    },

    // 批量測試所有設備可達性（靜默模式）
    async batchTestReachability() {
      if (this.batchTestingReachability || !this.selectedMaintenanceId || this.deviceList.length === 0) return;

      this.batchTestingReachability = true;
      try {
        const res = await fetch(
          `/api/v1/maintenance-devices/${this.selectedMaintenanceId}/batch-test-reachability`,
          { method: 'POST', headers: getAuthHeaders() }
        );

        if (res.ok) {
          // 重新載入設備列表和統計
          await this.loadDeviceList();
          await this.loadDeviceStats();
        }
      } catch (e) {
        console.error('批量測試可達性失敗:', e);
      } finally {
        this.batchTestingReachability = false;
      }
    },

    // 啟動可達性資料輪詢（每 10 秒讀取後端統計，由 scheduler 採集資料）
    startReachabilityPolling() {
      // 已經在執行中就跳過
      if (this.reachabilityInterval) return;
      // 沒有設備就跳過
      if (this.deviceList.length === 0) return;

      // 立即執行一次（只讀取，不觸發採集）
      this.refreshDeviceData();

      // 每 10 秒刷新一次（只讀取，由 scheduler 採集）
      this.reachabilityInterval = setInterval(() => {
        this.refreshDeviceData();
      }, 10000);
    },

    // 刷新設備資料（只讀取，不觸發採集）
    async refreshDeviceData() {
      if (!this.selectedMaintenanceId || this.deviceList.length === 0) return;
      try {
        await this.loadDeviceList();
        await this.loadDeviceStats();
      } catch (e) {
        console.error('刷新設備資料失敗:', e);
      }
    },

    // 停止可達性自動測試
    stopReachabilityPolling() {
      if (this.reachabilityInterval) {
        clearInterval(this.reachabilityInterval);
        this.reachabilityInterval = null;
      }
    },

    toggleDeviceSelectAll() {
      if (this.deviceSelectAll) {
        this.selectedDevices = this.deviceList.map(d => d.id);
      } else {
        this.selectedDevices = [];
      }
    },

    clearDeviceSelection() {
      this.selectedDevices = [];
      this.deviceSelectAll = false;
    },

    async batchDeleteDevices() {
      if (this.selectedDevices.length === 0) return;

      const confirmed = await this.showConfirm(
        `確定要刪除選中的 ${this.selectedDevices.length} 筆設備對應？`,
        '批量刪除確認'
      );
      if (!confirmed) return;

      try {
        const res = await fetch(`/api/v1/maintenance-devices/${this.selectedMaintenanceId}/batch-delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
          body: JSON.stringify({ device_ids: this.selectedDevices }),
        });

        if (res.ok) {
          const data = await res.json();
          this.showMessage(`成功刪除 ${data.deleted_count} 筆設備對應`, 'success');
          this.clearDeviceSelection();
          await this.loadDeviceList();
          await this.loadDeviceStats();
        } else {
          this.showMessage('批量刪除失敗', 'error');
        }
      } catch (e) {
        console.error('批量刪除設備失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    exportDeviceCsv() {
      const params = new URLSearchParams();
      if (this.deviceSearch) {
        params.append('search', this.deviceSearch);
      }
      if (this.deviceFilterReachable) {
        params.append('reachability', this.deviceFilterReachable);
      }
      const url = `/api/v1/maintenance-devices/${this.selectedMaintenanceId}/export-csv?${params}`;
      window.open(url, '_blank');
    },

    // ========== 通用 Modal 方法 ==========
    showMessage(message, type = 'info', title = '') {
      this.messageModal = {
        show: true,
        type,
        title: title || (type === 'success' ? '成功' : type === 'error' ? '錯誤' : '提示'),
        message,
      };
    },

    closeMessageModal() {
      this.messageModal.show = false;
    },

    showConfirm(message, title = '確認') {
      return new Promise((resolve) => {
        this.confirmModal = {
          show: true,
          title,
          message,
          resolve,
          onConfirm: null,
        };
      });
    },

    handleConfirm() {
      if (this.confirmModal.resolve) {
        this.confirmModal.resolve(true);
      }
      if (this.confirmModal.onConfirm) {
        this.confirmModal.onConfirm();
      }
      this.confirmModal.show = false;
    },

    // ========== 匯入結果 Modal 方法 ==========
    closeImportResultModal() {
      this.importResultModal.show = false;
    },

    // 從錯誤訊息中提取行號（例如 "Row 2: xxx" => "2"）
    extractRowNumber(error) {
      const match = error.match(/^Row\s+(\d+):/);
      return match ? match[1] : '-';
    },

    // 從錯誤訊息中提取錯誤原因（例如 "Row 2: xxx" => "xxx"）
    extractErrorMessage(error) {
      const match = error.match(/^Row\s+\d+:\s*(.+)$/);
      return match ? match[1] : error;
    },

    // 下載錯誤報告為 CSV
    downloadErrorReport() {
      if (this.importResultModal.errors.length === 0) return;

      const lines = ['行號,錯誤原因'];
      for (const error of this.importResultModal.errors) {
        const rowNum = this.extractRowNumber(error);
        const msg = this.extractErrorMessage(error).replaceAll('"', '""');  // CSV 轉義
        lines.push(`${rowNum},"${msg}"`);
      }

      const csv = lines.join('\n');
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `import_errors_${new Date().toISOString().slice(0,10)}.csv`;
      link.click();
    },

    // ========== ARP 來源操作 ==========
    async loadArpList() {
      if (!this.selectedMaintenanceId) return;

      // 保存捲動位置
      const scrollTop = this.$refs.arpScrollContainer?.scrollTop || 0;

      try {
        const params = new URLSearchParams();
        if (this.arpSearch) params.append('search', this.arpSearch);

        let url = `/api/v1/expectations/arp/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();

        const res = await fetch(url, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          const data = await res.json();
          this.arpSources = data.items || [];
          // 恢復捲動位置
          this.$nextTick(() => {
            if (this.$refs.arpScrollContainer) {
              this.$refs.arpScrollContainer.scrollTop = scrollTop;
            }
          });
        }
      } catch (e) {
        console.error('載入 ARP 來源失敗:', e);
      }
    },

    downloadArpTemplate() {
      const csv = `hostname,priority,description
CORE-ROUTER-01,10,主要 Gateway
CORE-ROUTER-02,20,備援 Gateway
DISTRO-SW-01,100,分發層交換機`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'arp_sources_template.csv';
      link.click();
    },

    async importArpList(event) {
      const file = event.target.files[0];
      if (!file || !this.selectedMaintenanceId) {
        event.target.value = '';
        return;
      }

      this.arpLoading = true;
      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch(`/api/v1/expectations/arp/${this.selectedMaintenanceId}/import-csv`, {
          method: 'POST',
          body: formData,
          headers: getAuthHeaders()
        });
        const data = await res.json();

        if (res.ok) {
          await this.loadArpList();
          this.showMessage(`新增: ${data.imported} 筆\n更新: ${data.updated} 筆\n錯誤: ${data.total_errors} 筆`, 'success', '匯入完成');
        } else {
          this.showMessage(data.detail || '匯入失敗', 'error');
        }
      } catch (e) {
        console.error('ARP 來源匯入失敗:', e);
        this.showMessage('匯入失敗，請檢查網路連線', 'error');
      } finally {
        this.arpLoading = false;
      }
      event.target.value = '';
    },

    openAddArp() {
      this.editingArp = null;
      this.newArp = { hostname: '', priority: 100, description: '' };
      this.showAddArpModal = true;
    },

    editArp(arp) {
      this.editingArp = arp;
      this.newArp = {
        id: arp.id,
        hostname: arp.hostname || '',
        priority: arp.priority || 100,
        description: arp.description || '',
      };
      this.showAddArpModal = true;
    },

    closeArpModal() {
      this.showAddArpModal = false;
      this.editingArp = null;
      this.newArp = { hostname: '', priority: 100, description: '' };
    },

    async saveArp() {
      if (!this.newArp.hostname || !this.selectedMaintenanceId) return;

      try {
        let res;
        const payload = {
          hostname: this.newArp.hostname.trim(),
          priority: this.newArp.priority || 100,
          description: this.newArp.description?.trim() || null,
        };

        if (this.editingArp && this.newArp.id) {
          res = await fetch(`/api/v1/expectations/arp/${this.selectedMaintenanceId}/${this.newArp.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
            body: JSON.stringify(payload),
          });
        } else {
          res = await fetch(`/api/v1/expectations/arp/${this.selectedMaintenanceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
            body: JSON.stringify(payload),
          });
        }

        if (res.ok) {
          const msg = this.editingArp ? 'ARP 來源更新成功' : 'ARP 來源新增成功';
          this.closeArpModal();
          await this.loadArpList();
          this.showMessage(msg, 'success');
        } else {
          const err = await res.json();
          this.showMessage(err.detail || (this.editingArp ? '更新失敗' : '新增失敗'), 'error');
        }
      } catch (e) {
        console.error('儲存 ARP 來源失敗:', e);
        this.showMessage('儲存失敗', 'error');
      }
    },

    async deleteArpSource(arp) {
      const confirmed = await this.showConfirm(`確定要刪除 ARP 來源 ${arp.hostname}？`, '刪除確認');
      if (!confirmed) return;

      try {
        const res = await fetch(`/api/v1/expectations/arp/${this.selectedMaintenanceId}/${arp.id}`, {
          method: 'DELETE',
          headers: getAuthHeaders()
        });
        if (res.ok) {
          await this.loadArpList();
          this.showMessage('刪除成功', 'success');
        }
      } catch (e) {
        console.error('刪除 ARP 來源失敗:', e);
        this.showMessage('刪除失敗', 'error');
      }
    },

    toggleArpSelectAll() {
      if (this.arpSelectAll) {
        this.selectedArps = this.arpSources.map(a => a.id);
      } else {
        this.selectedArps = [];
      }
    },

    clearArpSelection() {
      this.selectedArps = [];
      this.arpSelectAll = false;
    },

    async batchDeleteArps() {
      if (this.selectedArps.length === 0) return;

      const confirmed = await this.showConfirm(
        `確定要刪除選中的 ${this.selectedArps.length} 筆 ARP 來源？`,
        '批量刪除確認'
      );
      if (!confirmed) return;

      try {
        const res = await fetch(`/api/v1/expectations/arp/${this.selectedMaintenanceId}/batch-delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
          body: JSON.stringify({ item_ids: this.selectedArps }),
        });

        if (res.ok) {
          const data = await res.json();
          this.showMessage(`成功刪除 ${data.deleted_count} 筆 ARP 來源`, 'success');
          this.clearArpSelection();
          await this.loadArpList();
        } else {
          this.showMessage('批量刪除失敗', 'error');
        }
      } catch (e) {
        console.error('批量刪除 ARP 來源失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    exportArpCsv() {
      const params = new URLSearchParams();
      if (this.arpSearch) {
        params.append('search', this.arpSearch);
      }
      const url = `/api/v1/expectations/arp/${this.selectedMaintenanceId}/export-csv?${params}`;
      window.open(url, '_blank');
    },
  },
};
</script>
