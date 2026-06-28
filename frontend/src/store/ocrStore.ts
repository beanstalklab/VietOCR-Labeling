import { defineStore } from 'pinia'
import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// ---------------------------------------------------------------------------
// Serial OCR queue – sends only 1 OCR request at a time so the browser
// always has free connections available for serving images / thumbnails.
// An AbortController lets us cancel the in-flight request immediately
// when the user starts a new session.
// ---------------------------------------------------------------------------
type QueueItem = { pageIndex: number; resolve: () => void }
let _ocrQueue: QueueItem[] = []
let _ocrRunning = false
let _ocrAbort: AbortController | null = null

async function _processOcrQueue(store: ReturnType<typeof useOCRStore>) {
  if (_ocrRunning) return
  _ocrRunning = true

  while (_ocrQueue.length > 0) {
    const item = _ocrQueue.shift()!
    const { pageIndex, resolve } = item

    // Skip if already done or page removed while queued
    if (store.ocrResults[pageIndex] !== undefined || !store.pages[pageIndex]) {
      store._removeLoading(pageIndex)
      resolve()
      continue
    }

    const page = store.pages[pageIndex]
    _ocrAbort = new AbortController()
    try {
      const res = await api.post(
        '/ocr',
        { page_path: page.page_path },
        { signal: _ocrAbort.signal },
      )
      const rawBoxes: {
        id: number
        box: [number, number, number, number]
        text: string
      }[] = res.data.boxes

      const enriched: BoundingBox[] = rawBoxes.map((b) => ({
        ...b,
        originalText: b.text,
        checked: true,
      }))

      store.ocrResults[pageIndex] = enriched

      // Auto-navigate if user has nothing to view yet
      if (store.currentPageIndex === null) {
        store.currentPageIndex = pageIndex
        store.selectedBoxId = null
      }
    } catch (e) {
      if (axios.isCancel(e)) {
        // Cancelled by _clearOcrQueue — stop processing
        resolve()
        break
      }
      console.error('OCR failed for page', pageIndex, e)
    } finally {
      _ocrAbort = null
      store._removeLoading(pageIndex)
      resolve()
    }
  }

  _ocrRunning = false
}

function _clearOcrQueue() {
  // 1. Abort the in-flight HTTP request
  if (_ocrAbort) {
    _ocrAbort.abort()
    _ocrAbort = null
  }
  // 2. Drain pending queue
  _ocrQueue = []
  _ocrRunning = false
}

export interface BoundingBox {
  id: number
  box: [number, number, number, number] // x, y, w, h
  text: string
  originalText: string   // text from OCR (to detect edits)
  checked: boolean       // user tick for saving
}

export interface PageInfo {
  page_index: number      // global index across all files
  page_path: string
  page_url: string
  thumbnail_url: string
  source_filename: string // original filename (e.g. "contract.pdf")
}

export interface FileInfo {
  file_id: string
  filename: string
  page_start: number   // global index of first page
  page_count: number
}

export interface Stats {
  train_count: number
  val_count: number
  train_fix_count: number
  val_fix_count: number
}

export type Phase = 'upload' | 'working'

