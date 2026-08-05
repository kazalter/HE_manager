# HE Manager 功能状态

> 本文只记录功能现状。优化任务、优先级和验收标准统一以 `PLAN.md` 为准。

## 已完成

- 个人数据看板：`/stats/*` + `StatsView`。
- 标签基础体系：命名空间、自动打标与回填。
- 创作者聚合页。
- 感知哈希近似去重；跨标题 LSH/BK-tree 为长期可选项。
- ASMR 同步、下载、播放、字幕、打标、镜像和体积控制。
- Android release + Baseline Profile 性能优化。
- 公网/FRP 鉴权与安全加固。
- `/mobile/media` 后端分页，并兼容不传分页参数的旧 Android 客户端。

## 待闭环

- **标签管理界面**：现有代码和文档状态曾不一致，按 `PLAN.md` #12 核验后决定完整接通或移除死代码；在验收前不标记完成。
- **Android 分页 UI**：后端已支持 `limit`、`offset`、`X-Total-Count`，但 `LibraryScreenV2` 尚未接入。
- **Android 列表可选优化**：仅在 release 仍卡顿时，将卡片列表迁移到 `LazyVerticalGrid`。

## 业务约束

- ASMR 用户喜欢是私有播放列表，同步必须使用本人 token。
- ASMR 镜像由客户端多镜像 fallback，用户配置保存在 `source.favorites_url`。
- Android 性能只以 release 构建为准。
