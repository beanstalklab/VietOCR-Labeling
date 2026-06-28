<template>
  <div class="h-full flex flex-col bg-white overflow-hidden">

    <!-- Compact toolbar -->
    <div class="px-3 py-2 border-b border-gray-200 bg-gray-50 shrink-0 space-y-1.5">

      <!-- Row 1: file info + selection shortcuts -->
      <div class="flex items-center gap-1.5">
        <span
          v-if="currentSourceFilename"
          class="text-[11px] font-semibold text-gray-700 truncate max-w-[120px]"
          :title="currentSourceFilename"
        >{{ currentSourceFilename }}</span>
        <span class="text-[10px] text-gray-400">{{ checkedBoxes.length }}/{{ boxes.length }}</span>
        <span v-if="editedCount > 0" class="text-[10px] text-amber-600 font-medium">{{ editedCount }}✎</span>

        <span class="flex-1"></span>

        <button @click="doCheckAll()"
          class="text-[10px] px-1.5 py-px rounded border font-medium transition-colors leading-tight"
          :class="lastAction === 'all'
            ? 'bg-blue-600 text-white border-blue-600'
            : 'border-gray-300 text-gray-600 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-600'">
          Tất cả
        </button>
        <button @click="doUncheckAll()"
          class="text-[10px] px-1.5 py-px rounded border font-medium transition-colors leading-tight"
          :class="lastAction === 'none'
            ? 'bg-blue-600 text-white border-blue-600'
            : 'border-gray-300 text-gray-600 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-600'">
          Bỏ chọn
        </button>
        <button @click="doCheckEdited()"
          class="text-[10px] px-1.5 py-px rounded border font-medium transition-colors leading-tight"
          :class="lastAction === 'edited'
            ? 'bg-amber-500 text-white border-amber-500'
            : 'border-gray-300 text-gray-600 hover:bg-amber-50 hover:border-amber-300 hover:text-amber-600'">
          Đã sửa
        </button>
      </div>

      <!-- Row 2: train/val + save -->
      <div class="flex items-center gap-1.5">
        <div class="flex bg-gray-200 rounded p-0.5 text-[11px]">
          <button
            @click="store.annotationType = 'train'"
            :class="[
              'px-2 py-0.5 rounded font-medium transition-colors leading-tight',
              store.annotationType === 'train'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >Train {{ stats.train_count }}<span v-if="stats.train_fix_count" class="opacity-70">/{{ stats.train_fix_count }}fix</span></button>
          <button
            @click="store.annotationType = 'val'"
            :class="[
              'px-2 py-0.5 rounded font-medium transition-colors leading-tight',
              store.annotationType === 'val'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            ]"
          >Val {{ stats.val_count }}<span v-if="stats.val_fix_count" class="opacity-70">/{{ stats.val_fix_count }}fix</span></button>
        </div>

        <span class="flex-1"></span>

        <button
          @click="store.save(lastAction)"
          :disabled="store.loading || checkedBoxes.length === 0"
          class="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-1 px-3 rounded text-[11px] disabled:opacity-40 disabled:cursor-not-allowed transition-colors leading-tight"
        >
          <span v-if="store.loading">...</span>
          <span v-else>Lưu ({{ checkedBoxes.length }})</span>
        </button>
        <button
          @click="store.saveAndNext(lastAction)"
          :disabled="store.loading || checkedBoxes.length === 0"
          class="bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-1 px-3 rounded text-[11px] disabled:opacity-40 disabled:cursor-not-allowed transition-colors leading-tight"
        >Tiếp →</button>
      </div>

      <div v-if="saveMessage" class="text-[10px] text-emerald-600 font-medium bg-emerald-50 px-2 py-1 rounded leading-tight">
        {{ saveMessage }}
      </div>
    </div>

    <!-- Box list: each row = checkbox + id + auto-height textarea -->
    <div class="flex-1 overflow-y-auto" ref="listContainer">
      <div class="py-1">
        <div
          v-for="box in boxes"
          :key="box.id"
          :id="`box-item-${box.id}`"
          class="group flex items-start gap-1.5 px-2 py-[3px] transition-colors duration-75 border-l-2"
          :class="boxRowClass(box)"
        >
          <!-- Checkbox -->
          <input
            type="checkbox"
            :checked="box.checked"
            @change="store.toggleBoxChecked(box.id)"
            class="w-3.5 h-3.5 mt-[5px] rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer shrink-0"
          />

          <!-- ID label -->
          <span
            class="text-[11px] font-mono mt-[5px] shrink-0 cursor-pointer select-none font-semibold"
            :class="box.id === selectedBoxId ? 'text-red-600' : 'text-gray-500'"
            @click="store.selectBox(box.id)"
          >{{ box.id }}</span>

          <!-- Auto-height textarea wrapper (relative for edit badge) -->
          <div class="flex-1 min-w-0 relative">
            <textarea
              ref="textareaRefs"
              :data-box-id="box.id"
              :value="box.text"
              @input="onInput($event, box.id)"
              @focus="store.selectBox(box.id)"
              class="w-full px-1.5 py-0.5 border rounded text-[13px] text-gray-800 leading-[1.35] font-mono focus:outline-none focus:ring-1 focus:ring-red-300 focus:border-red-400 resize-none bg-white overflow-hidden"
              :class="box.text !== box.originalText ? 'border-amber-400' : 'border-gray-300'"
              rows="1"
            ></textarea>
            <!-- Edit indicator (absolute badge, no flow impact) -->
            <span
              v-if="box.text !== box.originalText"
              class="absolute -top-1.5 -right-1.5 text-[9px] text-amber-500 bg-white rounded-full leading-none px-[2px]"
            >✎</span>
          </div>

          <!-- Delete (hover) -->
          <button
            @click.stop="store.deleteBox(box.id)"
            class="mt-[5px] opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 transition-opacity shrink-0"
            title="Xóa"
          >
            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>
        </div>

        <div v-if="boxes.length === 0" class="text-center py-10 text-gray-400">
          <p class="text-xs">Không có vùng text nào</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUpdated } from 'vue'
