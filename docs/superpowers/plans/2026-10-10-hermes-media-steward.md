# Hermes Agent 媒体库管家 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 在 HE 网页中接入 Hermes Agent，实现媒体查询和建议，并在用户明确确认后修改标签/资料或启动扫描。

**Architecture:** HE 后端代理独立 Hermes API；Hermes 通过专用 MCP 桥接服务调用 HE 内网工具应用。每位管理员使用独立 Hermes profile；工具只能读取媒体与创建建议，实际写入由带用户鉴权的 HE 主应用确认接口执行。

**Tech Stack:** 现有 Python 3.12 / FastAPI / SQLAlchemy / SQLite WAL、Vue 3 / TypeScript / Vite；Hermes 官方 Docker 镜像、HTTP/SSE、MCP Python 官方 SDK、外部模型 API。

**Spec:** [已确认设计](../specs/2026-10-10-hermes-media-steward-design.md)

日期：2026-10-10。状态：SSH 已恢复并核对远端 AGENTS、git status、提交与阶段记录；H01 已验收并完成阶段提交（后端228项通过、运行时门禁PASS），H02 身份/持久化已验收并提交；H03～H08 未开始。第二轮审查增量已合并且保留此前 H01 工作。开发、构建、测试和部署均通过 SSH 在 /opt/stacks/he-manager 完成，按依赖顺序逐阶段验收和 commit。

## Global Constraints

- 使用入口：HE Manager 网页内置聊天。
- 初始用户范围：HE 管理员。
- 媒体删除、重复项合并和下载不属于一期工具。
- 模型调用使用外部模型 API；先验证现有 DeepSeek 配置能否满足 Hermes 的工具调用和流式响应要求，不兼容时增加独立 Hermes 模型配置。
- 数据库变更遵循 backend/app/migrations.py 中的幂等迁移模式；保持一个代码库和 main，不引入 Alembic。
- Hermes API、HE 内网工具应用和 MCP 均不发布宿主机端口；服务互访走专用内部网络，仅 Hermes 增加外部模型出口，MCP 与 HE 工具应用没有外网出口。
- MCP 桥接服务不直接读取 SQLite，也不挂载数据库、媒体目录或宿主机工作目录。
- 用户必须在 HE 页面检查并确认后，后端才执行。
- 发往外部模型的上下文限于用户请求及完成查询所需的结构化元数据，不发送媒体文件内容或二进制文件。
- 一期不在该主机加载本地大模型；保持 Python 3.12 / Node.js 22 的项目运行画像，Hermes 镜像自带的 Python 不影响后端版本。

## Review Focus

1. 管理员 A 猜到管理员 B 的 session/run/proposal ID：所有读取与控制返回 404，记忆及 profile 密钥也不共享。对应 H02、H05。
2. 建议生成后用户手动修改目标：确认返回 409，不能覆盖新值；重复确认只能返回同一结果。对应 H04。
3. HTTP/SSE 断流、UTF-8 字符跨 chunk、重复终态和代理缓冲：不重复消息、不丢终态，也不重新创建 run。对应 H05、H07。
4. 确认扫描后服务在排队/运行中重启或媒体盘未挂载：任务有明确中断/失败结果，不自动重放扫描。对应 H04、H08。
5. 媒体标题包含指令/HTML，或所问媒体没有语义画像：按数据处理、纯文本展示；推荐说明依据，不能编造文件内容。对应 H03、H06、H07。

---

## 复核发现与实施决策

原设计方向可行，但不能直接交给实现者执行。以下缺口已落实为本计划中的任务：

| 原先不完整之处 | 明确的实施决策 |
| --- | --- |
| 只写了会话映射，未隔离 Hermes 全局记忆 | 每位管理员独立 he-user-{user_id} profile、API key、MCP tool token；未配置的管理员 fail closed |
| 服务鉴权可能绕过现有主应用鉴权中间件 | 增加独立 HE 内网工具应用；主应用始终只接受用户 token，工具 token 无法调用确认接口 |
| 现有扫描 API 返回 Folder 或目录列表，不提供 job ID | 新增管家扫描 job 包装器，复用 scanner 和 job_lifecycle，不改变旧扫描 API 返回值 |
| 现有推荐器主要面向漫画 | 漫画复用现有推荐；视频/音频/图片仅按已有元数据筛选排序，返回推荐依据 |
| 写入确认没有事务与并发定义 | 预览存储、300 秒有效期、乐观版本校验、原子消费和审计；不用模型文本代替确认 |
| SSE 只写了代理 | 独立 Nginx location、fetch Bearer 流、事件归一化、重连读状态和 upstream 幂等键 |
| 未验证 Hermes/SDK 版本与工具限制 | H01 在隔离环境实测，按 digest/精确版本锁定；能力不满足时不得继续接入生产 |

## 文件分工

所有路径相对仓库根目录；现有巨型文件只增加注册/迁移入口，不整块重构。

