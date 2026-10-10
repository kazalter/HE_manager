# HE 管家读取能力与审批 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让管家读取整个 HE 项目的业务信息和媒体文件，通过可核对的网页审批执行资料整理、任务和文件改名/移动。

**Architecture:** 扩展现有 HE → Hermes → MCP → assistant-tools 链路，以共享工具契约和服务器操作注册表统一能力。查询没有业务副作用，提案不执行写入，登录管理员确认后由后端事务或持久任务执行。文件操作另设日志与恢复机制，审批 UI 汇总当前用户的提案和真实结果。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy/SQLite、MCP SDK 2.0、Vue 3/TypeScript、Tailwind、Docker Compose；不新增数据库或 OCR/转写服务。

**Spec:** `docs/superpowers/specs/2026-10-10-assistant-capabilities-approval-design.md`

## Global Constraints

- 开发、构建、部署全部通过 SSH 在 Linux `/opt/stacks/he-manager`；遵守 AGENTS.md 的单 main、提交前检查和前端 staging 发布规则。
- 保留旧 9 工具、旧提案和会话接口；身份验证、运行绑定、停止围栏、用户隔离不得放宽。
- 读取无需审批且无业务写入；凭据、原始数据库和原始备份文件不可作为工具内容输出。
- 列表最多 50 项、文本最多 32 KiB、日志最多 200 条；截断明确，分页稳定。
- 批量最多 50 个明确对象；选择变化产生新提案和哈希。文件操作一次一个媒体对象，仅同文件系统、不覆盖、已登记 HE 根目录内。
- Agent 不能批准；确认来自网页当前登录管理员，验证提案哈希、目标指纹、有效期和运行状态。
- 不增加永久删除、任意终端、部署、凭据修改、OCR/转写/视频分析服务。
- 当前上级指令禁止未经用户要求新增或运行自动测试；本计划使用代码审查、类型/生产构建与发布检查。用户明确要求测试时再补充行为用例与测试命令。
- 每个任务完成后检查自己的 diff 和暂存内容再提交；保留现有 `.env.bak-20261010-1443` 不读取、不提交。

## Review Focus

1. 中文、emoji、超长路径与非法编码：显示可读，文件名不被静默截断；归入任务 3、8。
2. 批量对象在审批前被外部修改/合并/删除：拒绝整个资料事务，显示重新生成提示；归入任务 5。
3. 文件目录内含关联音频、封面和子媒体，或扫描/下载正在写入：完整核对关联对象和占用，不能只移动磁盘路径；归入任务 7。
4. 升级时仍有旧运行或旧 pending 提案：停启必须等运行退出，旧契约与已保存结果仍可解析；归入任务 1、9。
5. 跨对话操作和面板关闭时请求返回：身份/对话切换不能把旧状态写到新对话，抽屉焦点恢复；归入任务 8。

## 执行与验证方式

默认建议在当前会话由主 Agent 顺序实施，全部任务完成后独立审查。每个任务先阅读指定文件，完成步骤后检查实际修改，不以模型文字代替结果。下面“审查”列出的行为是实现与复核的检查条件，不是本轮已运行或获准新增的测试。

基础命令均在 SSH 远端仓库执行：`git diff --check`、`git diff -- <本任务文件>`；前端任务使用 `cd frontend && npm run build -- --outDir /home/user1/he-manager-builds/assistant-approval-20261010`。Docker 构建和健康检查见任务 9。需要动态修改数据的验证不得在真实媒体上试验；若用户授权测试，使用隔离临时目录/数据库。

## 文件与接口约定

- `backend/app/assistant/tool_catalog.py`：只依赖 Pydantic DTO 的纯工具描述、参数与结果注册，MCP/后端共用。
- `backend/app/assistant/schemas.py`：兼容旧 DTO，新增严格领域 DTO；`RESULT_TYPES` 与 `ToolResultDTO` 适配新工具。
- 新 `project_reads.py`、`file_reads.py`、`operation_registry.py`、`operation_jobs.py`、`file_actions.py`、`approval_queries.py`：分别负责业务读、文件读、操作契约、持久任务、文件执行、审批查询。
- 新 `backend/app/services/assistant_runtime_logs.py`、`media_operation_guard.py`：脱敏日志及所有媒体写入路径共用的协调保护。
- 新 `frontend/src/components/assistant/ApprovalPanel.vue`、`ProjectResultCard.vue` 与 `frontend/src/composables/useAssistantApprovals.ts`；扩展现有 ProposalCard、AssistantView 和 API/types。
- 工具名、操作 kind 和 DTO 类型以以下任务为唯一命名来源；任何更名须同步全部调用方。

