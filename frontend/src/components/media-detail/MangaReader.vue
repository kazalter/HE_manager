<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Columns2,
  GalleryHorizontal,
  Keyboard,
  Loader2,
  RotateCcw,
  ScrollText,
  Square,
  ZoomIn,
  ZoomOut,
  X,
} from 'lucide-vue-next'
import { desktopBridge, desktopState, setDesktopPreferences, type ImageEnhancement } from '../../desktop'
import { UiToast } from '../ui'
import { useDesktopImageEnhancement } from '../../composables/useDesktopImageEnhancement'
import { authIdentity } from '../../auth'
import { API_BASE_URL, authUrl } from '../../config'
import type { Media } from '../../types'
import { useImageViewerZoom } from '../../composables/useImageViewerZoom'
import { useReaderImageBuffer } from '../../composables/useReaderImageBuffer'
import { readerImageWindow } from '../../utils/readerImageWindow'
import { useWebtoonZoom } from '../../composables/useWebtoonZoom'
import { useCompactViewport } from '../../composables/useCompactViewport'

export type MangaReadMode = 'single' | 'double' | 'webtoon'

const props = defineProps<{
  media: Media
  imagePages?: Media[]
  hasNextBatch?: boolean
  hasPreviousBatch?: boolean
  currentPage: number
  totalPages: number | null
  pageDimensions: Array<[number, number] | null>
  showControls: boolean
  clickOnlyControls: boolean
  progressText: string
  progressPercent: number
}>()

const emit = defineEmits<{
  'update:currentPage': [page: number]
  visiblePage: [mediaId: number, page: number]
  viewerClick: []
  viewerDoubleClick: []
  hideControls: []
  controlsHover: [hovering: boolean]
  boundary: [direction: -1 | 1]
  loadMore: []
}>()

const enhancementError = ref('')
async function changeEnhancement(mode: ImageEnhancement) {
  enhancementError.value = ''
  try { await setDesktopPreferences(desktopState.videoMode, mode) }
  catch (error: unknown) { enhancementError.value = error instanceof Error ? error.message : '无法切换增强设置，当前仍可阅读原图。' }
}
const mobileReader = window.innerWidth < 900
const preferencePrefix = props.imagePages ? 'he_image' : 'he_manga'
const modeKey = `${preferencePrefix}_read_mode${mobileReader ? '_mobile' : ''}`
const savedMode = localStorage.getItem(modeKey)
const readMode = ref<MangaReadMode>(savedMode === 'single' || savedMode === 'double' || savedMode === 'webtoon' ? savedMode : mobileReader ? 'webtoon' : 'single')
const isRtl = ref(localStorage.getItem(`${preferencePrefix}_rtl`) === 'true')
const showShortcutGuide = ref(false)

const stripKey = mobileReader ? 'he_manga_strip_collapsed_mobile' : 'he_manga_strip_collapsed'
const isStripCollapsed = ref(localStorage.getItem(stripKey) === 'true' || (mobileReader && localStorage.getItem(stripKey) === null))
const toggleStripCollapsed = () => {
  isStripCollapsed.value = !isStripCollapsed.value
  localStorage.setItem(stripKey, String(isStripCollapsed.value))
}
const isStripOpen = computed(() => !props.imagePages && (props.showControls || !props.clickOnlyControls) && !isStripCollapsed.value)

const thumbStripRef = ref<HTMLDivElement | null>(null)
const imageContainerRef = ref<HTMLDivElement | null>(null)
const canvasContentRef = ref<HTMLDivElement | null>(null)
const webtoonContainerRef = ref<HTMLDivElement | null>(null)
const webtoonContentRef = ref<HTMLDivElement | null>(null)
const webtoonZoom = useWebtoonZoom(webtoonContainerRef, webtoonContentRef)
const compactViewport = useCompactViewport()
const thumbStripScroll = ref(0)
const stripContainerWidth = ref(800)
let stripResizeObserver: ResizeObserver | null = null
const hoverThumbIndex = ref(-1)
const hoverThumbX = ref(0)
const hoverThumbY = ref(0)
let hoverTimer: number | undefined
let isDragging = false
let dragStartX = 0
let dragScrollStart = 0
let dragMoved = false
let lastWheelAt = 0
let isProgrammaticScroll = false
let programmaticScrollTimer: number | undefined
let scrollReportedPage: number | null = null
let webtoonScrollRafId: number | null = null
let scrollRafId: number | null = null
let dragRafId: number | null = null
let pendingDragScroll = 0
let webtoonTouchX = 0
let webtoonTouchY = 0
let webtoonTouchActive = false
let suppressWebtoonClick = false
let scrollDirection: -1 | 1 = 1
let lastWebtoonScrollTop = 0

const {
  isZoomed,
  isPanning: isZoomPanning,
  zoomPercent,
  zoomIn,
  zoomOut,
  resetZoom,
  handleZoomWheel,
  onMouseDown: onZoomMouseDown,
  wasDragging: wasZoomDragging,
  onTouchStart: onCanvasTouchStart, onTouchMove, onTouchEnd, wasTouchGesture, wasDoubleTap,
} = useImageViewerZoom(imageContainerRef, {
  contentRef: canvasContentRef,
  contentSize: (width, height) => canvasContentSize(width, height),
  doubleTapScale: 2.5,
  onDoubleTap: () => { if (compactViewport.value && !desktopBridge) emit('hideControls') },
  onSwipe: direction => { if ((direction === 1) !== isRtl.value) nextPage(); else previousPage() },
})
const showZoomControls = computed(() => props.showControls || (isZoomed.value && (!compactViewport.value || !!desktopBridge)))
const hideControlsForPinch = (event: TouchEvent) => {
  if (event.touches.length > 1 && compactViewport.value && !desktopBridge) emit('hideControls')
}
// Extent of the fitted page images, so a zoomed page pans to its edges rather than into the letterbox.
const canvasContentSize = (width: number, height: number) => {
  const pages = canvasPages.value
  const slot = width / pages.length
  let first = 0, last = 0, tallest = 0
  pages.forEach((page, index) => {
    const [pageWidth, pageHeight] = pageDimensionsFor(page)
    const fit = Math.min(slot / pageWidth, height / pageHeight)
    if (index === 0) first = pageWidth * fit
    if (index === pages.length - 1) last = pageWidth * fit
    tallest = Math.max(tallest, pageHeight * fit)
  })
  return { width: Math.min(width, width - slot + (first + last) / 2), height: tallest }
}
const onTouchStart = (event: TouchEvent) => { hideControlsForPinch(event); onCanvasTouchStart(event) }

