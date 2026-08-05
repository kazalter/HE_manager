# HE Manager 结构审查归档

> 本文不再作为执行计划。当前任务统一见 `PLAN.md`。

## 已完成的结构整改

- `backend/app/main.py` 已缩减为应用创建、middleware、lifespan、静态挂载和 Router 注册。
- 路由已迁入 `backend/app/routers/`：auth、media、audio、external、x_import、bd2、dedup、auto_sync、recommend、stats、creators。
- 共享运行逻辑已开始迁入 `backend/app/services/`。
- 数据迁移继续使用幂等 `migrations.py`，不引入 Alembic。
- Windows 开发/测试与 Linux Docker 保持同一套业务代码。

## 仍需处理的结构问题

以下工作已并入主计划，不在本文重复维护细节：

- `PLAN.md` #10：拆分前端 `MediaDetail.vue` 和大型外部来源面板。
- `PLAN.md` #11：继续拆分 `external_runtime.py`、`routers/external.py`、`scanner.py` 和 `auto_sync.py`。
- `PLAN.md` #13：补齐前端测试、E2E 和 CI。

## 保留约束

- 结构拆分只做机械迁移，不改变路由、response schema 或业务行为。
- 平台差异放在配置和部署脚本；业务模块不得硬依赖 Linux-only API。
- 播放与 Range 改动必须覆盖 Web `<video>`、音频和 Android Media3 回归。
