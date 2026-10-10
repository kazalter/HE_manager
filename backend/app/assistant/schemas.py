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
    "propose_scan",
]


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


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


class MediaQuery(PageQuery):
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
    rating: Annotated[int, Field(ge=0, le=5, strict=True)] | None = None
    favorite: Annotated[bool, Field(strict=True)] | None = None
    source_url: str | None = Field(default=None, max_length=2000)
    add_tags: list[TagInput] = Field(default_factory=list, max_length=20)
    remove_tag_ids: list[PositiveID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def nullability(self):
        if any(
            name in self.model_fields_set and getattr(self, name) is None
            for name in ("rating", "favorite")
        ):
            raise ValueError("only source_url can be cleared")
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
    truncated: bool = False


class MediaPageDTO(DTO):
    items: list[MediaDetailDTO] = Field(max_length=50)
    total: Count
    offset: Count = 0
    has_more: bool = False
    truncated: bool = False


class RecommendationDTO(DTO):
    items: list[MediaDetailDTO] = Field(max_length=50)
    basis: str = Field(max_length=2000)
    method: Literal["manga_retrieval", "metadata_filter"]
    truncated: bool = False


class StatsDTO(DTO):
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
    truncated: bool = False


class TagPageDTO(DTO):
    items: list[TagDTO] = Field(max_length=50)
    total: Count
    offset: Count = 0
    has_more: bool = False


class FolderDTO(DTO):
    id: PositiveID
    display_name: str = Field(max_length=500)
    status: str = Field(max_length=80)


class FolderPageDTO(DTO):
    items: list[FolderDTO] = Field(max_length=50)
    total: Count
    offset: Count = 0
    has_more: bool = False


class ProposalAckDTO(DTO):
    id: UUID
    kind: Literal["media_update", "scan"]
    target_id: PositiveID
    target_label: str = Field(max_length=500)
    state: Literal["pending", "applied", "queued", "rejected", "expired", "stale"]
    expires_at: datetime


class JobDTO(DTO):
    job_id: str
    folder_id: PositiveID
    status: str
    message: str | None = None
    created_at: datetime
    finished_at: datetime | None = None


class ActionResultDTO(DTO):
    proposal_id: UUID
    state: str
    media_id: PositiveID | None = None
    job_id: str | None = None
    job: JobDTO | None = None


class ProposalDTO(ProposalAckDTO):
    session_id: UUID
    before: dict
    after: dict
    payload_hash: str
    result: ActionResultDTO | None = None


class TruncatedDTO(DTO):
    truncated: Literal[True] = True
    reason: Literal["tool_result_too_large"] = "tool_result_too_large"


RESULT_TYPES = {
    "search_media": MediaPageDTO,
    "get_media_detail": MediaDetailDTO,
    "get_library_stats": StatsDTO,
    "recommend_media": RecommendationDTO,
    "list_duplicate_candidates": DuplicatePageDTO,
    "list_tags": TagPageDTO,
    "list_folders": FolderPageDTO,
    "propose_media_update": ProposalAckDTO,
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