const THUMB_W = 110
const THUMB_H = 148
const THUMB_GAP = 12
const THUMB_PAD = 24
const THUMB_BUFFER = 8
const WHEEL_INTERVAL_MS = 320

const stepSize = computed(() => (readMode.value === 'double' ? 2 : 1))

// Page selection v2 excludes auxiliary images. Do not reuse browser caches
// populated when the same page index could still refer to a hidden cover.
const pageUrlFor = (page: number) => props.imagePages
  ? authUrl(`${API_BASE_URL}/stream/${props.imagePages[page]?.id}`)
  : authUrl(`${API_BASE_URL}/manga/${props.media.id}/page/${page}?track_progress=false&page_set=2`)
const canvasPages = computed(() => {
  const pages = [props.currentPage]
  if (readMode.value === 'double' && (props.totalPages === null || props.currentPage + 1 < props.totalPages)) {
    pages.push(props.currentPage + 1)
  }
  return isRtl.value ? pages.reverse() : pages
})
const desktopImages = useDesktopImageEnhancement(() => canvasPages.value.filter(page => page >= 0 && (props.totalPages === null || page < props.totalPages)).map(pageUrlFor))
const displayPageUrlFor = (page: number) => desktopImages.displayUrl(pageUrlFor(page))
const pageLabel = (page: number) => `第 ${page + 1} ${props.imagePages ? '张' : '页'}`
const thumbnailUrl = (page: number) => authUrl(`${API_BASE_URL}/manga/${props.media.id}/page/${page}?thumbnail=true&track_progress=false&page_set=2`)

const totalPagesList = computed(() => {
  if (!props.totalPages) return []
  return Array.from({ length: props.totalPages }, (_, i) => i)
})

const setPage = (page: number) => {
  const maximum = props.totalPages ? props.totalPages - 1 : Number.MAX_SAFE_INTEGER
  emit('update:currentPage', Math.max(0, Math.min(page, maximum)))
}

const previousPage = () => {
  if (props.currentPage === 0 && props.hasPreviousBatch) { emit('boundary', -1); return }
  if (readMode.value === 'webtoon') {
    if (webtoonContainerRef.value) {
      webtoonContainerRef.value.scrollBy({ top: -window.innerHeight * 0.7, behavior: 'smooth' })
    }
    return
  }
  setPage(props.currentPage - stepSize.value)
}

const nextPage = () => {
  if (props.totalPages && props.currentPage + stepSize.value >= props.totalPages && props.hasNextBatch) { emit('boundary', 1); return }
  if (readMode.value === 'webtoon') {
    if (webtoonContainerRef.value) {
      webtoonContainerRef.value.scrollBy({ top: window.innerHeight * 0.7, behavior: 'smooth' })
    }
    return
  }
  const maximum = props.totalPages ? props.totalPages - 1 : Number.MAX_SAFE_INTEGER
  if (props.totalPages === null || props.currentPage < maximum) {
    setPage(props.currentPage + stepSize.value)
  }
}

const setReadMode = (mode: MangaReadMode) => {
  webtoonZoom.reset()
  readMode.value = mode
  localStorage.setItem(modeKey, mode)
  resetZoom()
  if (mode === 'webtoon') {
    nextTick(() => {
      scrollWebtoonToPage(props.currentPage)
    })
  }
}

const toggleRtl = () => {
  isRtl.value = !isRtl.value
  localStorage.setItem(`${preferencePrefix}_rtl`, String(isRtl.value))
}

const toggleShortcutGuide = () => {
  showShortcutGuide.value = !showShortcutGuide.value
}

const onSliderInput = (event: Event) => {
  const target = event.target as HTMLInputElement
  setPage(Number(target.value))
}

const isThumbnailActive = (index: number) => {
  if (readMode.value === 'double') {
    return index === props.currentPage || index === props.currentPage + 1
  }
  return index === props.currentPage
}

const totalWidth = computed(() => {
  if (!props.totalPages) return 0
  return THUMB_PAD * 2 + props.totalPages * THUMB_W + (props.totalPages - 1) * THUMB_GAP
})

const updateStripWidth = () => {
  if (thumbStripRef.value) {
    const w = thumbStripRef.value.clientWidth
    if (w > 0) stripContainerWidth.value = w
  }
}

watch(thumbStripRef, (el) => {
  if (stripResizeObserver) {
    stripResizeObserver.disconnect()
    stripResizeObserver = null
  }
  if (el && typeof ResizeObserver !== 'undefined') {
    stripResizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0) {
          stripContainerWidth.value = entry.contentRect.width
        }
      }
    })
    stripResizeObserver.observe(el)
    updateStripWidth()
  }
})

const visibleThumbnails = computed(() => {
  if (!props.totalPages) return []
  const containerWidth = stripContainerWidth.value
  const start = Math.max(0, Math.floor((thumbStripScroll.value - THUMB_PAD) / (THUMB_W + THUMB_GAP)) - THUMB_BUFFER)
  const end = Math.min(
    props.totalPages - 1,
    Math.ceil((thumbStripScroll.value + containerWidth - THUMB_PAD) / (THUMB_W + THUMB_GAP)) + THUMB_BUFFER,
  )
  return Array.from({ length: end - start + 1 }, (_, offset) => {
    const index = start + offset
    return { index, left: THUMB_PAD + index * (THUMB_W + THUMB_GAP) }
  })
})

const scrollToPage = (page: number, smooth = true) => {
  void nextTick(() => {
    const element = thumbStripRef.value
    if (!element) return
    const target = THUMB_PAD + page * (THUMB_W + THUMB_GAP) - element.clientWidth / 2 + THUMB_W / 2
    element.scrollTo({ left: Math.max(0, target), behavior: smooth ? 'smooth' : 'auto' })
  })
}

const onStripScroll = () => {
  if (scrollRafId !== null) return
  scrollRafId = requestAnimationFrame(() => {
    scrollRafId = null
    if (thumbStripRef.value) {
      thumbStripScroll.value = thumbStripRef.value.scrollLeft
    }
  })
}

const onStripMouseEnter = () => {
  emit('controlsHover', true)
}

const onStripMouseLeave = () => {
  if (isDragging) return
  onThumbLeave()
  emit('controlsHover', false)
}

const onDragStart = (event: MouseEvent) => {
  const element = thumbStripRef.value
  if (!element) return
  isDragging = true
  dragMoved = false
  dragStartX = event.clientX
  dragScrollStart = element.scrollLeft
  element.style.cursor = 'grabbing'
  element.style.scrollBehavior = 'auto'
  emit('controlsHover', true)
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragEnd)
}

