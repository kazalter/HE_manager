"""Pure DTO tool contract shared with the MCP image; no runtime imports."""
from dataclasses import dataclass
from typing import Literal
from . import schemas as s

class DetailArgs(s.ScopeQuery):
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
register("get_library_stats", s.ScopeQuery, "统计 HE 媒体类型、收藏、阅读状态。")
register("recommend_media", s.RecommendationQuery, "按已有资料推荐媒体；必须说明依据。")
register("list_duplicate_candidates", s.PageQuery, "读取重复候选，不执行合并或删除。")
register("list_tags", s.PageQuery, "读取标签及关联媒体数量。")
register("list_folders", s.PageQuery, "读取登记目录、状态和目录编号。")
register("propose_media_update", UpdateArgs, "提出资料修改；仅生成预览，管理员在网页批准后执行。", "proposal")
register("propose_scan", ScanArgs, "提出目录扫描；管理员在网页批准后才启动。", "proposal")
register("list_creators", s.CreatorQuery, "分页读取 HE 漫画作者和 X 作者，包含所有媒体状态。")
register("get_creator_detail", s.CreatorDetailQuery, "按作者 key（a:作者或 x:账号）分页查询关联媒体。")
register("list_tasks", s.TaskQuery, "分页读取 HE 扫描、下载/导入、自动同步和当前用户管家任务状态与可用进度；不启动任务。")
register("get_task_detail", s.TaskDetailQuery, "按任务 ID 读取状态，无写入。")
register("get_project_status", s.DTO, "读取 HE 健康、登记磁盘空间和备份清单；无凭据。")
register("get_project_settings", s.PageQuery, "分页读取目录扫描、缩略图和来源同步/下载目录设置；不包含账号凭据。")
register("list_directory", s.DirectoryQuery, "分页列出 HE 登记目录的文件和子目录；相对路径不能越界。")
register("read_text", s.TextQuery, "读取 HE 目录内 UTF-8 文本，最多 32 KiB；按 next_offset_bytes 继续。")
register("get_media_preview", s.PreviewQuery, "获取媒体/漫画页的网页预览；当前模型未分析文件内容。")
register("read_logs", s.LogQuery, "读取脱敏 HE 运行日志/工具错误，不返回原始异常或凭据；按 next_cursor 继续。")
register("propose_media_batch_update", s.BatchUpdateArgs, "提出最多 50 项明确媒体资料变更，网页批准后执行；选择子集要重新生成审批。", "proposal")
register("propose_tag_rename", s.TagRenameArgs, "提出标签改名，展示关联影响；网页批准后执行。", "proposal")
register("propose_tag_merge", s.TagMergeArgs, "提出标签合并，原标签删除但不删除媒体；网页批准后执行。", "proposal")
register("propose_maintenance", s.MaintenanceArgs, "提出缺失/重复复查、缩略图重建或备份任务；网页批准后执行。", "proposal")
register("propose_file_move", s.FileMoveArgs, "提出单媒体文件/漫画目录改名或移动，目标必须为登记目录相对路径；网页批准后执行。", "proposal")
READ_TOOLS = frozenset(k for k,v in TOOL_CATALOG.items() if v.mode == "read")
PROPOSAL_TOOLS = frozenset(k for k,v in TOOL_CATALOG.items() if v.mode == "proposal")
