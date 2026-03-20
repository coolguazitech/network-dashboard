<template>
  <div class="px-3 py-3">
    <!-- 頁面標題 -->
    <div class="flex justify-between items-center mb-4">
      <h1 class="text-xl font-bold text-white">通訊錄</h1>
      <div class="flex gap-2">
        <button
          v-if="maintenanceId"
          @click="exportCSV"
          class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm font-medium transition"
        >
          📤 CSV 匯出
        </button>
        <button
          v-if="userCanWrite"
          @click="showImportModal = true"
          class="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm font-medium transition"
        >
          📥 CSV 匯入
        </button>
        <button
          v-if="userCanWrite"
          @click="openContactModal(null)"
          class="px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm font-medium transition"
        >
          ➕ 新增聯絡人
        </button>
      </div>
    </div>

    <!-- 無歲修提示 -->
    <div v-if="!maintenanceId" class="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-600/40 p-8 text-center">
      <div class="text-5xl mb-3">📇</div>
      <p class="text-slate-400 text-lg">請先在頂部選擇歲修 ID</p>
    </div>

    <!-- 主內容區 -->
    <div v-else class="flex gap-4">
      <!-- 左側分類選單 -->
      <div class="w-48 flex-shrink-0">
        <div class="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-600/40 overflow-hidden">
          <!-- 標題 -->
          <div class="flex justify-between items-center px-3 py-2 border-b border-slate-700">
            <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wide">分類</h3>
            <button
              v-if="userCanWrite"
              @click="openCategoryModal(null)"
              class="text-cyan-400 hover:text-cyan-300 text-xs"
              title="新增分類"
            >
              +
            </button>
          </div>

          <!-- 列表 -->
          <div class="divide-y divide-slate-700/50">
            <!-- 全部 -->
            <div
              @click="selectedCategoryId = null"
              :class="[
                'flex items-center px-3 py-2 cursor-pointer text-sm transition group',
                selectedCategoryId === null
                  ? 'bg-cyan-500/10 text-cyan-300 border-l-2 border-cyan-400'
                  : 'text-slate-300 hover:bg-slate-700/50 border-l-2 border-transparent'
              ]"
            >
              <span class="flex-1">全部</span>
              <span class="text-xs text-slate-500">{{ totalContactCount }}</span>
            </div>

            <!-- 分類項目（階層式） -->
            <template v-for="category in categories" :key="category.id">
              <!-- 父分類 -->
              <div
                @click="selectedCategoryId = category.id"
                :class="[
                  'flex items-center px-3 py-2 cursor-pointer text-sm transition group',
                  selectedCategoryId === category.id
                    ? 'bg-cyan-500/10 text-cyan-300 border-l-2 border-cyan-400'
                    : 'text-slate-300 hover:bg-slate-700/50 border-l-2 border-transparent'
                ]"
              >
                <span
                  class="w-2 h-2 rounded-full mr-2 flex-shrink-0"
                  :style="{ backgroundColor: category.color || '#22d3ee' }"
                ></span>
                <span class="flex-1 truncate">{{ category.name }}</span>
                <span class="text-xs text-slate-500 mr-1">{{ getCategoryCount(category.id) }}</span>
                <!-- Hover 操作 -->
                <div v-if="userCanWrite" class="hidden group-hover:flex gap-2">
                  <button
                    @click.stop="openCategoryModal(category)"
                    class="text-slate-400 hover:text-cyan-400 text-base leading-none"
                    title="編輯"
                  >
                    ✎
                  </button>
                  <button
                    @click.stop="openSubCategoryModal(category)"
                    class="text-slate-400 hover:text-cyan-400 text-base leading-none"
                    title="新增子分類"
                  >
                    +
                  </button>
                  <button
                    @click.stop="deleteCategory(category)"
                    class="text-slate-400 hover:text-red-400 text-base leading-none"
                    title="刪除"
                  >
                    ×
                  </button>
                </div>
              </div>
              <!-- 子分類 -->
              <div
                v-for="child in (category.children || [])"
                :key="child.id"
                @click="selectedCategoryId = child.id"
                :class="[
                  'flex items-center pl-7 pr-3 py-1.5 cursor-pointer text-xs transition group',
                  selectedCategoryId === child.id
                    ? 'bg-cyan-500/10 text-cyan-300 border-l-2 border-cyan-400'
                    : 'text-slate-400 hover:bg-slate-700/50 border-l-2 border-transparent'
                ]"
              >
                <span
                  class="w-1.5 h-1.5 rounded-full mr-2 flex-shrink-0"
                  :style="{ backgroundColor: child.color || category.color || '#22d3ee' }"
                ></span>
                <span class="flex-1 truncate">{{ child.name }}</span>
                <span class="text-xs text-slate-500 mr-1">{{ getCategoryCount(child.id) }}</span>
                <div v-if="userCanWrite" class="hidden group-hover:flex gap-2">
                  <button
                    @click.stop="openCategoryModal(child)"
                    class="text-slate-400 hover:text-cyan-400 text-base leading-none"
                    title="編輯"
                  >
                    ✎
                  </button>
                  <button
                    @click.stop="deleteCategory(child)"
                    class="text-slate-400 hover:text-red-400 text-base leading-none"
                    title="刪除"
                  >
                    ×
                  </button>
                </div>
              </div>
            </template>

            <!-- 未分類（永遠顯示） -->
            <div
              @click="selectedCategoryId = 'uncategorized'"
              :class="[
                'flex items-center px-3 py-2 cursor-pointer text-sm transition',
                selectedCategoryId === 'uncategorized'
                  ? 'bg-slate-600/30 text-slate-200 border-l-2 border-slate-400'
                  : 'text-slate-500 hover:bg-slate-700/50 border-l-2 border-transparent'
              ]"
            >
              <span class="flex-1">未分類</span>
              <span class="text-xs text-slate-500">{{ uncategorizedCount }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右側聯絡人列表 -->
      <div class="flex-1">
        <!-- 搜尋欄 -->
        <div class="mb-3">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜尋姓名、角色、電話、手機..."
            class="w-full px-3 py-1.5 bg-slate-900 border border-slate-600/40 rounded-lg text-slate-200 placeholder-slate-500 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
          />
        </div>

        <!-- 批量操作欄 -->
        <div v-if="selectedContacts.length > 0 && userCanWrite" class="mb-3 flex items-center gap-3 bg-cyan-500/10 border border-cyan-500/30 rounded-xl px-3 py-2">
          <span class="text-sm text-cyan-300">已選擇 {{ selectedContacts.length }} 筆</span>

          <!-- 批量修改分類 -->
          <div class="flex items-center gap-2">
            <span class="text-xs text-slate-400">移至</span>
            <select
              v-model="bulkTargetCategory"
              class="px-2 py-1 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
            >
              <option :value="null">未分類</option>
              <template v-for="cat in categories" :key="cat.id">
                <option :value="cat.id">{{ cat.name }}</option>
                <option v-for="child in (cat.children || [])" :key="child.id" :value="child.id">
                  &nbsp;&nbsp;└ {{ child.name }}
                </option>
              </template>
            </select>
            <button
              @click="bulkChangeCategory"
              class="px-3 py-1 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm transition disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="saving"
            >
              移動
            </button>
          </div>

          <div class="border-l border-slate-600 h-5 mx-1"></div>

          <button
            @click="bulkDelete"
            class="px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm transition disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="saving"
          >
            批量刪除
          </button>
          <button
            @click="selectedContacts = []"
            class="px-3 py-1 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition"
          >
            取消選擇
          </button>
        </div>

        <!-- 載入中 -->
        <div v-if="loading" class="flex justify-center py-8">
          <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>

        <!-- 聯絡人列表 -->
        <div v-if="!loading && filteredContacts.length > 0" class="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-600/40 overflow-hidden">
          <!-- 表頭 -->
          <div class="grid grid-cols-12 gap-2 px-3 py-2 bg-slate-900/50 border-b border-slate-700 text-xs text-slate-400 uppercase tracking-wide items-center">
            <div v-if="userCanWrite" class="col-span-1 flex items-center">
              <input
                type="checkbox"
                :checked="isAllSelected"
                @change="toggleSelectAll"
                class="w-4 h-4 rounded border-slate-500 bg-slate-700 text-cyan-500 focus:ring-cyan-500"
              />
            </div>
            <div :class="userCanWrite ? 'col-span-2' : 'col-span-2'">姓名</div>
            <div class="col-span-2">分類</div>
            <div class="col-span-2">角色</div>
            <div class="col-span-1">公司</div>
            <div class="col-span-1">電話</div>
            <div :class="userCanWrite ? 'col-span-2' : 'col-span-3'">手機</div>
            <div v-if="userCanWrite" class="col-span-1"></div>
          </div>

          <!-- 列表內容 -->
          <div class="divide-y divide-slate-700/50">
            <div
              v-for="contact in filteredContacts"
              :key="contact.id"
              class="grid grid-cols-12 gap-2 px-3 py-2 text-sm hover:bg-slate-700/30 transition group items-center"
              :class="{ 'bg-cyan-500/10': selectedContacts.includes(contact.id) }"
            >
              <div v-if="userCanWrite" class="col-span-1 flex items-center">
                <input
                  type="checkbox"
                  :checked="selectedContacts.includes(contact.id)"
                  @change="toggleSelect(contact.id)"
                  class="w-4 h-4 rounded border-slate-500 bg-slate-700 text-cyan-500 focus:ring-cyan-500"
                />
              </div>
              <div :class="userCanWrite ? 'col-span-2' : 'col-span-2'" class="text-white font-medium truncate">{{ contact.name }}</div>
              <div class="col-span-2 text-slate-500 text-xs truncate" :title="getCategoryPath(contact.category_id)">{{ getCategoryPath(contact.category_id) || '-' }}</div>
              <div class="col-span-2 text-slate-400 truncate">{{ contact.title || '-' }}</div>
              <div class="col-span-1 text-slate-400 truncate">{{ contact.company || '-' }}</div>
              <div class="col-span-1 text-cyan-400 truncate">{{ contact.phone || '-' }}</div>
              <div :class="userCanWrite ? 'col-span-2' : 'col-span-3'" class="text-cyan-400">{{ contact.mobile || '-' }}</div>
              <div v-if="userCanWrite" class="col-span-1 flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition">
                <button
                  @click="openContactModal(contact)"
                  class="text-slate-400 hover:text-cyan-400 text-base leading-none"
                  title="編輯"
                >
                  ✎
                </button>
                <button
                  @click="deleteContact(contact)"
                  class="text-slate-400 hover:text-red-400 text-base leading-none"
                  title="刪除"
                >
                  ×
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- 無資料 -->
        <div v-else-if="!loading" class="bg-slate-800/60 backdrop-blur-sm rounded-xl border border-slate-600/40 p-8 text-center">
          <div class="text-4xl mb-3">📭</div>
          <p class="text-slate-400 text-sm">{{ searchQuery ? '沒有符合的搜尋結果' : '尚無聯絡人' }}</p>
          <button
            v-if="!searchQuery && userCanWrite"
            @click="openContactModal(null)"
            class="mt-3 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm transition"
          >
            + 新增聯絡人
          </button>
        </div>
      </div>
    </div>

    <!-- 聯絡人 Modal -->
    <Transition name="modal">
    <div
      v-if="showContactModal"
      class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @mousedown.self="showContactModal = false"
    >
      <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-5 w-[500px] max-w-full modal-content">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-white">
            {{ editingContact ? '編輯聯絡人' : '新增聯絡人' }}
          </h3>
          <button @click="showContactModal = false" class="text-slate-400 hover:text-white text-xl">&times;</button>
        </div>

        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-400 mb-1">姓名 *</label>
              <input
                v-model="contactForm.name"
                type="text"
                class="w-full px-3 py-2 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">分類</label>
              <select
                v-model="contactForm.category_id"
                class="w-full px-3 py-2 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              >
                <option :value="null">未分類</option>
                <template v-for="cat in categories" :key="cat.id">
                  <option :value="cat.id">{{ cat.name }}</option>
                  <option v-for="child in (cat.children || [])" :key="child.id" :value="child.id">
                    &nbsp;&nbsp;└ {{ child.name }}
                  </option>
                </template>
              </select>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-400 mb-1">角色</label>
              <input v-model="contactForm.title" type="text" class="w-full px-3 py-2 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">公司</label>
              <input v-model="contactForm.company" type="text" class="w-full px-3 py-2 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400" />
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-400 mb-1">部門</label>
              <input v-model="contactForm.department" type="text" class="w-full px-3 py-2 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">電話</label>
              <input v-model="contactForm.phone" type="tel" class="w-full px-3 py-2 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400" />
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs text-slate-400 mb-1">手機</label>
              <input v-model="contactForm.mobile" type="tel" class="w-full px-3 py-2 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400" />
            </div>
            <div>
              <label class="block text-xs text-slate-400 mb-1">分機</label>
              <input v-model="contactForm.extension" type="text" class="w-full px-3 py-2 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400" />
            </div>
          </div>

          <div>
            <label class="block text-xs text-slate-400 mb-1">備註</label>
            <textarea v-model="contactForm.notes" rows="2" class="w-full px-3 py-2 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400 resize-none"></textarea>
          </div>

        </div>

        <div class="flex justify-end gap-2 mt-4">
          <button @click="showContactModal = false" class="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition">
            取消
          </button>
          <button @click="saveContact" class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm transition disabled:opacity-50 disabled:cursor-not-allowed" :disabled="!contactForm.name || saving">
            儲存
          </button>
        </div>
      </div>
    </div>
    </Transition>

    <!-- 分類 Modal -->
    <Transition name="modal">
    <div
      v-if="showCategoryModal"
      class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @mousedown.self="showCategoryModal = false"
    >
      <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-5 w-96 max-w-full modal-content">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-white">
            {{ editingCategory ? '編輯分類' : (categoryForm.parent_id ? '新增子分類' : '新增分類') }}
          </h3>
          <button @click="showCategoryModal = false" class="text-slate-400 hover:text-white text-xl">&times;</button>
        </div>

        <div class="space-y-3">
          <div v-if="categoryForm.parent_id && !editingCategory" class="text-xs text-slate-400">
            父分類：<span class="text-cyan-400">{{ categories.find(c => c.id === categoryForm.parent_id)?.name }}</span>
          </div>
          <div>
            <label class="block text-xs text-slate-400 mb-1">{{ categoryForm.parent_id ? '子分類名稱' : '分類名稱' }} *</label>
            <input
              v-model="categoryForm.name"
              type="text"
              class="w-full px-3 py-2 bg-slate-700 border border-slate-600/40 rounded-lg text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
            />
          </div>

          <div>
            <label class="block text-xs text-slate-400 mb-1">顏色</label>
            <div class="flex gap-2 flex-wrap">
              <button
                v-for="color in colorOptions"
                :key="color"
                @click="categoryForm.color = color"
                :class="[
                  'w-6 h-6 rounded-full transition ring-2',
                  categoryForm.color === color ? 'ring-white' : 'ring-transparent'
                ]"
                :style="{ backgroundColor: color }"
              ></button>
            </div>
          </div>
        </div>

        <div class="flex justify-end gap-2 mt-4">
          <button @click="showCategoryModal = false" class="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition">
            取消
          </button>
          <button @click="saveCategory" class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm transition disabled:opacity-50 disabled:cursor-not-allowed" :disabled="!categoryForm.name || saving">
            儲存
          </button>
        </div>
      </div>
    </div>
    </Transition>

    <!-- 刪除確認 Modal -->
    <Transition name="modal">
    <div
      v-if="showDeleteModal"
      class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @mousedown.self="showDeleteModal = false"
    >
      <div class="bg-slate-800/95 backdrop-blur-xl border border-red-500/30 rounded-2xl shadow-2xl shadow-black/30 p-5 w-96 max-w-full modal-content">
        <div class="flex items-center gap-3 mb-4">
          <div class="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center">
            <span class="text-red-400 text-xl">⚠️</span>
          </div>
          <div>
            <h3 class="text-lg font-bold text-white">確認刪除</h3>
            <p class="text-sm text-slate-400">此操作無法復原</p>
          </div>
        </div>

        <p class="text-slate-300 mb-4">
          {{ deleteTarget?.type === 'category' ? '確定要刪除分類' : '確定要刪除聯絡人' }}
          「<span class="text-cyan-400 font-semibold">{{ deleteTarget?.name }}</span>」嗎？
        </p>

        <div class="flex justify-end gap-2">
          <button
            @click="showDeleteModal = false"
            class="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition"
          >
            取消
          </button>
          <button
            @click="confirmDelete"
            class="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg text-sm transition disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="saving"
          >
            確定刪除
          </button>
        </div>
      </div>
    </div>
    </Transition>

    <!-- CSV 匯入 Modal -->
    <Transition name="modal">
    <div
      v-if="showImportModal"
      class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @mousedown.self="showImportModal = false"
    >
      <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-5 w-[500px] max-w-full modal-content">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-white">📥 CSV 匯入</h3>
          <button @click="showImportModal = false" class="text-slate-400 hover:text-white text-xl">&times;</button>
        </div>

        <div class="bg-slate-700/50 rounded-lg p-3 mb-4 text-sm">
          <p class="text-slate-300 mb-2">CSV 格式說明：</p>
          <code class="block bg-slate-900 p-2 rounded-lg text-xs text-cyan-300 overflow-x-auto">
            category_name,sub_category_name,name,title,department,company,phone,mobile,extension,notes
          </code>
          <p class="text-slate-400 text-xs mt-2">* category_name / sub_category_name 欄位會自動建立對應分類與子分類</p>
          <p class="text-slate-400 text-xs">* sub_category_name 可留空，聯絡人將歸入主分類</p>
        </div>

        <div class="mb-4">
          <label class="block text-xs text-slate-400 mb-1">選擇 CSV 檔案</label>
          <input
            type="file"
            accept=".csv"
            @change="handleFileSelect"
            class="w-full text-sm text-slate-300 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-cyan-600 file:text-white hover:file:bg-cyan-500"
          />
        </div>

        <div class="flex justify-between">
          <button
            @click="downloadTemplate"
            class="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition"
          >
            📄 下載範本
          </button>
          <div class="flex gap-2">
            <button @click="showImportModal = false" class="px-4 py-2 bg-slate-600 hover:bg-slate-500 text-white rounded-lg text-sm transition">
              取消
            </button>
            <button
              @click="importCSV"
              class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg text-sm transition disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!importFile || saving"
            >
              匯入
            </button>
          </div>
        </div>
      </div>
    </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject, watch } from 'vue'