const onDragMove = (event: MouseEvent) => {
  if (!isDragging || !thumbStripRef.value) return
  const delta = event.clientX - dragStartX
  if (Math.abs(delta) > 3) dragMoved = true
  pendingDragScroll = dragScrollStart - delta
  if (dragRafId !== null) return
  dragRafId = requestAnimationFrame(() => {
    dragRafId = null
    if (thumbStripRef.value) {
      thumbStripRef.value.scrollLeft = pendingDragScroll
    }
  })
}

const onDragEnd = (event: MouseEvent) => {
  isDragging = false
  if (dragRafId !== null) {
    cancelAnimationFrame(dragRafId)
    dragRafId = null
  }
  if (thumbStripRef.value) {
    thumbStripRef.value.style.cursor = 'grab'
    thumbStripRef.value.style.scrollBehavior = ''
  }
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  const rect = thumbStripRef.value?.parentElement?.getBoundingClientRect()
  if (rect) {
    const isInside = event.clientX >= rect.left && event.clientX <= rect.right &&
                     event.clientY >= rect.top && event.clientY <= rect.bottom
    if (!isInside) {
      onThumbLeave()
      emit('controlsHover', false)
    }
  }
}

const onThumbClick = (page: number) => {
  if (!dragMoved) setPage(page)
}

const onThumbEnter = (page: number, event: MouseEvent) => {
  if (isDragging) return
  const target = event.currentTarget as HTMLElement
  window.clearTimeout(hoverTimer)
  hoverTimer = window.setTimeout(() => {
    if (isDragging) return
    hoverThumbIndex.value = page
    emit('controlsHover', true)
    const rect = target.getBoundingClientRect()
    const stripRect = thumbStripRef.value?.parentElement?.getBoundingClientRect()
    if (!stripRect) return
    hoverThumbX.value = rect.left + rect.width / 2 - stripRect.left
    hoverThumbY.value = rect.top - stripRect.top - 8
  }, 70)
}

const onThumbLeave = () => {
  window.clearTimeout(hoverTimer)
  hoverThumbIndex.value = -1
}

const onWheel = (event: WheelEvent) => {
  if (readMode.value === 'webtoon') {
    return
  }
  if (event.ctrlKey || event.metaKey) {
    handleZoomWheel(event)
    return
  }
  const now = Date.now()
  if (now - lastWheelAt < WHEEL_INTERVAL_MS) return
  const delta = Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX
  if (Math.abs(delta) < 8) return
  event.preventDefault()
  lastWheelAt = now
  delta > 0 ? nextPage() : previousPage()
}

const onWebtoonScroll = () => {
  if (webtoonTouchActive) suppressWebtoonClick = true
  scheduleVisiblePage()
  if (isProgrammaticScroll || readMode.value !== 'webtoon' || webtoonScrollRafId !== null) return
  webtoonScrollRafId = requestAnimationFrame(() => {
    webtoonScrollRafId = null
    if (isProgrammaticScroll || readMode.value !== 'webtoon') return
    const container = webtoonContainerRef.value
    if (!container || !props.totalPages) return
    const containerTop = container.scrollTop + container.clientHeight / 2
    const children = webtoonContentRef.value?.children
    if (!children?.length) return
    if (container.scrollTop !== lastWebtoonScrollTop) scrollDirection = container.scrollTop > lastWebtoonScrollTop ? 1 : -1
    lastWebtoonScrollTop = container.scrollTop
    let low = 0
    let high = children.length - 1
    while (low < high) {
      const mid = Math.floor((low + high) / 2)
      const el = children[mid] as HTMLElement
      if ((el.offsetTop + el.offsetHeight) * webtoonZoom.scale.value < containerTop) low = mid + 1
      else high = mid
    }
    if (container.scrollTop + container.clientHeight >= container.scrollHeight - 2) low = children.length - 1
    // Warm the actual viewport before waiting for parent/router progress updates.
    preloadAdjacentPages(low, true)
    if (!webtoonZoom.isInteracting.value && low !== props.currentPage) {
      // Scrolling reports progress; it must not trigger the page-navigation watcher.
      scrollReportedPage = low
      emit('update:currentPage', low)
    }
  })
}

const scrollWebtoonToPage = (page: number) => {
  if (readMode.value !== 'webtoon') return
  const container = webtoonContainerRef.value
  const el = webtoonContentRef.value?.children[page] as HTMLElement | undefined
  if (!container || !el) return
  isProgrammaticScroll = true
  window.clearTimeout(programmaticScrollTimer)
  // Only move the reader. scrollIntoView can also move the surrounding overlay.
  container.scrollTo({ top: el.offsetTop * webtoonZoom.scale.value, behavior: 'auto' })
  lastWebtoonScrollTop = container.scrollTop
  preloadAdjacentPages(page, true)
  programmaticScrollTimer = window.setTimeout(() => {
    isProgrammaticScroll = false
  }, 100)
}

// Observe native scrolling without preventing it or invoking paged-mode swipes.
const onWebtoonTouchStart = (event: TouchEvent) => {
  hideControlsForPinch(event)
  webtoonZoom.onTouchStart(event)
  if (!webtoonTouchActive) {
    suppressWebtoonClick = false
    webtoonTouchX = event.touches[0]?.clientX ?? 0
    webtoonTouchY = event.touches[0]?.clientY ?? 0
  }
  webtoonTouchActive = true
  if (event.touches.length !== 1) suppressWebtoonClick = true
}
const onWebtoonTouchMove = (event: TouchEvent) => {
  webtoonZoom.onPassiveTouchMove(event)
  const touch = event.touches[0]
  if (event.touches.length !== 1 || (touch && Math.hypot(touch.clientX - webtoonTouchX, touch.clientY - webtoonTouchY) > 8)) {
    suppressWebtoonClick = true
  }
}
const onWebtoonTouchEnd = (event: TouchEvent) => {
  webtoonZoom.onTouchEnd(event)
  const touch = event.changedTouches[0]
  if (event.type === 'touchcancel' || (touch && Math.hypot(touch.clientX - webtoonTouchX, touch.clientY - webtoonTouchY) > 8)) {
    suppressWebtoonClick = true
  }
  webtoonTouchActive = event.touches.length > 0
  if (!webtoonTouchActive) void nextTick(onWebtoonScroll)
}
const onWebtoonGesture = (event: Event) => {
  if (compactViewport.value && !desktopBridge) event.preventDefault()
}
// A touch double-tap zooms the page; only a mouse double-click toggles fullscreen.
const onViewerDoubleClick = () => {
  if (readMode.value !== 'webtoon' && wasDoubleTap()) return
  emit('viewerDoubleClick')
}
const onViewerClick = () => {
  if (readMode.value === 'webtoon' && suppressWebtoonClick) {
    suppressWebtoonClick = false
    return
  }
  if (wasZoomDragging() || wasTouchGesture()) return
  emit('viewerClick')
}

