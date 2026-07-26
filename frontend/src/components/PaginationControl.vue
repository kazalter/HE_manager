<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, useId, watch } from 'vue'
import { Check, ChevronDown, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-vue-next'

const props = withDefaults(defineProps<{
  page: number
  pageCount: number
  totalItems: number
  pageSize: number
  itemLabel?: string
  disabled?: boolean
}>(), {
  itemLabel: '项',
  disabled: false,
})

const emit = defineEmits<{
  change: [page: number]
}>()

const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const open = ref(false)
const pageInput = ref(String(props.page))
const panelId = `pagination-${useId()}`

const pages = computed(() => Array.from({ length: props.pageCount }, (_, index) => index + 1))
const inputPage = computed(() => Number(pageInput.value))
const inputValid = computed(() => (
  /^\d+$/.test(pageInput.value)
  && Number.isSafeInteger(inputPage.value)
  && inputPage.value >= 1
  && inputPage.value <= props.pageCount
))
const rangeStart = computed(() => props.totalItems ? (props.page - 1) * props.pageSize + 1 : 0)
const rangeEnd = computed(() => Math.min(props.totalItems, props.page * props.pageSize))

watch(() => props.page, page => {
  pageInput.value = String(page)
})

watch(open, async value => {
  if (!value) return
  pageInput.value = String(props.page)
  await nextTick()
  const selected = panelRef.value?.querySelector<HTMLButtonElement>('[data-page][aria-current="page"]')
  selected?.scrollIntoView({ block: 'center' })
})

const togglePanel = () => {
  if (props.disabled) return
  open.value = !open.value
}

const choosePage = (page: number) => {
  if (props.disabled || page < 1 || page > props.pageCount) return
  open.value = false
  if (page !== props.page) emit('change', page)
  nextTick(() => triggerRef.value?.focus())
}

const submitJump = () => {
  if (!inputValid.value) {
    pageInput.value = String(props.page)
    return
  }
  choosePage(inputPage.value)
}

const onGridKeydown = (event: KeyboardEvent) => {
  const target = (event.target as HTMLElement).closest<HTMLButtonElement>('[data-page]')
  if (!target) return
  const current = Number(target.dataset.page)
  let next = current
  if (event.key === 'ArrowRight') next += 1
  else if (event.key === 'ArrowLeft') next -= 1
  else if (event.key === 'ArrowDown') next += 5
  else if (event.key === 'ArrowUp') next -= 5
  else if (event.key === 'Home') next = 1
  else if (event.key === 'End') next = props.pageCount
  else return
  event.preventDefault()
  const bounded = Math.max(1, Math.min(props.pageCount, next))
  panelRef.value?.querySelector<HTMLButtonElement>(`[data-page="${bounded}"]`)?.focus()
}

const onDocumentPointerDown = (event: PointerEvent) => {
  if (open.value && !rootRef.value?.contains(event.target as Node)) open.value = false
}

const onDocumentKeydown = (event: KeyboardEvent) => {
  if (!open.value || event.key !== 'Escape') return
  open.value = false
  triggerRef.value?.focus()
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onDocumentKeydown)
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onDocumentKeydown)
})
</script>

