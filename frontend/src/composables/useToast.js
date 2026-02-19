import { reactive } from 'vue'

const messageModal = reactive({
  show: false,
  type: 'info',
  title: '',
  message: '',
})

const confirmModal = reactive({
  show: false,
  title: '',
  message: '',
  resolve: null,
})

function showMessage(message, type = 'info', title = '') {
  messageModal.show = true
  messageModal.type = type
  messageModal.title = title || (type === 'success' ? '成功' : type === 'error' ? '錯誤' : '提示')
  messageModal.message = message
}

function closeMessage() {
  messageModal.show = false
}

function showConfirm(message, title = '確認') {
  return new Promise((resolve) => {
    confirmModal.show = true
    confirmModal.title = title
    confirmModal.message = message
    confirmModal.resolve = resolve
  })
}

function handleConfirm() {
  if (confirmModal.resolve) {
    confirmModal.resolve(true)
  }
  confirmModal.show = false
}

function cancelConfirm() {
  if (confirmModal.resolve) {
    confirmModal.resolve(false)
  }
  confirmModal.show = false
}

export function useToast() {
  return {
    messageModal,
    confirmModal,
    showMessage,
    closeMessage,
    showConfirm,
    handleConfirm,
    cancelConfirm,
  }
}