| 文件 | 职责 |
| --- | --- |
| backend/app/assistant/{schemas,models,store}.py | 独立 DTO、工具身份 hash 表、会话/run/建议/审计表及归属查询 |
| backend/app/assistant/{config,identity}.py | 服务端配置、用户/profile 绑定、工具身份与限额 |
| backend/app/assistant/{readonly,internal_app}.py；backend/app/recommendations.py | 无副作用查询；推荐增加可选禁用内部 AI；只在内网进程注册工具 HTTP API |
| backend/app/assistant/{proposals,actions,scan_jobs}.py | 变更预览、确认事务、扫描 job 包装器 |
| backend/app/assistant/{hermes_client,sessions}.py | Hermes 协议适配、会话清除和 run 恢复 |
| backend/app/routers/assistant.py | 主应用 /assistant 用户接口，不注册内部工具路由 |
| backend/app/{main,migrations}.py | 注册新表与主路由、权限和启动恢复 |
| integrations/he_mcp/{server,client}.py | MCP schema 与 HTTP 转发，逐请求传递身份 |
| integrations/he_mcp/{Dockerfile,requirements.txt} | 独立轻量依赖和镜像，不升级 HE 业务依赖 |
| deploy/hermes/{runtime-lock.json,config.example.yaml,SOUL.md} | H01 实测版本/协议、无密钥配置、管家职责 |
| scripts/{prepare_hermes,check_hermes_runtime,run_assistant_acceptance}.py | profile 初始化、兼容性与验收检查，不打印密钥 |
| .gitignore；backend/requirements.txt | 忽略 profile/服务密钥；将 HTTP client 纳入生产依赖 |
| frontend/src/{types/assistant.ts,utils/assistantApi.ts,composables/useAssistantChat.ts} | 前后端契约、Bearer fetch/SSE、页面状态 |
| frontend/src/views/AssistantView.vue；components/assistant/*.vue | 聊天、媒体结果、建议确认卡、任务状态 |
| docker-compose.assistant.yml；frontend/nginx.conf | 可选服务、网络/卷/健康检查、无缓冲代理 |
| docs/hermes-operations.md；PLAN.md | 配置/升级/备份/回滚指南与主计划链接 |

## 固定接口与数据规则

**服务端 DTO（H02 定义，后续任务直接复用）：**

- ToolContext(session_id: UUID, run_id: UUID)；身份来自 bearer 校验，不接收模型指定 user_id/profile_name。
- MediaQuery(query: str, media_type: video|manga|image|audio|None, tag: str|None, favorite: bool|None, view_status: str|None, limit: int=20, offset: int=0)。limit 上限 50，query 上限 4000 字符。
- MediaPageDTO(items: list[MediaDetailDTO], total: int, offset: int, has_more: bool)。
- MediaDetailDTO(id, title, media_type, artist, tags, rating, favorite, view_status, duration, page_count, source_site)。禁止 absolute_path、relative_path、凭据 URL 或 token。
- RecommendationQuery(query, media_type, limit=12, avoid_tags=[], preferred_tags=[], seed=None)，query 上限 4000、limit 上限 50、两个标签列表各最多 20 项；RecommendationDTO(items, basis: str, method: manga_retrieval|metadata_filter)；StatsDTO 只含汇总数值；DuplicatePageDTO 只含 ID、标题、分数和判定依据。
- MediaPatch(rating: int[0..5]|None, favorite: bool|None, source_url: str|None, add_tags: list[TagInput], remove_tag_ids: list[int])，拒绝额外字段；未提供字段不修改，显式 null 只用于清空 source_url。source_url 只接受无 userinfo、凭据 query/fragment 的 HTTP(S) URL；TagInput(name, namespace="general")，name 1～80 字符，namespace 1～40 字符，输入空 namespace 规范化为 general，复用现有标签规范化/唯一性规则。
- 一期资料字段只开放评分、收藏、来源 URL 与媒体标签关系；标题/作者、观看进度、文件路径、全局标签重命名/合并留待另行定义派生索引和扫描覆盖规则。
- ProposalDTO(id, session_id, kind: media_update|scan, target_id, before, after, payload_hash, expires_at, state, result)。一项建议只对应一个 media_id 或一个已配置 folder_id。
- SessionDTO(id, title, state, created_at)；RunDTO(id, session_id, status, final_message_id, output, usage, error_code)；ToolResultDTO(tool_call_id, tool_name, result: 窄只读 DTO|ProposalAckDTO)，每 run 的展示结果 JSON 总计最多 64 KiB，超出时返回 truncated；EventDTO(event_id, type, run_id, message_id, data)。final_message_id 在 HE 内稳定生成，终态输出是最终展示的权威内容。
- ProposalAckDTO(id, kind, target_id, target_label, state, expires_at)，这是 MCP 返回给模型的建议结果；完整 before/after 只通过 HE 用户接口返回。ActionResultDTO(proposal_id, state, media_id|None, job_id|None)；JobDTO(job_id, folder_id, status, message, created_at, finished_at)。
- ProfileBinding(user_id, profile_name, api_key, api_key_generation, tool_token_hash) 为服务端私有类型；ToolPrincipal(user_id, profile_name)；RuntimeContract 为 H01 生成的版本化、无密钥协议记录，不发往前端。
- session/run/建议归属、确认结果、审计由 SQLite 持久化；完整正文在 Hermes profile。HE 仅在提交状态不确定期间持久化无密钥、限长的 submission envelope（消息、可信 instructions、实际 provider/model、幂等键和固定请求体），成功取得 upstream run ID 后清除；仅 hash 不足以跨重启恢复同一请求。Session 删除不宣称已删除独立长期记忆；操作指南说明其清理边界。

**HE 主应用接口：** GET /assistant/status；GET/POST /assistant/sessions；GET/DELETE /assistant/sessions/{sid}；GET /assistant/sessions/{sid}/messages；POST /assistant/sessions/{sid}/runs；GET /assistant/runs/{rid}；GET /assistant/runs/{rid}/events；GET /assistant/runs/{rid}/results；POST /assistant/runs/{rid}/stop；GET /assistant/sessions/{sid}/proposals；POST /assistant/proposals/{pid}/confirm；POST /assistant/proposals/{pid}/reject；GET /assistant/scan-jobs/{jid}。全部要求现有用户 Bearer + 活跃管理员身份 + 资源归属。

**HE 内网工具应用：** POST /tools/{tool_name}，固定名称列表匹配，输入包含 ToolContext；GET /healthz。独立 uvicorn app.assistant.internal_app:app，端口 8012；不在主应用注册。

**MCP：** Streamable HTTP /mcp，端口 8020。工具名称仅 search_media、get_media_detail、get_library_stats、recommend_media、list_duplicate_candidates、list_tags、list_folders、propose_media_update、propose_scan。list_folders 返回 folder_id、显示名称和状态，不返回路径；没有 confirm/apply/delete/通用 HTTP 工具。

**九工具的固定业务输入/返回（ToolContext 单独传递，extra=forbid）：**

所有 ID 为正整数；UUID 只用于 session/run/proposal。分页 limit=20（推荐 12）、1～50，offset=0 且非负；query 最大 4000 字符。空参数对象也必须校验，禁止通用 SQL、URL 或路径参数。

| 名称 | 业务 args | 结果 |
| --- | --- | --- |
| search_media | MediaQuery | MediaPageDTO |
| get_media_detail | media_id: int | MediaDetailDTO |
| get_library_stats | {} | StatsDTO(total: int, by_type: dict[media_type,int], favorite_count: int, watched_count: int)，均为非负整数 |
| recommend_media | RecommendationQuery | RecommendationDTO |
| list_duplicate_candidates | limit: int=20, offset: int=0 | DuplicatePageDTO(items: [{id, media_ids, titles, score, basis}], total, offset, has_more)；字段转自既有去重摘要，不重新检测 |
| list_tags | query: str="", namespace: str|None=None, limit: int=20, offset: int=0 | TagPageDTO(items: [{id, name, namespace, count}], total, offset, has_more) |
| list_folders | limit: int=20, offset: int=0 | FolderPageDTO(items: [{id, display_name, status}], total, offset, has_more)；display_name 不可直接采用绝对路径 |
| propose_media_update | media_id: int, patch: MediaPatch | ProposalAckDTO |
| propose_scan | folder_id: int | ProposalAckDTO |

H02 定义 DTO 的实际 Python 类型和序列化字段，H03/H04 与 H06 共用契约测试。若远端既有统计/去重字段不同，应在实现前记录确定的映射；不可为了计划中的名称改变既有业务 API。ToolResultDTO.result 是以上具名返回类型的受限联合，不允许任意 dict。H05/前端保持一致类型，端到端样例须包含九种结果。

**资源与默认限制：** HE_ASSISTANT_ENABLED 默认 0；关闭时拒绝创建 session/run、工具调用、生成建议与确认，管理员仍可读 status/已有历史并停止或清除已有会话；全局最多 1 个活跃 Agent run，每位管理员最多 1 个未结束 run；单轮输入 8000 字符、最多 8 轮 Agent 工具循环、每次模型生成默认最多 2048 输出 tokens、Agent run 180 秒后必须请求停止。停止完成前仍占并发槽；不能及时结束则关闭新 run，并明确报告停止未完成。建议有效期 300 秒，停止 run/清除会话使其未确认建议失效；管家同时最多 1 个未结束 assistant_scan，忙时确认返回 409。只读 HTTP 最多重试 1 次；创建 run 仅使用同一幂等键和完全一致的持久化请求体恢复。单个 tool JSON 上限 64 KiB、标题显示上限 500 字符、每项标签上限 50 并标记 truncated；历史分页最多 100 条，建议列表最多 50 条，run 最终输出上限 64 KiB。H01 测量并锁定容器限额，新增服务合计峰值内存预算 2 GiB，上线后 MemAvailable 至少 1 GiB、系统盘至少 5 GiB 可用；不满足即先解决资源条件。

**第二轮审查新增约束（由下列任务落实）：**

- RuntimeContract 是锁定镜像的实际契约。发现接口须校验 features 与 endpoints，并实际调用；不能把 endpoint 名称臆造为布尔 feature。工具集只检查 enabled=true 的实际展开名称，另以假模型抓取本轮收到的 tools schema 交叉验证。
- 建议幂等摘要覆盖版本、user_id、session_id、run_id、kind、target_id 和规范化 patch；同一 run 对两个目标做相同修改必须得到不同建议。重试返回原建议，不刷新有效期；stale/expired/rejected 不复活。
- 确认、停止及清除的业务状态更新使用同一 SQLite 写事务顺序：先提交的操作决定结果。停止/清除先提交时，后续确认和迟到建议不能写入；确认先提交时保留结果，停止聊天不撤销已确认修改或扫描。正常 completed 的 run 可以确认其尚未过期建议。
- 上游终态不总等于 executor 已退出。H01 必须验证停止、关闭及强制重启的差异；不能仅凭 interrupted/HTTP 200 放开槽。无法取得可靠退出证据则保持故障门禁，由运维确认整个网关已停止后解除，不给 HE 挂 docker.sock。
- 只读工具的业务查询与用于界面展示的助手记录分离。MediaResults 只消费 HE 校验过的窄 DTO；不解析模型自然语言猜媒体 ID，不透传原始工具事件。
- feature flag 关闭或 Hermes 离线时，HE 媒体库启动不等待助手恢复。恢复/watchdog 在主应用后台运行，助手门禁先关闭，已存在 run 仍可被核实、停止和清理。
- 数据库迁移仅由主应用负责；内网工具进程只校验 schema 并延迟 ready。SQLite 业务父目录若必须共享，须遮蔽密钥、profile、备份及其它非必要文件，验证 WAL/SHM 可用且禁止读取被遮蔽内容。
- 每阶段 commit 记录该阶段代码、测试与验收证据；H01 的 fake-provider 协议检查和真实外部模型兼容性分开记载，两者都通过才算 H01 完成。

**状态机和提交顺序：**

| 对象 | 状态与规则 |
| --- | --- |
| Session | creating → active → deleting → deleted；HE 预分配稳定 upstream session ID，创建超时先 GET 该 ID，409 只在映射核验一致时视为已存在；删除 404 视为已删除，不重新创建 |
| Run | submitting/submission_unknown → running → stopping → completed/cancelled/interrupted/failed；reconciling 表示恢复中，仍占槽；submission_unknown 无法解决时禁止新 run |
| Proposal | pending → applied（元数据）或 queued（扫描）；pending 也可转 rejected/expired/stale；一次消费，扫描最终结果从 job 获取 |
| Scan job | queued → running → completed/failed；主进程重启后未结束任务 → interrupted，不自动重放 |

UTC 持久化并以服务器时间校验有效期；过期/拒绝/停止 run 后到达的工具请求不能再生成有效建议。清除会话作废其所有未确认建议，停止单个 run 只作废该 run 的未确认建议。审计记录操作人、建议 ID、字段变更及结果，不保留密钥、完整提示或媒体路径。

## Task 1: H01 — 锁定可用 Hermes 运行时与模型协议

**Files:** 创建 deploy/hermes/runtime-lock.json、config.example.yaml、SOUL.md、scripts/check_hermes_runtime.py、backend/tests/fixtures/hermes/*.json；补充 docs/hermes-operations.md。依赖：无。

**Interfaces:** 输出 RuntimeContract(image_digest, hermes_version, mcp_sdk_version, capabilities, event_types, profile_routing, toolset_config, executor_exit_evidence, resource_limits)；后续任务不得猜测上游字段。runtime-lock 不含密钥。

- [x] Step 1：建立隔离检查场景，只使用临时 profile、同名九工具 MCP 桩（返回固定假数据）、假 provider 和假媒体，HE 生产数据目录不挂入检查容器。新增 backend/tests/test_hermes_runtime_check.py；先写并运行失败测试：真实 capabilities 形状可识别、缺端点拒绝、禁用工具不误报、额外启用工具拒绝、宽权限配置先于网络检查被拒绝、错误不含密钥。预期 RED；实现检查器后同一命令 python -m pytest backend/tests/test_hermes_runtime_check.py -q 必须 GREEN。
- [x] Step 2：从官方 stable 镜像解析实际 digest，记录版本、架构 digest、/opt/data 卷，以及 PID 1 和实际 gateway worker 的 UID/GID；不能用镜像 Config.User 或 root 探测容器代替 worker 身份。保留官方 init/监督入口，按实际 UID 处理 0700/0600；验证 /v1/runs、events、stop、session create/messages/delete、幂等和 profile 前缀鉴权；实测 POST /api/sessions 的指定 id/session_id、同 ID 409 和随后 GET 的行为，不能把 run 的幂等规则套到 session POST。
- [x] Step 3：在两个临时 profile 写入不同测试会话/偏好，验证跨 profile key 和 run/session ID 不可访问；采用一个默认 profile 启动的 multiplex gateway，验证 /p/he-user-ID/v1/* 与 /p/he-user-ID/api/sessions/* 的路由；默认 key 不被命名 profile 接受，HE 永不回退默认路由。检查实际 /v1/toolsets，只统计 enabled=true 的条目及其 concrete tools；该锁定版本目录不枚举 MCP，需额外核对 SDK 九工具枚举与真实发往模型的 schema；记录 MCP 实际前缀与记忆工具精确名称；仅允许本计划 MCP 工具与经核实的 profile 记忆能力。用假 provider 捕获真实发往模型的工具 schema，集合必须与 allowlist 一致，不能仅检查配置文件或 SOUL。同名建议工具会写助手建议表，MCP 注解不得虚标 readOnly；验证受控 MCP 服务的 trust 配置不会把“生成建议”停在上游 waiting_for_approval。HE 的用户确认仍是唯一业务写入授权，不新增 /approval 浏览器代理。发现能力时区分 features.session_resources 与 endpoints.session_create/session/session_messages/session_delete；端点还须用真实临时会话调用确认，锁定镜像可能与网页 main 不同。
- [x] Step 4：以现有 DeepSeek 配置做一次外部 API 工具调用与流式回复检查；记录实际请求/响应 schema、usage 支持、错误和超时。不兼容则配置另一外部 provider；记录只含 provider/model/base URL 的脱敏信息。缺少密钥时记录 blocked_external_model，仅完成假 provider 的协议检查，不生成总 PASS，也不进入 H02；报告只能包含检查项、错误码和脱敏证据路径。
- [x] Step 5：将已通过的协议写入 RuntimeContract 和脱敏 fixtures，独立锁定兼容的 MCP 官方 SDK/HTTP client 精确版本；记录输出 token、8 轮限制和停止的真实配置键；该版本必须配置 tools.tool_search.enabled="off"，通过命名 providers.he-model.extra_body.max_tokens 限制输出（顶层 run.max_tokens 不生效）；agent.run_budget_seconds 只作为附加保护，HE 独立持久化 watchdog 从提交时刻计 180 秒；确认 watchdog 不依赖浏览器/SSE 连接，并测量停止请求到 executor 退出的时间。分别验证 stop、SIGTERM drain、SIGKILL 后重启及超过 SSE 缓冲窗口的状态；若 interrupted 先于 executor 退出出现，记录可验证的退出证据和门禁策略，不把该状态当作立即释放槽的依据。资源测试记录镜像解包空间、缓存、临时文件、WAL、日志和备份所需空间，测量并发查询/推荐峰值与冷启动；不得把压缩镜像大小当作安装空间。若不能限制危险工具、隔离 profile 或可靠停止 run，该版本不进入后续任务。
- [x] Step 6：运行 python scripts/check_hermes_runtime.py --config <受保护检查配置路径>；预期 PASS，报告列出全部能力、工具集和资源测量且无密钥。按 AGENTS.md 核对 staged diff 后提交，建议消息 docs: lock Hermes runtime contract。

### H01 验收证据

- 锁定版本/SDK/资源及各项协议：`deploy/hermes/runtime-lock.json`、`backend/tests/fixtures/hermes/h01-evidence.json`。隔离三profile实时复查门禁PASS。
- 最终后端回归：228项通过（45.41秒），包含21项checker与5项假服务测试；只用临时数据库和容器。
- 已按用户更正切换到 DeepSeek 官方 `deepseek-flash`（DeepSeek-V4.1-Flash）：直接工具调用/流式和完整Hermes→假MCP→回答通过，usage可用。原401来自错误沿用中转地址。

## Task 2: H02 — 建立身份、会话与持久化契约

**Files:** 创建 backend/app/assistant/{__init__,schemas,models,store,config,identity}.py、scripts/prepare_hermes.py；修改 backend/app/migrations.py、main.py、.gitignore；测试 backend/tests/test_assistant_store.py、test_assistant_identity.py。依赖：H01。

**Interfaces:** get_profile(user_id: int) -> ProfileBinding；authenticate_tool_token(db, token: str) -> ToolPrincipal；require_owned_session(db, user_id: int, session_id: UUID) -> AssistantSession；reserve_run(db, user_id, session_id, client_request_id, input_hash: str, submission_envelope: SubmissionEnvelope) -> AssistantRun。DTO 与上一节一致。

- [x] Step 1：先写失败测试，固定以下断言；包含缺失配置、内网工具仅有身份 hash 表而没有 API-key/模型配置仍能正确鉴权、失活/降权用户、token 轮换、开关关闭后的写入/工具拒绝、同 client_request_id 不同消息 409。
~~~python
assert lookup_session_as_other_admin.status_code == 404
assert tool_token_on_public_confirm.status_code == 401
assert repeated_request.run_id == first_request.run_id
assert different_payload_same_request.status_code == 409
~~~
- [x] Step 2：在隔离 Python 3.12 环境运行 cd backend && python -m pytest tests/test_assistant_store.py tests/test_assistant_identity.py -q，确认新行为尚未实现而失败；数据库只用临时文件，不挂生产 /data。
- [x] Step 3：新增 AssistantToolIdentity(user_id, profile_name, tool_token_hash, credential_generation, enabled)、AssistantSession、AssistantRun、AssistantProposal、AssistantAudit 表，在主应用 create_all 前导入新 models，使用 checkfirst/幂等迁移；Run 的 (user_id, client_request_id)、Proposal 的 (run_id, kind, normalized_payload_hash) 和 Audit 的 proposal_id 唯一；包含 upstream ID、submission envelope、固定 API credential generation、deadline、结果和状态字段，并为 Run 增加 stop_requested_at（用户停止先提交时即便上游已 completed 也作废 pending）和 tool_results_json（总计最多 64 KiB）。工具身份表只有高熵 token 的 hash 与绑定元数据，不存 API key/模型密钥；authenticate_tool_token 仅查该表和用户/session/run，不依赖被遮蔽的 /data/assistant 私有配置。HE 预分配 run UUID 并同时用作上游 Idempotency-Key，在 reserve_run 前可将同一 UUID 放进可信 ToolContext；该键仅由服务端生成。SubmissionEnvelope 为 H01 协议固定的 provider/model、input、可信 instructions/ToolContext、预算、upstream session ID、Idempotency-Key 和 API credential generation；它是服务端私有类型，不接受前端构造。输入摘要涵盖用户可传的全部创建参数；同一 client_request_id 返回原请求，不因默认模型变更重建 envelope。reserve_run 在数据库短写事务中原子检查全局/每用户活跃 run 再插入，不能只用内存锁。metadata 事务使用条件更新确保并发不能重复消费。
- [x] Step 4：实现 profile 绑定、功能开关、只读配置加载和工具 token 的 hash/常量时间校验；每次工具调用重查活跃管理员、ToolContext 归属和 run 是否仍允许工具调用；session 必须 active，run 只能是 submitting/running，停止后晚到调用 fail closed。未配置 profile 返回 assistant_unconfigured，永不回退 default profile。
- [x] Step 5：实现 prepare_hermes.py --user-id ID：仅初始化显式指定的管理员，生成 he-user-ID profile 及独立随机密钥。HE 只保存必要 API key/工具 token hash；原始工具 token 留在 profile .env；其 hash 和 profile 绑定写入 AssistantToolIdentity，只有准备成功且绑定一致时 enabled=true。未完成的配置不激活，重跑修复一致性，不能复制主应用 API key 配置给内网工具 app。按 H01 配置键导入用户明确提供的独立 Hermes 模型配置（data/assistant/hermes-model.json），缺失时才读取既有 DeepSeek 配置作为候选；密钥不回写既有 HE 配置，所有配置权限 0600/目录 0700，重复执行不覆盖现有密钥/偏好；Windows 对 chmod 作平台适配。先在 .gitignore 中加入 /data/hermes/ 与 /data/assistant/，再创建这些目录中的 profile/服务配置；用 git check-ignore 验证测试路径，检查输出不包含 secrets。目录权限同时匹配 H01 镜像 UID，不能因 chmod 造成容器不可读。
- [x] Step 6：运行 Step 2 测试并验证迁移重复执行、新旧库启动与两用户边界，预期 PASS；核对 staged diff 后提交 feat: add assistant identity and persistence。

### H02 验收证据

- 31项身份/存储测试通过（32.48秒），包含真实临时SQLite的双管理员并发准入、跨用户404、轮换/降权/停止/期限、工具身份与用户token分离。
- 全后端259项通过（81.13秒）；每次运行使用新的临时数据库。曾复用测试容器的数据库引起旧下载测试计数失败，已通过同测试的新库对照确认并消除验证环境污染。
- 新/旧数据库重复迁移保持用户记录；准备脚本在仓库和镜像目录布局均通过，重复准备保持密钥和偏好，输出脱敏，配置0700/0600。仅Linux容器实测，生产库/容器未迁移或部署。

## Task 3: H03 — 实现无副作用的媒体工具应用

**Files:** 创建 backend/app/assistant/{readonly,internal_app}.py；修改 backend/app/recommendations.py、assistant/models.py、assistant/schemas.py、app/migrations.py；测试 backend/tests/test_assistant_readonly.py、test_assistant_internal_api.py、既有 test_recommendations.py。依赖：H02。

**Interfaces:** execute_read_tool(db, principal: ToolPrincipal, context: ToolContext, name: str, args: dict) -> dict；查询只返回前述 DTO。internal_app 只注册 /tools/* 和不含敏感信息的健康检查。

- [x] Step 1：写失败测试，使用真实临时 SQLite、恶意标题和隐藏重复项，固定以下断言；补齐分页上限、未知 tool、无 token、其它用户 context、URL/token 脱敏。
~~~python
assert media.last_opened_at == before.last_opened_at
assert media.view_status == before.view_status
assert len(search_result.items) <= 50
assert "absolute_path" not in detail
assert audio_recommendation.method == "metadata_filter"
~~~
- [x] Step 2：运行 cd backend && python -m pytest tests/test_assistant_readonly.py tests/test_assistant_internal_api.py -q，预期新工具相关断言失败。
- [x] Step 3：实现只读 SQL/现有纯服务查询，保留现有隐藏重复状态默认过滤；不用 GET /media/{id}，不调用会改变播放历史的路由，不遍历媒体文件系统。
- [x] Step 4：为 recommendations.recommend_manga 增加 keyword-only allow_ai: bool=True，false 时使用既有 heuristic/retrieval/local_reason 并跳过偏好解析及 rerank 的内部 DeepSeek 调用；现有网页调用默认行为保留。管家调用 allow_ai=False，把 ORM 结果转成窄 DTO，由 Hermes 负责解释，避免单个 MCP 调用中叠加两次模型请求；其它类型按筛选条件、评分和 ID 做确定排序。返回 method/basis，信息不足时说明依据不足，不新建向量模型或下载权重，不声称分析过媒体内容。现有 MiniLM 缓存可在预算内复用，缺失时保留现有 BM25/元数据降级，并明确 method/basis；不触发媒体画像分析。统计/重复候选/标签列表限制返回规模，source URL 对模型默认省略。测试应断言管家推荐未调用 call_deepseek、旧推荐默认路径仍可调用 AI；工具进程不需要读取 DeepSeek key。
- [x] Step 5：实现独立 internal_app，通过受限 token 认证并验证 ToolContext；服务 key 只在该 app 有效，主应用不新增鉴权绕过分支。启动仅检查 H02 所需表，不启动扫描器、同步调度器或主应用 lifespan。 工具的业务查询保持只读；助手展示结果另存到 Run.tool_results_json，在返回工具结果前校验 DTO、用户/run 归属和 stop_requested_at/有效状态。该短事务允许写助手记录，internal HTTP 返回 ToolResultDTO 包装；H06 仅将 result 业务 DTO 回传 MCP。H05 结果列表使用 ToolResultsDTO {items,truncated}。新增 tool_results_truncated 并按既有幂等 ALTER 迁移旧库。展示记录总计超过 64 KiB 时保留此前结果、持久化超限标记并返回明确 truncated，不保存未校验原文；只读查询可缩小范围后重试，已生成的建议沿用原幂等记录，不能重放副作用；为每次调用生成 HE tool_call_id，桥接只传递受限结构。测试分别断言业务表不变和助手展示记录正确，停止/清除提交后不接受迟到结果。
- [x] Step 6：运行 Step 2 测试，预期 PASS；通过临时数据库前后快照确认只读工具没有业务写入，拒绝超过 64 KiB 的工具响应并提示缩小查询，再运行既有 tests/test_recommendations.py，预期默认推荐行为通过，按规范提交 feat: expose read-only assistant tools。

## Task 4: H04 — 实现变更预览、原子确认和扫描 job

**Files:** 创建 backend/app/assistant/{proposals,actions,scan_jobs}.py；创建 backend/app/routers/assistant.py 的 proposal/job 路由；修改 assistant/internal_app.py 注册两种建议工具、main.py 路由和恢复注册；测试 backend/tests/test_assistant_actions.py、test_assistant_scan_jobs.py。依赖：H02、H03。

**Interfaces:** create_proposal(db, principal, context, kind, payload) -> ProposalAckDTO；confirm_proposal(db, user_id, proposal_id, payload_hash) -> ActionResultDTO；reject_proposal(db, user_id, proposal_id) -> ProposalDTO；run_scan_job(job_id: str, folder_id: int, reservation: object) -> None；get_owned_scan_job(db, user_id, job_id) -> JobDTO。

- [ ] Step 1：先写真实临时 SQLite 并发测试，包含拒绝/过期/目标消失/用户降权/旧值变化/两次同时确认。明确新增 test_same_patch_different_targets_creates_distinct_proposals、test_stop_commit_before_confirm_blocks_write、test_confirm_commit_before_stop_preserves_result、test_clear_commit_before_late_proposal_blocks_creation、test_completed_run_pending_proposal_can_confirm；使用两个独立连接及同步屏障控制提交顺序，不依赖 sleep 猜并发。
~~~python
assert proposal.state == "pending" and media.rating == original_rating
assert confirm_after_manual_edit.status_code == 409
assert count_applied_audits(proposal.id) == 1
assert count_started_scans(proposal.id) == 1
assert restarted_scan.status == "interrupted"
~~~
- [ ] Step 2：运行 cd backend && python -m pytest tests/test_assistant_actions.py tests/test_assistant_scan_jobs.py -q，预期新建议/确认功能失败。
- [ ] Step 3：只接受前述 MediaPatch 字段或现有 folder_id，生成完整 before/after 与规范 JSON hash、300 秒 expires_at，并在 H02 唯一约束下幂等创建。normalized_payload_hash 必须包含版本、user_id/session_id/run_id、kind、target_id 和规范化 patch；before 快照与 expires_at 在首次插入时固定，重试不刷新。两个 media_id 使用相同 patch 不得冲突。只比较将修改的字段及完整标签关系，扫描另记录 folder 配置指纹（含路径但只在服务端保存）。MCP 只返回 ProposalAckDTO，HE 用户预览不含内部路径；若旧 source_url 含凭据，预览/审计显示脱敏值，旧值核验仅保存不可逆指纹。新增/移除标签各最多 20 个，拒绝空变更和互相冲突操作。预览无媒体写入；确认接口仅接收 proposal_id/hash，不能从浏览器重新指定 payload。
- [ ] Step 4：实现 metadata 确认：使用独立、干净的数据库连接开启 BEGIN IMMEDIATE 短写事务，再读 pending、重查权限、session active、run 未被用户停止/清除及旧值（正常 completed 可确认）、条件消费、修改目标标签/字段并写 audit；不得沿用已预读旧值的 ORM 事务。事务内不调用网络、不等待后台线程；不调用会自行 commit 的现有路由。停止/清除在自身短写事务中先设 stopping/deleting 并作废 pending，提交后再发网络 stop/delete；建议创建和确认也在同一写事务内复查状态，禁止“检查后提交”的竞态。成功 state=applied；重复确认返回同一结果；失败回滚；旧值/标签或 folder 配置指纹变化时仅提交 stale 状态而不修改媒体，然后返回 409，需重新生成建议。拒绝 state=rejected，过期 state=expired，不能复活。
- [ ] Step 5：实现扫描包装器：在主应用进程复用 reserve_folder_scan，确认前检查 storage_guard，先按现有 job_lifecycle 的容量规则准入，并在短写事务中确认没有其它未结束 assistant_scan；事务内消费建议为 queued，直接用本事务的 Session 插入 BackgroundJob(kind=assistant_scan) 和 audit，提交成功后再排队。现有 services/job_lifecycle.record_job 会打开独立 Session 并 commit，不能在此事务中调用，不能用其 best-effort 异常吞掉机制作为权威状态。管家生命周期用显式短事务更新 BackgroundJob/Proposal.result，数据库忙仅重试状态持久化、不重跑 scan；保存失败报告 job_status_unavailable，复用现有恢复/TTL/容量规则。scan_folder 返回 bool，包装器负责 running/completed/failed，并将限长终态快照写入 Proposal.result 供 job 历史清理后仍能查询归属和结果；事务失败/队列失败/任务 finally 均释放 reservation；reserve_folder_scan 为进程内锁，主后端维持现有单 uvicorn worker，不在内网工具进程启动扫描。排队失败记录 failed，启动恢复未结束任务为 interrupted，并同步对应建议结果；扫描不能回滚已经完成的逐项媒体更新，界面明确说明可能有部分结果，不自动重放。旧 /folders 扫描响应不变；一期只扫描一个已配置目录，不接受文件路径。
- [ ] Step 6：运行 Step 2 与既有 tests/test_scan_and_range.py、test_job_recovery.py、test_backup_and_storage.py，预期 PASS；提交 feat: require confirmed assistant actions。

## Task 5: H05 — 实现 Hermes 会话、run 和 SSE 代理

**Files:** 创建 backend/app/assistant/{hermes_client,sessions}.py；补齐 routers/assistant.py；修改 backend/requirements.txt（将已有 httpx==0.28.1 从 dev 可用变为 runtime 可用）、main.py 的管理员路由注册；测试 backend/tests/test_assistant_proxy.py、test_assistant_sse.py。依赖：H01、H02、H04。

**Interfaces:** HermesClient.create_session(profile, he_session_id: UUID) -> str；start_run(profile: ProfileBinding, envelope: SubmissionEnvelope) -> str；get_run(profile, upstream_run_id) -> dict；stream_events(...) -> AsyncIterator[EventDTO]；stop_run(...), delete_session(...), get_messages(...)。HTTP 字段及终态严格按 H01 fixtures。

- [ ] Step 1：用 fake upstream 写失败测试，覆盖助手离线不阻塞主应用启动、flag 关闭仍恢复既有 run、终态先于 executor 退出仍占槽、经过校验的 tool result 恢复，以及 profile 归属、创建请求超时后取回同一 run、断流重连、UTF-8/多行 SSE、保活注释、重复终态、上游 429/5xx/不完整 JSON。
~~~python
assert retry.client_request_id == original.client_request_id
assert retry.he_run_id == original.he_run_id
assert retry.upstream_run_id == original.upstream_run_id
assert he_restart_does_not_release_running_upstream_slot
assert canonical_final_message_count == 1
assert "API_SERVER_KEY" not in serialized_events
~~~
- [ ] Step 2：运行 cd backend && python -m pytest tests/test_assistant_proxy.py tests/test_assistant_sse.py -q，预期新适配功能失败。读取上游也须限制资源：JSON 响应最多 8 MiB、SSE 单事件最多 128 KiB、最终输出及 tool-result 展示各最多 64 KiB；按实际接收字节限制后再解析，超限返回 upstream_response_too_large 并继续核实 run/请求停止，不能因代理失败直接释放槽。
- [ ] Step 3：实现 H01 协议适配与 per-user profile 路由；用户请求不得传入 profile/key/upstream 地址或任意 upstream 路径。HE 先持久化 session 映射及预分配的 he-UUID upstream ID，再按 H01 创建；超时先 GET 同一 ID，对核验一致的 409 返回既有会话，不能无条件重发创建。server 生成 ToolContext 并加入本轮可信 instructions；上游校验 profile API key，内网工具校验 ToolPrincipal 与 ToolContext，不声称 Hermes 原生理解 HE 用户 ID。
- [ ] Step 4：实现主应用 endpoints：创建会话、读脱敏消息、发 run、读状态/SSE、停止。client_request_id 和 input_hash 持久化；upstream 始终用同一 Idempotency-Key 和固定 JSON 请求体；提交响应未知时保存 submission_unknown，不能换 key。固定 API credential generation 不变；轮换密钥会改变幂等作用域，未解决的提交不得用新 key 重发。超过 H01 实测的 upstream 幂等保留窗口仍无法确认时停止自动重试并关闭新 run，不能用过期 key 再建任务。限制并发 1、输入 8000 字符、8 轮及输出 token 预算；只读网络最多重试一次。浏览器断线仅脱离订阅，不自动新建 run；重连先查 status/history，不承诺已过期 SSE 缓冲能完整回放。
- [ ] Step 5：归一化公开事件为 text_delta、tool_status、run_status、error，不向浏览器代理原始 headers、内部路径、推理或不受限 tool result；H01 实测上游 tool.completed 只有截断至 500 字符的 preview，不能作为完整结果。H03 internal_app 在工具返回前按 H02 DTO 校验结果，并在独立短事务中记录到所属 Run.tool_results_json（总计 64 KiB）；HE 生成每次调用唯一 tool_call_id，不假设它等于 Hermes 的模型调用 ID。所有归属来自认证 token 和服务端 active run；请求体/模型文本不决定 user/run。H05 从该可信结果记录投影到 tool_status.data.result，供 /runs/{rid}/results 恢复；上游工具事件只提供开始/结束状态。未知工具或错误形状只显示状态，不显示原文；H01 须先证实能够关联 HE run/tool_call_id 的结果来源。MediaResults 只从该通道取数据，建议卡仍从 proposals endpoint 取完整预览；历史同样只返回限长、分页的用户/助手展示消息。text_delta 携带稳定 message_id，run_status 给出权威最终 output；重复终态和重连用替换/对账，不把完整答案再追加到半截流文本后。interim/commentary 不混入最终答案。终态按真实状态结束；stop 后确认 executor 已结束再放开并发槽；服务器 watchdog 根据持久化 deadline 独立执行 stop，不随订阅断开取消。恢复与 watchdog 使用独立后台任务和数据库连接，HTTP 客户端随应用关闭释放；主应用启动不等待上游健康或长轮询。恢复期间助手拒绝新 run，媒体库照常 ready。清除会话先停止活跃 run，作废 pending proposals，再删除 Hermes transcript；失败持久化 deleting 状态供重试，旧会话禁止继续写入，profile 偏好清理另按操作文档说明。
- [ ] Step 6：运行 Step 2 与 tests/test_auth_tokens.py，预期 PASS；启动时将未结束 run 标为 reconciling 并保留槽；已知 upstream ID 先读真实状态，未知 ID 在保留窗口内用原 envelope/幂等键解决提交；仍执行的任务请求 stop 并等待真实终态。HE 单独重启不代表 Hermes 已停止，无法核实时关闭新 run 并显示可处理故障；提交 feat: proxy Hermes sessions and streaming runs。

## Task 6: H06 — 实现限定 MCP 桥接和职责提示

**Files:** 创建 integrations/he_mcp/{__init__,server,client}.py、Dockerfile、requirements.txt、requirements-dev.txt、tests/test_tools.py；补齐 deploy/hermes/config.example.yaml、SOUL.md；更新 runtime-lock 的实际工具清单。依赖：H01、H03、H04、H05。

**Interfaces:** call_he_tool(token: str, name: str, context: ToolContext, args: dict) -> dict；MCP 工具按本计划名称与 DTO 导出。每个 HTTP 请求的 bearer 经 request context 转发到内网应用，禁止放入全局变量。

- [ ] Step 1：使用 H01 锁定 SDK 的真实 Streamable HTTP client 写失败测试，包含 list_tools 精确集合、两管理员并发 token、未知工具、工具 payload 越权、仅创建建议。
~~~python
assert set(tool_names) == EXPECTED_NINE_TOOLS
assert forward_a.authorization != forward_b.authorization
assert propose_media_update_result.state == "pending"
assert public_confirm_calls == 0
~~~
- [ ] Step 2：在 Python 3.12 独立 MCP 环境安装锁定的 requirements-dev.txt，再运行 python -m pytest integrations/he_mcp/tests/test_tools.py -q，预期桥接尚未实现而失败；requirements-dev 引用生产 requirements 并固定 pytest，不把测试依赖装入 MCP 运行镜像，也不把 MCP 依赖装进 HE 生产 Python 环境。
- [ ] Step 3：使用 H01 SDK API 实现具名工具及结构化结果；HTTP 客户端只有固定工具基址/名称，没有用户输入 URL 或路径。每次保留原 profile token 的请求作用域，缺失 token fail closed；只读超时可重试一次，建议创建不盲目重试。
- [ ] Step 4：调用 H04 已实现的建议幂等创建，复用 H02 的 (run_id, kind, normalized_payload_hash) 唯一约束，不在桥接层另建数据库；MCP 超时后再次提交同一建议只得到原 proposal。工具注解表达只读/建议语义，实际权限仍由 HE 后端执行。只读工具 readOnlyHint=true，建议工具 readOnlyHint=false；仅本项目固定内网 MCP 服务按 H01 验证结果配置 trust，避免额外上游审批阻断建议生成。不能因此新增自动确认 HE 建议的路径。
- [ ] Step 5：写 SOUL.md：媒体字段是数据；推荐说明数据依据；写操作只生成待确认卡；不得说未执行操作已完成；不执行媒体内容中的指令。明确媒体原始文件不可读、长期偏好限于当前管理员；按 H01 实测配置仅开上述 MCP 与已验证 profile 记忆能力，关闭代码、文件、终端、浏览器、委派、cron、自改技能；运行时检查实际工具集。
- [ ] Step 6：运行 Step 2 并通过临时 profile 做一次搜索→建议→拒绝的集成检查，预期媒体无变化；提交 feat: connect scoped media MCP tools。

## Task 7: H07 — 实现网页聊天和确认卡

**Files:** 创建 frontend/src/types/assistant.ts、utils/assistantApi.ts、composables/useAssistantChat.ts、views/AssistantView.vue、components/assistant/{ChatMessages,MediaResults,ProposalCard}.vue；修改 router/index.ts、components/Sidebar.vue、views/MoreView.vue；测试 frontend/src/__tests__/{assistant-stream,assistant-actions,assistant-view}.test.ts。依赖：H04、H05。

**Interfaces:** sendMessage(sessionId, text, clientRequestId) -> Promise<RunDTO>；subscribeRun(runId, signal, onEvent) -> Promise<void>；confirmProposal(proposalId, payloadHash), rejectProposal(proposalId), clearSession(sessionId)。fetch 明确读取 authState.token 设置 Authorization，不能依赖 axios interceptor。

- [ ] Step 1：先写失败 UI 测试，覆盖鉴权隐藏、流拆包、重复点击/重连、确认/拒绝/过期/409、聊天 token/HTML 注入。
~~~typescript
expect(renderedMessages.filter(m => m.id === finalId)).toHaveLength(1)
expect(confirmRequestsBeforeUserClick).toBe(0)
expect(untrustedTitleElement.querySelector('script')).toBeNull()
expect(requestHeaders.Authorization).toBe('Bearer user-token')
~~~
- [ ] Step 2：运行 cd frontend && npm run test -- src/__tests__/assistant-stream.test.ts src/__tests__/assistant-actions.test.ts src/__tests__/assistant-view.test.ts，预期新界面未实现而失败。
- [ ] Step 3：实现具备 TextDecoder 流解码的 fetch SSE 与 AbortController；页面卸载只取消订阅，显式停止按钮调用 stop。重复发送使用原 clientRequestId，重连读取 status/history，按 final_message_id 替换半截回复并对账，不能假设 upstream 支持完整 Last-Event-ID 回放；401 沿用登录失效行为。
- [ ] Step 4：实现独立聊天页（MediaResults 从 /runs/{rid}/results 和校验后的 tool_status.data.result 恢复）及桌面侧栏/手机“更多”中的管理员入口，复用 UI 组件和主题。提供发送、停止、历史、清除、错误/重试、usage 和工具状态（上游不提供 usage 时显示不可用，不按 0 或虚构费用）；不把 Docker/MCP 术语或内部端口呈现在日常聊天流。
- [ ] Step 5：建议卡从 HE proposals endpoint 获取完整预览，展示目标、before/after、期限和确认/拒绝；确认等待期间禁用按钮，409 要求重新生成建议。消息和标题纯文本渲染，不用 v-html；媒体打开复用现有详情 UI（用户主动打开后才更新观看记录）。扫描卡显示 job ID 的实际状态；停止聊天不宣称停止已确认扫描。
- [ ] Step 6：运行 Step 2 和 npm run build，预期 PASS；浏览器检查 320/390/768/1440px、键盘弹出、PWA safe area、焦点/按键和长文本，无横向溢出；提交 feat: add media steward chat interface。

## Task 8: H08 — 可选 Compose 集成、端到端验收与运维

**Files:** 创建 docker-compose.assistant.yml、scripts/run_assistant_acceptance.py、docs/hermes-operations.md；修改 Dockerfile、frontend/nginx.conf、README.md、PLAN.md；测试 backend/tests/test_assistant_acceptance.py。依赖：H01～H07。

**Interfaces:** 基础 compose + assistant override 启动 backend/frontend、assistant-tools、assistant-mcp、hermes-agent。assistant-tools 复用 backend 镜像运行内部 app；HE 镜像增加 /srv/deploy/hermes 模板与准备脚本，HE_ASSISTANT_TEMPLATE_DIR 支持覆盖路径，不能假设镜像有完整仓库布局；Hermes digest 与 profile root 取 H01 产物，MCP 单独 Python 3.12 轻量镜像。

- [ ] Step 1：用临时 SQLite/profile 和 fake Hermes 完成离线端到端用例：登录→搜索→建议→拒绝/确认→重复确认→扫描 job→断流/恢复→清除会话。验收测试断言无确认没有写入、tool token 不能调用主 app、两管理员无串话、重启不重放 job。
- [ ] Step 2：实现 Compose override；backend 对助手不设置硬健康依赖，助手失败不阻止媒体库启动。assistant-tools 无宿主机端口、无媒体盘。先从远端配置解析真实 SQLite 文件与所有敏感文件位置；共享 SQLite 必须让 db/WAL/SHM 位于同一可写父目录，不仅挂单个 .db 文件。若沿用 ./data:/data，必须以更具体的空只读挂载遮蔽 /data/hermes、/data/assistant、实际 DeepSeek 配置文件、备份及其它非必要目录；挂载源占位文件先创建，避免 Compose 把不存在的文件变成目录。不得继承主应用模型密钥环境变量，不授予 docker.sock。用同 worker UID 实测 DB 查询/建议写入可用，以及 profile/.env、API-key 文件、模型配置和备份不可读；遮蔽或权限验证失败不得部署。工具进程不迁移、不调用 create_all，只检查 H02 schema；主应用先迁移成功，schema 未就绪时工具 readiness 为 false，不接入主应用鉴权/调度 lifespan；MCP 不挂数据卷；Hermes 仅挂 ./data/hermes:/opt/data；HE profile/API-key 配置为 ./data/assistant/，示例及 runtime-lock 放 deploy/hermes/。工具链走专用内部网络，只有 Hermes 获得外部模型出口，助手专用网络设 internal:true（backend 保留原 Compose 网络，避免破坏现有外部源功能），并仅为 Hermes 增加明确 egress 网络；MCP 只在内部网络。按 H01 设置 CPU/内存/PID 限额、no-new-privileges，验证镜像所需可写目录；禁止 docker.sock/host network/privileged；仅在 backend 复用现有媒体卷做已确认扫描；运行 docker compose -f docker-compose.yml -f docker-compose.assistant.yml config --quiet 只验证配置，避免普通 config 输出展开密钥。
- [ ] Step 3：为 /assistant/ 独立配置 Nginx location ^~ /assistant/，proxy_buffering off、proxy_cache off、gzip off、600 秒读取超时、X-Accel-Buffering:no 和 no-store；保持正常 Bearer headers。HE 的 180 秒停止 deadline、停止最终落定与 10 秒左右上游 keepalive 均实测，重启 nginx 后确认多 chunk 到达浏览器而非结束时一次返回。
- [ ] Step 4：在隔离测试环境运行 H02～H07 的目标测试、相关 auth/scan/job/storage 回归、前端 tests 和生产 build；通过后运行 python scripts/run_assistant_acceptance.py --config <受保护验收配置路径>，预期 PASS。只用临时媒体目录验证真实扫描；真实库仅作只读搜索比对，不能用生产媒体跑修改/删除验收。
- [ ] Step 5：记录磁盘和内存基线、数据库在线备份、frontend/dist 备份、HE 当前镜像 digest、Hermes profile 一致性快照（profile 短暂停止或受支持快照）。用真实漫画推荐冷启动测量既有 MiniLM 的额外内存和峰值，核对 H01 资源阈值；新增表不破坏旧镜像，回滚禁用助手并恢复旧镜像/前端，禁止直接用旧数据库覆盖上线后的媒体改动。
- [ ] Step 6：按已获授权的实施范围进行最终部署；上线前完成全部验收并展示结果，部署授权尚未涵盖时留此步骤待批准。开启 HE_ASSISTANT_ENABLED 后检查健康、内网端口、无密钥前端、会话和只读真实查询；记录 provider/model/image 版本、实测预算与功能限制。任何一项未通过，保持开关关闭。记录 disabled → migrated → profiles_ready → services_ready → verified → enabled 的启用顺序；表迁移、profile 准备、健康检查和验收任一步失败均不翻开关。只生成了能力清单或 health=ok 不算 verified。
- [ ] Step 7：完成操作文档：profile 初始化/停用与管理员降权后的访问关闭、模型密钥快照/轮换（API key 轮换先排空/核实该 profile 的 run）、升级锁版本、日志脱敏/轮转与 profile 磁盘监控、会话与长期记忆清理区别、数据备份、rollback 和常见故障；提交未知/停止不落定时，仅在确认对应 Hermes profile 没有执行或网关已停止后解除占槽，不能只删除数据库中的 running 记录。在本计划逐步记录 H01～H08 证据，PLAN.md 只保留入口和整体进度，不复制一套任务状态，在 staged diff 复核后提交 chore: ship optional Hermes media steward。

## 完成与审查规则

每项先完成本项测试/验收，再标记已完成并提交；下一项只能使用已稳定的接口。禁止同时实施删除/下载/自动定时任务或另做无关重构。每次提交按 AGENTS.md 检查 status 和 staged diff；测试/构建使用隔离环境，不连接生产库。所有验证失败都保留未完成状态及原因。

最终检查覆盖设计各章：目标/范围→H03、H04、H07；架构/身份→H01、H02、H06、H08；会话/流→H05、H07；无副作用工具→H03；权限/确认→H02、H04；失败/资源→H01、H04、H05、H08；上线验收→H08。上游兼容性和资源预算当前属于待实施验证项，文档审查不能替代 H01 的运行证据。

## 第二轮文档审查结论

本轮结论：架构与 H01～H08 依赖划分合格；原本地版本仍有八项实施约束缺口，本草案已按对应任务补齐。它作为后续实施的文档基线，不能当作运行兼容性或生产部署已通过的证据。本轮依据为本地设计/计划快照、官方 API/profile/Docker 文档和官方 main 源码；审查期间 SSH 曾被关闭，现已恢复并核对远端 AGENTS、当前提交 0b16fbd、工作区及阶段 ledger。审查开始时 H01 仅有运行时检查器/测试的未提交工作；现已取得运行时门禁 PASS，后端228项通过并提交H01，H02 身份/持久化已验收并提交；H03～H08 未开始。

已核对远端文档只有 H01 状态/标题增量，合并时保留其进度；H01 已验证锁定镜像 digest/worker UID、真实 capabilities/endpoints、实际工具 schema、命名 profile、外部模型、停止/退出与资源预算。官方 main 只能提示检查点，不能代替所选镜像。H01 任一必需项失败或真实模型配置缺失，均保留未完成状态，不接入真实媒体库。

本轮详细问题与证据见 [审查记录](2026-10-10-hermes-media-steward-review.md)。

## 官方参考

- [Hermes Docker：镜像与 /opt/data 持久化](https://hermes-agent.nousresearch.com/docs/user-guide/docker)
- [Hermes API：runs、session、流式事件和 profile 鉴权](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/)
- [Hermes profile 与共享 gateway 路由](https://hermes-agent.nousresearch.com/docs/user-guide/multi-profile-gateways)
- [Hermes MCP：外部工具及过滤](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md)
- [MCP Python 官方 SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Hermes API 官方源代码：指定 session ID 的创建与查询行为](https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server.py)，H01 仍须在锁定 digest 上实测。