<template>
  <nav class="media-pagination" aria-label="媒体分页">
    <p class="media-pagination__summary">
      显示 <strong>{{ rangeStart.toLocaleString() }}–{{ rangeEnd.toLocaleString() }}</strong>
      <span>共 {{ totalItems.toLocaleString() }} {{ itemLabel }}</span>
    </p>

    <div class="media-pagination__controls">
      <button
        type="button"
        class="media-pagination__icon media-pagination__edge"
        aria-label="第一页"
        title="第一页"
        :disabled="disabled || page <= 1"
        @click="choosePage(1)"
      >
        <ChevronsLeft :size="17" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="media-pagination__icon"
        aria-label="上一页"
        title="上一页"
        :disabled="disabled || page <= 1"
        @click="choosePage(page - 1)"
      >
        <ChevronLeft :size="18" aria-hidden="true" />
      </button>

      <div ref="rootRef" class="media-page-picker" :class="{ 'is-open': open }">
        <button
          :id="`${panelId}-trigger`"
          ref="triggerRef"
          type="button"
          class="media-page-picker__trigger"
          :disabled="disabled"
          :aria-expanded="open"
          :aria-controls="panelId"
          aria-haspopup="dialog"
          @click="togglePanel"
        >
          <span>第 <strong>{{ page }}</strong> / {{ pageCount }} 页</span>
          <ChevronDown :size="15" aria-hidden="true" />
        </button>

        <Transition name="page-picker">
          <section
            v-if="open"
            :id="panelId"
            ref="panelRef"
            class="media-page-picker__panel"
            role="dialog"
            aria-label="选择页码"
            :aria-labelledby="`${panelId}-title`"
          >
            <header>
              <div>
                <strong :id="`${panelId}-title`">选择页码</strong>
                <small>共 {{ totalItems.toLocaleString() }} {{ itemLabel }}</small>
              </div>
              <span>{{ pageCount }} 页</span>
            </header>

            <form class="media-page-picker__jump" @submit.prevent="submitJump">
              <label :for="`${panelId}-input`">跳至</label>
              <input
                :id="`${panelId}-input`"
                v-model="pageInput"
                type="text"
                inputmode="numeric"
                autocomplete="off"
                aria-label="输入页码"
                :aria-invalid="pageInput !== '' && !inputValid"
                @input="pageInput = pageInput.replace(/\D/g, '')"
                @focus="($event.target as HTMLInputElement).select()"
              />
              <span>页</span>
              <button type="submit" :disabled="!inputValid">前往</button>
            </form>

            <div class="media-page-picker__scroll custom-scrollbar" role="listbox" aria-label="可选页码" @keydown="onGridKeydown">
              <div class="media-page-picker__grid">
                <button
                  v-for="item in pages"
                  :key="item"
                  type="button"
                  role="option"
                  :data-page="item"
                  :aria-selected="item === page"
                  :aria-current="item === page ? 'page' : undefined"
                  :tabindex="item === page ? 0 : -1"
                  @click="choosePage(item)"
                >
                  <span>{{ item }}</span>
                  <Check v-if="item === page" :size="12" :stroke-width="3" aria-hidden="true" />
                </button>
              </div>
            </div>
          </section>
        </Transition>
      </div>

      <button
        type="button"
        class="media-pagination__icon"
        aria-label="下一页"
        title="下一页"
        :disabled="disabled || page >= pageCount"
        @click="choosePage(page + 1)"
      >
        <ChevronRight :size="18" aria-hidden="true" />
      </button>
      <button
        type="button"
        class="media-pagination__icon media-pagination__edge"
        aria-label="最后一页"
        title="最后一页"
        :disabled="disabled || page >= pageCount"
        @click="choosePage(pageCount)"
      >
        <ChevronsRight :size="17" aria-hidden="true" />
      </button>
    </div>
  </nav>
</template>

<style scoped>
.media-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  width: 100%;
  padding: 18px 2px 2px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
}

.media-pagination__summary {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin: 0;
  color: rgba(255, 255, 255, 0.38);
  font-size: 12px;
}

.media-pagination__summary strong { color: rgba(255, 255, 255, 0.76); }
.media-pagination__summary span::before { content: '·'; margin-right: 7px; color: rgba(255, 255, 255, 0.18); }
.media-pagination__controls { display: flex; align-items: center; justify-content: flex-end; gap: 6px; }

.media-pagination__icon,
.media-page-picker__trigger {
  height: 40px;
  border: 1px solid rgba(255, 255, 255, 0.09);
  border-radius: 11px;
  color: rgba(255, 255, 255, 0.62);
  background: rgba(255, 255, 255, 0.045);
  transition: border-color 160ms ease, background 160ms ease, color 160ms ease, transform 160ms ease;
}

.media-pagination__icon { display: grid; width: 40px; place-items: center; }
.media-pagination__icon:hover:not(:disabled),
.media-page-picker__trigger:hover:not(:disabled) {
  border-color: rgba(var(--color-accent), 0.36);
  color: white;
  background: rgba(var(--color-accent), 0.13);
}

.media-pagination button:focus-visible { outline: 2px solid rgba(var(--color-accent), 0.85); outline-offset: 2px; }
.media-pagination button:disabled { cursor: default; opacity: 0.32; }
.media-page-picker { position: relative; }

.media-page-picker__trigger {
  min-width: 150px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  padding: 0 14px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
  font-weight: 700;
}

