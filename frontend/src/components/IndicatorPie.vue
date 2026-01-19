<!-- filepath: /Users/coolguazi/Project/ClineTest/network_dashboard/frontend/src/components/IndicatorPie.vue -->
<template>
  <div class="bg-white rounded-lg shadow p-6 cursor-pointer hover:shadow-lg transition"
       @click="$emit('click')"
       :class="{ 'ring-2 ring-blue-500': isSelected }">
    
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-bold text-gray-800">{{ getTitle(type) }}</h3>
      <span class="text-3xl">{{ getIcon(type) }}</span>
    </div>

    <!-- 大數字 + 雙色進度條 -->
    <div class="mb-6">
      <div class="text-center mb-4">
        <div class="text-5xl font-bold" :class="statusColor">{{ passPercent }}%</div>
        <div class="text-sm text-gray-500 mt-1">通過率</div>
      </div>
      
      <!-- 雙色堆疊條 -->
      <div class="flex h-4 rounded-full overflow-hidden bg-gray-100">
        <div 
          class="bg-green-600 transition-all duration-500"
          :style="{ width: passPercent + '%' }"
        ></div>
        <div 
          class="bg-red-600 transition-all duration-500"
          :style="{ width: (100 - passPercent) + '%' }"
        ></div>
      </div>
    </div>

    <!-- 統計數字 -->
    <div class="space-y-2 text-sm">
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 bg-green-600 rounded-full"></div>
          <span class="text-gray-700">通過</span>
        </div>
        <span class="font-bold text-green-600">{{ data.pass_count }}</span>
      </div>
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-2">
          <div class="w-3 h-3 bg-red-600 rounded-full"></div>
          <span class="text-gray-700">失敗</span>
        </div>
        <span class="font-bold text-red-600">{{ data.fail_count }}</span>
      </div>
      <div class="border-t pt-2 flex justify-between items-center">
        <span class="text-gray-600">總數</span>
        <span class="font-bold">{{ data.total_count }}</span>
      </div>
    </div>

    <!-- 摘要 -->
    <p class="mt-4 text-xs text-gray-600 text-center leading-relaxed">{{ data.summary }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  type: String,
  data: Object,
  isSelected: Boolean,
})

defineEmits(['click'])

const passPercent = computed(() => {
  if (!props.data || props.data.total_count === 0) return 0
  return Math.round((props.data.pass_count / props.data.total_count) * 100)
})

const statusColor = computed(() => {
  if (passPercent.value === 100) return 'text-green-600'
  if (passPercent.value >= 80) return 'text-yellow-600'
  return 'text-red-600'
})

const getTitle = (type) => {
  const titles = {
    transceiver: '光模塊驗收',
    version: '版本驗收',
    uplink: 'Uplink 驗收',
  }
  return titles[type] || type
}

const getIcon = (type) => {
  const icons = {
    transceiver: '🔌',
    version: '📦',
    uplink: '🔗',
  }
  return icons[type] || '📊'
}
</script>