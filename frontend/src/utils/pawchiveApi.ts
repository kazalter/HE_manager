import axios from 'axios'
import { API_BASE_URL, authUrl } from '../config'
import type { PawchiveAccountStatus, PawchiveCapabilities, PawchiveCreatorFavorite, PawchiveDownloadJob, PawchiveDownloadPreview, PawchiveDownloadSelection, PawchivePage, PawchivePost, PawchiveScope } from '../types/pawchive'

const root = `${API_BASE_URL}/external/pawchive`

export const pawchiveMediaUrl = (ref: string | null | undefined) =>
  ref ? authUrl(`${root}/media/${encodeURIComponent(ref)}`) : ''

export async function fetchPawchiveCapabilities(signal?: AbortSignal): Promise<PawchiveCapabilities> {
  const response = await axios.get<PawchiveCapabilities>(`${root}/capabilities`, { signal })
  return response.data
}

export async function fetchPawchiveAccountStatus(signal?: AbortSignal): Promise<PawchiveAccountStatus> {
  const response = await axios.get<PawchiveAccountStatus>(`${root}/account/status`, { signal })
  return response.data
}

export async function loginPawchiveAccount(username: string, password: string): Promise<{ connected: boolean; items: PawchiveCreatorFavorite[] }> {
  const response = await axios.post(`${root}/account/login`, { username, password })
  return response.data
}

export async function logoutPawchiveAccount(): Promise<void> {
  await axios.delete(`${root}/account/session`)
}

export async function fetchPawchiveAccountFavorites(signal?: AbortSignal): Promise<PawchiveCreatorFavorite[]> {
  const response = await axios.get<{ items: PawchiveCreatorFavorite[] }>(`${root}/account/favorites`, { signal })
  return response.data.items
}

export async function setPawchiveAccountFavorite(creator: Pick<PawchiveCreatorFavorite, 'service' | 'creator_id'>): Promise<void> {
  await axios.put(`${root}/account/favorites/${encodeURIComponent(creator.service)}/${encodeURIComponent(creator.creator_id)}`)
}

export async function removePawchiveAccountFavorite(creator: Pick<PawchiveCreatorFavorite, 'service' | 'creator_id'>): Promise<void> {
  await axios.delete(`${root}/account/favorites/${encodeURIComponent(creator.service)}/${encodeURIComponent(creator.creator_id)}`)
}

export async function fetchPawchivePosts(scope: PawchiveScope, cursor = '', signal?: AbortSignal): Promise<PawchivePage> {
  const response = await axios.get<PawchivePage>(`${root}/posts`, {
    params: {
      q: scope.query || undefined,
      service: scope.service || undefined,
      creator_id: scope.creatorId || undefined,
      tag: scope.tag || undefined,
      media_type: scope.mediaType,
      cursor: cursor || undefined,
    },
    signal,
  })
  return response.data
}

export async function fetchPawchivePost(post: Pick<PawchivePost, 'service' | 'creator_id' | 'post_id'>, signal?: AbortSignal): Promise<PawchivePost> {
  const { service, creator_id, post_id } = post
  const response = await axios.get<PawchivePost>(`${root}/posts/${encodeURIComponent(service)}/${encodeURIComponent(creator_id)}/${encodeURIComponent(post_id)}`, { signal })
  return response.data
}

export function pawchiveError(error: unknown): string {
  if (axios.isCancel(error)) return ''
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail
    if (typeof detail?.message === 'string') return detail.message
    if (error.response?.status === 429) return '来源站点请求过快，请稍后重试。'
    if (error.response?.status === 403) return '来源站点限制访问。'
    if (error.response?.status === 503) return 'Pawchive 模块尚未启用。'
  }
  return '暂时无法读取 Pawchive，请稍后重试。'
}

export async function previewPawchiveDownload(selections: PawchiveDownloadSelection[]): Promise<PawchiveDownloadPreview> {
  const response = await axios.post<PawchiveDownloadPreview>(`${root}/downloads/preview`, { selections })
  return response.data
}

export async function createPawchiveDownload(selections: PawchiveDownloadSelection[]): Promise<{ job_id: string | null; status: string; queued: number }> {
  const response = await axios.post(`${root}/downloads`, { selections })
  return response.data
}

export async function listPawchiveDownloads(): Promise<PawchiveDownloadJob[]> {
  const response = await axios.get<{ items: PawchiveDownloadJob[] }>(`${root}/downloads`)
  return response.data.items
}

export async function getPawchiveDownload(jobId: string): Promise<PawchiveDownloadJob> {
  const response = await axios.get<PawchiveDownloadJob>(`${root}/downloads/${encodeURIComponent(jobId)}`)
  return response.data
}

export async function cancelPawchiveDownload(jobId: string): Promise<void> {
  await axios.post(`${root}/downloads/${encodeURIComponent(jobId)}/cancel`)
}

export async function retryPawchiveDownload(jobId: string): Promise<void> {
  await axios.post(`${root}/downloads/${encodeURIComponent(jobId)}/retry`)
}
