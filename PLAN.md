# HE Manager 综合整改计划

> 来源：2026-07-26 对生产代码、Docker 运行状态、SQLite 数据、前端构建和后端测试的综合审查。
>
> 执行规则：按编号顺序处理。每完成一个项目，先完成该项目的验收命令，再把本文件对应复选框改为 `[x]`，与代码放在同一个 commit 中并 push 到 `origin/main`。不把多个未完成项目混进同一提交。

## 审查基线

- 生产媒体：2291 项；SQLite 约 4.2 MB，`PRAGMA integrity_check=ok`。
- 当前媒体分页、统计和搜索 SQL 平均低于 1 ms。
- 后端空闲约 92 MB RAM，前端 nginx 约 2.4 MB RAM。
- 后端 Docker 镜像约 8.94 GB，其中 CUDA/PyTorch/Triton 占主要空间。
- 前端生产构建通过；媒体核心测试 11/11 通过。
- 完整后端测试发现 95 项：93 项通过；2 项因生产镜像缺少 `git` / 测试环境缺少 `pytest` 未通过。

## P0：部署、性能与数据可靠性

### 1. [x] 精简后端镜像并补齐运行依赖

目标：N100 服务器只安装 CPU 版 PyTorch，移除无用 CUDA/Triton 依赖，并确保 BD2 的 git 下载功能在容器内可用。

- 固定并安装 CPU-only PyTorch，再安装 sentence-transformers。
- Docker 运行依赖加入 `git`。
- 增加独立 `backend/requirements-dev.txt`，包含 pytest 等测试依赖，运行依赖和测试依赖分离。
- 更新 Dockerfile 中已经过时的“仅 Android 客户端”说明。
- 记录新镜像体积；目标显著低于当前 8.94 GB。

完成结果：使用 `torch 2.9.1+cpu`，镜像由 8.94 GB 降至 2.47 GB；容器内 `torch.version.cuda is None`，`git 2.39.5` 可用；CPU 镜像内后端测试 98 项全部通过。

验收：

```bash
docker compose build backend
docker run --rm he-manager-backend:latest python -c "import torch; assert torch.version.cuda is None"
docker run --rm he-manager-backend:latest git --version
```

### 2. [x] 建立健康检查和容器运行基线

目标：容器状态能真实反映 API、数据库是否可用，而不只是进程是否存在。

- 增加最小公开 `/healthz`，检查 API 与 SQLite。
- `docker-compose.yml` 为后端增加 healthcheck，前端依赖健康后端。
- healthcheck 不输出密钥、路径或业务数据。
- lifespan 退出时停止可停止的后台调度资源。

完成结果：新增公开但不含业务数据的 `/healthz`，后端检查 SQLite；Compose 为前后端配置 healthcheck 和健康依赖；lifespan 退出时释放自动同步调度锁。生产容器均已验证为 healthy，未鉴权 `/media` 仍返回 401。

验收：后端、前端容器均显示 healthy；未登录请求只能读取健康状态，不能读取业务数据。

### 3. [x] 消除鉴权写放大并收紧 Query Token

目标：媒体页缩略图请求不再逐张提交 SQLite。

- `AccessToken.last_used_at` 最多每 10 分钟更新一次。
- Query Token 只允许用于缩略图、视频/音频流和漫画页等二进制 GET 请求。
- 普通 JSON API 只接受 Authorization Header。
- 清理过期、撤销且超过保留期的 token。
- 补充鉴权和更新时间节流测试。

完成结果：token 使用时间按 10 分钟节流；URL token 仅接受二进制 GET 路由；启动和登录时清理过期/旧撤销 token。生产验证 Header `/media`=200、Query Token `/media`=401、Query Token 缩略图=200，连续请求时间戳不变；历史 token 从 98 条清理至 7 条。后端测试 103 项全部通过。

验收：连续请求 36 张缩略图不会产生 36 次 token 更新时间写入；Header 鉴权保持兼容。

### 4. [x] 持久化配置与收紧敏感文件权限

目标：重建容器不会丢失 AI 配置或模型缓存，同机其他普通用户不能直接读取凭据。

- DeepSeek 配置迁移到 `/data` 或持久卷。
- HuggingFace 模型缓存挂载到持久目录。
- 数据目录建议权限 700，敏感文件建议权限 600。
- 保持已有配置向新位置的兼容迁移。
- 文档明确 X/ASMR Cookie、DeepSeek Key 的保存边界。

完成结果：生产 DeepSeek 配置改为 `/data/deepseek.json` 并支持旧路径迁移；HuggingFace/SentenceTransformer 缓存固定到 `/data/huggingface`；配置写入使用原子替换和 0600，SQLite/数据目录启动时收紧为 0600/0700，容器默认 umask 077。生产权限与持久环境变量已验证，后端测试 105 项全部通过。

验收：配置后重建后端容器，配置仍存在且 API 不返回明文密钥。

### 5. [ ] 恢复去重任务并治理内存 Job 生命周期

目标：重启或异常不会让媒体永久停在 `checking`，后台任务状态不会无限占用内存。

- 启动时重新入队 `duplicate_status=checking` 的媒体。
- 去重处理异常时落明确可恢复状态。
- 下载、推荐、X 导入/同步 Job 增加数量上限和 TTL 清理。
- 对重启中的 running 任务标记 interrupted，能恢复的任务提供重试入口。
- 增加重启恢复和清理测试。

验收：模拟中途重启后没有永久隐藏的 checking 媒体；完成任务超出 TTL 后会被清理。

## P1：查询、接口与前端交付

