"""Shared narrow schemas. Public requests never carry provider or identity secrets."""

from __future__ import annotations
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

PositiveID = Annotated[int, Field(gt=0, strict=True)]
Count = Annotated[int, Field(ge=0, strict=True)]
Limit = Annotated[int, Field(ge=1, le=50, strict=True)]
MediaType = Literal["video", "manga", "image", "audio"]
ToolName = Literal[
    "search_media",
    "get_media_detail",
    "get_library_stats",
    "recommend_media",
    "list_duplicate_candidates",
    "list_tags",
    "list_folders",
    "propose_media_update",
    "list_creators",
    "get_creator_detail",
    "list_tasks",
    "get_task_detail",
    "get_project_status",
    "get_project_settings",
    "list_directory",
    "read_text",
    "get_media_preview",
    "read_logs",
    "propose_media_batch_update",
    "propose_tag_rename",
    "propose_tag_merge",
    "propose_maintenance",
    "propose_file_move",
    "propose_scan",
]


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ToolErrorDTO(DTO):
    code: str
    message: str
    request_id: str


class ToolContext(DTO):
    session_id: UUID
    run_id: UUID


class ToolPrincipal(DTO):
    user_id: PositiveID
    profile_name: str


class ProfileBinding(DTO):
    model_config = ConfigDict(extra="forbid", frozen=True)
    user_id: PositiveID
    profile_name: str
    api_key: SecretStr = Field(repr=False)
    api_key_generation: PositiveID
    tool_token_hash: str


class SubmissionEnvelope(DTO):
    model_config = ConfigDict(extra="forbid", frozen=True)
    input: str = Field(min_length=1, max_length=8000)
    instructions: str = Field(max_length=16000)
    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=100)
    idempotency_key: str = Field(min_length=1, max_length=100)
    api_key_generation: PositiveID
    max_turns: Literal[8] = 8
    output_tokens: Literal[2048] = 2048
    deadline_seconds: Literal[180] = 180


class RunRequest(DTO):
    input: str = Field(min_length=1, max_length=8000)
    client_request_id: UUID


class SessionRequest(DTO):
    title: str = Field(default="新对话", min_length=1, max_length=100)


class PageQuery(DTO):
    limit: Limit = 20
    offset: Count = 0


class ScopeQuery(DTO):
    scope: Literal["normal", "all", "missing", "duplicate", "checking"] = "normal"


class MediaQuery(PageQuery):
    scope: Literal["normal", "all", "missing", "duplicate", "checking"] = "normal"
    sort: Literal["id_desc", "title"] = "id_desc"
    query: str = Field(default="", max_length=4000)
    media_type: MediaType | None = None
    tag: str | None = Field(default=None, max_length=80)
    favorite: Annotated[bool, Field(strict=True)] | None = None
    view_status: Literal["unviewed", "viewing", "viewed"] | None = None


class RecommendationQuery(DTO):
    query: str = Field(default="", max_length=4000)
    media_type: MediaType | None = None
    limit: Limit = 12
    avoid_tags: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=20
    )
    preferred_tags: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        default_factory=list, max_length=20
    )
    seed: PositiveID | None = None


class TagInput(DTO):
    name: str = Field(min_length=1, max_length=80)
    namespace: str = Field(default="general", min_length=1, max_length=40)

    @field_validator("name", "namespace", mode="before")
    @classmethod
    def normalize(cls, value, info):
        if not isinstance(value, str):
            raise ValueError("tag requires text")
        return value.strip() or ("general" if info.field_name == "namespace" else "")