### DTO 契约补充

新增 DTO 均定义在 schemas.py，继承 DTO 并拒绝额外字段；列表 items ≤ 50，日志 items ≤ 200。字段不可为空时使用严格 ID/数值类型。

- `ToolErrorDTO`: code、message、request_id；message 使用错误码固定中文映射，不拼接内部异常。
- `CreatorPageDTO/TaskPageDTO/DirectoryPageDTO`: items、total、offset、has_more、next_offset；分别定义 CreatorDTO、TaskDTO、DirectoryEntryDTO。
- `CreatorDTO`: name、media_count、media_ids（详情分页而非全量）；`TaskDTO`: task_id、kind、status、progress（可空）、created_at、finished_at（可空）、summary。
- `DirectoryEntryDTO`: name、relative_path、entry_type(file|directory)、size（可空）、modified_at、media_id（可空）；根目录路径由 FolderDTO 新增 path、readable 字段，兼容旧字段。
- `TextChunkDTO`: folder_id、relative_path、text、offset_bytes、next_offset_bytes（可空）、truncated、encoding=utf-8。
- `PreviewDTO`: media_id、media_type、page_index（可空）、page_count（可空）、preview_path（同源受控 API 路径）、analysis_supported、analysis_performed、notice；原图二进制不存进 ToolResultDTO JSON。
- `ProjectStatusDTO`: health、storage、backup（只含清单/时间/状态）；`ProjectSettingsDTO`: settings（固定非敏感字段白名单）；`LogPageDTO`: items（时间/service/level/code/object_id/summary/request_id）、cursor、next_cursor、has_more。
- `OperationPreviewDTO`: kind、targets（type/media|tag|folder|project 与 ID）、before、after、fingerprint、impact_count、reversibility；`ApprovalPageDTO`: items: list[ProposalDTO]、total、offset、has_more、pending_count。
- `CapabilitiesDTO`: read_tools、proposal_tools、file_roots、image_analysis_supported、writes_require_approval=true；映射当前已启用且可用能力，不硬编码“全部可用”。
- ProposalDTO 增加 reason、impact_count、targets、reversibility 和 job 摘要；旧记录使用默认值。状态基于后端提案/任务联合解析，原 state 字符串保持兼容。

---

### Task 1: 共享工具契约与错误诊断

**Files:** Create `backend/app/assistant/tool_catalog.py`, `backend/app/assistant/tool_errors.py`; Modify `schemas.py`, `internal_app.py`, `integrations/he_mcp/{client,server}.py`, `integrations/he_mcp/Dockerfile`。

**Interfaces:** `ToolSpec(name: str, args_type: type[DTO], result_type: type[DTO], description: str, mode: Literal['read','proposal'])`; `TOOL_CATALOG: dict[str, ToolSpec]`；`safe_tool_error(status: int, code: str, request_id: str) -> ToolErrorDTO`。

- [ ] 阅读现有 9 工具的参数、结果、调用记录、错误分支及对应历史运行的脱敏错误码；区分参数、身份、运行状态和业务错误，记录实际根因或仍缺的证据。
- [ ] 实现纯 catalog，保留现有 9 名称和 schema；客户端只对 read 工具重试。MCP 镜像复制 catalog 及所需纯 DTO 模块，不导入数据库。工具单次 JSON 结果预算 48 KiB，列表逐项缩减并提供 next_offset/cursor，文本在 UTF-8 边界缩减；运行保存总预算扩展为 1 MiB，超出明确显示存储截断，不能伪造已保存完整结果。
- [ ] 实现错误白名单与随机 request_id；内部 app 记录状态/错误码/工具名，禁止认证头和 body；未知错误统一安全提示。为失败调用保存仅有时间、run_id、工具名、错误码与 request_id 的 AssistantToolEvent 元记录，主进程查询可读取；日志工具不得因此需要可写日志挂载。
- [ ] 前后端错误映射保留兼容行为，白名单错误不再一律显示 he_tool_rejected；审查旧保存结果可解析、非 JSON 响应和响应体上限。
- [ ] 检查 diff 并提交 `refactor(assistant): unify tool contracts and safe errors`。

