# Hermes 媒体库管家计划第二轮审查

日期：2026-10-10
对象：2026-10-10-hermes-media-steward.md 本地快照
结论：**架构合格；原计划仍需补充。修订稿已补齐文档约束，远端代码复核与 H01 运行验收尚未完成。**

## 审查范围与限制

- 逐章对照已批准设计、八项验收标准、九个 MCP 工具、H01～H08 依赖与接口。
- 查阅 Hermes 官方 API、Docker、profile 文档和 API main 源码，核对接口发现、停止和鉴权语义。
- 三次 SSH 均返回 Connection closed，未能读取服务器当前 AGENTS、git status、最新文档和代码；本地副本可能落后于远端进度。
- 本轮只编辑本地 Markdown，不安装/运行 Hermes，不实施业务代码，不部署、不提交远端 commit。以下问题是可从计划文字识别的缺口，不声称已经在服务器代码中复现。

## 可保留的设计

独立 Hermes、独立 MCP、独立工具 app 的分工合理；浏览器只访问 HE，工具身份与用户身份分离。九工具中只有创建建议具有助手记录副作用，确认和真实扫描由 HE 主应用控制。管理员 profile、BEGIN IMMEDIATE 确认、扫描提交后排队、SSE 断流对账、预算和每阶段验收/commit 已有明确基础。

## 必须补齐的八项

| 级别 | 问题与实际后果 | 修订落点与验收 |
| --- | --- | --- |
| P1 | 接口发现尚无准确 JSON 判定规则；把 endpoint 名当 feature 会误判能力。仅看工具配置也无法证明模型收到的实际工具集合。建议工具还可能触发 Hermes MCP trust 审批而停滞。 | H01 检查 features + endpoints + 真实调用，以假 provider 抓取实际 schema；H06 正确设置只读注解并验证固定 MCP trust，不代理上游业务确认。 |
| P1 | assistant-tools 挂整个 ./data，可能同时读到 Hermes profile、模型配置、API-key 和备份。单挂 .db 又会破坏 SQLite WAL/SHM 共享。工具进程与主进程还可能同时迁移。 | H08 共享真实数据库父目录并遮蔽敏感子目录/文件；同 worker UID 验证可读写 DB、不能读秘密。只由主应用迁移，工具检查 schema readiness；工具 token hash 存独立身份表，遮蔽密钥配置后仍能鉴权。 |
| P1 | 建议去重键未明确包含 target_id；同 run 对两个媒体设置同一评分可能被当成同一建议。 | H02/H04 摘要明确覆盖身份、上下文、种类、目标和规范 patch；两个目标得到不同 ID，重试不延长 TTL、不复活终态。 |
| P1 | 停止/清除与确认/生成建议的并发顺序没有明确原子规则；可能先停止，随后仍修改媒体。 | H04 以 SQLite 写事务提交顺序决定胜者；两个连接、同步屏障覆盖两个顺序。正常完成后的有效建议仍可确认。 |
| P1 | 状态终结与 executor 退出容易混淆，尤其 shutdown/interrupted；误释放槽会超过全局一任务限制。 | H01 验证 stop、SIGTERM、SIGKILL、重启和超期 SSE；H05 只按实测退出证据放槽，无法核实保留门禁，不挂 docker.sock。 |
| P2 | H07 计划 MediaResults 组件，但 H05 又过滤原始工具结果，没有定义结构化结果入口。实现者可能解析模型文字或透传未脱敏结果。 | H01 验证可关联的结果来源；H02 定义 ToolResultDTO 与 64 KiB 存储上限；H05 校验/投影 tool_status.data.result 与 /runs/{rid}/results；H07 消费同一 DTO。 |
| P2 | 恢复可能阻塞 HE 启动；feature flag 关闭后也不能停止处理旧 run。网络输出仅限制展示大小，未限制解析前的大响应。 | H05 后台恢复/watchdog、助手门禁先关闭、媒体库独立 ready；JSON 8 MiB、SSE 单事件 128 KiB，按字节先限制再解析，超限继续核实/停止 run。 |
| P2 | “运行 UID”和磁盘预算容易只看 Config.User、压缩镜像；还缺区分假模型与真实外部模型的通过证据。 | H01 记录实际 gateway UID/GID、解包/缓存/日志/WAL/备份空间、峰值内存及真实 provider 验证；缺模型密钥不能算总 PASS。 |

