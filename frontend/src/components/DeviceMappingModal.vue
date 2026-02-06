<template>
  <div class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
    <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
      <!-- Header -->
      <div class="flex justify-between items-center p-4 border-b border-slate-700">
        <h2 class="text-xl font-bold text-slate-100">🔄 Switch 設備對應管理</h2>
        <button @click="$emit('close')" class="text-slate-500 hover:text-slate-300 text-2xl">✕</button>
      </div>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-4">
        <!-- 錯誤/成功提示訊息 -->
        <transition name="fade">
          <div v-if="toast.show" 
            :class="[
              'mb-4 p-3 rounded-lg border flex items-start gap-2',
              toast.type === 'error' 
                ? 'bg-rose-900/30 border-rose-500/50 text-rose-300' 
                : 'bg-emerald-900/30 border-emerald-500/50 text-emerald-300'
            ]">
            <span class="text-lg">{{ toast.type === 'error' ? '⚠️' : '✅' }}</span>
            <div class="flex-1">
              <div class="font-medium">{{ toast.title }}</div>
              <div v-if="toast.message" class="text-sm opacity-80 mt-0.5">{{ toast.message }}</div>
            </div>
            <button @click="toast.show = false" class="text-slate-400 hover:text-slate-200">✕</button>
          </div>
        </transition>
        
        <!-- 新增設備對應 -->
        <div class="mb-4 bg-slate-900/50 border border-slate-700 rounded-lg p-3">
          <h3 class="font-semibold text-slate-200 mb-3 text-sm">新增設備對應</h3>
          <div class="grid grid-cols-12 gap-2 items-end">
            <!-- 舊設備 Hostname -->
            <div class="col-span-3">
              <label class="block text-xs text-slate-400 mb-1">舊設備 Hostname</label>
              <input v-model="newDevice.old_hostname" type="text" placeholder="SW-OLD-01"
                class="w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
            </div>
            <span class="text-slate-400 text-center col-span-1 pb-2">→</span>
            <!-- 新設備 Hostname -->
            <div class="col-span-3">
              <label class="block text-xs text-slate-400 mb-1">新設備 Hostname</label>
              <input v-model="newDevice.new_hostname" type="text" placeholder="SW-NEW-01"
                class="w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-slate-200 placeholder-slate-500 text-sm" />
            </div>
            <!-- 廠商下拉選單 -->
            <div class="col-span-2">
              <label class="block text-xs text-slate-400 mb-1">廠商 <span class="text-rose-400">*</span></label>
              <select v-model="newDevice.vendor"
                class="w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-slate-200 text-sm">
                <option value="" disabled>選擇廠商</option>
                <option v-for="v in vendorOptions" :key="v" :value="v">{{ v }}</option>
              </select>
            </div>
            <!-- 同 Port 對應 -->
            <div class="col-span-2">
              <label class="block text-xs text-slate-400 mb-1">同 Port 對應</label>
              <label class="flex items-center gap-2 px-2 py-1.5 bg-slate-900 border border-slate-600 rounded cursor-pointer">
                <input type="checkbox" v-model="newDevice.use_same_port" class="form-checkbox text-cyan-500 bg-slate-800 border-slate-600 rounded" />
                <span class="text-sm text-slate-200">{{ newDevice.use_same_port ? '啟用' : '停用' }}</span>
              </label>
            </div>
            <!-- 新增按鈕 -->
            <div class="col-span-1">
              <button @click="createDeviceMapping" 
                :disabled="!newDevice.old_hostname || !newDevice.new_hostname || !newDevice.vendor"
                class="w-full px-3 py-1.5 bg-cyan-600 text-white rounded text-sm hover:bg-cyan-500 disabled:bg-slate-700 disabled:text-slate-500">
                新增
              </button>
            </div>
          </div>
        </div>

        <!-- CSV 導入 -->
        <div class="mb-4 flex gap-2">
          <button @click="downloadDeviceTemplate" class="px-2 py-1 bg-slate-700 text-slate-300 rounded text-sm hover:bg-slate-600">
            📄 範本
          </button>
          <label class="px-2 py-1 bg-emerald-900/50 text-emerald-400 rounded text-sm hover:bg-emerald-900 cursor-pointer">
            📥 導入
            <input type="file" accept=".csv" class="hidden" @change="importDeviceCSV" />
          </label>
        </div>

        <!-- 設備列表 -->
        <div class="bg-slate-900/50 border border-slate-700 rounded-lg">
          <div class="flex justify-between items-center p-2 border-b border-slate-700">
            <span class="text-slate-200 text-sm font-medium">設備對應列表 ({{ deviceMappings.length }} 筆)</span>
            <button v-if="deviceMappings.length > 0" @click="clearAllDevices"
              class="text-xs text-rose-400 hover:bg-slate-700 px-2 py-0.5 rounded">清除全部</button>
          </div>
          
          <!-- 表頭 -->
          <div class="grid grid-cols-12 gap-2 px-3 py-2 border-b border-slate-700 bg-slate-800/50 text-xs text-slate-400 font-medium">
            <div class="col-span-3">舊設備</div>
            <div class="col-span-1"></div>
            <div class="col-span-3">新設備</div>
            <div class="col-span-2">廠商</div>
            <div class="col-span-2">同 Port</div>
            <div class="col-span-1">操作</div>
          </div>
          
          <div class="max-h-[280px] overflow-y-auto">
            <div v-if="deviceMappings.length === 0" class="text-center py-4 text-slate-500 text-sm">
              尚無設備對應關係
            </div>
            <div v-for="m in deviceMappings" :key="m.id"
              class="grid grid-cols-12 gap-2 items-center px-3 py-1.5 border-b border-slate-700/50 hover:bg-slate-700/30 text-sm">
              <!-- 編輯模式 -->
              <template v-if="editingDevice && editingDevice.id === m.id">
                <div class="col-span-3">
                  <input v-model="editingDevice.old_hostname" type="text"
                    class="w-full px-2 py-0.5 bg-slate-900 border border-cyan-500 rounded text-slate-200 text-sm font-mono" />
                </div>
                <div class="col-span-1 text-center text-slate-400">→</div>
                <div class="col-span-3">
                  <input v-model="editingDevice.new_hostname" type="text"
                    class="w-full px-2 py-0.5 bg-slate-900 border border-cyan-500 rounded text-slate-200 text-sm font-mono" />
                </div>
                <div class="col-span-2">
                  <select v-model="editingDevice.vendor"
                    class="w-full px-1 py-0.5 bg-slate-900 border border-cyan-500 rounded text-slate-200 text-xs">
                    <option v-for="v in vendorOptions" :key="v" :value="v">{{ v }}</option>
                  </select>
                </div>
                <div class="col-span-2">
                  <label class="flex items-center gap-1 cursor-pointer">
                    <input type="checkbox" v-model="editingDevice.use_same_port" 
                      class="form-checkbox text-cyan-500 bg-slate-800 border-slate-600 rounded" />
                    <span class="text-xs text-slate-200">{{ editingDevice.use_same_port ? '啟用' : '停用' }}</span>
                  </label>
                </div>
                <div class="col-span-1 flex gap-1">
                  <button @click="saveEditDevice" class="text-emerald-400 hover:text-emerald-300 px-1" title="儲存">✓</button>
                  <button @click="editingDevice = null" class="text-slate-400 hover:text-slate-300 px-1" title="取消">✗</button>
                </div>
              </template>
              <!-- 顯示模式 -->
              <template v-else>
                <div class="col-span-3 font-mono text-slate-200 truncate" :title="m.old_hostname">{{ m.old_hostname }}</div>
                <div class="col-span-1 text-center text-slate-400">→</div>
                <div class="col-span-3 font-mono text-slate-200 truncate" :title="m.new_hostname">{{ m.new_hostname }}</div>
                <div class="col-span-2">
                  <span :class="[
                    'px-1.5 py-0.5 rounded text-xs',
                    m.vendor === 'HPE' ? 'bg-emerald-900/50 text-emerald-300' :
                    m.vendor === 'Cisco-IOS' ? 'bg-blue-900/50 text-blue-300' :
                    'bg-purple-900/50 text-purple-300'
                  ]">{{ m.vendor || 'HPE' }}</span>
                </div>
                <div class="col-span-2">
                  <span :class="[
                    'text-xs',
                    m.use_same_port ? 'text-emerald-400' : 'text-slate-500'
                  ]">{{ m.use_same_port ? '✓ 啟用' : '✗ 停用' }}</span>
                </div>
                <div class="col-span-1 flex gap-1">
                  <button @click.stop="startEditDevice(m)" class="text-cyan-400 hover:text-cyan-300 px-1" title="編輯">✏️</button>
                  <button @click.stop="confirmDeleteDevice(m)" class="text-rose-400 hover:text-rose-300 px-1" title="刪除">🗑</button>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="p-3 border-t border-slate-700 bg-slate-800 flex justify-end">
        <button @click="$emit('close')" class="px-4 py-1.5 bg-slate-600 text-white rounded hover:bg-slate-500 text-sm">
          關閉
        </button>
      </div>
    </div>
    
    <!-- 確認刪除對話框 -->
    <transition name="fade">
      <div v-if="confirmDialog.show" class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-60">
        <div class="bg-slate-800 border border-slate-600 rounded-lg shadow-2xl p-4 max-w-sm mx-4">
          <div class="text-slate-200 mb-4">{{ confirmDialog.message }}</div>
          <div class="flex justify-end gap-2">
            <button @click="confirmDialog.show = false; confirmDialog.onCancel && confirmDialog.onCancel()"
              class="px-3 py-1.5 bg-slate-600 text-slate-200 rounded text-sm hover:bg-slate-500">取消</button>
            <button @click="confirmDialog.show = false; confirmDialog.onConfirm && confirmDialog.onConfirm()"
              class="px-3 py-1.5 bg-rose-600 text-white rounded text-sm hover:bg-rose-500">確定</button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script>
