import { ref } from 'vue'
import axios from 'axios'
import type { PawchivePage, PawchivePost, PawchiveScope } from '../types/pawchive'
import { fetchPawchivePosts, pawchiveError } from '../utils/pawchiveApi'

const initialScope = (): PawchiveScope => ({ query: '', service: '', creatorId: '', tag: '', mediaType: 'all' })

export function usePawchiveBrowse() {
  const scope = ref<PawchiveScope>(initialScope())
  const posts = ref<PawchivePost[]>([])
  const nextCursor = ref<string | null>(null)
  const hasMore = ref(false)
  const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const loadingMore = ref(false)
  const error = ref('')
  const warnings = ref<string[]>([])
  let version = 0
  let controller: AbortController | null = null

  const applyPage = (page: PawchivePage, append: boolean) => {
    const seen = new Set(append ? posts.value.map(post => post.post_key) : [])
    const fresh = page.items.filter(post => {
      if (seen.has(post.post_key)) return false
      seen.add(post.post_key)
      return true
    })
    posts.value = append ? [...posts.value, ...fresh] : fresh
    nextCursor.value = page.next_cursor
    hasMore.value = page.has_more
    warnings.value = page.warnings
  }

  const setScope = async (next: PawchiveScope) => {
    version++
    controller?.abort()
    controller = new AbortController()
    const requestedVersion = version
    scope.value = { ...next }
    posts.value = []
    nextCursor.value = null
    hasMore.value = false
    error.value = ''
    status.value = 'loading'
    try {
      const page = await fetchPawchivePosts(scope.value, '', controller.signal)
      if (requestedVersion !== version) return
      applyPage(page, false)
      status.value = 'ready'
    } catch (cause) {
      if (requestedVersion !== version || axios.isCancel(cause)) return
      error.value = pawchiveError(cause)
      status.value = 'error'
    }
  }

  const loadMore = async () => {
    if (!hasMore.value || !nextCursor.value || loadingMore.value) return
    const requestedVersion = version
    const signal = controller?.signal
    loadingMore.value = true
    error.value = ''
    try {
      const page = await fetchPawchivePosts(scope.value, nextCursor.value, signal)
      if (requestedVersion !== version) return
      applyPage(page, true)
    } catch (cause) {
      if (requestedVersion !== version || axios.isCancel(cause)) return
      error.value = pawchiveError(cause)
    } finally {
      if (requestedVersion === version) loadingMore.value = false
    }
  }

  const dispose = () => {
    version++
    controller?.abort()
  }

  return { scope, posts, nextCursor, hasMore, status, loadingMore, error, warnings, setScope, loadMore, dispose }
}
