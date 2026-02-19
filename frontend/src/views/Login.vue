<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 flex items-center justify-center px-4 relative">
    <!-- 彩色雲霧動畫 -->
    <div class="absolute inset-0 nebula-container">
      <div class="nebula nebula-1"></div>
      <div class="nebula nebula-2"></div>
      <div class="nebula nebula-3"></div>
      <div class="nebula nebula-4"></div>
    </div>
    <!-- 網格背景 -->
    <div class="absolute inset-0 grid-bg"></div>
    <div class="w-full max-w-sm relative z-10">
      <!-- Logo -->
      <div class="text-center mb-8">
        <div class="text-3xl font-black tracking-[0.12em] logo-wrapper">
          <span class="logo-text bg-gradient-to-r from-cyan-400 via-blue-500 via-purple-400 to-cyan-300 bg-clip-text text-transparent">NETORA</span>
          <span class="logo-glow" aria-hidden="true">
            <span class="glow-letter glow-1">N</span>
            <span class="glow-letter glow-2">E</span>
            <span class="glow-letter glow-3">T</span>
            <span class="glow-letter glow-4">O</span>
            <span class="glow-letter glow-5">R</span>
            <span class="glow-letter glow-6">A</span>
          </span>
        </div>
        <div class="text-[11px] text-cyan-400/70 tracking-[0.32em] mt-0.5">CHANGE MONITOR</div>
      </div>

      <!-- 表單卡片 -->
      <div class="bg-slate-800 border border-slate-700 rounded-xl p-6 shadow-xl">
        <!-- Tab 切換 -->
        <div class="flex mb-6 bg-slate-900 rounded-lg p-1">
          <button
            @click="activeTab = 'login'"
            :class="[
              'flex-1 py-2 text-sm font-medium rounded-md transition',
              activeTab === 'login'
                ? 'bg-cyan-600 text-white'
                : 'text-slate-400 hover:text-white'
            ]"
          >
            登入
          </button>
          <button
            @click="activeTab = 'register'"
            :class="[
              'flex-1 py-2 text-sm font-medium rounded-md transition',
              activeTab === 'register'
                ? 'bg-cyan-600 text-white'
                : 'text-slate-400 hover:text-white'
            ]"
          >
            訪客註冊
          </button>
        </div>

        <!-- 登入表單 -->
        <form v-if="activeTab === 'login'" @submit.prevent="handleLogin">
          <!-- 錯誤訊息 -->
          <Transition name="slide-down">
          <div v-if="errorMsg" key="login-error" class="shake mb-4 p-3 bg-red-900/30 border border-red-700/50 rounded text-red-300 text-sm">
            {{ errorMsg }}
          </div>
          </Transition>

          <!-- 帳號 -->
          <div class="mb-4 field-stagger" style="animation-delay: 0ms">
            <label class="block text-sm text-slate-400 mb-1.5">帳號</label>
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              class="w-full px-4 py-2.5 bg-slate-900 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent transition"
              placeholder="請輸入帳號"
              :disabled="loading"
            />
          </div>

          <!-- 密碼 -->
          <div class="mb-6 field-stagger" style="animation-delay: 80ms">
            <label class="block text-sm text-slate-400 mb-1.5">密碼</label>
            <div class="relative">
              <input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                class="w-full px-4 py-2.5 pr-10 bg-slate-900 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent transition"
                placeholder="請輸入密碼"
                :disabled="loading"
                @keyup.enter="handleLogin"
              />
              <button
                type="button"
                @click="showPassword = !showPassword"
                class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 transition"
                tabindex="-1"
              >
                <svg v-if="showPassword" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
              </button>
            </div>
          </div>

          <!-- 登入按鈕 -->
          <button
            type="submit"
            class="field-stagger w-full py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition flex items-center justify-center gap-2"
            style="animation-delay: 160ms"
            :disabled="loading || !username || !password"
          >
            <svg v-if="loading" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span>{{ loading ? '登入中...' : '登入' }}</span>
          </button>
        </form>

        <!-- 註冊表單 -->
        <form v-else @submit.prevent="handleRegister">
          <!-- 成功訊息 -->
          <Transition name="slide-down">
          <div v-if="successMsg" key="reg-success" class="mb-4 p-3 bg-green-900/30 border border-green-700/50 rounded text-green-300 text-sm">
            {{ successMsg }}
          </div>
          </Transition>

          <!-- 錯誤訊息 -->
          <Transition name="slide-down">
          <div v-if="errorMsg" key="reg-error" class="shake mb-4 p-3 bg-red-900/30 border border-red-700/50 rounded text-red-300 text-sm">
            {{ errorMsg }}
          </div>
          </Transition>

          <!-- 歲修 ID 選擇 -->
          <div class="mb-4 field-stagger" style="animation-delay: 0ms">
            <label class="block text-sm text-slate-400 mb-1.5">選擇歲修</label>
            <select
              v-model="regMaintenanceId"
              class="w-full px-4 py-2.5 bg-slate-900 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent transition"
              :disabled="loading || loadingMaintenances"
            >
              <option value="" disabled>{{ loadingMaintenances ? '載入中...' : '請選擇歲修' }}</option>
              <option v-for="m in maintenances" :key="m.id" :value="m.id">
                {{ m.name || m.id }}
              </option>
            </select>
          </div>

          <!-- 帳號 -->
          <div class="mb-4 field-stagger" style="animation-delay: 80ms">
            <label class="block text-sm text-slate-400 mb-1.5">帳號</label>
            <input
              v-model="regUsername"
              type="text"
              autocomplete="username"
              class="w-full px-4 py-2.5 bg-slate-900 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent transition"
              placeholder="請設定帳號"
              :disabled="loading"
            />
          </div>

          <!-- 顯示名稱 -->
          <div class="mb-4 field-stagger" style="animation-delay: 160ms">
            <div class="flex items-center gap-1.5 mb-1.5">
              <label class="text-sm text-slate-400">顯示名稱 <span class="text-red-400">*</span></label>
              <div class="relative group/dn">
                <svg class="w-3.5 h-3.5 text-slate-500 group-hover/dn:text-amber-400 transition cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div class="absolute left-0 bottom-full mb-2 w-64 px-3 py-2 bg-amber-50 border border-amber-300 rounded-lg shadow-lg text-xs text-amber-900 leading-relaxed opacity-0 invisible group-hover/dn:opacity-100 group-hover/dn:visible transition-all duration-200 z-50 pointer-events-none"
                  style="filter: drop-shadow(0 2px 8px rgba(217, 160, 0, 0.2));"
                >
                  此名稱將作為您在系統中的識別名稱，用於案件指派與操作記錄。名稱不可與其他使用者重複。
                  <div class="absolute left-3 top-full w-0 h-0 border-l-[6px] border-r-[6px] border-t-[6px] border-transparent border-t-amber-300"></div>
                  <div class="absolute left-3 top-full -mt-px w-0 h-0 border-l-[6px] border-r-[6px] border-t-[6px] border-transparent border-t-amber-50"></div>
                </div>
              </div>
            </div>
            <input
              v-model="regDisplayName"
              type="text"
              class="w-full px-4 py-2.5 bg-slate-900 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent transition"
              placeholder="您的名稱（不可與他人重複）"
              :disabled="loading"
            />
          </div>

          <!-- 密碼 -->
          <div class="mb-4 field-stagger" style="animation-delay: 240ms">
            <label class="block text-sm text-slate-400 mb-1.5">密碼</label>
            <div class="relative">
              <input
                v-model="regPassword"
                :type="showRegPassword ? 'text' : 'password'"
                autocomplete="new-password"
                class="w-full px-4 py-2.5 pr-10 bg-slate-900 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent transition"
                placeholder="請設定密碼"
                :disabled="loading"
              />
              <button
                type="button"
                @click="showRegPassword = !showRegPassword"
                class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 transition"
                tabindex="-1"
              >
                <svg v-if="showRegPassword" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
              </button>
            </div>
          </div>

          <!-- 確認密碼 -->
          <div class="mb-6 field-stagger" style="animation-delay: 320ms">
            <label class="block text-sm text-slate-400 mb-1.5">確認密碼</label>
            <div class="relative">
              <input
                v-model="regPasswordConfirm"
                :type="showRegPasswordConfirm ? 'text' : 'password'"
                autocomplete="new-password"
                class="w-full px-4 py-2.5 pr-10 bg-slate-900 border border-slate-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-cyan-500 focus:border-transparent transition"
                placeholder="再次輸入密碼"
                :disabled="loading"
              />
              <button
                type="button"
                @click="showRegPasswordConfirm = !showRegPasswordConfirm"
                class="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 transition"
                tabindex="-1"
              >
                <svg v-if="showRegPasswordConfirm" xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
                <svg v-else xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
              </button>
            </div>
          </div>

          <!-- 註冊按鈕 -->
          <button
            type="submit"
            class="field-stagger w-full py-2.5 bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white font-medium rounded-lg transition flex items-center justify-center gap-2"
            style="animation-delay: 400ms"
            :disabled="loading || !canRegister"
          >
            <svg v-if="loading" class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span>{{ loading ? '註冊中...' : '申請帳號' }}</span>
          </button>

          <!-- 提示 -->
          <div class="mt-4 text-xs text-slate-500 text-center">
            訪客帳號為唯讀權限，註冊後需等待管理員啟用
          </div>
        </form>
      </div>

      <!-- 底部提示 -->
      <div class="text-center mt-4 text-xs text-slate-500">
        {{ activeTab === 'login' ? '首次使用可切換至「訪客註冊」申請帳號' : '已有帳號？切換至「登入」' }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { login } from '@/utils/auth'
import api from '@/utils/api'

const router = useRouter()

// Tab 狀態
const activeTab = ref('login')

// 登入表單
const username = ref('')
const password = ref('')
const showPassword = ref(false)

// 註冊表單
const regMaintenanceId = ref('')
const regUsername = ref('')
const regDisplayName = ref('')
const regPassword = ref('')
const regPasswordConfirm = ref('')
const showRegPassword = ref(false)
const showRegPasswordConfirm = ref(false)

// 歲修列表
const maintenances = ref([])
const loadingMaintenances = ref(false)

// 狀態
const loading = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

// 計算是否可以註冊
const canRegister = computed(() => {
  return regMaintenanceId.value &&
    regUsername.value &&
    regDisplayName.value.trim() &&
    regPassword.value &&
    regPassword.value === regPasswordConfirm.value
})

// 載入歲修列表（使用公開端點，不需要認證）
const loadMaintenances = async () => {
  loadingMaintenances.value = true
  try {
    const response = await api.get('/auth/maintenances-public')
    maintenances.value = response.data || []
  } catch (err) {
    console.error('Failed to load maintenances:', err)
  } finally {
    loadingMaintenances.value = false
  }
}

// 登入處理
const handleLogin = async () => {
  if (!username.value || !password.value) return

  loading.value = true
  errorMsg.value = ''
  successMsg.value = ''

  const result = await login(username.value, password.value)

  loading.value = false

  if (result.ok) {
    const redirect = router.currentRoute.value.query.redirect || '/'
    router.push(redirect)
  } else {
    errorMsg.value = result.error
  }
}

// 註冊處理
const handleRegister = async () => {
  if (!canRegister.value) return

  if (regPassword.value !== regPasswordConfirm.value) {
    errorMsg.value = '兩次輸入的密碼不一致'
    return
  }

  loading.value = true
  errorMsg.value = ''
  successMsg.value = ''

  try {
    await api.post('/auth/register-guest', {
      username: regUsername.value,
      password: regPassword.value,
      maintenance_id: regMaintenanceId.value,
      display_name: regDisplayName.value.trim(),
    })

    successMsg.value = '註冊成功！請聯繫管理員啟用您的帳號。'

    // 清空表單
    regUsername.value = ''
    regDisplayName.value = ''
    regPassword.value = ''
    regPasswordConfirm.value = ''
  } catch (err) {
    errorMsg.value = err.response?.data?.detail || '註冊失敗，請稍後再試'
  } finally {
    loading.value = false
  }
}

// 切換 tab 時清空訊息
const clearMessages = () => {
  errorMsg.value = ''
  successMsg.value = ''
}

onMounted(() => {
  loadMaintenances()
})
</script>

<style scoped>
/* 雲霧容器 */
.nebula-container {
  overflow: hidden;
  filter: blur(30px);
  opacity: 0.7;
}

/* 彩色雲霧基底 */
.nebula {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 60%;
  height: 60%;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  mix-blend-mode: screen;
}

/* 粉紅雲 */
.nebula-1 {
  background: radial-gradient(ellipse 80% 60% at 30% 40%,
    rgba(255,100,150,0.8) 0%,
    rgba(255,80,120,0.4) 30%,
    transparent 70%
  );
  animation: drift1 32s ease-in-out infinite;
}

/* 青色雲 */
.nebula-2 {
  background: radial-gradient(ellipse 70% 80% at 70% 60%,
    rgba(80,220,255,0.8) 0%,
    rgba(60,180,220,0.4) 30%,
    transparent 70%
  );
  animation: drift2 40s ease-in-out infinite;
}

/* 紫色雲 */
.nebula-3 {
  background: radial-gradient(ellipse 60% 70% at 50% 30%,
    rgba(180,100,255,0.7) 0%,
    rgba(140,80,200,0.35) 30%,
    transparent 70%
  );
  animation: drift3 48s ease-in-out infinite;
}

/* 橙黃雲 */
.nebula-4 {
  background: radial-gradient(ellipse 50% 60% at 40% 70%,
    rgba(255,180,80,0.6) 0%,
    rgba(255,140,60,0.3) 30%,
    transparent 70%
  );
  animation: drift4 36s ease-in-out infinite;
}

@keyframes drift1 {
  0%, 100% { transform: translate(-50%, -50%) rotate(0deg) scale(1); }
  25% { transform: translate(-45%, -55%) rotate(15deg) scale(1.1); }
  50% { transform: translate(-55%, -45%) rotate(-10deg) scale(0.95); }
  75% { transform: translate(-48%, -52%) rotate(5deg) scale(1.05); }
}

@keyframes drift2 {
  0%, 100% { transform: translate(-50%, -50%) rotate(0deg) scale(1); }
  25% { transform: translate(-55%, -48%) rotate(-20deg) scale(1.05); }
  50% { transform: translate(-45%, -52%) rotate(15deg) scale(1.1); }
  75% { transform: translate(-52%, -45%) rotate(-5deg) scale(0.95); }
}

@keyframes drift3 {
  0%, 100% { transform: translate(-50%, -50%) rotate(0deg) scale(1); }
  33% { transform: translate(-48%, -55%) rotate(25deg) scale(1.15); }
  66% { transform: translate(-52%, -48%) rotate(-15deg) scale(0.9); }
}

@keyframes drift4 {
  0%, 100% { transform: translate(-50%, -50%) rotate(0deg) scale(1); }
  20% { transform: translate(-55%, -52%) rotate(-10deg) scale(1.1); }
  40% { transform: translate(-45%, -48%) rotate(20deg) scale(0.95); }
  60% { transform: translate(-52%, -55%) rotate(-5deg) scale(1.05); }
  80% { transform: translate(-48%, -45%) rotate(10deg) scale(1); }
}

.grid-bg {
  background-image:
    linear-gradient(rgba(6,182,212,0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(6,182,212,0.08) 1px, transparent 1px);
  background-size: 4px 4px;
  mask-image: radial-gradient(ellipse 60% 50% at 50% 50%, transparent 20%, black 60%);
  -webkit-mask-image: radial-gradient(ellipse 60% 50% at 50% 50%, transparent 20%, black 60%);
}

/* Logo 字母發光動畫 */
.logo-wrapper {
  position: relative;
  display: inline-block;
}

.logo-text {
  position: relative;
  z-index: 1;
}

.logo-glow {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 2;
  pointer-events: none;
  display: inline-flex;
}

.glow-letter {
  color: transparent;
  text-shadow:
    0 0 12px rgba(255, 255, 255, 1),
    0 0 28px rgba(255, 255, 255, 0.9),
    0 0 55px rgba(255, 255, 255, 0.6),
    0 0 90px rgba(250, 252, 255, 0.4);
  opacity: 0;
  animation: glow 20s ease-in-out infinite;
}

/* 動畫順序 N→E→T→O→R→A，純白核心 + 彩虹邊緣 */
.glow-1 {
  animation-delay: 0s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(255, 220, 220, 0.6),
    0 0 90px rgba(255, 100, 100, 0.35),
    0 0 120px rgba(255, 50, 50, 0.2);
}
.glow-2 {
  animation-delay: 0.3s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(255, 240, 200, 0.6),
    0 0 90px rgba(255, 180, 50, 0.35),
    0 0 120px rgba(255, 150, 0, 0.2);
}
.glow-3 {
  animation-delay: 0.6s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(220, 255, 220, 0.6),
    0 0 90px rgba(100, 255, 100, 0.35),
    0 0 120px rgba(0, 220, 100, 0.2);
}
.glow-4 {
  animation-delay: 0.9s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(200, 240, 255, 0.6),
    0 0 90px rgba(50, 200, 255, 0.35),
    0 0 120px rgba(0, 180, 255, 0.2);
}
.glow-5 {
  animation-delay: 1.2s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(220, 220, 255, 0.6),
    0 0 90px rgba(100, 100, 255, 0.35),
    0 0 120px rgba(80, 50, 255, 0.2);
}
.glow-6 {
  animation-delay: 1.5s;
  text-shadow:
    0 0 15px rgba(255, 255, 255, 1),
    0 0 35px rgba(255, 255, 255, 0.95),
    0 0 60px rgba(255, 220, 255, 0.6),
    0 0 90px rgba(255, 100, 255, 0.35),
    0 0 120px rgba(220, 50, 255, 0.2);
}

@keyframes glow {
  0% {
    opacity: 0;
  }
  4% {
    opacity: 1;
  }
  10% {
    opacity: 0.75;
  }
  18%, 100% {
    opacity: 0;
  }
}
</style>
