# Hermes Agent 媒体库管家设计

日期：2026-10-10
状态：用户已批准设计；2026-10-10 已按实施复核补齐细节
项目：HE Manager

## 1. 目标与已确认范围

在 HE Manager 网页中加入 Hermes Agent 聊天入口，让用户能用自然语言查询、理解和整理自己的媒体库。Hermes 作为独立 Agent 服务运行；HE Manager 保留用户身份、媒体数据和写入权限的控制权。

已确认的一期范围：

- 使用入口：HE Manager 网页内置聊天。
- 查询：媒体搜索与详情、媒体库统计、现有推荐能力、重复候选和标签列表。
- 建议与写入：管家可以提出标签/资料修改或启动扫描建议；用户必须在 HE 页面检查并确认后，后端才执行。
- 初始用户范围：HE 管理员。
- 媒体删除、重复项合并和下载不属于一期工具。
- 模型调用使用外部模型 API；先验证现有 DeepSeek 配置能否满足 Hermes 的工具调用和流式响应要求，不兼容时增加独立 Hermes 模型配置。

## 2. 仓库与部署基线

远程仓库 **/opt/stacks/he-manager** 当前为 **main** 分支。项目使用 FastAPI、Vue 3、SQLite 和 Docker Compose；应用已有 access-token 鉴权、媒体/标签/统计/推荐/去重 API、扫描后台任务以及 DeepSeek 配置。数据库变更遵循 **backend/app/migrations.py** 中的幂等迁移模式。

服务器当前为 x86_64、4 核、约 7.6 GiB 内存，系统盘约有 17 GiB 可用空间。Hermes Agent 与 MCP 运行时应纳入磁盘和内存预算；一期不在该主机加载本地大模型。

## 3. 架构

浏览器只访问 HE Manager 后端；HE 后端代理 Hermes 会话。Hermes 通过受限 MCP 工具访问 HE 专用接口，最后由现有业务服务和数据库提供数据或执行已确认操作。

- Vue 前端只连接 HE 后端，不持有 Hermes API key，也不直接访问 Hermes。
- HE 后端验证登录用户及管理员权限，维护 HE 用户与独立 Hermes profile/session 的映射，隔离每位管理员的长期记忆，并将消息及流式事件代理到 Hermes。
- Hermes API、MCP 和 HE 工具应用均不发布宿主机端口；工具互访使用专用内部网络，只有 Hermes 增加外部模型出口。
- MCP 桥接服务只调用独立 HE 内网工具应用的 /tools 接口；主应用不接受该服务凭据。它不直接读取 SQLite，也不挂载数据库、媒体目录或宿主机工作目录。
- HE 专用工具接口使用独立、范围受限的服务身份；不向 Hermes 或 MCP 暴露用户的普通管理员 access token。
- 一个 multiplex gateway 服务所有管理员，每位管理员使用独立 he-user-ID profile、API key 和 MCP tool token；未配置时拒绝请求，不回退默认 profile。Hermes profile 持久化在专属数据目录中。该卷不包含媒体原文件或 HE 数据库。

Hermes 官方提供 HTTP/SSE API 供自定义 Web 客户端使用，也支持通过 MCP 连接外部服务；其 API 默认工具面较宽，含终端和文件等工具。因此部署必须为 API 使用场景配置窄工具集，并对 MCP 工具实行 allowlist。

参考：

- [Hermes Agent API Server](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/api-server.md)
- [Hermes Agent MCP](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md)
- [Hermes Agent Programmatic Integration](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/programmatic-integration.md)

## 4. 请求与会话流程

1. 用户在 HE 网页打开管家并发送消息。前端使用已登录的 access token 调用 HE 的 assistant API。
2. HE 后端确认用户为管理员，确认会话属于该用户，并创建或恢复对应的 Hermes session。
3. 后端向内网 Hermes API 发起 run，并把 SSE 进度与回复流转发给前端。浏览器无法访问 Hermes API key 或内部服务地址。
4. Hermes 需要媒体信息时，只能调用本项目提供的 MCP 工具。每个工具有明确的输入 schema、结果上限和业务语义。
5. Hermes 若建议写入，工具仅生成结构化变更预览。HE 后端保存预览、调用者、目标、变更内容摘要和有效期；前端展示目标及变更前后值。
6. 用户明确确认后，HE 后端重新校验管理员身份、预览有效期、目标当前状态和 payload 摘要，再以一次性确认记录执行。拒绝或过期即作废。
7. 扫描确认由新增包装器创建 assistant_scan 后台任务 ID，复用现有 scanner 与 job_lifecycle；旧扫描 API 继续返回原有 Folder/目录列表。聊天界面读取持久化任务状态，重启后显示 interrupted，不自动重放。

会话索引和 pending 操作/审计记录保存在 HE SQLite；对话正文与 Hermes session 状态保存在 Hermes 专属持久卷。HE 在提交 run 状态未知期间另外保存限长、无密钥的固定 submission envelope，供同一幂等键跨重启恢复，成功取得上游 ID 后清除。用户可在 HE 界面清除会话；删除 transcript 与清理该 profile 的长期偏好是不同操作，界面和操作指南明确说明。审计只保留已确认操作所需字段，不保存模型 API key 或完整提示词。

## 5. 工具边界与副作用

### 只读工具