P1 表示实施前必须有明确约束和验收；P2 表示进入对应阶段前必须落实。全部已写入本地修订计划，不表示实现已通过。

## 契约一致性检查

- H02 定义 SubmissionEnvelope；H05 start_run 使用固定 envelope，禁止重试时重建 model/instructions/预算。
- H02 定义 ToolResultDTO 与 Run.tool_results_json；H05 提供结果接口；H07 读取同一结果格式。
- H04 事务定义同时约束 H05 的 stop/delete 和迟到工具请求，不能各自采用内存锁。
- H01 是后续阶段门槛：隔离协议、真实外部模型、安全边界、profile、停止证据及资源预算均通过。
- Task 标题统一 Task 1～8，保留 H01～H08 标识，方便执行脚本定位。
- 主 PLAN 的整体进度与各任务证据需远端合并后核实；本轮不重写未知的实施状态。

## 下一次执行顺序

1. SSH 恢复后先读最新远端文档、代码、AGENTS 和已有阶段证据。
2. 只合并本轮增量，保留已完成步骤、提交和日志；不得用本地整文件覆盖远端。
3. 未完成的 H01 先取得运行证据；真实外部模型没有配置时如实记录缺项。
4. 后续每阶段完成本阶段验收及相关回归，再记录证据、commit，继续下一阶段。

## 参考与证据边界

官方 API 源码当前把 session_resources 放在 features，把 session_create/session/session_messages/session_delete 放在 endpoints；toolsets 使用 data 列表并标注 enabled。本轮以此识别计划检查点，执行时仍以锁定镜像为准。[官方 API 源码](https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server.py)

官方文档说明 stop 先返回 stopping，需等 executor 退出才结束；这支持计划必须区分请求停止和已退出。[API runs/stop 文档](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/)

官方 Docker 文档区分监督入口与实际 Hermes worker 的权限，并要求持久化目录权限匹配 worker。[Docker 权限说明](https://hermes-agent.nousresearch.com/docs/user-guide/docker)

[MCP 信任与工具配置](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/mcp.md)、[profile/gateway 官方文档](https://hermes-agent.nousresearch.com/docs/user-guide/multi-profile-gateways)用于确定运行验证范围；没有据此宣称服务器安装版本已支持。

## SSH 恢复后合并记录

远端连接已恢复。已核对 AGENTS、工作区、0b16fbd 提交、H01 ledger，确认远端计划仅有已知的标题/状态增量后合并第二轮审查。H01 的既有测试/检查器保留并继续，未把任何阶段标为完成；本轮审查期间断连说明保留为历史记录。工具 token hash 改为独立身份表以便敏感配置遮蔽后仍可鉴权。

## H01 实测后的进一步修正

- `/v1/toolsets` 仅枚举 native/plugin 目录：MCP 必须另外比对 SDK 与真实模型 schema。关闭 tools.tool_search，才能直接暴露精确九工具。
- run 顶层 max_tokens 无效，改用命名 provider 的 extra_body.max_tokens。SDK2 结构化工具必须有可序列化返回类型并显式启用。
- 上游 tool.completed 只有截断 preview：完整展示 DTO 由 HE 内部工具服务保存，前端不可从 preview 或散文恢复。
- stop 返回200/stopping；终态取消、网关重启中断与 executor 退出证据分别处理。180 秒提交预算仍由 HE 独立 watchdog 保证。
- 用户已提供独立 minimax-m3 配置；真实 Hermes→模型→假MCP→最终回答/usage 已通过。H01 全部门禁完成前仍保持未提交、生产关闭。

## H01 验收状态更新

锁定镜像的完整门禁已通过；最新隔离后端回归227项通过。后续 checker 模型契约变更需补跑回归。用户随后指定 DeepSeek-V4.1-Flash，新凭据直接请求返回401，保留已有可用模型并记录待切换，未声称新模型通过。阶段提交后继续H02。
