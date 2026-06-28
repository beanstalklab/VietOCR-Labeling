<template>
  <div class="relative inline-block select-none" ref="container">
    <img
      v-if="currentPageUrl"
      :key="currentPageUrl"
      :src="currentPageUrl"
      alt="Document"
      class="block max-w-full h-auto"
      ref="imageRef"
      @load="onImageLoad"
      @error="onImageError"
      draggable="false"
    />

    <!-- Bounding box overlays -->
    <div
      v-for="box in boxes"
      :key="box.id"
      class="absolute border-2 cursor-pointer transition-all duration-100"
      :class="boxClass(box)"
      :style="getBoxStyle(box.box)"
      @click.stop="store.selectBox(box.id)"
    >
      <span
        class="absolute -top-5 left-0 text-[10px] px-1 py-0.5 rounded font-mono leading-none whitespace-nowrap"
        :class="labelClass(box)"
      >
        <span v-if="box.checked">✓</span> #{{ box.id }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useOCRStore } from '../store/ocrStore'
import type { BoundingBox } from '../store/ocrStore'
import { storeToRefs } from 'pinia'

const store = useOCRStore()
const { currentPageUrl, boxes, selectedBoxId } = storeToRefs(store)

const container = ref<HTMLElement | null>(null)
const imageRef = ref<HTMLImageElement | null>(null)
const scale = ref(1)

const onImageLoad = () => {
  updateScale()
}

const onImageError = () => {
  console.error('Image failed to load:', currentPageUrl.value)
  // Retry once after short delay
  setTimeout(() => {
    if (imageRef.value && currentPageUrl.value) {
      imageRef.value.src = currentPageUrl.value
    }
  }, 500)
}

// Recalculate scale when page changes
watch(currentPageUrl, () => {
  // Reset scale; will be recalculated when new image loads
  scale.value = 1
})

const updateScale = () => {
  const img = imageRef.value
  if (img && img.naturalWidth > 0 && img.clientWidth > 0) {
    scale.value = img.clientWidth / img.naturalWidth
  }
}

const getBoxStyle = (box: [number, number, number, number]) => {
  const [x, y, w, h] = box
  const s = scale.value
  return {
    left: `${x * s}px`,
    top: `${y * s}px`,
    width: `${w * s}px`,
    height: `${h * s}px`,
  }
}

const boxClass = (box: BoundingBox) => {
  const selected = box.id === selectedBoxId.value
  if (selected) return 'border-red-500 bg-red-500/15 shadow-lg z-10'
  if (!box.checked) return 'border-gray-400/50 bg-gray-400/5 opacity-40'
  if (box.text !== box.originalText) return 'border-amber-500/80 hover:bg-amber-500/10'
  return 'border-blue-500/70 hover:bg-blue-500/10 hover:border-blue-600'
}

const labelClass = (box: BoundingBox) => {
  const selected = box.id === selectedBoxId.value
  if (selected) return 'bg-red-500 text-white'
  if (!box.checked) return 'bg-gray-400 text-white'
  if (box.text !== box.originalText) return 'bg-amber-500 text-white'
  return 'bg-blue-500 text-white'
}

onMounted(() => {
  window.addEventListener('resize', updateScale)
  // If image already loaded from cache
  const img = imageRef.value
  if (img && img.complete && img.naturalWidth > 0) {
    updateScale()
  }
})
onBeforeUnmount(() => window.removeEventListener('resize', updateScale))
</script>
