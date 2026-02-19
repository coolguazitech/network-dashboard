<template>
  <!-- 通用訊息 Modal -->
  <Transition name="modal">
  <div v-if="messageModal.show" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[60]" @click.self="closeMessage">
    <div class="modal-content bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-96">
      <div class="flex items-start gap-3">
        <span v-if="messageModal.type === 'success'" class="text-2xl text-green-400">✓</span>
        <span v-else-if="messageModal.type === 'error'" class="text-2xl text-red-400">✕</span>
        <span v-else class="text-2xl text-blue-400">ℹ</span>
        <div class="flex-1">
          <h3 class="text-lg font-semibold text-white mb-2">{{ messageModal.title || '提示' }}</h3>
          <p class="text-slate-300 whitespace-pre-line">{{ messageModal.message }}</p>
        </div>
      </div>
      <div class="flex justify-end mt-6">
        <button @click="closeMessage" class="px-4 py-2 bg-slate-600 text-white rounded hover:bg-slate-500">
          確定
        </button>
      </div>
    </div>
  </div>
  </Transition>

  <!-- 通用確認 Modal -->
  <Transition name="modal">
  <div v-if="confirmModal.show" class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[60]">
    <div class="modal-content bg-slate-800/95 backdrop-blur-xl border border-slate-600/40 rounded-2xl shadow-2xl shadow-black/30 p-6 w-96">
      <div class="flex items-start gap-3">
        <span class="text-2xl text-amber-400">⚠</span>
        <div class="flex-1">
          <h3 class="text-lg font-semibold text-white mb-2">{{ confirmModal.title || '確認' }}</h3>
          <p class="text-slate-300 whitespace-pre-line">{{ confirmModal.message }}</p>
        </div>
      </div>
      <div class="flex justify-end gap-2 mt-6">
        <button @click="cancelConfirm" class="px-4 py-2 text-slate-400 hover:bg-slate-700 rounded">
          取消
        </button>
        <button @click="handleConfirm" class="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-500">
          確定
        </button>
      </div>
    </div>
  </div>
  </Transition>
</template>

<script setup>
import { useToast } from '@/composables/useToast'

const { messageModal, confirmModal, closeMessage, handleConfirm, cancelConfirm } = useToast()
</script>
