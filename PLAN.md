# HE Manager 优化计划

> 唯一主计划。`FEATURE_PLANS.md` 只记录功能状态，`CODE_REVIEW_PLAN.md` 只保留历史结构审查结论。
>
> 基线：2026-07-26 生产代码、Docker、SQLite、前端构建和后端测试综合审查。

## 执行规则

1. 按编号顺序，一次只完成一个任务。
2. 每项完成后立即执行该项验收和相关回归测试。
3. 验收通过后才把 `[ ]` 改为 `[x]`，并在同一 commit 中提交代码、测试和计划状态。
4. 不顺带修改后续任务；失败时保留未完成状态并记录原因。
5. Windows 开发/测试与 Linux Docker 共用一套业务代码。

## 审查基线

- 生产媒体 2291 项；SQLite 约 4.2 MB，`PRAGMA integrity_check=ok`。
- 媒体分页、统计和搜索 SQL 平均低于 1 ms。
- 后端空闲约 92 MB RAM，前端 nginx 约 2.4 MB RAM。
- 审查时后端镜像 8.94 GB；完整后端测试 95 项中 93 项通过，2 项因环境缺少依赖失败。

## 已完成

| # | 任务 | 结果 |
|---|---|---|
| 1 | [x] 精简后端镜像并补齐依赖 | CPU-only PyTorch；镜像 8.94 GB → 2.47 GB；容器测试 98 项通过 |
| 2 | [x] 健康检查和容器基线 | 前后端 healthcheck、SQLite 检查、健康依赖和退出清理已上线 |
| 3 | [x] 鉴权写入节流和 Query Token 收紧 | token 10 分钟节流；URL token 仅限二进制 GET；测试 103 项通过 |
| 4 | [x] 配置持久化和权限收紧 | AI 配置/模型缓存迁入 `/data`；敏感文件 0600、目录 0700；测试 105 项通过 |
| 5 | [x] 去重恢复和 Job 生命周期 | 中断任务可恢复；Job 具有 TTL/数量上限；测试 108 项通过 |
| 6 | [x] 高成本查询和 GET 副作用治理 | 外部收藏、媒体列表和推荐消除 N+1/GET 写入；测试 110 项通过 |
| 7 | [x] 移动端与外部列表分页 | API 分页已完成并兼容旧 Android；前端外部列表已接入；测试 111 项通过 |

## 当前任务

### 8. [ ] 加固扫描并发和 Range 语义

目标：重复点击扫描不会并发处理同一目录，播放器获得标准单区间 Range 响应。

- 增加 `folder_id` 级扫描锁，重复请求返回明确冲突。
- 限制视频封面和预览 VTT 生成的总并发。
- 修复扫描异常路径中未初始化的局部状态。
- 支持 `bytes=start-end`、`bytes=start-`、`bytes=-suffix`；不可满足或不支持的区间返回 416。
- 增加扫描并发和 Range 回归测试。

验收：同目录不能同时扫描；Web video、音频与 Android Media3 使用的常见 Range 请求均通过测试。

## 后续任务

### 9. [ ] 优化前端首屏与 nginx 交付

- `MediaDetail` / Artplayer 按需异步加载。
- nginx 为 JS/CSS/JSON/SVG 开启 gzip。
- 增加 `nosniff`、frame deny、referrer policy。
- 用本地资源替代 `via.placeholder.com`。
- “继续观看”改为独立的全库最近打开请求。
- 保持指纹静态资源 immutable 缓存。

验收：首页不预加载 Artplayer；可压缩资源返回 `Content-Encoding: gzip`。

### 10. [ ] 拆分前端巨型组件

- 拆分 `MediaDetail.vue` 为 shell、各媒体播放器和元数据面板。
- 抽取进度同步、键盘/全屏和播放器生命周期 composable。
- 拆分 ASMR/WNACG/X 面板的数据请求、筛选与任务轮询。
- 只做机械拆分，保持 UI 和 API 行为不变。

验收：前端构建和关键播放交互回归通过。

### 11. [ ] 拆分后端大型领域模块

- `external_runtime.py` 按 WNACG、ASMR、封面、本地关联和 Job 拆分。
- `routers/external.py` 按来源拆 Router。
- `scanner.py` 按媒体类型拆处理器。
- `auto_sync.py` 分离调度、执行、锁和日志。
- 保持路由和 response schema 不变。

验收：机械拆分期间完整后端测试持续通过。

### 12. [ ] 决定并闭环标签管理

二选一：

- 完整接通 Tag namespace/count、迁移、CRUD/merge API、`/tags` 路由与侧栏入口；或
- 删除不可用的 TagsView/tagging 死代码，并明确标记为未实现。

同时增加升级数据库迁移测试并统一前后端 Tag 类型。

验收：标签管理真实可达可用，或代码与文档均明确未实现。

### 13. [ ] 建立可重复测试与 CI

- 标准化后端 dev requirements、pytest 配置和测试命令。
- 推荐测试 mock HuggingFace，禁止测试时联网下载模型。
- 增加前端 Vitest：分页、鉴权、MediaDetail 关键状态。
- 增加登录、媒体分页、打开/关闭详情的最小 E2E。
- GitHub Actions 执行后端测试、前端类型检查和生产构建。

验收：CI 在无生产数据、无模型下载条件下稳定通过。

### 14. [ ] 文档与运维监控

- README 补充 CPU-only 镜像、持久卷、备份恢复和健康检查。
- 备份任务增加新鲜度检查；HDD 使用真实挂载或 sentinel，防止误写系统盘。
- 散落 `print` 逐步迁移为结构化 logging，并保持敏感信息脱敏。
- 最终核对主计划、功能状态和实际代码一致。

验收：文档命令可在当前 Linux Docker 画像执行，备份过期可被发现。

## 长期可选项

- 媒体达到 5～10 万项后再评估 SQLite FTS5、组合索引或 keyset pagination。
- 跨标题重复检测再评估 pHash LSH/BK-tree。
- Android release 滑动仍有瓶颈时再迁移 `LazyVerticalGrid`。