// Compensate once per render when decoded dimensions above the viewport change.
let pendingAnchor: { container: HTMLDivElement; element: HTMLElement; top: number } | null = null
const imageBuffer = useReaderImageBuffer(update => {
  const container = webtoonContainerRef.value
  const element = webtoonContentRef.value?.children[props.currentPage] as HTMLElement | undefined
  const anchor = !pendingAnchor && container && element && container.scrollTop > 0
    ? { container, element, top: element.offsetTop } : null
  if (anchor) pendingAnchor = anchor
  update()
  if (anchor) {
    void nextTick(async () => {
      webtoonZoom.measure()
      await nextTick()
      if (!webtoonZoom.isInteracting.value && webtoonContainerRef.value === anchor.container && anchor.element.isConnected) {
        const delta = (anchor.element.offsetTop - anchor.top) * webtoonZoom.scale.value
        if (delta) anchor.container.scrollTop += delta
      }
      pendingAnchor = null
      preloadAdjacentPages()
    })
  } else void nextTick(() => { webtoonZoom.measure(); preloadAdjacentPages() })
})
const pageDimensionsFor = (page: number): [number, number] => {
  const dimensions = props.pageDimensions[page]
  if (dimensions?.[0] && dimensions?.[1]) return dimensions
  const state = imageBuffer.states.get(pageUrlFor(page))
  return state?.width && state.height ? [state.width, state.height] : [2, 3]
}
const pageReady = (page: number) => imageBuffer.isDecoded(pageUrlFor(page))
const pageResident = (page: number) => imageBuffer.isResident(pageUrlFor(page))
const pageFailed = (page: number) => imageBuffer.states.get(pageUrlFor(page))?.status === 'error'
const pageAtOffset = (offset: number) => {
  const children = webtoonContentRef.value!.children
  let low = 0, high = children.length - 1
  while (low < high) {
    const mid = Math.floor((low + high) / 2), element = children[mid] as HTMLElement
    if ((element.offsetTop + element.offsetHeight) * webtoonZoom.scale.value < offset) low = mid + 1
    else high = mid
  }
  return low
}
const preloadAdjacentPages = (page = props.currentPage, fromViewport = false) => {
  if (!props.totalPages || authIdentity() !== openedIdentity) return
  let first = page, last = readMode.value === 'double' ? Math.min(page + 1, props.totalPages - 1) : page
  const container = webtoonContainerRef.value
  if (readMode.value === 'webtoon' && container?.clientHeight && (webtoonContentRef.value?.children[0] as HTMLElement | undefined)?.offsetHeight) {
    const visibleFirst = pageAtOffset(container.scrollTop)
    const visibleLast = pageAtOffset(container.scrollTop + container.clientHeight - 1)
    if (fromViewport || (page >= visibleFirst && page <= visibleLast)) { first = visibleFirst; last = visibleLast }
  }
  const planned = readerImageWindow(props.totalPages, first, last, scrollDirection, page => {
    const size = props.pageDimensions[page]
    if (size?.[0] && size?.[1]) return size
    const state = imageBuffer.states.get(pageUrlFor(page))
    return state?.width && state.height ? [state.width, state.height] : null
  })
  imageBuffer.requestWindow(planned.indices.map(pageUrlFor), planned.visibleCount)
}
const onWebtoonImageLoad = async (event: Event) => {
  const image = event.target as HTMLImageElement
  // Prepare the displayed DOM image as well as the retained preloader bitmap.
  try { await image.decode() } catch { /* A loaded image remains usable without decode(). */ }
  if (image.isConnected) scheduleVisiblePage()
}
// Decoder/prefetch readiness alone never advances desktop reading progress.
// Observe the actual displayed image after a paint, including cache hits.
const openedIdentity = authIdentity()
let visibleRaf: number | null = null, visibleDisposed = false, lastVisible = ''
function reportVisiblePage() {
  if (!desktopBridge || props.imagePages || visibleDisposed || document.hidden || authIdentity() !== openedIdentity) return
  const container = readMode.value === 'webtoon' ? webtoonContainerRef.value : imageContainerRef.value
  if (!container?.isConnected) return
  const rect = container.getBoundingClientRect()
  const top = Math.max(0, rect.top), bottom = Math.min(innerHeight, rect.bottom)
  const left = Math.max(0, rect.left), right = Math.min(innerWidth, rect.right)
  if (bottom <= top || right <= left) return
  let candidates = canvasPages.value
  if (readMode.value === 'webtoon') {
    const pages = [...container.querySelectorAll<HTMLElement>('.he-reader-page')]
    const atBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 2
    const line = (top + bottom) / 2
    const page = atBottom ? pages.at(-1) : pages.find(page => {
      const box = page.getBoundingClientRect(); return box.top <= line && box.bottom >= line
    })
    candidates = page ? [Number(page.dataset.page)] : []
  }
  const visible = candidates.filter(page => {
    const holder = container.querySelector<HTMLElement>(`[data-page="${page}"]`)
    const image = holder?.querySelector('img')
    if (!holder || !image?.complete || !image.naturalWidth) return false
    const source = new URL(image.currentSrc || image.getAttribute('src') || '', location.href).href
    if (source !== new URL(displayPageUrlFor(page), location.href).href) return false
    const box = image.getBoundingClientRect()
    return box.width > 0 && box.height > 0 && box.bottom > top && box.top < bottom && box.right > left && box.left < right
  })
  if (!visible.length) return
  const page = Math.max(...visible), key = `${props.media.id}:${page}`
  if (key === lastVisible) return
  lastVisible = key
  emit('visiblePage', props.media.id, page)
}
function scheduleVisiblePage() {
  if (!desktopBridge || visibleDisposed || visibleRaf !== null) return
  visibleRaf = requestAnimationFrame(() => {
    visibleRaf = requestAnimationFrame(() => { visibleRaf = null; reportVisiblePage() })
  })
}
watch([() => props.currentPage, readMode, () => props.totalPages,
  () => canvasPages.value.map(page => displayPageUrlFor(page)).join('|')], () => { void nextTick(scheduleVisiblePage) }, { immediate: true })

watch(() => [props.totalPages, readMode.value, props.imagePages?.map(item => item.id).join(',')], () => { preloadAdjacentPages(); void nextTick(() => preloadAdjacentPages()) })
watch(() => props.showControls, visible => { if (!visible) showShortcutGuide.value = false })
defineExpose({ nextPage, previousPage, stepSize, flushVisiblePage: reportVisiblePage })

