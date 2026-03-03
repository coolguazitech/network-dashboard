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
    <div class="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-600/40 p-4">
      <!-- Client 清單 Tab (歲修特定) -->
      <div v-if="activeTab === 'maclist'" class="space-y-4">
        <div class="flex justify-between items-center">
          <div class="flex items-center gap-2">
            <h3 class="text-white font-semibold">Client 清單</h3>
            <div class="relative group/info">
              <svg class="w-[18px] h-[18px] text-slate-500 group-hover/info:text-amber-400 transition cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div class="absolute left-0 top-full mt-2 w-80 px-4 py-3 bg-amber-50 border border-amber-300 rounded-lg shadow-lg text-sm text-amber-900 leading-relaxed opacity-0 invisible group-hover/info:opacity-100 group-hover/info:visible transition-all duration-200 z-50 pointer-events-none"
                style="filter: drop-shadow(0 2px 8px rgba(217, 160, 0, 0.2));"
              >
                <div class="absolute left-4 -top-[6px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-300"></div>
                <div class="absolute left-4 -top-[5px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-50"></div>
                <p class="mb-1 font-semibold">Client 清單說明</p>
                <p>管理歲修範圍內的 Client（MAC/IP），匯入後可在「案件管理」頁面同步為案件，系統會自動追蹤 Ping 可達狀態。</p>
                <p class="mt-2 font-medium">CSV 匯入格式：</p>
                <p class="font-mono text-xs mt-0.5">mac_address, ip_address, tenant_group, description, default_assignee</p>
                <p class="text-xs mt-0.5">未指定負責人則預設為系統管理員</p>
              </div>
            </div>
          </div>
          <div class="flex gap-2">
            <button @click="downloadMacTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded-lg transition">
              📄 下載範本
            </button>
            <label v-if="userCanWrite" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded-lg transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importMacList" />
            </label>
            <button v-if="userCanWrite" @click="showAddMacModal = true" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded-lg transition">
              ➕ 新增 Client
            </button>
          </div>
        </div>

        <div v-if="!selectedMaintenanceId" class="text-center py-8 text-slate-400">
          請先在頂部選擇歲修 ID
        </div>

        <div v-else>
          <!-- 統計 -->
          <div class="mb-4">
            <span class="text-sm text-slate-400">共 <span class="text-slate-200 font-bold">{{ macListStats.total }}</span> 筆</span>
          </div>

          <!-- 搜尋和匯出 -->
          <div class="flex gap-3 mb-3">
            <input
              v-model="macSearch"
              type="text"
              placeholder="搜尋 MAC、IP 或備註..."
              class="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              @input="debouncedLoadMacList"
            />
            <button @click="exportMacCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition">
              📤 匯出 CSV
            </button>
          </div>

          <!-- 批量操作 -->
          <div v-if="selectedMacs.length > 0" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded-xl border border-cyan-700/40">
            <span class="text-sm text-cyan-300">已選 {{ selectedMacs.length }} 筆</span>
            <button v-if="userCanWrite" @click="batchDeleteMacs" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded-lg transition">
              🗑️ 批量刪除
            </button>
            <button @click="clearSelection" class="px-2 py-1.5 text-slate-400 hover:text-white text-sm">
              ✕ 清除
            </button>
          </div>

          <!-- Client 列表 -->
          <div ref="clientScrollContainer" class="overflow-x-auto max-h-[600px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="isAllMacSelected" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">MAC 地址</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">IP 地址</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">Tenant</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">預設負責人</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="(mac, index) in macList" :key="mac.id" class="hover:bg-slate-700/50 transition row-stagger" :class="{ 'bg-cyan-900/20': selectedMacs.includes(mac.id) }" :style="{ animationDelay: index * 30 + 'ms' }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="mac.id" v-model="selectedMacs" class="rounded border-slate-500" />
                  </td>
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs">{{ mac.mac_address }}</td>
                  <td class="px-3 py-2 font-mono text-slate-300 text-xs">
                    <span
                      class="inline-block rounded-full mr-3 align-middle" style="width: 11px; height: 11px"
                      :class="mac.last_ping_reachable === true
                        ? 'ping-dot-green ping-glow-green'
                        : mac.last_ping_reachable === false
                          ? 'ping-dot-red ping-glow-red animate-pulse'
                          : 'bg-slate-600'"
                    ></span>{{ mac.ip_address }}</td>
                  <td class="px-3 py-2">
                    <span class="px-1.5 py-0.5 bg-purple-600/30 text-purple-300 rounded text-xs">{{ mac.tenant_group || 'F18' }}</span>
                  </td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ mac.description || '-' }}</td>
                  <td class="px-3 py-2 text-slate-300 text-xs">{{ mac.default_assignee || '-' }}</td>
                  <td class="px-3 py-2 text-xs whitespace-nowrap">
                    <button v-if="userCanWrite" @click="editClient(mac)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button v-if="userCanWrite" @click="deleteMac(mac)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="macList.length === 0">
                  <td colspan="7" class="px-4 py-8 text-center text-slate-500">
                    尚無 Client 資料，請匯入 CSV 或手動新增
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

        </div>
      </div>

      <!-- 設備清單 Tab (歲修特定) -->
      <div v-if="activeTab === 'devices'" class="space-y-4">
        <div class="flex justify-between items-center">
          <div class="flex items-center gap-2">
            <h3 class="text-white font-semibold">設備清單與對應</h3>
            <div class="relative group/info">
              <svg class="w-[18px] h-[18px] text-slate-500 group-hover/info:text-amber-400 transition cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div class="absolute left-0 top-full mt-2 w-80 px-4 py-3 bg-amber-50 border border-amber-300 rounded-lg shadow-lg text-sm text-amber-900 leading-relaxed opacity-0 invisible group-hover/info:opacity-100 group-hover/info:visible transition-all duration-200 z-50 pointer-events-none"
                style="filter: drop-shadow(0 2px 8px rgba(217, 160, 0, 0.2));"
              >
                <div class="absolute left-4 -top-[6px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-300"></div>
                <div class="absolute left-4 -top-[5px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-50"></div>
                <p class="mb-1 font-semibold">設備清單說明</p>
                <p>管理歲修範圍內的新舊設備對應關係。新設備用於各項指標驗收（Transceiver、Version、Uplink 等），舊設備用於資料比對參考。</p>
                <p class="mt-2 font-medium">CSV 匯入格式：</p>
                <p class="font-mono text-xs mt-0.5">old_hostname, old_ip_address, old_vendor, new_hostname, new_ip_address, new_vendor, tenant_group, description</p>
                <p class="text-xs mt-0.5">舊/新設備各三欄需同時填寫或同時留空，至少填一側</p>
              </div>
            </div>
          </div>
          <div class="flex gap-2 items-center">
            <button @click="downloadDeviceTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded-lg transition">
              📄 下載範本
            </button>
            <label v-if="userCanWrite" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded-lg transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importDeviceList" />
            </label>
            <button v-if="userCanWrite" @click="showAddDeviceModal = true" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded-lg transition">
              ➕ 新增設備
            </button>
          </div>
        </div>

        <div v-if="!selectedMaintenanceId" class="text-center py-8 text-slate-400">
          請先在頂部選擇歲修 ID
        </div>

        <div v-else>
          <!-- 統計卡片 -->
          <div class="grid grid-cols-3 gap-3 mb-4">
            <div class="bg-slate-900/60 rounded-xl p-3 text-center card-stagger" style="animation-delay: 0ms">
              <div class="text-2xl font-bold text-slate-200">{{ deviceStats.total || 0 }}</div>
              <div class="text-xs text-slate-400">全部設備</div>
            </div>
            <div class="bg-slate-900/60 rounded-xl p-3 text-center card-stagger" style="animation-delay: 80ms">
              <div class="text-2xl font-bold text-amber-400">{{ deviceStats.old_count || 0 }}</div>
              <div class="text-xs text-slate-400 mb-1">舊設備</div>
              <div class="flex justify-center gap-3 text-xs">
                <span class="text-green-400">可達 {{ deviceStats.old_reachable || 0 }}</span>
                <span class="text-red-300">不可達 {{ deviceStats.old_unreachable || 0 }}</span>
                <span v-if="deviceStats.old_unchecked" class="text-slate-500">未檢測 {{ deviceStats.old_unchecked }}</span>
              </div>
            </div>
            <div class="bg-slate-900/60 rounded-xl p-3 text-center card-stagger" style="animation-delay: 160ms">
              <div class="text-2xl font-bold text-cyan-400">{{ deviceStats.new_count || 0 }}</div>
              <div class="text-xs text-slate-400 mb-1">新設備</div>
              <div class="flex justify-center gap-3 text-xs">
                <span class="text-green-400">可達 {{ deviceStats.new_reachable || 0 }}</span>
                <span class="text-red-300">不可達 {{ deviceStats.new_unreachable || 0 }}</span>
                <span v-if="deviceStats.new_unchecked" class="text-slate-500">未檢測 {{ deviceStats.new_unchecked }}</span>
              </div>
            </div>
          </div>

          <!-- 搜尋和篩選 -->
          <div class="flex gap-3 mb-3">
            <input
              v-model="deviceSearch"
              type="text"
              placeholder="搜尋 hostname、IP 或備註..."
              class="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              @input="debouncedLoadDeviceList"
            />
            <button @click="exportDeviceCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition">
              📤 匯出 CSV
            </button>
          </div>

          <!-- 批量操作 -->
          <div v-if="selectedDevices.length > 0" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded-xl border border-cyan-700/40">
            <span class="text-sm text-cyan-300">已選 {{ selectedDevices.length }} 筆</span>
            <button v-if="userCanWrite" @click="batchDeleteDevices" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded-lg transition">
              🗑️ 批量刪除
            </button>
            <button @click="clearDeviceSelection" class="px-2 py-1 text-slate-400 hover:text-white text-sm">
              ✕ 清除選擇
            </button>
          </div>

          <!-- 設備列表 -->
          <div ref="deviceScrollContainer" class="overflow-x-auto max-h-[600px] overflow-y-auto">
            <table class="min-w-full text-sm table-fixed">
              <colgroup>
                <col class="w-[40px]" />
                <col class="w-[22%]" />
                <col class="w-[120px]" />
                <col class="w-[22%]" />
                <col class="w-[120px]" />
                <col class="w-[60px]" />
                <col />
                <col class="w-[90px]" />
              </colgroup>
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="isAllDeviceSelected" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase" colspan="2">舊設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase" colspan="2">新設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">Tenant</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
                <tr class="bg-slate-900/40">
                  <th class="px-2 py-1"></th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">Hostname</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">IP</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">Hostname</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">IP</th>
                  <th class="px-2 py-1"></th>
                  <th class="px-2 py-1"></th>
                  <th class="px-2 py-1"></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="(device, index) in deviceList" :key="device.id" class="hover:bg-slate-700/50 transition row-stagger" :class="{ 'bg-cyan-900/20': selectedDevices.includes(device.id) }" :style="{ animationDelay: index * 30 + 'ms' }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="device.id" v-model="selectedDevices" class="rounded border-slate-500" />
                  </td>
                  <td class="px-2 py-2 font-mono text-slate-200 text-xs break-all leading-snug">{{ device.old_hostname || '-' }}</td>
                  <td class="px-2 py-2 font-mono text-slate-400 text-xs whitespace-nowrap">
                    <span
                      v-if="device.old_hostname"
                      class="inline-block rounded-full mr-3 align-middle" style="width: 11px; height: 11px"
                      :class="getReachability(device.old_hostname) === true
                        ? 'ping-dot-green ping-glow-green'
                        : getReachability(device.old_hostname) === false
                          ? 'ping-dot-red ping-glow-red animate-pulse'
                          : 'bg-slate-600'"
                    ></span>{{ device.old_ip_address || '-' }}</td>
                  <td class="px-2 py-2 font-mono text-slate-200 text-xs break-all leading-snug">{{ device.new_hostname || '-' }}</td>
                  <td class="px-2 py-2 font-mono text-slate-400 text-xs whitespace-nowrap">
                    <span
                      v-if="device.new_hostname"
                      class="inline-block rounded-full mr-3 align-middle" style="width: 11px; height: 11px"
                      :class="getReachability(device.new_hostname) === true
                        ? 'ping-dot-green ping-glow-green'
                        : getReachability(device.new_hostname) === false
                          ? 'ping-dot-red ping-glow-red animate-pulse'
                          : 'bg-slate-600'"
                    ></span>{{ device.new_ip_address || '-' }}</td>
                  <td class="px-2 py-2">
                    <span class="px-1.5 py-0.5 bg-purple-600/30 text-purple-300 rounded text-xs">{{ device.tenant_group || 'F18' }}</span>
                  </td>
                  <td class="px-2 py-2 text-slate-400 text-xs truncate" :title="device.description">
                    {{ device.description || '-' }}
                  </td>
                  <td class="px-2 py-2 text-xs whitespace-nowrap">
                    <button v-if="userCanWrite" @click="editDeviceItem(device)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button v-if="userCanWrite" @click="deleteDeviceItem(device)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="deviceList.length === 0">
                  <td colspan="8" class="px-4 py-8 text-center text-slate-500">
                    尚無設備資料，請匯入 CSV 或手動新增
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

        </div>
      </div>
    </div>

    <!-- 新增/編輯 Client Modal -->
    <Transition name="modal">
    <div v-if="showAddMacModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" @mousedown.self="closeClientModal">
      <div class="modal-content bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-[450px]">
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
                  'w-full px-3 py-2 border rounded-lg font-mono uppercase text-sm',
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
                class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 font-mono text-sm"
              />
            </div>
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">Tenant Group <span class="text-red-400">*</span></label>
            <select
              v-model="newMac.tenant_group"
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 text-sm"
            >
              <option v-for="tg in tenantGroupOptions" :key="tg" :value="tg">{{ tg }}</option>
            </select>
            <p class="text-xs text-slate-500 mt-1">Tenant 群組分類</p>
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">備註（選填）</label>
            <input
              v-model="newMac.description"
              type="text"
              placeholder="例如：1號機台"
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm"
            />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">預設負責人（選填）</label>
            <select
              v-model="newMac.default_assignee"
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 text-sm"
            >
              <option value="">不指定（預設為系統管理員）</option>
              <option v-for="name in filteredDisplayNames" :key="name" :value="name">{{ name }}</option>
            </select>
            <p class="text-xs text-slate-500 mt-1">案件開啟時預設指派給誰</p>
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="closeClientModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded-lg">
            取消
          </button>
          <button @click="saveClient" :disabled="!newMac.mac_address || !newMac.ip_address" class="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingClient ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>
    </Transition>

    <!-- 新增/編輯設備對應 Modal -->
    <Transition name="modal">
    <div v-if="showAddDeviceModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" @mousedown.self="closeDeviceModal">
      <div class="modal-content bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-[650px]">
        <h3 class="text-lg font-semibold text-white mb-4">{{ editingDevice ? '編輯設備對應' : '新增設備對應' }}</h3>
        <p class="text-sm text-slate-400 mb-4">💡 至少需填寫一側，該側需填寫完整設備資訊（Hostname、IP、Device Type）</p>

        <div class="grid grid-cols-2 gap-6">
          <!-- 舊設備 -->
          <div class="space-y-3">
            <h4 class="text-sm font-medium text-red-400 border-b border-slate-600 pb-1">舊設備 (OLD) <span class="text-slate-500 font-normal">- 選填</span></h4>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Hostname</label>
              <input v-model="newDevice.old_hostname" type="text" placeholder="OLD-SW-001" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">IP 位址</label>
              <input v-model="newDevice.old_ip_address" type="text" placeholder="10.1.1.1" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Device Type</label>
              <select v-model="newDevice.old_vendor" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 text-sm">
                <option value="">-- 不選 --</option>
                <option value="HPE">HPE</option>
                <option value="Cisco-IOS">Cisco-IOS</option>
                <option value="Cisco-NXOS">Cisco-NXOS</option>
              </select>
            </div>
          </div>

          <!-- 新設備 -->
          <div class="space-y-3">
            <h4 class="text-sm font-medium text-green-400 border-b border-slate-600 pb-1">新設備 (NEW) <span class="text-slate-500 font-normal">- 選填</span></h4>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Hostname</label>
              <input v-model="newDevice.new_hostname" type="text" placeholder="NEW-SW-001" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">IP 位址</label>
              <input v-model="newDevice.new_ip_address" type="text" placeholder="10.1.1.101" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">Device Type</label>
              <select v-model="newDevice.new_vendor" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 text-sm">
                <option value="">-- 不選 --</option>
                <option value="HPE">HPE</option>
                <option value="Cisco-IOS">Cisco-IOS</option>
                <option value="Cisco-NXOS">Cisco-NXOS</option>
              </select>
            </div>
          </div>
        </div>

        <!-- 其他設定 -->
        <div class="mt-4 pt-4 border-t border-slate-600 space-y-3">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-xs text-slate-400 mb-1">Tenant Group <span class="text-red-400">*</span></label>
              <select v-model="newDevice.tenant_group" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 text-sm">
                <option v-for="tg in tenantGroupOptions" :key="tg" :value="tg">{{ tg }}</option>
              </select>
              <p class="text-xs text-slate-500 mt-1">用於 GNMS Ping API</p>
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">備註（選填）</label>
              <input v-model="newDevice.description" type="text" placeholder="例如：1F 機房" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
            </div>
          </div>
        </div>

        <div class="flex justify-end gap-2 mt-6">
          <button @click="closeDeviceModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded-lg">取消</button>
          <button @click="saveDevice" :disabled="!canAddDevice" class="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingDevice ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>
    </Transition>

    <!-- 匯入結果 Modal -->
    <Transition name="modal">
    <div v-if="importResultModal.show" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[60] p-4" @mousedown.self="closeImportResultModal">
      <div class="modal-content bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-[550px] max-h-[80vh] flex flex-col">
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
          <div class="bg-green-900/30 rounded-xl p-3 text-center">
            <div class="text-2xl font-bold text-green-400">{{ importResultModal.imported }}</div>
            <div class="text-xs text-slate-400">成功匯入</div>
          </div>
          <div class="bg-slate-700/50 rounded-xl p-3 text-center">
            <div class="text-2xl font-bold text-slate-400">{{ importResultModal.skipped }}</div>
            <div class="text-xs text-slate-400">{{ importResultModal.middleLabel || '略過（重複）' }}</div>
          </div>
          <div class="bg-red-900/30 rounded-xl p-3 text-center">
            <div class="text-2xl font-bold text-red-400">{{ importResultModal.totalErrors }}</div>
            <div class="text-xs text-slate-400">錯誤</div>
          </div>
        </div>

        <!-- 錯誤詳情列表 -->
        <div v-if="importResultModal.errors.length > 0" class="flex-1 min-h-0">
          <div class="flex justify-between items-center mb-2">
            <h4 class="text-sm font-medium text-red-400">❌ 錯誤詳情（共 {{ importResultModal.totalErrors }} 筆）</h4>
            <button @click="downloadErrorReport" class="px-2 py-1 text-xs bg-slate-600 hover:bg-slate-500 text-white rounded-lg transition">
              📥 下載錯誤報告
            </button>
          </div>
          <div class="bg-slate-900/60 border border-slate-600/40 rounded-xl overflow-y-auto max-h-[300px]">
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
          <button @click="closeImportResultModal" class="px-4 py-2 bg-slate-600 text-white rounded-lg hover:bg-slate-500">
            關閉
          </button>
        </div>
      </div>
    </div>
    </Transition>

    <!-- Loading -->
    <Transition name="modal">
    <div v-if="loading" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
      <div class="modal-content bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-cyan-400 mx-auto mb-2"></div>
        <p class="text-slate-300">載入中...</p>
      </div>
    </div>
    </Transition>
  </div>
