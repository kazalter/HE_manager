import { defineAsyncComponent } from 'vue'

// Keep the large detail viewer—and its optional media players—out of route
// chunks until a user actually opens a media item.
export const AsyncMediaDetail = defineAsyncComponent(() => import('./MediaDetail.vue'))