class MediaPatch(DTO):
    title: str | None = Field(default=None,min_length=1,max_length=500)
    artist: str | None = Field(default=None,max_length=500)
    view_status: Literal["unviewed","viewing","viewed"] | None = None
    rating: Annotated[int, Field(ge=0, le=5, strict=True)] | None = None
    favorite: Annotated[bool, Field(strict=True)] | None = None
    source_url: str | None = Field(default=None, max_length=2000)
    add_tags: list[TagInput] = Field(default_factory=list, max_length=20)
    remove_tag_ids: list[PositiveID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def nullability(self):
        if any(
            name in self.model_fields_set and getattr(self, name) is None
            for name in ("rating", "favorite", "title", "view_status")
        ):
            raise ValueError("only source_url and artist can be cleared")
        return self

    @field_validator("source_url")
    @classmethod
    def safe_source(cls, value):
        if value is None:
            return value
        try:
            parts = urlsplit(value)
            blocked = {
                "token",
                "key",
                "api_key",
                "apikey",
                "access_token",
                "auth",
                "authorization",
                "password",
                "secret",
                "signature",
                "sig",
                "credential",
                "credentials",
            }
            if (
                parts.scheme not in ("http", "https")
                or not parts.hostname
                or parts.username
                or parts.password
                or parts.fragment
                or any(
                    k.lower() in blocked or k.lower().startswith(("x-amz-", "x-goog-"))
                    for k, _ in parse_qsl(parts.query)
                )
            ):
                raise ValueError
            _ = parts.port
            if any(ord(c) < 32 for c in value):
                raise ValueError
        except ValueError:
            raise ValueError("source URL contains credentials or is invalid") from None
        return value


class TagDTO(DTO):
    id: PositiveID
    name: str = Field(max_length=80)
    namespace: str = Field(max_length=40)
    count: Count = 0


class MediaDetailDTO(DTO):
    id: PositiveID
    title: str = Field(max_length=500)
    media_type: MediaType
    artist: str | None = Field(default=None, max_length=500)
    tags: list[TagDTO] = Field(default_factory=list, max_length=50)
    rating: Annotated[int, Field(ge=0, le=5)] = 0
    favorite: bool = False
    view_status: str = "unviewed"
    duration: Count | None = None
    page_count: Count | None = None
    source_site: str | None = Field(default=None, max_length=100)
    folder_id: PositiveID | None = None
    absolute_path: str | None = None
    relative_path: str | None = None
    file_size: Count | None = None
    progress: Count = 0
    is_missing: bool = False
    duplicate_status: str = "unique"
    source_url: str | None = None
    truncated: bool = False


class MediaPageDTO(DTO):
    items: list[MediaDetailDTO] = Field(max_length=50)
    total: Count
    offset: Count = 0
    has_more: bool = False
    next_offset: Count | None = None
    truncated: bool = False


class RecommendationDTO(DTO):
    items: list[MediaDetailDTO] = Field(max_length=50)
    basis: str = Field(max_length=2000)
    method: Literal["manga_retrieval", "metadata_filter"]
    truncated: bool = False


class StatsDTO(DTO):
    scope: str = "normal"
    total: Count
    by_type: dict[MediaType, Count]
    favorite_count: Count
    watched_count: Count


class DuplicateDTO(DTO):
    id: PositiveID
    media_ids: list[PositiveID] = Field(max_length=50)
    titles: list[Annotated[str, Field(max_length=500)]] = Field(max_length=50)
    score: float
    basis: str = Field(max_length=2000)


class DuplicatePageDTO(DTO):
    items: list[DuplicateDTO] = Field(max_length=50)
    total: Count
    offset: Count = 0
    has_more: bool = False
    next_offset: Count | None = None
    truncated: bool = False


class TagPageDTO(DTO):
    items: list[TagDTO] = Field(max_length=50)
    total: Count
    offset: Count = 0
    has_more: bool = False
    next_offset: Count | None = None


class FolderDTO(DTO):
    path: str | None = None
    readable: bool = False
    id: PositiveID
    display_name: str = Field(max_length=500)
    status: str = Field(max_length=80)


class FolderPageDTO(DTO):
    items: list[FolderDTO] = Field(max_length=50)
    total: Count
    offset: Count = 0
    has_more: bool = False
    next_offset: Count | None = None


class ProposalAckDTO(DTO):
    reason: str = ""
    impact_count: Count = 1
    reversibility: str = "需重新审批"
    id: UUID
    kind: Literal["media_update", "scan", "media_batch_update", "tag_rename", "tag_merge", "maintenance", "file_move"]
    target_id: Count | None
    target_label: str = Field(max_length=500)
    state: Literal["pending", "applied", "queued", "rejected", "expired", "stale"]
    expires_at: datetime


class JobDTO(DTO):
    kind: str = "scan"
    progress: float | None = None
    job_id: str
    folder_id: PositiveID | None = None
    status: str
    message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class ActionResultDTO(DTO):
    items: list[dict] = Field(default_factory=list)
    proposal_id: UUID
    state: str
    media_id: PositiveID | None = None
    job_id: str | None = None
    job: JobDTO | None = None


class ProposalDTO(ProposalAckDTO):
    targets: list[dict] = Field(default_factory=list)
    session_id: UUID
    before: dict
    after: dict
    payload_hash: str
    result: ActionResultDTO | None = None


class TruncatedDTO(DTO):
    truncated: Literal[True] = True
    reason: Literal["tool_result_too_large"] = "tool_result_too_large"


class CreatorQuery(PageQuery):
    search: str = Field(default="", max_length=500)
class CreatorDetailQuery(PageQuery):
    key: str = Field(min_length=3, max_length=502)
class TaskQuery(PageQuery):
    kind: str | None = Field(default=None, max_length=80)
class TaskDetailQuery(DTO):
    task_id: str = Field(min_length=1, max_length=150)
class CreatorDTO(DTO):
    key: str
    name: str
    media_count: Count
class CreatorPageDTO(DTO):
    items: list[CreatorDTO] = Field(max_length=50)
    total: Count
    offset: Count
    has_more: bool
    next_offset: Count | None = None
class CreatorDetailDTO(MediaPageDTO):
    key: str
    name: str
class TaskDTO(DTO):
    task_id: str
    kind: str
    status: str
    progress: float | None = None
    created_at: datetime
    finished_at: datetime | None = None
    summary: str
class TaskPageDTO(DTO):
    items: list[TaskDTO] = Field(max_length=50)
    total: Count
    offset: Count
    has_more: bool
    next_offset: Count | None = None
class StorageDTO(DTO):
    folder_id: PositiveID
    path: str
    available: bool
    total_bytes: Count | None = None
    free_bytes: Count | None = None
class BackupEntryDTO(DTO):
    name: str
    size_bytes: Count
    modified_at: str
class ProjectStatusDTO(DTO):
    health: Literal["ok"] = "ok"
    storage: list[StorageDTO] = Field(max_length=50)
    backup: list[BackupEntryDTO] = Field(max_length=50)
    backup_count: Count
    truncated: bool = False
class FolderSettingDTO(DTO):
    id: PositiveID
    scan_mode: str
    thumbnail_enabled: bool
    thumbnail_interval: Count
class ProjectSettingsDTO(DTO):
    folders: list[FolderSettingDTO] = Field(max_length=50)
    total: Count
    offset: Count
    has_more: bool
    next_offset: Count | None = None


class DirectoryQuery(PageQuery):
    folder_id: PositiveID
    relative_path: str = Field(default="", max_length=4096)
class TextQuery(DTO):
    folder_id: PositiveID
    relative_path: str = Field(min_length=1, max_length=4096)
    offset_bytes: Count = 0
class PreviewQuery(DTO):
    media_id: PositiveID
    page_index: Count = 0
class DirectoryEntryDTO(DTO):
    name: str
    relative_path: str
    entry_type: Literal["file", "directory", "link"]
    size: Count | None = None
    modified_at: datetime
    media_id: PositiveID | None = None
class DirectoryPageDTO(DTO):
    items: list[DirectoryEntryDTO] = Field(max_length=50)
    total: Count
    offset: Count
    has_more: bool
    next_offset: Count | None = None
class TextChunkDTO(DTO):
    folder_id: PositiveID
    relative_path: str
    text: str
    offset_bytes: Count
    next_offset_bytes: Count | None = None
    truncated: bool
    encoding: Literal["utf-8"] = "utf-8"
class PreviewDTO(DTO):
    media_id: PositiveID
    media_type: MediaType
    page_index: Count | None = None
    page_count: Count | None = None
    preview_path: str
    analysis_supported: bool = False
    analysis_performed: bool = False
    notice: str = "可在网页查看预览；当前模型未分析文件内容。"


class LogQuery(DTO):
    source: Literal["all", "assistant", "scan", "download", "auto_sync", "import", "runtime"] = "all"
    cursor: str | None = Field(default=None,max_length=200)
    limit: Annotated[int,Field(ge=1,le=200,strict=True)] = 50
class LogEventDTO(DTO):
    timestamp: str
    service: str
    level: str
    code: str
    object_id: str | None = None
    summary: str
    request_id: str | None = None
    cursor: str
class LogPageDTO(DTO):
    items: list[LogEventDTO] = Field(max_length=200)
    cursor: str | None = None
    next_cursor: str | None = None
    has_more: bool
    truncated: bool = False


class BatchPatchItem(DTO):
    media_id: PositiveID
    patch: MediaPatch
class ProposalReason(DTO):
    reason: str = Field(default="",max_length=1000)
class BatchUpdateArgs(ProposalReason):
    items: list[BatchPatchItem] = Field(min_length=1,max_length=50)
    @model_validator(mode="after")
    def unique_ids(self):
        if len({x.media_id for x in self.items})!=len(self.items):raise ValueError("duplicate media IDs")
        return self
class TagRenameArgs(ProposalReason):
    tag_id: PositiveID
    name: str = Field(min_length=1,max_length=80)
    namespace: str | None = Field(default=None,min_length=1,max_length=40)
class TagMergeArgs(ProposalReason):
    source_tag_id: PositiveID
    target_tag_id: PositiveID
class MaintenanceArgs(ProposalReason):
    action: Literal["recheck_missing","recheck_duplicates","regenerate_thumbnail","backup_database"]
    media_ids: list[PositiveID] = Field(default_factory=list,max_length=50)
    all_media: bool = False
class FileMoveArgs(ProposalReason):
    media_id: PositiveID
    destination_folder_id: PositiveID
    destination_relative_path: str = Field(min_length=1,max_length=4096)
class OperationPreviewDTO(DTO):
    kind: str
    target_id: Count = 0
    label: str
    targets: list[dict]
    before: dict
    after: dict
    fingerprint: str
    impact_count: Count
    reversibility: str = "需重新审批"
class SelectionRequest(DTO):
    selected_target_ids: list[PositiveID] = Field(min_length=1,max_length=50)


RESULT_TYPES = {
    "search_media": MediaPageDTO,
    "get_media_detail": MediaDetailDTO,
    "get_library_stats": StatsDTO,
    "recommend_media": RecommendationDTO,
    "list_duplicate_candidates": DuplicatePageDTO,
    "list_tags": TagPageDTO,
    "list_folders": FolderPageDTO,
    "propose_media_update": ProposalAckDTO,
    "list_creators": CreatorPageDTO,
    "get_creator_detail": CreatorDetailDTO,
    "list_tasks": TaskPageDTO,
    "get_task_detail": TaskDTO,
    "get_project_status": ProjectStatusDTO,
    "get_project_settings": ProjectSettingsDTO,
    "list_directory": DirectoryPageDTO,
    "read_text": TextChunkDTO,
    "get_media_preview": PreviewDTO,
    "read_logs": LogPageDTO,
    "propose_media_batch_update": ProposalAckDTO,
    "propose_tag_rename": ProposalAckDTO,
    "propose_tag_merge": ProposalAckDTO,
    "propose_maintenance": ProposalAckDTO,
    "propose_file_move": ProposalAckDTO,
    "propose_scan": ProposalAckDTO,
}


class ToolResultDTO(DTO):
    tool_call_id: UUID
    tool_name: ToolName
    result: (
        MediaPageDTO
        | MediaDetailDTO
        | StatsDTO
        | RecommendationDTO
        | DuplicatePageDTO
        | TagPageDTO
        | FolderPageDTO
        | ProposalAckDTO
        | CreatorPageDTO
        | CreatorDetailDTO
        | TaskPageDTO
        | TaskDTO
        | ProjectStatusDTO
        | ProjectSettingsDTO
        | DirectoryPageDTO
        | TextChunkDTO
        | PreviewDTO
        | LogPageDTO
        | TruncatedDTO
    )

    @model_validator(mode="before")
    @classmethod
    def named_result(cls, value):
        if isinstance(value, dict) and value.get("tool_name") in RESULT_TYPES:
            value = dict(value)
            result = value.get("result")
            target = (
                TruncatedDTO
                if isinstance(result, dict)
                and result.get("reason") == "tool_result_too_large"
                else RESULT_TYPES[value["tool_name"]]
            )
            value["result"] = target.model_validate(result)
        return value


class ToolResultsDTO(DTO):
    items: list[ToolResultDTO]
    truncated: bool = False


class SessionDTO(DTO):
    id: UUID
    title: str
    state: str
    created_at: datetime
    updated_at: datetime


class RunDTO(DTO):
    id: UUID
    session_id: UUID
    status: str
    final_message_id: UUID
    output: str = Field(default="", max_length=65536)
    usage: dict | None = None
    error_code: str | None = None


class EventDTO(DTO):
    event_id: str
    type: Literal["text_delta", "tool_status", "run_status", "error"]
    run_id: UUID
    message_id: UUID | None = None
    data: dict


class HistoryMessageDTO(DTO):
    id: UUID
    role: Literal["user", "assistant"]
    content: str = Field(max_length=65536)
    run_id: UUID
    status: str


class HistoryPageDTO(DTO):
    items: list[HistoryMessageDTO] = Field(max_length=100)
    total: Count
    offset: Count = 0
    has_more: bool = False
    next_offset: Count | None = None


class SessionPageDTO(DTO):
    items: list[SessionDTO] = Field(max_length=100)
    total: Count
    offset: Count = 0
    has_more: bool = False
    next_offset: Count | None = None


class ProposalPageDTO(DTO):
    items: list[ProposalDTO] = Field(max_length=50)
    total: Count
    offset: Count = 0
    has_more: bool = False
    next_offset: Count | None = None


class AvailabilityDTO(DTO):
    enabled: bool
    busy: bool
    active_run_id: UUID | None = None
    error_code: str | None = None
