<template>
  <div class="px-3 py-3">
    <!-- 頁面標題 -->
    <div class="flex justify-between items-center mb-3">
      <div>
        <h1 class="text-xl font-bold text-white">⚙️ 設備與設定</h1>
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
      <!-- MAC 清單 Tab (歲修特定) -->
      <div v-if="activeTab === 'maclist'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h3 class="text-white font-semibold">MAC 清單</h3>
          <div class="flex gap-2">
            <button @click="showCategoryModal = true" class="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white text-sm rounded transition">
              🏷️ 管理分類
            </button>
            <button @click="downloadMacTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded transition">
              📄 下載範本
            </button>
            <label class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importMacList" />
            </label>
            <button @click="showAddMacModal = true" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition">
              ➕ 新增 MAC
            </button>
          </div>
        </div>
        
        <div v-if="!selectedMaintenanceId" class="text-center py-8 text-slate-400">
          請先在頂部選擇歲修 ID
        </div>
        
        <div v-else>
          <!-- 統計卡片 -->
          <div class="grid grid-cols-3 gap-3 mb-4">
            <div class="bg-slate-900/60 rounded p-3 text-center">
              <div class="text-2xl font-bold text-slate-200">{{ macListStats.total }}</div>
              <div class="text-xs text-slate-400">總數</div>
            </div>
            <div class="bg-slate-900/60 rounded p-3 text-center">
              <div class="text-2xl font-bold text-cyan-400">{{ macListStats.categorized }}</div>
              <div class="text-xs text-slate-400">已分類</div>
            </div>
            <div class="bg-slate-900/60 rounded p-3 text-center">
              <div class="text-2xl font-bold text-amber-400">{{ macListStats.uncategorized }}</div>
              <div class="text-xs text-slate-400">未分類</div>
            </div>
          </div>
          
          <!-- 搜尋框 -->
          <div class="mb-3">
            <input
              v-model="macSearch"
              type="text"
              placeholder="搜尋 MAC 或備註..."
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="debouncedLoadMacList"
            />
          </div>
          
          <!-- 篩選器和批量操作 -->
          <div class="flex justify-between items-center mb-3">
            <div class="flex gap-3">
              <select v-model="macFilterStatus" @change="loadMacList" class="px-3 py-1.5 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm">
                <option value="all">全部狀態</option>
                <option value="detected">✓ 可偵測</option>
                <option value="undetected">✗ 未偵測</option>
              </select>
              <select v-model="macFilterCategory" @change="loadMacList" class="px-3 py-1.5 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm">
                <option value="all">全部分類</option>
                <option value="uncategorized">未分類</option>
                <option v-for="cat in categories" :key="cat.id" :value="String(cat.id)">{{ cat.name }}</option>
              </select>
            </div>
            <!-- 批量操作 -->
            <div v-if="selectedMacs.length > 0" class="flex items-center gap-2">
              <span class="text-sm text-slate-400">已選 {{ selectedMacs.length }} 筆</span>
              <button @click="openBatchCategory" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-sm rounded transition">
                📁 批量分類
              </button>
              <button @click="clearSelection" class="px-2 py-1.5 text-slate-400 hover:text-white text-sm">
                ✕ 清除
              </button>
            </div>
          </div>

          <!-- MAC 列表 -->
          <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="selectAll" @change="toggleSelectAll" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">MAC 地址</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">偵測</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">分類</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="mac in macList" :key="mac.id" class="hover:bg-slate-700/50 transition" :class="{ 'bg-cyan-900/20': selectedMacs.includes(mac.mac_address) }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="mac.mac_address" v-model="selectedMacs" class="rounded border-slate-500" />
                  </td>
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs">{{ mac.mac_address }}</td>
                  <td class="px-3 py-2">
                    <span v-if="mac.is_detected" class="text-green-400 text-xs">✓ 可偵測</span>
                    <span v-else class="text-slate-500 text-xs">✗ 未偵測</span>
                  </td>
                  <td class="px-3 py-2">
                    <span v-if="mac.category_name" class="px-2 py-0.5 bg-cyan-600/30 text-cyan-300 rounded text-xs">{{ mac.category_name }}</span>
                    <span v-else class="text-slate-500 text-xs">-</span>
                  </td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ mac.description || '-' }}</td>
                  <td class="px-3 py-2 text-xs">
                    <button @click="openSetCategory(mac)" class="text-cyan-400 hover:text-cyan-300 mr-2">分類</button>
                    <button @click="deleteMac(mac)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="macList.length === 0">
                  <td colspan="6" class="px-4 py-8 text-center text-slate-500">
                    尚無 MAC 資料，請匯入 CSV 或手動新增
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          
          <!-- 提示 -->
          <p class="text-xs text-slate-500 mt-2">
            💡 CSV 格式：mac_address,description,category（description 和 category 選填，category 會自動建立）
          </p>
        </div>
      </div>

      <!-- 設備清單 Tab (歲修特定) -->
      <div v-if="activeTab === 'devices'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h3 class="text-white font-semibold">設備清單與對應</h3>
          <div class="flex gap-2">
            <button @click="downloadDeviceTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded transition">
              📄 下載範本
            </button>
            <label class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importDeviceList" />
            </label>
            <button @click="showAddDeviceModal = true" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition">
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
              placeholder="搜尋 hostname 或 IP..."
              class="flex-1 px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="debouncedLoadDeviceList"
            />
            <select v-model="deviceFilterReachable" @change="loadDeviceList" class="px-3 py-1.5 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm">
              <option value="">全部狀態</option>
              <option value="true">✓ 可達</option>
              <option value="false">✗ 不可達</option>
              <option value="null">? 未檢查</option>
            </select>
          </div>
          
          <!-- 批量操作 -->
          <div v-if="selectedDevices.length > 0" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded border border-cyan-700">
            <span class="text-sm text-cyan-300">已選 {{ selectedDevices.length }} 筆</span>
            <button @click="clearDeviceSelection" class="px-2 py-1 text-slate-400 hover:text-white text-sm">
              ✕ 清除選擇
            </button>
          </div>

          <!-- 設備列表 -->
          <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="deviceSelectAll" @change="toggleDeviceSelectAll" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase" colspan="3">舊設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase" colspan="3">新設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">同埠</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">可達</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
                <tr class="bg-slate-900/40">
                  <th class="px-2 py-1"></th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">Hostname</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">IP</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">廠商</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">Hostname</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">IP</th>
                  <th class="px-2 py-1 text-left text-xs text-slate-500">廠商</th>
                  <th class="px-2 py-1"></th>
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
                    <span :class="device.use_same_port ? 'text-green-400' : 'text-slate-500'" class="text-xs">
                      {{ device.use_same_port ? '✓' : '✗' }}
                    </span>
                  </td>
                  <td class="px-2 py-2">
                    <span v-if="device.is_reachable === true" class="text-green-400 text-xs">🟢</span>
                    <span v-else-if="device.is_reachable === false" class="text-red-400 text-xs">🔴</span>
                    <span v-else class="text-slate-500 text-xs">⚪</span>
                  </td>
                  <td class="px-2 py-2 text-xs whitespace-nowrap">
                    <button @click="editDeviceItem(device)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button @click="deleteDeviceItem(device)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="deviceList.length === 0">
                  <td colspan="10" class="px-4 py-8 text-center text-slate-500">
                    尚無設備資料，請匯入 CSV 或手動新增
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          
          <!-- 提示 -->
          <p class="text-xs text-slate-500 mt-2">
            💡 CSV 格式：old_hostname,old_ip_address,old_vendor,new_hostname,new_ip_address,new_vendor,use_same_port,description（若不更換，新舊填同一台）
          </p>
        </div>
      </div>

      <!-- Uplink 期望 Tab (歲修特定) -->
      <div v-if="activeTab === 'uplink'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h3 class="text-white font-semibold">Uplink 期望</h3>
          <div class="flex gap-2">
            <button @click="downloadUplinkTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded transition">
              📄 下載範本
            </button>
            <label class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importUplinkList" />
            </label>
            <button @click="openAddUplink" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition">
              ➕ 新增期望
            </button>
          </div>
        </div>
        
        <div v-if="!selectedMaintenanceId" class="text-center py-8 text-slate-400">
          請先在頂部選擇歲修 ID
        </div>
        
        <div v-else>
          <!-- 搜尋 -->
          <div class="mb-3">
            <input
              v-model="uplinkSearch"
              type="text"
              placeholder="搜尋設備或鄰居..."
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="loadUplinkList"
            />
          </div>
          
          <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">本地介面</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">預期鄰居</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">鄰居介面</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="uplink in uplinkExpectations" :key="uplink.id" class="hover:bg-slate-700/50 transition">
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs">{{ uplink.hostname }}</td>
                  <td class="px-3 py-2 font-mono text-slate-300 text-xs">{{ uplink.local_interface }}</td>
                  <td class="px-3 py-2 font-mono text-cyan-300 text-xs">{{ uplink.expected_neighbor }}</td>
                  <td class="px-3 py-2 font-mono text-slate-300 text-xs">{{ uplink.expected_interface || '-' }}</td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ uplink.description || '-' }}</td>
                  <td class="px-3 py-2 text-xs whitespace-nowrap">
                    <button @click="editUplink(uplink)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button @click="deleteUplink(uplink)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="uplinkExpectations.length === 0">
                  <td colspan="6" class="px-4 py-8 text-center text-slate-500">尚無 Uplink 期望</td>
                </tr>
              </tbody>
            </table>
          </div>
          
          <p class="text-xs text-slate-500 mt-2">
            💡 CSV 格式：hostname,local_interface,expected_neighbor,expected_interface,description
          </p>
        </div>
      </div>

      <!-- 版本期望 Tab (歲修特定) -->
      <div v-if="activeTab === 'version'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h3 class="text-white font-semibold">版本期望</h3>
          <div class="flex gap-2">
            <button @click="downloadVersionTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded transition">
              📄 下載範本
            </button>
            <label class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importVersionList" />
            </label>
            <button @click="openAddVersion" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition">
              ➕ 新增期望
            </button>
          </div>
        </div>
        
        <div v-if="!selectedMaintenanceId" class="text-center py-8 text-slate-400">
          請先在頂部選擇歲修 ID
        </div>
        
        <div v-else>
          <!-- 搜尋 -->
          <div class="mb-3">
            <input
              v-model="versionSearch"
              type="text"
              placeholder="搜尋設備或版本..."
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="loadVersionList"
            />
          </div>
          
          <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">目標版本</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="ver in versionExpectations" :key="ver.id" class="hover:bg-slate-700/50 transition">
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs">{{ ver.hostname }}</td>
                  <td class="px-3 py-2 text-xs">
                    <span v-for="(v, i) in (ver.expected_versions_list || ver.expected_versions.split(';'))" :key="i" class="inline-block px-2 py-0.5 bg-green-600/30 text-green-300 rounded mr-1 mb-1">
                      {{ v }}
                    </span>
                  </td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ ver.description || '-' }}</td>
                  <td class="px-3 py-2 text-xs whitespace-nowrap">
                    <button @click="editVersion(ver)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button @click="deleteVersion(ver)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="versionExpectations.length === 0">
                  <td colspan="4" class="px-4 py-8 text-center text-slate-500">尚無版本期望</td>
                </tr>
              </tbody>
            </table>
          </div>
          
          <p class="text-xs text-slate-500 mt-2">
            💡 CSV 格式：hostname,expected_versions,description（多版本用分號分隔，如 16.10.1;16.10.2）
          </p>
        </div>
      </div>

      <!-- Port Channel 期望 Tab (歲修特定) -->
      <div v-if="activeTab === 'portchannel'" class="space-y-4">
        <div class="flex justify-between items-center">
          <h3 class="text-white font-semibold">Port Channel 期望</h3>
          <div class="flex gap-2">
            <button @click="downloadPortChannelTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded transition">
              📄 下載範本
            </button>
            <label class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importPortChannelList" />
            </label>
            <button @click="openAddPortChannel" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition">
              ➕ 新增期望
            </button>
          </div>
        </div>
        
        <div v-if="!selectedMaintenanceId" class="text-center py-8 text-slate-400">
          請先在頂部選擇歲修 ID
        </div>
        
        <div v-else>
          <!-- 搜尋 -->
          <div class="mb-3">
            <input
              v-model="portChannelSearch"
              type="text"
              placeholder="搜尋設備或 Port-Channel..."
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="loadPortChannelList"
            />
          </div>
          
          <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">Port-Channel</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">成員介面</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="pc in portChannelExpectations" :key="pc.id" class="hover:bg-slate-700/50 transition">
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs">{{ pc.hostname }}</td>
                  <td class="px-3 py-2 font-mono text-cyan-300 text-xs">{{ pc.port_channel }}</td>
                  <td class="px-3 py-2 text-xs">
                    <span v-for="(m, i) in (pc.member_interfaces_list || pc.member_interfaces.split(';'))" :key="i" class="inline-block px-2 py-0.5 bg-purple-600/30 text-purple-300 rounded mr-1 mb-1">
                      {{ m }}
                    </span>
                  </td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ pc.description || '-' }}</td>
                  <td class="px-3 py-2 text-xs whitespace-nowrap">
                    <button @click="editPortChannel(pc)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button @click="deletePortChannel(pc)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="portChannelExpectations.length === 0">
                  <td colspan="5" class="px-4 py-8 text-center text-slate-500">尚無 Port Channel 期望</td>
                </tr>
              </tbody>
            </table>
          </div>
          
          <p class="text-xs text-slate-500 mt-2">
            💡 CSV 格式：hostname,port_channel,member_interfaces,description（成員介面用分號分隔，如 Gi1/0/1;Gi1/0/2）
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
            <label class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded transition cursor-pointer">
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
          
          <!-- 搜尋 -->
          <div class="mb-3">
            <input
              v-model="arpSearch"
              type="text"
              placeholder="搜尋設備或 IP..."
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="loadArpList"
            />
          </div>
          
          <div class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">IP</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">優先級</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="arp in arpSources" :key="arp.id" class="hover:bg-slate-700/50 transition">
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs">{{ arp.hostname }}</td>
                  <td class="px-3 py-2 font-mono text-slate-300 text-xs">{{ arp.ip_address }}</td>
                  <td class="px-3 py-2 text-slate-300 text-xs">{{ arp.priority }}</td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ arp.description || '-' }}</td>
                  <td class="px-3 py-2 text-xs whitespace-nowrap">
                    <button @click="editArp(arp)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button @click="deleteArpSource(arp)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="arpSources.length === 0">
                  <td colspan="5" class="px-4 py-8 text-center text-slate-500">尚無 ARP 來源設備</td>
                </tr>
              </tbody>
            </table>
          </div>
          
          <p class="text-xs text-slate-500 mt-2">
            💡 CSV 格式：hostname,ip_address,priority,description（priority 數字越小優先級越高）
          </p>
        </div>
      </div>
    </div>

    <!-- 設定分類 Modal -->
    <div v-if="showSetCategoryModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="showSetCategoryModal = false">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-96">
        <h3 class="text-lg font-semibold text-white mb-4">設定分類</h3>
        <p class="text-sm text-slate-400 mb-4">
          MAC: <span class="font-mono text-cyan-300">{{ selectedMacForCategory?.mac_address }}</span>
        </p>
        <div class="space-y-3">
          <label class="flex items-center gap-2 p-2 rounded hover:bg-slate-700 cursor-pointer">
            <input type="radio" v-model="selectedCategoryId" value="" class="text-cyan-500" />
            <span class="text-slate-300">無分類</span>
          </label>
          <label v-for="cat in categories" :key="cat.id" class="flex items-center gap-2 p-2 rounded hover:bg-slate-700 cursor-pointer">
            <input type="radio" v-model="selectedCategoryId" :value="String(cat.id)" class="text-cyan-500" />
            <span class="text-slate-200">{{ cat.name }}</span>
          </label>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="showSetCategoryModal = false" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">
            取消
          </button>
          <button @click="setMacCategory" class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500">
            確定
          </button>
        </div>
      </div>
    </div>

    <!-- 新增 MAC Modal -->
    <div v-if="showAddMacModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="showAddMacModal = false">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-96">
        <h3 class="text-lg font-semibold text-white mb-4">新增 MAC</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-slate-400 mb-1">MAC 地址 <span class="text-red-400">*</span></label>
            <input
              v-model="newMac.mac_address"
              type="text"
              placeholder="AA:BB:CC:DD:EE:FF"
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 font-mono uppercase"
            />
            <p class="text-xs text-slate-500 mt-1">格式：XX:XX:XX:XX:XX:XX</p>
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">備註（選填）</label>
            <input
              v-model="newMac.description"
              type="text"
              placeholder="例如：1號機台"
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500"
            />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">分類（選填）</label>
            <select
              v-model="newMac.category"
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200"
            >
              <option value="">無分類</option>
              <option v-for="cat in categories" :key="cat.id" :value="cat.name">{{ cat.name }}</option>
            </select>
            <p class="text-xs text-slate-500 mt-1">可選擇現有分類，或輸入新分類名稱自動建立</p>
            <input
              v-model="newMac.category"
              type="text"
              placeholder="或輸入新分類名稱"
              class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 mt-2"
            />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="showAddMacModal = false" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">
            取消
          </button>
          <button @click="addMac" :disabled="!newMac.mac_address" class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            新增
          </button>
        </div>
      </div>
    </div>

    <!-- 批量分類 Modal -->
    <div v-if="showBatchCategoryModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="showBatchCategoryModal = false">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-96">
        <h3 class="text-lg font-semibold text-white mb-4">批量設定分類</h3>
        <p class="text-sm text-slate-400 mb-4">
          將 <span class="text-cyan-300 font-bold">{{ selectedMacs.length }}</span> 個 MAC 設定為：
        </p>
        <div class="space-y-3 max-h-60 overflow-y-auto">
          <label class="flex items-center gap-2 p-2 rounded hover:bg-slate-700 cursor-pointer">
            <input type="radio" v-model="batchCategoryId" value="" class="text-cyan-500" />
            <span class="text-slate-300">移除分類</span>
          </label>
          <label v-for="cat in categories" :key="cat.id" class="flex items-center gap-2 p-2 rounded hover:bg-slate-700 cursor-pointer">
            <input type="radio" v-model="batchCategoryId" :value="String(cat.id)" class="text-cyan-500" />
            <span class="text-slate-200">{{ cat.name }}</span>
          </label>
        </div>
        <div class="flex justify-end gap-2 mt-6">
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
              <label class="block text-xs text-slate-400 mb-1">廠商 <span class="text-red-400">*</span></label>
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
              <label class="block text-xs text-slate-400 mb-1">廠商 <span class="text-red-400">*</span></label>
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
          </div>
          <div>
            <label class="block text-xs text-slate-400 mb-1">備註（選填）</label>
            <input v-model="newDevice.description" type="text" placeholder="例如：1F 機房" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
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
            <label class="block text-sm text-slate-400 mb-1">IP 位址 <span class="text-red-400">*</span></label>
            <input v-model="newArp.ip_address" type="text" placeholder="10.1.1.1" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
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
          <button @click="saveArp" :disabled="!newArp.hostname || !newArp.ip_address" class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingArp ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 新增/編輯 Uplink 期望 Modal -->
    <div v-if="showAddUplinkModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="closeUplinkModal">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-[500px]">
        <h3 class="text-lg font-semibold text-white mb-4">{{ editingUplink ? '編輯 Uplink 期望' : '新增 Uplink 期望' }}</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-slate-400 mb-1">設備 Hostname <span class="text-red-400">*</span></label>
            <input v-model="newUplink.hostname" type="text" placeholder="SW-001" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">本地介面 <span class="text-red-400">*</span></label>
            <input v-model="newUplink.local_interface" type="text" placeholder="Gi1/0/1" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">預期鄰居 <span class="text-red-400">*</span></label>
            <input v-model="newUplink.expected_neighbor" type="text" placeholder="CORE-SW-01" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">鄰居介面（選填）</label>
            <input v-model="newUplink.expected_interface" type="text" placeholder="Gi1/0/48" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">備註（選填）</label>
            <input v-model="newUplink.description" type="text" placeholder="例如：上聯到核心" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="closeUplinkModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">取消</button>
          <button @click="saveUplink" :disabled="!newUplink.hostname || !newUplink.local_interface || !newUplink.expected_neighbor" class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingUplink ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 新增/編輯版本期望 Modal -->
    <div v-if="showAddVersionModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="closeVersionModal">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-[500px]">
        <h3 class="text-lg font-semibold text-white mb-4">{{ editingVersion ? '編輯版本期望' : '新增版本期望' }}</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-slate-400 mb-1">設備 Hostname <span class="text-red-400">*</span></label>
            <input v-model="newVersion.hostname" type="text" placeholder="SW-001" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">目標版本 <span class="text-red-400">*</span></label>
            <input v-model="newVersion.expected_versions" type="text" placeholder="16.10.1;16.10.2" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
            <p class="text-xs text-slate-500 mt-1">多版本用分號分隔，符合任一版本即可</p>
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">備註（選填）</label>
            <input v-model="newVersion.description" type="text" placeholder="例如：可接受的版本範圍" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="closeVersionModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">取消</button>
          <button @click="saveVersion" :disabled="!newVersion.hostname || !newVersion.expected_versions" class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingVersion ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 新增/編輯 Port Channel 期望 Modal -->
    <div v-if="showAddPortChannelModal" class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50" @click.self="closePortChannelModal">
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl p-6 w-[500px]">
        <h3 class="text-lg font-semibold text-white mb-4">{{ editingPortChannel ? '編輯 Port Channel 期望' : '新增 Port Channel 期望' }}</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-slate-400 mb-1">設備 Hostname <span class="text-red-400">*</span></label>
            <input v-model="newPortChannel.hostname" type="text" placeholder="SW-001" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">Port-Channel 名稱 <span class="text-red-400">*</span></label>
            <input v-model="newPortChannel.port_channel" type="text" placeholder="Po1 或 Port-channel1" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">成員介面 <span class="text-red-400">*</span></label>
            <input v-model="newPortChannel.member_interfaces" type="text" placeholder="Gi1/0/1;Gi1/0/2" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
            <p class="text-xs text-slate-500 mt-1">多個介面用分號分隔</p>
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">備註（選填）</label>
            <input v-model="newPortChannel.description" type="text" placeholder="例如：上聯 LACP" class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="closePortChannelModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">取消</button>
          <button @click="savePortChannel" :disabled="!newPortChannel.hostname || !newPortChannel.port_channel || !newPortChannel.member_interfaces" class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingPortChannel ? '儲存' : '新增' }}
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
  name: 'Settings',
  inject: ['maintenanceId', 'refreshMaintenanceList'],
  components: { CategoryModal },
  data() {
    return {
      loading: false,
      activeTab: 'maclist',
      tabs: [
        { id: 'maclist', name: 'MAC 清單', icon: '📋', scope: 'maintenance' },
        { id: 'devices', name: '設備清單', icon: '🖥️', scope: 'maintenance' },
        { id: 'uplink', name: 'Uplink 期望', icon: '🔗', scope: 'maintenance' },
        { id: 'version', name: '版本期望', icon: '📦', scope: 'maintenance' },
        { id: 'portchannel', name: 'Port Channel 期望', icon: '⛓️', scope: 'maintenance' },
        { id: 'arp', name: 'ARP 來源', icon: '🌐', scope: 'maintenance' },
      ],
      
      // 數據
      maintenanceList: [],
      devices: [],
      deviceMappings: [],
      uplinkExpectations: [],
      versionExpectations: [],
      arpSources: [],
      portChannelExpectations: [],
      
      // Uplink 期望
      uplinkSearch: '',
      
      // 版本期望
      versionSearch: '',
      
      // Port Channel 期望
      portChannelSearch: '',
      
      // ARP 來源
      arpSearch: '',
      
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
      
      // MAC 清單
      macList: [],
      macListStats: { total: 0, categorized: 0, uncategorized: 0 },
      macSearch: '',
      macFilterStatus: 'all',
      macFilterCategory: 'all',
      showAddMacModal: false,
      newMac: { mac_address: '', description: '', category: '' },
      macSearchTimeout: null,
      categories: [],
      showSetCategoryModal: false,
      selectedMacForCategory: null,
      selectedCategoryId: null,
      // 批量選擇
      selectedMacs: [],
      selectAll: false,
      showBatchCategoryModal: false,
      batchCategoryId: '',
      // 分類管理 Modal
      showCategoryModal: false,
      
      // 新增歲修表單
      newMaintenance: { id: '', name: '' },
      showAddMaintenanceModal: false,
      
      // 刪除歲修確認
      showDeleteMaintenanceModal: false,
      deleteTarget: null,
      deleteConfirmInput: '',
      
      // Modal 控制
      showAddDeviceModal: false,
      editingDevice: false,  // 區分新增/編輯模式
      newDevice: { 
        id: null,
        old_hostname: '', old_ip_address: '', old_vendor: 'HPE', 
        new_hostname: '', new_ip_address: '', new_vendor: 'HPE',
        use_same_port: true, description: '' 
      },
      showImportDeviceModal: false,
      showAddMappingModal: false,
      showAddUplinkModal: false,
      showImportUplinkModal: false,
      showAddVersionModal: false,
      showImportVersionModal: false,
      showAddArpModal: false,
      showAddPortChannelModal: false,
      
      // ARP 來源表單
      newArp: { hostname: '', ip_address: '', priority: 100, description: '' },
      editingArp: null,
      
      // Uplink 期望表單
      newUplink: { hostname: '', local_interface: '', expected_neighbor: '', expected_interface: '', description: '' },
      editingUplink: null,
      
      // 版本期望表單
      newVersion: { hostname: '', expected_versions: '', description: '' },
      editingVersion: null,
      
      // Port Channel 期望表單
      newPortChannel: { hostname: '', port_channel: '', member_interfaces: '', description: '' },
      editingPortChannel: null,
      
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
    };
  },
  computed: {
    selectedMaintenanceId() {
      return this.maintenanceId;
    },
    canAddDevice() {
      return this.newDevice.old_hostname && this.newDevice.old_ip_address && this.newDevice.old_vendor
          && this.newDevice.new_hostname && this.newDevice.new_ip_address && this.newDevice.new_vendor;
    },
  },
  watch: {
    selectedMaintenanceId(newId) {
      if (newId) {
        this.loadMaintenanceData();
      }
    },
  },
  mounted() {
    this.loadMaintenanceList();
    this.loadDevices();
    if (this.selectedMaintenanceId) {
      this.loadMaintenanceData();
    }
  },
  methods: {
    // 歲修管理
    async loadMaintenanceList() {
      try {
        const res = await fetch('/api/v1/maintenance');
        if (res.ok) {
          this.maintenanceList = await res.json();
        }
      } catch (e) {
        console.error('載入歲修列表失敗:', e);
      }
    },
    
    async createMaintenance() {
      if (!this.newMaintenance.id) return;
      
      try {
        const res = await fetch('/api/v1/maintenance', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.newMaintenance),
        });
        
        if (res.ok) {
          this.showAddMaintenanceModal = false;
          this.newMaintenance = { id: '', name: '' };
          await this.loadMaintenanceList();
          // 刷新頂部的歲修選擇器
          if (this.refreshMaintenanceList) {
            this.refreshMaintenanceList();
          }
        } else {
          const err = await res.json();
          this.showMessage(`建立失敗: ${err.detail || '未知錯誤'}`, 'error');
        }
      } catch (e) {
        console.error('建立歲修失敗:', e);
        this.showMessage('建立失敗，請稍後再試', 'error');
      }
    },
    
    deleteMaintenance(m) {
      // 開啟自訂確認 Modal
      this.deleteTarget = m;
      this.deleteConfirmInput = '';
      this.showDeleteMaintenanceModal = true;
    },
    
    cancelDeleteMaintenance() {
      this.showDeleteMaintenanceModal = false;
      this.deleteTarget = null;
      this.deleteConfirmInput = '';
    },
    
    async confirmDeleteMaintenance() {
      if (!this.deleteTarget || this.deleteConfirmInput !== this.deleteTarget.id) {
        return;
      }
      
      try {
        const res = await fetch(`/api/v1/maintenance/${encodeURIComponent(this.deleteTarget.id)}`, {
          method: 'DELETE',
        });
        
        if (res.ok) {
          this.showDeleteMaintenanceModal = false;
          this.deleteTarget = null;
          this.deleteConfirmInput = '';
          await this.loadMaintenanceList();
          // 刷新頂部的歲修選擇器
          if (this.refreshMaintenanceList) {
            this.refreshMaintenanceList();
          }
        } else {
          const err = await res.json();
          this.showMessage(`刪除失敗: ${err.detail || '未知錯誤'}`, 'error');
        }
      } catch (e) {
        console.error('刪除歲修失敗:', e);
        this.showMessage('刪除失敗，請稍後再試', 'error');
      }
    },
    
    formatDate(dateStr) {
      if (!dateStr) return '-';
      try {
        const d = new Date(dateStr);
        return d.toLocaleString('zh-TW', {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
        });
      } catch {
        return dateStr;
      }
    },
    
    async loadDevices() {
      this.loading = true;
      try {
        const res = await fetch('/api/v1/switches');
        if (res.ok) {
          this.devices = await res.json();
        }
      } catch (e) {
        console.error('載入設備失敗:', e);
      } finally {
        this.loading = false;
      }
    },
    
    async loadMaintenanceData() {
      if (!this.selectedMaintenanceId) return;
      
      this.loading = true;
      try {
        // 載入設備對應
        const mappingRes = await fetch(`/api/v1/device-mappings/${this.selectedMaintenanceId}`);
        if (mappingRes.ok) {
          const data = await mappingRes.json();
          this.deviceMappings = data.mappings || [];
        }
        
        // 載入 Uplink 期望
        await this.loadUplinkList();
        
        // 載入版本期望
        await this.loadVersionList();
        
        // 載入 Port Channel 期望
        await this.loadPortChannelList();
        
        // 載入 ARP 來源
        await this.loadArpList();
        
        // 載入分類
        await this.loadCategories();
        
        // 載入 MAC 清單
        await this.loadMacList();
        await this.loadMacStats();
        
        // 載入設備清單
        await this.loadDeviceList();
        await this.loadDeviceStats();
      } catch (e) {
        console.error('載入歲修數據失敗:', e);
      } finally {
        this.loading = false;
      }
    },
    
    // 設備操作
    editDevice(device) {
      this.showMessage(`編輯設備功能尚未實作: ${device.hostname}`, 'info');
    },
    async deleteDevice(device) {
      const confirmed = await this.showConfirm(`確定要刪除設備 ${device.hostname}？`, '刪除確認');
      if (!confirmed) return;
      // TODO: 呼叫刪除 API
    },
    
    // 設備對應操作
    editMapping(mapping) {
      this.showMessage(`編輯對應功能尚未實作: ${mapping.old_hostname} → ${mapping.new_hostname}`, 'info');
    },
    async deleteMapping(mapping) {
      const confirmed = await this.showConfirm(`確定要刪除對應 ${mapping.old_hostname} → ${mapping.new_hostname}？`, '刪除確認');
      if (!confirmed) return;
      try {
        const res = await fetch(`/api/v1/device-mappings/${this.selectedMaintenanceId}/${mapping.id}`, {
          method: 'DELETE',
        });
        if (res.ok) {
          await this.loadMaintenanceData();
        }
      } catch (e) {
        console.error('刪除對應失敗:', e);
        this.showMessage('刪除失敗', 'error');
      }
    },
    
    // ========== Uplink 期望操作 ==========
    async loadUplinkList() {
      if (!this.selectedMaintenanceId) return;
      
      try {
        const params = new URLSearchParams();
        if (this.uplinkSearch) params.append('search', this.uplinkSearch);
        
        let url = `/api/v1/expectations/uplink/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();
        
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          this.uplinkExpectations = data.items || [];
        }
      } catch (e) {
        console.error('載入 Uplink 期望失敗:', e);
      }
    },
    
    downloadUplinkTemplate() {
      const csv = `hostname,local_interface,expected_neighbor,expected_interface,description
SW-001,Gi1/0/1,CORE-SW-01,Gi1/0/48,上聯到核心
SW-001,Gi1/0/2,CORE-SW-02,Gi1/0/48,備援上聯
SW-002,Eth1/1,SPINE-01,Eth49/1,Leaf to Spine`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'uplink_expectations_template.csv';
      link.click();
    },
    
    async importUplinkList(event) {
      const file = event.target.files[0];
      if (!file || !this.selectedMaintenanceId) return;
      
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const res = await fetch(`/api/v1/expectations/uplink/${this.selectedMaintenanceId}/import-csv`, {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        
        if (res.ok) {
          await this.loadUplinkList();
          this.showMessage(`新增: ${data.imported} 筆\n更新: ${data.updated} 筆\n錯誤: ${data.total_errors} 筆`, 'success', '匯入完成');
        } else {
          this.showMessage(data.detail || '匯入失敗', 'error');
        }
      } catch (e) {
        console.error('Uplink 匯入失敗:', e);
        this.showMessage('匯入失敗', 'error');
      }
      event.target.value = '';
    },
    
    openAddUplink() {
      this.editingUplink = null;
      this.newUplink = { hostname: '', local_interface: '', expected_neighbor: '', expected_interface: '', description: '' };
      this.showAddUplinkModal = true;
    },
    
    editUplink(uplink) {
      this.editingUplink = uplink;
      this.newUplink = {
        id: uplink.id,
        hostname: uplink.hostname || '',
        local_interface: uplink.local_interface || '',
        expected_neighbor: uplink.expected_neighbor || '',
        expected_interface: uplink.expected_interface || '',
        description: uplink.description || '',
      };
      this.showAddUplinkModal = true;
    },
    
    closeUplinkModal() {
      this.showAddUplinkModal = false;
      this.editingUplink = null;
      this.newUplink = { hostname: '', local_interface: '', expected_neighbor: '', expected_interface: '', description: '' };
    },
    
    async saveUplink() {
      if (!this.newUplink.hostname || !this.newUplink.local_interface || !this.newUplink.expected_neighbor || !this.selectedMaintenanceId) return;
      
      try {
        let res;
        const payload = {
          hostname: this.newUplink.hostname.trim(),
          local_interface: this.newUplink.local_interface.trim(),
          expected_neighbor: this.newUplink.expected_neighbor.trim(),
          expected_interface: this.newUplink.expected_interface?.trim() || null,
          description: this.newUplink.description?.trim() || null,
        };
        
        if (this.editingUplink && this.newUplink.id) {
          res = await fetch(`/api/v1/expectations/uplink/${this.selectedMaintenanceId}/${this.newUplink.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
        } else {
          res = await fetch(`/api/v1/expectations/uplink/${this.selectedMaintenanceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
        }
        
        if (res.ok) {
          const msg = this.editingUplink ? 'Uplink 期望更新成功' : 'Uplink 期望新增成功';
          this.closeUplinkModal();
          await this.loadUplinkList();
          this.showMessage(msg, 'success');
        } else {
          try {
            const err = await res.json();
            this.showMessage(err.detail || `錯誤 ${res.status}: ${res.statusText}`, 'error');
          } catch {
            this.showMessage(`錯誤 ${res.status}: ${res.statusText}`, 'error');
          }
        }
      } catch (e) {
        console.error('儲存 Uplink 期望失敗:', e);
        this.showMessage(`儲存失敗: ${e.message || '網路錯誤'}`, 'error');
      }
    },
    
    async deleteUplink(uplink) {
      const confirmed = await this.showConfirm(`確定要刪除 ${uplink.hostname}:${uplink.local_interface} 的 Uplink 期望？`, '刪除確認');
      if (!confirmed) return;
      
      try {
        const res = await fetch(`/api/v1/expectations/uplink/${this.selectedMaintenanceId}/${uplink.id}`, {
          method: 'DELETE',
        });
        if (res.ok) {
          await this.loadUplinkList();
          this.showMessage('刪除成功', 'success');
        }
      } catch (e) {
        console.error('刪除 Uplink 期望失敗:', e);
        this.showMessage('刪除失敗', 'error');
      }
    },
    
    // ========== 版本期望操作 ==========
    async loadVersionList() {
      if (!this.selectedMaintenanceId) return;
      
      try {
        const params = new URLSearchParams();
        if (this.versionSearch) params.append('search', this.versionSearch);
        
        let url = `/api/v1/expectations/version/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();
        
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          this.versionExpectations = data.items || [];
        }
      } catch (e) {
        console.error('載入版本期望失敗:', e);
      }
    },
    
    downloadVersionTemplate() {
      const csv = `hostname,expected_versions,description
SW-001,16.10.1;16.10.2,可接受兩個版本
SW-002,WC.17.10.01,指定特定版本
CORE-SW-01,9.4(1),NX-OS版本`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'version_expectations_template.csv';
      link.click();
    },
    
    async importVersionList(event) {
      const file = event.target.files[0];
      if (!file || !this.selectedMaintenanceId) return;
      
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const res = await fetch(`/api/v1/expectations/version/${this.selectedMaintenanceId}/import-csv`, {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        
        if (res.ok) {
          await this.loadVersionList();
          this.showMessage(`新增: ${data.imported} 筆\n更新: ${data.updated} 筆\n錯誤: ${data.total_errors} 筆`, 'success', '匯入完成');
        } else {
          this.showMessage(data.detail || '匯入失敗', 'error');
        }
      } catch (e) {
        console.error('版本期望匯入失敗:', e);
        this.showMessage('匯入失敗', 'error');
      }
      event.target.value = '';
    },
    
    openAddVersion() {
      this.editingVersion = null;
      this.newVersion = { hostname: '', expected_versions: '', description: '' };
      this.showAddVersionModal = true;
    },
    
    editVersion(ver) {
      this.editingVersion = ver;
      this.newVersion = {
        id: ver.id,
        hostname: ver.hostname || '',
        expected_versions: ver.expected_versions || '',
        description: ver.description || '',
      };
      this.showAddVersionModal = true;
    },
    
    closeVersionModal() {
      this.showAddVersionModal = false;
      this.editingVersion = null;
      this.newVersion = { hostname: '', expected_versions: '', description: '' };
    },
    
    async saveVersion() {
      if (!this.newVersion.hostname || !this.newVersion.expected_versions || !this.selectedMaintenanceId) return;
      
      try {
        let res;
        const payload = {
          hostname: this.newVersion.hostname.trim(),
          expected_versions: this.newVersion.expected_versions.trim(),
          description: this.newVersion.description?.trim() || null,
        };
        
        if (this.editingVersion && this.newVersion.id) {
          res = await fetch(`/api/v1/expectations/version/${this.selectedMaintenanceId}/${this.newVersion.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
        } else {
          res = await fetch(`/api/v1/expectations/version/${this.selectedMaintenanceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
        }
        
        if (res.ok) {
          const msg = this.editingVersion ? '版本期望更新成功' : '版本期望新增成功';
          this.closeVersionModal();
          await this.loadVersionList();
          this.showMessage(msg, 'success');
        } else {
          const err = await res.json();
          this.showMessage(err.detail || (this.editingVersion ? '更新失敗' : '新增失敗'), 'error');
        }
      } catch (e) {
        console.error('儲存版本期望失敗:', e);
        this.showMessage('儲存失敗', 'error');
      }
    },
    
    async deleteVersion(ver) {
      const confirmed = await this.showConfirm(`確定要刪除 ${ver.hostname} 的版本期望？`, '刪除確認');
      if (!confirmed) return;
      
      try {
        const res = await fetch(`/api/v1/expectations/version/${this.selectedMaintenanceId}/${ver.id}`, {
          method: 'DELETE',
        });
        if (res.ok) {
          await this.loadVersionList();
          this.showMessage('刪除成功', 'success');
        }
      } catch (e) {
        console.error('刪除版本期望失敗:', e);
        this.showMessage('刪除失敗', 'error');
      }
    },
    
    // ========== Port Channel 期望操作 ==========
    async loadPortChannelList() {
      if (!this.selectedMaintenanceId) return;
      
      try {
        const params = new URLSearchParams();
        if (this.portChannelSearch) params.append('search', this.portChannelSearch);
        
        let url = `/api/v1/expectations/port-channel/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();
        
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          this.portChannelExpectations = data.items || [];
        }
      } catch (e) {
        console.error('載入 Port Channel 期望失敗:', e);
      }
    },
    
    downloadPortChannelTemplate() {
      const csv = `hostname,port_channel,member_interfaces,description
SW-001,Po1,Gi1/0/1;Gi1/0/2,上聯 LACP
SW-002,Port-channel1,Eth1/1;Eth1/2,vPC到核心
CORE-01,Po10,Gi0/1;Gi0/2;Gi0/3,三成員 LAG`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'port_channel_expectations_template.csv';
      link.click();
    },
    
    async importPortChannelList(event) {
      const file = event.target.files[0];
      if (!file || !this.selectedMaintenanceId) return;
      
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const res = await fetch(`/api/v1/expectations/port-channel/${this.selectedMaintenanceId}/import-csv`, {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        
        if (res.ok) {
          await this.loadPortChannelList();
          this.showMessage(`新增: ${data.imported} 筆\n更新: ${data.updated} 筆\n錯誤: ${data.total_errors} 筆`, 'success', '匯入完成');
        } else {
          this.showMessage(data.detail || '匯入失敗', 'error');
        }
      } catch (e) {
        console.error('Port-Channel 匯入失敗:', e);
        this.showMessage('匯入失敗', 'error');
      }
      event.target.value = '';
    },
    
    openAddPortChannel() {
      this.editingPortChannel = null;
      this.newPortChannel = { hostname: '', port_channel: '', member_interfaces: '', description: '' };
      this.showAddPortChannelModal = true;
    },
    
    editPortChannel(pc) {
      this.editingPortChannel = pc;
      this.newPortChannel = {
        id: pc.id,
        hostname: pc.hostname || '',
        port_channel: pc.port_channel || '',
        member_interfaces: pc.member_interfaces || '',
        description: pc.description || '',
      };
      this.showAddPortChannelModal = true;
    },
    
    closePortChannelModal() {
      this.showAddPortChannelModal = false;
      this.editingPortChannel = null;
      this.newPortChannel = { hostname: '', port_channel: '', member_interfaces: '', description: '' };
    },
    
    async savePortChannel() {
      if (!this.newPortChannel.hostname || !this.newPortChannel.port_channel || !this.newPortChannel.member_interfaces || !this.selectedMaintenanceId) return;
      
      try {
        let res;
        const payload = {
          hostname: this.newPortChannel.hostname.trim(),
          port_channel: this.newPortChannel.port_channel.trim(),
          member_interfaces: this.newPortChannel.member_interfaces.trim(),
          description: this.newPortChannel.description?.trim() || null,
        };
        
        if (this.editingPortChannel && this.newPortChannel.id) {
          res = await fetch(`/api/v1/expectations/port-channel/${this.selectedMaintenanceId}/${this.newPortChannel.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
        } else {
          res = await fetch(`/api/v1/expectations/port-channel/${this.selectedMaintenanceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
        }
        
        if (res.ok) {
          const msg = this.editingPortChannel ? 'Port Channel 期望更新成功' : 'Port Channel 期望新增成功';
          this.closePortChannelModal();
          await this.loadPortChannelList();
          this.showMessage(msg, 'success');
        } else {
          const err = await res.json();
          this.showMessage(err.detail || (this.editingPortChannel ? '更新失敗' : '新增失敗'), 'error');
        }
      } catch (e) {
        console.error('儲存 Port Channel 期望失敗:', e);
        this.showMessage('儲存失敗', 'error');
      }
    },
    
    async deletePortChannel(pc) {
      const confirmed = await this.showConfirm(`確定要刪除 ${pc.hostname}:${pc.port_channel} 的 Port Channel 期望？`, '刪除確認');
      if (!confirmed) return;
      
      try {
        const res = await fetch(`/api/v1/expectations/port-channel/${this.selectedMaintenanceId}/${pc.id}`, {
          method: 'DELETE',
        });
        if (res.ok) {
          await this.loadPortChannelList();
          this.showMessage('刪除成功', 'success');
        }
      } catch (e) {
        console.error('刪除 Port Channel 期望失敗:', e);
        this.showMessage('刪除失敗', 'error');
      }
    },
    
    // ========== ARP 來源操作 ==========
    async loadArpList() {
      if (!this.selectedMaintenanceId) return;
      
      try {
        const params = new URLSearchParams();
        if (this.arpSearch) params.append('search', this.arpSearch);
        
        let url = `/api/v1/expectations/arp/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();
        
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          this.arpSources = data.items || [];
        }
      } catch (e) {
        console.error('載入 ARP 來源失敗:', e);
      }
    },
    
    downloadArpTemplate() {
      const csv = `hostname,ip_address,priority,description
CORE-ROUTER-01,10.1.1.1,10,主要 Gateway
CORE-ROUTER-02,10.1.1.2,20,備援 Gateway
DISTRO-SW-01,10.1.2.1,100,分發層交換機`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'arp_sources_template.csv';
      link.click();
    },
    
    async importArpList(event) {
      const file = event.target.files[0];
      if (!file || !this.selectedMaintenanceId) return;
      
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const res = await fetch(`/api/v1/expectations/arp/${this.selectedMaintenanceId}/import-csv`, {
          method: 'POST',
          body: formData,
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
        this.showMessage('匯入失敗', 'error');
      }
      event.target.value = '';
    },
    
    openAddArp() {
      this.editingArp = null;
      this.newArp = { hostname: '', ip_address: '', priority: 100, description: '' };
      this.showAddArpModal = true;
    },
    
    editArp(arp) {
      this.editingArp = arp;
      this.newArp = {
        id: arp.id,
        hostname: arp.hostname || '',
        ip_address: arp.ip_address || '',
        priority: arp.priority || 100,
        description: arp.description || '',
      };
      this.showAddArpModal = true;
    },
    
    closeArpModal() {
      this.showAddArpModal = false;
      this.editingArp = null;
      this.newArp = { hostname: '', ip_address: '', priority: 100, description: '' };
    },
    
    async saveArp() {
      if (!this.newArp.hostname || !this.newArp.ip_address || !this.selectedMaintenanceId) return;
      
      try {
        let res;
        const payload = {
          hostname: this.newArp.hostname.trim(),
          ip_address: this.newArp.ip_address.trim(),
          priority: this.newArp.priority || 100,
          description: this.newArp.description?.trim() || null,
        };
        
        if (this.editingArp && this.newArp.id) {
          res = await fetch(`/api/v1/expectations/arp/${this.selectedMaintenanceId}/${this.newArp.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
        } else {
          res = await fetch(`/api/v1/expectations/arp/${this.selectedMaintenanceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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
    
    // ========== MAC 清單操作 ==========
    async loadMacList() {
      if (!this.selectedMaintenanceId) return;
      
      try {
        // 使用 detailed 端點獲取完整資訊
        const params = new URLSearchParams();
        if (this.macSearch) params.append('search', this.macSearch);
        if (this.macFilterStatus !== 'all') params.append('filter_status', this.macFilterStatus);
        if (this.macFilterCategory !== 'all') params.append('filter_category', this.macFilterCategory);
        
        let url = `/api/v1/mac-list/${this.selectedMaintenanceId}/detailed`;
        if (params.toString()) url += '?' + params.toString();
        
        const res = await fetch(url);
        if (res.ok) {
          this.macList = await res.json();
        }
      } catch (e) {
        console.error('載入 MAC 清單失敗:', e);
      }
    },
    
    async loadCategories() {
      if (!this.selectedMaintenanceId) return;
      
      try {
        const res = await fetch(`/api/v1/categories?maintenance_id=${this.selectedMaintenanceId}`);
        if (res.ok) {
          this.categories = await res.json();
        }
      } catch (e) {
        console.error('載入分類失敗:', e);
      }
    },
    
    openSetCategory(mac) {
      this.selectedMacForCategory = mac;
      this.selectedCategoryId = mac.category_id ? String(mac.category_id) : '';
      this.showSetCategoryModal = true;
    },
    
    async setMacCategory() {
      if (!this.selectedMacForCategory || !this.selectedMaintenanceId) return;
      
      try {
        const mac = this.selectedMacForCategory.mac_address;
        
        // 如果要移除分類
        if (!this.selectedCategoryId) {
          // 從所有分類移除
          if (this.selectedMacForCategory.category_id) {
            await fetch(`/api/v1/categories/${this.selectedMacForCategory.category_id}/members/${encodeURIComponent(mac)}`, {
              method: 'DELETE',
            });
          }
        } else {
          // 先從舊分類移除（如果有）
          if (this.selectedMacForCategory.category_id && this.selectedMacForCategory.category_id !== parseInt(this.selectedCategoryId)) {
            await fetch(`/api/v1/categories/${this.selectedMacForCategory.category_id}/members/${encodeURIComponent(mac)}`, {
              method: 'DELETE',
            });
          }
          
          // 添加到新分類
          await fetch(`/api/v1/categories/${this.selectedCategoryId}/members`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mac_address: mac }),
          });
        }
        
        this.showSetCategoryModal = false;
        await this.loadMacList();
        await this.loadMacStats();
      } catch (e) {
        console.error('設定分類失敗:', e);
        this.showMessage('設定分類失敗', 'error');
      }
    },
    
    async loadMacStats() {
      if (!this.selectedMaintenanceId) return;
      
      try {
        const res = await fetch(`/api/v1/mac-list/${this.selectedMaintenanceId}/stats`);
        if (res.ok) {
          this.macListStats = await res.json();
        }
      } catch (e) {
        console.error('載入 MAC 統計失敗:', e);
      }
    },
    
    debouncedLoadMacList() {
      if (this.macSearchTimeout) {
        clearTimeout(this.macSearchTimeout);
      }
      this.macSearchTimeout = setTimeout(() => {
        this.loadMacList();
      }, 300);
    },
    
    downloadMacTemplate() {
      const csv = `mac_address,description,category
AA:BB:CC:DD:EE:01,機台1號,Demo
AA:BB:CC:DD:EE:02,機台2號,Demo
AA:BB:CC:DD:EE:03,不斷電機台A,不斷電機台
AA:BB:CC:DD:EE:04,,AMHS`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'mac_list_template.csv';
      link.click();
    },
    
    async importMacList(event) {
      const file = event.target.files[0];
      if (!file || !this.selectedMaintenanceId) return;
      
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const res = await fetch(`/api/v1/mac-list/${this.selectedMaintenanceId}/import-csv`, {
          method: 'POST',
          body: formData,
        });
        const data = await res.json();
        
        if (res.ok) {
          await this.loadCategories();  // 可能有新分類
          await this.loadMacList();
          await this.loadMacStats();
          this.showMessage(`新增: ${data.imported} 筆\n略過: ${data.skipped} 筆\n錯誤: ${data.total_errors} 筆`, 'success', '匯入完成');
        } else {
          this.showMessage(data.detail || '匯入失敗', 'error');
        }
      } catch (e) {
        console.error('MAC 匯入失敗:', e);
        this.showMessage('匯入失敗', 'error');
      }
      
      event.target.value = '';
    },
    
    async deleteMac(mac) {
      const confirmed = await this.showConfirm(`確定要刪除 ${mac.mac_address}？`, '刪除確認');
      if (!confirmed) return;
      
      try {
        const res = await fetch(`/api/v1/mac-list/${this.selectedMaintenanceId}/${encodeURIComponent(mac.mac_address)}`, {
          method: 'DELETE',
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
    
    async addMac() {
      if (!this.newMac.mac_address || !this.selectedMaintenanceId) return;
      
      // 標準化 MAC 格式並去除空白
      const mac = this.newMac.mac_address.trim().toUpperCase().replace(/-/g, ':');
      const description = this.newMac.description?.trim() || null;
      const category = this.newMac.category?.trim() || null;
      
      try {
        const res = await fetch(`/api/v1/mac-list/${this.selectedMaintenanceId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mac_address: mac,
            description: description,
            category: category,
          }),
        });
        
        if (res.ok) {
          this.showAddMacModal = false;
          this.newMac = { mac_address: '', description: '', category: '' };
          await this.loadCategories();  // 重新載入分類（可能有新建的）
          await this.loadMacList();
          await this.loadMacStats();
        } else {
          const err = await res.json();
          this.showMessage(err.detail || '新增失敗', 'error');
        }
      } catch (e) {
        console.error('新增 MAC 失敗:', e);
        this.showMessage('新增失敗', 'error');
      }
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
    
    // 分類更新後的回調（同時刷新 MAC 清單）
    async onCategoryRefresh() {
      await this.loadCategories();
      await this.loadMacList();
      await this.loadMacStats();
    },
    
    // ========== 設備清單方法 ==========
    async loadDeviceList() {
      if (!this.selectedMaintenanceId) return;
      
      try {
        const params = new URLSearchParams();
        if (this.deviceSearch) params.append('search', this.deviceSearch);
        if (this.deviceFilterRole) params.append('role', this.deviceFilterRole);
        if (this.deviceFilterReachable && this.deviceFilterReachable !== 'null') {
          params.append('is_reachable', this.deviceFilterReachable);
        }
        if (this.deviceFilterMapping) {
          params.append('has_mapping', this.deviceFilterMapping);
        }
        
        let url = `/api/v1/maintenance-devices/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();
        
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          this.deviceList = data.devices || [];
        }
      } catch (e) {
        console.error('載入設備清單失敗:', e);
      }
    },
    
    async loadDeviceStats() {
      if (!this.selectedMaintenanceId) return;
      
      try {
        const res = await fetch(`/api/v1/maintenance-devices/${this.selectedMaintenanceId}/stats`);
        if (res.ok) {
          this.deviceStats = await res.json();
        }
      } catch (e) {
        console.error('載入設備統計失敗:', e);
      }
    },
    
    debouncedLoadDeviceList() {
      if (this.deviceSearchTimeout) clearTimeout(this.deviceSearchTimeout);
      this.deviceSearchTimeout = setTimeout(() => this.loadDeviceList(), 300);
    },
    
    getRoleClass(role) {
      switch (role) {
        case 'old': return 'bg-red-600/30 text-red-300';
        case 'new': return 'bg-green-600/30 text-green-300';
        case 'unchanged': return 'bg-amber-600/30 text-amber-300';
        default: return 'bg-slate-600/30 text-slate-300';
      }
    },
    
    downloadDeviceTemplate() {
      const csv = `old_hostname,old_ip_address,old_vendor,new_hostname,new_ip_address,new_vendor,use_same_port,description
OLD-SW-001,10.1.1.1,HPE,NEW-SW-001,10.1.1.101,HPE,TRUE,1F機房更換
OLD-SW-002,10.1.1.2,Cisco-IOS,NEW-SW-002,10.1.1.102,Cisco-IOS,TRUE,2F機房更換
SW-UNCHANGED,10.1.1.200,Cisco-NXOS,SW-UNCHANGED,10.1.1.200,Cisco-NXOS,TRUE,不更換設備`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'device_mapping_template.csv';
      link.click();
    },
    
    async importDeviceList(event) {
      const file = event.target.files[0];
      if (!file || !this.selectedMaintenanceId) return;
      
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const res = await fetch(`/api/v1/maintenance-devices/${this.selectedMaintenanceId}/import-csv`, {
          method: 'POST',
          body: formData,
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
        this.showMessage('匯入失敗', 'error');
      }
      event.target.value = '';
    },
    
    async addDevice() {
      if (!this.canAddDevice || !this.selectedMaintenanceId) return;
      
      try {
        const res = await fetch(`/api/v1/maintenance-devices/${this.selectedMaintenanceId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            old_hostname: this.newDevice.old_hostname.trim(),
            old_ip_address: this.newDevice.old_ip_address.trim(),
            old_vendor: this.newDevice.old_vendor,
            new_hostname: this.newDevice.new_hostname.trim(),
            new_ip_address: this.newDevice.new_ip_address.trim(),
            new_vendor: this.newDevice.new_vendor,
            use_same_port: this.newDevice.use_same_port,
            description: this.newDevice.description?.trim() || null,
          }),
        });
        
        if (res.ok) {
          this.showAddDeviceModal = false;
          this.newDevice = { 
            old_hostname: '', old_ip_address: '', old_vendor: 'HPE', 
            new_hostname: '', new_ip_address: '', new_vendor: 'HPE',
            use_same_port: true, description: '' 
          };
          await this.loadDeviceList();
          await this.loadDeviceStats();
          this.showMessage('設備對應新增成功', 'success');
        } else {
          const err = await res.json();
          this.showMessage(err.detail || '新增失敗', 'error');
        }
      } catch (e) {
        console.error('新增設備失敗:', e);
        this.showMessage('新增失敗', 'error');
      }
    },
    
    // 關閉設備 Modal 並重置狀態
    closeDeviceModal() {
      this.showAddDeviceModal = false;
      this.editingDevice = false;
      this.newDevice = { 
        id: null,
        old_hostname: '', old_ip_address: '', old_vendor: 'HPE', 
        new_hostname: '', new_ip_address: '', new_vendor: 'HPE',
        use_same_port: true, description: '' 
      };
    },
    
    // 儲存設備（新增或編輯）
    async saveDevice() {
      if (!this.canAddDevice || !this.selectedMaintenanceId) return;
      
      try {
        let res;
        if (this.editingDevice && this.newDevice.id) {
          // 編輯模式 - 使用 PUT
          res = await fetch(`/api/v1/maintenance-devices/${this.selectedMaintenanceId}/${this.newDevice.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              old_hostname: this.newDevice.old_hostname.trim(),
              old_ip_address: this.newDevice.old_ip_address.trim(),
              old_vendor: this.newDevice.old_vendor,
              new_hostname: this.newDevice.new_hostname.trim(),
              new_ip_address: this.newDevice.new_ip_address.trim(),
              new_vendor: this.newDevice.new_vendor,
              use_same_port: this.newDevice.use_same_port,
              description: this.newDevice.description?.trim() || null,
            }),
          });
        } else {
          // 新增模式 - 使用 POST
          res = await fetch(`/api/v1/maintenance-devices/${this.selectedMaintenanceId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              old_hostname: this.newDevice.old_hostname.trim(),
              old_ip_address: this.newDevice.old_ip_address.trim(),
              old_vendor: this.newDevice.old_vendor,
              new_hostname: this.newDevice.new_hostname.trim(),
              new_ip_address: this.newDevice.new_ip_address.trim(),
              new_vendor: this.newDevice.new_vendor,
              use_same_port: this.newDevice.use_same_port,
              description: this.newDevice.description?.trim() || null,
            }),
          });
        }
        
        if (res.ok) {
          const msg = this.editingDevice ? '設備對應更新成功' : '設備對應新增成功';
          this.closeDeviceModal();
          await this.loadDeviceList();
          await this.loadDeviceStats();
          this.showMessage(msg, 'success');
        } else {
          const err = await res.json();
          this.showMessage(err.detail || (this.editingDevice ? '更新失敗' : '新增失敗'), 'error');
        }
      } catch (e) {
        console.error('儲存設備失敗:', e);
        this.showMessage('儲存失敗', 'error');
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
    
    openPairModal(device) {
      this.showMessage(`配對功能尚未完成: ${device.hostname}`, 'info');
    },
    
    async unpairDevice(device) {
      const confirmed = await this.showConfirm(`確定要取消 ${device.hostname} 的配對？`, '取消配對');
      if (!confirmed) return;
      
      try {
        const res = await fetch(`/api/v1/maintenance-devices/${this.selectedMaintenanceId}/pair/${encodeURIComponent(device.hostname)}`, {
          method: 'DELETE',
        });
        if (res.ok) {
          await this.loadDeviceList();
          await this.loadDeviceStats();
        }
      } catch (e) {
        console.error('取消配對失敗:', e);
        this.showMessage('取消配對失敗', 'error');
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
    
    // ========== 批量選擇 ==========
    toggleSelectAll() {
      if (this.selectAll) {
        this.selectedMacs = this.macList.map(m => m.mac_address);
      } else {
        this.selectedMacs = [];
      }
    },
    
    clearSelection() {
      this.selectedMacs = [];
      this.selectAll = false;
    },
    
    openBatchCategory() {
      this.batchCategoryId = '';
      this.showBatchCategoryModal = true;
    },
    
    async applyBatchCategory() {
      if (this.selectedMacs.length === 0) return;
      
      this.loading = true;
      try {
        for (const mac of this.selectedMacs) {
          // 獲取該 MAC 當前的分類
          const macData = this.macList.find(m => m.mac_address === mac);
          const oldCatId = macData?.category_id;
          
          // 如果要移除分類
          if (!this.batchCategoryId) {
            if (oldCatId) {
              await fetch(`/api/v1/categories/${oldCatId}/members/${encodeURIComponent(mac)}`, {
                method: 'DELETE',
              });
            }
          } else {
            // 先從舊分類移除（如果有且不同）
            if (oldCatId && oldCatId !== parseInt(this.batchCategoryId)) {
              await fetch(`/api/v1/categories/${oldCatId}/members/${encodeURIComponent(mac)}`, {
                method: 'DELETE',
              });
            }
            // 添加到新分類
            await fetch(`/api/v1/categories/${this.batchCategoryId}/members`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ mac_address: mac }),
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
  },
};
</script>
