"""Pure DTO tool contract shared with the MCP image; no runtime imports."""
from dataclasses import dataclass
from typing import Literal
from . import schemas as s

class DetailArgs(s.DTO):
    media_id: s.PositiveID
class UpdateArgs(s.DTO):
    media_id: s.PositiveID
    patch: s.MediaPatch
class ScanArgs(s.DTO):
    folder_id: s.PositiveID

@dataclass(frozen=True)
class ToolSpec:
    name: str
    args_type: type[s.DTO]
    result_type: type[s.DTO]
    description: str
    mode: Literal["read", "proposal"]

TOOL_CATALOG = {}
def register(name, args_type, description, mode="read"):
    TOOL_CATALOG[name] = ToolSpec(name, args_type, s.RESULT_TYPES[name], description, mode)

register("search_media", s.MediaQuery, "查询 HE 媒体资料；按条件筛选与分页，无阅读进度副作用。")
register("get_media_detail", DetailArgs, "按媒体 ID 读取资料，不修改阅读进度。")
register("get_library_stats", s.DTO, "统计 HE 媒体类型、收藏、阅读状态。")
register("recommend_media", s.RecommendationQuery, "按已有资料推荐媒体；必须说明依据。")
register("list_duplicate_candidates", s.PageQuery, "读取重复候选，不执行合并或删除。")
register("list_tags", s.PageQuery, "读取标签及关联媒体数量。")
register("list_folders", s.PageQuery, "读取登记目录、状态和目录编号。")
register("propose_media_update", UpdateArgs, "提出资料修改；仅生成预览，管理员在网页批准后执行。", "proposal")
register("propose_scan", ScanArgs, "提出目录扫描；管理员在网页批准后才启动。", "proposal")
READ_TOOLS = frozenset(k for k,v in TOOL_CATALOG.items() if v.mode == "read")
PROPOSAL_TOOLS = frozenset(k for k,v in TOOL_CATALOG.items() if v.mode == "proposal")
