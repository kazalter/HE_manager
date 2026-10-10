# Hermes 媒体库管家运维

## 入口、范围与版本

管理员登录 HE 网页后进入“媒体管家”。可读取整个 HE 项目：所有状态的媒体资料、作者、登记媒体目录、UTF-8 文本、预览、后台任务、脱敏运行日志、存储与备份清单。文件限登记媒体目录且位于 `/mnt/hdd`，不读取账号凭据、原始数据库和备份内容。

所有业务写入先生成不可变提案，由当前管理员在聊天卡或右侧审批抽屉逐项批准。支持标题、作者、评分、收藏、来源、观看状态和标签；最多 50 项批量资料修改；标签改名/合并；扫描、缺失/重复复查、视频缩略图重建、备份；单媒体文件或漫画目录在同一文件系统内改名/移动。目标存在时拒绝覆盖，不支持永久删除、跨磁盘移动、任意终端或部署。建议有效期 5 分钟；目标变化需要重新生成，批量选择改变需重新预览。已批准任务通过审批历史及任务查询查看进度。

每位管理员独立 profile `he-user-<用户ID>`，API 密钥和工具令牌彼此独立。MCP 有 24 个 HE 工具，名单由 `assistant/tool_catalog.py` 统一维护；原生 memory 保存该 profile 的简短偏好。外部模型接收请求与工具结构化结果（含允许读取的脱敏文本），不会收到原始媒体二进制。当前模型不分析图片、音视频内容，网页可按需打开受鉴权的预览；音视频预览限前 10 秒。读取列表最多 50 项、文本每次 32 KiB 且按完整行继续、日志最多 200 条，截断显式返回继续位置。

锁定 Hermes 0.21.6 / 818c13be，镜像及协议见 [runtime-lock](../deploy/hermes/runtime-lock.json)。MCP 使用 Python 3.12 / MCP 2.0.0 / httpx2 2.7.0。独立模型为 DeepSeek 官方 `https://api.deepseek.com/v1` 的 `deepseek-flash`（DeepSeek-V4.1-Flash），关闭 thinking；每轮上限 8 次迭代、2048 输出 token、180 秒。全局一个运行槽，profile agent cache 最多 2。模型账单以实际 usage 和供应商账单为准。

## 可选部署与启用顺序

在服务器 `/opt/stacks/he-manager` 执行。基础 Compose 仍能独立启动；附加服务没有阻止主后端启动的硬健康依赖。正常维护统一使用两个 Compose 文件，避免后续单独基础 `up` 丢失助手网络与开关。

```sh
export HE_ASSISTANT_BACKEND_IMAGE=he-manager-backend:assistant-h08
export HE_ASSISTANT_ENABLED=0
docker compose -f docker-compose.yml -f docker-compose.assistant.yml config --quiet
```

不能打印普通 `config` 输出，它可能展开现有环境中的密钥。模型配置保存在 `data/assistant/hermes-model.json`，注册表为 `data/assistant/profiles.json`；目录 0700、文件 0600，禁止放入 Git、终端输出或前端。Hermes home 为 `data/hermes`，gateway worker UID/GID 1000:1000。主应用及这些专用目录应按实际 worker 权限准备；不要降低整个 data 的权限。

启用顺序必须是 `disabled → migrated → profiles_ready → services_ready → verified → enabled`：

1. 热备数据库、当前前端产物、Compose 环境和私有配置；记录旧后端 image ID。构建带新标签的 HE 镜像和 MCP 镜像，保留旧镜像。
2. 开关 0 启动主 backend，等待 healthy，由主应用完成幂等迁移。工具 app 不迁移，也不运行扫描调度器。
3. 仅为明确选定的现有管理员准备 profile，例如用户 ID 1。不要为普通用户初始化。

   ```sh
   docker compose -f docker-compose.yml -f docker-compose.assistant.yml up -d --no-build --wait backend
   docker exec he-manager python /srv/scripts/prepare_hermes.py --user-id 1
   ```

   如果主 backend 以 root 准备了新的 home，启动 gateway 前仅将 `data/hermes` 的目录与文件 owner 设为 1000:1000，并保持目录 0700/私有文件 0600；勿改变主 data 或媒体盘的 owner。

   重复准备保留 profile API key、工具令牌和长期记忆；尚未确认退出的 run 会拒绝准备。该命令不是密钥轮换功能。
4. 预先创建 `data/huggingface` 缓存目录并保持 1000 可读；占位目录 `deploy/hermes/empty-dir` 只能包含公开 README，占位文件必须是 `{}`。执行部署检查，再启动三个附加服务：

   ```sh
   python3 scripts/check_assistant_deployment.py
   docker compose -f docker-compose.yml -f docker-compose.assistant.yml up -d --no-build --wait assistant-tools assistant-mcp hermes-agent
   ```

   当前数据库为 `/data/library.db`，DB/WAL/SHM 和父目录均需属于 1000:1000。检查器校验共享可写父目录、挂载遮蔽、实际敏感文件清单及 owner。新增 data 文件或更换 DB 路径后重新检查；未知文件拒绝部署，先增加具体遮蔽和测试。工具以只读方式挂 `/mnt/hdd` 和 `data/assistant-logs`，共享 SQLite data 父目录用于记录工具结果/提案；备份、旧 DB、模型配置、profile 和密钥均被更具体的公开只读挂载遮蔽。MCP 没有数据卷。Hermes 仅挂自己 home，不挂 docker.sock。
