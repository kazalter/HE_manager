export interface Page<T> {
  items: T[]
  total: number
  offset: number
  has_more: boolean
}
export interface SessionDTO {
  id: string
  title: string
  state: string
  created_at?: string
  updated_at?: string
  error_code?: string | null
}
export interface RunDTO {
  id: string
  session_id: string
  status: string
  final_message_id: string
  output: string
  usage: Record<string, number> | null
  error_code: string | null
}
export interface AvailabilityDTO {
  enabled: boolean
  busy: boolean
  active_run_id: string | null
  error_code: string | null
}
export interface MessageDTO {
  id: string
  role: 'user' | 'assistant'
  content: string
  run_id: string
  status: string
}
export interface ToolResultDTO {
  tool_call_id: string
  tool_name: string
  result: Record<string, unknown>
}
export interface ToolResultsDTO {
  items: ToolResultDTO[]
  truncated: boolean
}
export interface JobDTO {
  job_id: string
  folder_id: number | null
  kind?: string
  progress?: number | null
  status: string
  message: string | null
  created_at: string
  finished_at: string | null
}
export interface ActionResultDTO {
  proposal_id: string
  state: string
  media_id?: number | null
  job_id?: string | null
  job?: JobDTO | null
}
export interface ProposalDTO {
  id: string
  session_id: string
  kind: 'media_update' | 'scan' | 'media_batch_update' | 'tag_rename' | 'tag_merge' | 'maintenance' | 'file_move'
  target_id: number | null
  reason?: string
  session_title?: string
  impact_count?: number
  reversibility?: string
  targets?: { type: string; id: number | null; label: string }[]
  target_label: string
  state: string
  expires_at: string
  payload_hash: string
  before: Record<string, unknown>
  after: Record<string, unknown>
  result: ActionResultDTO | null
}
export interface AssistantEvent {
  event_id: string
  type: 'text_delta' | 'tool_status' | 'run_status' | 'error'
  run_id: string
  message_id: string | null
  data: Record<string, unknown>
}
export interface RequestOptions {
  signal?: AbortSignal
  offset?: number
  limit?: number
}

export interface ApprovalPageDTO extends Page<ProposalDTO> { pending_count: number }
export interface CapabilitiesDTO {
  read_tools: string[]
  proposal_tools: string[]
  file_roots: { id: number; display_name: string; path: string; readable: boolean }[]
  image_analysis_supported: boolean
  writes_require_approval: true
}
