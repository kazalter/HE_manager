<script setup lang="ts">
withDefaults(defineProps<{ message: string; overlay?: boolean; urgent?: boolean }>(), { overlay: false, urgent: false })
</script>
<template>
 <div :role="urgent ? 'alert' : 'status'" :aria-live="urgent ? 'assertive' : 'polite'" class="rounded-2xl border px-4 py-2.5 text-body shadow-pop" :class="overlay ? 'border-white/10 bg-black/85 text-white' : 'border-line-strong bg-surface-3 text-ink'">{{ message }}</div>
</template>
