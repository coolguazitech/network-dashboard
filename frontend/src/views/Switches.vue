<template>
  <div class="px-3 py-3">
    <div class="flex justify-between items-center mb-4">
      <h1 class="text-xl font-bold text-white">設備管理</h1>
      <button
        v-if="canWrite"
        @click="openAddModal"
        class="px-3 py-1.5 bg-cyan-600/90 hover:bg-cyan-500 text-white text-xs rounded-lg transition font-medium shadow-sm shadow-cyan-500/20"
      >
        新增設備
      </button>
    </div>

    <!-- 載入中 -->
    <div v-if="loading" class="rounded-xl border border-slate-700/30 p-10 text-center">
      <div class="animate-pulse text-slate-500 text-sm">載入中...</div>
    </div>

    <!-- 無數據 -->
    <div v-else-if="!switches || switches.length === 0" class="rounded-xl border border-slate-700/30 p-12 text-center">
      <p class="text-slate-500 text-sm">暫無設備資料</p>
    </div>

    <!-- 設備列表 -->
    <div v-else class="bg-slate-800/50 rounded-xl border border-slate-700/30 overflow-hidden">
      <div class="overflow-x-auto">
        <table class="min-w-full">
          <thead class="bg-slate-900/60 sticky top-0">
            <tr>
              <th class="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">主機名稱</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">IP 位址</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">廠商</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">平台</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">站點</th>
              <th class="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase tracking-wider">狀態</th>
              <th v-if="canWrite" class="px-4 py-3 text-right text-xs font-medium text-slate-400 uppercase tracking-wider">操作</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-700/30">
            <tr v-for="sw in switches" :key="sw.id" class="hover:bg-cyan-500/5 transition-colors">
              <td class="px-4 py-3">
                <div class="text-sm font-medium font-mono text-slate-100 break-all">{{ sw.hostname }}</div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <div class="text-sm text-slate-400 font-mono">{{ sw.ip_address }}</div>
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span class="px-2 py-0.5 text-xs font-medium rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                  {{ sw.vendor }}
                </span>
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-slate-400">
                {{ sw.platform }}
              </td>
              <td class="px-4 py-3 whitespace-nowrap text-sm text-slate-400">
                {{ sw.site || '—' }}
              </td>
              <td class="px-4 py-3 whitespace-nowrap">
                <span
                  :class="sw.is_active
                    ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                    : 'bg-slate-700/30 text-slate-500 border-slate-700/40'"
                  class="px-2 py-0.5 text-xs font-medium rounded border"
                >
                  {{ sw.is_active ? '啟用' : '停用' }}
                </span>
              </td>
              <td v-if="canWrite" class="px-4 py-3 whitespace-nowrap text-right text-sm">
                <button
                  @click="editSwitch(sw)"
                  class="text-cyan-400 hover:text-cyan-300 mr-3 transition"
                >
                  編輯
                </button>
                <button
                  @click="confirmDelete(sw)"
                  class="text-red-400 hover:text-red-300 transition"
                >
                  刪除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 新增/編輯 Modal -->
    <teleport to="body">
      <Transition name="modal">
      <div
        v-if="showModal"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-start justify-center z-50 p-4 pt-20"
        @click.self="closeModal"
      >
        <div class="modal-content bg-slate-800/95 backdrop-blur-xl rounded-2xl border border-slate-600/40 w-full max-w-2xl shadow-2xl shadow-black/30">
          <div class="flex justify-between items-center px-5 py-4 border-b border-slate-700">
            <h3 class="text-white font-semibold">{{ isEditMode ? '編輯設備' : '新增設備' }}</h3>
            <button @click="closeModal" class="text-slate-400 hover:text-white text-xl leading-none">&times;</button>
          </div>

          <form @submit.prevent="saveSwitch" class="px-5 py-4 space-y-4">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="form-label">主機名稱 <span class="text-red-400">*</span></label>
                <input v-model="formData.hostname" type="text" required class="form-input" placeholder="core-switch-01" />
              </div>
              <div>
                <label class="form-label">IP 位址 <span class="text-red-400">*</span></label>
                <input v-model="formData.ip_address" type="text" required pattern="^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$" class="form-input" placeholder="192.168.1.1" />
              </div>
              <div>
                <label class="form-label">廠商 <span class="text-red-400">*</span></label>
                <select v-model="formData.vendor" required class="form-select">
                  <option value="">請選擇廠商</option>
                  <option value="cisco">Cisco</option>
                  <option value="aruba">Aruba</option>
                  <option value="hpe">HPE</option>
                  <option value="huawei">Huawei</option>
                  <option value="other">其他</option>
                </select>
              </div>
              <div>
                <label class="form-label">平台 <span class="text-red-400">*</span></label>
                <select v-model="formData.platform" required class="form-select">
                  <option value="">請選擇平台</option>
                  <option value="ios">IOS</option>
                  <option value="nxos">NX-OS</option>
                  <option value="aruba_os">ArubaOS</option>
                  <option value="aruba_cx">ArubaOS-CX</option>
                  <option value="comware">Comware</option>
                </select>
              </div>
              <div>
                <label class="form-label">站點 <span class="text-red-400">*</span></label>
                <select v-model="formData.site" required class="form-select">
                  <option value="">請選擇站點</option>
                  <option value="datacenter">資料中心</option>
                  <option value="office">辦公室</option>
                  <option value="branch">分支</option>
                </select>
              </div>
              <div>
                <label class="form-label">型號</label>
                <input v-model="formData.model" type="text" class="form-input" placeholder="C9300-48P" />
              </div>
            </div>

            <div>
              <label class="form-label">位置</label>
              <input v-model="formData.location" type="text" class="form-input" placeholder="機房 A 櫃 5" />
            </div>

            <div>
              <label class="form-label">備註</label>
              <textarea v-model="formData.description" rows="3" class="form-input resize-none" placeholder="備註說明"></textarea>
            </div>

            <div class="flex items-center gap-2">
              <input v-model="formData.is_active" type="checkbox" id="is_active" class="rounded border-slate-500 bg-slate-900 text-cyan-500 focus:ring-cyan-500/50" />
              <label for="is_active" class="text-sm text-slate-300">啟用</label>
            </div>

            <div class="flex justify-end gap-3 pt-4 border-t border-slate-700">
              <button type="button" @click="closeModal" class="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded-lg transition">
                取消
              </button>
              <button type="submit" :disabled="saving" class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded-lg transition shadow-sm shadow-cyan-500/20 disabled:opacity-50 disabled:cursor-not-allowed">
                {{ isEditMode ? '更新' : '新增' }}
              </button>
            </div>
          </form>
        </div>
      </div>
      </Transition>
    </teleport>

    <!-- 刪除確認 Modal -->
    <teleport to="body">
      <Transition name="modal">
      <div
        v-if="showDeleteConfirm"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
        @click.self="cancelDelete"
      >
        <div class="modal-content bg-slate-800/95 backdrop-blur-xl rounded-2xl border border-slate-600/40 w-full max-w-sm shadow-2xl shadow-black/30 p-6 text-center">
          <h3 class="text-lg font-semibold text-white mb-2">確認刪除</h3>
          <p class="text-sm text-slate-400 mb-5">
            確定要刪除設備 <span class="text-red-300 font-medium">{{ deleteTarget?.hostname }}</span> 嗎？此操作無法復原。
          </p>
          <div class="flex justify-center gap-3">
            <button @click="cancelDelete" class="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded-lg transition">
              取消
            </button>
            <button @click="deleteSwitch" :disabled="saving" class="px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-sm rounded-lg transition disabled:opacity-50 disabled:cursor-not-allowed">
              確認刪除
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
import { useToast } from '@/composables/useToast'
import { canWrite } from '@/utils/auth'

