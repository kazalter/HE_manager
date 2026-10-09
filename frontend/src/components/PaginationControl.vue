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
  padding: 20px 0 4px;
  border-top: 1px solid rgb(var(--color-line));
}

.media-pagination__summary {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
  color: rgb(var(--color-subtle));
  font-size: 0.8125rem;
  font-variant-numeric: tabular-nums;
}

.media-pagination__summary strong { color: rgb(var(--color-ink)); font-weight: 500; }
.media-pagination__summary span::before { content: '·'; margin-right: 8px; color: rgb(var(--color-faint)); }
.media-pagination__controls { display: flex; align-items: center; justify-content: flex-end; gap: 4px; }

.media-pagination__icon,
.media-page-picker__trigger {
  height: 36px;
  border: 1px solid rgb(var(--color-line));
  border-radius: 10px;
  color: rgb(var(--color-muted));
  background: rgb(var(--color-surface-2));
  transition: border-color 150ms var(--ease-out), background-color 150ms var(--ease-out), color 150ms var(--ease-out);
}

.media-pagination__icon { display: grid; width: 36px; place-items: center; }
.media-pagination__icon:hover:not(:disabled),
.media-page-picker__trigger:hover:not(:disabled) {
  border-color: rgb(var(--color-line-strong));
  color: rgb(var(--color-ink));
  background: rgb(var(--color-surface-3));
}

.media-pagination button:focus-visible { outline: 2px solid rgb(var(--color-accent)); outline-offset: 2px; }
.media-pagination button:disabled { cursor: default; opacity: 0.4; }
.media-page-picker { position: relative; }

.media-page-picker__trigger {
  min-width: 136px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 12px;
  font-size: 0.8125rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
}

.media-page-picker__trigger strong { color: rgb(var(--color-ink)); font-weight: 600; }
.media-page-picker__trigger svg { color: rgb(var(--color-subtle)); transition: transform 180ms var(--ease-out); }
.media-page-picker.is-open .media-page-picker__trigger { border-color: rgb(var(--color-accent) / 0.6); color: rgb(var(--color-ink)); }
.media-page-picker.is-open .media-page-picker__trigger svg { transform: rotate(180deg); }

.media-page-picker__panel {
  position: absolute;
  z-index: 60;
  right: 50%;
  bottom: calc(100% + 8px);
  width: 312px;
  overflow: hidden;
  border: 1px solid rgb(var(--color-line-strong));
  border-radius: 14px;
  background: rgb(var(--color-surface-3));
  box-shadow: var(--shadow-pop);
  transform: translateX(50%);
}

.media-page-picker__panel > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid rgb(var(--color-line-strong) / 0.7);
}

.media-page-picker__panel > header strong,
.media-page-picker__panel > header small { display: block; }
.media-page-picker__panel > header strong { color: rgb(var(--color-ink)); font-size: 0.875rem; font-weight: 600; }
.media-page-picker__panel > header small { margin-top: 2px; color: rgb(var(--color-subtle)); font-size: 0.75rem; font-variant-numeric: tabular-nums; }
.media-page-picker__panel > header > span { padding: 2px 8px; border-radius: 6px; color: rgb(var(--color-muted)); background: rgb(var(--color-surface-2)); font-size: 0.75rem; font-weight: 500; font-variant-numeric: tabular-nums; }

.media-page-picker__jump {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid rgb(var(--color-line-strong) / 0.7);
  color: rgb(var(--color-subtle));
  font-size: 0.8125rem;
}

.media-page-picker__jump label { font-weight: 500; color: rgb(var(--color-muted)); }
.media-page-picker__jump input {
  width: 60px;
  height: 32px;
  border: 1px solid rgb(var(--color-line-strong));
  border-radius: 8px;
  outline: 0;
  color: rgb(var(--color-ink));
  background: rgb(var(--color-surface-2));
  font-size: 0.8125rem;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  text-align: center;
}
.media-page-picker__jump input:focus { border-color: rgb(var(--color-accent)); box-shadow: 0 0 0 3px rgb(var(--color-accent) / 0.25); }
.media-page-picker__jump input[aria-invalid="true"] { border-color: rgb(var(--color-danger) / 0.7); color: rgb(var(--color-danger)); }
.media-page-picker__jump button { height: 32px; margin-left: auto; border-radius: 8px; padding: 0 12px; color: rgb(var(--color-on-accent)); background: rgb(var(--color-accent)); font-size: 0.8125rem; font-weight: 500; }
.media-page-picker__jump button:hover:not(:disabled) { background: rgb(var(--color-accent) / 0.9); }

.media-page-picker__scroll { max-height: 244px; overflow-y: auto; overscroll-behavior: contain; padding: 8px; }
.media-page-picker__grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 4px; }
.media-page-picker__grid button { height: 36px; display: flex; align-items: center; justify-content: center; gap: 3px; border: 1px solid transparent; border-radius: 8px; color: rgb(var(--color-muted)); background: transparent; font-size: 0.8125rem; font-weight: 500; font-variant-numeric: tabular-nums; transition: background-color 100ms var(--ease-out), color 100ms var(--ease-out); }
.media-page-picker__grid button:hover { color: rgb(var(--color-ink)); background: rgb(var(--color-line-strong) / 0.6); }
.media-page-picker__grid button:focus-visible { outline-offset: -2px; color: rgb(var(--color-ink)); }
.media-page-picker__grid button[aria-selected="true"] { color: rgb(var(--color-on-accent)); background: rgb(var(--color-accent)); }

.page-picker-enter-active,
.page-picker-leave-active { transition: opacity 150ms var(--ease-out), transform 180ms var(--ease-out); }
.page-picker-enter-from,
.page-picker-leave-to { opacity: 0; transform: translateX(50%) translateY(6px); }

@media (max-width: 640px) {
  .media-pagination { align-items: stretch; flex-direction: column; gap: 12px; }
  .media-pagination__summary { justify-content: center; }
  .media-pagination__controls { justify-content: center; gap: 8px; }
  .media-pagination__edge { display: none; }
  .media-pagination__icon { width: 44px; height: 44px; }
  .media-page-picker__trigger { min-width: 148px; height: 44px; }
  .media-page-picker__panel { position: fixed; right: 12px; bottom: calc(var(--he-nav-height, 80px) + env(safe-area-inset-bottom) + 12px); left: 12px; width: auto; transform: none; }
  .page-picker-enter-from,
  .page-picker-leave-to { transform: translateY(8px); }
  .media-page-picker__scroll { max-height: 42vh; }
  .media-page-picker__grid button { height: 44px; }
}

@media (prefers-reduced-motion: reduce) {
  .media-pagination *, .page-picker-enter-active, .page-picker-leave-active { transition-duration: 0.01ms !important; scroll-behavior: auto !important; }
}
</style>