### Task 2: 完整业务查询

**Files:** Create `project_reads.py`; Modify `readonly.py`, `schemas.py`, `tool_catalog.py`, `internal_app.py`。

**Interfaces:** `execute_project_read(db, principal: ToolPrincipal, context: ToolContext, name: str, args: dict) -> DTO`。新增工具 `list_creators`, `get_creator_detail`, `list_tasks`, `get_task_detail`, `get_project_status`, `get_project_settings`。已有 search/detail/stats 添加 `scope: Literal['normal','all','missing','duplicate','checking'] = 'normal'`；Search 增加 `sort: Literal['id_desc','title'] = 'id_desc'`；按 title 排序以 ID 作稳定次排序。

- [ ] 实现作者关系、媒体状态筛选、来源/路径、标签/目录详情；添加只读 DTO，不返回 ORM 的完整序列化结果。
- [ ] 实现业务任务、HE 健康、存储与备份清单、非敏感设置读取。依据当前配置有效值投影允许字段，不返回 Cookie/proxy 凭据/model key。
- [ ] 注册领域工具和严格结果验证，保留现有 normal 行为；任务统一输出 `task_id, kind, status, progress, created_at, finished_at, summary`，不存在进度时用 null。
- [ ] 审查缺失/重复分类互斥与统计条件、任务归属、稳定排序分页；不得调用会写入进度或启动任务的路由。
- [ ] 检查 diff 并提交 `feat(assistant): expand HE project queries`。

### Task 3: 受控媒体文件读取与预览

**Files:** Create `file_reads.py`; Modify `schemas.py`, `tool_catalog.py`, `internal_app.py`, `routers/assistant.py`, `docker-compose.assistant.yml`; Reference `services/{media_access,manga_pages,range_response}.py`。

**Interfaces:** `resolve_project_path(db, folder_id: int, relative_path: str, *, must_exist: bool = True) -> Path`；`execute_file_read(db, principal, context, name: str, args: dict) -> DTO`。工具 `list_directory(folder_id, relative_path, limit, offset)`, `read_text(folder_id, relative_path, offset_bytes)`, `get_media_preview(media_id, page_index)`。

- [ ] 增加已登记媒体目录只读挂载，拒绝真实路径/链接/压缩包越界及根目录中凭据类型文件；目录排序为目录优先、名称稳定，显式分页。
- [ ] 实现最多 32 KiB 的 UTF-8 文本块及 next_offset，非法编码返回明确错误；二进制内容不误判为文本。中文/emoji 在字节边界保留完整字符。
- [ ] 实现文件/页预览描述 DTO 与仅当前管理员可访问的 HE 预览端点；复用读文件服务，避免阅读/播放状态写入。图片限制解码尺寸/文件大小，压缩包限制条目数和解压大小。
- [ ] 由网页的认证 fetch 获取预览 Blob；模型侧仅在确认支持图像输入且 MCP 图片链路可用时返回 image content block，否则输出“未分析文件内容”。绝不假定预览链接能被提供商访问。
- [ ] 审查中文、emoji、长路径、符号链接、压缩炸弹和断开文件；检查 diff 并提交 `feat(assistant): add bounded media file reads`。

### Task 4: 运行日志与任务查询的数据来源

**Files:** Create `services/assistant_runtime_logs.py`; Modify `main.py`, `assistant/{project_reads,tool_catalog,schemas,internal_app}.py`, `docker-compose.assistant.yml`。

**Interfaces:** `emit_event(service: str, level: str, code: str, object_id: str | None, summary_fields: dict) -> None`；`read_events(source: str, cursor: str | None, limit: int) -> LogPageDTO`；工具 `read_logs(source, cursor, limit)`，limit ≤ 200。

