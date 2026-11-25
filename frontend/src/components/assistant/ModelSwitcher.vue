<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { Check, ChevronUp, Cpu, Plus, Trash2 } from 'lucide-vue-next'
import { UiButton } from '../ui'
import type {
  AssistantModelConfigDTO,
  AssistantModelPresetDTO,
  AssistantModelUpdateRequest,
} from '../../types/assistant'

const props = withDefaults(defineProps<{
  modelConfig: AssistantModelConfigDTO | null
  busy?: boolean
  disabled?: boolean
  error?: string
  compact?: boolean
}>(), {
  busy: false,
  disabled: false,
  error: '',
  compact: false,
})

const emit = defineEmits<{
  selectPreset: [presetId: string]
  deletePreset: [presetId: string]
  saveCustom: [payload: AssistantModelUpdateRequest]
  toggleThinking: [thinkingDisabled: boolean]
}>()

const rootRef = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)
const menuOpen = ref(false)
const customOpen = ref(false)
const panelId = `assistant-model-${useId()}`

const customModel = ref('')
const customLabel = ref('')
const customBaseUrl = ref('')
const customApiKey = ref('')
const customThinkingDisabled = ref(true)

const currentLabel = computed(() => {
  const cfg = props.modelConfig
  if (!cfg) return '切换模型'
  return cfg.display_model || cfg.model || '切换模型'
})

function hostLabel(url: string) {
  try {
    return new URL(url).host || url
  } catch {
    return url
  }
}

function isPresetActive(preset: AssistantModelPresetDTO) {
  const cfg = props.modelConfig
  if (!cfg) return false
  return (
    preset.model === cfg.model &&
    preset.base_url.replace(/\/+$/, '') === cfg.base_url.replace(/\/+$/, '')
  )
}

function openCustomForm() {
  customOpen.value = !customOpen.value
  if (customOpen.value && props.modelConfig) {
    customModel.value = props.modelConfig.model
    customLabel.value = ''
    customBaseUrl.value = props.modelConfig.base_url
    customApiKey.value = ''
    customThinkingDisabled.value = props.modelConfig.thinking_disabled
  }
}

function choosePreset(preset: AssistantModelPresetDTO) {
  if (props.disabled || props.busy) return
  menuOpen.value = false
  customOpen.value = false
  if (!isPresetActive(preset)) {
    emit('selectPreset', preset.id)
  }
}

function submitCustom() {
  if (props.disabled || props.busy) return
  const model = customModel.value.trim()
  if (!model) return
  emit('saveCustom', {
    model,
    display_model: customLabel.value.trim() || model,
    base_url: customBaseUrl.value.trim() || undefined,
    api_key: customApiKey.value.trim() || undefined,
    thinking_disabled: customThinkingDisabled.value,
    save_preset: true,
  })
}

watch(
  () => props.modelConfig,
  next => {
    if (next && customOpen.value && !props.error) {
      customOpen.value = false
      customApiKey.value = ''
    }
  },
)

const onPointerDown = (event: PointerEvent) => {
  if (menuOpen.value && !rootRef.value?.contains(event.target as Node)) {
    menuOpen.value = false
    customOpen.value = false
  }
}