export const useOCRStore = defineStore('ocr', {
  state: () => ({
    // Uploaded files (supports multiple)
    files: [] as FileInfo[],
    pages: [] as PageInfo[],

    // OCR results cache: pageIndex → boxes (with originalText + checked)
    ocrResults: {} as Record<number, BoundingBox[]>,

    // Current page being viewed
    currentPageIndex: null as number | null,
    selectedBoxId: null as number | null,

    // Save
    annotationType: 'train' as 'train' | 'val',
    stats: { train_count: 0, val_count: 0, train_fix_count: 0, val_fix_count: 0 } as Stats,

    // UI
    phase: 'upload' as Phase,
    loading: false,
    /** Set of page indices currently being OCR'd (supports concurrent) */
    loadingPages: new Set<number>(),
    saveMessage: null as string | null,
  }),

  getters: {
    hasFile: (state) => state.pages.length > 0,

    /** All distinct filenames */
    filenames: (state): string[] => state.files.map((f) => f.filename),

    /** Indices of pages that have OCR results */
    processedPageIndices: (state): number[] =>
      Object.keys(state.ocrResults).map(Number).sort((a, b) => a - b),

    currentPage: (state): PageInfo | null =>
      state.currentPageIndex !== null
        ? state.pages[state.currentPageIndex] ?? null
        : null,

    currentPageUrl(): string | null {
      const page = this.currentPage
      return page ? page.page_url + `?p=${page.page_index}` : null
    },

    currentPagePath(): string | null {
      return this.currentPage?.page_path ?? null
    },

    /** Source filename of the current page */
    currentSourceFilename(): string | null {
      return this.currentPage?.source_filename ?? null
    },

    /** Boxes for current page */
    boxes(): BoundingBox[] {
      if (this.currentPageIndex === null) return []
      return this.ocrResults[this.currentPageIndex] ?? []
    },

    /** Only checked boxes */
    checkedBoxes(): BoundingBox[] {
      return this.boxes.filter((b: BoundingBox) => b.checked)
    },

    /** Is the current page fully ready to view? (has OCR results) */
    hasCurrentPage(): boolean {
      if (this.currentPageIndex === null) return false
      return this.ocrResults[this.currentPageIndex] !== undefined
    },

    /** Is a specific page currently loading? */
    isPageLoading(): (idx: number) => boolean {
      return (idx: number) => this.loadingPages.has(idx)
    },

    /** Is any page loading? */
    anyPageLoading: (state): boolean => state.loadingPages.size > 0,

    isPageProcessed() {
      return (idx: number) => this.ocrResults[idx] !== undefined
    },

    /** Group pages by source file for display */
    pagesByFile(): { file: FileInfo; pages: PageInfo[] }[] {
      return this.files.map((f) => ({
        file: f,
        pages: this.pages.slice(f.page_start, f.page_start + f.page_count),
      }))
    },
  },

  actions: {
    // =================================================================
    // Upload – supports multiple files, accumulates pages
    // =================================================================
    async uploadFiles(fileList: File[]) {
      if (fileList.length === 0) return

      this.loading = true
      const initialPageCount = this.pages.length

      for (const file of fileList) {
        try {
          const formData = new FormData()
          formData.append('file', file)
          const res = await api.post('/upload', formData)
          const data = res.data

          const pageStart = this.pages.length

          const fileInfo: FileInfo = {
            file_id: data.file_id,
            filename: data.filename,
            page_start: pageStart,
            page_count: data.pages.length,
          }
          this.files.push(fileInfo)

          // Re-index pages to global indices and append
          for (const p of data.pages) {
            const globalIndex = pageStart + p.page_index
            this.pages.push({
              page_index: globalIndex,
              page_path: p.page_path,
              page_url: p.page_url,
              thumbnail_url: p.thumbnail_url,
              source_filename: p.source_filename || data.filename,
            })
          }

          // Single-image file → auto process
          if (data.pages.length === 1 && fileList.length === 1) {
            this.queuePage(pageStart)
          }
        } catch (e: any) {
          console.error('Upload failed for', file.name, e)
          const detail = e?.response?.data?.detail
          if (detail) {
            alert(detail)
          } else {
            alert(`Upload thất bại: ${file.name}`)
          }
        }
      }

      // Only switch to working phase if new pages were actually added
      if (this.pages.length > initialPageCount) {
        this.phase = 'working'
      }

      this.loading = false
    },

    /** Convenience: upload a single file */
    async uploadFile(file: File) {
      await this.uploadFiles([file])
    },

    /** Add more files to existing session */
    async addMoreFiles(fileList: File[]) {
      await this.uploadFiles(fileList)
    },

    // =================================================================
    // Helpers: reactive Set mutation (Pinia needs reassignment)
    // =================================================================
    _addLoading(pageIndex: number) {
      const s = new Set(this.loadingPages)
      s.add(pageIndex)
      this.loadingPages = s
    },

    _removeLoading(pageIndex: number) {
      const s = new Set(this.loadingPages)
      s.delete(pageIndex)
      this.loadingPages = s
    },

    // =================================================================
    // Queue a page for OCR processing (serial queue, 1 at a time)
    // =================================================================
    queuePage(pageIndex: number) {
      const page = this.pages[pageIndex]
      if (!page) return

      // Already processed or queued → skip
      if (this.ocrResults[pageIndex] !== undefined) return
      if (this.loadingPages.has(pageIndex)) return

      this._addLoading(pageIndex)

      // Push into serial queue — resolved when this page's OCR finishes
      new Promise<void>((resolve) => {
        _ocrQueue.push({ pageIndex, resolve })
        _processOcrQueue(this)
      })
    },

    // =================================================================
    // Click handler: navigate if ready, queue if not
    // =================================================================
    handlePageClick(pageIndex: number) {
      // Already processed → navigate instantly
      if (this.ocrResults[pageIndex] !== undefined) {
        this.goToPage(pageIndex)
        return
      }

      // Not yet queued → queue it in background
      if (!this.loadingPages.has(pageIndex)) {
        this.queuePage(pageIndex)
      }
      // If loading → do nothing (user can see spinner on thumbnail)
    },

    /** Remove OCR results for a page */
    removePage(pageIndex: number) {
      delete this.ocrResults[pageIndex]
      if (this.currentPageIndex === pageIndex) {
        const remaining = this.processedPageIndices
        this.currentPageIndex = remaining.length > 0 ? remaining[0] : null
        this.selectedBoxId = null
      }
    },

    /** Remove an entire file and all its pages from the session */
    removeFile(fileIdx: number) {
      const fi = this.files[fileIdx]
      if (!fi) return

      const removeStart = fi.page_start
      const removeCount = fi.page_count

      // 1. Remove OCR results for pages of this file
      for (let p = removeStart; p < removeStart + removeCount; p++) {
        delete this.ocrResults[p]
      }

      // 2. Remove file entry & page entries
      this.files.splice(fileIdx, 1)
      this.pages.splice(removeStart, removeCount)

      // 3. Re-index remaining pages
      for (let i = removeStart; i < this.pages.length; i++) {
        this.pages[i].page_index = i
      }

      // 4. Re-index file entries (shift page_start)
      for (let i = fileIdx; i < this.files.length; i++) {
        this.files[i].page_start -= removeCount
      }

      // 5. Re-key OCR results (shift indices)
      const newResults: Record<number, BoundingBox[]> = {}
      for (const [key, val] of Object.entries(this.ocrResults)) {
        const oldIdx = Number(key)
        if (oldIdx < removeStart) {
          newResults[oldIdx] = val
        } else if (oldIdx >= removeStart + removeCount) {
          newResults[oldIdx - removeCount] = val
        }
      }
      this.ocrResults = newResults

      // 6. Re-key loading pages
      const newLoading = new Set<number>()
      for (const idx of this.loadingPages) {
        if (idx < removeStart) {
          newLoading.add(idx)
        } else if (idx >= removeStart + removeCount) {
          newLoading.add(idx - removeCount)
        }
      }
      this.loadingPages = newLoading

      // 7. Fix currentPageIndex
      if (this.currentPageIndex !== null) {
        if (
          this.currentPageIndex >= removeStart &&
          this.currentPageIndex < removeStart + removeCount
        ) {
          // Was viewing a page in the removed file
          const remaining = Object.keys(this.ocrResults)
            .map(Number)
            .sort((a, b) => a - b)
          this.currentPageIndex =
            remaining.length > 0 ? remaining[0] : null
          this.selectedBoxId = null
        } else if (this.currentPageIndex >= removeStart + removeCount) {
          this.currentPageIndex -= removeCount
        }
      }

      // 8. If no files left → back to upload phase
      if (this.files.length === 0) {
        this.phase = 'upload'
      }
    },

    // =================================================================
    // Page navigation (instant, only to processed pages)
    // =================================================================
    goToPage(pageIndex: number) {
      if (this.ocrResults[pageIndex] === undefined) return
      this.currentPageIndex = pageIndex
      this.selectedBoxId = null
      this.saveMessage = null
    },

    goToNextPage() {
      const indices = this.processedPageIndices
      const cur = indices.indexOf(this.currentPageIndex!)
      if (cur >= 0 && cur < indices.length - 1) {
        this.goToPage(indices[cur + 1])
      }
    },

    goToPrevPage() {
      const indices = this.processedPageIndices
      const cur = indices.indexOf(this.currentPageIndex!)
      if (cur > 0) {
        this.goToPage(indices[cur - 1])
      }
    },

    // =================================================================
    // Box interaction
    // =================================================================
    selectBox(id: number) {
      this.selectedBoxId = id
    },

    updateBoxText(id: number, text: string) {
      if (this.currentPageIndex === null) return
      const boxes = this.ocrResults[this.currentPageIndex]
      if (!boxes) return
      const box = boxes.find((b) => b.id === id)
      if (box) box.text = text
    },

    deleteBox(id: number) {
      if (this.currentPageIndex === null) return
      this.ocrResults[this.currentPageIndex] =
        (this.ocrResults[this.currentPageIndex] ?? []).filter(
          (b) => b.id !== id,
        )
      if (this.selectedBoxId === id) this.selectedBoxId = null
    },

    // --- Checkbox ---
    toggleBoxChecked(id: number) {
      if (this.currentPageIndex === null) return
      const box = (this.ocrResults[this.currentPageIndex] ?? []).find(
        (b) => b.id === id,
      )
      if (box) box.checked = !box.checked
    },

    checkAll() {
      for (const b of this.boxes) b.checked = true
    },

    uncheckAll() {
      for (const b of this.boxes) b.checked = false
    },

    /** Check only boxes whose text was edited */
    checkEdited() {
      for (const b of this.boxes) {
        b.checked = b.text !== b.originalText
      }
    },

    // =================================================================
    // Save (only checked boxes of current page)
    // – sends source_filename so backend uses {stem}_{yymmdd}_{ith}
    // =================================================================
    /**
     * @param saveMode - 'all' | 'edited' | null
     *   'edited' → only write to fix/ folder
     *   anything else → write to all/ + auto-filter fix/
     */
    async save(saveMode: 'all' | 'edited' | null = null) {
      const toSave = this.checkedBoxes
      if (this.currentPageIndex === null || toSave.length === 0) {
        alert('Không có box nào được chọn để lưu.')
        return
      }
      this.loading = true
      this.saveMessage = null
      try {
        const res = await api.post('/save', {
          page_path: this.currentPagePath,
          boxes: toSave.map((b) => ({
            id: b.id,
            box: b.box,
            text: b.text,
            original_text: b.originalText,
          })),
          annotation_type: this.annotationType,
          source_filename: this.currentSourceFilename,
          save_mode: saveMode === 'edited' ? 'fix_only' : 'dual',
        })
        const data = res.data
        const fixMsg = data.fix_count > 0 ? ` (${data.fix_count} fix)` : ''
        this.saveMessage =
          `Đã lưu ${data.saved_count} mẫu${fixMsg} → ${this.annotationType}`
        await this.fetchStats()
      } catch (e) {
        console.error('Save failed:', e)
        alert('Lưu thất bại.')
      } finally {
        this.loading = false
      }
    },

    async saveAndNext(saveMode: 'all' | 'edited' | null = null) {
      await this.save(saveMode)
      this.goToNextPage()
    },

    // =================================================================
    // Stats
    // =================================================================
    async fetchStats(retries = 3) {
      for (let i = 0; i < retries; i++) {
        try {
          const res = await api.get('/stats')
          this.stats = res.data
          return
        } catch {
          if (i < retries - 1) await new Promise((r) => setTimeout(r, 2000))
        }
      }
    },

    // =================================================================
    // Reset
    // =================================================================
    resetState() {
      _clearOcrQueue()
      this.files = []
      this.pages = []
      this.ocrResults = {}
      this.currentPageIndex = null
      this.selectedBoxId = null
      this.saveMessage = null
      this.phase = 'upload'
      this.loadingPages = new Set()
    },

    async newSession() {
      // 1. Reset frontend immediately (cancels in-flight OCR request)
      this.resetState()
      // 2. Ask backend to clean temp files (fire-and-forget, don't block UI)
      api.post('/cleanup').catch(() => { })
    },
  },
})
