<template>
  <div class="px-3 py-3">
    <!-- 頁面標題 -->
    <div class="flex justify-between items-center mb-3">
      <div>
        <h1 class="text-xl font-bold text-white">⚙️ 設置</h1>
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
          <!-- 搜尋和操作 -->
          <div class="flex gap-3 mb-3">
            <input
              v-model="uplinkSearch"
              type="text"
              placeholder="搜尋設備或鄰居..."
              class="flex-1 px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="loadUplinkList"
            />
            <button @click="exportUplinkCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition">
              📤 匯出 CSV
            </button>
          </div>

          <!-- 批量操作 -->
          <div v-if="selectedUplinks.length > 0" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded border border-cyan-700">
            <span class="text-sm text-cyan-300">已選 {{ selectedUplinks.length }} 筆</span>
            <button @click="batchDeleteUplinks" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded transition">
              🗑️ 批量刪除
            </button>
            <button @click="clearUplinkSelection" class="px-2 py-1 text-slate-400 hover:text-white text-sm">
              ✕ 清除選擇
            </button>
          </div>

          <div ref="uplinkScrollContainer" class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="uplinkSelectAll" @change="toggleUplinkSelectAll" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">本地介面</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">預期鄰居</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">鄰居介面</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="uplink in uplinkExpectations" :key="uplink.id" class="hover:bg-slate-700/50 transition" :class="{ 'bg-cyan-900/20': selectedUplinks.includes(uplink.id) }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="uplink.id" v-model="selectedUplinks" class="rounded border-slate-500" />
                  </td>
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
          <!-- 搜尋和操作 -->
          <div class="flex gap-3 mb-3">
            <input
              v-model="versionSearch"
              type="text"
              placeholder="搜尋設備或版本..."
              class="flex-1 px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="loadVersionList"
            />
            <button @click="exportVersionCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition">
              📤 匯出 CSV
            </button>
          </div>

          <!-- 批量操作 -->
          <div v-if="selectedVersions.length > 0" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded border border-cyan-700">
            <span class="text-sm text-cyan-300">已選 {{ selectedVersions.length }} 筆</span>
            <button @click="batchDeleteVersions" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded transition">
              🗑️ 批量刪除
            </button>
            <button @click="clearVersionSelection" class="px-2 py-1 text-slate-400 hover:text-white text-sm">
              ✕ 清除選擇
            </button>
          </div>

          <div ref="versionScrollContainer" class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="versionSelectAll" @change="toggleVersionSelectAll" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">目標版本</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="ver in versionExpectations" :key="ver.id" class="hover:bg-slate-700/50 transition" :class="{ 'bg-cyan-900/20': selectedVersions.includes(ver.id) }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="ver.id" v-model="selectedVersions" class="rounded border-slate-500" />
                  </td>
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
          <!-- 搜尋和操作 -->
          <div class="flex gap-3 mb-3">
            <input
              v-model="portChannelSearch"
              type="text"
              placeholder="搜尋設備或 Port-Channel..."
              class="flex-1 px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm"
              @input="loadPortChannelList"
            />
            <button @click="exportPortChannelCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition">
              📤 匯出 CSV
            </button>
          </div>

          <!-- 批量操作 -->
          <div v-if="selectedPortChannels.length > 0" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded border border-cyan-700">
            <span class="text-sm text-cyan-300">已選 {{ selectedPortChannels.length }} 筆</span>
            <button @click="batchDeletePortChannels" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded transition">
              🗑️ 批量刪除
            </button>
            <button @click="clearPortChannelSelection" class="px-2 py-1 text-slate-400 hover:text-white text-sm">
              ✕ 清除選擇
            </button>
          </div>

          <div ref="portChannelScrollContainer" class="overflow-x-auto max-h-[400px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="portChannelSelectAll" @change="togglePortChannelSelectAll" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">Port-Channel</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">成員介面</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="pc in portChannelExpectations" :key="pc.id" class="hover:bg-slate-700/50 transition" :class="{ 'bg-cyan-900/20': selectedPortChannels.includes(pc.id) }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="pc.id" v-model="selectedPortChannels" class="rounded border-slate-500" />
                  </td>
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
import { apiFetch, formatErrorMessage, ErrorType } from '../utils/api.js';

