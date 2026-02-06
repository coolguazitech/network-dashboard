<template>
  <div class="container mx-auto px-4 py-8">
    <div class="flex justify-between items-center mb-6">
      <h1 class="text-3xl font-bold">設備管理</h1>
      <button
        @click="openAddModal"
        class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors"
      >
        ➕ 新增設備
      </button>
    </div>

    <!-- 載入中 -->
    <div v-if="loading" class="flex justify-center items-center py-12">
      <div class="text-gray-500">載入中...</div>
    </div>

    <!-- 無數據 -->
    <div v-else-if="!switches || switches.length === 0" class="text-center py-12 text-gray-500">
      暫無設備資料
    </div>

    <!-- 設備列表 -->
    <div v-else class="bg-white rounded-lg shadow overflow-hidden">
      <table class="min-w-full divide-y divide-gray-200">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              主機名稱
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              IP 位址
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              廠商
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              平台
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              站點
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              狀態
            </th>
            <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
              操作
            </th>
          </tr>
        </thead>
        <tbody class="bg-white divide-y divide-gray-200">
          <tr v-for="sw in switches" :key="sw.id" class="hover:bg-gray-50">
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="text-sm font-medium text-gray-900">{{ sw.hostname }}</div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <div class="text-sm text-gray-500">{{ sw.ip_address }}</div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">
                {{ sw.vendor }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ sw.platform }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
              {{ sw.site || '-' }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span
                :class="sw.is_active ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'"
                class="px-2 inline-flex text-xs leading-5 font-semibold rounded-full"
              >
                {{ sw.is_active ? '啟用' : '停用' }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
              <button
                @click="editSwitch(sw)"
                class="text-indigo-600 hover:text-indigo-900 mr-3"
              >
                編輯
              </button>
              <button
                @click="confirmDelete(sw)"
                class="text-red-600 hover:text-red-900"
              >
                刪除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 新增/編輯 Modal -->
    <div
      v-if="showModal"
      class="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50"
      @click.self="closeModal"
    >
      <div class="relative top-20 mx-auto p-5 border w-full max-w-2xl shadow-lg rounded-md bg-white">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-medium">{{ isEditMode ? '編輯設備' : '新增設備' }}</h3>
          <button @click="closeModal" class="text-gray-400 hover:text-gray-600">
            ✕
          </button>
        </div>

        <form @submit.prevent="saveSwitch" class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <!-- 主機名稱 -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                主機名稱 <span class="text-red-500">*</span>
              </label>
              <input
                v-model="formData.hostname"
                type="text"
                required
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="例如: core-switch-01"
              />
            </div>

            <!-- IP 位址 -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                IP 位址 <span class="text-red-500">*</span>
              </label>
              <input
                v-model="formData.ip_address"
                type="text"
                required
                pattern="^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="例如: 192.168.1.1"
              />
            </div>

            <!-- 廠商 -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                廠商 <span class="text-red-500">*</span>
              </label>
              <select
                v-model="formData.vendor"
                required
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">請選擇廠商</option>
                <option value="cisco">Cisco</option>
                <option value="aruba">Aruba</option>
                <option value="hpe">HPE</option>
                <option value="huawei">Huawei</option>
                <option value="other">其他</option>
              </select>
            </div>

            <!-- 平台 -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                平台 <span class="text-red-500">*</span>
              </label>
              <select
                v-model="formData.platform"
                required
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">請選擇平台</option>
                <option value="ios">IOS</option>
                <option value="nxos">NX-OS</option>
                <option value="aruba_os">ArubaOS</option>
                <option value="aruba_cx">ArubaOS-CX</option>
                <option value="comware">Comware</option>
              </select>
            </div>

            <!-- 站點 -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                站點 <span class="text-red-500">*</span>
              </label>
              <select
                v-model="formData.site"
                required
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">請選擇站點</option>
                <option value="datacenter">資料中心</option>
                <option value="office">辦公室</option>
                <option value="branch">分支</option>
              </select>
            </div>

            <!-- 型號 -->
            <div>
              <label class="block text-sm font-medium text-gray-700 mb-1">
                型號
              </label>
              <input
                v-model="formData.model"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="例如: C9300-48P"
              />
            </div>
          </div>

          <!-- 位置 -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              位置
            </label>
            <input
              v-model="formData.location"
              type="text"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="例如: 機房 A 櫃 5"
            />
          </div>

          <!-- 備註 -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">
              備註
            </label>
            <textarea
              v-model="formData.description"
              rows="3"
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="備註說明"
            ></textarea>
          </div>

          <!-- 啟用狀態 -->
          <div class="flex items-center">
            <input
              v-model="formData.is_active"
              type="checkbox"
              id="is_active"
              class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
            />
            <label for="is_active" class="ml-2 block text-sm text-gray-900">
              啟用
            </label>
          </div>

          <!-- 按鈕 -->
          <div class="flex justify-end space-x-3 pt-4 border-t">
            <button
              type="button"
              @click="closeModal"
              class="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              取消
            </button>
            <button
              type="submit"
              class="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
            >
              {{ isEditMode ? '更新' : '新增' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- 刪除確認 Modal -->
    <div
      v-if="showDeleteConfirm"
      class="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50"
      @click.self="cancelDelete"
    >
      <div class="relative top-1/3 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white">
        <div class="mt-3 text-center">
          <h3 class="text-lg leading-6 font-medium text-gray-900 mb-2">確認刪除</h3>
          <div class="mt-2 px-7 py-3">
            <p class="text-sm text-gray-500">
              確定要刪除設備 <strong>{{ deleteTarget?.hostname }}</strong> 嗎？此操作無法復原。
            </p>
          </div>
          <div class="flex justify-center space-x-3 mt-4">
            <button
              @click="cancelDelete"
              class="px-4 py-2 bg-gray-200 text-gray-800 text-sm font-medium rounded-md hover:bg-gray-300"
            >
              取消
            </button>
            <button
              @click="deleteSwitch"
              class="px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-md hover:bg-red-700"
            >
              確認刪除
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { getAuthHeaders } from '@/utils/auth'

export default {
  name: 'Switches',
  data() {
    return {
      switches: [],
      loading: false,
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
        const response = await fetch('/api/v1/switches', {
          headers: getAuthHeaders()
        })
        const data = await response.json()
        this.switches = data.data || []
      } catch (error) {
        console.error('載入設備列表失敗:', error)
        alert('載入設備列表失敗')
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
      try {
        const url = this.isEditMode
          ? `/api/v1/switches/${this.formData.id}`
          : '/api/v1/switches'
        
        const method = this.isEditMode ? 'PUT' : 'POST'
        
        const response = await fetch(url, {
          method,
          headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders()
          },
          body: JSON.stringify(this.formData)
        })

        if (response.ok) {
          alert(this.isEditMode ? '設備更新成功' : '設備新增成功')
          this.closeModal()
          this.loadSwitches()
        } else {
          const error = await response.json()
          alert(`操作失敗: ${error.detail || '未知錯誤'}`)
        }
      } catch (error) {
        console.error('儲存設備失敗:', error)
        alert('儲存設備失敗')
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
      try {
        const response = await fetch(`/api/v1/switches/${this.deleteTarget.id}`, {
          method: 'DELETE',
          headers: getAuthHeaders()
        })

        if (response.ok) {
          alert('設備刪除成功')
          this.cancelDelete()
          this.loadSwitches()
        } else {
          const error = await response.json()
          alert(`刪除失敗: ${error.detail || '未知錯誤'}`)
        }
      } catch (error) {
        console.error('刪除設備失敗:', error)
        alert('刪除設備失敗')
      }
    }
  }
}
</script>
