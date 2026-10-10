# HE 管家能力与审批：实施、审查及发布记录

日期：2026-10-10。设计与计划已获用户批准，直接实施并发布到 Linux `/opt/stacks/he-manager`。

## 交付

- 保留左侧日期分组对话历史与首条问题自动标题。
- 24 个结构化 HE 工具：所有状态媒体、作者、目录/有界文本/鉴权预览、任务/已有自动同步日志/新增脱敏事件、存储/备份/非敏感设置；模型不接收媒体二进制，当前无图像/音视频分析能力。
- 管家业务写入仅生成提案；当前管理员逐次批准。支持资料、批量50项、标签改名/合并、扫描/维护，以及同文件系统内单媒体文件或漫画目录移动。
- 待审批数量、右侧抽屉、上下文跳转、批量重新预览、不可变完整影响清单、执行记录/进度/逐项结果。审批过期或目标变化需重新生成。
- 文件移动拒绝覆盖、越界、符号链接/硬链接、跨盘及无法核对的侧车/清单；持久意图日志、关联路径更新、失败回退和启动恢复。状态不明暂停冲突写入。

## 独立审查与修正

新上下文审查由 gpt-6-astra 完成，范围 `8d1c549..97286fd`。无 Critical，10项 Important 在一次修正中处理，提交 `3cd1a70`：

1. title/artist/view_status 的修改前值进入单项和批量指纹，原字段提案保持兼容。
2. 播放器、媒体详情和自动同步的路径检查写入进入互斥；先获得租约再读路径。
3. 扫描/下载/导入的租约放入生命周期 try 内，失败仍释放预约、更新任务并清理状态。
4. 单文件歌词、字幕、tracks.json、Pawchive 侧车及非漫画目录无法完整预览时拒绝移动。
5. 文本先有界全文件识别凭据，多行敏感值/私钥拒绝；URL 复用来源地址凭据策略；按完整行分页。
6. 设置结果 DTO/分页形状一致，返回校验失败与参数错误分开；来源设置只投影非敏感字段。
7. 保存完整不可变对象/关联清单，历史无需重新读取已移动的原路径；初始显示50项，其余分页。
8. 删除、合并或路径关系变化使提案提交 stale，明确要求重新生成。
9. 任务投影加入扫描、自动同步、当前用户管家运行、存储进度；已有自动同步业务日志只返回状态/计数/固定原因；新增结构化生命周期事件。
10. 重复复查明确展示全部可能的对比媒体，冻结允许写入的媒体 ID，新增对象不会被本次任务修改。

部分结果保留与卡片展示、next_offset 缺失重新评为 Important 并处理。备份完整影响清单随不可变快照实现返回项目对象。

## 实际检查证据

- Python 全部 app 源码语法编译、Git whitespace 检查通过。
- Vue TypeScript 与 Vite 生产构建成功；曾出现 ActionResultDTO.items 类型遗漏，按后端契约补齐后重建成功。
- backend / MCP Docker 构建成功；新镜像 app.main/task_reads 导入成功，工具数24。
- 发布前活动管家运行、扫描、后台任务和来源同步均0；SQLite 热备完整性 `ok`。
- 实际管理员 profile include 与 catalog 完全一致，24项；私有 .env 哈希保持，其他模型/提供商字段保持。
- 新表 assistant_tool_events / assistant_file_operations 与提案字段迁移存在。
- backend、assistant-tools、assistant-mcp、hermes-agent 健康 HTTP200；前端及上述服务 Compose 均 healthy。
- 在线 index.html/version.json 与 staging 逐字节一致；旧 hashed assets 保留。
- 在线只读 UI 查看：待审批抽屉显示数量0，关闭归还按钮焦点，实际目录/能力说明可读取。没有代用户批准真实修改。

没有新增或执行自动测试；依据上级开发者指令。没有运行媒体写入、文件故障注入、并发或回退验收。构建、源代码审查与健康不能代替这些动态行为证明。

## 备份与回退

- 新镜像：`he-manager-backend:assistant-approval-20261010`；MCP `he-manager-mcp:hermes-2.0.0`。
- 旧镜像：`he-manager-backend:before-assistant-approval-20261010`、`he-manager-mcp:before-assistant-approval-20261010`。
- 数据库与停止 gateway 后的私有配置快照：`data/backups/assistant-approval-20261010/{library.db,private-profiles.tgz}`，权限0600，目录0700。
- 前端和私有 Compose env：`/home/user1/he-manager-backups/assistant-approval-20261010/{frontend-dist.tgz,compose.env}`，权限0600。
- staging：`/home/user1/he-manager-builds/assistant-approval-20261010`。

紧急撤回先停用管家、确认全部已批准任务退出并检查未完成文件日志。可保留升级后的数据库回退媒体主应用镜像/静态资源；旧管家 DTO 不识别新增提案类型，不能直接重新启用旧助手读取新记录。恢复升级前数据库会丢失发布后的数据，必须经过用户另行授权；不能用恢复 DB 代替核对已移动文件。回退未在本轮执行。

## 实施取舍（完整 ledger rulings）

- Ruling: Work in approved main checkout — approved plan follows AGENTS single main and remote deployment — cost if wrong: live source checkout changes before build, protected by commits.
- Ruling: No tests added/run — developer prohibition supersedes TDD skill, plan records this — cost if wrong: behavior defects may escape static review/build.
- Task 3: complete — read-only roots, descriptor guarded file reads, bounded UTF-8, manga/image preview and 10-second ffmpeg audio/video preview. Compile/diff passed; no tests run. Ruling: current model image analysis stays disabled until supported multimodal capability is explicitly established; preview available to user — cost: Agent cannot describe pixels with current text model.
- Task 7: Ruling: shared/exclusive project-wide mutation lease instead of per-folder mutex — existing writer paths cross folder boundaries, concurrent normal jobs still coexist — cost: file moves require all current HE mutation work to finish; unresolved file recovery pauses all guarded writers. Pawchive preview cache excluded because it stores regenerable hashed remote cache, not registered media/DB path references.
- Task 8: Ruling: approval cards own actions and emit a shared refresh event — reuse existing ProposalCard state handling — cost if wrong: duplicate refresh or temporarily stale display; server approval remains authoritative.
- Task 9: Ruling: text continuation must start/end at line boundaries; lines over 32 KiB fail explicitly — prevents later chunks exposing a credential label omitted from the chunk — cost: oversized single-line text cannot be read.
- Final: Ruling: partial result preservation/card rendering and next_offset omissions re-graded Important — needed to tell the user what executed and continue bounded reads — cost if wrong: added display/query fields.
- Final: Ruling: reject implicit lyrics/manifests and non-manga directories — single-file journal cannot move undeclared sidecars — cost: some audio/Pawchive objects must be organized manually.
- Final: Ruling: duplicate recheck discloses all existing HE media as potential counterparts and freezes allowed IDs — worker writes pair/fingerprint/status on counterparts — cost: larger impact preview and more stale refusals.
- Final: Ruling: full text screen limited to 8 MiB before pagination, reject multiline credential values — incomplete chunks cannot safely recognize credentials — cost: oversized/credential-bearing files unavailable.

## 延后的小项

- Final: minor (deferred): execution-history tab includes pending proposals as full operation history; pending tab remains separate and accurate.

## 审查未动态判断的范围

实际 profile 配置、发布排空、迁移兼容和健康由本次发布检查补充；浏览器只读查看验证抽屉/焦点。文件系统故障恢复、并发写入、移动写入、浏览器异步竞态与手机真机未作动态验证。
