# Hermes 媒体库管家运行契约

本文件记录 H01 的实际协议和后续部署约束。H02–H08 完成前，生产助手保持关闭。

## 版本与进程

- 官方镜像固定为 `nousresearch/hermes-agent@sha256:ffa4fbb471c2bc8c85fbcfc629347585cc1586c86d2e6db465d01203ce696d95`，已验证 amd64；Hermes0.21.6（上游818c13be）。升级必须重跑 H01，不能用 main 文档代替运行验证。
- 保留官方 init/s6 入口。PID1 为 root，实际 gateway 为1000:1000（HERMES_UID/HERMES_GID）；HE 私有目录0700、密钥0600。不要把镜像 Config.User 当成 worker 身份，也不要直接强制 `user:1000` 绕开初始化。
- Hermes 配置由其原生 `hermes_yaml` 读写，启动会迁移配置；不能把 config.yaml 永久当成 JSON，也不能凭空安装 PyYAML 修复迁移。
- 独立桥接环境：Python3.12、MCP2.0.0、httpx2 2.7.0。SDK2 使用 `MCPServer`、`ClientSession` 和 `streamable_http_client(..., http_client=...)`；传入独立 httpx2.AsyncClient，不把 SDK 放入 HE 生产环境。
- 结构化工具必须显式 `structured_output=True`，并使用具名 DTO 或可序列化的参数化返回类型；裸 `dict` 不能启用 SDK2 结构化输出。只读注解使用 `read_only_hint`，线上协议为 `readOnlyHint`。

## 配置与模型

参照 `deploy/hermes/config.example.yaml` 和 SOUL。该配置模板经过真实出站请求捕获确认：

1. `platform_toolsets.api_server: [he, memory]`，MCP include 精确九个工具，禁用 MCP resources/prompts。
2. `tools.tool_search.enabled: "off"`，避免额外发现/调用入口。实际模型 schema 只能是九个 `mcp__he__NAME` 和 `memory`。
3. 命名 `providers.he-model.extra_body.max_tokens:2048`；顶层 `/v1/runs` 的 max_tokens 被此版本忽略。
4. `agent.max_turns:8`。假 provider 连续请求工具时实际以 `max_iterations_reached(8/8)` 退出。
5. `agent.run_budget_seconds:180` 是附加预算。HE 必须另有从提交时刻计时、脱离浏览器/SSE 的持久化 watchdog，覆盖 agent 创建和 MCP discovery。
6. `gateway.api_server.max_concurrent_runs:1` 是上游保护，HE 还需以数据库事务限制全局及每管理员活跃 run。
7. 仅自有受限 MCP 设 `trust:full`，建议工具如实标注非只读。HE 的确认事务仍是唯一媒体写入入口。

独立模型配置在 `data/assistant/hermes-model.json`，不纳入 Git。HE 生成各管理员 profile 的 `.env`，将模型密钥放到 `HE_ASSISTANT_MODEL_KEY`。生产媒体原文件和主应用的其它凭据不得挂入 Hermes/桥接容器。

已验证 `https://api.feedmob.it.com/v1` / `minimax-m3`：直接工具调用及流式结构、完整 Hermes→模型→假MCP查询→最终回答/usage 都成功。该 provider 的流结尾有 finish_reason=stop 和 usage，但没有 `[DONE]`；判断完整输出需要终态证据，不能把 EOF 单独当成功。

## 会话、隔离与幂等

- 默认启动一个 multiplex gateway；管理员请求只走 `/p/he-user-ID/v1/*` 和 `/p/he-user-ID/api/sessions/*`，不回退默认路由。
- 命名 profile 只接受自己的 API key；默认/其它管理员 key 返回401。使用其它 profile 的 run/session ID 返回404。
- 两管理员测试偏好分别写入各自 USER.md，记忆互不包含。清除会话与清除长期偏好为不同操作；会话删除不等于删除整个 profile。
- capabilities 提供 features.session_resources；创建/读取/消息/删除以 endpoints 表里的 method/path 为准。
- POST /api/sessions 支持 `id` 与 `session_id`；成功201，同 ID 冲突409。重复 title 也会返回400 invalid_title。重试建会话先 GET 指定 ID 并核对归属，不套用 run 的幂等规则。
- 会话 GET/messages200；DELETE200，删除后 GET/再次DELETE404（HE 清除流程可以把已删除404视为目标达成）。
- POST /v1/runs 带固定 Idempotency-Key。相同参数重试202并返回同 run_id、replayed=true；同 key 不同参数409；记录可跨网关重启恢复。HE 固定请求 envelope 与 credential generation。

