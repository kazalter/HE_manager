import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import { effectScope } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { authState } from '../auth'
import AssistantView from '../views/AssistantView.vue'
import ChatMessages from '../components/assistant/ChatMessages.vue'
import MediaResults from '../components/assistant/MediaResults.vue'
import { useAssistantChat } from '../composables/useAssistantChat'
const SID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  RID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  MID = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
const run = (patch = {}) => ({
  id: RID,
  session_id: SID,
  final_message_id: MID,
  status: 'running',
  output: '',
  usage: null,
  error_code: null,
  ...patch,
})
const page = (items: any[]) => ({
  items,
  total: items.length,
  offset: 0,
  has_more: false,
})
function fakeApi() {
  return {
    getAvailability: vi.fn().mockResolvedValue({
      enabled: true,
      busy: false,
      active_run_id: null,
      error_code: null,
    }),
    listSessions: vi
      .fn()
      .mockResolvedValue(page([{ id: SID, title: '测试', state: 'active' }])),
    createSession: vi
      .fn()
      .mockResolvedValue({ id: SID, title: '测试', state: 'active' }),
    getMessages: vi.fn().mockResolvedValue(page([])),
    getProposals: vi.fn().mockResolvedValue(page([])),
    getRun: vi.fn().mockResolvedValue(run()),
    getResults: vi.fn().mockResolvedValue({ items: [], truncated: false }),
    sendMessage: vi.fn().mockResolvedValue(run()),
    subscribeRun: vi.fn().mockResolvedValue(undefined),
    stopRun: vi.fn().mockResolvedValue(run({ status: 'cancelled' })),
    clearSession: vi.fn().mockResolvedValue({ id: SID, state: 'cleared' }),
  }
}
beforeEach(() => {
  authState.token = 'user-token'
  authState.user = { id: 1, is_admin: true, username: 'admin' } as any
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})
describe('assistant chat lifecycle', () => {
  it('restores saved results and proposals when same-ID retry is already completed', async () => {
    const api = fakeApi()
    api.sendMessage.mockRejectedValueOnce(new Error('accepted response lost'))
    api.sendMessage.mockResolvedValue(run({ status: 'completed', output: 'canonical final' }))
    const result = { tool_call_id: 'new-result', tool_name: 'search_media', result: { items: [{ id: 7, title: 'saved match' }] } }
    const card = { id: 'saved-proposal', kind: 'media_update', state: 'pending' }
    api.getResults.mockResolvedValue({ items: [result], truncated: true })
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    try {
      await chat.initialize()
      await chat.send('search and propose')
      expect(chat.hasRetry.value).toBe(true)
      chat.results.value = [{ tool_call_id: 'old-result', tool_name: 'search_media', result: {} }] as any
      api.getProposals.mockResolvedValue(page([card]))
      await chat.retrySend()
      expect(api.sendMessage).toHaveBeenCalledTimes(2)
      expect(api.sendMessage.mock.calls[0]).toEqual(api.sendMessage.mock.calls[1])
      expect(chat.run.value?.status).toBe('completed')
      expect(chat.results.value).toEqual([result])
      expect(chat.proposals.value).toEqual([card])
      expect(chat.truncated.value).toBe(true)
      expect(chat.hasRetry.value).toBe(false)
      expect(api.getAvailability).toHaveBeenCalledTimes(2)
      expect(api.subscribeRun).not.toHaveBeenCalled()
    } finally { scope.stop() }
  })

  it('discards terminal submission result restoration after identity changes', async () => {
    const api = fakeApi()
    api.sendMessage.mockResolvedValue(run({ status: 'completed', output: 'private final' }))
    let resolveResults!: (value: any) => void
    api.getResults.mockImplementation(() => new Promise(resolve => { resolveResults = resolve }))
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    try {
      await chat.initialize()
      const sending = chat.send('private request')
      await flushPromises()
      expect(api.getResults).toHaveBeenCalledTimes(1)
      authState.token = 'second-token'
      authState.user = { id: 2, is_admin: true, username: 'second' } as any
      await flushPromises()
      resolveResults({ items: [{ tool_call_id: 'private-result', tool_name: 'search_media', result: {} }], truncated: false })
      await sending
      expect(chat.results.value).toEqual([])
      expect(chat.proposals.value).toEqual([])
      expect(chat.run.value).toBeNull()
    } finally { scope.stop() }
  })

  it('keeps a drafted message when the keyboard shortcut is used during a busy run', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async (url: string) =>
          new Response(
            JSON.stringify(
              url.endsWith('/status')
                ? { enabled: true, busy: true, active_run_id: null }
                : /\/sessions\?/.test(url)
                  ? page([{ id: SID, title: '测试', state: 'active' }])
                  : url.includes('/messages')
                    ? page([
                        {
                          id: MID,
                          role: 'assistant',
                          content: '旧回复',
                          run_id: RID,
                          status: 'completed',
                        },
                      ])
                    : url.endsWith('/results')
                      ? { items: [], truncated: false }
                      : url.endsWith('/runs/' + RID)
                        ? run({ status: 'completed', output: '旧回复' })
                        : page([]),
            ),
          ),
      ),
    )
    const wrapper = mount(AssistantView)
    await flushPromises()
    const textarea = wrapper.get('textarea')
    await textarea.setValue('下一条消息')
    await textarea.trigger('keydown', { key: 'Enter', ctrlKey: true })
    await flushPromises()
    expect((textarea.element as HTMLTextAreaElement).value).toBe('下一条消息')
    wrapper.unmount()
  })

  it('discards the prior identity draft and reinitializes after changing accounts', async () => {
    let statusReads = 0
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.endsWith('/status')) statusReads++
        return new Response(
          JSON.stringify(
            url.endsWith('/status')
              ? { enabled: true, busy: false, active_run_id: null }
              : page([]),
          ),
        )
      }),
    )
    const wrapper = mount(AssistantView)
    await flushPromises()
    await wrapper.get('textarea').setValue('上一个账号的私密草稿')
    authState.token = 'second-account-token'
    authState.user = { id: 2, is_admin: true, username: 'second' } as any
    await flushPromises()
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe(
      '',
    )
    expect(statusReads).toBe(2)
    wrapper.unmount()
  })

  it('retains the newer terminal snapshot observed during reconnect history restore', async () => {
    const api = fakeApi()
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    await chat.send('hi')
    api.getRun
      .mockResolvedValueOnce(run())
      .mockResolvedValueOnce(
        run({ status: 'completed', output: 'finished during history read' }),
      )
    await chat.reconnect()
    expect(chat.run.value?.status).toBe('completed')
    expect(chat.messages.value.find((m) => m.id === MID)?.content).toBe(
      'finished during history read',
    )
    expect(api.subscribeRun).toHaveBeenCalledTimes(1)
    scope.stop()
  })
  it('generates a valid idempotency UUID on HTTP LAN origins without randomUUID', async () => {
    const secure = crypto.getRandomValues.bind(crypto)
    vi.stubGlobal('crypto', { getRandomValues: secure })
    const api = fakeApi()
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    await chat.send('LAN message')
    expect(api.sendMessage).toHaveBeenCalledTimes(1)
    expect(api.sendMessage.mock.calls[0]?.[2]).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    )
    scope.stop()
  })

  it('keeps the composer visible after focus and delayed viewport layout changes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async (url: string) =>
          new Response(
            JSON.stringify(
              url.endsWith('/status')
                ? { enabled: true, busy: false, active_run_id: null }
                : page([]),
            ),
          ),
      ),
    )
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal(
      'requestAnimationFrame',
      vi.fn((callback: FrameRequestCallback) => {
        frames.push(callback)
        return frames.length
      }),
    )
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    const wrapper = mount(AssistantView, { attachTo: document.body })
    await flushPromises()
    const form = wrapper.get('form').element as HTMLFormElement
    form.scrollIntoView = vi.fn()
    ;(wrapper.get('textarea').element as HTMLTextAreaElement).focus()
    frames.shift()?.(0)
    frames.shift()?.(0)
    expect(form.scrollIntoView).toHaveBeenCalledWith(
      expect.objectContaining({ block: 'nearest' }),
    )
    wrapper.unmount()
  })

  it('blocks sending while the selected history is loading', async () => {
    const api = fakeApi()
    let resolve!: any
    api.getMessages.mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r
        }),
    )
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    const initializing = chat.initialize()
    await flushPromises()
    expect(chat.loading.value).toBe(true)
    expect(chat.canSend.value).toBe(false)
    resolve(page([]))
    await initializing
    scope.stop()
  })

  it('updates retry visibility reactively after a failed send and clears it on success', async () => {
    const api = fakeApi()
    api.sendMessage.mockRejectedValueOnce(new Error('network'))
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    expect(chat.hasRetry.value).toBe(false)
    await chat.send('retry')
    expect(chat.hasRetry.value).toBe(true)
    await chat.retrySend()
    expect(chat.hasRetry.value).toBe(false)
    scope.stop()
  })
  it('ignores events from a superseded subscription after reconnect', async () => {
    const api = fakeApi()
    const callbacks: any[] = []
    api.subscribeRun.mockImplementation(
      async (_r: any, _s: any, event: any) => {
        callbacks.push(event)
      },
    )
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    await chat.send('hi')
    await chat.reconnect()
    callbacks[0]({
      event_id: '3',
      type: 'text_delta',
      run_id: RID,
      message_id: MID,
      data: { delta: 'old-stream' },
    })
    expect(
      chat.messages.value.find((m) => m.id === MID)?.content,
    ).not.toContain('old-stream')
    scope.stop()
  })
  it('clear invalidates an in-flight send so a late response cannot resurrect the conversation', async () => {
    const api = fakeApi()
    let resolve!: any
    api.sendMessage.mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r
        }),
    )
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    const sending = chat.send('hi')
    await flushPromises()
    await chat.clear()
    resolve(run())
    await sending
    expect(chat.run.value).toBeNull()
    expect(chat.messages.value).toEqual([])
    expect(api.subscribeRun).not.toHaveBeenCalled()
    scope.stop()
  })
  it('restores latest completed run results and usage when selecting its history', async () => {
    const api = fakeApi()
    api.getMessages.mockResolvedValue(
      page([
        {
          id: MID,
          role: 'assistant',
          content: 'done',
          run_id: RID,
          status: 'completed',
        },
      ]),
    )
    api.getRun.mockResolvedValue(
      run({ status: 'completed', output: 'done', usage: { total_tokens: 10 } }),
    )
    api.getResults.mockResolvedValue({
      items: [
        { tool_call_id: MID, tool_name: 'search_media', result: { items: [] } },
      ],
      truncated: false,
    } as any)
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    expect(chat.run.value?.usage?.total_tokens).toBe(10)
    expect(chat.results.value).toHaveLength(1)
    scope.stop()
  })

  it('hides page and makes no requests for ordinary users', async () => {
    authState.user = { id: 2, is_admin: false } as any
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(AssistantView)
    await flushPromises()
    expect(wrapper.text()).toContain('管理员')
    expect(wrapper.find('textarea').exists()).toBe(false)
    expect(fetcher).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('renders messages and media titles as pure text', () => {
    const chat = mount(ChatMessages, {
      props: {
        messages: [
          {
            id: MID,
            role: 'assistant',
            content: '<img src=x onerror=evil()>',
            run_id: RID,
            status: 'completed',
          },
        ],
      },
    })
    expect(chat.find('img').exists()).toBe(false)
    expect(chat.text()).toContain('<img')
    chat.unmount()
    const media = mount(MediaResults, {
      props: {
        results: [
          {
            tool_call_id: MID,
            tool_name: 'search_media',
            result: {
              items: [
                {
                  id: 1,
                  title: '<script>evil</script>',
                  media_type: 'manga',
                  tags: [],
                },
              ],
              total: 1,
            },
          },
        ] as any,
      },
    })
    expect(media.find('script').exists()).toBe(false)
    expect(media.text()).toContain('<script>')
    media.unmount()
  })
  it('deduplicates simultaneous sends and replaces partial final output once', async () => {
    const api = fakeApi()
    let deliver: any
    api.subscribeRun.mockImplementation(
      async (_rid: any, _signal: any, onEvent: any) => {
        deliver = onEvent
      },
    )
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    await Promise.all([chat.send('你好'), chat.send('你好')])
    expect(api.sendMessage).toHaveBeenCalledTimes(1)
    deliver({
      event_id: '1',
      type: 'text_delta',
      run_id: RID,
      message_id: MID,
      data: { delta: '半截' },
    })
    deliver({
      event_id: '2',
      type: 'run_status',
      run_id: RID,
      message_id: MID,
      data: run({ status: 'completed', output: '完整回复' }),
    })
    deliver({
      event_id: '2',
      type: 'run_status',
      run_id: RID,
      message_id: MID,
      data: run({ status: 'completed', output: '完整回复' }),
    })
    expect(chat.messages.value.filter((m) => m.id === MID)).toHaveLength(1)
    expect(chat.messages.value.find((m) => m.id === MID)?.content).toBe(
      '完整回复',
    )
    scope.stop()
  })
  it('retries failed submission with the same client request id and frozen text', async () => {
    const api = fakeApi()
    api.sendMessage.mockRejectedValueOnce(new Error('network'))
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    await chat.send('原文')
    await chat.retrySend()
    expect(api.sendMessage).toHaveBeenCalledTimes(2)
    expect(api.sendMessage.mock.calls[0]).toEqual(api.sendMessage.mock.calls[1])
    scope.stop()
  })
  it('reconnect restores status/history/results without creating another run', async () => {
    const api = fakeApi()
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    await chat.send('hi')
    await chat.reconnect()
    expect(api.sendMessage).toHaveBeenCalledTimes(1)
    expect(api.getRun).toHaveBeenCalledWith(RID, expect.anything())
    expect(api.getMessages).toHaveBeenCalled()
    expect(api.getResults).toHaveBeenCalled()
    scope.stop()
  })
  it('unmount aborts only subscription and ignores late events without calling stop', async () => {
    const api = fakeApi()
    let signal: any, deliver: any
    api.subscribeRun.mockImplementation(
      async (_rid: any, s: any, event: any) => {
        signal = s
        deliver = event
      },
    )
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    await chat.send('hi')
    scope.stop()
    expect(signal.aborted).toBe(true)
    expect(api.stopRun).not.toHaveBeenCalled()
    const old = chat.messages.value.map((m) => m.content)
    deliver({
      event_id: '1',
      type: 'text_delta',
      run_id: RID,
      message_id: MID,
      data: { delta: '迟到' },
    })
    expect(chat.messages.value.map((m) => m.content)).toEqual(old)
  })
  it('logout invalidates pending async responses and discards prior identity state', async () => {
    const api = fakeApi()
    let resolve!: any
    api.sendMessage.mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r
        }),
    )
    const scope = effectScope()
    const chat = scope.run(() => useAssistantChat(api as any))!
    await chat.initialize()
    const sending = chat.send('hi')
    await flushPromises()
    authState.token = 'other-user'
    authState.user = { id: 2, is_admin: true } as any
    await flushPromises()
    resolve(run())
    await sending
    expect(chat.run.value).toBeNull()
    expect(chat.messages.value).toEqual([])
    scope.stop()
  })
})
