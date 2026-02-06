<template>
  <div class="px-4">
    <!-- 頁面標題 -->
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-xl font-bold text-white">使用者管理</h1>
      <button
        @click="openUserModal()"
        class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition flex items-center gap-2"
      >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
        </svg>
        新增使用者
      </button>
    </div>

    <!-- 待啟用帳號提示 -->
    <div v-if="pendingUsers.length > 0" class="mb-4 p-3 bg-amber-900/30 border border-amber-700/50 rounded-lg">
      <div class="flex items-center gap-2 text-amber-400 text-sm font-medium mb-2">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        有 {{ pendingUsers.length }} 個帳號待啟用
      </div>
      <div class="flex flex-wrap gap-2">
        <div
          v-for="user in pendingUsers"
          :key="user.id"
          class="flex items-center gap-2 px-2 py-1 bg-slate-800 rounded text-sm"
        >
          <span class="text-white">{{ user.username }}</span>
          <span class="text-slate-400 text-xs">({{ user.maintenance_id }})</span>
          <button
            @click="activateUser(user)"
            class="text-green-400 hover:text-green-300 text-xs underline"
          >
            啟用
          </button>
        </div>
      </div>
    </div>

    <!-- 使用者列表 -->
    <div class="bg-slate-800/80 border border-slate-700 rounded-lg overflow-hidden">
      <!-- 表頭 -->
      <div class="grid grid-cols-12 gap-2 px-4 py-3 bg-slate-900/50 border-b border-slate-700 text-xs text-slate-400 uppercase tracking-wide">
        <div class="col-span-1">帳號</div>
        <div class="col-span-2">顯示名稱</div>
        <div class="col-span-2">Email</div>
        <div class="col-span-2">角色</div>
        <div class="col-span-2">歲修 ID</div>
        <div class="col-span-2">最後登入</div>
        <div class="col-span-1 text-right">操作</div>
      </div>

      <!-- 載入中 -->
      <div v-if="loading" class="px-4 py-8 text-center text-slate-400">
        <svg class="w-6 h-6 animate-spin mx-auto mb-2" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        載入中...
      </div>

      <!-- 使用者列表 -->
      <div v-else class="divide-y divide-slate-700/50">
        <div
          v-for="user in activeUsers"
          :key="user.id"
          class="grid grid-cols-12 gap-2 px-4 py-3 hover:bg-slate-700/30 transition group items-center"
        >
          <!-- 帳號 -->
          <div class="col-span-1 flex items-center gap-2">
            <span class="text-white text-sm font-medium truncate">{{ user.username }}</span>
          </div>

          <!-- 顯示名稱 -->
          <div class="col-span-2 text-slate-300 text-sm truncate">
            {{ user.display_name || '-' }}
          </div>

          <!-- Email -->
          <div class="col-span-2 text-slate-400 text-sm truncate">
            {{ user.email || '-' }}
          </div>

          <!-- 角色 -->
          <div class="col-span-2">
            <span :class="getRoleBadgeClass(user.role)">
              {{ getRoleLabel(user.role) }}
            </span>
          </div>

          <!-- 歲修 ID -->
          <div class="col-span-2 text-slate-400 text-sm truncate">
            {{ user.maintenance_id || '-' }}
          </div>

          <!-- 最後登入 -->
          <div class="col-span-2 text-slate-500 text-xs">
            {{ formatDate(user.last_login_at) }}
          </div>

          <!-- 操作 -->
          <div class="col-span-1 flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition">
            <button
              @click="openUserModal(user)"
              class="text-cyan-400 hover:text-cyan-300 p-1"
              title="編輯"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
            <button
              @click="openResetPasswordModal(user)"
              class="text-amber-400 hover:text-amber-300 p-1"
              title="重設密碼"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
              </svg>
            </button>
            <button
              v-if="user.role !== 'root'"
              @click="confirmDelete(user)"
              class="text-red-400 hover:text-red-300 p-1"
              title="刪除"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>

        <!-- 無資料 -->
        <div v-if="activeUsers.length === 0" class="px-4 py-8 text-center text-slate-500">
          尚無使用者資料
        </div>
      </div>
    </div>

    <!-- 新增/編輯使用者 Modal -->
    <div
      v-if="showUserModal"
      class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
      @click.self="showUserModal = false"
    >
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl w-full max-w-md p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-white">{{ editingUser ? '編輯使用者' : '新增使用者' }}</h3>
          <button @click="showUserModal = false" class="text-slate-400 hover:text-slate-200">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form @submit.prevent="saveUser">
          <!-- 帳號 -->
          <div class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">帳號 <span class="text-red-400">*</span></label>
            <input
              v-model="userForm.username"
              type="text"
              :disabled="!!editingUser"
              :class="[
                'w-full px-3 py-2 border border-slate-600 rounded text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400',
                editingUser ? 'bg-slate-800 text-slate-500 cursor-not-allowed' : 'bg-slate-700 text-white'
              ]"
              placeholder="請輸入帳號"
            />
          </div>

          <!-- 密碼（僅新增時） -->
          <div v-if="!editingUser" class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">密碼 <span class="text-red-400">*</span></label>
            <input
              v-model="userForm.password"
              type="password"
              class="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              placeholder="請輸入密碼"
            />
          </div>

          <!-- 顯示名稱 -->
          <div class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">顯示名稱</label>
            <input
              v-model="userForm.display_name"
              type="text"
              class="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              placeholder="請輸入顯示名稱"
            />
          </div>

          <!-- Email -->
          <div class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">Email</label>
            <input
              v-model="userForm.email"
              type="email"
              class="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
              placeholder="請輸入 Email"
            />
          </div>

          <!-- 角色（編輯 root 時隱藏） -->
          <div v-if="editingUser?.role !== 'root'" class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">角色 <span class="text-red-400">*</span></label>
            <select
              v-model="userForm.role"
              :disabled="!!editingUser"
              :class="[
                'w-full px-3 py-2 border border-slate-600 rounded text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400',
                editingUser ? 'bg-slate-800 text-slate-500 cursor-not-allowed' : 'bg-slate-700 text-white'
              ]"
            >
              <option v-for="role in selectableRoles" :key="role.value" :value="role.value">
                {{ role.label }} - {{ role.description }}
              </option>
            </select>
          </div>

          <!-- 歲修 ID（非 root 時） -->
          <div v-if="userForm.role !== 'root'" class="mb-4">
            <label class="block text-sm text-slate-400 mb-1">歲修 ID <span class="text-red-400">*</span></label>
            <select
              v-model="userForm.maintenance_id"
              :disabled="!!editingUser"
              :class="[
                'w-full px-3 py-2 border border-slate-600 rounded text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400',
                editingUser ? 'bg-slate-800 text-slate-500 cursor-not-allowed' : 'bg-slate-700 text-white'
              ]"
            >
              <option value="" disabled>請選擇歲修</option>
              <option v-for="m in maintenances" :key="m.id" :value="m.id">
                {{ m.name || m.id }}
              </option>
            </select>
          </div>

          <!-- 啟用狀態（僅編輯非 root 時） -->
          <div v-if="editingUser && editingUser.role !== 'root'" class="mb-4">
            <label class="flex items-center gap-2 cursor-pointer">
              <input
                v-model="userForm.is_active"
                type="checkbox"
                class="w-4 h-4 rounded border-slate-600 bg-slate-700 text-cyan-500 focus:ring-cyan-400"
              />
              <span class="text-sm text-slate-300">啟用帳號</span>
            </label>
          </div>

          <!-- 按鈕 -->
          <div class="flex justify-end gap-2 mt-6">
            <button
              type="button"
              @click="showUserModal = false"
              class="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded transition"
            >
              取消
            </button>
            <button
              type="submit"
              class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition disabled:opacity-50"
              :disabled="saving || !isUserFormValid"
            >
              {{ saving ? '儲存中...' : '儲存' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- 重設密碼 Modal -->
    <div
      v-if="showResetPasswordModal"
      class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
      @click.self="showResetPasswordModal = false"
    >
      <div class="bg-slate-800 border border-slate-700 rounded-lg shadow-2xl w-full max-w-sm p-5">
        <div class="flex justify-between items-center mb-4">
          <h3 class="text-lg font-bold text-white">重設密碼 - {{ resetPasswordTarget?.username }}</h3>
          <button @click="showResetPasswordModal = false" class="text-slate-400 hover:text-slate-200">
            <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="mb-4">
          <label class="block text-sm text-slate-400 mb-1">新密碼</label>
          <input
            v-model="newPassword"
            type="password"
            class="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded text-white text-sm focus:outline-none focus:ring-1 focus:ring-cyan-400"
            placeholder="請輸入新密碼"
          />
        </div>

        <div class="flex justify-end gap-2">
          <button
            type="button"
            @click="showResetPasswordModal = false"
            class="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded transition"
          >
            取消
          </button>
          <button
            @click="resetPassword"
            class="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm rounded transition disabled:opacity-50"
            :disabled="saving || !newPassword"
          >
            {{ saving ? '重設中...' : '重設密碼' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 刪除確認 Modal -->
    <div
      v-if="showDeleteModal"
      class="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50"
    >
      <div class="bg-slate-800 border border-red-700 rounded-lg shadow-2xl w-full max-w-sm p-5">
        <h3 class="text-lg font-bold text-red-400 mb-4">確認刪除</h3>
        <p class="text-slate-300 mb-4">
          確定要刪除使用者「<span class="text-red-300 font-medium">{{ deleteTarget?.username }}</span>」嗎？
        </p>
        <p class="text-slate-500 text-sm mb-4">此操作無法復原。</p>
        <div class="flex justify-end gap-2">
          <button
            @click="showDeleteModal = false"
            class="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded transition"
          >
            取消
          </button>
          <button
            @click="deleteUser"
            class="px-4 py-2 bg-red-600 hover:bg-red-500 text-white text-sm rounded transition disabled:opacity-50"
            :disabled="saving"
          >
            {{ saving ? '刪除中...' : '確認刪除' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { getAuthHeaders } from '@/utils/auth'
import api from '@/utils/api'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'

dayjs.extend(utc)

const loading = ref(false)
const saving = ref(false)
const users = ref([])
const maintenances = ref([])
const availableRoles = ref([])

// 計算活躍與待啟用用戶
const activeUsers = computed(() => users.value.filter(u => u.is_active))
const pendingUsers = computed(() => users.value.filter(u => !u.is_active))

// 過濾掉 ROOT 角色（不允許建立新的 ROOT 帳號）
const selectableRoles = computed(() => availableRoles.value.filter(r => r.value !== 'root'))

// 使用者表單
const showUserModal = ref(false)
const editingUser = ref(null)
const userForm = ref({
  username: '',
  password: '',
  display_name: '',
  email: '',
  role: 'guest',
  maintenance_id: '',
  is_active: true,
})

// 重設密碼
const showResetPasswordModal = ref(false)
const resetPasswordTarget = ref(null)
const newPassword = ref('')

// 刪除確認
const showDeleteModal = ref(false)
const deleteTarget = ref(null)

const isUserFormValid = computed(() => {
  if (editingUser.value) {
    return true
  }
  // 新增時：需要帳號、密碼、角色
  if (!userForm.value.username || !userForm.value.password || !userForm.value.role) {
    return false
  }
  // 非 root 需要歲修 ID
  if (userForm.value.role !== 'root' && !userForm.value.maintenance_id) {
    return false
  }
  return true
})

const formatDate = (dateStr) => {
  if (!dateStr) return '-'
  return dayjs.utc(dateStr).local().format('YYYY-MM-DD HH:mm')
}

const getRoleLabel = (role) => {
  const labels = {
    root: '管理員',
    pm: 'PM',
    guest: '訪客',
  }
  return labels[role] || role
}

const getRoleBadgeClass = (role) => {
  const classes = {
    root: 'px-1.5 py-0.5 bg-amber-600/30 text-amber-400 text-xs rounded',
    pm: 'px-1.5 py-0.5 bg-cyan-600/30 text-cyan-400 text-xs rounded',
    guest: 'px-1.5 py-0.5 bg-slate-600/30 text-slate-400 text-xs rounded',
  }
  return classes[role] || 'px-1.5 py-0.5 bg-slate-600/30 text-slate-400 text-xs rounded'
}

const loadUsers = async () => {
  loading.value = true
  try {
    const res = await fetch('/api/v1/users?include_inactive=true', {
      headers: getAuthHeaders(),
    })
    if (res.ok) {
      users.value = await res.json()
    }
  } catch (e) {
    console.error('載入使用者失敗:', e)
  } finally {
    loading.value = false
  }
}

const loadMaintenances = async () => {
  try {
    const response = await api.get('/maintenance')
    maintenances.value = response.data || []
  } catch (e) {
    console.error('載入歲修列表失敗:', e)
  }
}

const loadAvailableRoles = async () => {
  try {
    const res = await fetch('/api/v1/users/roles/available', {
      headers: getAuthHeaders(),
    })
    if (res.ok) {
      availableRoles.value = await res.json()
    }
  } catch (e) {
    console.error('載入角色列表失敗:', e)
  }
}

const openUserModal = async (user = null) => {
  // 重新載入歲修列表，確保有最新資料
  await loadMaintenances()

  editingUser.value = user
  if (user) {
    userForm.value = {
      username: user.username,
      password: '',
      display_name: user.display_name || '',
      email: user.email || '',
      role: user.role,
      maintenance_id: user.maintenance_id || '',
      is_active: user.is_active,
    }
  } else {
    userForm.value = {
      username: '',
      password: '',
      display_name: '',
      email: '',
      role: 'pm',
      maintenance_id: '',
      is_active: true,
    }
  }
  showUserModal.value = true
}

const saveUser = async () => {
  saving.value = true
  try {
    if (editingUser.value) {
      // 更新
      const payload = {
        display_name: userForm.value.display_name || null,
        email: userForm.value.email || null,
      }
      // 只有非 root 使用者才能更改啟用狀態（角色和歲修 ID 已鎖定）
      if (editingUser.value.role !== 'root') {
        payload.is_active = userForm.value.is_active
      }
      const res = await fetch(`/api/v1/users/${editingUser.value.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const err = await res.json()
        alert(`更新失敗: ${err.detail || '未知錯誤'}`)
        return
      }
    } else {
      // 新增
      const res = await fetch('/api/v1/users', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          username: userForm.value.username,
          password: userForm.value.password,
          display_name: userForm.value.display_name || null,
          email: userForm.value.email || null,
          role: userForm.value.role,
          maintenance_id: userForm.value.role === 'root' ? null : userForm.value.maintenance_id,
        }),
      })
      if (!res.ok) {
        const err = await res.json()
        alert(`新增失敗: ${err.detail || '未知錯誤'}`)
        return
      }
    }
    showUserModal.value = false
    await loadUsers()
  } finally {
    saving.value = false
  }
}

const activateUser = async (user) => {
  saving.value = true
  try {
    const res = await fetch(`/api/v1/users/${user.id}/activate`, {
      method: 'POST',
      headers: getAuthHeaders(),
    })
    if (!res.ok) {
      const err = await res.json()
      alert(`啟用失敗: ${err.detail || '未知錯誤'}`)
      return
    }
    await loadUsers()
  } finally {
    saving.value = false
  }
}

const openResetPasswordModal = (user) => {
  resetPasswordTarget.value = user
  newPassword.value = ''
  showResetPasswordModal.value = true
}

const resetPassword = async () => {
  if (!resetPasswordTarget.value || !newPassword.value) return
  saving.value = true
  try {
    const res = await fetch(`/api/v1/users/${resetPasswordTarget.value.id}/reset-password`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ new_password: newPassword.value }),
    })
    if (!res.ok) {
      const err = await res.json()
      alert(`重設失敗: ${err.detail || '未知錯誤'}`)
      return
    }
    showResetPasswordModal.value = false
    alert('密碼已重設')
  } finally {
    saving.value = false
  }
}

const confirmDelete = (user) => {
  deleteTarget.value = user
  showDeleteModal.value = true
}

const deleteUser = async () => {
  if (!deleteTarget.value) return
  saving.value = true
  try {
    const res = await fetch(`/api/v1/users/${deleteTarget.value.id}`, {
      method: 'DELETE',
      headers: getAuthHeaders(),
    })
    if (!res.ok) {
      const err = await res.json()
      alert(`刪除失敗: ${err.detail || '未知錯誤'}`)
      return
    }
    showDeleteModal.value = false
    await loadUsers()
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadMaintenances(), loadAvailableRoles()])
})
</script>
