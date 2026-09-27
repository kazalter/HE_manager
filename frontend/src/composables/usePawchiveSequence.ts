import { computed, ref } from 'vue'
import axios from 'axios'
import type { PawchiveAttachment, PawchivePost, PawchiveScope } from '../types/pawchive'
import { fetchPawchivePost, fetchPawchivePosts, pawchiveError } from '../utils/pawchiveApi'

interface Position { postKey: string; attachmentKey: string }
interface CurrentItem {
  post: PawchivePost
  attachment: PawchiveAttachment
  index: number
  total: number
}

export function usePawchiveSequence() {
  const active = ref(false)
  const busy = ref(false)
  const error = ref('')
  const notice = ref('')
  const ended = ref(false)
  const current = ref<CurrentItem | null>(null)
  const history = ref<Position[]>([])
  const scope = ref<PawchiveScope>({ query: '', service: '', creatorId: '', tag: '', mediaType: 'all' })
  const posts = ref<PawchivePost[]>([])
  const cursor = ref<string | null>(null)
  const hasMore = ref(false)
  const scopeLabel = computed(() => scope.value.creatorId
    ? `创作者 ${scope.value.service} · ${scope.value.creatorId}`
    : scope.value.query ? `搜索：${scope.value.query}` : '最新帖子')
  const detailCache = new Map<string, PawchivePost>()
  let version = 0
  let controller: AbortController | null = null
  let postIndex = -1
  let searchIndex: number | null = null

  const playable = (post: PawchivePost) => post.attachments.filter(attachment =>
    attachment.availability === 'playable' &&
    (scope.value.mediaType === 'all' || attachment.media_type === scope.value.mediaType))

  const detailAt = async (index: number): Promise<PawchivePost> => {
    const summary = posts.value[index]
    if (!summary) throw new Error('missing post')
    const cached = detailCache.get(summary.post_key)
    if (cached) return cached
    const detail = await fetchPawchivePost(summary, controller?.signal)
    detailCache.set(summary.post_key, detail)
    if (detailCache.size > 30) detailCache.delete(detailCache.keys().next().value!)
    return detail
  }

  const setCurrent = (index: number, post: PawchivePost, attachmentIndex: number, saveHistory: boolean) => {
    const attachments = playable(post)
    const next = attachments[attachmentIndex]
    if (!next) return false
    if (saveHistory && current.value) history.value.push({ postKey: current.value.post.post_key, attachmentKey: current.value.attachment.attachment_key })
    notice.value = current.value && current.value.post.post_key !== post.post_key ? '已进入下一篇帖子' : ''
    current.value = { post, attachment: next, index: attachmentIndex, total: attachments.length }
    postIndex = index
    searchIndex = null
    ended.value = false
    error.value = ''
    return true
  }

  const loadPage = async () => {
    if (!hasMore.value || !cursor.value) return false
    const page = await fetchPawchivePosts(scope.value, cursor.value, controller?.signal)
    const seen = new Set(posts.value.map(post => post.post_key))
    posts.value.push(...page.items.filter(post => {
      if (seen.has(post.post_key)) return false
      seen.add(post.post_key)
      return true
    }))
    cursor.value = page.next_cursor
    hasMore.value = page.has_more
    return true
  }

  const next = async () => {
    if (!active.value || busy.value || ended.value) return
    busy.value = true
    error.value = ''
    const requestedVersion = version
    try {
      if (current.value && searchIndex === null) {
        const inPost = playable(current.value.post)
        if (current.value.index + 1 < inPost.length) {
          setCurrent(postIndex, current.value.post, current.value.index + 1, true)
          return
        }
      }
      let index = searchIndex ?? (postIndex >= 0 ? postIndex + 1 : 0)
      let checked = 0
      let pages = 0
      while (checked < 10 && pages <= 2) {
        if (requestedVersion !== version) return
        if (index >= posts.value.length) {
          if (!hasMore.value) { ended.value = true; error.value = '已到当前范围末尾'; return }
          if (pages >= 2) break
          await loadPage()
          pages++
          if (requestedVersion !== version) return
          if (index >= posts.value.length && !hasMore.value) { ended.value = true; error.value = '已到当前范围末尾'; return }
          if (index >= posts.value.length) continue
        }
        let detail: PawchivePost
        try { detail = await detailAt(index) }
        catch (cause) {
          if (axios.isAxiosError(cause) && cause.response?.status === 404) { index++; checked++; continue }
          throw cause
        }
        if (requestedVersion !== version) return
        checked++
        if (playable(detail).length) {
          setCurrent(index, detail, 0, true)
          return
        }
        index++
      }
      searchIndex = index
      error.value = '本段暂无可播放媒体，点击“下一项”继续查找。'
    } catch (cause) {
      if (requestedVersion === version && !axios.isCancel(cause)) {
        searchIndex = searchIndex ?? (postIndex >= 0 ? postIndex + 1 : 0)
        error.value = pawchiveError(cause)
      }
    } finally {
      if (requestedVersion === version) busy.value = false
    }
  }

  const previous = async () => {
    if (!active.value || busy.value || !history.value.length) return
    busy.value = true
    const requestedVersion = version
    const position = history.value[history.value.length - 1]!
    try {
      const index = posts.value.findIndex(post => post.post_key === position.postKey)
      if (index < 0) return
      const detail = await detailAt(index)
      if (requestedVersion !== version) return
      const attachmentIndex = playable(detail).findIndex(item => item.attachment_key === position.attachmentKey)
      if (attachmentIndex >= 0) {
        history.value.pop()
        setCurrent(index, detail, attachmentIndex, false)
      }
    } catch (cause) {
      if (requestedVersion === version && !axios.isCancel(cause)) error.value = pawchiveError(cause)
    } finally {
      if (requestedVersion === version) busy.value = false
    }
  }

  const open = async (index: number, initialPosts: PawchivePost[], nextCursor: string | null,
                      more: boolean, browseScope: PawchiveScope) => {
    close()
    active.value = true
    busy.value = true
    scope.value = { ...browseScope }
    posts.value = [...initialPosts]
    cursor.value = nextCursor
    hasMore.value = more
    searchIndex = index
    const requestedVersion = version
    try {
      const detail = await detailAt(index)
      if (requestedVersion !== version) return
      if (playable(detail).length) setCurrent(index, detail, 0, false)
      else { busy.value = false; await next() }
    } catch (cause) {
      if (requestedVersion === version && !axios.isCancel(cause)) error.value = pawchiveError(cause)
    } finally {
      if (requestedVersion === version) busy.value = false
    }
  }

  const close = () => {
    version++
    controller?.abort()
    controller = new AbortController()
    active.value = false
    current.value = null
    history.value = []
    detailCache.clear()
    busy.value = false
    error.value = ''
    notice.value = ''
    ended.value = false
    postIndex = -1
    searchIndex = null
  }

  return { active, busy, error, notice, ended, current, history, scopeLabel, open, next, previous, close }
}
