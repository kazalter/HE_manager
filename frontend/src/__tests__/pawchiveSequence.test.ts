import { afterEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { usePawchiveSequence } from '../composables/usePawchiveSequence'
import type { PawchiveAttachment, PawchivePage, PawchivePost, PawchiveScope } from '../types/pawchive'

const attachment = (key: string): PawchiveAttachment => ({
  attachment_key: key, original_index: 0, filename: `${key}.jpg`, media_type: 'image',
  mime_type: 'image/jpeg', stream_ref: key, preview_ref: key, availability: 'playable',
})
const post = (key: string, attachments: PawchiveAttachment[] = []): PawchivePost => ({
  post_key: key, service: 'fanbox', creator_id: '7', post_id: key,
  title: key, creator_name: 'Creator', source_url: '', published_at: null,
  reported_attachment_count: attachments.length, playable_count: attachments.length,
  preview_ref: null, tags: [], attachments,
})
const page = (items: PawchivePost[], cursor: string | null): PawchivePage => ({
  items, next_cursor: cursor, has_more: !!cursor, total: null,
  applied_filters: {}, filter_scope: 'server', warnings: [],
})
const scope: PawchiveScope = { query: 'test', service: '', creatorId: '', tag: '', mediaType: 'all' }

const counted = (key: string, images: number, attachments: PawchiveAttachment[] = []): PawchivePost => ({
  ...post(key, attachments), image_count: images, video_count: 0,
})
const flush = () => new Promise(resolve => setTimeout(resolve, 0))

describe('Pawchive media sequence', () => {
  afterEach(() => { vi.restoreAllMocks() })

  it('keeps the scope and history across two page boundaries', async () => {
    const first = post('one', [attachment('a'), attachment('b')])
    const empty = post('two')
    const third = post('three', [attachment('c')])
    const calls: string[] = []
    vi.spyOn(axios, 'get').mockImplementation(async (url, options) => {
      if (url.endsWith('/posts')) {
        const cursor = options?.params?.cursor
        calls.push(cursor)
        return { data: cursor === 'page-2' ? page([empty], 'page-3') : page([third], null) }
      }
      if (url.endsWith('/one')) return { data: first }
      if (url.endsWith('/two')) return { data: empty }
      if (url.endsWith('/three')) return { data: third }
      throw new Error(`unexpected ${url}`)
    })
    const session = usePawchiveSequence()
    await session.open(0, [first], 'page-2', true, scope)
    expect(session.current.value?.attachment.attachment_key).toBe('a')
    await session.next()
    expect(session.current.value?.attachment.attachment_key).toBe('b')
    await session.next()
    expect(session.current.value?.attachment.attachment_key).toBe('c')
    expect(calls).toEqual(['page-2', 'page-3'])
    expect(session.scopeLabel.value).toContain('test')
    await session.previous()
    expect(session.current.value?.attachment.attachment_key).toBe('b')
    session.close()
  })

  it('jumps to a thumbnail in the current post and preserves previous navigation', async () => {
    const first = post('one', [attachment('a'), attachment('b'), attachment('c')])
    vi.spyOn(axios, 'get').mockImplementation(async url => {
      if (url.endsWith('/one')) return { data: first }
      throw new Error('unexpected post request')
    })
    const session = usePawchiveSequence()
    await session.open(0, [first], null, false, scope)
    expect(session.postAttachments.value.map(item => item.attachment_key)).toEqual(['a', 'b', 'c'])
    session.selectAttachment(2)
    expect(session.current.value?.attachment.attachment_key).toBe('c')
    await session.previous()
    expect(session.current.value?.attachment.attachment_key).toBe('a')
    session.close()
  })

  it('skips posts reported as empty without requesting their details, across pages', async () => {
    const first = counted('one', 1, [attachment('a')])
    const empties = Array.from({ length: 30 }, (_, index) => counted(`empty-${index}`, 0))
    const last = counted('last', 1, [attachment('z')])
    const details: string[] = []
    vi.spyOn(axios, 'get').mockImplementation(async (url, options) => {
      if (url.endsWith('/posts')) {
        return { data: options?.params?.cursor === 'page-2' ? page(empties.slice(15), 'page-3') : page([last], null) }
      }
      details.push(url.split('/').pop()!)
      if (url.endsWith('/one')) return { data: first }
      if (url.endsWith('/last')) return { data: last }
      throw new Error(`unexpected ${url}`)
    })
    const session = usePawchiveSequence()
    await session.open(0, [first, ...empties.slice(0, 15)], 'page-2', true, scope)
    await flush()
    await session.next()
    expect(session.current.value?.attachment.attachment_key).toBe('z')
    expect(session.error.value).toBe('')
    expect(details).toEqual(['one', 'last'])
    session.close()
  })

  it('switches to the prefetched post without another search', async () => {
    const first = counted('one', 1, [attachment('a')])
    const second = counted('two', 1, [attachment('b')])
    const get = vi.spyOn(axios, 'get').mockImplementation(async url => {
      if (url.endsWith('/one')) return { data: first }
      if (url.endsWith('/two')) return { data: second }
      throw new Error(`unexpected ${url}`)
    })
    const session = usePawchiveSequence()
    await session.open(0, [first, second], null, false, scope)
    await flush()
    expect(session.nextPost.value?.post_key).toBe('two')
    const calls = get.mock.calls.length
    await session.next()
    expect(session.busy.value).toBe(false)
    expect(session.current.value?.attachment.attachment_key).toBe('b')
    expect(get.mock.calls.length).toBe(calls)
    session.close()
  })

  it('retries a transient detail failure once', async () => {
    vi.useFakeTimers()
    try {
      const first = counted('one', 1, [attachment('a')])
      let attempts = 0
      vi.spyOn(axios, 'get').mockImplementation(async () => {
        if (++attempts === 1) throw new axios.AxiosError('offline', 'ERR_NETWORK')
        return { data: first }
      })
      const session = usePawchiveSequence()
      const opening = session.open(0, [first], null, false, scope)
      await vi.advanceTimersByTimeAsync(1600)
      await opening
      expect(attempts).toBe(2)
      expect(session.current.value?.attachment.attachment_key).toBe('a')
      session.close()
    } finally {
      vi.useRealTimers()
    }
  })

  it('reloads the current post to replace media refs in place', async () => {
    let signed = 0
    const fresh = () => counted('one', 1, [{ ...attachment('a'), stream_ref: `ref-${++signed}` }])
    vi.spyOn(axios, 'get').mockImplementation(async () => ({ data: fresh() }))
    const session = usePawchiveSequence()
    await session.open(0, [counted('one', 1)], null, false, scope)
    expect(session.current.value?.attachment.stream_ref).toBe('ref-1')
    await expect(session.reloadCurrent()).resolves.toBe(true)
    expect(session.current.value?.attachment.stream_ref).toBe('ref-2')
    expect(session.history.value).toEqual([])
    session.close()
  })
})