.media-page-picker__trigger strong { color: rgb(var(--color-accent-glow)); font-size: 14px; }
.media-page-picker__trigger svg { transition: transform 180ms ease; }
.media-page-picker.is-open .media-page-picker__trigger svg { transform: rotate(180deg); }

.media-page-picker__panel {
  position: absolute;
  z-index: 60;
  right: 50%;
  bottom: calc(100% + 10px);
  width: 320px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 17px;
  background: rgba(var(--color-sidebar), 0.97);
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.58), inset 0 1px rgba(255, 255, 255, 0.055);
  transform: translateX(50%);
  backdrop-filter: blur(24px);
}

.media-page-picker__panel > header {
  min-height: 63px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 11px 14px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.07);
  background: rgba(255, 255, 255, 0.025);
}

.media-page-picker__panel > header strong,
.media-page-picker__panel > header small { display: block; }
.media-page-picker__panel > header strong { color: rgba(255, 255, 255, 0.9); font-size: 14px; }
.media-page-picker__panel > header small { margin-top: 3px; color: rgba(255, 255, 255, 0.35); font-size: 10px; }
.media-page-picker__panel > header > span { padding: 4px 8px; border-radius: 999px; color: rgb(var(--color-accent-glow)); background: rgba(var(--color-accent), 0.12); font-size: 10px; font-weight: 800; }

.media-page-picker__jump {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.065);
  color: rgba(255, 255, 255, 0.45);
  font-size: 11px;
}

.media-page-picker__jump label { font-weight: 800; }
.media-page-picker__jump input {
  width: 56px;
  height: 32px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 9px;
  outline: 0;
  color: white;
  background: rgba(0, 0, 0, 0.26);
  font-size: 12px;
  font-weight: 800;
  text-align: center;
}
.media-page-picker__jump input:focus { border-color: rgba(var(--color-accent), 0.7); box-shadow: 0 0 0 3px rgba(var(--color-accent), 0.12); }
.media-page-picker__jump input[aria-invalid="true"] { border-color: rgba(248, 113, 113, 0.65); color: rgb(254, 202, 202); }
.media-page-picker__jump button { height: 32px; margin-left: auto; border: 1px solid rgba(var(--color-accent), 0.4); border-radius: 9px; padding: 0 12px; color: white; background: rgba(var(--color-accent), 0.8); font-size: 11px; font-weight: 800; }

.media-page-picker__scroll { max-height: 245px; overflow-y: auto; overscroll-behavior: contain; padding: 10px; }
.media-page-picker__grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; }
.media-page-picker__grid button { height: 36px; display: flex; align-items: center; justify-content: center; gap: 3px; border: 1px solid transparent; border-radius: 9px; color: rgba(255, 255, 255, 0.58); background: rgba(255, 255, 255, 0.04); font-size: 11px; font-weight: 700; }
.media-page-picker__grid button:hover,
.media-page-picker__grid button:focus-visible { border-color: rgba(var(--color-accent), 0.42); color: white; background: rgba(var(--color-accent), 0.13); }
.media-page-picker__grid button[aria-selected="true"] { border-color: rgba(var(--color-accent-glow), 0.28); color: white; background: rgb(var(--color-accent)); box-shadow: 0 5px 15px rgba(var(--color-accent), 0.2); }

.page-picker-enter-active,
.page-picker-leave-active { transition: opacity 150ms ease, transform 180ms var(--ease-out-expo); }
.page-picker-enter-from,
.page-picker-leave-to { opacity: 0; transform: translateX(50%) translateY(7px) scale(0.98); }

@media (max-width: 640px) {
  .media-pagination { align-items: stretch; flex-direction: column; gap: 12px; }
  .media-pagination__summary { justify-content: center; }
  .media-pagination__controls { justify-content: center; }
  .media-pagination__edge { display: none; }
  .media-page-picker__trigger { min-width: 142px; }
  .media-page-picker__panel { position: fixed; right: 12px; bottom: 12px; left: 12px; width: auto; transform: none; }
  .page-picker-enter-from,
  .page-picker-leave-to { transform: translateY(9px) scale(0.98); }
  .media-page-picker__scroll { max-height: 42vh; }
}

@media (prefers-reduced-motion: reduce) {
  .media-pagination *, .page-picker-enter-active, .page-picker-leave-active { transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
}
</style>