import { useOCRStore } from '../store/ocrStore'
import type { BoundingBox } from '../store/ocrStore'
import { storeToRefs } from 'pinia'

const store = useOCRStore()
const {
  boxes, checkedBoxes, selectedBoxId, saveMessage,
  stats, currentSourceFilename,
} = storeToRefs(store)

const listContainer = ref<HTMLElement | null>(null)
const textareaRefs = ref<HTMLTextAreaElement[]>([])
const lastAction = ref<'all' | 'none' | 'edited' | null>(null)

const editedCount = computed(() =>
  boxes.value.filter((b: BoundingBox) => b.text !== b.originalText).length,
)

const doCheckAll = () => { store.checkAll(); lastAction.value = 'all' }
const doUncheckAll = () => { store.uncheckAll(); lastAction.value = 'none' }
const doCheckEdited = () => { store.checkEdited(); lastAction.value = 'edited' }

// --- Auto-resize textareas ---
const autoResize = (el: HTMLTextAreaElement) => {
  el.style.height = 'auto'
  el.style.height = el.scrollHeight + 'px'
}

const onInput = (e: Event, boxId: number) => {
  const ta = e.target as HTMLTextAreaElement
  store.updateBoxText(boxId, ta.value)
  autoResize(ta)
}

/** Resize all textareas after Vue updates the DOM (e.g. page change) */
const resizeAll = () => {
  if (!textareaRefs.value) return
  for (const ta of textareaRefs.value) {
    if (ta) autoResize(ta)
  }
}

onUpdated(() => {
  nextTick(resizeAll)
})

// --- Box row styling ---
const boxRowClass = (box: BoundingBox) => {
  const selected = box.id === selectedBoxId.value
  const checked = box.checked
  if (selected) return 'bg-red-50/80 border-l-red-500'
  if (!checked) return 'opacity-40 border-l-transparent'
  return 'border-l-transparent hover:bg-gray-50/60'
}

// --- Scroll to selected box ---
watch(selectedBoxId, async (newId) => {
  if (newId !== null) {
    await nextTick()
    const el = document.getElementById(`box-item-${newId}`)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }
})
</script>
