export type PawchiveMediaType = 'all' | 'image' | 'video'

export interface PawchiveScope {
  query: string
  service: string
  creatorId: string
  tag: string
  mediaType: PawchiveMediaType
}

export interface PawchiveAttachment {
  attachment_key: string
  original_index: number
  filename: string
  media_type: 'image' | 'video' | 'unsupported'
  mime_type: string | null
  stream_ref: string | null
  preview_ref: string | null
  availability: 'playable' | 'unsupported'
}

export interface PawchivePost {
  post_key: string
  service: string
  creator_id: string
  post_id: string
  title: string
  creator_name: string
  source_url: string
  published_at: string | null
  reported_attachment_count: number
  playable_count: number | null
  /** Counted from the list entry; absent on responses from older backends. */
  image_count?: number
  video_count?: number
  preview_ref: string | null
  tags: string[]
  attachments: PawchiveAttachment[]
}

export interface PawchivePage {
  items: PawchivePost[]
  next_cursor: string | null
  has_more: boolean
  total: number | null
  applied_filters: Record<string, string>
  filter_scope: string
  warnings: string[]
}

export interface PawchiveCapabilities {
  search: boolean
  creator_scope: boolean
  creator_search: boolean
  global_tags: boolean
  creator_tags: boolean
  media_filter: string
  sort: string[]
  image: boolean
  video: string[]
}

export interface PawchiveCreator {
  service: string
  creator_id: string
  creator_name: string
  source_url: string
  updated_at?: string | null
  banner_url?: string
  icon_url?: string
}

export interface PawchiveCreatorFavorite extends PawchiveCreator {
  created_at?: string | null
}

export interface PawchiveAccountStatus {
  connected: boolean
}

export interface PawchiveDownloadSelection {
  service: string
  creator_id: string
  post_id: string
  attachment_keys?: string[]
}

export interface PawchiveDownloadPreview {
  selected_posts: number
  supported: number
  unsupported: number
  already_downloaded: number
  unknown_size: number
}

export interface PawchiveDownloadAttachment {
  attachment_key: string
  filename: string
  status: string
  error: string | null
  media_id: number | null
  file_size: number | null
  post_key?: string
}

export interface PawchiveDownloadJob {
  job_id: string
  status: string
  total: number
  completed: number
  failed: number
  canceled: number
  message: string
  attachments: PawchiveDownloadAttachment[]
}