watch(() => props.currentPage, page => {
  if (readMode.value !== 'webtoon') {
    resetZoom()
  } else if (page === scrollReportedPage) {
    scrollReportedPage = null
  } else {
    scrollReportedPage = null
    void nextTick(() => scrollWebtoonToPage(page))
  }
  scrollToPage(page)
  preloadAdjacentPages()
}, { immediate: true })
watch(() => props.totalPages, (total, previousTotal) => {
  if (!total) return
  scrollToPage(props.currentPage, false)
  if (readMode.value === 'webtoon' && !previousTotal) {
    void nextTick(() => scrollWebtoonToPage(props.currentPage))
  }
})
watch(() => props.media.id, () => {
  if (props.imagePages) return
  imageBuffer.clear()
  scrollDirection = 1; lastWebtoonScrollTop = 0
  preloadAdjacentPages()
  scrollReportedPage = null
  hoverThumbIndex.value = -1
  thumbStripScroll.value = 0
  scrollToPage(props.currentPage, false)
})

watch(isStripOpen, (open) => {
  if (open) {
    nextTick(() => {
      updateStripWidth()
      scrollToPage(props.currentPage, false)
    })
  }
})

onMounted(() => {
  updateStripWidth()
  preloadAdjacentPages()
  window.addEventListener('resize', onReaderViewportResize, { passive: true })
  window.addEventListener('resize', updateStripWidth, { passive: true })
  window.addEventListener('resize', scheduleVisiblePage, { passive: true })
  document.addEventListener('visibilitychange', scheduleVisiblePage)
})

onBeforeUnmount(() => {
  visibleDisposed = true
  if (visibleRaf !== null) cancelAnimationFrame(visibleRaf)
  window.removeEventListener('resize', scheduleVisiblePage)
  document.removeEventListener('visibilitychange', scheduleVisiblePage)
  imageBuffer.dispose()
  window.removeEventListener('resize', onReaderViewportResize)
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragEnd)
  window.removeEventListener('resize', updateStripWidth)
  window.clearTimeout(programmaticScrollTimer)
  window.clearTimeout(hoverTimer)
  if (scrollRafId !== null) cancelAnimationFrame(scrollRafId)
  if (webtoonScrollRafId !== null) cancelAnimationFrame(webtoonScrollRafId)
  if (dragRafId !== null) cancelAnimationFrame(dragRafId)
  if (stripResizeObserver) {
    stripResizeObserver.disconnect()
    stripResizeObserver = null
  }
})
function onReaderViewportResize() { preloadAdjacentPages() }
</script>

