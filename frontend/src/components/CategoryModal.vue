<template>
  <div class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4" @mousedown.self="$emit('close')">
    <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
      <!-- Header -->
      <div class="flex justify-between items-center p-4 border-b border-slate-700 bg-slate-800">
        <h2 class="text-xl font-bold text-slate-100">🏷️ 分類管理</h2>
        <button @click="$emit('close')" class="text-slate-500 hover:text-slate-300 text-2xl">✕</button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-4">
        <!-- 新增分類 -->
        <div class="mb-6 bg-slate-900/50 rounded-lg p-4 border border-slate-700">
          <h3 class="font-semibold text-slate-200 mb-3">新增分類（最多 5 個）</h3>
          <div class="flex gap-3 items-end">
            <div class="flex-1">
              <label class="block text-sm text-slate-400 mb-1">名稱</label>
              <input
                v-model="newCategory.name"
                type="text"
                placeholder="例如：生產機台"
                class="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 focus:ring-2 focus:ring-cyan-500 focus:border-transparent"
                :disabled="categories.length >= 5"
              />
            </div>
            <div class="w-32">
              <label class="block text-sm text-slate-400 mb-1">顏色</label>
              <input
                v-model="newCategory.color"
                type="color"
                class="w-full h-10 border border-slate-600 rounded cursor-pointer bg-slate-900"
                :disabled="categories.length >= 5"
              />
            </div>
            <button
              @click="createCategory"
              :disabled="!newCategory.name || categories.length >= 5"
              class="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed transition"
            >
              新增
            </button>
          </div>
          <p v-if="categories.length >= 5" class="text-sm text-amber-500 mt-2">
            ⚠️ 已達到分類上限 (5 個)
          </p>
        </div>

        <!-- 分類列表 -->
        <div class="space-y-4">
          <div
            v-for="cat in categories"
            :key="cat.id"
            class="border border-slate-700 rounded-lg p-4 bg-slate-900/50"
          >
            <div class="flex justify-between items-start mb-3">
              <div class="flex items-center gap-3">
                <div class="w-4 h-4 rounded-full" :style="{ backgroundColor: cat.color }"></div>
                <div v-if="editingId !== cat.id">
                  <h4 class="font-semibold text-slate-100">{{ cat.name }}</h4>
                  <p class="text-sm text-slate-500">{{ getMemberCount(cat.id) }} 台機台</p>
                </div>
                <div v-else class="flex gap-2">
                  <input
                    v-model="editForm.name"
                    class="px-2 py-1 bg-slate-900 border border-slate-600 rounded text-sm text-slate-200"
                    placeholder="分類名稱"
                  />
                  <input
                    v-model="editForm.color"
                    type="color"
                    class="w-8 h-8 border border-slate-600 rounded cursor-pointer bg-slate-900"
                  />
                </div>
              </div>
              <div class="flex gap-2">
                <template v-if="editingId !== cat.id">
                  <button
                    @click="startEdit(cat)"
                    class="px-2 py-1 text-sm text-cyan-400 hover:bg-slate-700 rounded"
                  >
                    編輯
                  </button>
                  <button
                    @click="deleteCategory(cat)"
                    class="px-2 py-1 text-sm text-rose-400 hover:bg-slate-700 rounded"
                  >
                    刪除
                  </button>
                </template>
                <template v-else>
                  <button
                    @click="saveEdit(cat.id)"
                    class="px-2 py-1 text-sm text-emerald-400 hover:bg-slate-700 rounded"
                  >
                    保存
                  </button>
                  <button
                    @click="editingId = null"
                    class="px-2 py-1 text-sm text-slate-400 hover:bg-slate-700 rounded"
                  >
                    取消
                  </button>
                </template>
              </div>
            </div>

            <!-- 成員列表 (只讀) -->
            <div class="bg-slate-800 rounded p-3 border border-slate-700">
              <div class="flex justify-between items-center mb-2">
                <span class="text-sm font-medium text-slate-300">機台清單</span>
                <span class="text-xs text-slate-500">
                  （MAC 只能透過「新增 MAC」或「匯入 CSV」時指定，或使用批量分類功能）
                </span>
              </div>

              <!-- 成員列表 -->
              <div v-if="categoryMembers[cat.id] && categoryMembers[cat.id].length > 0" class="max-h-40 overflow-y-auto">
                <div
                  v-for="member in categoryMembers[cat.id]"
                  :key="member.id"
                  class="flex justify-between items-center py-1.5 px-2 hover:bg-slate-700 rounded text-sm"
                >
                  <span class="font-mono text-slate-200">{{ member.mac_address }}</span>
                  <div class="flex items-center gap-2">
                    <span v-if="member.description" class="text-slate-500 text-xs">{{ member.description }}</span>
                    <button
                      @click="removeMember(cat.id, member.mac_address)"
                      class="text-rose-400 hover:text-rose-300 text-lg"
                      title="從此分類移除"
                    >
                      ✕
                    </button>
                  </div>
                </div>
              </div>
              <p v-else class="text-sm text-slate-500 text-center py-2">尚無機台</p>
            </div>
          </div>
        </div>

        <!-- 空狀態 -->
        <div v-if="categories.length === 0" class="text-center py-8 text-slate-500">
          <p class="text-4xl mb-2">📂</p>
          <p>尚未建立任何分類</p>
          <p class="text-sm">請在上方新增第一個分類</p>
        </div>
      </div>

      <!-- Footer -->
      <div class="p-4 border-t border-slate-700 bg-slate-800">
        <div class="flex justify-end">
          <button
            @click="$emit('close')"
            class="px-4 py-2 bg-slate-600 text-white rounded hover:bg-slate-500 transition"
          >
            關閉
          </button>
        </div>
      </div>

      <!-- 確認移除成員對話框 -->
      <div
        v-if="confirmDialog.show"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-60"
      >
        <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-96">
          <h3 class="font-semibold text-slate-100 mb-3">確認移除</h3>
          <p class="text-slate-300 mb-4">
            確定要將 <span class="font-mono font-bold text-slate-100">{{ confirmDialog.macAddress }}</span> 從此分類移除嗎？
          </p>
          <p class="text-sm text-slate-500 mb-4">該 MAC 不會被刪除，只是變成「未分類」狀態。</p>
          <div class="flex justify-end gap-2">
            <button
              @click="confirmDialog.show = false"
              class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded transition"
            >
              取消
            </button>
            <button
              @click="confirmRemoveMember"
              class="px-4 py-2 bg-rose-600 text-white rounded hover:bg-rose-500 transition"
            >
              確定移除
            </button>
          </div>
        </div>
      </div>

      <!-- 刪除分類確認對話框 -->
      <div
        v-if="deleteDialog.show"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-60"
      >
        <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-96">
          <h3 class="font-semibold text-slate-100 mb-3">⚠️ 確認刪除分類</h3>
          <p class="text-slate-300 mb-2">
            確定要刪除分類「<span class="font-bold text-slate-100">{{ deleteDialog.category?.name }}</span>」嗎？
          </p>
          <p class="text-sm text-amber-400 bg-amber-900/30 p-2 rounded mb-4 border border-amber-800">
            該分類下的 {{ deleteDialog.category?.member_count || 0 }} 台機台將變成未分類。
          </p>
          <div class="flex justify-end gap-2">
            <button
              @click="deleteDialog.show = false"
              class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded transition"
            >
              取消
            </button>
            <button
              @click="confirmDeleteCategory"
              class="px-4 py-2 bg-rose-600 text-white rounded hover:bg-rose-500 transition"
            >
              確定刪除
            </button>
          </div>
        </div>
      </div>

      <!-- 錯誤提示對話框 -->
      <div
        v-if="errorDialog.show"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-60"
      >
        <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-96">
          <h3 class="font-semibold text-rose-400 mb-3">❌ 錯誤</h3>
          <p class="text-slate-300 mb-4 whitespace-pre-line">{{ errorDialog.message }}</p>
          <div class="flex justify-end">
            <button
              @click="errorDialog.show = false"
              class="px-4 py-2 bg-slate-600 text-white rounded hover:bg-slate-500 transition"
            >
              確定
            </button>
          </div>
        </div>
      </div>

      <!-- 成功提示對話框 -->
      <div
        v-if="successDialog.show"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-60"
      >
        <div class="bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-96">
          <h3 class="font-semibold text-green-400 mb-3">✓ 成功</h3>
          <p class="text-slate-300 mb-4 whitespace-pre-line">{{ successDialog.message }}</p>
          <div class="flex justify-end">
            <button
              @click="successDialog.show = false"
              class="px-4 py-2 bg-slate-600 text-white rounded hover:bg-slate-500 transition"
            >
              確定
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import api from '@/utils/api'

