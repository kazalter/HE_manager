import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import axios, { type InternalAxiosRequestConfig } from 'axios'
vi.mock('../desktop', () => ({ desktopBridge: {}, desktopSession: reactive({ server: 'https://one.example', generation: 'store-one', revision: 1 }) }))
import { desktopSession } from '../desktop'
import { authState } from '../auth'
import { externalDownloadStore } from '../stores/externalDownloadStore'
import { dedupStore } from '../stores/dedupStore'
import { xImportStore } from '../stores/xImportStore'
import { asmrDownloadStore } from '../stores/asmrDownloadStore'
const account = (id: number) => ({ id, username: 'user-' + id, is_admin: false, is_active: true, created_at: '' })
const key = (id: number, server = 'https://one.example') => 'he-manager:external-download-job-id:desktop:' + encodeURIComponent(JSON.stringify([server, id]))
const requests: InternalAxiosRequestConfig[] = []
let resolveOld!: (value: any) => void
let originalAdapter: typeof axios.defaults.adapter
beforeEach(async () => {
  originalAdapter = axios.defaults.adapter; requests.length = 0; localStorage.clear()
  Object.assign(desktopSession, { server: 'https://one.example', generation: 'store-one' }); authState.user = account(1)
  axios.defaults.adapter = async config => {
    requests.push(config)
    if (config.url === '/external/wnacg/downloads' && config.headers.get('X-HE-Generation') === 'store-one') return new Promise(resolve => { resolveOld = resolve })
    return { data: { job_id: 'job-two', status: 'completed' }, status: 200, statusText: 'OK', headers: {}, config }
  }
  // Eagerly create the account-bound clients after installing this adapter.
  externalDownloadStore.clearError(); dedupStore.clearError(); asmrDownloadStore.clearError(); xImportStore.clearError()
  await flushPromises()
})
afterEach(async () => { authState.user = null; await flushPromises(); axios.defaults.adapter = originalAdapter; vi.restoreAllMocks() })
it('keeps a late old job response, storage writes and polling out of the new account', async () => {
  const old = externalDownloadStore.startDownload([1], '/synthetic')
  const rejected = expect(old).rejects.toMatchObject({ code: 'ERR_CANCELED' })
  await flushPromises()
  const oldRequest = requests[0]!
  Object.assign(desktopSession, { generation: 'store-two' }); authState.user = account(2)
  expect(externalDownloadStore.state.job).toBeNull()
  await externalDownloadStore.startDownload([2], '/synthetic'); await flushPromises()
  expect(externalDownloadStore.state.job?.job_id).toBe('job-two')
  expect(localStorage.getItem(key(2))).toBe('job-two')
  resolveOld({ data: { job_id: 'job-one', status: 'running' }, status: 200, statusText: 'OK', headers: {}, config: oldRequest })
  await rejected; await flushPromises()
  expect(oldRequest.signal?.aborted).toBe(true)
  expect(externalDownloadStore.state.job?.job_id).toBe('job-two')
  expect(externalDownloadStore.state.errorMessage).toBe('')
  expect(localStorage.getItem(key(1))).toBeNull()
  expect(localStorage.getItem(key(2))).toBe('job-two')
  expect(requests.some(request => request.url?.includes('job-one'))).toBe(false)
})
it('restores only this server/account job key; old global desktop keys are not adopted', async () => {
  localStorage.setItem('he-manager:external-download-job-id', 'legacy-other-account')
  localStorage.setItem(key(2), 'job-two')
  desktopSession.generation = 'store-two'; authState.user = account(2)
  externalDownloadStore.ensureResumed(); await flushPromises()
  expect(requests.map(request => request.url)).toContain('/external/downloads/job-two')
  expect(requests.some(request => request.url?.includes('legacy-other-account'))).toBe(false)
  requests.length = 0
  desktopSession.server = 'https://two.example'; desktopSession.generation = 'another-server'
  externalDownloadStore.ensureResumed(); await flushPromises()
  expect(requests).toEqual([])
  expect(externalDownloadStore.state.job).toBeNull()
})
it('replaces all four singleton state closures on identity change', async () => {
  dedupStore.state.errorMessage = 'private duplicate state'
  xImportStore.setError('private import state')
  asmrDownloadStore.state.errorMessage = 'private ASMR state'
  externalDownloadStore.setError('private download state')
  desktopSession.generation = 'store-two'; authState.user = account(2)
  expect(dedupStore.state.errorMessage).toBe('')
  expect(xImportStore.state.errorMessage).toBe('')
  expect(asmrDownloadStore.state.errorMessage).toBe('')
  expect(externalDownloadStore.state.errorMessage).toBe('')
})
