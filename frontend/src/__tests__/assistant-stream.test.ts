import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import { authState } from '../auth'
import {
  subscribeRun,
  sendMessage,
  AssistantApiError,
} from '../utils/assistantApi'

const RID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
const MID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
function streaming(wire: string, chunkSize = 1) {
  const bytes = new TextEncoder().encode(wire)
  return new Response(
    new ReadableStream({
      start(controller) {
        for (let i = 0; i < bytes.length; i += chunkSize)
          controller.enqueue(bytes.slice(i, i + chunkSize))
        controller.close()
      },
    }),
    { status: 200 },
  )
}
const envelope = (data: unknown) =>
  JSON.stringify({
    event_id: '1',
    type: 'text_delta',
    run_id: RID,
    message_id: MID,
    data,
  })
beforeEach(() => {
  authState.token = 'user-token'
  authState.user = { id: 1, is_admin: true, username: 'admin' } as any
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
describe('authenticated assistant stream', () => {
  it('decodes split UTF8 multiline CRLF and ignores heartbeat comments', async () => {
    const wire =
      ': heartbeat\r\n\r\nid: 1\r\ndata: {"event_id":"1","type":"text_delta",\r\ndata: "run_id":"' +
      RID +
      '","message_id":"' +
      MID +
      '","data":{"delta":"你好"}}\r\n\r\n'
    const fetcher = vi.fn().mockResolvedValue(streaming(wire))
    vi.stubGlobal('fetch', fetcher)
    const events: any[] = []
    await subscribeRun(RID, new AbortController().signal, (e) => events.push(e))
    expect(events).toHaveLength(1)
    expect(events[0].data.delta).toBe('你好')
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
      'Bearer user-token',
    )
    expect(fetcher.mock.calls[0][0]).not.toContain('token=')
  })
  it('rejects malformed and oversized events before delivering any event', async () => {
    for (const wire of [
      'data: {invalid\n\n',
      'data: ' + 'x'.repeat(128 * 1024 + 1),
    ]) {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(streaming(wire, 4096)))
      const listener = vi.fn()
      await expect(
        subscribeRun(RID, new AbortController().signal, listener),
      ).rejects.toBeInstanceOf(AssistantApiError)
      expect(listener).not.toHaveBeenCalled()
    }
  })
  it('rejects foreign run envelopes and ignores duplicate numeric cursors', async () => {
    const value = envelope({ delta: 'x' })
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          streaming(
            'id: 1\ndata: ' + value + '\n\nid: 1\ndata: ' + value + '\n\n',
            9,
          ),
        ),
    )
    const listener = vi.fn()
    await subscribeRun(RID, new AbortController().signal, listener)
    expect(listener).toHaveBeenCalledTimes(1)
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          streaming('data: ' + value.replace(RID, MID) + '\n\n'),
        ),
    )
    await expect(
      subscribeRun(RID, new AbortController().signal, vi.fn()),
    ).rejects.toBeInstanceOf(AssistantApiError)
  })
  it('clears current login on 401 without sending a URL token', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response('{"detail":"Unauthorized"}', { status: 401 }),
        ),
    )
    await expect(sendMessage(MID, 'hi', RID)).rejects.toMatchObject({
      status: 401,
    })
    expect(authState.token).toBe('')
    expect(authState.user).toBeNull()
  })
  it('does not clear a newer login when an older request returns 401', async () => {
    let resolve!: (r: Response) => void
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        () =>
          new Promise((r) => {
            resolve = r
          }),
      ),
    )
    const request = sendMessage(MID, 'hi', RID)
    authState.token = 'new-token'
    resolve(new Response('{}', { status: 401 }))
    await expect(request).rejects.toMatchObject({ status: 401 })
    expect(authState.token).toBe('new-token')
  })
})
