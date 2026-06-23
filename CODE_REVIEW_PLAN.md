# HE Manager 优化计划

> 更新日期：2026-06-23
> 原始代码审查中的轻量优化已完成；当前只保留仍有执行价值的任务。

## 当前结论

核心剩余任务是 **拆分 `backend/app/main.py`**。其它轻量优化已经完成或取消：

- `/media` 分页 + `selectinload`：已完成。
- 前端路由懒加载：已完成。
- `/auto-sync` admin 保护：已完成。
- downloader callback schema/token/path 校验：已完成。
- lifespan + `migrations.py`：已完成。
- 缩略图信号量：已完成。
- `creators.py` TTL 缓存 + 聚合查询：已完成。
- Pydantic v2 `ConfigDict`：已完成。
- `frontend/nginx.conf` SPA fallback：已完成。
- Alembic：已取消，继续保持幂等 `ALTER TABLE` + `migrations.py`。

## P0：拆分 `backend/app/main.py`

### 问题

`main.py` 仍是巨型入口文件，集中了承担不同职责的路由、下载编排、BD2 spine、媒体访问、清理任务、认证中间件和 helper。继续堆叠会导致：

- 搜索和修改成本高。
- `git add backend/app/main.py` 容易夹带无关 hunk。
- import 循环和模块级状态风险变高。
- 热重载抖动更明显。

### 目标结构

```text
backend/app/
├── main.py                  # 创建 FastAPI、CORS、lifespan、挂载 routers
├── routers/
│   ├── auth.py              # /auth /users
│   ├── media.py             # /media /mobile/media /stream /manga
│   ├── audio.py             # /audio/*
│   ├── external.py          # /external/* WNACG + ASMR
│   ├── x_import.py          # /x/*
│   ├── bd2.py               # /bd2/*
│   ├── dedup.py             # /dedup/*
│   ├── auto_sync.py         # /auto-sync/*
│   ├── recommend.py         # /recommend/* /ai/*
│   ├── stats.py             # /stats/*
│   └── creators.py          # /creators /mobile/creators
├── services/
│   ├── downloads.py
│   ├── external_media.py
│   ├── covers.py
│   ├── media_access.py
│   └── thumbnail_cleanup.py
└── migrations.py            # 已存在，继续集中幂等迁移
```

### 执行顺序

1. **只做机械搬迁，不改行为。**
2. 先抽 `routers/stats.py`、`routers/creators.py`、`routers/dedup.py` 这类低耦合路由。
3. 再抽 `auth.py`、`media.py`、`audio.py`。
4. 最后处理 `external.py`、`x_import.py`、`bd2.py` 这些状态和 helper 多的区域。
5. 每抽一组就跑后端测试；不要等全部拆完才验证。

### 状态处理

拆分时重点检查模块级状态：

- `DOWNLOAD_JOBS`
- `MANGA_PROFILE_JOBS`
- `MANGA_METADATA_JOBS`
- `EXTERNAL_COVERS_DIR`
- `_BD2_DOWNLOAD_STATE`
- 登录限流状态
- thumbnail / cover 目录常量

共享状态不要随意复制；需要集中时放进明确的 service/state 模块。

### 验收标准

- `main.py` 只保留 app 创建、middleware、lifespan、静态挂载和 `include_router`。
- 所有现有路由路径和 response model 不变。
- 后端测试通过：`python -m pytest tests -q`。
- 前端构建通过：`npm run build`。
- Windows 本地测试和 Linux Docker 部署画像都不被破坏。

## 运行画像要求

不要为了拆分或部署整理而分 Win/Linux 两套代码。

- Windows 是开发/测试画像，必须能直接跑后端测试。
- Linux 是部署画像，差异放在 `docker-compose.yml`、`frontend/nginx.conf`、`deploy_to_linux.py` 和环境变量。
- Nginx Proxy Manager 是外层入口，不等同于 `frontend/nginx.conf`。
- 平台特定能力必须做兼容封装，例如文件锁：Linux 用 `fcntl`，Windows 用 `msvcrt`。

## 暂不做

- 不引入 Alembic，除非用户重新确认。
- 不重写 Range/206 流式响应，除非能完整回归 Web `<video>`、Android Media3 和音频播放。
- 不迁移到 Pinia，当前手写 store 足够。
- 不把 Android 分页和 `main.py` 拆分混在一个提交里。
