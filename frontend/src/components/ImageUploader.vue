<template>
  <div
    class="w-full max-w-lg"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="handleDrop"
  >
    <div
      :class="[
        'p-10 border-2 border-dashed rounded-2xl text-center cursor-pointer transition-all duration-200',
        isDragging
          ? 'border-blue-500 bg-blue-50 scale-[1.02]'
          : 'border-gray-300 bg-white hover:border-blue-400 hover:bg-gray-50'
      ]"
      @click="triggerInput"
    >
      <input
        type="file"
        ref="fileInput"
        class="hidden"
        accept="image/*,application/pdf"
        multiple
        @change="handleFileChange"
      />

      <div v-if="store.loading" class="py-4">
        <div class="inline-block w-8 h-8 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-3"></div>
        <p class="text-gray-500 font-medium">Đang tải lên...</p>
      </div>

      <div v-else class="py-4">
        <div class="w-16 h-16 mx-auto mb-4 bg-blue-100 rounded-2xl flex items-center justify-center">
          <svg class="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/>
          </svg>
        </div>
        <p class="text-lg font-semibold text-gray-700 mb-1">Kéo thả file vào đây</p>
        <p class="text-sm text-gray-500 mb-3">hoặc nhấn để chọn file (chọn được nhiều file)</p>
        <div class="flex justify-center gap-2">
          <span class="text-xs bg-gray-100 text-gray-600 px-2.5 py-1 rounded-full">PDF</span>
          <span class="text-xs bg-gray-100 text-gray-600 px-2.5 py-1 rounded-full">JPG</span>
          <span class="text-xs bg-gray-100 text-gray-600 px-2.5 py-1 rounded-full">PNG</span>
          <span class="text-xs bg-blue-100 text-blue-600 px-2.5 py-1 rounded-full font-medium">Nhiều file</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useOCRStore } from '../store/ocrStore'

const store = useOCRStore()
const fileInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)

const handleFileChange = (e: Event) => {
  const input = e.target as HTMLInputElement
  const files = input.files
  if (files && files.length > 0) {
    store.uploadFiles(Array.from(files))
  }
  // Reset so same files can be selected again
  input.value = ''
}

const handleDrop = (e: DragEvent) => {
  isDragging.value = false
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    store.uploadFiles(Array.from(files))
  }
}

const triggerInput = () => {
  fileInput.value?.click()
}
</script>
