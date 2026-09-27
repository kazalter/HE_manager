import { describe, expect, it, vi } from 'vitest'
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

describe('Pawchive media sequence', () => {
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
})
