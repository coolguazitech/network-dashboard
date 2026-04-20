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

    <!-- 內容區載入遮罩 -->
    <div v-if="loading" class="fixed top-14 left-0 right-0 bottom-0 bg-slate-950/60 backdrop-blur-[2px] flex items-center justify-center z-40">
      <div class="flex flex-col items-center gap-4 px-8 py-6 rounded-2xl bg-slate-800/80 border border-slate-700/50 shadow-2xl">
        <div class="relative h-10 w-10">
          <div class="absolute inset-0 rounded-full border-2 border-slate-700"></div>
          <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-cyan-400 animate-spin"></div>
        </div>
        <span class="text-slate-300 text-sm tracking-wide">載入中...</span>
      </div>
    </div>

    <!-- Tab 內容 -->
    <div class="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-600/40 p-4">
      <!-- Uplink 期望 Tab (歲修特定) -->
      <div v-if="activeTab === 'uplink'" class="space-y-4">
        <div class="flex justify-between items-center">
          <div class="flex items-center gap-2">
            <h3 class="text-white font-semibold">Uplink 期望</h3>
            <div class="relative group/info">
              <svg class="w-[18px] h-[18px] text-slate-500 group-hover/info:text-amber-400 transition cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div class="absolute left-0 top-full mt-2 w-80 px-4 py-3 bg-amber-50 border border-amber-300 rounded-lg shadow-lg text-sm text-amber-900 leading-relaxed opacity-0 invisible group-hover/info:opacity-100 group-hover/info:visible transition-all duration-200 z-50 pointer-events-none"
                style="filter: drop-shadow(0 2px 8px rgba(217, 160, 0, 0.2));"
              >
                <div class="absolute left-4 -top-[6px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-300"></div>
                <div class="absolute left-4 -top-[5px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-50"></div>
                <p class="mb-1 font-semibold">Uplink 期望說明</p>
                <p>設定每台新設備的上聯鄰居期望，用於驗收時比對 CDP/LLDP 鄰居資訊。本地設備與鄰居設備都必須來自設備清單中的「新設備」。</p>
                <p class="mt-2 font-medium">CSV 匯入格式：</p>
                <p class="font-mono text-xs mt-0.5">hostname*, local_interface*, expected_neighbor*, expected_interface*, description</p>
              </div>
            </div>
          </div>
          <div class="flex gap-2">
            <button @click="downloadUplinkTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded-lg transition">
              📄 下載範本
            </button>
            <label v-if="userCanWrite" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded-lg transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importUplinkList" />
            </label>
            <button v-if="userCanWrite" @click="startGnmsTopologyWizard" class="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-sm rounded-lg transition">
              🔄 從 GNMS 匯入
            </button>
            <button v-if="userCanWrite" @click="openAddUplink" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded-lg transition">
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
              class="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              @input="debouncedLoadUplinkList"
            />
            <button @click="exportUplinkCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition">
              📤 匯出 CSV
            </button>
          </div>

          <!-- 批量操作 -->
          <div v-if="selectedUplinks.length > 0 && userCanWrite" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded-xl border border-cyan-700/40">
            <span class="text-sm text-cyan-300">已選 {{ selectedUplinks.length }} 筆</span>
            <button @click="batchDeleteUplinks" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded-lg transition">
              🗑️ 批量刪除
            </button>
            <button @click="clearUplinkSelection" class="px-2 py-1 text-slate-400 hover:text-white text-sm">
              ✕ 清除選擇
            </button>
          </div>

          <div ref="uplinkScrollContainer" class="overflow-x-auto max-h-[600px] overflow-y-auto">
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
                  <th v-if="userCanWrite" class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="(uplink, ui) in uplinkExpectations" :key="uplink.id" class="hover:bg-slate-700/50 transition row-stagger" :class="{ 'bg-cyan-900/20': selectedUplinks.includes(uplink.id) }" :style="{ animationDelay: ui * 30 + 'ms' }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="uplink.id" v-model="selectedUplinks" class="rounded border-slate-500" />
                  </td>
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs break-all">{{ uplink.hostname }}</td>
                  <td class="px-3 py-2 font-mono text-slate-300 text-xs">{{ uplink.local_interface }}</td>
                  <td class="px-3 py-2 font-mono text-cyan-300 text-xs">{{ uplink.expected_neighbor }}</td>
                  <td class="px-3 py-2 font-mono text-slate-300 text-xs">{{ uplink.expected_interface || '-' }}</td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ uplink.description || '-' }}</td>
                  <td v-if="userCanWrite" class="px-3 py-2 text-xs whitespace-nowrap">
                    <button @click="editUplink(uplink)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button @click="deleteUplink(uplink)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="uplinkExpectations.length === 0 && !loading">
                  <td colspan="7" class="px-4 py-8 text-center text-slate-500">尚無 Uplink 期望</td>
                </tr>
              </tbody>
            </table>
          </div>
          
        </div>
      </div>

      <!-- Version 期望 Tab (歲修特定) -->
      <div v-if="activeTab === 'version'" class="space-y-4">
        <div class="flex justify-between items-center">
          <div class="flex items-center gap-2">
            <h3 class="text-white font-semibold">Version 期望</h3>
            <div class="relative group/info">
              <svg class="w-[18px] h-[18px] text-slate-500 group-hover/info:text-amber-400 transition cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div class="absolute left-0 top-full mt-2 w-80 px-4 py-3 bg-amber-50 border border-amber-300 rounded-lg shadow-lg text-sm text-amber-900 leading-relaxed opacity-0 invisible group-hover/info:opacity-100 group-hover/info:visible transition-all duration-200 z-50 pointer-events-none"
                style="filter: drop-shadow(0 2px 8px rgba(217, 160, 0, 0.2));"
              >
                <div class="absolute left-4 -top-[6px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-300"></div>
                <div class="absolute left-4 -top-[5px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-50"></div>
                <p class="mb-1 font-semibold">Version 期望說明</p>
                <p>設定每台新設備的預期韌體版本，驗收時比對實際版本是否符合。可設定多個可接受版本，符合任一即通過。</p>
                <p class="mt-2 font-medium">CSV 匯入格式：</p>
                <p class="font-mono text-xs mt-0.5">hostname, expected_versions, description</p>
                <p class="text-xs mt-0.5">多版本用分號分隔，如 16.10.1;16.10.2</p>
              </div>
            </div>
          </div>
          <div class="flex gap-2">
            <button @click="downloadVersionTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded-lg transition">
              📄 下載範本
            </button>
            <label v-if="userCanWrite" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded-lg transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importVersionList" />
            </label>
            <button v-if="userCanWrite" @click="openAddVersion" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded-lg transition">
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
              class="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              @input="debouncedLoadVersionList"
            />
            <button @click="exportVersionCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition">
              📤 匯出 CSV
            </button>
          </div>

          <!-- 批量操作 -->
          <div v-if="selectedVersions.length > 0 && userCanWrite" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded-xl border border-cyan-700/40">
            <span class="text-sm text-cyan-300">已選 {{ selectedVersions.length }} 筆</span>
            <button @click="batchDeleteVersions" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded-lg transition">
              🗑️ 批量刪除
            </button>
            <button @click="clearVersionSelection" class="px-2 py-1 text-slate-400 hover:text-white text-sm">
              ✕ 清除選擇
            </button>
          </div>

          <div ref="versionScrollContainer" class="overflow-x-auto max-h-[600px] overflow-y-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center">
                    <input type="checkbox" v-model="versionSelectAll" @change="toggleVersionSelectAll" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">目標版本</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">備註</th>
                  <th v-if="userCanWrite" class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="(ver, vi) in versionExpectations" :key="ver.id" class="hover:bg-slate-700/50 transition row-stagger" :class="{ 'bg-cyan-900/20': selectedVersions.includes(ver.id) }" :style="{ animationDelay: vi * 30 + 'ms' }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="ver.id" v-model="selectedVersions" class="rounded border-slate-500" />
                  </td>
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs break-all">{{ ver.hostname }}</td>
                  <td class="px-3 py-2 text-xs">
                    <span v-for="(v, i) in (ver.expected_versions_list || (ver.expected_versions || '').split(';'))" :key="i" class="inline-block px-2 py-0.5 bg-green-600/30 text-green-300 rounded mr-1 mb-1">
                      {{ v }}
                    </span>
                  </td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ ver.description || '-' }}</td>
                  <td v-if="userCanWrite" class="px-3 py-2 text-xs whitespace-nowrap">
                    <button @click="editVersion(ver)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button @click="deleteVersion(ver)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="versionExpectations.length === 0 && !loading">
                  <td colspan="5" class="px-4 py-8 text-center text-slate-500">尚無 Version 期望</td>
                </tr>
              </tbody>
            </table>
          </div>
          
        </div>
      </div>

      <!-- Port Channel 期望 Tab (歲修特定) -->
      <div v-if="activeTab === 'portchannel'" class="space-y-4">
        <div class="flex justify-between items-center">
          <div class="flex items-center gap-2">
            <h3 class="text-white font-semibold">Port Channel 期望</h3>
            <div class="relative group/info">
              <svg class="w-[18px] h-[18px] text-slate-500 group-hover/info:text-amber-400 transition cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div class="absolute left-0 top-full mt-2 w-80 px-4 py-3 bg-amber-50 border border-amber-300 rounded-lg shadow-lg text-sm text-amber-900 leading-relaxed opacity-0 invisible group-hover/info:opacity-100 group-hover/info:visible transition-all duration-200 z-50 pointer-events-none"
                style="filter: drop-shadow(0 2px 8px rgba(217, 160, 0, 0.2));"
              >
                <div class="absolute left-4 -top-[6px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-300"></div>
                <div class="absolute left-4 -top-[5px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-50"></div>
                <p class="mb-1 font-semibold">Port Channel 期望說明</p>
                <p>設定每台新設備的 Port-Channel 期望，驗收時檢查 Port-Channel 是否存在、狀態是否為 UP、成員埠是否齊全。</p>
                <p class="mt-2 font-medium">CSV 匯入格式：</p>
                <p class="font-mono text-xs mt-0.5">hostname, port_channel, member_interfaces, description</p>
                <p class="text-xs mt-0.5">成員介面用分號分隔，如 Gi1/0/1;Gi1/0/2</p>
              </div>
            </div>
          </div>
          <div class="flex gap-2">
            <button @click="downloadPortChannelTemplate" class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-sm rounded-lg transition">
              📄 下載範本
            </button>
            <label v-if="userCanWrite" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded-lg transition cursor-pointer">
              📥 匯入 CSV
              <input type="file" accept=".csv" class="hidden" @change="importPortChannelList" />
            </label>
            <button v-if="userCanWrite" @click="openAddPortChannel" class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded-lg transition">
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
              class="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              @input="debouncedLoadPortChannelList"
            />
            <button @click="exportPortChannelCsv" class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded-lg transition">
              📤 匯出 CSV
            </button>
          </div>

          <!-- 批量操作 -->
          <div v-if="selectedPortChannels.length > 0 && userCanWrite" class="flex items-center gap-2 mb-3 p-2 bg-cyan-900/20 rounded-xl border border-cyan-700/40">
            <span class="text-sm text-cyan-300">已選 {{ selectedPortChannels.length }} 筆</span>
            <button @click="batchDeletePortChannels" class="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white text-sm rounded-lg transition">
              🗑️ 批量刪除
            </button>
            <button @click="clearPortChannelSelection" class="px-2 py-1 text-slate-400 hover:text-white text-sm">
              ✕ 清除選擇
            </button>
          </div>

          <div ref="portChannelScrollContainer" class="overflow-x-auto max-h-[600px] overflow-y-auto">
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
                  <th v-if="userCanWrite" class="px-3 py-2 text-left text-xs font-medium text-slate-400 uppercase">操作</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700">
                <tr v-for="(pc, pi) in portChannelExpectations" :key="pc.id" class="hover:bg-slate-700/50 transition row-stagger" :class="{ 'bg-cyan-900/20': selectedPortChannels.includes(pc.id) }" :style="{ animationDelay: pi * 30 + 'ms' }">
                  <td class="px-2 py-2 text-center">
                    <input type="checkbox" :value="pc.id" v-model="selectedPortChannels" class="rounded border-slate-500" />
                  </td>
                  <td class="px-3 py-2 font-mono text-slate-200 text-xs break-all">{{ pc.hostname }}</td>
                  <td class="px-3 py-2 font-mono text-cyan-300 text-xs">{{ pc.port_channel }}</td>
                  <td class="px-3 py-2 text-xs">
                    <span v-for="(m, i) in (pc.member_interfaces_list || (pc.member_interfaces || '').split(';'))" :key="i" class="inline-block px-2 py-0.5 bg-purple-600/30 text-purple-300 rounded mr-1 mb-1">
                      {{ m }}
                    </span>
                  </td>
                  <td class="px-3 py-2 text-slate-400 text-xs">{{ pc.description || '-' }}</td>
                  <td v-if="userCanWrite" class="px-3 py-2 text-xs whitespace-nowrap">
                    <button @click="editPortChannel(pc)" class="text-cyan-400 hover:text-cyan-300 mr-2">編輯</button>
                    <button @click="deletePortChannel(pc)" class="text-red-400 hover:text-red-300">刪除</button>
                  </td>
                </tr>
                <tr v-if="portChannelExpectations.length === 0 && !loading">
                  <td colspan="6" class="px-4 py-8 text-center text-slate-500">尚無 Port Channel 期望</td>
                </tr>
              </tbody>
            </table>
          </div>
          
        </div>
      </div>
    </div>

    <!-- 新增/編輯 Uplink 期望 Modal -->
    <Transition name="modal">
    <div v-if="showAddUplinkModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" @mousedown.self="closeUplinkModal">
      <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-[500px] modal-content">
        <h3 class="text-lg font-semibold text-white mb-4">{{ editingUplink ? '編輯 Uplink 期望' : '新增 Uplink 期望' }}</h3>
        <p class="text-xs text-yellow-400 mb-4">注意：本地設備與鄰居設備都必須來自設備清單中的「新設備」</p>
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-slate-400 mb-1">設備 Hostname <span class="text-red-400">*</span></label>
            <input v-model="newUplink.hostname" type="text" placeholder="輸入新設備名稱" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">本地介面 <span class="text-red-400">*</span></label>
            <input v-model="newUplink.local_interface" type="text" placeholder="Gi1/0/1" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">預期鄰居 <span class="text-red-400">*</span></label>
            <input v-model="newUplink.expected_neighbor" type="text" placeholder="輸入新設備名稱" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">鄰居介面 <span class="text-red-400">*</span></label>
            <input v-model="newUplink.expected_interface" type="text" placeholder="Gi1/0/48" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">備註（選填）</label>
            <input v-model="newUplink.description" type="text" placeholder="例如：上聯到核心" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="closeUplinkModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded-lg">取消</button>
          <button @click="saveUplink" :disabled="!newUplink.hostname || !newUplink.local_interface || !newUplink.expected_neighbor || !newUplink.expected_interface" class="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingUplink ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>
    </Transition>

    <!-- 新增/編輯 Version 期望 Modal -->
    <Transition name="modal">
    <div v-if="showAddVersionModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" @mousedown.self="closeVersionModal">
      <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-[500px] modal-content">
        <h3 class="text-lg font-semibold text-white mb-4">{{ editingVersion ? '編輯 Version 期望' : '新增 Version 期望' }}</h3>
        <p class="text-xs text-yellow-400 mb-4">注意：設備 Hostname 必須來自設備清單中的「新設備」</p>
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-slate-400 mb-1">設備 Hostname <span class="text-red-400">*</span></label>
            <input v-model="newVersion.hostname" type="text" placeholder="SW-001" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">目標版本 <span class="text-red-400">*</span></label>
            <input v-model="newVersion.expected_versions" type="text" placeholder="16.10.1;16.10.2" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
            <p class="text-xs text-slate-500 mt-1">多版本用分號分隔，符合任一版本即可</p>
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">備註（選填）</label>
            <input v-model="newVersion.description" type="text" placeholder="例如：可接受的版本範圍" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="closeVersionModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded-lg">取消</button>
          <button @click="saveVersion" :disabled="!newVersion.hostname || !newVersion.expected_versions" class="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingVersion ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>
    </Transition>

    <!-- 新增/編輯 Port Channel 期望 Modal -->
    <Transition name="modal">
    <div v-if="showAddPortChannelModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" @mousedown.self="closePortChannelModal">
      <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-[500px] modal-content">
        <h3 class="text-lg font-semibold text-white mb-4">{{ editingPortChannel ? '編輯 Port Channel 期望' : '新增 Port Channel 期望' }}</h3>
        <p class="text-xs text-yellow-400 mb-4">注意：設備 Hostname 必須來自設備清單中的「新設備」</p>
        <div class="space-y-4">
          <div>
            <label class="block text-sm text-slate-400 mb-1">設備 Hostname <span class="text-red-400">*</span></label>
            <input v-model="newPortChannel.hostname" type="text" placeholder="SW-001" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">Port-Channel 名稱 <span class="text-red-400">*</span></label>
            <input v-model="newPortChannel.port_channel" type="text" placeholder="Po1 或 Port-channel1" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">成員介面 <span class="text-red-400">*</span></label>
            <input v-model="newPortChannel.member_interfaces" type="text" placeholder="Gi1/0/1;Gi1/0/2" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
            <p class="text-xs text-slate-500 mt-1">多個介面用分號分隔</p>
          </div>
          <div>
            <label class="block text-sm text-slate-400 mb-1">備註（選填）</label>
            <input v-model="newPortChannel.description" type="text" placeholder="例如：上聯 LACP" class="w-full px-3 py-2 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm" />
          </div>
        </div>
        <div class="flex justify-end gap-2 mt-6">
          <button @click="closePortChannelModal" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded-lg">取消</button>
          <button @click="savePortChannel" :disabled="!newPortChannel.hostname || !newPortChannel.port_channel || !newPortChannel.member_interfaces" class="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
            {{ editingPortChannel ? '儲存' : '新增' }}
          </button>
        </div>
      </div>
    </div>
    </Transition>

    <!-- GNMS Topology Uplink 匯入精靈 Modal -->
    <Transition name="modal">
    <div v-if="gnmsTopoWizard.show" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" @mousedown.self="closeGnmsTopoWizard">
      <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-[750px] max-h-[85vh] flex flex-col">

        <!-- Header + 步驟指示 -->
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-lg font-semibold text-white">從 GNMS 匯入 Uplink 期望</h3>
          <div class="flex items-center gap-1 text-xs">
            <span v-for="s in 4" :key="s"
              class="w-6 h-6 rounded-full flex items-center justify-center font-bold transition"
              :class="s === gnmsTopoWizard.step
                ? 'bg-cyan-500 text-white'
                : s < gnmsTopoWizard.step ? 'bg-green-600 text-white' : 'bg-slate-700 text-slate-400'"
            >{{ s < gnmsTopoWizard.step ? '✓' : s }}</span>
          </div>
        </div>

        <!-- Step 1: 確認開始 -->
        <div v-if="gnmsTopoWizard.step === 1" class="flex-1 space-y-4">
          <p class="text-slate-300">系統將根據設備清單，從 GNMS Topology API 批次查詢每台設備的鄰居拓樸，自動篩選出 Uplink 連線作為期望值匯入。</p>
          <div class="bg-slate-900/60 rounded-lg p-4 space-y-2 text-sm">
            <div class="flex justify-between"><span class="text-slate-400">歲修 ID</span><span class="text-white font-mono">{{ selectedMaintenanceId }}</span></div>
            <div class="flex justify-between"><span class="text-slate-400">設備數</span><span class="text-white">{{ gnmsTopoWizard.deviceTotal }} 台</span></div>
            <div class="flex justify-between"><span class="text-slate-400">每批上限</span><span class="text-white">100 台</span></div>
            <div class="flex justify-between"><span class="text-slate-400">預計批次</span><span class="text-white">{{ Math.ceil(gnmsTopoWizard.deviceTotal / 100) || 0 }} 批</span></div>
          </div>
          <div class="bg-blue-900/20 rounded-lg p-3 text-sm text-blue-300 border border-blue-700/40">
            💡 適用場景：歲修未更換設備，Uplink 連線與現行完全一致，可直接以當前拓樸作為期望值。
          </div>
          <div v-if="gnmsTopoWizard.deviceTotal === 0" class="text-amber-400 text-sm bg-amber-900/20 rounded-lg p-3">
            ⚠ 設備清單為空，請先匯入設備後再使用此功能。
          </div>
        </div>

        <!-- Step 2: 載入中 -->
        <div v-if="gnmsTopoWizard.step === 2" class="flex-1 flex flex-col items-center justify-center py-8">
          <div class="relative h-12 w-12 mb-4">
            <div class="absolute inset-0 rounded-full border-2 border-slate-700"></div>
            <div class="absolute inset-0 rounded-full border-2 border-transparent border-t-cyan-400 animate-spin"></div>
          </div>
          <p class="text-slate-300 mb-1">正在查詢 GNMS Topology API...</p>
          <p class="text-sm text-slate-500">第 {{ gnmsTopoWizard.batchIndex + 1 }} / {{ gnmsTopoWizard.totalBatches }} 批</p>
        </div>

        <!-- Step 3: 批次完成中間狀態 -->
        <div v-if="gnmsTopoWizard.step === 3 && gnmsTopoWizard.batchDone" class="flex-1 flex flex-col items-center justify-center py-6 space-y-4">
          <div class="text-3xl">✅</div>
          <p class="text-white font-semibold">第 {{ gnmsTopoWizard.batchIndex + 1 }} / {{ gnmsTopoWizard.totalBatches }} 批匯入完成</p>
          <div class="bg-slate-900/60 rounded-lg p-4 space-y-1 text-sm w-full max-w-xs">
            <div class="flex justify-between"><span class="text-slate-400">本批新增</span><span class="text-green-400 font-bold">{{ gnmsTopoWizard.batchImported }}</span></div>
            <div class="flex justify-between"><span class="text-slate-400">本批更新</span><span class="text-blue-400">{{ gnmsTopoWizard.batchUpdated }}</span></div>
            <div class="flex justify-between border-t border-slate-700 pt-1 mt-1"><span class="text-slate-400">累計新增</span><span class="text-white font-bold">{{ gnmsTopoWizard.totalImported }}</span></div>
            <div class="flex justify-between"><span class="text-slate-400">累計更新</span><span class="text-white">{{ gnmsTopoWizard.totalUpdated }}</span></div>
          </div>
        </div>

        <!-- Step 3: 檢視/篩選 entries -->
        <div v-if="gnmsTopoWizard.step === 3 && !gnmsTopoWizard.batchDone" class="flex-1 overflow-hidden flex flex-col space-y-3">
          <div class="flex items-center justify-between">
            <p class="text-sm text-slate-400">
              第 <span class="text-white font-bold">{{ gnmsTopoWizard.batchIndex + 1 }}</span> / {{ gnmsTopoWizard.totalBatches }} 批
              — 共 <span class="text-white font-bold">{{ gnmsTopoWizard.allEntries.length }}</span> 筆 Uplink
            </p>
          </div>

          <!-- 搜尋 -->
          <div class="flex items-center gap-2">
            <input
              v-model="gnmsTopoWizard.search"
              type="text"
              placeholder="篩選設備或鄰居名稱..."
              class="flex-1 px-3 py-1.5 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
            />
            <button
              @click="gnmsTopoSelectAll"
              class="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs rounded-lg transition whitespace-nowrap"
            >全選 ({{ gnmsTopoFilteredEntries.length }})</button>
            <button
              @click="gnmsTopoWizard.selectedEntries = []"
              class="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 text-xs rounded-lg transition whitespace-nowrap"
            >清除</button>
          </div>

          <div v-if="gnmsTopoWizard.selectedEntries.length > 0" class="flex items-center gap-2 p-2 bg-cyan-900/20 rounded-lg border border-cyan-700/40 text-sm">
            <span class="text-cyan-300">已選 <b>{{ gnmsTopoWizard.selectedEntries.length }}</b> 筆 Uplink 期望</span>
          </div>

          <!-- Uplink 清單表格 -->
          <div class="overflow-y-auto max-h-[320px] rounded-lg border border-slate-700">
            <table class="min-w-full text-sm">
              <thead class="bg-slate-900/60 sticky top-0">
                <tr>
                  <th class="px-2 py-2 text-center w-8">
                    <input type="checkbox" :checked="gnmsTopoFilteredEntries.length > 0 && gnmsTopoFilteredEntries.every(e => gnmsTopoWizard.selectedEntries.includes(gnmsTopoEntryKey(e)))" @change="gnmsTopoToggleAll" class="rounded border-slate-500" />
                  </th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400">本地設備</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400">本地介面</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400">遠端鄰居</th>
                  <th class="px-3 py-2 text-left text-xs font-medium text-slate-400">遠端介面</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-700/50">
                <tr v-for="entry in gnmsTopoFilteredEntries" :key="gnmsTopoEntryKey(entry)"
                    class="hover:bg-slate-700/30 transition cursor-pointer"
                    :class="{ 'bg-cyan-900/15': gnmsTopoWizard.selectedEntries.includes(gnmsTopoEntryKey(entry)) }"
                    @click="gnmsTopoToggleEntry(entry)">
                  <td class="px-2 py-1.5 text-center" @click.stop>
                    <input type="checkbox" :checked="gnmsTopoWizard.selectedEntries.includes(gnmsTopoEntryKey(entry))" @change="gnmsTopoToggleEntry(entry)" class="rounded border-slate-500" />
                  </td>
                  <td class="px-3 py-1.5 text-white font-mono text-xs">{{ entry.hostname }}</td>
                  <td class="px-3 py-1.5 text-slate-300 font-mono text-xs">{{ entry.local_interface }}</td>
                  <td class="px-3 py-1.5 text-cyan-300 font-mono text-xs">{{ entry.expected_neighbor }}</td>
                  <td class="px-3 py-1.5 text-slate-300 font-mono text-xs">{{ entry.expected_interface || '-' }}</td>
                </tr>
                <tr v-if="gnmsTopoFilteredEntries.length === 0">
                  <td colspan="5" class="px-4 py-6 text-center text-slate-500">
                    {{ gnmsTopoWizard.allEntries.length === 0 ? '此批設備無 Uplink 連線' : '無符合篩選條件的結果' }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Step 4: 匯入完成 -->
        <div v-if="gnmsTopoWizard.step === 4" class="flex-1 space-y-4">
          <div class="text-center py-4">
            <div class="text-4xl mb-2">✅</div>
            <p class="text-lg text-white font-semibold">匯入完成</p>
          </div>
          <div class="bg-slate-900/60 rounded-lg p-4 space-y-2 text-sm">
            <div class="flex justify-between"><span class="text-slate-400">新增</span><span class="text-green-400 font-bold">{{ gnmsTopoWizard.totalImported }} 筆</span></div>
            <div class="flex justify-between"><span class="text-slate-400">更新</span><span class="text-blue-400 font-bold">{{ gnmsTopoWizard.totalUpdated }} 筆</span></div>
            <div v-if="gnmsTopoWizard.totalErrors.length" class="flex justify-between"><span class="text-slate-400">錯誤</span><span class="text-red-400">{{ gnmsTopoWizard.totalErrors.length }} 筆</span></div>
          </div>
          <div v-if="gnmsTopoWizard.totalErrors.length" class="max-h-[150px] overflow-y-auto rounded-lg border border-red-800/40 p-3">
            <p v-for="(err, i) in gnmsTopoWizard.totalErrors.slice(0, 20)" :key="i" class="text-xs text-red-400 font-mono">{{ err }}</p>
            <p v-if="gnmsTopoWizard.totalErrors.length > 20" class="text-xs text-slate-500 mt-1">... 還有 {{ gnmsTopoWizard.totalErrors.length - 20 }} 筆錯誤</p>
          </div>
        </div>

        <!-- Footer 按鈕 -->
        <div class="flex justify-between items-center mt-5 pt-4 border-t border-slate-700">
          <button @click="closeGnmsTopoWizard" class="px-4 py-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition text-sm">
            {{ gnmsTopoWizard.step === 4 ? '關閉' : '取消' }}
          </button>
          <div class="flex gap-2">
            <button v-if="gnmsTopoWizard.step === 1 && gnmsTopoWizard.deviceTotal > 0"
              @click="gnmsTopoFetchBatch"
              class="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 transition text-sm">
              開始查詢
            </button>
            <button v-if="gnmsTopoWizard.step === 3 && !gnmsTopoWizard.batchDone"
              @click="gnmsTopoSkipBatch"
              class="px-4 py-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition text-sm">
              {{ gnmsTopoWizard.batchIndex + 1 < gnmsTopoWizard.totalBatches ? '跳過此批 ▸' : '跳過並完成' }}
            </button>
            <button v-if="gnmsTopoWizard.step === 3 && !gnmsTopoWizard.batchDone"
              @click="gnmsTopoImportBatch"
              :disabled="gnmsTopoWizard.loading || gnmsTopoWizard.selectedEntries.length === 0"
              class="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 transition text-sm disabled:opacity-50">
              匯入選取 ({{ gnmsTopoWizard.selectedEntries.length }})
            </button>
            <button v-if="gnmsTopoWizard.step === 3 && gnmsTopoWizard.batchDone"
              @click="gnmsTopoAdvanceOrFinish"
              class="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 transition text-sm">
              {{ gnmsTopoWizard.batchIndex + 1 < gnmsTopoWizard.totalBatches ? '繼續下一批 ▸' : '完成' }}
            </button>
            <button v-if="gnmsTopoWizard.step === 4"
              @click="loadUplinkList(); closeGnmsTopoWizard()"
              class="px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-500 transition text-sm">
              完成
            </button>
          </div>
        </div>

      </div>
    </div>
    </Transition>

  </div>
</template>

<script>
import api, { downloadFile } from '@/utils/api';
import { useToast } from '@/composables/useToast';
import { canWrite } from '@/utils/auth';

export default {
  name: 'Settings',
  inject: ['maintenanceId', 'refreshMaintenanceList'],
  setup() {
    return useToast();
  },
  data() {
    return {
      loading: false,
      uplinkLoading: false,
      versionLoading: false,
      portChannelLoading: false,
      activeTab: 'uplink',
      tabs: [
        { id: 'uplink', name: 'Uplink 期望', icon: '🔗', scope: 'maintenance' },
        { id: 'version', name: 'Version 期望', icon: '📦', scope: 'maintenance' },
        { id: 'portchannel', name: 'Port Channel 期望', icon: '⛓️', scope: 'maintenance' },
      ],
      
      // 數據
      maintenanceList: [],
      uplinkExpectations: [],
      versionExpectations: [],
      portChannelExpectations: [],
      
      // Uplink 期望
      uplinkSearch: '',
      selectedUplinks: [],
      uplinkSelectAll: false,

      // Version 期望
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
      
      // Version 期望表單
      newVersion: { hostname: '', expected_versions: '', description: '' },
      editingVersion: null,
      
      // Port Channel 期望表單
      newPortChannel: { hostname: '', port_channel: '', member_interfaces: '', description: '' },
      editingPortChannel: null,


      // 搜尋防抖計時��
      uplinkSearchTimeout: null,
      versionSearchTimeout: null,
      portChannelSearchTimeout: null,

      // GNMS Topology 匯入精靈
      gnmsTopoWizard: {
        show: false,
        step: 1,          // 1=確認, 2=載入中, 3=檢視/篩選, 4=完成
        loading: false,
        deviceTotal: 0,
        batchIndex: 0,
        totalBatches: 0,
        allEntries: [],         // GnmsTopologyUplinkEntry[]
        selectedEntries: [],    // entry key 陣列
        search: '',
        // 累計結果
        totalImported: 0,
        totalUpdated: 0,
        totalErrors: [],
        // 當前批次結果
        batchDone: false,
        batchImported: 0,
        batchUpdated: 0,
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
    gnmsTopoFilteredEntries() {
      const q = (this.gnmsTopoWizard.search || '').trim().toUpperCase();
      if (!q) return this.gnmsTopoWizard.allEntries;
      return this.gnmsTopoWizard.allEntries.filter(e =>
        e.hostname.toUpperCase().includes(q)
        || e.expected_neighbor.toUpperCase().includes(q)
        || e.local_interface.toUpperCase().includes(q)
        || e.expected_interface.toUpperCase().includes(q)
      );
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
  beforeUnmount() {
    this._unmounted = true;
    if (this._abortController) this._abortController.abort();
    clearTimeout(this.uplinkSearchTimeout);
    clearTimeout(this.versionSearchTimeout);
    clearTimeout(this.portChannelSearchTimeout);
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

    // 搜尋防抖方法
    debouncedLoadUplinkList() {
      clearTimeout(this.uplinkSearchTimeout);
      this.uplinkSearchTimeout = setTimeout(() => this.loadUplinkList(), 300);
    },
    debouncedLoadVersionList() {
      clearTimeout(this.versionSearchTimeout);
      this.versionSearchTimeout = setTimeout(() => this.loadVersionList(), 300);
    },
    debouncedLoadPortChannelList() {
      clearTimeout(this.portChannelSearchTimeout);
      this.portChannelSearchTimeout = setTimeout(() => this.loadPortChannelList(), 300);
    },

    // 歲修管理
    async loadMaintenanceList() {
      try {
        const { data } = await api.get('/maintenance');
        this.maintenanceList = data;
      } catch (e) {
        console.error('載入歲修列表失敗:', e);
        this.showMessage('載入失敗，請稍後再試', 'error');
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
        await api.post('/maintenance', { id: idValue, name: nameValue });
        this.showAddMaintenanceModal = false;
        this.newMaintenance = { id: '', name: '' };
        await this.loadMaintenanceList();
        if (this.refreshMaintenanceList) {
          this.refreshMaintenanceList();
        }
      } catch (e) {
        console.error('建立歲修失敗:', e);
        this.showMessage(`建立失敗: ${e.response?.data?.detail || '請稍後再試'}`, 'error');
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
        await api.delete(`/maintenance/${encodeURIComponent(this.deleteTarget.id)}`);
        this.showDeleteMaintenanceModal = false;
        this.deleteTarget = null;
        this.deleteConfirmInput = '';
        await this.loadMaintenanceList();
        if (this.refreshMaintenanceList) {
          this.refreshMaintenanceList();
        }
      } catch (e) {
        console.error('刪除歲修失敗:', e);
        this.showMessage(`刪除失敗: ${e.response?.data?.detail || '請稍後再試'}`, 'error');
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
    
    async loadMaintenanceData() {
      if (!this.selectedMaintenanceId) return;

      // 取消上一次未完成的請求
      if (this._abortController) {
        this._abortController.abort();
      }
      this._abortController = new AbortController();

      this.loading = true;
      try {
        await Promise.all([
          this.loadUplinkList(),
          this.loadVersionList(),
          this.loadPortChannelList(),
        ]);
      } catch (e) {
        if (e?.name !== 'CanceledError') {
          console.error('載入歲修數據失敗:', e);
        }
      } finally {
        this.loading = false;
      }
    },
    
    // ========== Uplink 期望操作 ==========
    async loadUplinkList() {
      if (!this.selectedMaintenanceId) return;

      // 保存捲動位置
      const scrollTop = this.$refs.uplinkScrollContainer?.scrollTop || 0;

      this.uplinkLoading = true;
      try {
        const params = new URLSearchParams();
        if (this.uplinkSearch) params.append('search', this.uplinkSearch);

        let url = `/expectations/uplink/${encodeURIComponent(this.selectedMaintenanceId)}`;
        if (params.toString()) url += '?' + params.toString();

        const { data } = await api.get(url);
        this.uplinkExpectations = data.items || [];
        this.$nextTick(() => {
          if (this.$refs.uplinkScrollContainer) {
            this.$refs.uplinkScrollContainer.scrollTop = scrollTop;
          }
        });
      } catch (e) {
        console.error('載入 Uplink 期望失敗:', e);
      } finally {
        this.uplinkLoading = false;
      }
    },
    
    downloadUplinkTemplate() {
      // 注意：本地設備與鄰居設備都必須來自設備清單中的「新設備」
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
        const { data } = await api.post(`/expectations/uplink/${this.selectedMaintenanceId}/import-csv`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
        await this.loadUplinkList();
        const toastType = (data.total_errors > 0 && data.imported === 0) ? 'error' : 'success';
        this.showMessage(`新增: ${data.imported} 筆\n更新: ${data.updated} 筆\n錯誤: ${data.total_errors} 筆`, toastType, '匯入完成');
      } catch (e) {
        console.error('Uplink 匯入失敗:', e);
        this.showMessage(e.response?.data?.detail || '匯入失敗，請檢查網路連線', 'error');
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
      if (!this.newUplink.hostname || !this.newUplink.local_interface || !this.newUplink.expected_neighbor || !this.newUplink.expected_interface || !this.selectedMaintenanceId) return;

      // 驗證主機名稱格式（後端會驗證是否在新設備清單中）
      const hostnameCheck = this.validateHostname(this.newUplink.hostname);
      if (!hostnameCheck.valid) {
        this.showMessage(hostnameCheck.error, 'error');
        return;
      }

      // 驗證鄰居主機名稱格式（後端會驗證是否在新設備清單中）
      const neighborCheck = this.validateHostname(this.newUplink.expected_neighbor);
      if (!neighborCheck.valid) {
        this.showMessage(`鄰居${neighborCheck.error}`, 'error');
        return;
      }

      const payload = {
        hostname: this.newUplink.hostname.trim(),
        local_interface: this.newUplink.local_interface.trim(),
        expected_neighbor: this.newUplink.expected_neighbor.trim(),
        expected_interface: this.newUplink.expected_interface.trim(),
        description: this.newUplink.description?.trim() || null,
      };

      try {
        if (this.editingUplink && this.newUplink.id) {
          await api.put(`/expectations/uplink/${this.selectedMaintenanceId}/${this.newUplink.id}`, payload);
        } else {
          await api.post(`/expectations/uplink/${this.selectedMaintenanceId}`, payload);
        }
        const msg = this.editingUplink ? 'Uplink 期望更新成功' : 'Uplink 期望新增成功';
        this.closeUplinkModal();
        await this.loadUplinkList();
        this.showMessage(msg, 'success');
      } catch (e) {
        console.error('儲存 Uplink 期望失敗:', e);
        this.showMessage(e.response?.data?.detail || `儲存失敗: ${e.message || '網路錯誤'}`, 'error');
      }
    },
    
    async deleteUplink(uplink) {
      const confirmed = await this.showConfirm(`確定要刪除 ${uplink.hostname}:${uplink.local_interface} 的 Uplink 期望？`, '刪除確認');
      if (!confirmed) return;

      try {
        await api.delete(`/expectations/uplink/${this.selectedMaintenanceId}/${uplink.id}`);
        await this.loadUplinkList();
        this.showMessage('刪除成功', 'success');
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
        const { data } = await api.post(`/expectations/uplink/${this.selectedMaintenanceId}/batch-delete`, { item_ids: this.selectedUplinks });
        this.showMessage(`成功刪除 ${data.deleted_count} 筆 Uplink 期望`, 'success');
        this.clearUplinkSelection();
        await this.loadUplinkList();
      } catch (e) {
        console.error('批量刪除 Uplink 失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    async exportUplinkCsv() {
      const params = new URLSearchParams();
      if (this.uplinkSearch) {
        params.append('search', this.uplinkSearch);
      }
      await downloadFile(
        `/expectations/uplink/${this.selectedMaintenanceId}/export-csv?${params}`,
        `uplink_expectations_${this.selectedMaintenanceId}.csv`,
      );
    },

    // ========== GNMS Topology Uplink 匯入精靈 ==========
    gnmsTopoEntryKey(entry) {
      return `${entry.hostname}::${entry.local_interface}`;
    },

    async startGnmsTopologyWizard() {
      if (!this.selectedMaintenanceId) {
        this.showMessage('請先選擇歲修 ID', 'warning');
        return;
      }

      // 取得設備數
      let deviceTotal = 0;
      try {
        const { data } = await api.get(`/maintenance-devices/${this.selectedMaintenanceId}/stats`);
        deviceTotal = data.total || 0;
      } catch (e) {
        console.error('載入設備統計失敗:', e);
      }

      this.gnmsTopoWizard = {
        show: true,
        step: 1,
        loading: false,
        deviceTotal,
        batchIndex: 0,
        totalBatches: Math.ceil(deviceTotal / 100) || 0,
        allEntries: [],
        selectedEntries: [],
        search: '',
        totalImported: 0,
        totalUpdated: 0,
        totalErrors: [],
        batchDone: false,
        batchImported: 0,
        batchUpdated: 0,
      };
    },

    closeGnmsTopoWizard() {
      this.gnmsTopoWizard.show = false;
    },

    gnmsTopoToggleEntry(entry) {
      const key = this.gnmsTopoEntryKey(entry);
      const idx = this.gnmsTopoWizard.selectedEntries.indexOf(key);
      if (idx >= 0) {
        this.gnmsTopoWizard.selectedEntries.splice(idx, 1);
      } else {
        this.gnmsTopoWizard.selectedEntries.push(key);
      }
    },

    gnmsTopoToggleAll(e) {
      const filtered = this.gnmsTopoFilteredEntries.map(en => this.gnmsTopoEntryKey(en));
      if (e.target.checked) {
        const set = new Set([...this.gnmsTopoWizard.selectedEntries, ...filtered]);
        this.gnmsTopoWizard.selectedEntries = [...set];
      } else {
        const remove = new Set(filtered);
        this.gnmsTopoWizard.selectedEntries = this.gnmsTopoWizard.selectedEntries.filter(k => !remove.has(k));
      }
    },

    gnmsTopoSelectAll() {
      const filtered = this.gnmsTopoFilteredEntries.map(en => this.gnmsTopoEntryKey(en));
      const set = new Set([...this.gnmsTopoWizard.selectedEntries, ...filtered]);
      this.gnmsTopoWizard.selectedEntries = [...set];
    },

    async gnmsTopoFetchBatch() {
      const wiz = this.gnmsTopoWizard;
      wiz.step = 2;
      wiz.loading = true;

      try {
        const { data } = await api.get(
          `/expectations/uplink/${this.selectedMaintenanceId}/gnms-topology-fetch`,
          {
            params: { batch_index: wiz.batchIndex },
            timeout: 120000,
          },
        );
        wiz.totalBatches = data.total_batches;
        // 收集所有 entries
        const entries = [];
        for (const dev of data.devices) {
          entries.push(...dev.entries);
        }
        wiz.allEntries = entries;
        // 預設全選
        wiz.selectedEntries = entries.map(e => this.gnmsTopoEntryKey(e));
        wiz.step = 3;
      } catch (e) {
        const msg = e.response?.data?.detail || e.message || '查詢失敗';
        this.showMessage(`GNMS Topology 查詢失敗：${msg}`, 'error');
        wiz.step = 1;
      } finally {
        wiz.loading = false;
      }
    },

    gnmsTopoAdvanceOrFinish() {
      const wiz = this.gnmsTopoWizard;
      if (wiz.batchIndex + 1 < wiz.totalBatches) {
        wiz.batchIndex = wiz.batchIndex + 1;
        wiz.allEntries = [];
        wiz.selectedEntries = [];
        wiz.search = '';
        wiz.batchDone = false;
        this.gnmsTopoFetchBatch();
      } else {
        wiz.step = 4;
      }
    },

    gnmsTopoSkipBatch() {
      this.gnmsTopoAdvanceOrFinish();
    },

    async gnmsTopoImportBatch() {
      const wiz = this.gnmsTopoWizard;
      const selectedKeys = new Set(wiz.selectedEntries);
      const entriesToImport = wiz.allEntries.filter(e => selectedKeys.has(this.gnmsTopoEntryKey(e)));

      if (entriesToImport.length === 0) {
        this.showMessage('請先勾選要匯入的 Uplink 期望', 'warning');
        return;
      }

      wiz.loading = true;

      try {
        const { data } = await api.post(
          `/expectations/uplink/${this.selectedMaintenanceId}/gnms-topology-import`,
          { entries: entriesToImport },
          { timeout: 60000 },
        );

        // 累計結果
        wiz.totalImported += data.imported;
        wiz.totalUpdated += data.updated;
        wiz.totalErrors.push(...(data.errors || []));
        wiz.batchImported = data.imported;
        wiz.batchUpdated = data.updated;

        wiz.batchDone = true;
      } catch (e) {
        const msg = e.response?.data?.detail || e.message || '匯入失敗';
        this.showMessage(`匯入失敗：${msg}`, 'error');
      } finally {
        wiz.loading = false;
      }
    },

    // ========== Version 期望操作 ==========
    async loadVersionList() {
      if (!this.selectedMaintenanceId) return;

      // 保存捲動位置
      const scrollTop = this.$refs.versionScrollContainer?.scrollTop || 0;

      this.versionLoading = true;
      try {
        const params = new URLSearchParams();
        if (this.versionSearch) params.append('search', this.versionSearch);

        let url = `/expectations/version/${encodeURIComponent(this.selectedMaintenanceId)}`;
        if (params.toString()) url += '?' + params.toString();

        const { data } = await api.get(url);
        this.versionExpectations = data.items || [];
        this.$nextTick(() => {
          if (this.$refs.versionScrollContainer) {
            this.$refs.versionScrollContainer.scrollTop = scrollTop;
          }
        });
      } catch (e) {
        console.error('載入 Version 期望失敗:', e);
      } finally {
        this.versionLoading = false;
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
        const { data } = await api.post(`/expectations/version/${this.selectedMaintenanceId}/import-csv`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
        await this.loadVersionList();
        const toastType = (data.total_errors > 0 && data.imported === 0) ? 'error' : 'success';
        this.showMessage(`新增: ${data.imported} 筆\n更新: ${data.updated} 筆\n錯誤: ${data.total_errors} 筆`, toastType, '匯入完成');
      } catch (e) {
        console.error('Version 期望匯入失敗:', e);
        this.showMessage(e.response?.data?.detail || '匯入失敗，請檢查網路連線', 'error');
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

      // 驗證主機名稱格式
      const hostnameCheck = this.validateHostname(this.newVersion.hostname);
      if (!hostnameCheck.valid) {
        this.showMessage(hostnameCheck.error, 'error');
        return;
      }

      try {
        let res;
        const payload = {
          hostname: this.newVersion.hostname.trim(),
          expected_versions: this.newVersion.expected_versions.trim(),
          description: this.newVersion.description?.trim() || null,
        };
        
        if (this.editingVersion && this.newVersion.id) {
          await api.put(`/expectations/version/${this.selectedMaintenanceId}/${this.newVersion.id}`, payload);
        } else {
          await api.post(`/expectations/version/${this.selectedMaintenanceId}`, payload);
        }
        const msg = this.editingVersion ? 'Version 期望更新成功' : 'Version 期望新增成功';
        this.closeVersionModal();
        await this.loadVersionList();
        this.showMessage(msg, 'success');
      } catch (e) {
        console.error('儲存 Version 期望失敗:', e);
        this.showMessage(e.response?.data?.detail || '儲存失敗', 'error');
      }
    },
    
    async deleteVersion(ver) {
      const confirmed = await this.showConfirm(`確定要刪除 ${ver.hostname} 的 Version 期望？`, '刪除確認');
      if (!confirmed) return;

      try {
        await api.delete(`/expectations/version/${this.selectedMaintenanceId}/${ver.id}`);
        await this.loadVersionList();
        this.showMessage('刪除成功', 'success');
      } catch (e) {
        console.error('刪除 Version 期望失敗:', e);
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
        `確定要刪除選中的 ${this.selectedVersions.length} 筆 Version 期望？`,
        '批量刪除確認'
      );
      if (!confirmed) return;

      try {
        const { data } = await api.post(`/expectations/version/${this.selectedMaintenanceId}/batch-delete`, { item_ids: this.selectedVersions });
        this.showMessage(`成功刪除 ${data.deleted_count} 筆 Version 期望`, 'success');
        this.clearVersionSelection();
        await this.loadVersionList();
      } catch (e) {
        console.error('批量刪除 Version 期望失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    async exportVersionCsv() {
      const params = new URLSearchParams();
      if (this.versionSearch) {
        params.append('search', this.versionSearch);
      }
      await downloadFile(
        `/expectations/version/${this.selectedMaintenanceId}/export-csv?${params}`,
        `version_expectations_${this.selectedMaintenanceId}.csv`,
      );
    },

    // ========== Port Channel 期望操作 ==========
    async loadPortChannelList() {
      if (!this.selectedMaintenanceId) return;

      // 保存捲動位置
      const scrollTop = this.$refs.portChannelScrollContainer?.scrollTop || 0;

      this.portChannelLoading = true;
      try {
        const params = new URLSearchParams();
        if (this.portChannelSearch) params.append('search', this.portChannelSearch);

        let url = `/expectations/port-channel/${encodeURIComponent(this.selectedMaintenanceId)}`;
        if (params.toString()) url += '?' + params.toString();

        const { data } = await api.get(url);
        this.portChannelExpectations = data.items || [];
        this.$nextTick(() => {
          if (this.$refs.portChannelScrollContainer) {
            this.$refs.portChannelScrollContainer.scrollTop = scrollTop;
          }
        });
      } catch (e) {
        console.error('載入 Port Channel 期望失敗:', e);
      } finally {
        this.portChannelLoading = false;
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
        const { data } = await api.post(`/expectations/port-channel/${this.selectedMaintenanceId}/import-csv`, formData, { headers: { 'Content-Type': 'multipart/form-data' } });
        await this.loadPortChannelList();
        const toastType = (data.total_errors > 0 && data.imported === 0) ? 'error' : 'success';
        this.showMessage(`新增: ${data.imported} 筆\n更新: ${data.updated} 筆\n錯誤: ${data.total_errors} 筆`, toastType, '匯入完成');
      } catch (e) {
        console.error('Port-Channel 匯入失敗:', e);
        this.showMessage(e.response?.data?.detail || '匯入失敗，請檢查網路連線', 'error');
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

      // 驗證主機名稱格式
      const hostnameCheck = this.validateHostname(this.newPortChannel.hostname);
      if (!hostnameCheck.valid) {
        this.showMessage(hostnameCheck.error, 'error');
        return;
      }

      try {
        let res;
        const payload = {
          hostname: this.newPortChannel.hostname.trim(),
          port_channel: this.newPortChannel.port_channel.trim(),
          member_interfaces: this.newPortChannel.member_interfaces.trim(),
          description: this.newPortChannel.description?.trim() || null,
        };
        
        if (this.editingPortChannel && this.newPortChannel.id) {
          await api.put(`/expectations/port-channel/${this.selectedMaintenanceId}/${this.newPortChannel.id}`, payload);
        } else {
          await api.post(`/expectations/port-channel/${this.selectedMaintenanceId}`, payload);
        }
        const msg = this.editingPortChannel ? 'Port Channel 期望更新成功' : 'Port Channel 期望新增成功';
        this.closePortChannelModal();
        await this.loadPortChannelList();
        this.showMessage(msg, 'success');
      } catch (e) {
        console.error('儲存 Port Channel 期望失敗:', e);
        this.showMessage(e.response?.data?.detail || '儲存失敗', 'error');
      }
    },
    
    async deletePortChannel(pc) {
      const confirmed = await this.showConfirm(`確定要刪除 ${pc.hostname}:${pc.port_channel} 的 Port Channel 期望？`, '刪除確認');
      if (!confirmed) return;

      try {
        await api.delete(`/expectations/port-channel/${this.selectedMaintenanceId}/${pc.id}`);
        await this.loadPortChannelList();
        this.showMessage('刪除成功', 'success');
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
        const { data } = await api.post(`/expectations/port-channel/${this.selectedMaintenanceId}/batch-delete`, { item_ids: this.selectedPortChannels });
        this.showMessage(`成功刪除 ${data.deleted_count} 筆 Port Channel 期望`, 'success');
        this.clearPortChannelSelection();
        await this.loadPortChannelList();
      } catch (e) {
        console.error('批量刪除 Port Channel 失敗:', e);
        this.showMessage('批量刪除失敗', 'error');
      }
    },

    async exportPortChannelCsv() {
      const params = new URLSearchParams();
      if (this.portChannelSearch) {
        params.append('search', this.portChannelSearch);
      }
      await downloadFile(
        `/expectations/port-channel/${this.selectedMaintenanceId}/export-csv?${params}`,
        `port_channel_expectations_${this.selectedMaintenanceId}.csv`,
      );
    },

    // ========== Uplink 期望操作 ==========
  },
};
</script>
