import { ref, watch, onScopeDispose } from 'vue'
import { authState } from '../auth'
import { listApprovals, assistantErrorText } from '../utils/assistantApi'
import type { ProposalDTO } from '../types/assistant'
export function useAssistantApprovals() {
  const items = ref<ProposalDTO[]>([]), pendingCount = ref(0), tab = ref<'pending' | 'history'>('pending'), busy = ref(false), error = ref(''), hasMore = ref(false)
  let generation = 0, alive = true, request = new AbortController()
  async function refresh(append = false) {
    if (!alive || !authState.token || !authState.user?.is_admin) return
    const current = ++generation; request.abort(); request = new AbortController(); busy.value = true; error.value = ''
    const offset = append ? items.value.length : 0
    try {
      const controller = request, currentTab = tab.value
      const page = await listApprovals(currentTab, { offset, signal: controller.signal })
      if (!append) {
        const keep = items.value.length
        while (page.has_more && page.items.length < keep) {
          const next = await listApprovals(currentTab, { offset: page.items.length, signal: controller.signal })
          if (!next.items.length) { page.has_more = false; break }
          page.items.push(...next.items); page.has_more = next.has_more
        }
      }
      if (!alive || current !== generation) return
      items.value = append ? [...new Map([...items.value, ...page.items].map(x => [x.id, x])).values()] : page.items
      pendingCount.value = page.pending_count; hasMore.value = page.has_more
    } catch (e) { if (alive && current === generation && !request.signal.aborted) error.value = assistantErrorText(e) }
    finally { if (alive && current === generation) busy.value = false }
  }
  function dispose() { alive = false; generation++; request.abort(); clearInterval(timer); window.removeEventListener('he-assistant-approval-changed', changed) }
  const changed = () => { void refresh() }
  const timer = setInterval(changed, 15000)
  window.addEventListener('he-assistant-approval-changed', changed)
  watch(() => [authState.token, authState.user?.id, authState.user?.is_admin], () => { generation++; request.abort(); items.value = []; pendingCount.value = 0; hasMore.value = false; busy.value = false; error.value = ''; void refresh() }, { immediate: true })
  watch(tab, changed)
  onScopeDispose(dispose)
  return { items, pendingCount, tab, busy, error, hasMore, refresh, loadMore: () => refresh(true), dispose }
}