5. 在隔离环境完成离线、原生链路、SSE、停止、权限、扫描和回滚门禁后，才可以把开关设为 1。仅 health 或工具清单不算验收。工具与主应用都需要重新创建以应用环境开关：

   ```sh
   export HE_ASSISTANT_ENABLED=1
   python3 scripts/check_assistant_deployment.py
   docker compose -f docker-compose.yml -f docker-compose.assistant.yml up -d --no-build --wait backend assistant-tools
   ```

6. 检查私有服务没有 HostPort、tools/MCP 只有 internal 网络、Hermes 才有 egress；使用选定管理员执行真实只读搜索，验证 SSE、usage、会话清理和原有媒体功能。任何门禁失败回到开关 0。单用户生产环境不要新建第二管理员来凑验收；双管理员隔离在临时库验证。

CPU/内存/PID 限额：tools 1 CPU/1024 MiB/128 PID，MCP 0.25 CPU/128 MiB/64 PID，Hermes 1 CPU/768 MiB/256 PID。tools/MCP rootfs 只读、cap_drop ALL、有限 /tmp tmpfs；Hermes 官方 root init 需要写 /etc 完成 UID 映射，实际 gateway 为 1000 且有效 capabilities 为 0。附加服务内存限额总和 1920 MiB，不能把各容器实际峰值或宿主机剩余内存当作限额。

## 可重复验收

在安装后端开发依赖、使用独立临时数据库的测试环境中运行。验收配置必须是独立的 0600 文件，脚本拒绝 symlink、超大输入和未知字段。

```json
{"mode":"offline"}
```

```sh
python scripts/run_assistant_acceptance.py --config /private/assistant-offline.json
```

离线验收覆盖真实登录、查询、无确认无业务写入、拒绝、明确确认、重复确认、两个管理员隔离、临时图片真实扫描、job 不重放、断流恢复和清除。不能指向生产数据库跑测试。

真实链路验收配置包含 `mode: live`、`api_url`、两个管理员的 `tokens`、`query` 和 `expected_media_id`。仅在隔离测试库运行双管理员脚本；它创建自己的会话、只搜索、验证可信工具结果及跨账号 404，完成后停止并清理。不要把配置中的 token 放进 shell 参数。生产只读验收只使用现有管理员，不修改真实媒体或启动扫描。

## 冷启动、日志与磁盘

2026-10-10：真实库一致性快照 2654 条，readonly/immutable SQLite、network none 的冷推荐已验证；当前 MiniLM **未缓存、未加载**，因此使用原有关键词/规则路径。不能宣称向量模型的内存已验收。新增或替换 Hugging Face 缓存前，必须在隔离容器装载该实际缓存，测量一次冷推荐及 cgroup memory.peak、OOM、模型成功加载和输出，核对工具 1024 MiB 与总 2 GiB 门槛。工具无外网，缓存只读；运行中不下载模型。

实际隔离原生 search→recommend→proposal→reject 峰值：gateway 545714176 B、tools 146927616 B、MCP 88686592 B，保守求和 781328384 B；无 OOM。Nginx 收到 121 个 chunk，首 chunk 0.034 秒、末 chunk 5.806 秒。首次构建后宿主机 MemAvailable 3861 MiB，系统盘剩余 8.2 GiB；这是测量时点，扩库/缓存/升级后重新测量。

三个附加容器日志各 10 MiB × 3 轮转；HE 不返回原始上游错误。Hermes home 内自己的日志和 session 数据不受 Docker 日志轮转覆盖，需定期监测 `du -sh data/hermes data/assistant`、磁盘剩余、容器 OOM/重启次数。人工诊断只抽取固定错误码和状态，不粘贴 profile .env、原始请求/响应、记忆或模型密钥到公开 issue。不要删除运行中的 SQLite WAL/SHM。

## 停用、降权、清理与轮换