### 6. [ ] 清理高成本查询和 GET 副作用

目标：外部收藏与推荐查询随数据量线性、可控增长。

- `/external/favorites` 批量关联本地媒体，移除逐项 SQL/磁盘检查/commit。
- GET 列表接口不再修复或写数据库；修复动作放到同步或显式维护任务。
- 推荐候选一次 eager-load tags、AI profile、metadata profile。
- 为关键查询增加查询数量或回归测试。

验收：外部收藏列表 SQL 数量不随项目数 N+1 增长；推荐列表不产生逐媒体 lazy-load 查询。

### 7. [ ] 完成移动端与外部列表分页

目标：任何增长型列表都不默认整库返回。

- `/mobile/media` 增加兼容的 limit/offset/total；不破坏旧 Android 客户端。
- 外部收藏增加服务端分页和总数。
- `/media`、X 帖子、日志等 limit 设置合理最大值。
- 前端外部收藏面板接入分页或窗口化渲染。
- 更新 FEATURE_PLANS 中“Android 分页”的真实状态。

验收：大列表响应有明确上限；旧客户端未传分页参数时保持兼容。

### 8. [ ] 加固扫描并发和 Range 语义

目标：重复点击扫描不会并发处理同一目录，播放器获得标准 Range 响应。

- 增加 folder_id 级扫描锁和重复任务反馈。
- 限制视频预览图/VTT 生成并发。
- 修复扫描异常中未初始化局部状态。
- Range 支持正常区间、开放结尾和 suffix range；越界返回 416。
- 增加 Range 和并发扫描测试。

验收：同目录不能同时扫描；Range 回归覆盖 Web video、音频和 Android Media3 常见请求。

### 9. [ ] 优化前端首屏与 nginx 交付

目标：不打开详情时不下载播放器，公网静态资源有压缩和安全头。

- `MediaDetail` / Artplayer 改为按需异步加载。
- nginx 开启 gzip（JS/CSS/JSON/SVG）。
- nginx 静态响应增加 nosniff、frame deny、referrer policy。
- 移除 `via.placeholder.com`，改成本地占位。
- “继续观看”改为独立的全库最近打开请求。
- 保持指纹静态资源 immutable 缓存。

验收：首页网络瀑布不再预加载 Artplayer；压缩请求返回 `Content-Encoding: gzip`。

## P2：结构、测试和文档治理

### 10. [ ] 拆分前端巨型组件

目标：降低播放器和外部收藏改动的回归面。

- 拆分 `MediaDetail.vue` 为 shell、VideoPlayer、MangaReader、AudioPlayer、ImageViewer、MetadataPanel。
- 抽取进度同步、键盘/全屏、播放器生命周期 composable。
- 拆分 ASMR/WNACG/X 面板中的数据请求、筛选和任务轮询逻辑。
- 每次只做机械拆分，保持 UI 和 API 行为不变。

验收：单个核心组件职责清晰；前端构建和关键播放交互回归通过。

### 11. [ ] 拆分后端大型领域模块

目标：继续完成 Router/Service 分层，而不是形成新的千行 Service。

- `external_runtime.py` 按 WNACG、ASMR、封面、本地媒体关联、Job 拆分。
- `routers/external.py` 按来源拆 Router。
- `scanner.py` 按媒体类型拆分处理器。
- `auto_sync.py` 分离调度、执行、锁和日志。
- 保持路由路径和 response schema 不变。

验收：机械拆分阶段全套后端测试保持通过。

### 12. [ ] 决定并闭环标签管理功能

目标：删除“文档称已完成、实际不可用”的漂移状态。

- 二选一：完整实现 Tag namespace/count、迁移、CRUD/merge API 和 `/tags` 路由；或删除未接通的 TagsView/tagging 死代码并把功能改回未完成。
- 增加升级数据库迁移测试，不能只测试全新建库。
- 修正前后端 Tag 类型一致性。

验收：标签管理从侧栏可达且操作可用，或代码与路线图明确标记为未实现，不保留假完成状态。

### 13. [ ] 建立可重复测试与 CI

目标：干净环境能按照文档一条命令完成检查。

- 后端 dev requirements、pytest 配置和测试命令标准化。
- 推荐测试 mock HuggingFace 模型，不在测试中联网下载。
- 增加前端 Vitest：分页、鉴权状态、MediaDetail 关键状态。
- 增加最小 E2E：登录、媒体分页、打开/关闭详情。
- GitHub Actions 执行后端测试、前端类型检查和生产构建。

验收：CI 在无外网模型下载、无生产数据条件下稳定通过。

### 14. [ ] 更新文档与运维监控

目标：文档重新成为可靠事实来源。

- 更新 `CODE_REVIEW_PLAN.md`：main.py 拆分已经完成。
- 更新 `FEATURE_PLANS.md` 的 Android 分页、标签管理实际状态。
- README 补充 CPU-only AI 镜像、持久卷、备份恢复和健康检查。
- 备份任务增加新鲜度检查；挂载 HDD 时使用真实挂载或 sentinel，避免误写系统盘。
- 日志从散落 print 逐步迁移为结构化 logging，保留敏感信息脱敏策略。

验收：文档命令在当前 Linux Docker 画像可执行，备份过期能被发现。

## 长期可选项（不阻塞上述整改）

- 媒体达到 5～10 万项后，再评估 SQLite FTS5、组合索引或 keyset pagination。
- 跨标题重复检测再引入 pHash LSH/BK-tree；当前 normalized-title 候选策略保留。
- 若 Android release 滑动仍有瓶颈，再推进 LazyVerticalGrid 迁移。