export default {
  name: 'Switches',
  setup() {
    return { ...useToast(), canWrite }
  },
  data() {
    return {
      switches: [],
      loading: false,
      saving: false,
      showModal: false,
      showDeleteConfirm: false,
      isEditMode: false,
      deleteTarget: null,
      formData: {
        id: null,
        hostname: '',
        ip_address: '',
        vendor: '',
        platform: '',
        site: '',
        model: '',
        location: '',
        description: '',
        is_active: true
      }
    }
  },
  mounted() {
    this.loadSwitches()
  },
  methods: {
    async loadSwitches() {
      this.loading = true
      try {
        const { data } = await api.get('/switches')
        this.switches = data.data || []
      } catch (error) {
        console.error('載入設備列表失敗:', error)
        this.showMessage('載入設備列表失敗', 'error')
      } finally {
        this.loading = false
      }
    },
    openAddModal() {
      this.isEditMode = false
      this.resetForm()
      this.showModal = true
    },
    editSwitch(sw) {
      this.isEditMode = true
      this.formData = {
        id: sw.id,
        hostname: sw.hostname,
        ip_address: sw.ip_address,
        vendor: sw.vendor,
        platform: sw.platform,
        site: sw.site || '',
        model: sw.model || '',
        location: sw.location || '',
        description: sw.description || '',
        is_active: sw.is_active
      }
      this.showModal = true
    },
    closeModal() {
      this.showModal = false
      this.resetForm()
    },
    resetForm() {
      this.formData = {
        id: null,
        hostname: '',
        ip_address: '',
        vendor: '',
        platform: '',
        site: '',
        model: '',
        location: '',
        description: '',
        is_active: true
      }
    },
    async saveSwitch() {
      this.saving = true
      try {
        const url = this.isEditMode
          ? `/switches/${this.formData.id}`
          : '/switches'

        if (this.isEditMode) {
          await api.put(url, this.formData)
        } else {
          const { id, ...payload } = this.formData
          await api.post(url, payload)
        }

        await this.loadSwitches()
        this.closeModal()
        this.showMessage(this.isEditMode ? '設備更新成功' : '設備新增成功', 'success')
      } catch (error) {
        const detail = error.response?.data?.detail || '未知錯誤'
        this.showMessage(`操作失敗: ${detail}`, 'error')
      } finally {
        this.saving = false
      }
    },
    confirmDelete(sw) {
      this.deleteTarget = sw
      this.showDeleteConfirm = true
    },
    cancelDelete() {
      this.deleteTarget = null
      this.showDeleteConfirm = false
    },
    async deleteSwitch() {
      this.saving = true
      try {
        await api.delete(`/switches/${this.deleteTarget.id}`)
        await this.loadSwitches()
        this.cancelDelete()
        this.showMessage('設備刪除成功', 'success')
      } catch (error) {
        const detail = error.response?.data?.detail || '未知錯誤'
        this.showMessage(`刪除失敗: ${detail}`, 'error')
      } finally {
        this.saving = false
      }
    }
  }
}
</script>
