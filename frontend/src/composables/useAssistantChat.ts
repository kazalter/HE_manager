import { computed, onScopeDispose, ref, watch } from 'vue'
import { authState } from '../auth'
import * as defaultApi from '../utils/assistantApi'
import type {
  AssistantEvent,
  AvailabilityDTO,
  MessageDTO,
  ProposalDTO,
  RunDTO,
  SessionDTO,
  ToolResultDTO,
} from '../types/assistant'

type Api = Pick<
  typeof defaultApi,
  | 'getAvailability'
  | 'listSessions'
  | 'createSession'
  | 'getMessages'
  | 'getProposals'
  | 'getRun'
  | 'getResults'
  | 'sendMessage'
  | 'subscribeRun'
  | 'stopRun'
  | 'clearSession'
>
const terminal = (status: string) =>
  ['completed', 'failed', 'cancelled', 'interrupted'].includes(status)
export function useAssistantChat(api: Api = defaultApi) {
  const sessions = ref<SessionDTO[]>([]),
    session = ref<SessionDTO | null>(null),
    run = ref<RunDTO | null>(null)
  const messages = ref<MessageDTO[]>([]),
    results = ref<ToolResultDTO[]>([]),
    proposals = ref<ProposalDTO[]>([])
  const availability = ref<AvailabilityDTO>({
    enabled: false,
    busy: false,
    active_run_id: null,
    error_code: null,
  })
  const loading = ref(false),
    sending = ref(false),
    connected = ref(false),
    error = ref(''),
    toolStatus = ref(''),
    truncated = ref(false)
  const olderOffset = ref(0),
    moreSessions = ref(false),
    moreProposals = ref(false)
  const allowed = computed(
    () => !!authState.token && !!authState.user?.is_admin,
  )
  const active = computed(
    () =>
      !!run.value &&
      (!terminal(run.value.status) ||
        availability.value.active_run_id === run.value.id),
  )
  const canSend = computed(
    () =>
      allowed.value &&
      availability.value.enabled &&
      !availability.value.busy &&
      !sending.value &&
      !loading.value &&
      (!session.value || session.value.state === 'active'),
  )
  let epoch = 0,
    alive = true,
    requests = new AbortController(),
    stream: AbortController | null = null,
    sendPromise: Promise<void> | null = null
  const pending = ref<{ sid: string; text: string; cid: string } | null>(null)
  const options = () => ({ signal: requests.signal })
  const valid = (e: number) => alive && e === epoch && allowed.value
  function invalidate() {
    epoch++
    requests.abort()
    stream?.abort()
    requests = new AbortController()
    stream = null
    pending.value = null
    sendPromise = null
    sending.value = false
    connected.value = false
    loading.value = false
  }
  function fail(cause: unknown) {
    error.value =
      cause instanceof defaultApi.AssistantApiError && cause.status === 409
        ? '当前任务或资料状态已变化，请刷新后重新操作。'
        : '连接暂不可用，可重试或重新连接；不会自动重复执行。'
  }
  function setRun(value: RunDTO) {
    run.value = value
    let message = messages.value.find((m) => m.id === value.final_message_id)
    if (!message) {
      message = {
        id: value.final_message_id,
        role: 'assistant',
        content: value.output || '',
        run_id: value.id,
        status: value.status,
      }
      messages.value.push(message)
    }
    message.status = value.status
    if (terminal(value.status) || value.output)
      message.content = value.output || ''
  }
  async function refreshAvailability(e = epoch) {
    const value = await api.getAvailability(options())
    if (valid(e)) availability.value = value
  }
  async function refreshProposals() {
    const e = epoch,
      sid = session.value?.id
    if (!sid) return
    const value = await api.getProposals(sid, options())
    if (valid(e) && session.value?.id === sid) {
      proposals.value = value.items
      moreProposals.value = value.has_more
    }
  }
  async function restore(e = epoch) {
    const sid = session.value?.id
    if (!sid) return
    let history = await api.getMessages(sid, options())
    if (history.has_more)
      history = await api.getMessages(sid, {
        ...options(),
        offset: Math.max(0, history.total - 100),
      })
    const cards = await api.getProposals(sid, options())
    if (!valid(e) || session.value?.id !== sid) return
    messages.value = history.items
    olderOffset.value = history.offset
    proposals.value = cards.items
    moreProposals.value = cards.has_more
    const rid = run.value?.id ?? history.items.at(-1)?.run_id
    if (rid) {
      const current = await api.getRun(rid, options())
      if (!valid(e) || session.value?.id !== sid) return
      if (current.session_id !== sid)
        throw new defaultApi.AssistantApiError(
          502,
          'assistant_invalid_response',
        )
      setRun(current)
      const value = await api.getResults(rid, options())
      if (valid(e) && session.value?.id === sid && run.value?.id === rid) {
        results.value = value.items
        truncated.value = value.truncated
      }
    }
  }
  function receive(event: AssistantEvent, e: number, rid: string) {
    if (!valid(e) || run.value?.id !== rid || event.run_id !== rid) return
    if (event.type === 'text_delta' && typeof event.data.delta === 'string') {
      const message = messages.value.find(
        (m) => m.id === run.value!.final_message_id,
      )
      if (message && !terminal(message.status))
        message.content += event.data.delta
    } else if (event.type === 'run_status') {
      if (
        event.data.partial === true &&
        typeof event.data.output === 'string'
      ) {
        const message = messages.value.find(
          (m) => m.id === run.value!.final_message_id,
        )
        if (message) message.content = event.data.output
        return
      }
      const value = event.data as unknown as RunDTO
      if (
        value.id !== rid ||
        value.session_id !== session.value?.id ||
        typeof value.output !== 'string'
      )
        return
      setRun(value)
      if (terminal(value.status)) {
        connected.value = false
        void Promise.all([refreshAvailability(e), refreshProposals()]).catch(
          (c) => {
            if (valid(e)) fail(c)
          },
        )
      }
    } else if (event.type === 'tool_status') {
      const data = event.data
      if (
        typeof data.tool_call_id === 'string' &&
        typeof data.tool_name === 'string' &&
        data.result &&
        typeof data.result === 'object'
      ) {
        const value = data as unknown as ToolResultDTO
        if (!results.value.some((r) => r.tool_call_id === value.tool_call_id))
          results.value.push(value)
        if (value.tool_name.startsWith('propose_'))
          void refreshProposals().catch((c) => {
            if (valid(e)) fail(c)
          })
      } else
        toolStatus.value =
          data.phase === 'started' ? '正在查询媒体库…' : '媒体库查询已返回'
    } else if (event.type === 'error')
      error.value = '回复遇到问题，正在核实任务状态；请稍后重新连接。'
  }
  function attach() {
    if (!run.value || terminal(run.value.status)) return
    stream?.abort()
    stream = new AbortController()
    const controller = stream,
      e = epoch,
      rid = run.value.id
    connected.value = true
    void api
      .subscribeRun(rid, controller.signal, (event) => {
        if (stream === controller && !controller.signal.aborted)
          receive(event, e, rid)
      })
      .then(() => {
        if (valid(e) && stream === controller) {
          connected.value = false
          if (run.value && !terminal(run.value.status))
            error.value = '连接已断开，重新连接可恢复当前任务。'
        }
      })
      .catch((c) => {
        if (valid(e) && stream === controller && !controller.signal.aborted) {
          connected.value = false
          fail(c)
        }
      })
  }
  async function initialize() {
    if (!allowed.value) return
    const e = epoch
    loading.value = true
    error.value = ''
    try {
      const [status, list] = await Promise.all([
        api.getAvailability(options()),
        api.listSessions(options()),
      ])
      if (!valid(e)) return
      availability.value = status
      sessions.value = list.items
      moreSessions.value = list.has_more
      if (status.active_run_id) {
        const value = await api.getRun(status.active_run_id, options())
        if (!valid(e)) return
        session.value = list.items.find((s) => s.id === value.session_id) ?? {
          id: value.session_id,
          title: '恢复的对话',
          state: 'active',
        }
        run.value = value
        await restore(e)
        if (valid(e)) attach()
      } else if (list.items[0]) await selectSession(list.items[0])
    } catch (c) {
      if (valid(e)) fail(c)
    } finally {
      if (valid(e)) loading.value = false
    }
  }
  async function selectSession(value: SessionDTO) {
    invalidate()
    session.value = value
    run.value = null
    messages.value = []
    results.value = []
    proposals.value = []
    truncated.value = false
    toolStatus.value = ''
    error.value = ''
    const e = epoch
    loading.value = true
    try {
      await restore(e)
      if (valid(e) && availability.value.active_run_id) {
        const current = await api.getRun(
          availability.value.active_run_id,
          options(),
        )
        if (valid(e) && current.session_id === value.id) {
          setRun(current)
          attach()
        }
      }
    } catch (c) {
      if (valid(e)) fail(c)
    } finally {
      if (valid(e)) loading.value = false
    }
  }
  async function newSession() {
    if (
      !allowed.value ||
      !availability.value.enabled ||
      loading.value ||
      sending.value
    )
      return
    const e = epoch
    loading.value = true
    try {
      const value = await api.createSession(options())
      if (!valid(e)) return
      sessions.value.unshift(value)
      await selectSession(value)
    } catch (c) {
      if (valid(e)) fail(c)
    } finally {
      if (valid(e)) loading.value = false
    }
  }
  function performSend() {
    if (sendPromise) return sendPromise
    if (!pending.value) return Promise.resolve()
    const request = { ...pending.value },
      e = epoch
    sending.value = true
    error.value = ''
    sendPromise = api
      .sendMessage(request.sid, request.text, request.cid, options())
      .then((value) => {
        if (!valid(e)) return
        pending.value = null
        const inputId = 'input:' + request.cid
        if (!messages.value.some((m) => m.id === inputId))
          messages.value.push({
            id: inputId,
            role: 'user',
            content: request.text,
            run_id: value.id,
            status: value.status,
          })
        setRun(value)
        availability.value = {
          ...availability.value,
          busy: !terminal(value.status),
          active_run_id: !terminal(value.status) ? value.id : null,
        }
        attach()
      })
      .catch((c) => {
        if (valid(e)) fail(c)
      })
      .finally(() => {
        if (valid(e)) {
          sending.value = false
          sendPromise = null
        }
      })
    return sendPromise
  }
  async function send(text: string) {
    if (sending.value) return sendPromise ?? Promise.resolve()
    if (!canSend.value || pending.value) return
    text = text.trim()
    if (!text || text.length > 8000) {
      error.value = '请输入 1～8000 字的消息。'
      return
    }
    if (!session.value) {
      await newSession()
      if (!session.value) return
    }
    pending.value = {
      sid: session.value.id,
      text,
      cid: defaultApi.newClientRequestId(),
    }
    return performSend()
  }
  const retrySend = () =>
    pending.value && allowed.value ? performSend() : Promise.resolve()
  async function reconnect() {
    if (!run.value || !allowed.value) return
    const e = epoch,
      rid = run.value.id
    stream?.abort()
    error.value = ''
    try {
      const value = await api.getRun(rid, options())
      if (!valid(e)) return
      run.value = value
      await restore(e)
      if (valid(e)) {
        await refreshAvailability(e)
        attach()
      }
    } catch (c) {
      if (valid(e)) fail(c)
    }
  }
  async function stop() {
    if (!run.value || !allowed.value) return
    const e = epoch,
      rid = run.value.id
    try {
      const value = await api.stopRun(rid, options())
      if (valid(e)) {
        setRun(value)
        await Promise.all([refreshAvailability(e), refreshProposals()])
      }
    } catch (c) {
      if (valid(e)) fail(c)
    }
  }
  async function clear() {
    if (!session.value || !allowed.value) return
    const sid = session.value.id
    invalidate()
    const e = epoch
    try {
      const value = await api.clearSession(sid, options())
      if (!valid(e)) return
      session.value = value
      stream?.abort()
      messages.value = []
      results.value = []
      proposals.value = []
      run.value = null
      pending.value = null
      if (value.state === 'cleared') {
        sessions.value = sessions.value.filter((s) => s.id !== sid)
        session.value = null
      } else error.value = '清除正在等待任务结束，稍后重新连接可查看进展。'
      await refreshAvailability(e)
    } catch (c) {
      if (valid(e)) fail(c)
    }
  }
  async function loadOlder() {
    if (!session.value || olderOffset.value <= 0) return
    const e = epoch
    const page = await api.getMessages(session.value.id, {
      ...options(),
      offset: Math.max(0, olderOffset.value - 100),
      limit: Math.min(100, olderOffset.value),
    })
    if (valid(e)) {
      const ids = new Set(messages.value.map((m) => m.id))
      messages.value = [
        ...page.items.filter((m) => !ids.has(m.id)),
        ...messages.value,
      ]
      olderOffset.value = page.offset
    }
  }
  async function loadMoreSessions() {
    const e = epoch
    const page = await api.listSessions({
      ...options(),
      offset: sessions.value.length,
    })
    if (valid(e)) {
      sessions.value.push(...page.items)
      moreSessions.value = page.has_more
    }
  }
  async function loadMoreProposals() {
    if (!session.value) return
    const e = epoch
    const page = await api.getProposals(session.value.id, {
      ...options(),
      offset: proposals.value.length,
    })
    if (valid(e)) {
      proposals.value.push(...page.items)
      moreProposals.value = page.has_more
    }
  }
  watch(
    () => [authState.token, authState.user?.id, authState.user?.is_admin],
    () => {
      invalidate()
      sessions.value = []
      session.value = null
      run.value = null
      messages.value = []
      results.value = []
      proposals.value = []
      availability.value = {
        enabled: false,
        busy: false,
        active_run_id: null,
        error_code: null,
      }
    },
  )
  onScopeDispose(() => {
    invalidate()
    alive = false
  })
  return {
    sessions,
    session,
    run,
    messages,
    results,
    proposals,
    availability,
    loading,
    sending,
    connected,
    error,
    toolStatus,
    truncated,
    olderOffset,
    moreSessions,
    moreProposals,
    allowed,
    active,
    canSend,
    initialize,
    selectSession,
    newSession,
    send,
    retrySend,
    reconnect,
    stop,
    clear,
    refreshProposals,
    loadOlder,
    loadMoreSessions,
    loadMoreProposals,
    hasRetry: computed(() => pending.value !== null),
  }
}
