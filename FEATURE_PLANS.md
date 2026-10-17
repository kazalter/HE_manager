# HE Manager 功能状态

> 本文只记录功能现状。优化任务、优先级和验收标准统一以 `PLAN.md` 为准。

## 已完成

- 个人数据看板：`/stats/*` + `StatsView`。
- 标签管理系统：统一命名空间、自动打标、回填、标签合并与管理界面（`/tags` + `TagsView`）。
- 创作者聚合页。
- Web 图片与漫画阅读自动播放：可设置 1～300 秒间隔，支持播放/暂停、到末尾停止和后台标签页暂停计时。
- Pawchive 外部源：公开帖子浏览与创作者范围、图片/视频跨帖跨页连续观看、明确选择后的附件下载与普通媒体入库；支持任务状态、取消和安全重试。
- 感知哈希近似去重；跨标题 LSH/BK-tree 为长期可选项。
- ASMR 同步、下载、播放、字幕、打标、镜像和体积控制。
- Android release + Baseline Profile 性能优化。
- 公网/FRP 鉴权与安全加固。
- `/mobile/media` 后端分页，并兼容不传分页参数的旧 Android 客户端。
- 存储与运维监控：SQLite 在线热备份（`sqlite3.backup` API）、备份新鲜度检测（`scripts/backup_db.py`）、Sentinel 存储挂载保护（`storage_guard.py`）与结构化日志体系。

## 待闭环

- **Android 分页 UI**：后端已支持 `limit`、`offset`、`X-Total-Count`，待后续 Android 端迭代接入。
- **Android 列表可选优化**：仅在 release 仍卡顿时，将卡片列表迁移到 `LazyVerticalGrid`。

## 业务约束

- ASMR 用户喜欢是私有播放列表，同步必须使用本人 token。
- ASMR 镜像由客户端多镜像 fallback，用户配置保存在 `source.favorites_url`。
- Android 性能只以 release 构建为准。

## 删除并丢弃（2026-10-12，已上线）

媒体卡片、详情、WNACG 收藏与 X 整帖提供确认删除；本地内容删除后持久保留“丢弃”状态，后续扫描、同步与下载跳过。支持丢弃记录、失败清理重试和显式允许重新下载。详见 [操作与发布记录](docs/media-discard.md)。

## 桌面端 0.1.0（2026-10-17，体验版）

新增 `desktop/` 共享客户端，面向 Mac arm64 / Windows x64；复用 Vue 媒体库，通过当前服务器鉴权 API 读取媒体。独立 mpv 窗口提供本地 Anime4K 档位切换；本地库 JPG/PNG 图片与漫画支持 Real-ESRGAN 超分、原图回退和客户端缓存。原生 GPU 验证与已知边界见 [桌面端说明](desktop/README.md)。