- [ ] 建立字段白名单的事件摘要和轮转日志（单文件 5 MiB、最多 3 份）；未知异常只输出错误码和 request_id，不复制 traceback 或 str(exc)。保留运维原日志渠道。
- [ ] 在扫描、导入/下载、自动同步和管家生命周期处接入业务事件；已有业务日志投影脱敏摘要，历史原文不得直接送模型；读取任务 1 的 AssistantToolEvent 时同样按字段白名单投影。
- [ ] 主进程写日志，toolworker 仅挂日志目录只读；设置权限，cursor 包含文件代次/位置，轮转后明确提供新游标。
- [ ] 审查认证头、带密码 URL、Cookie、模型响应和非结构化异常不能进入工具输出；检查 diff 并提交 `feat(assistant): expose safe HE runtime events`。

### Task 5: 扩展结构化资料与批量审批

**Files:** Create `operation_registry.py`; Modify `assistant/{schemas,models,proposals,actions,tool_catalog}.py`, `migrations.py`; Reference `tagging.py`, `routers/media.py`。

**Interfaces:** `OperationSpec(kind: str, args_type: type[DTO], preview: Callable, fingerprint: Callable, execute: Callable, async_job: bool)`；`OPERATION_REGISTRY`；`create_operation_proposal(db, principal, context, kind: str, args: dict) -> ProposalAckDTO`。

操作 kind：保留 `media_update`, `scan`；新增 `media_batch_update`, `tag_rename`, `tag_merge`, `maintenance`, `file_move`。工具新增 `propose_media_batch_update`, `propose_tag_rename`, `propose_tag_merge`, `propose_maintenance`, `propose_file_move`。所有新提案可接受 `reason: str`，最长 1000 字符；服务器预览不能依赖 reason 判断权限。

- [ ] 用幂等迁移扩展 reason、impact_count、reversibility 和目标集合，旧 DTO 字段有默认值；保留 target_id 为旧兼容主对象，新全局操作通过有类型的 targets 指定，内部 target_id=0 表示项目对象，API 输出 target_id=null；不以虚假正数冒充数据库对象。
- [ ] MediaPatch 增加 title、artist、view_status；扩展 nullability 规则：artist 可清空，title/rating/favorite/view_status 不可 null；严格字段验证。
- [ ] 为单项/批量、标签改名/合并构建服务器前后差异与完整关系指纹。批量 1–50 个不重复对象，事务内验证全体目标再写入；标签合并必须展示所有关联关系影响，清单分页但 fingerprint 覆盖全量。
- [ ] 实现 `derive_selected_proposal(db, user_id: int, proposal_id: str, selected_target_ids: list[int]) -> ProposalDTO`，从服务器原 payload 子集生成新提案并使旧提案失效；保留来源运行与有效期上限。
- [ ] 审查外部合并/删除/关系变化与重复确认，确保 stale 不产生部分事务结果；检查 diff 并提交 `feat(assistant): extend explicit change proposals`。

### Task 6: 审批后执行维护任务

**Files:** Create `operation_jobs.py`; Modify `assistant/{actions,schemas,models}.py`, `routers/assistant.py`, `main.py`, `services/job_lifecycle.py`; Reference `scan_jobs.py`, `services/backup.py`, `routers/{media,dedup}.py`。

**Interfaces:** `enqueue_operation_job(proposal_id: str) -> str`；`get_owned_operation_job(db, user_id: int, job_id: str) -> JobDTO`；`recover_operation_jobs() -> None`。maintenance action 为 `recheck_missing`, `recheck_duplicates`, `regenerate_thumbnail`, `backup_database`，参数使用显式 ID 集合或明确全库作用域。

