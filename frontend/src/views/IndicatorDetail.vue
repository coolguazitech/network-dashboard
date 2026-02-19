<template>
  <div class="px-3 py-3">
    <!-- 標題和返回按鈕 -->
    <div class="flex items-center gap-3 mb-4">
      <button @click="$router.back()" class="px-3 py-1.5 bg-slate-700/60 hover:bg-slate-600/60 text-slate-300 hover:text-white text-sm rounded-lg border border-slate-600/50 transition">
        ← 返回
      </button>
      <h2 class="text-xl font-bold text-white">{{ metadata.title }}</h2>
    </div>

    <!-- 圖表卡片 -->
    <div class="card mb-4">
      <h3 class="card-title">Pass Rate 趨勢圖</h3>
      <div class="chart-container">
        <v-chart :option="chartOption" autoresize />
      </div>
    </div>

    <!-- 原始資料表格 -->
    <div class="card">
      <div class="flex justify-between items-center mb-4">
        <h3 class="card-title mb-0">原始資料</h3>
        <button @click="fetchRawData" class="px-3 py-1.5 bg-slate-700/60 hover:bg-slate-600/60 text-slate-300 hover:text-white text-sm rounded-lg border border-slate-600/50 transition">
          刷新
        </button>
      </div>

      <div class="overflow-x-auto max-h-[500px] overflow-y-auto">
        <table class="data-table">
          <thead class="sticky top-0">
            <tr>
              <th v-for="col in tableColumns" :key="col.key">
                {{ col.title }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in tableRows" :key="index" class="row-stagger" :style="{ animationDelay: index * 30 + 'ms' }">
              <td v-for="col in tableColumns" :key="col.key">
                <template v-if="col.data_type === 'boolean'">
                  <span :class="row[col.key] ? 'badge-success' : 'badge-danger'" class="badge">
                    {{ row[col.key] ? '✓' : '✗' }}
                  </span>
                </template>
                <template v-else-if="col.data_type === 'datetime'">
                  {{ formatTime(row[col.key]) }}
                </template>
                <template v-else-if="col.data_type === 'float'">
                  {{ formatNumber(row[col.key]) }}
                </template>
                <template v-else>
                  {{ row[col.key] }}
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 無資料 -->
      <div v-if="tableRows.length === 0 && !loading" class="text-center py-8 text-slate-500">
        暫無原始資料
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { useRoute } from 'vue-router'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import VChart from 'vue-echarts'
import api from '@/utils/api'
import dayjs from 'dayjs'

use([CanvasRenderer, LineChart, GridComponent, TooltipComponent, LegendComponent])

const route = useRoute()
const indicatorName = route.params.name
const maintenanceId = inject('maintenanceId')

const loading = ref(true)
const metadata = ref({ title: '', description: '' })
const timeSeries = ref([])
const tableColumns = ref([])
const tableRows = ref([])

const chartOption = computed(() => {
  if (timeSeries.value.length === 0) {
    return {}
  }

  const seriesNames = metadata.value.series_names || ['tx', 'rx']
  const colors = metadata.value.display_config?.line_colors || ['#22d3ee', '#a78bfa']

  return {
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(15, 23, 42, 0.9)',
      borderColor: 'rgba(51, 65, 85, 0.5)',
      textStyle: { color: '#e2e8f0', fontSize: 12 },
    },
    legend: {
      data: seriesNames.map(s => s.toUpperCase()),
      textStyle: { color: '#94a3b8' },
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'time',
      axisLabel: {
        formatter: '{HH}:{mm}',
        color: '#64748b',
      },
      axisLine: { lineStyle: { color: '#334155' } },
      splitLine: { lineStyle: { color: '#1e293b' } },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: {
        formatter: '{value}%',
        color: '#64748b',
      },
      axisLine: { lineStyle: { color: '#334155' } },
      splitLine: { lineStyle: { color: '#1e293b' } },
    },
    series: seriesNames.map((name, index) => ({
      name: name.toUpperCase(),
      type: 'line',
      smooth: true,
      color: colors[index],
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: colors[index] + '30' },
            { offset: 1, color: colors[index] + '05' },
          ],
        },
      },
      data: timeSeries.value.map(point => [
        new Date(point.timestamp),
        point.values[name] || 0,
      ]),
    })),
  }
})

const fetchMetadata = async () => {
  try {
    const response = await api.get(`/indicators/${indicatorName}`)
    metadata.value = response.data
  } catch (error) {
    console.error('Failed to fetch metadata:', error)
  }
}

const fetchTimeSeries = async () => {
  try {
    const mid = maintenanceId?.value || maintenanceId
    const response = await api.get(`/indicators/${mid}/${indicatorName}/timeseries`)
    timeSeries.value = response.data.data
    metadata.value.series_names = response.data.series_names
    metadata.value.display_config = response.data.display_config
  } catch (error) {
    console.error('Failed to fetch timeseries:', error)
  }
}

const fetchRawData = async () => {
  try {
    const mid = maintenanceId?.value || maintenanceId
    const response = await api.get(`/indicators/${mid}/${indicatorName}/rawdata`)
    tableColumns.value = response.data.columns
    tableRows.value = response.data.rows
  } catch (error) {
    console.error('Failed to fetch raw data:', error)
  } finally {
    loading.value = false
  }
}

const formatTime = (time) => {
  if (!time) return '—'
  return dayjs(time).format('MM-DD HH:mm:ss')
}

const formatNumber = (num) => {
  if (num === null || num === undefined) return '—'
  return num.toFixed(2)
}

onMounted(async () => {
  await fetchMetadata()
  await Promise.all([fetchTimeSeries(), fetchRawData()])
})
</script>