import api from '@/utils/api'
import { canWrite } from '@/utils/auth'

const maintenanceId = inject('maintenanceId')
const userCanWrite = computed(() => canWrite.value)

const loading = ref(false)
const saving = ref(false)

const categories = ref([])
const contacts = ref([])
const selectedContacts = ref([])
const bulkTargetCategory = ref(null)
const selectedCategoryId = ref(null)
const searchQuery = ref('')

// Modal states
const showContactModal = ref(false)
const showCategoryModal = ref(false)
const showImportModal = ref(false)
const showDeleteModal = ref(false)
const editingContact = ref(null)
const editingCategory = ref(null)
const importFile = ref(null)
const deleteTarget = ref(null) // { type: 'category'|'contact', id, name, data }

// Form data
const contactForm = ref({
  name: '',
  title: '',
  company: '',
  phone: '',
  mobile: '',
  category_id: null,
})

const categoryForm = ref({
  name: '',
  color: '#22d3ee',
  parent_id: null,
})

const colorOptions = ['#22d3ee', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#6366f1', '#14b8a6']

// Computed
const totalContactCount = computed(() => contacts.value.length)

const uncategorizedCount = computed(() => {
  return contacts.value.filter(c => !c.category_id).length
})

const getCategoryPath = (categoryId) => {
  if (!categoryId) return ''
  for (const cat of categories.value) {
    if (cat.id === categoryId) return cat.name
    for (const child of (cat.children || [])) {
      if (child.id === categoryId) return `${cat.name} > ${child.name}`
    }
  }
  return ''
}

const getCategoryCount = (categoryId) => {
  // 對父分類：計算本身 + 所有子分類的聯絡人數
  const cat = categories.value.find(c => c.id === categoryId)
  if (cat && cat.children && cat.children.length > 0) {
    const childIds = cat.children.map(c => c.id)
    return contacts.value.filter(c => c.category_id === categoryId || childIds.includes(c.category_id)).length
  }
  return contacts.value.filter(c => c.category_id === categoryId).length
}

const filteredContacts = computed(() => {
  let result = contacts.value

  // Filter by category
  if (selectedCategoryId.value === 'uncategorized') {
    result = result.filter(c => !c.category_id)
  } else if (selectedCategoryId.value) {
    // 如果選的是父分類，也包含其子分類的聯絡人
    const cat = categories.value.find(c => c.id === selectedCategoryId.value)
    if (cat && cat.children && cat.children.length > 0) {
      const allIds = [selectedCategoryId.value, ...cat.children.map(c => c.id)]
      result = result.filter(c => allIds.includes(c.category_id))
    } else {
      result = result.filter(c => c.category_id === selectedCategoryId.value)
    }
  }

  // Filter by search query
  if (searchQuery.value) {
    const query = searchQuery.value.toLowerCase()
    result = result.filter(c =>
      c.name?.toLowerCase().includes(query) ||
      c.title?.toLowerCase().includes(query) ||
      c.phone?.toLowerCase().includes(query) ||
      c.mobile?.toLowerCase().includes(query) ||
      c.company?.toLowerCase().includes(query)
    )
  }

  return result
})

// 全選狀態
const isAllSelected = computed(() => {
  if (filteredContacts.value.length === 0) return false
  return filteredContacts.value.every(c => selectedContacts.value.includes(c.id))
})

// 切換全選
const toggleSelectAll = () => {
  if (isAllSelected.value) {
    // 取消全選（只取消當前篩選的）
    const filteredIds = filteredContacts.value.map(c => c.id)
    selectedContacts.value = selectedContacts.value.filter(id => !filteredIds.includes(id))
  } else {
    // 全選當前篩選的
    const filteredIds = filteredContacts.value.map(c => c.id)
    const newSelection = [...new Set([...selectedContacts.value, ...filteredIds])]
    selectedContacts.value = newSelection
  }
}

// 切換單筆選擇
const toggleSelect = (id) => {
  const idx = selectedContacts.value.indexOf(id)
  if (idx > -1) {
    selectedContacts.value.splice(idx, 1)
  } else {
    selectedContacts.value.push(id)
  }
}

// 批量刪除
const bulkDelete = async () => {
  if (!selectedContacts.value.length) return
  if (!confirm('確定要刪除選取的聯絡人？')) return

  saving.value = true
  try {
    const results = { success: 0, failed: 0 }
    for (const id of [...selectedContacts.value]) {
      try {
        await api.delete(`/contacts/${maintenanceId.value}/${id}`)
        results.success++
      } catch {
        results.failed++
      }
    }

    if (results.failed > 0) {
      alert(`刪除完成：成功 ${results.success} 筆，失敗 ${results.failed} 筆`)
    } else {
      alert(`已刪除 ${results.success} 筆聯絡人`)
    }

    selectedContacts.value = []
    await fetchContacts()
  } finally {
    saving.value = false
  }
}

// 批量修改分類
const bulkChangeCategory = async () => {
  if (!selectedContacts.value.length || bulkTargetCategory.value === undefined) return

  const findCatName = (id) => {
    for (const cat of categories.value) {
      if (cat.id === id) return cat.name
      for (const child of (cat.children || [])) {
        if (child.id === id) return `${cat.name} > ${child.name}`
      }
    }
    return '未分類'
  }
  const targetName = bulkTargetCategory.value === null ? '未分類' : findCatName(bulkTargetCategory.value)

  if (!confirm(`確定要將選中的 ${selectedContacts.value.length} 筆聯絡人移至「${targetName}」嗎？`)) {
    return
  }

  saving.value = true
  try {
    const results = { success: 0, failed: 0 }
    for (const id of [...selectedContacts.value]) {
      try {
        await api.put(`/contacts/${maintenanceId.value}/${id}`, {
          category_id: bulkTargetCategory.value
        })
        results.success++
      } catch {
        results.failed++
      }
    }

    if (results.failed > 0) {
      alert(`分類變更完成：成功 ${results.success} 筆，失敗 ${results.failed} 筆`)
    } else {
      alert(`已變更 ${results.success} 筆聯絡人分類`)
    }

    selectedContacts.value = []
    bulkTargetCategory.value = null
    await fetchContacts()
  } finally {
    saving.value = false
  }
}

// API calls
const fetchCategories = async () => {
  if (!maintenanceId.value) return
  try {
    const response = await api.get(`/contacts/categories/${maintenanceId.value}`)
    categories.value = response.data
  } catch (error) {
    console.error('Failed to fetch categories:', error)
  }
}

const fetchContacts = async () => {
  if (!maintenanceId.value) return
  loading.value = true
  try {
    const response = await api.get(`/contacts/${maintenanceId.value}`)
    contacts.value = response.data
  } catch (e) {
    console.error(e)
    alert('載入聯絡人失敗')
  } finally {
    loading.value = false
  }
}

// Category operations
const openCategoryModal = (category) => {
  editingCategory.value = category
  if (category) {
    categoryForm.value = { name: category.name, color: category.color || '#22d3ee', parent_id: category.parent_id || null }
  } else {
    categoryForm.value = { name: '', color: '#22d3ee', parent_id: null }
  }
  showCategoryModal.value = true
}

const saveCategory = async () => {
  if (!categoryForm.value.name || !maintenanceId.value) return

  saving.value = true
  try {
    const payload = {
      name: categoryForm.value.name,
      color: categoryForm.value.color,
    }
    if (editingCategory.value) {
      await api.put(`/contacts/categories/${editingCategory.value.id}`, payload)
    } else {
      await api.post('/contacts/categories', {
        ...payload,
        parent_id: categoryForm.value.parent_id || null,
        maintenance_id: maintenanceId.value,
      })
    }
    showCategoryModal.value = false
    await fetchCategories()
    await fetchContacts()
  } catch (error) {
    console.error('Failed to save category:', error)
    alert(`儲存失敗: ${error.response?.data?.detail || error.message}`)
  } finally {
    saving.value = false
  }
}

const deleteCategory = (category) => {
  deleteTarget.value = {
    type: 'category',
    id: category.id,
    name: category.name,
    data: category,
  }
  showDeleteModal.value = true
}

// 新增子分類
const openSubCategoryModal = (parentCategory) => {
  editingCategory.value = null
  categoryForm.value = { name: '', color: parentCategory.color || '#22d3ee', parent_id: parentCategory.id }
  showCategoryModal.value = true
}

// Contact operations
const openContactModal = (contact) => {
  editingContact.value = contact
  if (contact) {
    contactForm.value = { ...contact }
  } else {
    contactForm.value = {
      name: '',
      title: '',
      department: '',
      company: '',
      phone: '',
      mobile: '',
      extension: '',
      notes: '',
      category_id: selectedCategoryId.value === 'uncategorized' ? null : selectedCategoryId.value,
    }
  }
  showContactModal.value = true
}

const saveContact = async () => {
  if (!contactForm.value.name) {
    alert('請輸入姓名')
    return
  }
  if (!maintenanceId.value) {
    alert('請先選擇歲修 ID')
    return
  }

  const editableFields = ['name', 'title', 'department', 'company', 'phone', 'mobile', 'extension', 'notes', 'category_id']
  const payload = {}
  for (const key of editableFields) {
    if (key in contactForm.value) payload[key] = contactForm.value[key]
  }

  saving.value = true
  try {
    if (editingContact.value) {
      await api.put(`/contacts/${maintenanceId.value}/${editingContact.value.id}`, payload)
    } else {
      await api.post(`/contacts/${maintenanceId.value}`, payload)
    }
    showContactModal.value = false
    await fetchContacts()
  } catch (error) {
    console.error('Failed to save contact:', error)
    alert(`儲存失敗: ${error.response?.data?.detail || error.message}`)
  } finally {
    saving.value = false
  }
}

const deleteContact = (contact) => {
  deleteTarget.value = {
    type: 'contact',
    id: contact.id,
    name: contact.name,
    data: contact,
  }
  showDeleteModal.value = true
}

const confirmDelete = async () => {
  if (!deleteTarget.value) return

  saving.value = true
  try {
    if (deleteTarget.value.type === 'category') {
      await api.delete(`/contacts/categories/${deleteTarget.value.id}`)
      if (selectedCategoryId.value === deleteTarget.value.id) {
        selectedCategoryId.value = null
      }
      await fetchCategories()
      await fetchContacts()
    } else if (deleteTarget.value.type === 'contact') {
      await api.delete(`/contacts/${maintenanceId.value}/${deleteTarget.value.id}`)
      await fetchContacts()
    }
    showDeleteModal.value = false
    deleteTarget.value = null
  } catch (e) {
    console.error(e)
    alert('刪除失敗，請稍後再試')
  } finally {
    saving.value = false
  }
}

// CSV operations
const handleFileSelect = (event) => {
  importFile.value = event.target.files[0]
}

const importCSV = async () => {
  if (!importFile.value || !maintenanceId.value) return

  const formData = new FormData()
  formData.append('file', importFile.value)

  try {
    await api.post(`/contacts/${maintenanceId.value}/import-csv`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    showImportModal.value = false
    importFile.value = null
    await fetchCategories()
    await fetchContacts()
  } catch (error) {
    console.error('Failed to import CSV:', error)
    alert('CSV 匯入失敗，請檢查檔案格式')
  }
}

const downloadTemplate = () => {
  const csv = 'category_name,sub_category_name,name,title,department,company,phone,mobile,extension,notes\n技術團隊,,張三,PM,IT部門,A公司,02-12345678,0912345678,1234,備註\n技術團隊,網路組,李四,工程師,A公司,02-12345679,0923456789,5678,備註'
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = 'contacts_template.csv'
  link.click()
  URL.revokeObjectURL(link.href)
}

// 匯出 CSV（根據當前篩選條件）
const exportCSV = () => {
  const data = filteredContacts.value
  if (data.length === 0) {
    alert('沒有可匯出的資料')
    return
  }

  // CSV 標題列
  const headers = ['分類', '子分類', '姓名', '角色', '部門', '公司', '電話', '手機', '分機', '備註']

  // 轉換資料為 CSV 格式
  const escapeCSV = (val) => {
    if (val === null || val === undefined) return ''
    const str = String(val)
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`
    }
    return str
  }

  // 建立 category_id -> { parentName, childName } 的映射
  const catPathMap = {}
  for (const cat of categories.value) {
    catPathMap[cat.id] = { parent: cat.name, child: '' }
    for (const child of (cat.children || [])) {
      catPathMap[child.id] = { parent: cat.name, child: child.name }
    }
  }

  const rows = data.map(c => {
    const path = catPathMap[c.category_id] || { parent: '未分類', child: '' }
    return [
      escapeCSV(path.parent),
      escapeCSV(path.child),
      escapeCSV(c.name),
      escapeCSV(c.title),
      escapeCSV(c.department),
      escapeCSV(c.company),
      escapeCSV(c.phone),
      escapeCSV(c.mobile),
      escapeCSV(c.extension),
      escapeCSV(c.notes)
    ].join(',')
  })

  const csv = [headers.join(','), ...rows].join('\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)

  // 檔名包含篩選資訊
  let filename = `contacts_${maintenanceId.value}`
  if (selectedCategoryId.value === 'uncategorized') {
    filename += '_未分類'
  } else if (selectedCategoryId.value) {
    const cat = categories.value.find(c => c.id === selectedCategoryId.value)
    if (cat) filename += `_${cat.name}`
  }
  if (searchQuery.value) {
    filename += `_搜尋${searchQuery.value}`
  }
  filename += '.csv'

  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

// Watch maintenance ID changes
watch(maintenanceId, (newId) => {
  selectedContacts.value = []  // 清空選擇
  if (newId) {
    fetchCategories()
    fetchContacts()
  }
})

// 切換分類時清空選擇
watch(selectedCategoryId, () => {
  selectedContacts.value = []
})

// 關閉匯入 Modal 時清空檔案
watch(showImportModal, (val) => {
  if (!val) {
    importFile.value = null
  }
})

onMounted(() => {
  if (maintenanceId.value) {
    fetchCategories()
    fetchContacts()
  }
})
</script>