- 全局停用：持久设置开关 0，重新创建 backend 和 tools。已接纳 run 的后台停止/恢复仍按持久状态处理，确认退出后再停 gateway；HE 媒体库可以独立运行。
- 账号被停用或取消管理员身份后，公共接口和工具鉴权均读取最新用户状态，立即拒绝。若仅停用某个工具身份，可在维护事务中设置该 user 的 `assistant_tool_identities.enabled=false`；仍需收敛已有 run，不能删除 run 或 identity 来释放占槽。
- “清除对话”先停止并确认执行器退出，再删除该会话上游历史及 HE 输入、最终消息、usage 和工具结果。长期偏好/记忆保留，建议会被撤销，历史审计保留。
- 清除长期偏好与清除对话不同。先排空该 profile 并停 gateway，备份后清理该 profile 的原生 memory/user profile 文件；保留 .env、config、注册表和工具身份。不按猜测文件名删除整个 profile。
- 模型密钥轮换：排空并确认所有相关 run 的 `executor_exited_at`，停 gateway，私密快照；用 0600 原子写更新独立模型 JSON 及每个已有 profile .env 的 `HE_ASSISTANT_MODEL_KEY`。重复 prepare 不覆盖已有 .env，不能代替轮换。启动并重做工具/stream/预算验收；失败恢复快照。
- profile API key / 工具令牌轮换：同样先排空/停 gateway。生成新随机值，同时更新 profile .env 的 `API_SERVER_KEY`、`HE_TOOL_TOKEN` 和递增的 `HE_API_KEY_GENERATION`；同步 HE 私有 profiles 注册表的 API key、generation、工具 token SHA256，以及该 identity 的 token hash、credential_generation。保持 user/profile 绑定不变，备份并用事务更新 DB、原子更新文件，失败时 gateway 保持停止。旧 run 使用原 generation，必须已退出。核对三处一致后启动；不同步会故障关闭，不能临时放宽鉴权。当前没有自动轮换命令，按此维护流程操作。

## 不明提交、停止未落定与重启

超时不等于未提交；HE 持久保存原 input、profile generation 和 Idempotency-Key，在上游 24 小时幂等窗内仅用同一 envelope 恢复，不能改请求 ID 再发一次。窗口过期、密钥变更、上游 shutdown/interrupted 或无法确认执行器退出时，保持全局占槽并给出错误码。health.active=0、终态字样或数据库没有 running 行都不能证明线程已经退出。

正常停止兼容 `interrupted_during_api_call`，以及锁定版本已实测的 between-tool `interrupted_by_user` 完整终态标记。裸 cancelled、未知退出理由或 shutdown 保留占槽。HE 重启先恢复/停止旧 run，扫描恢复只标记中断，绝不重放 job。

人工解除占槽前：禁用助手；保存 run/profile 状态；停止对应 gateway 容器并通过 Docker independently 确认旧容器 PID 已消失、没有第二 gateway/worker 实例；保留证据。仅在此后，以独立维护事务将受影响 run 标记 interrupted、记录操作错误码和 executor_exited_at，同时撤销 pending 建议。不要删除行，不提供公共解锁接口，不给 HE docker.sock。重启 gateway、确认 profile 代次匹配并重新验收后才能启用。若不能证明旧执行器消失，保持故障关闭。

## 备份与回滚

SQLite 必须用 online backup API 获得一致性快照，不能只复制活跃 .db；备份做 integrity_check。现有 `scripts/backup_db.py --db-path /data/library.db --backup --backup-dir <本次独立目录>` 可在装有 HE 依赖的环境运行。避免复用别的任务目录而触发其备份轮转。

一致性 profile 快照：排空 run，短暂停 gateway 后，以 0700 备份目录保存 data/hermes、data/assistant、.env、当前 frontend/dist、nginx 配置和旧 HE image ID；所有密钥快照 0600。保存 main SQLite online backup，恢复前比较当前媒体数据。2026-10-10 上线前备份位于 `/home/user1/he-manager-backups/hermes-20261010-084315`；完整性为 ok，旧 HE image 为 `sha256:5e259e34ac97127b414f51bbfee6a6516c315f3005218db7184dc4bfee60eac8`。私有快照勿加入 Git。

回滚顺序：关闭助手并收敛 run → 停附加服务 → 设置旧 HE image（可先用 Docker tag 保留旧 ID）→ 恢复旧前端产物和适配 nginx 配置 → 用相同 data/media 卷启动 backend/frontend → 验证健康和原有媒体 API。**保留当前数据库和新增 assistant 表，不用旧数据库备份覆盖上线后的媒体编辑。** 新增表对旧镜像是加法，旧镜像可忽略它们。只有独立的数据损坏恢复才考虑数据库快照，并先明确丢失哪些上线后改动。升级 Hermes digest、MCP、模型、预算或 profile 配置需要重跑锁定版本门禁，不能盲目跟随 latest。

手机布局已做 Chromium 320/390/768/1440 及 PWA 键盘模拟；真实 iOS 设备未验收，不能把模拟当作设备结论。

## 本次上线状态（2026-10-10）

生产已完成全部阶段并启用，管理员在 `http://192.168.0.101:8011` 登录进入“媒体管家”。现有管理员5的profile已准备；工具/模型身份隔离，未新增管理员。HE 镜像 manifest 为 `sha256:9882860c2e9253fbc8dde4dc45483a2aaf4d95803205abed4d15c10afc546942`，独立审查修复提交为 `61ebaae`。5个服务 healthy，附加服务无宿主机端口。

真实只读搜索及同请求完成重试通过（1次搜索、89个流分块、4.345秒、usage可用）；会话清理和临时登录token撤销完成。2654条媒体及8张业务表与上线前热备一致；无未落定run。最终后端353项、前端97项、MCP11项通过；静态文件实际凭据扫描零命中。完整门禁、实施取舍及一项待改文案见 [最终审查记录](hermes-implementation-review.md)。