export default {
  name: 'Settings',
  inject: ['maintenanceId', 'refreshMaintenanceList'],
  data() {
    return {
      loading: false,
      uplinkLoading: false,
      versionLoading: false,
      portChannelLoading: false,
      activeTab: 'uplink',
      tabs: [
        { id: 'uplink', name: 'Uplink 期望', icon: '🔗', scope: 'maintenance' },
        { id: 'version', name: '版本期望', icon: '📦', scope: 'maintenance' },
        { id: 'portchannel', name: 'Port Channel 期望', icon: '⛓️', scope: 'maintenance' },
      ],
      
      // 數據
      maintenanceList: [],
      devices: [],
      deviceMappings: [],
      uplinkExpectations: [],
      versionExpectations: [],
      portChannelExpectations: [],
      
      // Uplink 期望
      uplinkSearch: '',
      selectedUplinks: [],
      uplinkSelectAll: false,

      // 版本期望
      versionSearch: '',
      selectedVersions: [],
      versionSelectAll: false,

      // Port Channel 期望
      portChannelSearch: '',
      selectedPortChannels: [],
      portChannelSelectAll: false,

      // 新增歲修表單
      newMaintenance: { id: '', name: '' },
      showAddMaintenanceModal: false,

      // 刪除歲修確認
      showDeleteMaintenanceModal: false,
      deleteTarget: null,
      deleteConfirmInput: '',

      // Modal 控制
      showAddMappingModal: false,
      showAddUplinkModal: false,
      showImportUplinkModal: false,
      showAddVersionModal: false,
      showImportVersionModal: false,
      showAddPortChannelModal: false,

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
  },
  watch: {
    selectedMaintenanceId(newId) {
      if (newId) {
        this.loadMaintenanceData();
      }
    },
    activeTab(newTab) {
      // 保存 Tab 狀態到 localStorage
      localStorage.setItem('settings_active_tab', newTab);
    },
  },
  mounted() {
    // 從 localStorage 恢復 Tab 狀態
    const savedTab = localStorage.getItem('settings_active_tab');
    if (savedTab && this.tabs.some(t => t.id === savedTab)) {
      this.activeTab = savedTab;
    }

    this.loadMaintenanceList();
    if (this.selectedMaintenanceId) {
      this.loadMaintenanceData();
    }
  },
  methods: {
    // CSV 檔案驗證
    validateCsvFile(file) {
      if (!file) return { valid: false, error: '請選擇檔案' };

      const fileName = file.name.toLowerCase();
      if (!fileName.endsWith('.csv')) {
        return { valid: false, error: '請上傳 CSV 格式的檔案（.csv）' };
      }

      const validTypes = ['text/csv', 'application/vnd.ms-excel', 'text/plain', ''];
      if (!validTypes.includes(file.type)) {
        return { valid: false, error: `不支援的檔案類型: ${file.type}` };
      }

      const maxSize = 10 * 1024 * 1024;
      if (file.size > maxSize) {
        return { valid: false, error: '檔案大小超過限制（最大 10MB）' };
      }

      return { valid: true };
    },

    // 主機名稱驗證
    validateHostname(hostname) {
      if (!hostname || !hostname.trim()) {
        return { valid: false, error: '主機名稱不可為空' };
      }
      const value = hostname.trim();
      // 允許：字母、數字、橫線、底線、點，長度 1-255
      if (value.length > 255) {
        return { valid: false, error: '主機名稱過長（最多 255 字元）' };
      }
      const hostnamePattern = /^[a-zA-Z0-9][a-zA-Z0-9._-]*$/;
      if (!hostnamePattern.test(value)) {
        return { valid: false, error: '主機名稱格式錯誤：只允許字母、數字、點、底線和橫線，且須以字母或數字開頭' };
      }
      return { valid: true };
    },

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

      // 歲修 ID 格式驗證（允許字母、數字、橫線，長度 2-50）
      const idValue = this.newMaintenance.id.trim();
      const idPattern = /^[A-Za-z0-9][\w-]{1,49}$/;
      if (!idPattern.test(idValue)) {
        this.showMessage('歲修 ID 格式錯誤：只允許字母、數字、底線和橫線，長度 2-50 字元，且須以字母或數字開頭', 'error');
        return;
      }

      // 名稱長度驗證
      const nameValue = this.newMaintenance.name?.trim() || '';
      if (nameValue.length > 100) {
        this.showMessage('歲修名稱過長，最多 100 字元', 'error');
        return;
      }

      try {
        const res = await fetch('/api/v1/maintenance', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: idValue, name: nameValue }),
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

      // 保存捲動位置
      const scrollTop = this.$refs.uplinkScrollContainer?.scrollTop || 0;

      try {
        const params = new URLSearchParams();
        if (this.uplinkSearch) params.append('search', this.uplinkSearch);

        let url = `/api/v1/expectations/uplink/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();

        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          this.uplinkExpectations = data.items || [];
          // 恢復捲動位置
          this.$nextTick(() => {
            if (this.$refs.uplinkScrollContainer) {
              this.$refs.uplinkScrollContainer.scrollTop = scrollTop;
            }
          });
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
      if (!file || !this.selectedMaintenanceId) {
        event.target.value = '';
        return;
      }

      const validation = this.validateCsvFile(file);
      if (!validation.valid) {
        this.showMessage(validation.error, 'error');
        event.target.value = '';
        return;
      }

      this.uplinkLoading = true;
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
        this.showMessage('匯入失敗，請檢查網路連線', 'error');
      } finally {
        this.uplinkLoading = false;
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

      // 驗證主機名稱
      const hostnameCheck = this.validateHostname(this.newUplink.hostname);
      if (!hostnameCheck.valid) {
        this.showMessage(hostnameCheck.error, 'error');
        return;
      }

      // 驗證鄰居主機名稱
      const neighborCheck = this.validateHostname(this.newUplink.expected_neighbor);
      if (!neighborCheck.valid) {
        this.showMessage(`鄰居${neighborCheck.error}`, 'error');
        return;
      }

      const payload = {
        hostname: this.newUplink.hostname.trim(),
        local_interface: this.newUplink.local_interface.trim(),
        expected_neighbor: this.newUplink.expected_neighbor.trim(),
        expected_interface: this.newUplink.expected_interface?.trim() || null,
        description: this.newUplink.description?.trim() || null,
      };

      try {
        let res;
        
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

    toggleUplinkSelectAll() {
      if (this.uplinkSelectAll) {
        this.selectedUplinks = this.uplinkExpectations.map(u => u.id);
      } else {
        this.selectedUplinks = [];
      }
    },

    clearUplinkSelection() {
      this.selectedUplinks = [];
      this.uplinkSelectAll = false;
    },

    async batchDeleteUplinks() {
      if (this.selectedUplinks.length === 0) return;

      const confirmed = await this.showConfirm(
        `確定要刪除選中的 ${this.selectedUplinks.length} 筆 Uplink 期望？`,
        '批量刪除確認'
      );
      if (!confirmed) return;

      try {
        const res = await fetch(`/api/v1/expectations/uplink/${this.selectedMaintenanceId}/batch-delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.selectedUplinks),
        });

        if (res.ok) {
          const data = await res.json();
          this.showMessage(`成功刪除 ${data.deleted_count} 筆 Uplink 期望`, 'success');
          this.clearUplinkSelection();
          await this.loadUplinkList();
        } else {
          this.showMessage('批量刪除失敗', 'error');
        }
      } catch (e) {
        console.error('批量刪除 Uplink 失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    exportUplinkCsv() {
      const params = new URLSearchParams();
      if (this.uplinkSearch) {
        params.append('search', this.uplinkSearch);
      }
      const url = `/api/v1/expectations/uplink/${this.selectedMaintenanceId}/export-csv?${params}`;
      window.open(url, '_blank');
    },

    // ========== 版本期望操作 ==========
    async loadVersionList() {
      if (!this.selectedMaintenanceId) return;

      // 保存捲動位置
      const scrollTop = this.$refs.versionScrollContainer?.scrollTop || 0;

      try {
        const params = new URLSearchParams();
        if (this.versionSearch) params.append('search', this.versionSearch);

        let url = `/api/v1/expectations/version/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();

        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          this.versionExpectations = data.items || [];
          // 恢復捲動位置
          this.$nextTick(() => {
            if (this.$refs.versionScrollContainer) {
              this.$refs.versionScrollContainer.scrollTop = scrollTop;
            }
          });
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
      if (!file || !this.selectedMaintenanceId) {
        event.target.value = '';
        return;
      }

      const validation = this.validateCsvFile(file);
      if (!validation.valid) {
        this.showMessage(validation.error, 'error');
        event.target.value = '';
        return;
      }

      this.versionLoading = true;
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
        this.showMessage('匯入失敗，請檢查網路連線', 'error');
      } finally {
        this.versionLoading = false;
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

    toggleVersionSelectAll() {
      if (this.versionSelectAll) {
        this.selectedVersions = this.versionExpectations.map(v => v.id);
      } else {
        this.selectedVersions = [];
      }
    },

    clearVersionSelection() {
      this.selectedVersions = [];
      this.versionSelectAll = false;
    },

    async batchDeleteVersions() {
      if (this.selectedVersions.length === 0) return;

      const confirmed = await this.showConfirm(
        `確定要刪除選中的 ${this.selectedVersions.length} 筆版本期望？`,
        '批量刪除確認'
      );
      if (!confirmed) return;

      try {
        const res = await fetch(`/api/v1/expectations/version/${this.selectedMaintenanceId}/batch-delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.selectedVersions),
        });

        if (res.ok) {
          const data = await res.json();
          this.showMessage(`成功刪除 ${data.deleted_count} 筆版本期望`, 'success');
          this.clearVersionSelection();
          await this.loadVersionList();
        } else {
          this.showMessage('批量刪除失敗', 'error');
        }
      } catch (e) {
        console.error('批量刪除版本期望失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    exportVersionCsv() {
      const params = new URLSearchParams();
      if (this.versionSearch) {
        params.append('search', this.versionSearch);
      }
      const url = `/api/v1/expectations/version/${this.selectedMaintenanceId}/export-csv?${params}`;
      window.open(url, '_blank');
    },

    // ========== Port Channel 期望操作 ==========
    async loadPortChannelList() {
      if (!this.selectedMaintenanceId) return;

      // 保存捲動位置
      const scrollTop = this.$refs.portChannelScrollContainer?.scrollTop || 0;

      try {
        const params = new URLSearchParams();
        if (this.portChannelSearch) params.append('search', this.portChannelSearch);

        let url = `/api/v1/expectations/port-channel/${this.selectedMaintenanceId}`;
        if (params.toString()) url += '?' + params.toString();

        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          this.portChannelExpectations = data.items || [];
          // 恢復捲動位置
          this.$nextTick(() => {
            if (this.$refs.portChannelScrollContainer) {
              this.$refs.portChannelScrollContainer.scrollTop = scrollTop;
            }
          });
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
      if (!file || !this.selectedMaintenanceId) {
        event.target.value = '';
        return;
      }

      const validation = this.validateCsvFile(file);
      if (!validation.valid) {
        this.showMessage(validation.error, 'error');
        event.target.value = '';
        return;
      }

      this.portChannelLoading = true;
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
        this.showMessage('匯入失敗，請檢查網路連線', 'error');
      } finally {
        this.portChannelLoading = false;
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

    togglePortChannelSelectAll() {
      if (this.portChannelSelectAll) {
        this.selectedPortChannels = this.portChannelExpectations.map(pc => pc.id);
      } else {
        this.selectedPortChannels = [];
      }
    },

    clearPortChannelSelection() {
      this.selectedPortChannels = [];
      this.portChannelSelectAll = false;
    },

    async batchDeletePortChannels() {
      if (this.selectedPortChannels.length === 0) return;

      const confirmed = await this.showConfirm(
        `確定要刪除選中的 ${this.selectedPortChannels.length} 筆 Port Channel 期望？`,
        '批量刪除確認'
      );
      if (!confirmed) return;

      try {
        const res = await fetch(`/api/v1/expectations/port-channel/${this.selectedMaintenanceId}/batch-delete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.selectedPortChannels),
        });

        if (res.ok) {
          const data = await res.json();
          this.showMessage(`成功刪除 ${data.deleted_count} 筆 Port Channel 期望`, 'success');
          this.clearPortChannelSelection();
          await this.loadPortChannelList();
        } else {
          this.showMessage('批量刪除失敗', 'error');
        }
      } catch (e) {
        console.error('批量刪除 Port Channel 失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    exportPortChannelCsv() {
      const params = new URLSearchParams();
      if (this.portChannelSearch) {
        params.append('search', this.portChannelSearch);
      }
      const url = `/api/v1/expectations/port-channel/${this.selectedMaintenanceId}/export-csv?${params}`;
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

    // ========== Uplink 期望操作 ==========
  },
};
</script>
