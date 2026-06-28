<template>
  <div class="bg-white border-b border-gray-200 shrink-0">

    <!-- Row 1: File tabs -->
    <div v-if="files.length > 0" class="flex items-center gap-2 px-4 pt-2 pb-1.5 border-b border-gray-100">
      <div class="flex items-center gap-1.5 flex-1 overflow-x-auto" ref="fileTabStrip" @wheel.prevent="onFileTabWheel">
        <div
          v-for="(fi, idx) in files"
          :key="fi.file_id"
          class="inline-flex items-center gap-1 rounded-lg text-xs font-medium transition-all duration-150 shrink-0 border"
          :class="focusedFileIdx === idx
            ? 'bg-blue-600 border-blue-600 text-white shadow-sm'
            : 'bg-white border-gray-200 text-gray-500 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-600'"
        >
          <button
            @click="selectFile(idx)"
            class="inline-flex items-center gap-1.5 pl-3 pr-1 py-1.5 cursor-pointer"
          >
            <svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path v-if="fi.filename.endsWith('.pdf')" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"/>
              <path v-else stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/>
            </svg>
            <span class="truncate max-w-[180px]" :title="fi.filename">{{ fi.filename }}</span>
            <span class="text-[10px] opacity-70">({{ fi.page_count }}tr.)</span>
          </button>
          <button
            @click.stop="removeFile(idx)"
            class="w-5 h-5 mr-1 rounded flex items-center justify-center transition-colors shrink-0 cursor-pointer"
            :class="focusedFileIdx === idx
              ? 'hover:bg-blue-500 text-blue-200 hover:text-white'
              : 'hover:bg-red-100 text-gray-300 hover:text-red-500'"
            title="Xóa file khỏi phiên"
          >
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>
      </div>

      <div class="flex items-center gap-2 shrink-0 text-xs text-gray-500">
        <span>{{ processedCount }}/{{ pages.length }} xử lý</span>
        <span v-if="loadingCount > 0" class="text-blue-600 animate-pulse font-medium">
          {{ loadingCount }} đang chạy
        </span>
      </div>
    </div>

    <!-- Row 2: Thumbnails + controls -->
    <div class="flex items-center gap-2 px-4 py-1.5">

      <!-- Nav -->
      <button
        @click="store.goToPrevPage()"
        :disabled="!canGoPrev"
        class="text-xs font-medium px-2 py-1 rounded border border-gray-300 disabled:opacity-30 hover:bg-gray-50 transition-colors shrink-0"
        title="Trang trước (←)"
      >←</button>

      <span class="text-xs text-gray-500 shrink-0 font-medium whitespace-nowrap min-w-[60px] text-center">
        <template v-if="currentPageIndex !== null">
          {{ currentPageIndex + 1 }} / {{ pages.length }}
        </template>
        <template v-else>—</template>
      </span>

      <button
        @click="store.goToNextPage()"
        :disabled="!canGoNext"
        class="text-xs font-medium px-2 py-1 rounded border border-gray-300 disabled:opacity-30 hover:bg-gray-50 transition-colors shrink-0"
        title="Trang sau (→)"
      >→</button>

      <!-- Thumbnail strip (mouse wheel → horizontal scroll) -->
      <div class="flex-1 overflow-x-auto" ref="thumbStrip" @wheel.prevent="onThumbWheel">
        <div class="flex items-end gap-2 py-0.5">
          <template v-for="(group, gIdx) in pagesByFile" :key="group.file.file_id">
            <!-- File group container -->
            <div
              :ref="(el: any) => setFileRef(gIdx, el)"
              class="shrink-0 rounded-lg p-1 transition-all duration-150 border"
              :class="focusedFileIdx === gIdx
                ? 'border-blue-400 bg-blue-50/50'
                : 'border-gray-200 bg-gray-50/20'"
            >
              <!-- Group header -->
              <div
                class="text-[9px] font-bold px-1 mb-0.5 truncate max-w-[240px] leading-tight"
                :class="focusedFileIdx === gIdx ? 'text-blue-600' : 'text-gray-400'"
                :title="group.file.filename"
              >
                {{ truncateName(group.file.filename, 24) }}
              </div>

              <!-- Thumbnails row -->
              <div class="flex items-center gap-0.5">
                <div
                  v-for="page in group.pages"
                  :key="page.page_index"
                  class="shrink-0 cursor-pointer rounded overflow-hidden border-2 transition-all duration-150 relative group"
                  :class="thumbnailClass(page.page_index)"
                  @click="handleClick(page.page_index, gIdx)"
                >
                  <!-- Loading spinner -->
                  <div
                    v-if="store.isPageLoading(page.page_index)"
                    class="absolute inset-0 bg-white/70 z-10 flex items-center justify-center"
                  >
                    <div class="w-4 h-4 border-2 border-blue-200 border-t-blue-600 rounded-full animate-spin"></div>
                  </div>

                  <!-- Processed dot -->
                  <div
                    v-if="isProcessed(page.page_index) && !store.isPageLoading(page.page_index)"
                    class="absolute top-0.5 right-0.5 z-10 w-2.5 h-2.5 rounded-full bg-green-500 border border-white"
                  ></div>

                  <!-- Remove on hover -->
                  <button
                    v-if="isProcessed(page.page_index) && currentPageIndex !== page.page_index"
                    @click.stop="store.removePage(page.page_index)"
                    class="absolute top-0 left-0 z-10 w-4 h-4 rounded-full bg-red-500 text-white text-[7px] leading-none items-center justify-center hidden group-hover:flex border border-white"
                  >✕</button>

                  <div class="w-11 h-[56px] bg-gray-100">
                    <img
                      :src="page.thumbnail_url"
                      :alt="`${page.page_index + 1}`"
                      class="w-full h-full object-cover"
                      loading="lazy"
                    />
                  </div>
                  <div class="absolute bottom-0 inset-x-0 bg-black/50 text-white text-[8px] text-center py-px font-medium">
                    {{ page.page_index + 1 }}
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- Process all button -->
      <button
        v-if="unprocessedCount > 0"
        @click="processAllUnprocessed"
        class="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-1.5 px-3 rounded-lg text-xs transition-colors shrink-0 whitespace-nowrap shadow-sm"
      >
        Xử lý {{ unprocessedCount }} trang
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useOCRStore } from '../store/ocrStore'
import { storeToRefs } from 'pinia'

