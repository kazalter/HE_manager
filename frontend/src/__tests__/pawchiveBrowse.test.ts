import { describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { usePawchiveBrowse } from '../composables/usePawchiveBrowse'
import type { PawchivePage, PawchiveScope } from '../types/pawchive'

const scope = (query: string): PawchiveScope => ({ query, service: '', creatorId: '', tag: '', mediaType: 'all' })
const page = (key: string): PawchivePage => ({
  items: [{ post_key: key, service: 'fanbox', creator_id: '1', post_id: key, title: key,
    creator_name: 'test', source_url: '', published_at: null, reported_attachment_count: 0,
    playable_count: null, preview_ref: null, tags: [], attachments: [] }],
  has_more: false, next_cursor: null, total: null, applied_filters: {}, filter_scope: 'server', warnings: [],
})

describe('Pawchive browse session', () => {
  it('ignores an older response after the scope changes', async () => {
    let finishOld!: (value: { data: PawchivePage }) => void
    const oldRequest = new Promise<{ data: PawchivePage }>(resolve => { finishOld = resolve })
    vi.spyOn(axios, 'get').mockReturnValueOnce(oldRequest as never).mockResolvedValueOnce({ data: page('new') })
    const browse = usePawchiveBrowse()
    const first = browse.setScope(scope('old'))
    await browse.setScope(scope('new'))
    finishOld({ data: page('old') })
    await first
    expect(browse.posts.value.map(post => post.post_key)).toEqual(['new'])
    browse.dispose()
  })
})
