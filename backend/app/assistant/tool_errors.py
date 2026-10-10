"""Safe public errors; never forward exception text or credential-bearing bodies."""
from .schemas import ToolErrorDTO
MESSAGES = {
    "assistant_tag_exists": "目标标签已存在，请改用标签合并。",
    "assistant_invalid_tool_args": "工具参数不正确，请按工具 schema 修正。",
    "assistant_invalid_proposal": "变更参数不正确。",
    "assistant_invalid_tool_token": "工具身份不可用，请检查管家连接配置。",
    "assistant_tool_context_invalid": "对话或运行上下文不可用。",
    "assistant_run_unavailable": "运行已停止或过期，请重新发起。",
    "assistant_media_not_found": "媒体不存在或不符合查询范围。",
    "assistant_folder_not_found": "目录不存在。",
    "assistant_not_found": "对象不存在或当前用户无权访问。",
    "assistant_path_outside_root": "路径不在 HE 登记目录中，或包含符号链接。",
    "assistant_file_unavailable": "文件不存在或暂时无法读取。",
    "assistant_content_too_large": "文件内容超过读取上限。",
    "assistant_invalid_text": "此文件不是可读取的 UTF-8 文本。",
    "assistant_proposal_stale": "资料或文件已变化，请重新生成审批。",
    "assistant_proposal_expired": "审批已过期，请重新生成。",
    "assistant_empty_change": "没有需要修改的内容。",
    "assistant_conflicting_tags": "标签增删存在冲突。",
    "assistant_operation_busy": "相关目录正在扫描、下载或修改，请稍后重试。",
    "assistant_file_destination_exists": "目标已存在，不能覆盖。",
    "assistant_cross_device_move": "本次文件整理仅支持同一文件系统移动。",
    "assistant_file_relationship_unsupported": "此对象的关联文件无法完整核对，暂不能移动。",
    "assistant_tool_unavailable": "工具暂不可用，请稍后重试。",
}
def safe_tool_error(status: int, code: str, request_id: str) -> ToolErrorDTO:
    if code not in MESSAGES:
        code = "assistant_tool_unavailable" if status >= 500 else "assistant_tool_context_invalid"
    return ToolErrorDTO(code=code, message=MESSAGES[code], request_id=request_id)