## 流、结果和停止

- SSE lifecycle 类型在每条 JSON 的 `event` 字段；帧包含 id，JSON 包含相同 seq，不要求有 event: 行。支持 UTF-8、多行 data、注释和重连去重。
- 已实测 tool.started、tool.completed、message.delta、reasoning.available、run.completed；推理不转发给 HE 网页。
- tool.completed 的 preview 最多500字符，缺少完整结构和模型 tool_call_id。HE internal_app 在返回前保存经过 DTO 校验的助手展示结果；HE 生成调用 UUID。H05 从该记录恢复，不能解析 preview 或模型散文构造媒体卡。
- 每事件128KiB、每 JSON8MiB，读取时先限长再解析；展示结果/最终文本另受64KiB界限限制。
- POST /v1/runs/{id}/stop 实际200、status=stopping。stopping 持续占槽；正常协作退出为cancelled，实测含 `interrupted_during_api_call`。不能只看到 HTTP200 或 interrupted 就放开并发槽。
- 正常终态由锁定源码中 await executor 返回后发布，结合对应退出原因形成正常退出证据。异常/shutdown/restart 的 interrupted 可能先于工作退出，保持故障门禁；只读 health 的 active_runs 不构成 executor 退出证明。
- SIGTERM 隔离测试：旧进程已退出，容器Exit0，无OOM，约3.27秒；重启约34.88秒ready。SIGKILL：旧进程已退出，Exit137，无OOM，约0.17秒；重启约42.86秒ready。原 run 变interrupted，固定幂等键仍返回原 run，不能自动重放。
- 运维恢复需验证旧 gateway 进程确实消失，再恢复新实例并核对中断状态。HE 不挂 docker.sock；无法核实退出时持续拒绝新 run，媒体库保持可用。启动恢复不能阻塞主应用 ready。
- SSE 缓冲只保留约5分钟，状态/幂等记录保留更久。过期事件404时回查 run、HE 最终消息和结果；不能凭404重建或重跑。

## 资源与后续部署

H01 测量范围是锁定 gateway、假 MCP、模型调用与隔离脚本。最终资源数据以 runtime-lock.json 为准；H08 还需测量真实工具查询/推荐峰值。

- Hermes、工具服务、MCP桥接总内存上限2GiB；预留系统 MemAvailable≥1GiB，根盘可用≥5GiB。
- 镜像解包约4.24GiB，不等于下载压缩包大小；安装前还需考虑层解包临时空间。
- 记录 profile/config/技能缓存、SQLite+WAL/SHM、日志/请求转储、Docker容器可写层和备份；持续记录 memory.peak 与 OOMKilled，不能只看某一刻的 docker stats。
- 只由主 HE 执行 migrations；工具 app 挂数据库所在目录供 WAL 工作，同时遮蔽 assistant/profile/model密钥、其它配置和备份。工具 app 仅检查 schema，不启动扫描或同步调度。
- 按 H08 顺序：disabled→migrated→profiles_ready→services_ready→verified→enabled；生产默认关闭，先完成验收再启用。SSE 的两层反代均需关闭缓冲。
- 备份通过 SQLite 安全备份流程。回滚应用镜像保留新增表；不能用旧数据库覆盖后续新增的媒体数据。

## H01 检查器

`python scripts/check_hermes_runtime.py --config <0600的隔离检查配置>`。

检查配置仅供两固定测试 profile 和默认 profile；必需 isolated_h01=true、内网 base_url、各 profile API key、完整 measured evidence_file。检查器验证完整实测证据，重新请求三 profile 的版本/capabilities/目录/隔离鉴权；缺少真实模型、预算、重启、SDK或资源证据都 FAIL。输出只含错误码或脱敏摘要，不回显配置、密钥或原始异常。

此检查器是 H01 实验门禁，不是对运行中的生产 profile 执行写入探测的入口。H08 需另做生产配置和健康预检。

## 模型切换记录（2026-10-10）

用户要求切换 `DeepSeek-V4.1-Flash`，直接工具调用认证返回401；未激活该凭据，继续保留已验证的独立 `minimax-m3` 配置。收到有效凭据后重跑直接工具/流式检查及完整 Hermes→假MCP 调用链，更新锁定记录；不能把旧模型的成功当作新模型验收。检查配置 `expected_model` 必须与外部实测记录一致。