- **search_media**：按关键词、类型、标签、收藏、观看状态等筛选，限制单次结果数。
- **get_media_detail**：读取指定媒体的必要元数据及标签。
- **get_library_stats**：读取现有媒体库统计。
- **recommend_media**：漫画复用既有推荐检索，管家调用关闭内部 AI 解析/重排，避免嵌套模型请求；视频、音频、图片仅按已有元数据筛选排序，说明推荐依据与信息限制。
- **list_duplicate_candidates**：读取重复检测摘要和候选项。
- **list_tags**：读取标签及计数。
- **list_folders**：读取已配置目录的 ID、显示名称与状态，不返回路径。

### 需要确认的建议工具

- **propose_media_update**：为评分、收藏、无凭据来源 URL、媒体标签关系生成变更预览；标题/作者、观看进度、路径与全局标签重命名/合并不在一期修改字段内。
- **propose_scan**：仅为一个已配置 folder_id 生成扫描说明，不接受路径。

以上工具本身不得直接修改媒体或排队扫描。建议记录可写入 HE 的独立表；MCP 只返回建议 ID 和状态，完整 before/after 由 HE 用户接口提供。用户确认后由 HE 主应用 action endpoint 执行；建议有效期 300 秒，原子校验旧值、消费记录、修改字段/标签并写审计，重复确认返回原结果。扫描建议、job 和 audit 在同一事务中创建，提交成功后排队；进程崩溃不重复启动扫描，已完成的扫描部分更新不能自动回滚。

一期不向 Agent 暴露媒体文件删除、文件系统读写、重复项合并、外部下载、Shell/终端、浏览器自动化、定时任务或任意代码执行工具。

现有 **GET /media/{media_id}** 会写入 last_opened_at 和观看状态，不可作为只读 Agent 工具。实现时需使用无副作用的查询服务或新建只读查询路径。

## 6. 权限、安全与数据处理

- 管家入口与 assistant API 初始仅对管理员开放；每个会话和 pending 操作都绑定用户 ID。
- 确认凭据必须短时、单次使用，并绑定用户、目标、操作类型与变更摘要；所有字段在执行时由后端重新校验。
- Hermes API key、模型密钥和 MCP 服务凭据只保存在服务端受限权限配置中；不得进入前端 bundle、浏览器存储、URL 或日志。
- Hermes 只启用必要的 MCP 和基础会话能力，关闭终端、文件、浏览器、代码执行、委派和定时任务等非媒体库工具。
- MCP 只走专用 Docker 内网，也不挂载媒体盘或数据库；Hermes 只用内网地址访问工具、外部出口访问模型 API。主应用用户凭据与工具凭据不可混用。
- 发往外部模型的上下文限于用户请求及完成查询所需的结构化元数据，不发送媒体文件内容或二进制文件。
- 媒体标题、标签、外部来源文本视为不可信数据，不将其解释为对 Agent 的额外指令。
- 工具输出与错误信息不包含 secrets、绝对文件路径或无关账户数据。

## 7. 失败与资源处理

- Hermes、MCP 或模型服务不可用时，HE 网页显示可恢复错误；媒体库其他功能保持可用。
- SSE 断开时按 session/run ID 查询状态与脱敏历史；最终回复用稳定消息 ID 替换半截文本，不承诺过期事件完整回放。Nginx 为 /assistant/ 配置不缓冲/不缓存流；前端 fetch 显式携带用户 Bearer。
- 只读请求可做有限重试；写入不自动重试。确认操作使用幂等键，结果不确定时先查询操作状态再决定是否再次提交。
- 扫描遵循现有 job 生命周期与容量限制；包装器返回已完成、失败或中断状态。stop run 不宣称取消已确认扫描。
- 初期全局/每管理员最多 1 个未结束 Agent run，输入 8000 字符、查询 50 条、工具循环 8 轮、每次模型生成 2048 输出 tokens，180 秒请求停止；executor 实际退出前保留并发槽。HE 重启后必须核实或停止仍运行的 Hermes run，无法核实时关闭新 run，媒体库仍可使用。
- Hermes profile 和 HE 数据库分别备份；升级或配置变更前确认回滚方式及剩余磁盘空间。

## 8. 验收标准

设计实现完成后，至少验证：

1. 普通用户无法访问管家 API、会话或写入确认入口；管理员会话彼此隔离。
2. Hermes API、MCP 服务没有宿主机发布端口；前端产物和浏览器网络记录中没有 Hermes 密钥。
3. Hermes 只能看到配置的 allowlist 工具，不能执行终端、文件、浏览器、定时或代码工具。
4. 搜索、统计、推荐、标签、重复项查询结果与现有 HE 数据一致；读取媒体详情不会更新打开时间、进度或观看状态。
5. 模型提出修改后，未确认、拒绝、过期及重复提交均不会产生非预期写入；确认后只改变预览列出的目标和字段，并生成审计记录。
6. 扫描建议在确认前不排队；确认后返回任务 ID，页面能看到完成或失败状态。
7. Hermes/模型服务不可用、限流、超时、前端断流及容器重启均不会使 HE 媒体浏览或数据库不可用；活跃会话能按设计恢复或明确显示中断。
8. Docker Compose 构建、健康检查、内存/磁盘使用和数据备份/回滚流程符合服务器资源预算。

## 9. 实施拆分边界

实施任务依赖与验收以 [实施计划](../plans/2026-10-10-hermes-media-steward.md) 为准：H01 运行时实测与锁版本 → H02 身份/持久化 → H03 只读工具 → H04 确认/扫描 → H05 会话/SSE → H06 MCP → H07 网页 → H08 部署/验收。任何删除、合并、下载或非管理员支持均需单独设计和批准后再扩展。
