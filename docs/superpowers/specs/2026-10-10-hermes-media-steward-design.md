# Hermes Agent 媒体库管家设计

日期：2026-10-10
状态：待用户审阅
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
- HE 后端验证登录用户及管理员权限，维护 HE 用户与 Hermes 会话的映射，并将消息及流式事件代理到 Hermes。
- Hermes Agent API 和 MCP 桥接服务只加入 Compose 内部网络，不发布宿主机端口。
- MCP 桥接服务只调用 HE 的专用 assistant-tools 接口。它不直接读取 SQLite，也不挂载数据库、媒体目录或宿主机工作目录。
- HE 专用工具接口使用独立、范围受限的服务身份；不向 Hermes 或 MCP 暴露用户的普通管理员 access token。
- Hermes profile 持久化在专属数据目录中。该卷不包含媒体原文件或 HE 数据库。

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
7. 扫描操作返回现有后台任务 ID；聊天界面读取任务状态并在任务结束后汇报结果。

会话索引和 pending 操作/审计记录保存在 HE SQLite；对话正文与 Hermes session 状态保存在 Hermes 专属持久卷。用户可在 HE 界面清除会话。审计只保留已确认操作所需字段，不保存模型 API key 或完整提示词。

## 5. 工具边界与副作用

### 只读工具

- **search_media**：按关键词、类型、标签、收藏、观看状态等筛选，限制单次结果数。
- **get_media_detail**：读取指定媒体的必要元数据及标签。
- **get_library_stats**：读取现有媒体库统计。
- **recommend_media**：调用现有推荐逻辑。
- **list_duplicate_candidates**：读取重复检测摘要和候选项。
- **list_tags**：读取标签及计数。

### 需要确认的建议工具

- **propose_media_update**：返回限定字段的资料或标签变更预览。
- **propose_scan**：返回可扫描目录/范围与预期任务说明。

以上工具本身不得直接提交写入。用户确认后由 HE 专用 action endpoint 执行，且写操作必须幂等。扫描只在用户确认后排队。

一期不向 Agent 暴露媒体文件删除、文件系统读写、重复项合并、外部下载、Shell/终端、浏览器自动化、定时任务或任意代码执行工具。

现有 **GET /media/{media_id}** 会写入 last_opened_at 和观看状态，不可作为只读 Agent 工具。实现时需使用无副作用的查询服务或新建只读查询路径。

## 6. 权限、安全与数据处理

- 管家入口与 assistant API 初始仅对管理员开放；每个会话和 pending 操作都绑定用户 ID。
- 确认凭据必须短时、单次使用，并绑定用户、目标、操作类型与变更摘要；所有字段在执行时由后端重新校验。
- Hermes API key、模型密钥和 MCP 服务凭据只保存在服务端受限权限配置中；不得进入前端 bundle、浏览器存储、URL 或日志。
- Hermes 只启用必要的 MCP 和基础会话能力，关闭终端、文件、浏览器、代码执行、委派和定时任务等非媒体库工具。
- MCP 与 Hermes 只共享 Docker 内网；Hermes 不通过公网地址连接 HE Manager；MCP 只走 Compose 内部网，也不挂载媒体盘或数据库。
- 发往外部模型的上下文限于用户请求及完成查询所需的结构化元数据，不发送媒体文件内容或二进制文件。
- 媒体标题、标签、外部来源文本视为不可信数据，不将其解释为对 Agent 的额外指令。
- 工具输出与错误信息不包含 secrets、绝对文件路径或无关账户数据。

## 7. 失败与资源处理

- Hermes、MCP 或模型服务不可用时，HE 网页显示可恢复错误；媒体库其他功能保持可用。
- SSE 断开时允许按会话/run ID 恢复状态；前端支持停止当前 run。
- 只读请求可做有限重试；写入不自动重试。确认操作使用幂等键，结果不确定时先查询操作状态再决定是否再次提交。
- 扫描遵循现有 job 生命周期与容量限制；扫描失败或服务重启后回报现有任务状态。
- 初期限制活跃 Agent run 并发、单轮输入长度、查询返回条数和最大工具调用轮数，避免挤占媒体库服务资源。
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

后续实施计划按以下依赖顺序拆分：Hermes 运行时与模型兼容性验证、HE 受限工具与授权/确认模型、网页聊天和 SSE 会话、MCP 工具与写入预览、Compose 隔离/持久化/健康检查、端到端与资源验收。任何删除、合并、下载或非管理员支持均需单独设计和批准后再扩展。
