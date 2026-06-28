<script setup lang="ts">
import { onMounted, ref } from 'vue'
import ImageUploader from './components/ImageUploader.vue'
import PageSelector from './components/PageSelector.vue'
import CanvasOverlay from './components/CanvasOverlay.vue'
import LabelEditor from './components/LabelEditor.vue'
import { useOCRStore } from './store/ocrStore'
import { storeToRefs } from 'pinia'

const store = useOCRStore()
const { phase, hasCurrentPage, anyPageLoading } = storeToRefs(store)

const addFileInput = ref<HTMLInputElement | null>(null)

const triggerAddFile = () => {
  addFileInput.value?.click()
}

const handleAddFile = (e: Event) => {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (files && files.length > 0) {
    store.addMoreFiles(Array.from(files))
  }
  input.value = ''
}

onMounted(() => {
  store.fetchStats()
})
</script>

<template>
  <div class="flex flex-col h-screen w-screen bg-gray-50 overflow-hidden">
    <!-- Hidden file input for "Add more files" — uses sr-only instead of hidden -->
    <input
      type="file"
      ref="addFileInput"
      class="absolute opacity-0 w-0 h-0 overflow-hidden pointer-events-none"
      accept="image/*,application/pdf"
      multiple
      @change="handleAddFile"
    />

    <!-- Top Bar -->
    <header class="h-12 bg-white border-b border-gray-200 flex items-center px-4 shadow-sm shrink-0 z-30">
      <div class="flex items-center gap-2.5 flex-1 min-w-0">
        <div class="w-7 h-7 bg-blue-600 rounded-lg flex items-center justify-center shrink-0">
          <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
        </div>
        <h1 class="text-base font-semibold text-gray-800 shrink-0">VietOCR Labeling</h1>
      </div>

      <div v-if="phase === 'working'" class="flex items-center gap-1.5 shrink-0">
        <button
          @click="triggerAddFile"
          class="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700 bg-blue-50 hover:bg-blue-100 px-3 py-1.5 rounded-lg transition-colors"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/>
          </svg>
          Thêm file
        </button>
        <button
          @click="store.newSession()"
          class="text-xs text-gray-500 hover:text-red-600 hover:bg-red-50 px-3 py-1.5 rounded-lg transition-colors"
        >
          Phiên mới
        </button>
      </div>
    </header>

    <!-- Page Selector Bar -->
    <PageSelector v-if="phase === 'working'" @add-files="triggerAddFile" />

    <!-- Main content -->
    <div class="flex-1 flex overflow-hidden">
      <main class="flex-1 overflow-hidden relative">

        <!-- Upload -->
        <div v-if="phase === 'upload'" class="w-full h-full flex items-center justify-center p-8">
          <ImageUploader />
        </div>

        <!-- Canvas with bounding boxes -->
        <div v-else-if="hasCurrentPage" class="w-full h-full overflow-auto">
          <div class="min-h-full flex items-start justify-center p-6">
            <CanvasOverlay />
          </div>
        </div>

        <!-- No page selected yet -->
        <div v-else class="w-full h-full flex items-center justify-center">
          <div class="text-center">
            <template v-if="anyPageLoading">
              <div class="inline-block w-8 h-8 border-3 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-3"></div>
              <p class="text-gray-500 font-medium">Đang xử lý OCR...</p>
              <p class="text-gray-400 text-sm mt-1">Trang nào xong sẽ có chấm xanh, click vào để xem</p>
            </template>
            <template v-else>
              <p class="text-gray-400 text-lg mb-2">Click vào một trang để bắt đầu</p>
              <p class="text-gray-300 text-sm">Click nhiều trang - chúng xử lý đồng thời</p>
            </template>
          </div>
        </div>
      </main>

      <!-- Sidebar -->
      <aside
        v-if="phase === 'working' && hasCurrentPage"
        class="w-[380px] shrink-0 border-l border-gray-200 z-20"
      >
        <LabelEditor />
      </aside>
    </div>
  </div>
</template>