<template>
  <div class="he-manga-reader flex-1 min-h-0 flex flex-col bg-black overflow-hidden relative">
    <UiToast v-if="enhancementError || desktopImages.message.value" :message="enhancementError || desktopImages.message.value" :urgent="!!enhancementError" overlay class="pointer-events-none absolute left-1/2 top-16 z-30 max-w-[90%] -translate-x-1/2" />
    <div
      class="flex-1 min-h-0 flex items-center justify-center w-full relative group overflow-hidden"
      @wheel="onWheel"
      @click="onViewerClick"
      @dblclick="onViewerDoubleClick"
    >
      <!-- Left Prev Button -->
      <button
        @click.stop="previousPage"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 -translate-x-6 pointer-events-none'
            : 'opacity-0 -translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="he-page-nav absolute left-5 z-20 grid size-12 place-items-center rounded-full bg-black/60 text-white/80 transition-[opacity,transform,background-color,color] duration-200 ease-out hover:bg-black/80 hover:text-white focus-ring"
        title="上一页" aria-label="上一页" :tabindex="showControls ? 0 : -1"
      >
        <ChevronLeft :size="26" aria-hidden="true" />
      </button>

      <!-- Webtoon Continuous Scroll Mode -->
      <div
        v-if="readMode === 'webtoon'"
        ref="webtoonContainerRef"
        style="overflow-anchor: none; overscroll-behavior: contain; touch-action: pan-y"
        class="he-webtoon-viewport w-full h-full overflow-y-auto overflow-x-hidden custom-scrollbar select-none"
        @scroll="onWebtoonScroll"
        @touchstart.passive="onWebtoonTouchStart"
        @touchmove.passive="onWebtoonTouchMove"
        @touchend.passive="onWebtoonTouchEnd"
        @touchcancel.passive="onWebtoonTouchEnd"
        @gesturestart="onWebtoonGesture" @gesturechange="onWebtoonGesture"
      >
        <div class="he-webtoon-space relative w-full">
          <div ref="webtoonContentRef" class="he-webtoon-content relative w-full flex flex-col items-center py-6 px-2">
            <div
              v-for="pageIndex in totalPagesList"
              :key="imagePages?.[pageIndex]?.id ?? pageIndex"
              :id="`webtoon-page-${pageIndex}`"
              :data-page="pageIndex"
              class="he-reader-page w-full max-w-[840px] shrink-0 my-1 relative group bg-white/5"
              :style="{ aspectRatio: `${pageDimensionsFor(pageIndex)[0]} / ${pageDimensionsFor(pageIndex)[1]}` }"
              :aria-busy="!pageReady(pageIndex) && !pageFailed(pageIndex)"
            >
              <img
                v-if="pageResident(pageIndex)"
                :src="displayPageUrlFor(pageIndex)"
                @load="onWebtoonImageLoad"
                :width="pageDimensionsFor(pageIndex)[0]"
                :height="pageDimensionsFor(pageIndex)[1]"
                loading="eager"
                decoding="async"
                class="w-full h-full object-contain block rounded-sm"
                :alt="imagePages?.[pageIndex]?.title || `第 ${pageIndex + 1} 页`"
              />
              <div v-else-if="pageFailed(pageIndex)" class="absolute inset-0 flex flex-col items-center justify-center gap-3 text-meta text-white/60" role="status">
                <span>图片加载失败</span>
                <button type="button" class="h-10 rounded-lg bg-white/10 px-4 text-body font-medium text-white transition-colors hover:bg-white/15 focus-ring pointer-coarse:h-11" @click.stop="imageBuffer.retry(pageUrlFor(pageIndex))">重新加载</button>
              </div>
              <div v-if="showControls" class="pointer-events-none absolute right-2 top-2 inline-flex h-6 items-center rounded-md bg-black/60 px-1.5 text-caption font-medium tabular-nums text-white/90 opacity-0 transition-opacity group-hover:opacity-100">
                {{ pageIndex + 1 }} / {{ totalPages }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Single / Double Page Canvas Mode -->
      <div
        v-else
        ref="imageContainerRef"
        class="w-full h-full flex items-center justify-center overflow-hidden select-none"
        :style="{ cursor: isZoomed ? (isZoomPanning ? 'grabbing' : 'grab') : 'default' }"
        @mousedown="onZoomMouseDown"
        @touchstart="onTouchStart" @touchmove="onTouchMove" @touchend="onTouchEnd" @touchcancel="onTouchEnd"
        style="touch-action: none"
      >
        <!-- Key each page by its source, so a pending page never retains the previous bitmap. -->
        <!-- Transform is written by useImageViewerZoom, so gestures do not re-render the reader. -->
        <div
          ref="canvasContentRef"
          class="w-full h-full flex items-center justify-center"
          :class="readMode === 'double' ? 'gap-1 sm:gap-2 px-2' : ''"
        >
          <div
            v-for="pageIndex in canvasPages"
            :key="pageUrlFor(pageIndex)"
            class="he-reader-canvas-page relative flex h-full min-w-0 flex-1 items-center justify-center"
            :aria-label="pageLabel(pageIndex)"
            :data-page="pageIndex"
            :aria-busy="!pageReady(pageIndex) && !pageFailed(pageIndex)"
          >
            <img
              v-if="pageReady(pageIndex)"
              :src="displayPageUrlFor(pageIndex)"
            @load="scheduleVisiblePage"
              decoding="sync"
              class="h-full w-full object-contain pointer-events-none"
              :alt="imagePages?.[pageIndex]?.title || pageLabel(pageIndex)"
            />
            <div v-else class="flex flex-col items-center justify-center gap-3 px-4 text-center text-meta text-white/75" role="status" aria-live="polite">
              <template v-if="pageFailed(pageIndex)">
                <span>{{ pageLabel(pageIndex) }}加载失败</span>
                <button
                  type="button"
                  class="min-h-11 rounded-lg bg-white/10 px-4 text-body font-medium text-white transition-colors hover:bg-white/15 focus-ring"
                  @mousedown.stop @touchstart.stop @dblclick.stop
                  @click.stop="imageBuffer.retry(pageUrlFor(pageIndex))"
                >重新加载</button>
              </template>
              <template v-else>
                <Loader2 :size="28" class="animate-spin motion-reduce:animate-none" aria-hidden="true" />
                <span>正在加载{{ pageLabel(pageIndex) }}…</span>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- Right Next Button -->
      <button
        @click.stop="nextPage"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        :class="showControls
          ? 'opacity-100 translate-x-0'
          : clickOnlyControls
            ? 'opacity-0 translate-x-6 pointer-events-none'
            : 'opacity-0 translate-x-6 hover:opacity-100 hover:translate-x-0'"
        class="he-page-nav absolute right-5 z-20 grid size-12 place-items-center rounded-full bg-black/60 text-white/80 transition-[opacity,transform,background-color,color] duration-200 ease-out hover:bg-black/80 hover:text-white focus-ring"
        title="下一页" aria-label="下一页" :tabindex="showControls ? 0 : -1"
      >
        <ChevronRight :size="26" aria-hidden="true" />
      </button>

      <!-- Bottom Floating Control Pill (Slider + Mode Switcher + Shortcuts) -->
      <div
        :class="showControls || !clickOnlyControls ? 'opacity-100' : 'opacity-0 pointer-events-none'"
        :inert="!showControls && clickOnlyControls"
        class="he-manga-controls absolute left-1/2 z-20 flex w-[min(640px,calc(100%-2rem))] select-none flex-col gap-2 rounded-2xl bg-black/75 p-2.5 text-white ring-1 ring-inset ring-white/10 transition-[transform,opacity] duration-200 ease-out sm:px-3"
        :style="{
          width: desktopBridge ? 'min(800px, calc(100% - 2rem))' : undefined,
          bottom: 'calc(12px + env(safe-area-inset-bottom))',
          transform: `translate3d(-50%, ${isStripOpen ? 'calc(-184px - env(safe-area-inset-bottom))' : (showControls || !clickOnlyControls ? '0px' : '12px')}, 0)`,
        }"
        style="will-change: transform, opacity;"
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
        @click.stop
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <!-- Reading Mode Switcher -->
          <div class="flex shrink-0 items-center gap-0.5 rounded-lg bg-white/8 p-0.5" role="group" aria-label="阅读模式">
            <button
              type="button"
              @click="setReadMode('single')"
              class="he-reader-seg"
              :class="readMode === 'single' ? 'bg-white/15 text-white' : 'text-white/65 hover:text-white'"
              title="单页模式" :aria-pressed="readMode === 'single'"
            >
              <Square :size="14" aria-hidden="true" />
              <span class="hidden sm:inline">单页</span>
            </button>
            <button
              type="button"
              @click="setReadMode('double')"
              class="he-reader-seg"
              :class="readMode === 'double' ? 'bg-white/15 text-white' : 'text-white/65 hover:text-white'"
              title="双页跨页模式" :aria-pressed="readMode === 'double'"
            >
              <Columns2 :size="14" aria-hidden="true" />
              <span class="hidden sm:inline">双页</span>
            </button>
            <button
              type="button"
              @click="setReadMode('webtoon')"
              class="he-reader-seg"
              :class="readMode === 'webtoon' ? 'bg-white/15 text-white' : 'text-white/65 hover:text-white'"
              title="连续卷轴模式 (条漫)" :aria-pressed="readMode === 'webtoon'"
            >
              <ScrollText :size="14" aria-hidden="true" />
              <span class="hidden sm:inline">卷轴</span>
            </button>
          </div>

          <!-- In Double Mode: RTL / LTR Toggle -->
          <button
            v-if="readMode === 'double'"
            type="button"
            @click="toggleRtl"
            class="he-reader-btn px-2.5 text-meta font-medium text-white/80 hover:bg-white/10 hover:text-white"
            :title="isRtl ? '日漫从右往左翻 (RTL)' : '普通从左往右翻 (LTR)'"
          >
            {{ isRtl ? '从右往左' : '从左往右' }}
          </button>

          <button v-if="imagePages && hasNextBatch" type="button" title="加载后续图片" class="he-reader-btn px-2.5 text-meta font-medium text-white/80 hover:bg-white/10 hover:text-white" @click="emit('loadMore')">更多图片</button>

          <label v-if="desktopBridge" class="shrink-0 text-meta text-white/80">
            <span class="sr-only">图片增强</span>
            <select aria-label="图片增强" :value="desktopState.imageMode" :disabled="!desktopState.image" class="he-reader-btn max-w-36 rounded-lg border border-white/20 bg-black/80 px-2 text-white focus-ring disabled:opacity-50" @change="changeEnhancement(($event.target as HTMLSelectElement).value as ImageEnhancement)">
              <option value="off">原画</option><option value="anime">动漫 · 2×</option><option value="photo">图片 · 4×</option>
            </select>
          </label>

          <!-- Middle Page info -->
          <div class="ml-auto flex shrink-0 items-baseline gap-2 whitespace-nowrap px-1 tabular-nums">
            <span class="text-body font-medium text-white">{{ progressText }}</span>
            <span class="text-meta text-white/60">{{ progressPercent }}%</span>
          </div>

          <!-- Shortcut Guide Toggle Button -->
          <button
            type="button"
            @click="toggleShortcutGuide"
            class="he-reader-btn w-8 text-white/70 hover:bg-white/10 hover:text-white"
            :class="{ 'bg-white/15 text-white': showShortcutGuide }"
            title="快捷键指南" aria-label="快捷键指南" :aria-expanded="showShortcutGuide" data-keyboard-guide
          >
            <Keyboard :size="16" aria-hidden="true" />
          </button>

          <!-- Toggle Thumbnail Strip Button -->
          <button
            v-if="!imagePages && totalPages && totalPages > 0"
            type="button"
            @click="toggleStripCollapsed"
            class="he-reader-btn gap-1.5 px-2.5 text-meta font-medium text-white/70 hover:bg-white/10 hover:text-white"
            :class="{ 'bg-white/15 text-white': isStripOpen }"
            :title="isStripOpen ? '收起底部预览长条' : '展开底部预览长条'"
          >
            <GalleryHorizontal :size="15" aria-hidden="true" />
            <span class="hidden sm:inline">{{ isStripOpen ? '收起目录' : '展开目录' }}</span>
          </button>
        </div>

        <!-- Interactive Progress Slider -->
        <div class="relative flex items-center px-1">
          <input
            type="range"
            :min="0"
            :max="Math.max(0, (totalPages || 1) - 1)"
            :step="stepSize"
            :value="currentPage"
            @input="onSliderInput"
            class="he-reader-slider h-5 w-full cursor-pointer"
            :style="{ '--fill': `${Math.min(100, Math.max(0, currentPage / Math.max(1, (totalPages || 1) - 1) * 100))}%` }"
            :title="`第 ${currentPage + 1} 页`"
          />
        </div>
      </div>

      <!-- Shortcut Guide Popover -->
      <div
        v-if="showShortcutGuide"
        class="absolute z-30 w-80 max-w-[calc(100%-2rem)] select-none rounded-2xl bg-black/90 p-4 text-meta text-white/85 ring-1 ring-inset ring-white/12 animate-fluid-entrance"
        :style="{
          bottom: isStripOpen ? '280px' : '96px',
          left: '50%',
          transform: 'translateX(-50%)',
          transition: 'bottom 240ms var(--ease-out)',
        }"
        @click.stop
      >
        <div class="mb-3 flex items-center justify-between">
          <span class="flex items-center gap-2 text-body font-medium text-white">
            <Keyboard :size="16" class="text-white/60" aria-hidden="true" />
            阅读器快捷键
          </span>
          <button type="button" class="he-reader-btn w-8 text-white/60 hover:bg-white/10 hover:text-white" aria-label="关闭快捷键指南" title="关闭" @click="showShortcutGuide = false"><X :size="16" aria-hidden="true" /></button>
        </div>
        <div class="space-y-2.5">
          <div class="flex items-center justify-between">
            <span class="text-white/65">翻页 / 换页</span>
            <kbd class="he-reader-kbd">← / →</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/65">滚轮翻页</span>
            <kbd class="he-reader-kbd">鼠标滚轮</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/65">画面缩放</span>
            <kbd class="he-reader-kbd">Ctrl + 滚轮 / + -</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/65">适应屏幕 / 重置</span>
            <kbd class="he-reader-kbd">0 / 双击</kbd>
          </div>
          <div class="flex items-center justify-between">
            <span class="text-white/65">拖拽平移</span>
            <kbd class="he-reader-kbd">按住鼠标左键</kbd>
          </div>
        </div>
      </div>

      <!-- Zoom Controls Floating Pill (Single / Double Mode) -->
      <div
        v-if="readMode !== 'webtoon'"
        :class="showZoomControls
          ? 'opacity-100'
          : 'opacity-0 pointer-events-none'"
        :inert="!showZoomControls"
        class="he-manga-zoom absolute right-6 z-20 flex select-none items-center gap-0.5 rounded-2xl bg-black/75 p-1 text-white/80 ring-1 ring-inset ring-white/10 transition-[transform,opacity] duration-200 ease-out"
        :style="{
          top: desktopBridge ? '84px' : undefined,
          bottom: desktopBridge ? 'auto' : 'calc(12px + env(safe-area-inset-bottom))',
          transform: `translate3d(0, ${desktopBridge ? (showControls ? '0px' : '-12px') : isStripOpen ? 'calc(-184px - env(safe-area-inset-bottom))' : (showZoomControls ? '0px' : '12px')}, 0)`,
        }"
        style="will-change: transform, opacity;"
        @click.stop
        @mouseenter="emit('controlsHover', true)"
        @mouseleave="emit('controlsHover', false)"
      >
        <button
          @click="zoomOut()"
          :disabled="!isZoomed"
          class="he-reader-btn w-8 hover:bg-white/10 hover:text-white disabled:pointer-events-none disabled:opacity-35"
          aria-label="缩小"
          title="缩小 (Ctrl + 滚轮向下 / 快捷键: -)"
        >
          <ZoomOut :size="16" aria-hidden="true" />
        </button>

        <button
          @click="resetZoom(true)"
          class="he-reader-btn min-w-14 px-2 text-meta font-medium tabular-nums hover:bg-white/10 hover:text-white"
          :class="isZoomed ? 'text-white' : 'text-white/65'"
          title="重置缩放 (快捷键: 0)"
        >
          {{ zoomPercent }}%
        </button>

        <button
          @click="zoomIn()"
          :disabled="zoomPercent >= 500"
          class="he-reader-btn w-8 hover:bg-white/10 hover:text-white disabled:pointer-events-none disabled:opacity-35"
          aria-label="放大"
          title="放大 (Ctrl + 滚轮向上 / 快捷键: +)"
        >
          <ZoomIn :size="16" aria-hidden="true" />
        </button>

        <button
          v-if="isZoomed"
          @click="resetZoom(true)"
          class="he-reader-btn w-8 text-white/65 hover:bg-white/10 hover:text-white"
          aria-label="适应屏幕"
          title="适应屏幕 (快捷键: 0)"
        >
          <RotateCcw :size="15" aria-hidden="true" />
        </button>
      </div>
    </div>

    <!-- Bottom Thumbnail Strip Bar -->
    <div
      v-if="!imagePages && totalPages && totalPages > 0"
      :class="isStripOpen
        ? 'translate-y-0 opacity-100'
        : 'translate-y-full opacity-0 pointer-events-none'"
      :inert="!isStripOpen"
      class="he-manga-strip absolute inset-x-0 bottom-0 z-30 flex select-none flex-col border-t border-white/10 bg-black/90 transition-[transform,opacity] duration-200 ease-out"
      style="will-change: transform, opacity;"
      @click.stop
      @mouseenter="onStripMouseEnter"
      @mouseleave="onStripMouseLeave"
    >
      <div class="flex items-center justify-between px-6 py-0.5 text-meta">
        <div class="flex items-center gap-2 tabular-nums">
          <span class="font-medium text-white/85">预览目录</span>
          <span class="text-white/55">共 {{ totalPages }} 页 · 第 {{ currentPage + 1 }} 页</span>
        </div>
        <button
          type="button"
          @click="toggleStripCollapsed"
          class="he-reader-btn !h-6 gap-1 px-2 text-meta text-white/65 hover:bg-white/10 hover:text-white"
          title="收起预览目录"
        >
          <ChevronDown :size="14" aria-hidden="true" />
          <span>收起</span>
        </button>
      </div>

      <div
        v-if="hoverThumbIndex >= 0"
        class="pointer-events-none absolute z-50 rounded-2xl bg-black/95 p-1 ring-1 ring-inset ring-white/15"
        :style="{ width: '200px', height: '268px', left: `${hoverThumbX}px`, top: `${hoverThumbY}px`, transform: 'translate(-50%, -100%)' }"
      >
        <img :src="thumbnailUrl(hoverThumbIndex)" class="h-full w-full rounded-lg object-contain" alt="" />
        <div class="absolute inset-x-1 bottom-1 rounded-b-lg bg-black/70 py-0.5 text-center text-caption font-medium tabular-nums text-white/90">
          第 {{ hoverThumbIndex + 1 }} 页
        </div>
      </div>

      <div
        ref="thumbStripRef"
        class="overflow-x-auto py-2 custom-scrollbar select-none"
        style="cursor: grab"
        @scroll="onStripScroll"
        @mousedown.prevent="onDragStart"
      >
        <div :style="{ width: `${totalWidth}px`, height: `${THUMB_H + 4}px`, position: 'relative' }">
          <div
            v-for="item in visibleThumbnails"
            :key="item.index"
            class="absolute top-0.5 cursor-pointer overflow-hidden rounded-lg border-2 transition-colors duration-150"
            style="contain: layout paint style;"
            :class="isThumbnailActive(item.index)
              ? 'z-10 border-accent bg-accent/10'
              : 'border-transparent bg-white/5 hover:border-white/30'"
            :style="{ left: `${item.left}px`, width: `${THUMB_W}px`, height: `${THUMB_H}px` }"
            @click="onThumbClick(item.index)"
            @mouseenter="onThumbEnter(item.index, $event)"
            @mouseleave="onThumbLeave"
          >
            <img
              :src="thumbnailUrl(item.index)"
              loading="lazy"
              decoding="async"
              class="h-full w-full object-cover"
              :class="isThumbnailActive(item.index) ? '' : 'opacity-80 hover:opacity-100'"
              draggable="false"
              alt=""
            />
            <div
              class="absolute inset-x-0 bottom-0 py-0.5 text-center text-caption font-medium tabular-nums"
              :class="isThumbnailActive(item.index) ? 'bg-accent text-on-accent' : 'bg-black/65 text-white/85'"
            >
              {{ item.index + 1 }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.he-reader-seg {
  display: inline-flex;
  flex-shrink: 0;
  white-space: nowrap;
  height: 32px;
  align-items: center;
  gap: 6px;
  border-radius: 6px;
  padding-inline: 10px;
  font-size: var(--text-meta, 0.8125rem);
  font-weight: 500;
  transition: background-color 120ms var(--ease-out), color 120ms var(--ease-out);
}
.he-reader-btn {
  display: inline-flex;
  height: 32px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  transition: background-color 120ms var(--ease-out), color 120ms var(--ease-out);
}
.he-reader-kbd {
  display: inline-flex;
  height: 22px;
  align-items: center;
  border-radius: 6px;
  border: 1px solid rgb(255 255 255 / 0.15);
  background: rgb(255 255 255 / 0.08);
  padding-inline: 6px;
  font-size: 0.75em;
  color: rgb(255 255 255 / 0.85);
}
.he-reader-slider {
  appearance: none;
  -webkit-appearance: none;
  background: transparent;
}
.he-reader-slider::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: 4px;
  background: linear-gradient(to right, rgb(var(--color-accent)) var(--fill, 0%), rgb(255 255 255 / 0.2) var(--fill, 0%));
}
.he-reader-slider::-moz-range-track {
  height: 4px;
  border-radius: 4px;
  background: linear-gradient(to right, rgb(var(--color-accent)) var(--fill, 0%), rgb(255 255 255 / 0.2) var(--fill, 0%));
}
.he-reader-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  margin-top: -5px;
  border-radius: 9999px;
  background: #fff;
  box-shadow: 0 0 0 3px rgb(var(--color-accent) / 0.45);
}
.he-reader-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border: 0;
  border-radius: 9999px;
  background: #fff;
  box-shadow: 0 0 0 3px rgb(var(--color-accent) / 0.45);
}
.he-reader-slider:focus-visible { outline: 2px solid rgb(var(--color-accent)); outline-offset: 2px; border-radius: 4px; }
@media (max-width: 899px) {
  .he-manga-controls > div:first-child { flex-wrap: wrap; gap: 4px; }
  .he-manga-controls button { min-height: 44px; min-width: 44px; }
  .he-manga-controls input[type="range"] { min-height: 30px; }
  [data-keyboard-guide] { display: none; }
  .he-manga-zoom { right: 12px; top: calc(140px + env(safe-area-inset-top)); bottom: auto !important; transform: none !important; }
  .he-manga-zoom button { min-height: 44px; min-width: 44px; }
  .he-manga-strip { padding-bottom: env(safe-area-inset-bottom); }
  .he-manga-strip button { min-height: 44px; }
  .he-page-nav.left-5 { left: 8px; width: 44px; height: 44px; }
  .he-page-nav.right-5 { right: 8px; width: 44px; height: 44px; }
}
</style>