</template>

<script>
import api, { downloadFile } from '@/utils/api';
import { canWrite } from '@/utils/auth';
import { useToast } from '@/composables/useToast';

export default {
  name: 'Devices',
  inject: ['maintenanceId', 'refreshMaintenanceList'],
  setup() {
    return useToast();
  },
  data() {
    return {
      loading: false,
      macLoading: false,
      deviceLoading: false,
      activeTab: 'maclist',
      tabs: [
        { id: 'maclist', name: 'Client 清單', icon: '📋', scope: 'maintenance' },
        { id: 'devices', name: '設備清單', icon: '🖥️', scope: 'maintenance' },
      ],

      // 新設備清單
      deviceList: [],
      deviceStats: {
        total: 0, old_count: 0, new_count: 0,
        old_reachable: 0, old_unreachable: 0, old_unchecked: 0,
        new_reachable: 0, new_unreachable: 0, new_unchecked: 0,
      },
      deviceSearch: '',
      deviceFilterRole: '',
      deviceFilterMapping: '',
      deviceSearchTimeout: null,
      selectedDevices: [],
      reachabilityInterval: null,  // 自動測試可達性 interval ID (每10秒)
      reachabilityStatus: {},  // hostname -> { is_reachable, last_check_at }
      clientPingInterval: null,  // Client 清單 Ping 狀態輪詢 interval ID (每15秒)

      // Client 清單 (原 MAC 清單)
      macList: [],
      macListStats: { total: 0 },
      macSearch: '',
      showAddMacModal: false,
      editingClient: false,
      editingClientId: null,
      newMac: {
        mac_address: '', ip_address: '', tenant_group: 'F18',
        description: '', default_assignee: '',
      },
      userDisplayNames: [],
      macSearchTimeout: null,
      selectedMacs: [],

      // Modal 控制
      showAddDeviceModal: false,
      editingDevice: false,  // 區分新增/編輯模式
      tenantGroupOptions: ['F18', 'F6', 'AP', 'F14', 'F12'],  // Tenant Group 選項
      newDevice: {
        id: null,
        old_hostname: '', old_ip_address: '', old_vendor: '',
        new_hostname: '', new_ip_address: '', new_vendor: '',
        tenant_group: 'F18', description: ''
      },


      // 匯入結果 Modal
      importResultModal: {
        show: false,
        imported: 0,
        skipped: 0,
        errors: [],
        totalErrors: 0,
        middleLabel: '略過（重複）',
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
    filteredDisplayNames() {
      // 過濾掉「系統管理員」，因為已在預設選項中標示
      return this.userDisplayNames.filter(n => n !== '系統管理員');
    },
    isAllMacSelected: {
      get() { return this.macList.length > 0 && this.selectedMacs.length === this.macList.length; },
      set(val) { this.selectedMacs = val ? this.macList.map(m => m.id) : []; },
    },
    isAllDeviceSelected: {
      get() { return this.deviceList.length > 0 && this.selectedDevices.length === this.deviceList.length; },
      set(val) { this.selectedDevices = val ? this.deviceList.map(d => d.id) : []; },
    },
    canAddDevice() {
      const d = this.newDevice;
      const oldH = d.old_hostname?.trim();
      const oldIp = d.old_ip_address?.trim();
      const oldV = d.old_vendor;
      const newH = d.new_hostname?.trim();
      const newIp = d.new_ip_address?.trim();
      const newV = d.new_vendor;

      const oldFilled = oldH && oldIp && oldV;
      const newFilled = newH && newIp && newV;
      const oldPartial = (oldH || oldIp || oldV) && !oldFilled;
      const newPartial = (newH || newIp || newV) && !newFilled;

      // At least one side fully filled, no partial fills
      return (oldFilled || newFilled) && !oldPartial && !newPartial;
    },
  },
  watch: {
    selectedMaintenanceId(newId) {
      this.stopReachabilityPolling();
      this.stopClientPingPolling();
      if (newId) {
        this.loadMaintenanceData();
      }
    },
    activeTab(newTab) {
      localStorage.setItem('devices_active_tab', newTab);
      if (newTab === 'devices') {
        this.startReachabilityPolling();
        this.stopClientPingPolling();
      } else if (newTab === 'maclist') {
        this.stopReachabilityPolling();
        this.startClientPingPolling();
      } else {
        this.stopReachabilityPolling();
        this.stopClientPingPolling();
      }
    },
    'deviceList.length'(newLen) {
      if (newLen > 0 && this.activeTab === 'devices') {
        this.startReachabilityPolling();
      } else if (newLen === 0) {
        this.stopReachabilityPolling();
      }
    },
  },
  mounted() {
    // 從 localStorage 恢復 Tab 狀態
    const savedTab = localStorage.getItem('devices_active_tab');
    if (savedTab && this.tabs.some(t => t.id === savedTab)) {
      this.activeTab = savedTab;
    }

    this.loadUserDisplayNames();
    if (this.selectedMaintenanceId) {
      this.loadMaintenanceData();
    }
  },
  beforeUnmount() {
    this.stopReachabilityPolling();
    this.stopClientPingPolling();
    clearTimeout(this.macSearchTimeout);
    clearTimeout(this.deviceSearchTimeout);
  },
  methods: {
    async loadMaintenanceData() {
      if (!this.selectedMaintenanceId) return;

      this.loading = true;
      try {
        // 載入 MAC 清單
        await this.loadMacList();
        await this.loadMacStats();

        // 載入設備清單
        await this.loadDeviceList();
        await this.loadDeviceStats();
        await this.loadReachabilityStatus();

        if (this.activeTab === 'devices' && this.deviceList.length > 0) {
          this.startReachabilityPolling();
        } else if (this.activeTab === 'maclist' && this.macList.length > 0) {
          this.startClientPingPolling();
        }
      } catch (e) {
        console.error('載入歲修數據失敗:', e);
        this.showMessage('載入歲修數據失敗', 'error');
      } finally {
        this.loading = false;
      }
    },

    async loadUserDisplayNames() {
      try {
        const { data } = await api.get('/users/display-names');
        this.userDisplayNames = data;
      } catch (e) {
        console.error('載入使用者列表失敗:', e);
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
        const params = new URLSearchParams();
        const cleanSearch = this.sanitizeSearchInput(this.macSearch);
        if (cleanSearch) params.append('search', cleanSearch);

        let url = `/mac-list/${this.selectedMaintenanceId}/detailed`;
        if (params.toString()) url += '?' + params.toString();

        const { data } = await api.get(url);
        this.macList = data;

        // 恢復滾動位置
        this.$nextTick(() => {
          if (scrollContainer) {
            scrollContainer.scrollTop = scrollTop;
          }
        });
      } catch (e) {
        console.error('載入 MAC 清單失敗:', e);
        this.showMessage('載入 MAC 清單失敗', 'error');
      } finally {
        this.macLoading = false;
      }
    },

    async loadMacStats() {
      if (!this.selectedMaintenanceId) return;

      try {
        const { data } = await api.get(`/mac-list/${this.selectedMaintenanceId}/stats`);
        this.macListStats = data;
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
      const csv = `mac_address,ip_address,tenant_group,description,default_assignee
AA:BB:CC:DD:EE:01,192.168.1.100,F18,1號機台,系統管理員
AA:BB:CC:DD:EE:02,192.168.1.101,F6,2號機台,
AA:BB:CC:DD:EE:03,192.168.1.102,AP,,`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'client_list_template.csv';
      link.click();
      URL.revokeObjectURL(link.href);
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
        const { data } = await api.post(
          `/mac-list/${this.selectedMaintenanceId}/import-csv`,
          formData,
          { headers: { 'Content-Type': 'multipart/form-data' } },
        );
        await this.loadMacList();
        await this.loadMacStats();
        // 使用新的匯入結果 Modal 顯示詳細錯誤
        this.importResultModal = {
          show: true,
          imported: data.imported || 0,
          skipped: data.skipped || 0,
          errors: data.errors || [],
          totalErrors: data.total_errors || 0,
          middleLabel: '略過（重複）',
        };
      } catch (e) {
        console.error('MAC 匯入失敗:', e);
        this.showMessage(e.response?.data?.detail || '匯入失敗，請檢查網路連線', 'error');
      } finally {
        this.macLoading = false;
      }

      event.target.value = '';
    },

    async deleteMac(mac) {
      const confirmed = await this.showConfirm(`確定要刪除 ${mac.mac_address}？`, '刪除確認');
      if (!confirmed) return;

      try {
        await api.delete(`/mac-list/${this.selectedMaintenanceId}/${encodeURIComponent(mac.mac_address)}`);
        await this.loadMacList();
        await this.loadMacStats();
      } catch (e) {
        console.error('刪除 MAC 失敗:', e);
        this.showMessage('刪除失敗', 'error');
      }
    },

    // 編輯 Client
    editClient(mac) {
      this.newMac = {
        mac_address: mac.mac_address || '',
        ip_address: mac.ip_address || '',
        tenant_group: mac.tenant_group || 'F18',
        description: mac.description || '',
        default_assignee: mac.default_assignee || '',
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
      this.newMac = { mac_address: '', ip_address: '', tenant_group: 'F18', description: '', default_assignee: '' };
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
      const tenantGroup = this.newMac.tenant_group || 'F18';
      const defaultAssignee = this.newMac.default_assignee?.trim() || null;

      const isEdit = this.editingClient && this.editingClientId;

      try {
        if (isEdit) {
          // 編輯模式：使用 PUT 請求
          await api.put(`/mac-list/${this.selectedMaintenanceId}/${this.editingClientId}`, {
            ip_address: ip,
            tenant_group: tenantGroup,
            description: description,
            default_assignee: defaultAssignee,
          });
        } else {
          // 新增模式：使用 POST 請求
          await api.post(`/mac-list/${this.selectedMaintenanceId}`, {
            mac_address: mac,
            ip_address: ip,
            tenant_group: tenantGroup,
            description: description,
            default_assignee: defaultAssignee,
          });
        }

        const msg = isEdit ? 'Client 更新成功' : 'Client 新增成功';
        this.closeClientModal();
        await this.loadMacList();
        await this.loadMacStats();
        this.showMessage(msg, 'success');
      } catch (e) {
        console.error(isEdit ? '更新 Client 失敗:' : '新增 Client 失敗:', e);
        this.showMessage(e.response?.data?.detail || (isEdit ? '更新失敗' : '新增失敗'), 'error');
      }
    },

    // 舊的 addMac 方法保留給其他地方調用（如果有的話）
    async addMac() {
      await this.saveClient();
    },

    // ========== 批量選擇 ==========
    clearSelection() {
      this.selectedMacs = [];
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

        const { data } = await api.post(`/mac-list/${this.selectedMaintenanceId}/batch-delete`, { mac_ids: macIds });
        this.showMessage(`成功刪除 ${data.deleted_count} 個 MAC 地址`, 'success');
        this.clearSelection();
        await this.loadMacList();
        await this.loadMacStats();
      } catch (e) {
        console.error('批量刪除 MAC 失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    async exportMacCsv() {
      const params = new URLSearchParams();
      if (this.macSearch) {
        params.append('search', this.sanitizeSearchInput(this.macSearch));
      }
      await downloadFile(
        `/mac-list/${this.selectedMaintenanceId}/export-csv?${params}`,
        `mac_list_${this.selectedMaintenanceId}.csv`,
      );
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
        if (this.deviceFilterMapping) {
          params.append('has_mapping', this.deviceFilterMapping);
        }

        let url = `/maintenance-devices/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();

        const { data } = await api.get(url);
        this.deviceList = data.devices || [];

        // 恢復滾動位置
        this.$nextTick(() => {
          if (scrollContainer) {
            scrollContainer.scrollTop = scrollTop;
          }
        });
      } catch (e) {
        console.error('載入設備清單失敗:', e);
        this.showMessage('載入設備清單失敗', 'error');
      } finally {
        this.deviceLoading = false;
      }
    },

    async loadDeviceStats() {
      if (!this.selectedMaintenanceId) return;

      try {
        const { data } = await api.get(`/maintenance-devices/${this.selectedMaintenanceId}/stats`);
        this.deviceStats = data;
      } catch (e) {
        console.error('載入設備統計失敗:', e);
      }
    },

    async loadReachabilityStatus() {
      if (!this.selectedMaintenanceId) return;
      try {
        const { data } = await api.get(`/maintenance-devices/${this.selectedMaintenanceId}/reachability-status`);
        this.reachabilityStatus = data.devices || {};
      } catch (e) {
        console.error('載入可達性狀態失敗:', e);
      }
    },

    getReachability(hostname) {
      if (!hostname) return null;
      const status = this.reachabilityStatus[hostname];
      return status ? status.is_reachable : null;
    },

    debouncedLoadDeviceList() {
      if (this.deviceSearchTimeout) clearTimeout(this.deviceSearchTimeout);
      // 不修改原值，避免移除用戶正在輸入的空格
      this.deviceSearchTimeout = setTimeout(() => this.loadDeviceList(), 300);
    },

    downloadDeviceTemplate() {
      const csv = `old_hostname,old_ip_address,old_vendor,new_hostname,new_ip_address,new_vendor,tenant_group,description
OLD-SW-001,10.1.1.1,HPE,NEW-SW-001,10.1.1.101,HPE,F18,新舊設備都填
,,,,NEW-SW-003,10.1.1.103,Cisco-IOS,F6,只填新設備
OLD-SW-004,10.1.1.4,Cisco-NXOS,,,,,只填舊設備`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'device_mapping_template.csv';
      link.click();
      URL.revokeObjectURL(link.href);
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
        const { data } = await api.post(
          `/maintenance-devices/${this.selectedMaintenanceId}/import-csv`,
          formData,
          { headers: { 'Content-Type': 'multipart/form-data' } },
        );
        await this.loadDeviceList();
        await this.loadDeviceStats();
        // 使用匯入結果 Modal 顯示詳細結果
        this.importResultModal = {
          show: true,
          imported: data.imported || 0,
          skipped: data.updated || 0,
          errors: data.errors || [],
          totalErrors: data.total_errors || 0,
          middleLabel: '更新',
        };
      } catch (e) {
        console.error('設備匯入失敗:', e);
        this.showMessage(e.response?.data?.detail || '匯入失敗，請檢查網路連線', 'error');
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
        old_hostname: '', old_ip_address: '', old_vendor: '',
        new_hostname: '', new_ip_address: '', new_vendor: '',
        tenant_group: 'F18', description: ''
      };
    },

    // 儲存設備（新增或編輯）
    async saveDevice() {
      if (!this.canAddDevice || !this.selectedMaintenanceId) return;

      const ipPattern = /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
      const d = this.newDevice;

      const oldIp = d.old_ip_address?.trim() || '';
      const newIp = d.new_ip_address?.trim() || '';

      // Validate old IP only if old side is filled
      if (oldIp && !ipPattern.test(oldIp)) {
        this.showMessage('舊設備 IP 位址格式錯誤，正確格式：例如 192.168.1.1', 'error');
        return;
      }

      // Validate new IP only if new side is filled
      if (newIp && !ipPattern.test(newIp)) {
        this.showMessage('新設備 IP 位址格式錯誤，正確格式：例如 192.168.1.1', 'error');
        return;
      }

      const payload = {
        old_hostname: d.old_hostname?.trim() || null,
        old_ip_address: oldIp || null,
        old_vendor: d.old_vendor || null,
        new_hostname: d.new_hostname?.trim() || null,
        new_ip_address: newIp || null,
        new_vendor: d.new_vendor || null,
        tenant_group: d.tenant_group,
        description: d.description?.trim() || null,
      };

      const isEdit = this.editingDevice && d.id;
      const url = isEdit
        ? `/maintenance-devices/${this.selectedMaintenanceId}/${d.id}`
        : `/maintenance-devices/${this.selectedMaintenanceId}`;
      const method = isEdit ? 'PUT' : 'POST';

      try {
        const apiMethod = method === 'PUT' ? api.put : api.post;
        await apiMethod(url, payload);

        const msg = isEdit ? '設備對應更新成功' : '設備對應新增成功';
        this.closeDeviceModal();
        await this.loadDeviceList();
        await this.loadDeviceStats();
        this.showMessage(msg, 'success');
      } catch (e) {
        const detail = e.response?.data?.detail;
        const status = e.response?.status;
        if (status === 400 || status === 422) {
          this.showMessage(`資料驗證失敗：${detail || '請檢查輸入'}`, 'error');
        } else if (!e.response) {
          this.showMessage('網路連線失敗，請檢查連線狀態', 'error');
        } else {
          this.showMessage(detail || (this.editingDevice ? '更新失敗' : '新增失敗'), 'error');
        }
      }
    },

    editDeviceItem(device) {
      // 填入現有資料到表單
      this.newDevice = {
        id: device.id,
        old_hostname: device.old_hostname || '',
        old_ip_address: device.old_ip_address || '',
        old_vendor: device.old_vendor || '',
        new_hostname: device.new_hostname || '',
        new_ip_address: device.new_ip_address || '',
        new_vendor: device.new_vendor || '',
        tenant_group: device.tenant_group || 'F18',
        description: device.description || '',
      };
      this.editingDevice = true;
      this.showAddDeviceModal = true;
    },

    async deleteDeviceItem(device) {
      const oldName = device.old_hostname || '-';
      const newName = device.new_hostname || '-';
      const confirmed = await this.showConfirm(`確定要刪除設備對應 ${oldName} → ${newName}？`, '刪除確認');
      if (!confirmed) return;

      try {
        await api.delete(`/maintenance-devices/${this.selectedMaintenanceId}/${device.id}`);
        await this.loadDeviceList();
        await this.loadDeviceStats();
      } catch (e) {
        console.error('刪除設備對應失敗:', e);
        this.showMessage('刪除失敗', 'error');
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
        await this.loadReachabilityStatus();
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

    // 啟動 Client 清單 Ping 狀態輪詢（每 15 秒）
    startClientPingPolling() {
      if (this.clientPingInterval) return;
      if (this.macList.length === 0) return;

      this.clientPingInterval = setInterval(() => {
        this.loadMacList();
      }, 15000);
    },

    // 停止 Client 清單 Ping 狀態輪詢
    stopClientPingPolling() {
      if (this.clientPingInterval) {
        clearInterval(this.clientPingInterval);
        this.clientPingInterval = null;
      }
    },

    clearDeviceSelection() {
      this.selectedDevices = [];
    },

    async batchDeleteDevices() {
      if (this.selectedDevices.length === 0) return;

      const confirmed = await this.showConfirm(
        `確定要刪除選中的 ${this.selectedDevices.length} 筆設備對應？`,
        '批量刪除確認'
      );
      if (!confirmed) return;

      try {
        const { data } = await api.post(`/maintenance-devices/${this.selectedMaintenanceId}/batch-delete`, {
          device_ids: this.selectedDevices,
        });
        this.showMessage(`成功刪除 ${data.deleted_count} 筆設備對應`, 'success');
        this.clearDeviceSelection();
        await this.loadDeviceList();
        await this.loadDeviceStats();
      } catch (e) {
        console.error('批量刪除設備失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    async exportDeviceCsv() {
      const params = new URLSearchParams();
      if (this.deviceSearch) {
        params.append('search', this.sanitizeSearchInput(this.deviceSearch));
      }
      await downloadFile(
        `/maintenance-devices/${this.selectedMaintenanceId}/export-csv?${params}`,
        `devices_${this.selectedMaintenanceId}.csv`,
      );
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
  },
};
</script>
