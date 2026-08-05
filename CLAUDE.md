# CLAUDE.md - HE Manager

Claude/Antigravity/Codex 都按 `AGENTS.md` 工作；不要在这里维护第二套长期规则。

## 必读

1. 先读 `AGENTS.md`。
2. 当前优化任务和执行顺序只看 `PLAN.md`。
3. `FEATURE_PLANS.md` 记录功能现状，`CODE_REVIEW_PLAN.md` 是历史结构审查归档。

## 额外提醒

- 一个代码库、一条 `main`；不要拆 Win/Linux 两套代码或长期分支。
- Windows 是本地开发/测试画像；Linux 是 Docker 部署画像。平台差异放配置和脚本，业务代码保持跨平台。
- Android 性能判断必须用 release 构建；debug 卡顿不代表真实体感。
- Android 主列表是 `LibraryScreenV2`；除非任务明确，不碰 `MangaActivity` 和 `player/PlayerActivity`。
- commit 前必须按 `AGENTS.md` 跑 `git status` 和 `git diff --cached`，避免夹带无关 hunk。
