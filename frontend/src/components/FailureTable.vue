<!-- filepath: /Users/coolguazi/Project/ClineTest/network_dashboard/frontend/src/components/FailureTable.vue -->
<template>
  <div>
    <div v-if="failures.length === 0" class="text-center py-8 text-gray-500">
      ✅ 無失敗項目 - 所有檢查都通過了！
    </div>

    <div v-else class="overflow-x-auto">
      <table class="min-w-full">
        <thead class="bg-gray-50">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">
              設備
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">
              {{ columnTitle }}
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">
              問題描述
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200">
          <tr v-for="(failure, idx) in failures" :key="idx" class="hover:bg-gray-50">
            <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
              {{ failure.device }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-700">
              {{ getInterfaceName(failure) }}
            </td>
            <td class="px-6 py-4 text-sm text-red-600">
              {{ failure.reason }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  failures: Array,
  indicatorType: String,
})

const columnTitle = computed(() => {
  const titles = {
    transceiver: '接口',
    version: '設備',
    uplink: '鄰居',
  }
  return titles[props.indicatorType] || '項目'
})

const getInterfaceName = (failure) => {
  if (props.indicatorType === 'transceiver') {
    return failure.interface || '-'
  } else if (props.indicatorType === 'uplink') {
    return failure.expected_neighbor || '-'
  }
  return failure.device || '-'
}
</script>