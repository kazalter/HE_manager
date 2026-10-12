import axios from 'axios'
import { API_BASE_URL } from '../config'
export interface DiscardTarget { kind: 'media' | 'external' | 'x_post'; target_id: number }
export interface DiscardPreview {
  title: string; source_type: string; preview_hash: string; media_count: number; file_size: number; scope: string; message: string
  files: Array<{ relative_path: string; exists: boolean; is_directory: boolean }>
}
export interface DiscardRecord {
  id: string; title: string; source_type: string; status: 'discarded'; discarded_at: string
  media_count: number; file_size: number; media_ids: number[]; cleanup_status: string; cleanup_error: string | null
}
export const previewDiscard = async (target: DiscardTarget, signal: AbortSignal) =>
  (await axios.post<DiscardPreview>(`${API_BASE_URL}/discard/preview`, target, { signal })).data
export const executeDiscard = async (target: DiscardTarget, preview_hash: string) =>
  (await axios.post<DiscardRecord>(`${API_BASE_URL}/discard`, { ...target, confirm: true, preview_hash })).data
export const formatBytes = (size: number) => {
  if (!size) return '无本地媒体文件'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']; const i = Math.min(4, Math.floor(Math.log(size) / Math.log(1024)))
  return `${Number((size / 1024 ** i).toFixed(1))} ${units[i]}`
}