export default {
  name: 'CategoryModal',
  props: {
    categories: {
      type: Array,
      default: () => [],
    },
    maintenanceId: {
      type: String,
      required: true,
    },
  },
  emits: ['close', 'refresh'],
  data() {
    return {
      newCategory: { name: '', color: '#3B82F6' },
      editingId: null,
      editForm: { name: '', color: '' },
      categoryMembers: {},
      confirmDialog: {
        show: false,
        categoryId: null,
        macAddress: '',
      },
      deleteDialog: {
        show: false,
        category: null,
      },
      errorDialog: {
        show: false,
        message: '',
      },
      successDialog: {
        show: false,
        message: '',
      },
    };
  },
  mounted() {
    this.loadAllMembers();
  },
  watch: {
    categories: {
      handler() {
        this.loadAllMembers();
      },
      deep: true,
    },
  },
  methods: {
    async loadAllMembers() {
      for (const cat of this.categories) {
        await this.loadMembers(cat.id);
      }
    },

    async loadMembers(categoryId) {
      try {
        const { data } = await api.get(`/categories/${categoryId}/members`);
        this.categoryMembers[categoryId] = data;
        this.categoryMembers = { ...this.categoryMembers };
      } catch (e) {
        console.error('載入成員失敗:', e);
      }
    },

    async createCategory() {
      const name = this.newCategory.name?.trim();
      if (!name) return;
      
      // 檢查名稱是否重複
      const exists = this.categories.some(
        c => c.name.toLowerCase() === name.toLowerCase()
      );
      if (exists) {
        this.showError(`分類名稱「${name}」已存在，請使用其他名稱`);
        return;
      }
      
      try {
        const payload = {
          name: name,
          color: this.newCategory.color,
          maintenance_id: this.maintenanceId,
        };
        await api.post('/categories', payload);
        this.newCategory = { name: '', color: '#3B82F6' };
        this.$emit('refresh');
        this.showSuccess('分類建立成功');
      } catch (e) {
        console.error('建立分類失敗:', e);
        const detail = e.response?.data?.detail;
        this.showError(detail || '建立分類失敗，請稍後再試');
      }
    },

    startEdit(cat) {
      this.editingId = cat.id;
      this.editForm = { name: cat.name, color: cat.color };
    },

    async saveEdit(categoryId) {
      const name = this.editForm.name?.trim();
      if (!name) {
        this.showError('分類名稱不能為空');
        return;
      }
      
      // 檢查名稱是否與其他分類重複
      const exists = this.categories.some(
        c => c.id !== categoryId && c.name.toLowerCase() === name.toLowerCase()
      );
      if (exists) {
        this.showError(`分類名稱「${name}」已存在，請使用其他名稱`);
        return;
      }
      
      try {
        await api.put(`/categories/${categoryId}`, { name: name, color: this.editForm.color });
        this.editingId = null;
        this.$emit('refresh');
        this.showSuccess('分類已更新');
      } catch (e) {
        console.error('更新分類失敗:', e);
        const detail = e.response?.data?.detail;
        this.showError(detail || '更新分類失敗，請稍後再試');
      }
    },

    deleteCategory(cat) {
      this.deleteDialog = {
        show: true,
        category: cat,
      };
    },

    async confirmDeleteCategory() {
      const cat = this.deleteDialog.category;
      this.deleteDialog.show = false;
      
      try {
        await api.delete(`/categories/${cat.id}`);
        this.$emit('refresh');
        this.showSuccess(`分類「${cat.name}」已刪除`);
      } catch (e) {
        console.error('刪除分類失敗:', e);
        const detail = e.response?.data?.detail;
        this.showError(detail || '刪除分類失敗，請稍後再試');
      }
    },

    removeMember(categoryId, macAddress) {
      this.confirmDialog = {
        show: true,
        categoryId,
        macAddress,
      };
    },

    async confirmRemoveMember() {
      const { categoryId, macAddress } = this.confirmDialog;
      this.confirmDialog.show = false;
      
      try {
        const encodedMac = encodeURIComponent(macAddress);
        await api.delete(`/categories/${categoryId}/members/${encodedMac}`);
        await this.loadMembers(categoryId);
        this.$emit('refresh');
      } catch (e) {
        console.error('移除成員失敗:', e);
        const detail = e.response?.data?.detail;
        this.showError(detail || '移除成員失敗，請稍後再試');
      }
    },

    showError(message) {
      this.errorDialog = {
        show: true,
        message,
      };
    },
    
    showSuccess(message) {
      this.successDialog = {
        show: true,
        message,
      };
    },
    
    getMemberCount(categoryId) {
      const members = this.categoryMembers[categoryId];
      return members ? members.length : 0;
    },
  },
};
</script>
