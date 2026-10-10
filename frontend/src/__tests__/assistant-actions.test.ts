import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ProposalCard from '../components/assistant/ProposalCard.vue'
import { authState } from '../auth'
const proposal = () => ({
  id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
  session_id: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
  kind: 'media_update',
  target_id: 1,
  target_label: '<script>evil</script>',
  state: 'pending',
  expires_at: new Date(Date.now() + 300000).toISOString().replace('Z', ''),
  payload_hash: 'a'.repeat(64),
  before: { rating: 2 },
  after: { rating: 4 },
  result: null,
})
beforeEach(() => {
  authState.token = 'user-token'
  authState.user = { id: 1, is_admin: true } as any
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.useRealTimers()
})
describe('explicit assistant proposal confirmation', () => {
  it('blocks legacy truncated previews with no exact tag change list', () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(ProposalCard, {
      props: {
        proposal: {
          ...proposal(),
          before: { tags: [], tags_truncated: true },
          after: { tags: [], tags_truncated: true },
        } as any,
      },
    })
    expect(wrapper.get('[data-confirm]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('重新生成')
    expect(fetcher).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows exact tag additions and removals using readable field labels', () => {
    vi.stubGlobal('fetch', vi.fn())
    const p = {
      ...proposal(),
      before: { tags: [], tags_truncated: true },
      after: {
        tags: [],
        tags_truncated: true,
        add_tags: [{ name: '新增标签', namespace: 'general' }],
        remove_tags: [{ id: 159, name: '移除标签', namespace: 'general' }],
      },
    }
    const wrapper = mount(ProposalCard, { props: { proposal: p as any } })
    expect(wrapper.text()).toContain('新增标签：新增标签')
    expect(wrapper.text()).toContain('移除标签：移除标签')
    expect(wrapper.text()).not.toContain('"namespace"')
    wrapper.unmount()
  })

  it('renders target as text and never confirms before click', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({
            proposal_id: proposal().id,
            state: 'applied',
            media_id: 1,
          }),
          { status: 200 },
        ),
      )
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(ProposalCard, {
      props: { proposal: proposal() as any },
    })
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>evil</script>')
    expect(fetcher).not.toHaveBeenCalled()
    await wrapper.get('[data-confirm]').trigger('click')
    await flushPromises()
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      payload_hash: 'a'.repeat(64),
    })
    expect(wrapper.text()).toContain('已执行')
    wrapper.unmount()
  })
  it('disables both actions while confirmation is pending and rejects duplicate clicks', async () => {
    let resolve!: (r: Response) => void
    const fetcher = vi.fn().mockImplementation(
      () =>
        new Promise((r) => {
          resolve = r
        }),
    )
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(ProposalCard, {
      props: { proposal: proposal() as any },
    })
    await wrapper.get('[data-confirm]').trigger('click')
    await wrapper.get('[data-confirm]').trigger('click')
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-reject]').attributes('disabled')).toBeDefined()
    resolve(
      new Response(
        JSON.stringify({ proposal_id: proposal().id, state: 'applied' }),
      ),
    )
    await flushPromises()
    wrapper.unmount()
  })
  it('supports explicit rejection without confirmation', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ ...proposal(), state: 'rejected' })),
      )
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(ProposalCard, {
      props: { proposal: proposal() as any },
    })
    await wrapper.get('[data-reject]').trigger('click')
    await flushPromises()
    expect(fetcher.mock.calls[0][0]).toMatch(/\/reject$/)
    expect(wrapper.text()).toContain('已拒绝')
    wrapper.unmount()
  })
  it('interprets naive UTC expiry and blocks elapsed proposals', async () => {
    const fetcher = vi.fn()
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(ProposalCard, {
      props: {
        proposal: {
          ...proposal(),
          expires_at: new Date(Date.now() - 1000)
            .toISOString()
            .replace('Z', ''),
        } as any,
      },
    })
    expect(wrapper.get('[data-confirm]').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('已过期')
    expect(fetcher).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('on 409 requires regenerating a proposal and never automatically retries', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response('{"detail":"assistant_proposal_stale"}', { status: 409 }),
      )
    vi.stubGlobal('fetch', fetcher)
    const wrapper = mount(ProposalCard, {
      props: { proposal: proposal() as any },
    })
    await wrapper.get('[data-confirm]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('重新生成')
    expect(wrapper.get('[data-confirm]').attributes('disabled')).toBeDefined()
    expect(fetcher).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
  it('shows confirmed scan job actual status and never claims chat stop cancels it', async () => {
    const p = {
      ...proposal(),
      kind: 'scan',
      state: 'queued',
      result: {
        proposal_id: proposal().id,
        state: 'queued',
        job_id: 'assistant-scan-test',
        job: {
          job_id: 'assistant-scan-test',
          folder_id: 1,
          status: 'failed',
          message: '扫描可能已处理部分文件',
          created_at: new Date().toISOString(),
          finished_at: new Date().toISOString(),
        },
      },
    }
    vi.stubGlobal('fetch', vi.fn())
    const wrapper = mount(ProposalCard, { props: { proposal: p as any } })
    expect(wrapper.text()).toContain('执行失败')
    expect(wrapper.text()).toContain('部分')
    expect(wrapper.text()).toContain('assistant-scan-test')
    wrapper.unmount()
  })
})