import { getAuthHeaders } from '@/utils/auth'

export default {
  name: 'DeviceMappingModal',
  props: {
    maintenanceId: { type: String, required: true },
  },
  emits: ['close', 'refresh'],
  data() {
    return {
      deviceMappings: [],
      vendorOptions: ['HPE', 'Cisco-IOS', 'Cisco-NXOS'],
      newDevice: { 
        old_hostname: '', 
        new_hostname: '', 
        vendor: 'HPE',
        use_same_port: true 
      },
      editingDevice: null,
      toast: {
        show: false,
        type: 'error', // 'error' | 'success'
        title: '',
        message: '',
      },
      confirmDialog: {
        show: false,
        message: '',
        onConfirm: null,
        onCancel: null,
      },
    };
  },
  mounted() {
    this.loadDeviceMappings();
  },
  methods: {
    showToast(type, title, message = '', duration = 5000) {
      this.toast = { show: true, type, title, message };
      if (duration > 0) {
        setTimeout(() => { this.toast.show = false; }, duration);
      }
    },
    
    showConfirm(message) {
      return new Promise((resolve) => {
        this.confirmDialog = {
          show: true,
          message,
          onConfirm: () => resolve(true),
          onCancel: () => resolve(false),
        };
      });
    },
    
    async loadDeviceMappings() {
      try {
        const res = await fetch(`/api/v1/device-mappings/${this.maintenanceId}`, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          const data = await res.json();
          this.deviceMappings = data.mappings || [];
        }
      } catch (e) { console.error(e); }
    },
    
    async createDeviceMapping() {
      if (!this.newDevice.old_hostname || !this.newDevice.new_hostname || !this.newDevice.vendor) return;
      try {
        const res = await fetch(`/api/v1/device-mappings/${this.maintenanceId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
          body: JSON.stringify({
            ...this.newDevice,
            maintenance_id: this.maintenanceId
          }),
        });
        if (res.ok) {
          this.newDevice = { 
            old_hostname: '', 
            new_hostname: '', 
            vendor: 'HPE',
            use_same_port: true 
          };
          await this.loadDeviceMappings();
          this.$emit('refresh');
          this.showToast('success', '新增成功');
        } else {
          const err = await res.json();
          this.showToast('error', '無法新增對應', err.detail || '設備對應關係衝突');
        }
      } catch (e) { 
        console.error(e);
        this.showToast('error', '新增失敗', '網路錯誤，請稍後再試');
      }
    },
    
    startEditDevice(m) {
      this.editingDevice = { ...m };
    },
    
    async saveEditDevice() {
      if (!this.editingDevice) return;
      try {
        const res = await fetch(`/api/v1/device-mappings/${this.maintenanceId}/${this.editingDevice.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
          body: JSON.stringify({
            old_hostname: this.editingDevice.old_hostname,
            new_hostname: this.editingDevice.new_hostname,
            vendor: this.editingDevice.vendor,
            use_same_port: this.editingDevice.use_same_port,
          }),
        });
        if (res.ok) {
          this.editingDevice = null;
          await this.loadDeviceMappings();
          this.$emit('refresh');
          this.showToast('success', '更新成功');
        } else {
          const err = await res.json();
          this.showToast('error', '無法更新', err.detail || '設備對應關係衝突');
        }
      } catch (e) { 
        console.error(e);
        this.showToast('error', '更新失敗', '網路錯誤，請稍後再試');
      }
    },
    
    async confirmDeleteDevice(m) {
      const confirmed = await this.showConfirm(`確定要刪除 ${m.old_hostname} → ${m.new_hostname} 嗎？`);
      if (confirmed) {
        this.deleteDevice(m);
      }
    },
    
    async deleteDevice(m) {
      try {
        const res = await fetch(`/api/v1/device-mappings/${this.maintenanceId}/${m.id}`, { method: 'DELETE', headers: getAuthHeaders() });
        if (res.ok) {
          await this.loadDeviceMappings();
          this.$emit('refresh');
          this.showToast('success', '已刪除');
        }
      } catch (e) { console.error(e); }
    },
    
    async clearAllDevices() {
      const confirmed = await this.showConfirm(`確定要清除所有 ${this.deviceMappings.length} 筆設備對應嗎？`);
      if (!confirmed) return;
      try {
        await fetch(`/api/v1/device-mappings/${this.maintenanceId}`, { method: 'DELETE', headers: getAuthHeaders() });
        await this.loadDeviceMappings();
        this.$emit('refresh');
        this.showToast('success', '已清除全部');
      } catch (e) { console.error(e); }
    },
    
    downloadDeviceTemplate() {
      const csv = `old_hostname,new_hostname,vendor,use_same_port
SW-OLD-01,SW-NEW-01,HPE,true
SW-OLD-02,SW-NEW-02,Cisco-IOS,true
SW-OLD-03,SW-NEW-03,Cisco-NXOS,false`;
      const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'device_mappings_template.csv';
      link.click();
    },
    
    async importDeviceCSV(e) {
      const file = e.target.files[0];
      if (!file) return;
      const formData = new FormData();
      formData.append('file', file);
      try {
        const res = await fetch(`/api/v1/device-mappings/${this.maintenanceId}/import-csv`, {
          method: 'POST', body: formData, headers: getAuthHeaders()
        });
        const data = await res.json();
        if (res.ok) {
          this.showToast('success', '導入完成', `新增: ${data.imported} 筆，更新: ${data.updated} 筆`);
          await this.loadDeviceMappings();
          this.$emit('refresh');
        } else {
          this.showToast('error', '導入失敗', data.detail || '格式錯誤');
        }
      } catch (e) { 
        console.error(e);
        this.showToast('error', '導入失敗', '網路錯誤，請稍後再試');
      }
      e.target.value = '';
    },
  },
};
</script>

<style scoped>
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
.z-60 {
  z-index: 60;
}
</style>