- [ ] 从现有路由抽取需要的最小业务服务函数，维护公开接口兼容；全库任务预览固定对象集合和数量，确认再验证，不隐含扩展目标。
- [ ] 扩展 JobDTO：folder_id 可空，新 kind/target/progress 字段有默认值；新任务 ID `assistant-operation-{proposal_id}`，队列入库后执行一次，进程重启标记中断/需要恢复，禁止自动重放。
- [ ] 确认继续用现有用户/运行/过期/hash/fingerprint 验证，完成结果更新提案与审计；保留扫描旧 ID 和旧行为。备份执行禁用清理旧备份。
- [ ] 审查确认重复点击、排队失败、数据库状态写入失败；独立于聊天停止，未支持安全取消的执行器不显示取消按钮。
- [ ] 检查 diff 并提交 `feat(assistant): execute approved maintenance jobs`。

### Task 7: 文件改名/移动的一致性与恢复

**Files:** Create `assistant/file_actions.py`, `services/media_operation_guard.py`; Modify `assistant/{models,operation_registry,operation_jobs,proposals}.py`, `migrations.py`, `main.py`, `scanners/{common,runner}.py`; 修改 `services/external/{matching,wnacg,asmr}.py`、`services/external/pawchive/{downloader,media_cache}.py` 的目标写入入口；检查 `services/x_import_runtime.py`、`services/external_runtime.py` 和公开路径变更入口，并接入同一保护。

**Interfaces:** `preview_file_move(db, media_id: int, destination_folder_id: int, destination_relative_path: str) -> OperationPreviewDTO`；`execute_file_move(proposal_id: str) -> ActionResultDTO`；`recover_file_operations() -> None`；`acquire_media_operation(folder_ids: list[int], media_ids: list[int]) -> ContextManager`。

- [ ] 记录关联路径清单：Media.absolute_path/relative_path/folder_id 及音频、封面、子媒体和其他确有对应关系的路径字段；无法完整建立关系的对象明确拒绝，不猜测字符串替换。
- [ ] 实现共用协调机制：排序获取目录/对象保护，下载目标和扫描预约都参加协调；文件操作不得与持有预约的扫描、下载或路径写入并发。部署为现有单后端 worker，toolworker 只读。
- [ ] 创建持久 `AssistantFileOperation` 表：proposal 唯一，源/目标、完整对象指纹、状态、恢复信息。锁内检查已登记根、无链接、目标不存在、同 st_dev、合法名称及关联项未变化；目录清单上限 10000 条，超出拒绝提案，避免不完整的关联指纹。
- [ ] 执行意图入库 → 不覆盖移动 → DB 路径事务 → 完成；Linux 使用 renameat2(RENAME_NOREPLACE)，Windows 使用拒绝覆盖的 os.rename；其他平台无等效原语时明确拒绝。源身份在锁内再次检查，禁止用可覆盖的 os.replace；目标存在错误不做重试覆盖。
- [ ] 实现启动恢复：源/目标/数据库三方指纹可验证时完成或回滚；未知状态标记 needs_recovery、阻止冲突操作并显示可操作说明。不得把恢复判断直接转化成自动重放。
- [ ] 审查嵌套漫画目录、长路径、扫描/下载占用、每个阶段失败、同名目标与跨盘拒绝；检查 diff 并提交 `feat(assistant): journal approved media file moves`。

### Task 8: 用户级审批接口与界面

**Files:** Create `assistant/approval_queries.py`, `frontend/src/composables/useAssistantApprovals.ts`, `frontend/src/components/assistant/{ApprovalPanel,ProjectResultCard}.vue`; Modify `routers/assistant.py`, `assistant/schemas.py`, `frontend/src/{types/assistant.ts,utils/assistantApi.ts,views/AssistantView.vue,components/assistant/ProposalCard.vue,components/assistant/MediaResults.vue}`。

**Interfaces:** GET `/assistant/approvals?tab=pending|history&limit&offset` → ApprovalPageDTO（含有效 pending_count）；GET `/assistant/capabilities` → CapabilitiesDTO；POST `/assistant/proposals/{id}/selection` → ProposalDTO；保留确认/拒绝/会话提案接口。`useAssistantApprovals()` 返回 `{items,pendingCount,tab,busy,error,refresh,loadMore,act,selectTargets,dispose}`。

