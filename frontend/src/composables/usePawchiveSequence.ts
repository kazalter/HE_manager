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
type SearchResult =
  | { kind: 'found'; index: number; detail: PawchivePost }
  | { kind: 'end' }
  | { kind: 'paused'; index: number }
  | { kind: 'stale' }

// Media refs live 12h on the backend; refetch well before cached ones expire.
const DETAIL_MAX_AGE = 6 * 3600 * 1000
// Posts with known-empty counts cost nothing to skip, so a search may walk
// several pages; posts whose counts are unknown still need a detail request.
const SEARCH_PAGE_LIMIT = 8
const PREFETCH_PAGE_LIMIT = 3
const DETAIL_CHECK_LIMIT = 10

const isNotFound = (cause: unknown) => axios.isAxiosError(cause) && cause.response?.status === 404
const isTransient = (cause: unknown) => axios.isAxiosError(cause) && !axios.isCancel(cause) &&
  (!cause.response || [502, 503, 504].includes(cause.response.status))

export function usePawchiveSequence() {
  const active = ref(false)
  const busy = ref(false)
  const error = ref('')
  const notice = ref('')
  const ended = ref(false)
  const skipped = ref(0)
  const current = ref<CurrentItem | null>(null)
  const nextPost = ref<PawchivePost | null>(null)
  const history = ref<Position[]>([])
  const scope = ref<PawchiveScope>({ query: '', service: '', creatorId: '', tag: '', mediaType: 'all' })
  const posts = ref<PawchivePost[]>([])
  const cursor = ref<string | null>(null)
  const hasMore = ref(false)
  const scopeLabel = computed(() => scope.value.creatorId
    ? `创作者 ${scope.value.service} · ${scope.value.creatorId}`
    : scope.value.query ? `搜索：${scope.value.query}` : '最新帖子')
  const detailCache = new Map<string, { post: PawchivePost; at: number }>()
  const detailRequests = new Map<string, Promise<PawchivePost>>()
  let version = 0
  let controller: AbortController | null = null
  let postIndex = -1
  let nextPostIndex = -1
  let searchIndex: number | null = null
  let nextLookup = 0
  let pagePromise: Promise<boolean> | null = null

  const playable = (post: PawchivePost) => post.attachments.filter(attachment =>
    attachment.availability === 'playable' &&
    (scope.value.mediaType === 'all' || attachment.media_type === scope.value.mediaType))
  // Media count from the list entry; null when the backend did not report it.
  const summaryMediaCount = (post: PawchivePost): number | null => {
    if (typeof post.image_count !== 'number' || typeof post.video_count !== 'number') return null
    if (scope.value.mediaType === 'image') return post.image_count
    if (scope.value.mediaType === 'video') return post.video_count
    return post.image_count + post.video_count
  }

  const postAttachments = computed(() => current.value ? playable(current.value.post) : [])
  const nextPostAttachments = computed(() => nextPost.value ? playable(nextPost.value) : [])

  const fetchDetail = async (summary: PawchivePost) => {
    const signal = controller?.signal
    try { return await fetchPawchivePost(summary, signal) }
    catch (cause) {
      if (!isTransient(cause) || signal?.aborted) throw cause
      await new Promise(resolve => window.setTimeout(resolve, 1500))
      if (signal?.aborted) throw cause
      return fetchPawchivePost(summary, signal)
    }
  }

  const detailAt = (index: number, fresh = false): Promise<PawchivePost> => {
    const summary = posts.value[index]
    if (!summary) return Promise.reject(new Error('missing post'))
    const key = summary.post_key
    const cached = detailCache.get(key)
    if (!fresh && cached && Date.now() - cached.at < DETAIL_MAX_AGE) return Promise.resolve(cached.post)
    const pending = detailRequests.get(key)
    if (pending && !fresh) return pending
    const requestedVersion = version
    const request = fetchDetail(summary).then(detail => {
      if (requestedVersion === version) {
        detailCache.delete(key)
        detailCache.set(key, { post: detail, at: Date.now() })
        if (detailCache.size > 30) detailCache.delete(detailCache.keys().next().value!)
      }
      return detail
    }).finally(() => { if (detailRequests.get(key) === request) detailRequests.delete(key) })
    detailRequests.set(key, request)
    return request
  }

  const setCurrent = (index: number, post: PawchivePost, attachmentIndex: number, saveHistory: boolean) => {
    const attachments = playable(post)
    const next = attachments[attachmentIndex]
    if (!next) return false
    const postChanged = current.value?.post.post_key !== post.post_key
    if (saveHistory && current.value) history.value.push({ postKey: current.value.post.post_key, attachmentKey: current.value.attachment.attachment_key })
    notice.value = current.value && postChanged ? '已进入下一篇帖子' : ''
    current.value = { post, attachment: next, index: attachmentIndex, total: attachments.length }
    postIndex = index
    searchIndex = null
    ended.value = false
    error.value = ''
    if (postChanged) prepareNextPost()
    return true
  }

  const selectAttachment = (attachmentIndex: number) => {
    if (!active.value || busy.value || !current.value || !Number.isInteger(attachmentIndex)) return
    if (attachmentIndex === current.value.index) return
    setCurrent(postIndex, current.value.post, attachmentIndex, true)
  }

  const loadPage = async () => {
    if (pagePromise) return pagePromise
    if (!hasMore.value || !cursor.value) return false
    const requestedVersion = version
    const pending = (async () => {
      const page = await fetchPawchivePosts(scope.value, cursor.value!, controller?.signal)
      if (requestedVersion !== version) return false
      const seen = new Set(posts.value.map(post => post.post_key))
      posts.value.push(...page.items.filter(post => {
        if (seen.has(post.post_key)) return false
        seen.add(post.post_key)
        return true
      }))
      cursor.value = page.next_cursor
      hasMore.value = page.has_more
      return true
    })()
    pagePromise = pending
    try { return await pending }
    finally { if (pagePromise === pending) pagePromise = null }
  }

  // Walk forward from `start` to the next post with playable media in scope.
  const search = async (start: number, stale: () => boolean, pageLimit: number,
                        onSkip?: () => void): Promise<SearchResult> => {
    let index = start
    let pages = 0
    let checks = 0
    while (!stale()) {
      if (index >= posts.value.length) {
        if (!hasMore.value) return { kind: 'end' }
        if (pages >= pageLimit) return { kind: 'paused', index }
        await loadPage()
        pages++
        continue
      }
      if (summaryMediaCount(posts.value[index]!) === 0) {
        index++
        onSkip?.()
        continue
      }
      let detail: PawchivePost
      try { detail = await detailAt(index) }
      catch (cause) {
        if (!isNotFound(cause)) throw cause
        detail = { ...posts.value[index]!, attachments: [] }
      }
      if (stale()) break
      if (playable(detail).length) return { kind: 'found', index, detail }
      index++
      onSkip?.()
      if (++checks >= DETAIL_CHECK_LIMIT) return { kind: 'paused', index }
    }
    return { kind: 'stale' }
  }

  function prepareNextPost() {
    const ownerKey = current.value?.post.post_key
    const requestedVersion = version
    const lookup = ++nextLookup
    nextPost.value = null
    nextPostIndex = -1
    if (!ownerKey) return
    const stale = () => requestedVersion !== version || lookup !== nextLookup || current.value?.post.post_key !== ownerKey
    void search(postIndex + 1, stale, PREFETCH_PAGE_LIMIT).then(result => {
      if (result.kind !== 'found' || stale()) return
      nextPost.value = result.detail
      nextPostIndex = result.index
    }).catch(() => {})
  }

  const next = async () => {
    if (!active.value || busy.value || ended.value) return
    if (current.value && searchIndex === null) {
      const inPost = playable(current.value.post)
      if (current.value.index + 1 < inPost.length) {
        setCurrent(postIndex, current.value.post, current.value.index + 1, true)
        return
      }
      if (nextPost.value && nextPostIndex > postIndex) {
        setCurrent(nextPostIndex, nextPost.value, 0, true)
        return
      }
    }
    busy.value = true
    error.value = ''
    skipped.value = 0
    const requestedVersion = version
    const start = searchIndex ?? (postIndex >= 0 ? postIndex + 1 : 0)
    try {
      const result = await search(start, () => requestedVersion !== version, SEARCH_PAGE_LIMIT, () => { skipped.value++ })
      if (result.kind === 'stale') return
      if (result.kind === 'found') {
        setCurrent(result.index, result.detail, 0, true)
        return
      }
      if (result.kind === 'end') {
        ended.value = true
        error.value = current.value ? '已到当前范围末尾' : '当前范围内没有可播放的媒体'
        return
      }
      searchIndex = result.index
      error.value = `已跳过 ${skipped.value} 篇没有媒体的帖子，点击“下一项”继续查找。`
    } catch (cause) {
      if (requestedVersion === version && !axios.isCancel(cause)) {
        searchIndex = searchIndex ?? start
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

  // Refetch the current post for fresh media refs, keeping the same attachment.
  const reloadCurrent = async (): Promise<boolean> => {
    const item = current.value
    if (!active.value || !item || postIndex < 0) return false
    const requestedVersion = version
    const { post_key: postKey } = item.post
    const { attachment_key: attachmentKey } = item.attachment
    try {
      const detail = await detailAt(postIndex, true)
      if (requestedVersion !== version || current.value?.post.post_key !== postKey ||
          current.value.attachment.attachment_key !== attachmentKey) return false
      const attachments = playable(detail)
      const index = attachments.findIndex(attachment => attachment.attachment_key === attachmentKey)
      if (index < 0) return false
      current.value = { post: detail, attachment: attachments[index]!, index, total: attachments.length }
      return true
    } catch {
      return false
    }
  }

  const open = async (index: number, initialPosts: PawchivePost[], nextCursor: string | null,
                      more: boolean, browseScope: PawchiveScope) => {
    close()
    active.value = true
    scope.value = { ...browseScope }
    posts.value = [...initialPosts]
    cursor.value = nextCursor
    hasMore.value = more
    searchIndex = index
    await next()
  }

  const close = () => {
    version++
    nextLookup++
    nextPost.value = null
    nextPostIndex = -1
    pagePromise = null
    controller?.abort()
    controller = new AbortController()
    active.value = false
    current.value = null
    history.value = []
    detailCache.clear()
    detailRequests.clear()
    busy.value = false
    error.value = ''
    notice.value = ''
    ended.value = false
    skipped.value = 0
    postIndex = -1
    searchIndex = null
  }

  return { active, busy, error, notice, ended, skipped, current, nextPost, postAttachments, nextPostAttachments, history, scopeLabel, open, next, previous, selectAttachment, reloadCurrent, close }
}