const store = useOCRStore()
const {
  pages, files, currentPageIndex, processedPageIndices, loadingPages, pagesByFile,
} = storeToRefs(store)

const thumbStrip = ref<HTMLElement | null>(null)
const fileTabStrip = ref<HTMLElement | null>(null)

/** Convert vertical mouse wheel to horizontal scroll */
const onThumbWheel = (e: WheelEvent) => {
  if (!thumbStrip.value) return
  thumbStrip.value.scrollLeft += e.deltaY || e.deltaX
}

const onFileTabWheel = (e: WheelEvent) => {
  if (!fileTabStrip.value) return
  fileTabStrip.value.scrollLeft += e.deltaY || e.deltaX
}
const fileRefs = ref<Record<number, HTMLElement | null>>({})
const focusedFileIdx = ref(0)

const setFileRef = (idx: number, el: HTMLElement | null) => {
  fileRefs.value[idx] = el
}

const isProcessed = (idx: number) => store.isPageProcessed(idx)
const processedCount = computed(() => processedPageIndices.value.length)
const unprocessedCount = computed(() =>
  pages.value.length - processedCount.value - loadingPages.value.size,
)
const loadingCount = computed(() => loadingPages.value.size)

const canGoPrev = computed(() => {
  const indices = processedPageIndices.value
  return indices.indexOf(currentPageIndex.value!) > 0
})

const canGoNext = computed(() => {
  const indices = processedPageIndices.value
  const cur = indices.indexOf(currentPageIndex.value!)
  return cur >= 0 && cur < indices.length - 1
})

const fileIndexForPage = (pageIndex: number): number => {
  for (let i = 0; i < files.value.length; i++) {
    const f = files.value[i]
    if (pageIndex >= f.page_start && pageIndex < f.page_start + f.page_count) {
      return i
    }
  }
  return 0
}

const thumbnailClass = (pageIndex: number) => {
  if (pageIndex === currentPageIndex.value) {
    return 'border-blue-500 shadow-md ring-2 ring-blue-200'
  }
  if (store.isPageLoading(pageIndex)) {
    return 'border-yellow-400 ring-1 ring-yellow-200'
  }
  if (isProcessed(pageIndex)) {
    return 'border-green-300 hover:border-green-400'
  }
  return 'border-gray-200 hover:border-blue-300'
}

/** Remove a file from the session */
const removeFile = (idx: number) => {
  const fi = files.value[idx]
  if (!fi) return
  const name = fi.filename
  if (!confirm(`Xóa "${name}" khỏi phiên làm việc?`)) return
  store.removeFile(idx)
  // Adjust focusedFileIdx
  if (files.value.length === 0) {
    focusedFileIdx.value = 0
  } else if (focusedFileIdx.value >= files.value.length) {
    focusedFileIdx.value = files.value.length - 1
  }
}

/** Click file tab → highlight + scroll + navigate to first processed page */
const selectFile = (idx: number) => {
  focusedFileIdx.value = idx
  scrollToFileGroup(idx)

  const fi = files.value[idx]
  if (!fi) return
  for (let p = fi.page_start; p < fi.page_start + fi.page_count; p++) {
    if (store.isPageProcessed(p)) {
      store.goToPage(p)
      return
    }
  }
}

/** Click page thumbnail → also focus its parent file */
const handleClick = (pageIndex: number, groupIdx: number) => {
  focusedFileIdx.value = groupIdx
  store.handlePageClick(pageIndex)
}

const processAllUnprocessed = () => {
  const all = pages.value
    .map((p) => p.page_index)
    .filter((i) => !store.isPageProcessed(i) && !store.isPageLoading(i))
  for (const idx of all) {
    store.queuePage(idx)
  }
}

const scrollToFileGroup = (fileIdx: number) => {
  const el = fileRefs.value[fileIdx]
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'start' })
  }
}

/** Sync focus when prev/next navigation changes currentPageIndex */
watch(currentPageIndex, (idx) => {
  if (idx === null) return
  focusedFileIdx.value = fileIndexForPage(idx)
})

const truncateName = (name: string, max: number): string => {
  if (name.length <= max) return name
  const ext = name.includes('.') ? name.slice(name.lastIndexOf('.')) : ''
  const stem = name.slice(0, name.length - ext.length)
  const keep = max - ext.length - 2
  return stem.slice(0, Math.max(keep, 4)) + '..' + ext
}
</script>
