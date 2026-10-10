import { authState, expireAuth } from '../auth'
import { API_BASE_URL } from '../config'
import type {
  ActionResultDTO,
  AssistantEvent,
  AvailabilityDTO,
  JobDTO,
  Page,
  ProposalDTO,
  RunDTO,
  SessionDTO,
  MessageDTO,
  ToolResultsDTO,
  RequestOptions,
} from '../types/assistant'

export class AssistantApiError extends Error {
  status: number
  code: string
  constructor(status: number, code = 'assistant_unavailable') {
    super(code)
    this.status = status
    this.code = code
  }
}
export function newClientRequestId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  // getRandomValues also works on HTTP LAN origins, unlike randomUUID.
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6]! & 0x0f) | 0x40
  bytes[8] = (bytes[8]! & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
const pathId = (id: string) => encodeURIComponent(id)
export function utcTime(value: string) {
  return Date.parse(/[zZ]$|[+-]\d{2}:\d{2}$/.test(value) ? value : value + 'Z')
}
function headers() {
  if (!authState.token)
    throw new AssistantApiError(401, 'assistant_login_required')
  return {
    Authorization: 'Bearer ' + authState.token,
    'Content-Type': 'application/json',
  }
}
async function check(response: Response, token: string) {
  if (response.status === 401 && authState.token === token) expireAuth()
  if (!response.ok) {
    await response.body?.cancel()
    throw new AssistantApiError(
      response.status,
      response.status === 409 ? 'assistant_conflict' : 'assistant_unavailable',
    )
  }
}
async function json<T>(
  path: string,
  method = 'GET',
  body?: unknown,
  opts: RequestOptions = {},
): Promise<T> {
  const token = authState.token,
    controller = new AbortController()
  const abort = () => controller.abort()
  opts.signal?.addEventListener('abort', abort, { once: true })
  if (opts.signal?.aborted) controller.abort()
  const timer = setTimeout(abort, 30000)
  try {
    const response = await fetch(API_BASE_URL + '/assistant' + path, {
      method,
      headers: headers(),
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
    await check(response, token)
    const reader = response.body?.getReader()
    if (!reader) throw new AssistantApiError(502, 'assistant_invalid_response')
    const chunks: Uint8Array[] = []
    let size = 0
    try {
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        size += value.byteLength
        if (size > 8 * 1024 * 1024)
          throw new AssistantApiError(502, 'assistant_response_too_large')
        chunks.push(value)
      }
    } finally {
      await reader.cancel()
      reader.releaseLock()
    }
    const bytes = new Uint8Array(size)
    let offset = 0
    for (const chunk of chunks) {
      bytes.set(chunk, offset)
      offset += chunk.length
    }
    try {
      return JSON.parse(
        new TextDecoder('utf-8', { fatal: true }).decode(bytes),
      ) as T
    } catch {
      throw new AssistantApiError(502, 'assistant_invalid_response')
    }
  } finally {
    clearTimeout(timer)
    opts.signal?.removeEventListener('abort', abort)
  }
}
function query(opts: RequestOptions, defaultLimit: number) {
  return (
    '?limit=' +
    Math.min(defaultLimit, Math.max(1, opts.limit ?? defaultLimit)) +
    '&offset=' +
    Math.max(0, opts.offset ?? 0)
  )
}
export const getAvailability = (opts: RequestOptions = {}) =>
  json<AvailabilityDTO>('/status', 'GET', undefined, opts)
export const listSessions = (opts: RequestOptions = {}) =>
  json<Page<SessionDTO>>('/sessions' + query(opts, 100), 'GET', undefined, opts)
export const createSession = (opts: RequestOptions = {}) =>
  json<SessionDTO>('/sessions', 'POST', { title: '新对话' }, opts)
export const getMessages = (id: string, opts: RequestOptions = {}) =>
  json<Page<MessageDTO>>(
    '/sessions/' + pathId(id) + '/messages' + query(opts, 100),
    'GET',
    undefined,
    opts,
  )
export const getProposals = (id: string, opts: RequestOptions = {}) =>
  json<Page<ProposalDTO>>(
    '/sessions/' + pathId(id) + '/proposals' + query(opts, 50),
    'GET',
    undefined,
    opts,
  )
export const sendMessage = (
  id: string,
  text: string,
  clientRequestId: string,
  opts: RequestOptions = {},
) =>
  json<RunDTO>(
    '/sessions/' + pathId(id) + '/runs',
    'POST',
    { input: text, client_request_id: clientRequestId },
    opts,
  )
export const getRun = (id: string, opts: RequestOptions = {}) =>
  json<RunDTO>('/runs/' + pathId(id), 'GET', undefined, opts)
export const getResults = (id: string, opts: RequestOptions = {}) =>
  json<ToolResultsDTO>(
    '/runs/' + pathId(id) + '/results',
    'GET',
    undefined,
    opts,
  )
export const stopRun = (id: string, opts: RequestOptions = {}) =>
  json<RunDTO>('/runs/' + pathId(id) + '/stop', 'POST', undefined, opts)
export const clearSession = (id: string, opts: RequestOptions = {}) =>
  json<SessionDTO>('/sessions/' + pathId(id), 'DELETE', undefined, opts)
export const confirmProposal = (
  id: string,
  payloadHash: string,
  opts: RequestOptions = {},
) =>
  json<ActionResultDTO>(
    '/proposals/' + pathId(id) + '/confirm',
    'POST',
    { payload_hash: payloadHash },
    opts,
  )
export const rejectProposal = (id: string, opts: RequestOptions = {}) =>
  json<ProposalDTO>(
    '/proposals/' + pathId(id) + '/reject',
    'POST',
    undefined,
    opts,
  )
export const getJob = (id: string, opts: RequestOptions = {}) =>
  json<JobDTO>('/jobs/' + pathId(id), 'GET', undefined, opts)

export async function subscribeRun(
  runId: string,
  signal: AbortSignal,
  onEvent: (event: AssistantEvent) => void,
  lastEventId?: string,
): Promise<void> {
  const token = authState.token
  const requestHeaders: Record<string, string> = headers()
  requestHeaders.Accept = 'text/event-stream'
  if (lastEventId && /^[0-9]{1,20}$/.test(lastEventId))
    requestHeaders['Last-Event-ID'] = lastEventId
  const response = await fetch(
    API_BASE_URL + '/assistant/runs/' + pathId(runId) + '/events',
    {
      headers: requestHeaders,
      signal,
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
    },
  )
  await check(response, token)
  const reader = response.body?.getReader()
  if (!reader) throw new AssistantApiError(502, 'assistant_invalid_response')
  const decoder = new TextDecoder('utf-8', { fatal: true })
  let line = '',
    lines: string[] = [],
    size = 0,
    first = true,
    cursor = -1n
  function deliver() {
    const data = lines
      .filter((l) => l.startsWith('data:'))
      .map((l) => l.slice(5).replace(/^ /, ''))
      .join('\n')
    const id = lines
      .find((l) => l.startsWith('id:'))
      ?.slice(3)
      .trim()
    lines = []
    size = 0
    if (!data) return
    let event: AssistantEvent
    try {
      event = JSON.parse(data)
    } catch {
      throw new AssistantApiError(502, 'assistant_invalid_stream')
    }
    if (
      !event ||
      event.run_id !== runId ||
      !['text_delta', 'tool_status', 'run_status', 'error'].includes(
        event.type,
      ) ||
      typeof event.event_id !== 'string' ||
      event.event_id.length > 100 ||
      !event.data ||
      typeof event.data !== 'object' ||
      Array.isArray(event.data)
    )
      throw new AssistantApiError(502, 'assistant_invalid_stream')
    if (id && /^[0-9]{1,20}$/.test(id)) {
      const next = BigInt(id)
      if (id !== event.event_id)
        throw new AssistantApiError(502, 'assistant_invalid_stream')
      if (next <= cursor) return
      cursor = next
    }
    if (!signal.aborted && authState.token === token) onEvent(event)
  }
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      let start = 0
      while (start < value.length) {
        let end = value.indexOf(10, start)
        end = end < 0 ? value.length : end + 1
        const piece = value.subarray(start, end)
        size += piece.byteLength
        if (size > 128 * 1024)
          throw new AssistantApiError(502, 'assistant_stream_too_large')
        line += decoder.decode(piece, { stream: true })
        start = end
        if (!line.endsWith('\n')) continue
        let completed = line.slice(0, -1).replace(/\r$/, '')
        line = ''
        if (first) {
          completed = completed.replace(/^\uFEFF/, '')
          first = false
        }
        if (!completed) deliver()
        else if (!completed.startsWith(':')) lines.push(completed)
      }
    }
    line += decoder.decode()
    if (line) lines.push(line)
    if (lines.length) deliver()
  } finally {
    await reader.cancel()
    reader.releaseLock()
  }
}
