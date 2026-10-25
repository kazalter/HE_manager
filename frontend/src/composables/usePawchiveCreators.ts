import { computed, ref } from 'vue'
import axios from 'axios'
import type { PawchiveCreatorPage, PawchiveCreatorSort } from '../types/pawchive'
import { fetchPawchiveCreators, pawchiveError } from '../utils/pawchiveApi'

export function usePawchiveCreators() {
  const query = ref('')
  const service = ref('')
  const sort = ref<PawchiveCreatorSort>('popular')
  const page = ref(1)
  const result = ref<PawchiveCreatorPage | null>(null)
  const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const error = ref('')
  const items = computed(() => result.value?.items || [])
  let version = 0
  let controller: AbortController | null = null

  const load = async () => {
    const request = ++version
    controller?.abort()
    controller = new AbortController()
    status.value = 'loading'
    error.value = ''
    try {
      const data = await fetchPawchiveCreators(query.value, service.value, sort.value, page.value, controller.signal)
      if (request !== version) return
      result.value = data
      page.value = data.page
      status.value = 'ready'
    } catch (cause) {
      if (request !== version || axios.isCancel(cause)) return
      error.value = pawchiveError(cause)
      status.value = 'error'
    }
  }
  const search = async (next: { query?: string; service?: string; sort?: PawchiveCreatorSort; page?: number }) => {
    if (next.query !== undefined) query.value = next.query
    if (next.service !== undefined) service.value = next.service
    if (next.sort !== undefined) sort.value = next.sort
    page.value = next.page ?? 1
    // Previous results belong to the old filters, not the current query.
    result.value = null
    await load()
  }
  const dispose = () => { version++; controller?.abort() }
  return { query, service, sort, page, result, items, status, error, load, search, dispose }
}
