<template>
  <div class="px-3 py-3">
    <!-- 頁面標題 -->
    <div class="flex justify-between items-center mb-3">
      <div class="flex items-center gap-2">
        <h1 class="text-xl font-bold text-white">案件管理</h1>
        <div class="relative group/info2">
          <svg class="w-[18px] h-[18px] text-slate-500 group-hover/info2:text-amber-400 transition cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div class="absolute left-0 top-full mt-2 w-80 px-4 py-3 bg-amber-50 border border-amber-300 rounded-lg shadow-lg text-sm text-amber-900 leading-relaxed opacity-0 invisible group-hover/info2:opacity-100 group-hover/info2:visible transition-all duration-200 z-50 pointer-events-none"
            style="filter: drop-shadow(0 2px 8px rgba(217, 160, 0, 0.2));"
          >
            <div class="absolute left-4 -top-[6px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-300"></div>
            <div class="absolute left-4 -top-[5px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-50"></div>
            <p class="mb-1 font-semibold">案件管理說明</p>
            <p>系統會對 Client 清單中的 MAC 進行 Ping 檢測，不可達的 MAC 會被建立案件進行追蹤。</p>
            <p class="mt-1.5">Ping 可達且未在「處理中」或「待討論」的案件會自動結案；Ping 不可達時無法手動標記已結案。</p>
          </div>
        </div>
        <span v-if="stats.active" class="text-xs text-slate-500">
          {{ stats.active }} 件進行中
        </span>
      </div>
      <div class="flex items-center gap-2">
        <!-- Info 氣泡 -->
        <div v-if="userCanWrite" class="relative group/info">
          <svg class="w-[18px] h-[18px] text-slate-500 group-hover/info:text-amber-400 transition cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div class="absolute right-0 top-full mt-2 w-80 px-4 py-3 bg-amber-50 border border-amber-300 rounded-lg shadow-lg text-sm text-amber-900 leading-relaxed opacity-0 invisible group-hover/info:opacity-100 group-hover/info:visible transition-all duration-200 z-50 pointer-events-none"
            style="filter: drop-shadow(0 2px 8px rgba(217, 160, 0, 0.2));"
          >
            <div class="absolute right-4 -top-[6px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-300"></div>
            <div class="absolute right-4 -top-[5px] w-0 h-0 border-l-[6px] border-r-[6px] border-b-[6px] border-transparent border-b-amber-50"></div>
            <p class="mb-1 font-semibold">同步案件說明</p>
            <p>匯入 MAC 清單後，點擊「同步案件」會為每個 MAC 自動建立案件。</p>
          </div>
        </div>
        <button
          v-if="userCanWrite"
          @click="syncCases"
          :disabled="syncing"
          class="px-3 py-1.5 bg-cyan-600/90 hover:bg-cyan-500 disabled:bg-slate-800 disabled:text-slate-600 text-white text-xs rounded transition font-medium"
        >
          {{ syncing ? '同步中...' : '同步案件' }}
        </button>
      </div>
    </div>

    <!-- 未選擇歲修 -->
    <div v-if="!selectedMaintenanceId" class="rounded-lg border border-slate-700/30 p-12 text-center">
      <p class="text-slate-500">請先在頂部選擇歲修 ID</p>
    </div>

    <template v-else>
      <!-- 不可達提示（獨立於狀態卡片） -->
      <button
        v-if="(stats.ping_unreachable || 0) > 0"
        @click="applyStatFilter('ping_unreachable')"
        class="card-stagger flex items-center gap-2 mb-3 px-3 py-1.5 rounded-lg text-xs cursor-pointer transition-all duration-300"
        :class="activeStatFilter === 'ping_unreachable'
          ? 'bg-red-500/15 border border-red-500/40 text-red-300'
          : 'bg-red-500/5 border border-red-500/15 text-red-400/80 hover:bg-red-500/10 hover:border-red-500/30'"
      >
        <span class="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse"></span>
        <span>未結案中有 <b class="tabular-nums">{{ stats.ping_unreachable }}</b> 件 Ping 不可達</span>
      </button>

      <!-- 統計指標 -->
      <div class="grid grid-cols-4 gap-3 mb-4">
        <!-- 狀態分布 -->
        <button
          v-for="(stat, si) in statusBreakdown"
          :key="stat.key"
          @click="applyStatFilter(stat.key)"
          class="card-stagger relative bg-slate-800/70 backdrop-blur-sm border rounded-xl p-3 text-center cursor-pointer transition-all duration-300 hover:-translate-y-0.5"
          :style="{ animationDelay: si * 80 + 'ms' }"
          :class="activeStatFilter === stat.key ? stat.borderActive : stat.borderDefault"
        >
          <div class="text-2xl font-bold tabular-nums" :class="stat.color">{{ stat.value }}</div>
          <div class="text-xs text-slate-400 mt-1">{{ stat.label }}</div>
        </button>

        <!-- 已結案 -->
        <button
          @click="applyStatFilter('RESOLVED')"
          class="card-stagger relative bg-slate-800/70 backdrop-blur-sm border rounded-xl p-3 text-center cursor-pointer transition-all duration-300 hover:-translate-y-0.5"
          :style="{ animationDelay: statusBreakdown.length * 80 + 'ms' }"
          :class="activeStatFilter === 'RESOLVED'
            ? 'border-emerald-500/60 ring-1 ring-emerald-500/30 shadow-lg shadow-emerald-500/10'
            : 'border-emerald-500/15 hover:border-emerald-500/30 hover:shadow-lg hover:shadow-emerald-500/5'"
        >
          <div class="text-2xl font-bold tabular-nums text-emerald-400" style="text-shadow: 0 0 20px rgba(52,211,153,0.3)">{{ stats.resolved || 0 }}</div>
          <div class="text-xs text-slate-400 mt-1">已結案</div>
        </button>
      </div>

      <!-- 篩選列 -->
      <div class="flex items-center gap-2 mb-4 bg-slate-800/50 backdrop-blur-sm border border-slate-700/20 rounded-xl px-3 py-2.5 shadow-sm">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="搜尋 MAC / IP..."
          class="flex-1 min-w-0 px-3 py-1.5 bg-slate-900 border border-slate-600/40 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-400 transition"
          @input="debouncedLoadCases"
        />

        <div class="flex rounded-lg overflow-hidden border border-slate-700/40 flex-shrink-0">
          <button
            v-for="opt in statusFilterOptions"
            :key="opt.value"
            @click="setStatusFilter(opt.value)"
            class="px-3 py-1.5 text-xs transition border-r border-slate-700/40 last:border-r-0"
            :class="filterStatus === opt.value
              ? 'bg-cyan-600 text-white'
              : 'bg-slate-900/50 text-slate-400 hover:bg-slate-800/80 hover:text-slate-200'"
          >
            {{ opt.label }}
          </button>
        </div>

        <div class="flex rounded-lg overflow-hidden border border-slate-700/40 flex-shrink-0">
          <button
            v-for="opt in pingFilterOptions"
            :key="opt.value"
            @click="setPingFilter(opt.value)"
            class="px-3 py-1.5 text-xs transition border-r border-slate-700/40 last:border-r-0"
            :class="filterPing === opt.value
              ? 'bg-cyan-600 text-white'
              : 'bg-slate-900/50 text-slate-400 hover:bg-slate-800/80 hover:text-slate-200'"
          >
            {{ opt.label }}
          </button>
        </div>

        <button
          @click="toggleMyFilter"
          :disabled="!currentDisplayName"
          class="px-3 py-1.5 text-xs rounded-lg transition border flex-shrink-0"
          :class="!currentDisplayName ? 'bg-slate-900/50 border-slate-700/40 text-slate-600 cursor-default' : filterMine ? 'bg-cyan-600 border-cyan-500/60 text-white' : 'bg-slate-900/50 border-slate-700/40 text-slate-400 hover:text-slate-200'"
        >
          我的案件
        </button>
      </div>

      <!-- 載入中 -->
      <div v-if="loading" class="rounded-lg border border-slate-700/30 p-10 text-center">
        <div class="animate-pulse text-slate-500 text-sm">載入中...</div>
      </div>

      <!-- 案件列表 -->
      <div v-else-if="cases.length > 0" class="space-y-1.5">
        <div
          v-for="(c, ci) in cases"
          :key="c.id"
          class="bg-slate-800/50 backdrop-blur-sm rounded-xl border-l-[6px] transition-all duration-200 overflow-hidden"
          :class="[
            expandedId === c.id
              ? 'bg-slate-800/80 shadow-lg shadow-cyan-500/5'
              : 'hover:bg-slate-800/70 hover:shadow-md hover:shadow-black/10',
            statusBorderClass(c.status),
            isMyPendingCase(c) ? 'ring-1 ring-blue-400/50' : ''
          ]"
          :style="{ animationDelay: ci * 30 + 'ms' }"
        >
          <!-- 案件行 -->
          <div class="px-4 py-3 cursor-pointer" @click="toggleExpand(c.id)">
            <!-- Row 1: MAC + IP + 備註 ... 指派人 + 動作 + 狀態 -->
            <div class="flex items-center gap-3">
              <!-- Ping -->
              <span
                class="inline-block rounded-full flex-shrink-0" style="width: 11px; height: 11px"
                :class="c.last_ping_reachable === true
                  ? 'ping-dot-green ping-glow-green'
                  : c.last_ping_reachable === false
                    ? 'ping-dot-red ping-glow-red animate-pulse'
                    : 'bg-slate-600'"
                :title="c.last_ping_reachable === true ? '可達' : c.last_ping_reachable === false ? '不可達' : '未檢測'"
              ></span>

              <!-- MAC + IP + 備註 -->
              <span class="text-sm font-mono font-semibold text-slate-100">{{ c.mac_address }}</span>
              <span class="text-sm text-slate-500 font-mono">{{ c.ip_address || '' }}</span>
              <span v-if="c.description" class="text-sm text-slate-500 truncate max-w-[160px]">{{ c.description }}</span>

              <span class="flex-1"></span>

              <!-- 右側操作群組 -->
              <div class="flex items-center gap-2 flex-shrink-0">
                <!-- 指派人 -->
                <div @click.stop class="flex items-center gap-1 w-[160px] justify-end">
                  <template v-if="canAssignCase(c)">
                    <span class="text-sm text-slate-400 flex-shrink-0">指派給</span>
                    <select
                      :value="c.assignee || ''"
                      @change.stop="inlineSetAssignee(c, $event.target.value)"
                      class="px-2 py-0.5 bg-slate-900/50 border border-slate-700/40 rounded text-sm text-slate-400 min-w-0 cursor-pointer hover:border-slate-500 transition"
                    >
                      <option value="">（未指派）</option>
                      <option v-for="name in userList" :key="name" :value="name">{{ name }}</option>
                    </select>
                  </template>
                  <span v-else class="text-sm text-slate-400"><span class="flex-shrink-0">指派給</span> {{ c.assignee || '—' }}</span>
                </div>

                <!-- 分隔 -->
                <span class="w-px h-4 bg-slate-700/50"></span>

                <!-- 接受按鈕（指派給我的待接受案件） -->
                <button
                  v-if="isMyPendingCase(c)"
                  @click.stop="acceptCase(c)"
                  class="px-2.5 py-0.5 text-sm rounded font-semibold bg-blue-500 hover:bg-blue-400 text-white transition-all case-accept-btn whitespace-nowrap"
                >
                  接受
                </button>

                <!-- 重啟按鈕（已結案案件） -->
                <button
                  v-if="isMyResolvedCase(c)"
                  @click.stop="reopenCase(c)"
                  class="px-2.5 py-0.5 text-sm rounded font-semibold bg-amber-500/80 hover:bg-amber-500 text-white transition-all case-reopen-btn whitespace-nowrap"
                >
                  重啟
                </button>

                <!-- 狀態文字（無按鈕時顯示） -->
                <span
                  v-if="!isMyPendingCase(c) && !isMyResolvedCase(c)"
                  class="text-sm font-medium whitespace-nowrap"
                  :class="statusTextClass(c.status)"
                >{{ statusLabel(c.status) }}</span>

                <!-- 箭頭 -->
                <svg
                  class="w-4 h-4 text-slate-500 transition-transform flex-shrink-0"
                  :class="expandedId === c.id ? 'rotate-180' : ''"
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                ><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" /></svg>
              </div>
            </div>

            <!-- Row 2: 屬性標籤 + 摘要 -->
            <div class="mt-2 pl-[22px] flex items-center gap-3 min-h-[30px]">
              <!-- 屬性標籤 -->
              <div v-if="c.change_tags" class="flex gap-1.5 flex-wrap">
                <button
                  v-for="tag in c.change_tags"
                  :key="tag.attribute"
                  class="px-2 py-0.5 text-sm rounded border transition-all cursor-pointer hover:-translate-y-px hover:shadow-sm active:translate-y-0"
                  :class="tag.has_change
                    ? 'bg-red-500/15 text-red-300 border-red-500/30 hover:bg-red-500/25 hover:shadow-red-500/10'
                    : 'bg-emerald-500/10 text-emerald-300/80 border-emerald-500/20 hover:bg-emerald-500/20 hover:shadow-emerald-500/10'"
                  @click.stop="openTimeline(c, tag)"
                >{{ tag.label }}</button>
              </div>

              <!-- 摘要 -->
              <input
                v-if="canEditCase(c)"
                :value="c.summary || ''"
                type="text"
                maxlength="35"
                placeholder="摘要..."
                class="ml-2 text-sm font-bold text-slate-300 leading-snug px-2 py-0.5 bg-slate-700/30 border border-slate-600/25 rounded focus:border-cyan-500/50 focus:outline-none transition w-[480px] max-w-[480px]"
                @blur="inlineSaveSummary(c, $event.target.value)"
                @keyup.enter="$event.target.blur()"
                @click.stop
              />
              <span v-else-if="c.summary" class="ml-2 text-sm font-bold text-slate-300 leading-snug px-2 py-0.5 bg-slate-700/30 border border-slate-600/25 rounded truncate w-[480px] max-w-[480px]">{{ c.summary }}</span>
            </div>
          </div>

          <!-- 展開詳情（手風琴） -->
          <transition name="accordion">
            <div v-if="expandedId === c.id" class="border-t border-slate-700/20 bg-gradient-to-b from-slate-900/40 to-slate-900/20">
              <div v-if="detailLoading" class="text-center py-8 text-slate-400 animate-pulse">載入案件詳情...</div>

              <div v-else-if="caseDetail" class="px-5 py-4 space-y-4">

                <!-- 處理狀態 -->
                <div>
                  <label class="text-sm text-slate-500 uppercase tracking-wider mb-1.5 block">處理狀態</label>
                  <div class="flex rounded-lg overflow-hidden border border-slate-700 w-fit">
                    <button
                      v-for="opt in getStatusActionsForCase(c)"
                      :key="opt.value"
                      @click="inlineSetStatus(c, opt.value)"
                      :disabled="!canEditCase(c) || (opt.value === 'RESOLVED' && c.last_ping_reachable !== true)"
                      :title="opt.value === 'RESOLVED' && c.last_ping_reachable !== true ? 'Ping 不可達時無法標記為已結案' : ''"
                      class="px-3 py-1.5 text-sm transition border-r border-slate-700 last:border-r-0"
                      :class="c.status === opt.value
                        ? opt.activeClass
                        : (canEditCase(c) && !(opt.value === 'RESOLVED' && c.last_ping_reachable !== true))
                          ? 'bg-slate-900/60 text-slate-500 hover:bg-slate-800 hover:text-slate-300'
                          : 'bg-slate-900/60 text-slate-700 cursor-default'"
                    >
                      {{ opt.label }}
                    </button>
                  </div>
                </div>

                <!-- 採集異常 banner -->
                <div v-if="caseDetail.collection_errors?.length"
                     class="bg-purple-900/20 border border-purple-500/30 rounded-lg px-4 py-3">
                  <div class="flex items-center gap-2 text-purple-300 text-sm font-medium mb-1">
                    <span>⚠</span>
                    <span>採集異常</span>
                  </div>
                  <div class="text-purple-400/80 text-xs space-y-0.5">
                    <div v-for="err in caseDetail.collection_errors" :key="err.collection_type + err.switch_hostname">
                      {{ err.collection_type }} ({{ err.switch_hostname }})
                      <span class="text-purple-500/60 ml-1">{{ err.occurred_at ? formatTime(err.occurred_at) : '' }}</span>
                    </div>
                  </div>
                  <div class="text-purple-500/60 text-xs mt-1">上述 API 採集失敗，部分欄位可能不完整</div>
                </div>

                <!-- 最新快照 -->
                <div v-if="caseDetail.latest_snapshot">
                  <label class="text-sm text-slate-500 uppercase tracking-wider mb-2 block">最新快照</label>
                  <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                    <div class="bg-slate-900/50 rounded-lg px-3 py-2 border border-slate-700/50">
                      <span class="text-slate-500 text-sm">交換機</span>
                      <div class="text-slate-200 font-mono text-sm mt-0.5 break-all">{{ caseDetail.latest_snapshot.switch_hostname || '—' }}</div>
                    </div>
                    <div class="bg-slate-900/50 rounded-lg px-3 py-2 border border-slate-700/50">
                      <span class="text-slate-500 text-sm">介面</span>
                      <div class="text-slate-200 font-mono text-sm mt-0.5">{{ caseDetail.latest_snapshot.interface_name || '—' }}</div>
                    </div>
                    <div class="bg-slate-900/50 rounded-lg px-3 py-2 border border-slate-700/50">
                      <span class="text-slate-500 text-sm">速率</span>
                      <div class="font-mono text-sm mt-0.5" :class="caseDetail.latest_snapshot.speed ? 'text-slate-200' : 'text-slate-500'">{{ caseDetail.latest_snapshot.speed || '—' }}</div>
                    </div>
                    <div class="bg-slate-900/50 rounded-lg px-3 py-2 border border-slate-700/50">
                      <span class="text-slate-500 text-sm">雙工</span>
                      <div class="font-mono text-sm mt-0.5" :class="caseDetail.latest_snapshot.duplex ? 'text-slate-200' : 'text-slate-500'">{{ caseDetail.latest_snapshot.duplex || '—' }}</div>
                    </div>
                    <div class="bg-slate-900/50 rounded-lg px-3 py-2 border border-slate-700/50">
                      <span class="text-slate-500 text-sm">連線狀態</span>
                      <div class="font-mono text-sm mt-0.5" :class="caseDetail.latest_snapshot.link_status === 'up' ? 'text-green-400' : caseDetail.latest_snapshot.link_status === 'down' ? 'text-red-400' : 'text-slate-500'">
                        {{ caseDetail.latest_snapshot.link_status || '—' }}
                      </div>
                    </div>
                    <div class="bg-slate-900/50 rounded-lg px-3 py-2 border border-slate-700/50">
                      <span class="text-slate-500 text-sm">VLAN</span>
                      <div class="font-mono text-sm mt-0.5" :class="caseDetail.latest_snapshot.vlan_id != null ? 'text-slate-200' : 'text-slate-500'">{{ caseDetail.latest_snapshot.vlan_id ?? '—' }}</div>
                    </div>
                    <div class="bg-slate-900/50 rounded-lg px-3 py-2 border border-slate-700/50">
                      <span class="text-slate-500 text-sm">Ping</span>
                      <div class="font-mono text-sm mt-0.5" :class="caseDetail.latest_snapshot.ping_reachable === true ? 'text-green-400' : caseDetail.latest_snapshot.ping_reachable === false ? 'text-red-400' : 'text-slate-500'">
                        {{ caseDetail.latest_snapshot.ping_reachable === true ? '可達' : caseDetail.latest_snapshot.ping_reachable === false ? '不可達' : '—' }}
                      </div>
                    </div>
                    <div class="bg-slate-900/50 rounded-lg px-3 py-2 border border-slate-700/50">
                      <span class="text-slate-500 text-sm">ACL</span>
                      <div class="font-mono text-sm mt-0.5" :class="caseDetail.latest_snapshot.acl_rules_applied ? 'text-slate-200' : 'text-slate-500'">
                        {{ caseDetail.latest_snapshot.acl_rules_applied || '—' }}
                      </div>
                    </div>
                  </div>
                  <div v-if="caseDetail.latest_snapshot.collected_at" class="text-sm text-slate-600 mt-1.5 text-right">
                    採集時間：{{ formatTime(caseDetail.latest_snapshot.collected_at) }}
                  </div>
                </div>

                <!-- 查案紀錄 -->
                <div>
                  <label class="text-sm text-slate-500 uppercase tracking-wider mb-2 block">查案紀錄</label>
                  <div class="space-y-2 max-h-[280px] overflow-y-auto pr-1">
                    <div
                      v-for="note in caseDetail.notes"
                      :key="note.id"
                      class="bg-slate-900/50 rounded-lg px-3 py-2.5 border border-slate-700/50"
                    >
                      <div class="flex justify-between items-center mb-1">
                        <span class="text-sm font-medium text-cyan-400">{{ note.author }}</span>
                        <div class="flex items-center gap-2">
                          <button
                            v-if="canEditNote(note)"
                            @click="startEditNote(note)"
                            class="text-sm text-slate-500 hover:text-cyan-400 transition"
                          >編輯</button>
                          <button
                            v-if="canDeleteNote(note)"
                            @click="deleteNote(note)"
                            class="text-sm text-slate-500 hover:text-red-400 transition"
                          >刪除</button>
                          <span class="text-sm text-slate-500">{{ formatTime(note.created_at) }}</span>
                        </div>
                      </div>
                      <!-- 編輯模式 -->
                      <div v-if="editingNoteId === note.id">
                        <textarea
                          v-model="editingNoteContent"
                          rows="3"
                          class="w-full px-3 py-2 bg-slate-900/80 border border-cyan-500/40 rounded-lg text-slate-200 text-sm resize-none focus:outline-none"
                          @keydown.ctrl.enter="saveEditNote(note)"
                          @keydown.escape="cancelEditNote"
                        ></textarea>
                        <div class="flex justify-end gap-2 mt-1.5">
                          <button @click="cancelEditNote" class="px-3 py-1 text-sm text-slate-400 hover:text-slate-200 transition">取消</button>
                          <button @click="saveEditNote(note)" :disabled="!editingNoteContent.trim()" class="px-3 py-1 text-sm bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded transition">儲存</button>
                        </div>
                      </div>
                      <!-- 顯示模式 -->
                      <div v-else class="text-sm text-slate-300 leading-relaxed">
                        <template v-for="(seg, si) in parseNoteContent(note.content)" :key="si">
                          <img
                            v-if="seg.type === 'image'"
                            :src="seg.url"
                            class="max-w-full max-h-[300px] rounded-lg border border-slate-600 my-1.5 cursor-pointer hover:opacity-90 transition"
                            @click="previewImage(seg.url)"
                          />
                          <span v-else class="whitespace-pre-wrap">{{ seg.text }}</span>
                        </template>
                      </div>
                    </div>
                    <div v-if="!caseDetail.notes || caseDetail.notes.length === 0" class="text-sm text-slate-500 text-center py-4">
                      尚無紀錄
                    </div>
                  </div>

                  <!-- 新增筆記（所有登入使用者皆可留言） -->
                  <div class="mt-3">
                    <div
                      class="relative rounded-lg border transition"
                      :class="dragOver ? 'border-cyan-500 bg-cyan-500/5' : 'border-slate-600/80'"
                      @dragover.prevent="dragOver = true"
                      @dragleave.prevent="dragOver = false"
                      @drop.prevent="handleDrop($event, c)"
                    >
                      <textarea
                        v-model="newNote"
                        rows="3"
                        :placeholder="dragOver ? '放開以上傳圖片...' : '新增查案紀錄（可拖曳或 Ctrl+V 貼上圖片）...'"
                        class="w-full px-3 py-2.5 bg-slate-900/80 rounded-lg text-slate-200 text-sm placeholder-slate-500 resize-none border-0 focus:outline-none"
                        @keydown.ctrl.enter="addNote(c)"
                        @paste="handlePaste($event, c)"
                      ></textarea>
                      <div v-if="uploading" class="absolute inset-0 flex items-center justify-center bg-slate-900/80 rounded-lg">
                        <span class="text-cyan-400 text-sm animate-pulse">上傳圖片中...</span>
                      </div>
                    </div>
                    <div v-if="pendingImages.length > 0" class="flex gap-2 mt-2 flex-wrap">
                      <div v-for="(img, i) in pendingImages" :key="i" class="relative group">
                        <img :src="img" class="h-16 rounded-lg border border-slate-600" />
                        <button
                          @click="removePendingImage(i)"
                          class="absolute -top-1 -right-1 w-4 h-4 bg-red-500 text-white text-xs rounded-full leading-none hidden group-hover:flex items-center justify-center"
                        >&times;</button>
                      </div>
                    </div>
                    <div class="flex justify-end mt-2">
                      <button
                        @click="addNote(c)"
                        :disabled="!newNote.trim() && pendingImages.length === 0"
                        class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500 text-white text-sm rounded-lg transition shadow-sm"
                      >
                        送出
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              <div v-else class="px-6 py-8 text-center text-slate-400">
                <p>載入案件詳情失敗</p>
                <button class="mt-2 text-sm text-blue-400 hover:text-blue-300" @click="toggleExpand(cases.find(c => c.id === expandedId))">重試</button>
              </div>
            </div>
          </transition>
        </div>
      </div>

      <!-- 分頁 -->
      <div v-if="cases.length > 0 && totalPages > 1" class="flex items-center justify-center gap-2 mt-4">
        <button
          @click="goToPage(currentPage - 1)"
          :disabled="currentPage <= 1"
          class="px-3 py-1.5 text-xs rounded-lg border transition"
          :class="currentPage <= 1
            ? 'bg-slate-900/50 border-slate-700/40 text-slate-600 cursor-default'
            : 'bg-slate-900/50 border-slate-700/40 text-slate-400 hover:bg-slate-800 hover:text-slate-200'"
        >上一頁</button>

        <template v-for="(p, idx) in paginationRange" :key="typeof p === 'string' ? p + idx : p">
          <span v-if="p === '...'" class="text-slate-600 text-xs px-1">...</span>
          <button
            v-else
            @click="goToPage(p)"
            class="w-8 h-8 text-xs rounded-lg border transition"
            :class="p === currentPage
              ? 'bg-cyan-600 border-cyan-500/60 text-white'
              : 'bg-slate-900/50 border-slate-700/40 text-slate-400 hover:bg-slate-800 hover:text-slate-200'"
          >{{ p }}</button>
        </template>

        <button
          @click="goToPage(currentPage + 1)"
          :disabled="currentPage >= totalPages"
          class="px-3 py-1.5 text-xs rounded-lg border transition"
          :class="currentPage >= totalPages
            ? 'bg-slate-900/50 border-slate-700/40 text-slate-600 cursor-default'
            : 'bg-slate-900/50 border-slate-700/40 text-slate-400 hover:bg-slate-800 hover:text-slate-200'"
        >下一頁</button>

        <span class="text-xs text-slate-500 ml-2">共 {{ totalCount }} 筆</span>
      </div>

      <!-- 無資料 -->
      <div v-else-if="!loading && cases.length === 0" class="rounded-lg border border-slate-700/30 p-12 text-center">
        <p class="text-slate-500 text-sm">尚無案件資料，請先匯入 Client 清單後點擊「同步案件」</p>
      </div>
    </template>

    <!-- 變化時間線 Modal -->
    <teleport to="body">
      <Transition name="modal">
      <div
        v-if="timelineModal.show"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
        @click.self="timelineModal.show = false"
      >
        <div class="modal-content bg-slate-800/95 backdrop-blur-xl rounded-2xl border border-slate-600/40 w-full max-w-md max-h-[80vh] flex flex-col shadow-2xl shadow-black/30" style="box-shadow: 0 25px 50px rgba(0,0,0,0.4), 0 0 40px rgba(0,210,255,0.03)">
          <!-- Header -->
          <div class="flex justify-between items-center px-5 py-4 border-b border-slate-700">
            <h3 class="text-white font-semibold">{{ timelineModal.label }} 變化歷史</h3>
            <button @click="timelineModal.show = false" class="text-slate-400 hover:text-white text-xl leading-none">&times;</button>
          </div>
          <!-- Timeline -->
          <div class="px-5 py-4 overflow-y-auto flex-1">
            <div v-if="timelineModal.loading" class="text-center py-8 text-slate-400 animate-pulse">載入中...</div>
            <div v-else-if="timelineModal.entries.length === 0" class="text-center py-8 text-slate-500">無歷史紀錄</div>

            <!-- 全 null -->
            <div v-else-if="timelineModal.allNull" class="text-center py-10">
              <div class="w-11 h-11 rounded-full bg-slate-700/40 border border-slate-600/30 flex items-center justify-center mx-auto mb-3">
                <span class="text-slate-500 text-lg">—</span>
              </div>
              <p class="text-sm text-slate-400">此屬性尚無實際資料</p>
              <p class="text-xs text-slate-600 mt-1.5">共 {{ timelineModal.entries.length }} 筆採集記錄</p>
            </div>

            <!-- 無變化 -->
            <div v-else-if="timelineModal.changePoints.length <= 1" class="text-center py-10">
              <div class="w-11 h-11 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto mb-3">
                <span class="text-emerald-400 text-sm font-bold">✓</span>
              </div>
              <p class="text-sm text-slate-400">此屬性穩定未變化</p>
              <div v-if="timelineModal.changePoints.length === 1" class="mt-3 inline-block px-4 py-2.5 bg-slate-900/60 rounded-lg border border-slate-700/50">
                <span class="text-[10px] text-slate-500 uppercase tracking-wider block mb-1">目前值</span>
                <span class="text-sm font-mono text-slate-200">
                  {{ timelineModal.changePoints[0].value === null ? '—' : String(timelineModal.changePoints[0].value) }}
                </span>
              </div>
              <p class="text-xs text-slate-600 mt-3">共 {{ timelineModal.entries.length }} 筆採集記錄</p>
            </div>

            <!-- 有變化：垂直時間線 -->
            <div v-else>
              <!-- 統計摘要 -->
              <div class="flex items-center gap-2 mb-4 text-xs text-slate-500">
                <span>共 <b class="text-slate-300 tabular-nums">{{ timelineModal.changePoints.length }}</b> 次變化</span>
                <span v-if="timelineModal.totalSpan" class="text-slate-700">·</span>
                <span v-if="timelineModal.totalSpan">跨越 {{ timelineModal.totalSpan }}</span>
                <span class="text-slate-700">·</span>
                <span>{{ timelineModal.entries.length }} 筆記錄</span>
              </div>

              <!-- 垂直時間線 -->
              <div class="relative ml-1">
                <!-- 垂直連接線 -->
                <div class="absolute left-[5px] top-3 bottom-3 w-px bg-gradient-to-b from-cyan-500/30 via-slate-600/15 to-red-500/30"></div>

                <div
                  v-for="(pt, i) in timelineModal.changePoints"
                  :key="i"
                  class="relative pl-7 pb-3 last:pb-0 row-stagger"
                  :style="{ animationDelay: i * 80 + 'ms' }"
                >
                  <!-- 節點圓點 -->
                  <div
                    class="absolute left-0 top-2.5 w-[11px] h-[11px] rounded-full border-2 border-slate-800 z-10"
                    :class="pt.isInitial ? 'bg-cyan-400' : 'bg-red-400'"
                    :style="pt.isInitial ? 'box-shadow: 0 0 6px rgba(34,211,238,0.35)' : 'box-shadow: 0 0 6px rgba(248,113,113,0.25)'"
                  ></div>

                  <!-- 內容卡片 -->
                  <div
                    class="rounded-lg px-3 py-2 border"
                    :class="pt.isInitial
                      ? 'bg-cyan-500/5 border-cyan-500/15'
                      : 'bg-red-500/5 border-red-500/15'"
                  >
                    <div class="flex items-center justify-between mb-1">
                      <span class="text-xs text-slate-500 tabular-nums">{{ formatTime(pt.collected_at) }}</span>
                      <span
                        class="text-[10px] font-medium px-1.5 py-0.5 rounded"
                        :class="pt.isInitial
                          ? 'text-cyan-400/80 bg-cyan-500/10'
                          : 'text-red-400/80 bg-red-500/10'"
                      >{{ pt.isInitial ? '初始' : '變更' }}</span>
                    </div>
                    <!-- 變更：old → new -->
                    <div v-if="!pt.isInitial && i > 0" class="flex items-center gap-1.5 text-sm font-mono">
                      <span class="text-slate-500">{{ timelineModal.changePoints[i-1].value === null ? '—' : String(timelineModal.changePoints[i-1].value) }}</span>
                      <svg class="w-3.5 h-3.5 text-slate-600 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                      </svg>
                      <span :class="pt.value === null ? 'text-slate-500' : 'text-white'">{{ pt.value === null ? '—' : String(pt.value) }}</span>
                    </div>
                    <!-- 初始值 -->
                    <div v-else class="text-sm font-mono" :class="pt.value === null ? 'text-slate-500' : 'text-slate-100'">
                      {{ pt.value === null ? '—' : String(pt.value) }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <!-- Footer -->
          <div class="px-5 py-3 border-t border-slate-700 text-right">
            <button @click="timelineModal.show = false" class="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded-lg transition">
              關閉
            </button>
          </div>
        </div>
      </div>
      </Transition>
    </teleport>
  </div>
</template>

<script>
import api from '@/utils/api'
import { canWrite, currentUser, isRoot } from '@/utils/auth'
import { useToast } from '@/composables/useToast'
import { refreshCaseBadge } from '@/composables/useCaseBadge'

const STATUS_CONFIG = {
  UNASSIGNED: { label: '未指派', class: 'bg-slate-700/50 text-slate-300' },
  ASSIGNED: { label: '新案件', class: 'bg-blue-500/15 text-blue-300' },
  IN_PROGRESS: { label: '處理中', class: 'bg-amber-500/15 text-amber-300' },
  DISCUSSING: { label: '待討論', class: 'bg-purple-500/15 text-purple-300' },
  RESOLVED: { label: '已結案', class: 'bg-emerald-500/15 text-emerald-300' },
}

export default {
  name: 'Cases',
  inject: ['maintenanceId'],
  setup() {
    return useToast()
  },
  data() {
    return {
      loading: false,
      syncing: false,
      cases: [],
      stats: {},
      // 篩選
      searchQuery: '',
      filterStatus: '',
      filterPing: '',
      filterMine: false,
      activeStatFilter: '',
      // 分頁
      currentPage: 1,
      totalPages: 1,
      totalCount: 0,
      // 展開
      expandedId: null,
      detailLoading: false,
      caseDetail: null,
      // 編輯
      editSummary: '',
      editStatus: '',
      editAssignee: '',
      newNote: '',
      // 筆記編輯
      editingNoteId: null,
      editingNoteContent: '',
      // 時間線 Modal
      timelineModal: {
        show: false,
        label: '',
        attribute: '',
        loading: false,
        entries: [],
        changePoints: [],
        allNull: false,
        totalSpan: '',
        caseObj: null,
      },
      // 圖片上傳
      uploading: false,
      dragOver: false,
      pendingImages: [],
      // 使用者列表（供指派 dropdown）
      userList: [],
      // 自動刷新
      refreshTimer: null,
      debounceTimer: null,
    }
  },
  computed: {
    selectedMaintenanceId() {
      return this.maintenanceId
    },
    userCanWrite() {
      return canWrite.value
    },
    currentDisplayName() {
      return currentUser.value?.display_name || ''
    },
    statusFilterOptions() {
      return [
        { value: 'ALL', label: '全部' },
        { value: '', label: '未結案' },
        { value: 'ASSIGNED', label: '新案件' },
        { value: 'IN_PROGRESS', label: '處理中' },
        { value: 'DISCUSSING', label: '待討論' },
        { value: 'RESOLVED', label: '已結案' },
      ]
    },
    pingFilterOptions() {
      return [
        { value: '', label: '不限' },
        { value: 'false', label: '不可達' },
        { value: 'true', label: '可達' },
      ]
    },
    statusOptions() {
      return {
        IN_PROGRESS: { label: '繼續處理', activeClass: 'bg-amber-500/30 text-amber-200 font-medium' },
        DISCUSSING: { label: '需討論', activeClass: 'bg-purple-500/30 text-purple-200 font-medium' },
        RESOLVED: { label: '結案', activeClass: 'bg-green-500/30 text-green-200 font-medium' },
      }
    },
    statusBreakdown() {
      const s = this.stats
      return [
        { key: 'ASSIGNED', label: '新案件', value: s.assigned || 0, color: 'text-blue-400', borderActive: 'border-blue-500/60 ring-1 ring-blue-500/30 shadow-lg shadow-blue-500/10', borderDefault: 'border-blue-500/15 hover:border-blue-500/30 hover:shadow-lg hover:shadow-blue-500/5' },
        { key: 'IN_PROGRESS', label: '處理中', value: s.in_progress || 0, color: 'text-amber-400', borderActive: 'border-amber-500/60 ring-1 ring-amber-500/30 shadow-lg shadow-amber-500/10', borderDefault: 'border-amber-500/15 hover:border-amber-500/30 hover:shadow-lg hover:shadow-amber-500/5' },
        { key: 'DISCUSSING', label: '待討論', value: s.discussing || 0, color: 'text-purple-400', borderActive: 'border-purple-500/60 ring-1 ring-purple-500/30 shadow-lg shadow-purple-500/10', borderDefault: 'border-purple-500/15 hover:border-purple-500/30 hover:shadow-lg hover:shadow-purple-500/5' },
      ]
    },
    paginationRange() {
      const total = this.totalPages
      const current = this.currentPage
      if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
      const pages = []
      pages.push(1)
      if (current > 3) pages.push('...')
      for (let i = Math.max(2, current - 1); i <= Math.min(total - 1, current + 1); i++) {
        pages.push(i)
      }
      if (current < total - 2) pages.push('...')
      pages.push(total)
      return pages
    },
  },
  watch: {
    selectedMaintenanceId(newId) {
      this.currentPage = 1
      if (newId) {
        this.loadStats()
        this.loadCases()
      } else {
        this.cases = []
        this.stats = {}
        this.totalPages = 1
        this.totalCount = 0
      }
    },
  },
  mounted() {
    this.loadUserNames()
    if (this.selectedMaintenanceId) {
      this.loadStats()
      this.loadCases()
    }
    // 15 秒自動刷新
    this.refreshTimer = setInterval(() => {
      if (document.hidden) return
      if (this.selectedMaintenanceId && !this.loading) {
        this.loadStats()
        this.silentRefreshCases()
      }
    }, 15000)
  },
  beforeUnmount() {
    if (this.refreshTimer) clearInterval(this.refreshTimer)
    if (this.debounceTimer) clearTimeout(this.debounceTimer)
  },
  methods: {
    // ── 篩選按鈕 ────────────────────────────────────────
    setStatusFilter(value) {
      this.filterStatus = value
      this.activeStatFilter = (value === 'ALL' || value === '') ? '' : value
      this.currentPage = 1
      this.loadCases()
    },

    setPingFilter(value) {
      this.filterPing = value
      if (value === 'false') {
        this.activeStatFilter = 'ping_unreachable'
      } else if (this.activeStatFilter === 'ping_unreachable') {
        this.activeStatFilter = ''
      }
      this.currentPage = 1
      this.loadCases()
    },

    // ── 資料載入 ──────────────────────────────────────
    async loadUserNames() {
      try {
        const { data } = await api.get('/users/display-names')
        this.userList = data || []
      } catch {
        // 靜默失敗
      }
    },

    async loadStats() {
      if (!this.selectedMaintenanceId) return
      try {
        const { data } = await api.get(`/cases/${this.selectedMaintenanceId}/stats`)
        this.stats = data
      } catch (e) {
        console.error('Failed to load case stats:', e)
      }
    },

    _buildCaseParams() {
      const params = { page: this.currentPage, page_size: 50 }
      if (this.searchQuery) params.search = this.searchQuery
      if (this.filterStatus === 'ALL') {
        params.include_resolved = true
      } else if (this.filterStatus) {
        params.status = this.filterStatus
        if (this.filterStatus === 'RESOLVED') {
          params.include_resolved = true
        }
      }
      if (this.filterPing !== '') {
        params.ping_reachable = this.filterPing === 'true'
      }
      if (this.filterMine && this.currentDisplayName) params.assignee = this.currentDisplayName
      return params
    },

    async loadCases() {
      if (!this.selectedMaintenanceId) return
      this.loading = true
      try {
        const params = this._buildCaseParams()
        const { data } = await api.get(`/cases/${this.selectedMaintenanceId}`, { params })
        this.cases = data.cases || []
        this.totalPages = data.total_pages || 1
        this.totalCount = data.total || 0
      } catch (e) {
        console.error('Failed to load cases:', e)
        this.showMessage('載入案件失敗', 'error')
      } finally {
        this.loading = false
      }
    },

    async silentRefreshCases() {
      // Skip if user is editing inline
      const activeEl = document.activeElement
      if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'SELECT' || activeEl.tagName === 'TEXTAREA')) {
        const caseList = this.$refs.caseListRef || this.$el
        if (caseList && caseList.contains(activeEl)) return
      }
      if (!this.selectedMaintenanceId) return
      try {
        const params = this._buildCaseParams()
        const { data } = await api.get(`/cases/${this.selectedMaintenanceId}`, { params })
        this.cases = data.cases || []
        this.totalPages = data.total_pages || 1
        this.totalCount = data.total || 0
      } catch (e) {
        // 靜默失敗
      }
    },

    goToPage(page) {
      if (page < 1 || page > this.totalPages || page === this.currentPage) return
      this.currentPage = page
      this.expandedId = null
      this.caseDetail = null
      this.loadCases()
    },

    debouncedLoadCases() {
      if (this.debounceTimer) clearTimeout(this.debounceTimer)
      this.currentPage = 1
      this.debounceTimer = setTimeout(() => this.loadCases(), 300)
    },

    // ── 同步案件 ──────────────────────────────────────
    async syncCases() {
      if (!this.selectedMaintenanceId) return
      this.syncing = true
      try {
        const { data } = await api.post(`/cases/${this.selectedMaintenanceId}/sync`)
        const msg = data.created > 0
          ? `同步完成：新增 ${data.created} 筆案件`
          : '案件已是最新狀態'
        this.showMessage(msg, 'success')
        await this.loadStats()
        await this.loadCases()
      } catch (e) {
        this.showMessage('同步失敗', 'error')
      } finally {
        this.syncing = false
      }
    },

    // ── 展開 / 收合 ──────────────────────────────────
    async toggleExpand(caseId) {
      if (this.expandedId === caseId) {
        this.expandedId = null
        this.caseDetail = null
        return
      }
      this.expandedId = caseId
      this.detailLoading = true
      this.caseDetail = null
      this.newNote = ''
      this.pendingImages = []
      this.editingNoteId = null
      this.editingNoteContent = ''

      try {
        const { data } = await api.get(`/cases/${this.selectedMaintenanceId}/${caseId}`)
        if (this.expandedId !== caseId) return  // user switched to a different case
        this.caseDetail = data.case
        // Update inline change_tags from detail (freshly computed)
        if (data.case?.change_tags) {
          const idx = this.cases.findIndex(x => x.id === caseId)
          if (idx >= 0) this.cases[idx].change_tags = data.case.change_tags
        }
        const c = this.cases.find(x => x.id === caseId)
        if (c) {
          this.editSummary = c.summary || ''
          this.editStatus = c.status
          this.editAssignee = c.assignee || ''
        }
      } catch (e) {
        this.showMessage('載入案件詳情失敗', 'error')
      } finally {
        this.detailLoading = false
      }
    },

    // ── 篩選 ──────────────────────────────────────────
    applyStatFilter(key) {
      if (this.activeStatFilter === key) {
        this.activeStatFilter = ''
        this.filterStatus = ''
        this.filterPing = ''
      } else {
        this.activeStatFilter = key
        if (key === 'ping_unreachable') {
          this.filterStatus = ''
          this.filterPing = 'false'
        } else if (key) {
          this.filterStatus = key
          this.filterPing = ''
        } else {
          this.filterStatus = ''
          this.filterPing = ''
        }
      }
      this.currentPage = 1
      this.loadCases()
    },

    toggleMyFilter() {
      this.filterMine = !this.filterMine
      this.currentPage = 1
      this.loadCases()
    },

    // ── 接受 / 重啟案件 ────────────────────────────────────
    isMyPendingCase(c) {
      return c.status === 'ASSIGNED' && c.assignee === this.currentDisplayName
    },

    isMyResolvedCase(c) {
      return c.status === 'RESOLVED' && c.assignee === this.currentDisplayName
    },

    async acceptCase(c) {
      const ok = await this.updateCase(c, { status: 'IN_PROGRESS' })
      if (ok) this.showMessage('已接受案件，案件將移至「處理中」', 'success')
    },

    async reopenCase(c) {
      const ok = await this.updateCase(c, { status: 'IN_PROGRESS' })
      if (ok) this.showMessage('案件已重啟，案件將移至「處理中」', 'success')
    },

    getStatusActionsForCase(c) {
      const opts = this.statusOptions
      if (c.status === 'DISCUSSING') {
        return [
          { value: 'IN_PROGRESS', ...opts.IN_PROGRESS },
          { value: 'RESOLVED', ...opts.RESOLVED },
        ]
      }
      return [
        { value: 'DISCUSSING', ...opts.DISCUSSING },
        { value: 'RESOLVED', ...opts.RESOLVED },
      ]
    },

    // ── 行內快速操作 ────────────────────────────────────
    async inlineSetStatus(c, newStatus) {
      if (c.status === newStatus) return
      if (!this.canEditCase(c)) return
      await this.updateCase(c, { status: newStatus })
    },

    async inlineSetAssignee(c, newAssignee) {
      if ((c.assignee || '') === newAssignee) return
      await this.updateCase(c, { assignee: newAssignee })
    },

    // ── 編輯 ──────────────────────────────────────────
    canEditCase(c) {
      return c.assignee === this.currentDisplayName
    },

    canAssignCase(c) {
      // 已指派：只有當前被指派人可以轉交
      if (c.assignee) return c.assignee === this.currentDisplayName
      // 未指派：ROOT/PM 可以指派
      return canWrite.value
    },

    async inlineSaveSummary(c, value) {
      const trimmed = value.trim()
      if (trimmed === (c.summary || '')) return
      await this.updateCase(c, { summary: trimmed })
    },

    async saveStatus(c) {
      if (this.editStatus === c.status) return
      await this.updateCase(c, { status: this.editStatus })
    },

    async saveAssignee(c) {
      if (this.editAssignee === (c.assignee || '')) return
      await this.updateCase(c, { assignee: this.editAssignee })
    },

    async updateCase(c, payload) {
      try {
        const { data } = await api.put(
          `/cases/${this.selectedMaintenanceId}/${c.id}`,
          payload,
        )
        const idx = this.cases.findIndex(x => x.id === c.id)
        if (idx >= 0 && data.case) {
          this.cases[idx] = { ...this.cases[idx], ...data.case }
        }
        this.loadStats()
        refreshCaseBadge()
        return true
      } catch (e) {
        const msg = e.response?.data?.detail || '更新失敗'
        this.showMessage(msg, 'error')
        this.editSummary = c.summary || ''
        this.editStatus = c.status
        this.editAssignee = c.assignee || ''
        return false
      }
    },

    async addNote(c) {
      const text = this.newNote.trim()
      if (!text && this.pendingImages.length === 0) return

      let content = text
      for (const url of this.pendingImages) {
        content += (content ? '\n' : '') + `![image](${url})`
      }

      try {
        const { data } = await api.post(
          `/cases/${this.selectedMaintenanceId}/${c.id}/notes`,
          { content },
        )
        if (this.caseDetail && data.note) {
          this.caseDetail.notes = [data.note, ...(this.caseDetail.notes || [])]
        }
        this.newNote = ''
        this.pendingImages = []
        this.showMessage('筆記已新增', 'success')
      } catch (e) {
        const msg = e.response?.data?.detail || '新增筆記失敗'
        this.showMessage(msg, 'error')
      }
    },

    // ── 筆記編輯 ──────────────────────────────────────
    canEditNote(note) {
      return note.author === this.currentDisplayName
    },

    startEditNote(note) {
      this.editingNoteId = note.id
      this.editingNoteContent = note.content
    },

    cancelEditNote() {
      this.editingNoteId = null
      this.editingNoteContent = ''
    },

    async saveEditNote(note) {
      const content = this.editingNoteContent.trim()
      if (!content) return
      if (content === note.content) {
        this.cancelEditNote()
        return
      }

      try {
        const { data } = await api.put(
          `/cases/${this.selectedMaintenanceId}/${this.expandedId}/notes/${note.id}`,
          { content },
        )
        if (data.note) {
          const idx = this.caseDetail.notes.findIndex(n => n.id === note.id)
          if (idx >= 0) {
            this.caseDetail.notes[idx] = { ...this.caseDetail.notes[idx], ...data.note }
          }
        }
        this.cancelEditNote()
        this.showMessage('筆記已更新', 'success')
      } catch (e) {
        const msg = e.response?.data?.detail || '更新筆記失敗'
        this.showMessage(msg, 'error')
      }
    },

    canDeleteNote(note) {
      return note.author === this.currentDisplayName
    },

    async deleteNote(note) {
      if (this.confirmModal?.visible) return
      const confirmed = await this.showConfirm('確定要刪除此筆記？')
      if (!confirmed) return

      try {
        await api.delete(
          `/cases/${this.selectedMaintenanceId}/${this.expandedId}/notes/${note.id}`,
        )
        if (this.caseDetail) {
          this.caseDetail.notes = this.caseDetail.notes.filter(n => n.id !== note.id)
        }
        this.showMessage('筆記已刪除', 'success')
      } catch (e) {
        const msg = e.response?.data?.detail || '刪除筆記失敗'
        this.showMessage(msg, 'error')
      }
    },

    // ── 圖片上傳 ──────────────────────────────────────
    async uploadImage(file) {
      if (!file || !file.type.startsWith('image/')) return null
      if (file.size > 5 * 1024 * 1024) {
        this.showMessage('圖片大小超過 5MB 限制', 'error')
        return null
      }

      this.uploading = true
      try {
        const formData = new FormData()
        formData.append('file', file)
        const { data } = await api.post(
          `/uploads/case-image/${this.selectedMaintenanceId}`,
          formData,
          { headers: { 'Content-Type': 'multipart/form-data' } },
        )
        return data.url
      } catch (e) {
        this.showMessage('圖片上傳失敗', 'error')
        return null
      } finally {
        this.uploading = false
      }
    },

    async handleDrop(event) {
      this.dragOver = false
      const files = event.dataTransfer?.files
      if (!files) return
      for (const file of files) {
        if (file.type.startsWith('image/')) {
          const url = await this.uploadImage(file)
          if (url) this.pendingImages.push(url)
        }
      }
    },

    async handlePaste(event) {
      const items = event.clipboardData?.items
      if (!items) return
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          event.preventDefault()
          const file = item.getAsFile()
          const url = await this.uploadImage(file)
          if (url) this.pendingImages.push(url)
          return
        }
      }
    },

    removePendingImage(index) {
      this.pendingImages.splice(index, 1)
    },

    parseNoteContent(content) {
      if (!content) return [{ type: 'text', text: '' }]
      const parts = []
      const re = /!\[([^\]]*)\]\(([^)]+)\)/g
      let last = 0
      let match
      while ((match = re.exec(content)) !== null) {
        if (match.index > last) {
          parts.push({ type: 'text', text: content.slice(last, match.index) })
        }
        parts.push({ type: 'image', url: match[2] })
        last = match.index + match[0].length
      }
      if (last < content.length) {
        parts.push({ type: 'text', text: content.slice(last) })
      }
      return parts.length > 0 ? parts : [{ type: 'text', text: content }]
    },

    previewImage(url) {
      try {
        const parsed = new URL(url, window.location.origin)
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
          window.open(parsed.href, '_blank')
        }
      } catch {
        // invalid URL, ignore
      }
    },

    // ── 時間線 Modal ──────────────────────────────────
    async openTimeline(c, tag) {
      this.timelineModal.show = true
      this.timelineModal.label = tag.label
      this.timelineModal.attribute = tag.attribute
      this.timelineModal.loading = true
      this.timelineModal.entries = []
      this.timelineModal.changePoints = []
      this.timelineModal.allNull = false
      this.timelineModal.totalSpan = ''
      this.timelineModal.caseObj = c

      try {
        const { data } = await api.get(
          `/cases/${this.selectedMaintenanceId}/${c.id}/changes/${tag.attribute}`,
        )
        const entries = data.timeline || []
        const allNull = entries.length > 0 && entries.every(e => e.value === null)
        this.timelineModal.allNull = allNull
        this.timelineModal.entries = entries

        if (!allNull && entries.length > 0) {
          // entries are DESC (newest first) → reverse to chronological
          const chrono = [...entries].reverse()

          // Build change points: initial value + all subsequent changes
          const points = []
          points.push({ ...chrono[0], isInitial: true })
          for (let i = 1; i < chrono.length; i++) {
            if (String(chrono[i].value) !== String(chrono[i - 1].value)) {
              points.push({ ...chrono[i], isInitial: false })
            }
          }

          // Compute proportional positions along the timeline
          if (points.length >= 2) {
            const t0 = new Date(points[0].collected_at).getTime()
            const tN = new Date(points[points.length - 1].collected_at).getTime()
            const span = tN - t0
            for (const pt of points) {
              const t = new Date(pt.collected_at).getTime()
              pt.position = span > 0 ? ((t - t0) / span) * 100 : 50
            }
            // Human-readable total span
            const totalMs = tN - t0
            const hours = Math.floor(totalMs / 3600000)
            const mins = Math.floor((totalMs % 3600000) / 60000)
            this.timelineModal.totalSpan = hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
          } else {
            points[0].position = 50
            this.timelineModal.totalSpan = ''
          }

          this.timelineModal.changePoints = points
        }
      } catch (e) {
        this.showMessage('載入變化歷史失敗', 'error')
      } finally {
        this.timelineModal.loading = false
      }
    },

    // ── 格式化 ──────────────────────────────────────
    statusLabel(status) {
      return STATUS_CONFIG[status]?.label || status
    },
    statusClass(status) {
      return STATUS_CONFIG[status]?.class || 'bg-slate-500/20 text-slate-300'
    },
    statusBorderClass(status) {
      const map = {
        UNASSIGNED: 'border-l-slate-500/60',
        ASSIGNED: 'border-l-blue-400/70',
        IN_PROGRESS: 'border-l-amber-400/70',
        DISCUSSING: 'border-l-purple-400/70',
        RESOLVED: 'border-l-emerald-400/70',
      }
      return map[status] || 'border-l-slate-500/60'
    },
    statusTextClass(status) {
      const map = {
        UNASSIGNED: 'text-slate-400',
        ASSIGNED: 'text-blue-300/80',
        IN_PROGRESS: 'text-amber-300/80',
        DISCUSSING: 'text-purple-300/80',
        RESOLVED: 'text-emerald-300/80',
      }
      return map[status] || 'text-slate-400'
    },
    formatTime(isoString) {
      if (!isoString) return '—'
      const s = isoString.endsWith('Z') || isoString.includes('+') || /T\d{2}:\d{2}:\d{2}[+-]/.test(isoString) ? isoString : isoString + 'Z'
      const d = new Date(s)
      const mm = String(d.getMonth() + 1).padStart(2, '0')
      const dd = String(d.getDate()).padStart(2, '0')
      const hh = String(d.getHours()).padStart(2, '0')
      const mi = String(d.getMinutes()).padStart(2, '0')
      return `${mm}-${dd} ${hh}:${mi}`
    },
  },
}
</script>

<style scoped>
/* 接受按鈕光暈脈動 */
.case-accept-btn {
  animation: accept-pulse 1.5s ease-in-out infinite;
}
@keyframes accept-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.5), 0 0 0 0 rgba(59, 130, 246, 0); }
  50% { box-shadow: 0 0 10px 3px rgba(59, 130, 246, 0.35), 0 0 18px 5px rgba(59, 130, 246, 0.1); }
}

/* 重啟按鈕光暈脈動 */
.case-reopen-btn {
  animation: reopen-pulse 1.5s ease-in-out infinite;
}
@keyframes reopen-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.5), 0 0 0 0 rgba(245, 158, 11, 0); }
  50% { box-shadow: 0 0 10px 3px rgba(245, 158, 11, 0.35), 0 0 18px 5px rgba(245, 158, 11, 0.1); }
}

/* accordion */
.accordion-enter-active,
.accordion-leave-active {
  transition: max-height 0.3s ease, opacity 0.25s ease;
  overflow: hidden;
}
.accordion-enter-from,
.accordion-leave-to {
  max-height: 0;
  opacity: 0;
}
.accordion-enter-to,
.accordion-leave-from {
  max-height: 1000px;
  opacity: 1;
}
</style>