const onKeydown = (event: KeyboardEvent) => {
  if (menuOpen.value && event.key === 'Escape') {
    event.stopPropagation()
    menuOpen.value = false
    customOpen.value = false
    triggerRef.value?.focus()
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', onPointerDown)
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onPointerDown)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div ref="rootRef" class="relative min-w-0">
    <button
      ref="triggerRef"
      type="button"
      class="inline-flex items-center gap-1.5 rounded-xl border px-2.5 py-1.5 text-xs font-medium transition-colors duration-150 focus-ring disabled:cursor-not-allowed disabled:opacity-55"
      :class="[
        compact ? 'max-w-[168px]' : 'max-w-[220px]',
        menuOpen
          ? 'border-accent/45 bg-accent/14 text-ink'
          : 'border-line bg-surface/85 text-muted hover:border-line-strong hover:bg-surface-3 hover:text-ink',
      ]"
      :aria-expanded="menuOpen"
      :aria-controls="panelId"
      aria-haspopup="dialog"
      :title="`当前模型：${currentLabel}（点击切换）`"
      :disabled="busy"
      @click="menuOpen = !menuOpen"
    >
      <Cpu :size="13" class="shrink-0 text-accent" aria-hidden="true" />
      <span class="min-w-0 truncate">{{ currentLabel }}</span>
      <ChevronUp
        :size="13"
        class="shrink-0 text-subtle transition-transform duration-150"
        :class="menuOpen ? 'rotate-180' : ''"
        aria-hidden="true"
      />
    </button>

    <Transition name="he-pop">
      <div
        v-if="menuOpen"
        :id="panelId"
        role="dialog"
        aria-label="切换媒体库管家模型"
        class="custom-scrollbar absolute bottom-full left-0 z-40 mb-2 max-h-[min(420px,62vh)] w-[min(340px,calc(100vw-2rem))] overflow-y-auto rounded-2xl border border-line-strong glass-elevated p-2.5 shadow-pop"
      >
        <div class="flex items-center justify-between gap-2 border-b border-line/70 px-1.5 pb-2">
          <span class="text-xs font-semibold text-ink">切换模型</span>
          <span v-if="modelConfig?.base_url" class="truncate text-[11px] text-subtle">
            {{ hostLabel(modelConfig.base_url) }}
          </span>
        </div>

        <p v-if="error" role="alert" class="mt-2 rounded-xl border border-danger/30 bg-danger/10 px-2.5 py-1.5 text-xs text-danger">
          {{ error }}
        </p>

        <div v-if="modelConfig?.presets?.length" class="mt-2 space-y-1">
          <div
            v-for="preset in modelConfig.presets"
            :key="preset.id"
            class="flex items-center gap-1"
          >
            <button
              type="button"
              :disabled="disabled || busy"
              class="flex min-w-0 flex-1 items-center justify-between gap-2 rounded-xl border px-2.5 py-2 text-left transition-colors duration-150 focus-ring-inset disabled:cursor-not-allowed disabled:opacity-55"
              :class="isPresetActive(preset)
                ? 'border-accent/35 bg-accent/12 text-ink'
                : 'border-transparent text-muted hover:bg-surface-2/85 hover:text-ink'"
              @click="choosePreset(preset)"
            >
              <span class="min-w-0 flex-1">
                <span class="block truncate text-xs font-medium text-ink">{{ preset.label }}</span>
                <span class="mt-0.5 block truncate text-[11px] text-subtle">
                  {{ preset.model }} · {{ hostLabel(preset.base_url) }}
                </span>
              </span>
              <Check v-if="isPresetActive(preset)" :size="14" class="shrink-0 text-accent" aria-hidden="true" />
            </button>
            <button
              v-if="preset.custom && !isPresetActive(preset)"
              type="button"
              class="grid size-8 shrink-0 place-items-center rounded-lg text-subtle transition-colors hover:bg-danger/12 hover:text-danger focus-ring"
              title="移除预设"
              :aria-label="`移除预设 ${preset.label}`"
              :disabled="disabled || busy"
              @click="emit('deletePreset', preset.id)"
            >
              <Trash2 :size="13" aria-hidden="true" />
            </button>
          </div>
        </div>
        <p v-else class="px-2 py-3 text-center text-xs text-subtle">
          {{ modelConfig ? '暂无预设，可在下方添加模型' : '模型配置未加载或暂不可用' }}
        </p>

        <div v-if="modelConfig" class="mt-2 flex items-center justify-between gap-2 rounded-xl border border-line/70 bg-surface-2/50 px-2.5 py-2">
          <span class="text-xs text-muted">深度思考模式</span>
          <button
            type="button"
            role="switch"
            :aria-checked="!modelConfig.thinking_disabled"
            :disabled="disabled || busy"
            class="inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[11px] font-medium transition-colors focus-ring disabled:opacity-55"
            :class="!modelConfig.thinking_disabled
              ? 'border-accent/45 bg-accent/15 text-accent-glow'
              : 'border-line bg-surface text-subtle hover:text-ink'"
            @click="emit('toggleThinking', !modelConfig.thinking_disabled)"
          >
            {{ !modelConfig.thinking_disabled ? '已开启' : '已关闭' }}
          </button>
        </div>

        <div class="mt-2 border-t border-line/70 pt-2">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-2 rounded-xl px-2.5 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-ring"
            :aria-expanded="customOpen"
            @click="openCustomForm"
          >
            <span class="inline-flex items-center gap-1.5">
              <Plus :size="13" class="text-accent" aria-hidden="true" />
              <span>自定义 / 添加模型</span>
            </span>
          </button>

          <div v-if="customOpen" class="mt-2 space-y-2 rounded-xl border border-line/80 bg-surface-2/65 p-2.5">
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-subtle">模型 ID *</span>
              <input
                v-model="customModel"
                type="text"
                class="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs text-ink outline-none focus:border-accent"
                placeholder="例如 deepseek-v4-pro / gpt-4o"
              />
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-subtle">显示名称</span>
              <input
                v-model="customLabel"
                type="text"
                class="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs text-ink outline-none focus:border-accent"
                placeholder="留空则使用模型 ID"
              />
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-subtle">API 地址 (HTTPS)</span>
              <input
                v-model="customBaseUrl"
                type="url"
                class="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs text-ink outline-none focus:border-accent"
                placeholder="https://api.deepseek.com/v1"
              />
            </label>
            <label class="block">
              <span class="mb-1 block text-[11px] font-medium text-subtle">API Key</span>
              <input
                v-model="customApiKey"
                type="password"
                autocomplete="new-password"
                class="w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs text-ink outline-none focus:border-accent"
                placeholder="留空沿用当前密钥"
              />
            </label>
            <label class="flex cursor-pointer items-center gap-2 pt-0.5 text-[11px] text-muted">
              <input v-model="customThinkingDisabled" type="checkbox" class="rounded border-line accent-accent" />
              <span>禁用思考模式 (thinking: disabled)</span>
            </label>
            <div class="flex justify-end gap-1.5 pt-1">
              <UiButton size="sm" variant="ghost" class="min-h-7 px-2 text-xs" @click="customOpen = false">取消</UiButton>
              <UiButton
                size="sm"
                variant="primary"
                class="min-h-7 px-2.5 text-xs"
                :loading="busy"
                :disabled="disabled || !customModel.trim()"
                @click="submitCustom"
              >
                保存并切换
              </UiButton>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
