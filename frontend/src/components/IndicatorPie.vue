<!-- filepath: /Users/coolguazi/Project/ClineTest/network_dashboard/frontend/src/components/IndicatorPie.vue -->
<template>
  <div class="bg-white rounded-lg shadow p-2.5 cursor-pointer hover:shadow-lg transition"
       @click="$emit('click')"
       :class="{ 'ring-2 ring-blue-500': isSelected }">
    
    <div class="flex items-center justify-between mb-1.5">
      <h3 class="text-sm font-bold text-gray-800">{{ getTitle(type) }}</h3>
      <span class="text-lg">{{ getIcon(type) }}</span>
    </div>

    <!-- 大數字 + 雙色進度條 -->
    <div class="mb-2">
      <div class="text-center mb-1.5">
        <div class="text-2xl font-bold" :class="statusColor">{{ passPercent }}%</div>
        <div class="text-xs text-gray-500">通過率</div>
      </div>
      
      <!-- 雙色堆疊條 -->
      <div class="flex h-2 rounded-full overflow-hidden bg-gray-100">
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
    <div class="space-y-1 text-xs">
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-1">
          <div class="w-2 h-2 bg-green-600 rounded-full"></div>
          <span class="text-gray-700">通過</span>
        </div>
        <span class="font-bold text-green-600">{{ data.pass_count }}</span>
      </div>
      <div class="flex justify-between items-center">
        <div class="flex items-center gap-1">
          <div class="w-2 h-2 bg-red-600 rounded-full"></div>
          <span class="text-gray-700">失敗</span>
        </div>
        <span class="font-bold text-red-600">{{ data.fail_count }}</span>
      </div>
      <div class="border-t pt-1.5 flex justify-between items-center">
        <span class="text-gray-600">總數</span>
        <span class="font-bold">{{ data.total_count }}</span>
      </div>
    </div>

    <!-- 摘要 -->
    <p class="mt-2 text-xs text-gray-600 text-center leading-snug">{{ data.summary }}</p>
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
    transceiver: '💡',
    version: '📦',
    uplink: '🔗',
    port_channel: '⛓️',
  }
  return icons[type] || '📊'
}
</script>