- [ ] 实现用户级查询、实际能力列表和目标子集接口；按 created_at+id 稳定排序；pending_count 排除过期/停止/失效运行提案，执行记录含真实 Job 状态。
- [ ] 实现 API DTO/error code 白名单和可取消请求；共享审批状态更新，聊天卡与面板一致。每个请求绑定身份 generation，退出、切换用户或组件销毁后不写旧结果。
- [ ] 提案卡增加 reason、影响清单、类型化 diff、全路径和具体按钮；批量选择重新生成提案，生成期间不可批准。事务失败整体显示失败，成功显示每个对象结果。
- [ ] ApprovalPanel 提供待审批/执行记录、对话跳转与分页；桌面侧栏/手机抽屉、Esc、焦点约束和返回、44px 按钮、320px 无横向溢出；顶部数量与能力说明。
- [ ] ProjectResultCard 显示目录/日志/任务/系统和媒体预览，认证 Blob 在卸载时释放；仅可信后端结果渲染，不渲染模型生成的执行成功卡。
- [ ] 审查跨对话返回、面板关闭返回、过期倒计时、长中文路径与旧 ProposalDTO；运行 production build 到 staging，检查 diff 并提交 `feat(assistant): add approval center and project result cards`。

### Task 9: Hermes 接线、发布与任务收尾

**Files:** Modify `assistant/sessions.py`, `deploy/hermes/{config.example.yaml,SOUL.md}`, `docker-compose.assistant.yml`, `PLAN.md`, `docs/hermes-operations.md`；Reference `assistant/identity.py`, `scripts/prepare_hermes*.py`。

**Interfaces:** `build_assistant_instructions(context: ToolContext, capabilities: CapabilitiesDTO) -> str`；Hermes profile 授权工具名与 catalog 同步，绝不开放通用终端。

- [ ] 更新提示词、实际 profile 工具名单、SOUL 及模板：以运行绑定上下文调用读取/提案工具，说明真实内容分析能力；引用媒体/日志文本不可覆盖系统指令。更新 profile 时保留凭据与用户绑定，不打印私密配置。
- [ ] 完整代码审查：逐项覆盖设计第 3–8 节和 Review Focus，旧运行/提案/存储结果兼容；记录未验证项和真实根因，独立审查问题修正后再发布。
- [ ] 检查现有 active runs、scan/operation/file jobs 为零；建立数据库热备份和镜像/静态资源备份，检查备份完整性。未退出任务先等待，不强制中断未知文件操作。
- [ ] 构建：`docker compose -f docker-compose.yml -f docker-compose.assistant.yml build backend assistant-mcp`；前端执行约定 staging build。发布后端/工具/MCP、需要时 Hermes；只更新本轮服务，使用 `up -d --no-deps --wait --wait-timeout 90`（具体服务由 diff 确定）。
- [ ] 原子发布前端 index/version，保留旧 hashed assets；检查 HTTP 与 staging 一致、Docker health、工具 catalog 名称和实际可用能力一致。只做只读线上查看；任何写入验收依照用户审批，不替用户点击批准真实操作。
- [ ] 更新 PLAN.md、操作指南、备份/回退路径与实施结果，检查 diff 后提交 `docs(assistant): record capabilities and approval rollout`。汇报已实现、部署状态、检查证据和限制。

## 自审覆盖与交接

- 设计 1–2：目标/旧接口/方案选择 → Global Constraints、任务 1、9。
- 设计 3：业务/文件/日志/系统读取 → 任务 2–4、8、9。
- 设计 4–5：提案/事务/任务/文件恢复 → 任务 5–7。
- 设计 6：审批面板、移动布局、结果/焦点 → 任务 8。
- 设计 7：错误/迁移/模板/发布 → 任务 1、5、7、9。
- 设计 8：验证条件 → 各任务审查步骤、Review Focus、任务 9；自动测试受上级指令约束，未获要求前不执行。

计划完成后先请用户复核并选执行方式。建议当前会话顺序实施：接口与状态高度耦合，保持主 Agent 的上下文可减少反复对齐；用户可选择逐任务分派并逐任务独立审查。

## 实施完成记录

用户已批准并选择直接实施。任务1～9已提交与发布，检查及动态验证限制见 [发布记录](../../assistant-capabilities-approval-rollout.md)。本计划中的审查条件不能视为已执行的自动测试。
