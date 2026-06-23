# HE Manager 代码审查报告与优化计划书

> 审查日期：2026-06-23
> 审查范围：`backend/app/**`（FastAPI）、`frontend/src/**`（Vue 3）、`Dockerfile`、`docker-compose.yml`、`nginx.conf`、部署脚本
> 审查方法：通读核心文件 + 静态分析（路由清单、模块依赖、依赖版本、并发模型）

---

## 0. 总体印象

这是一个**完成度相当高、注释质量极好**的个人媒体库项目。代码风格统一、关键决策都有"为什么这么做"的说明（如 WAL pragma、curl_cffi 指纹、路径穿越守卫等），测试基线 36 通过。从工程素养看，已经超过多数"个人项目"水准。

但有几个**结构性问题**会随规模（库增长到几千~上万条目、多用户并发）逐渐放大成本。本计划书按"严重程度 × 性价比"排序，给出可执行的优化路径。

---

## 1. 关键发现（按严重程度排序）

### 🔴 P0 — `backend/app/main.py` 巨型文件（5127 行）

**现状**：单文件包含 **100+ 个路由** + BD2 spine 解析逻辑 + 外部下载任务编排 + 缩略图清理 + 鉴权中间件 + 登录限流 + 数据库迁移 + 各种 helper（`_bd2_*`、`ensure_*_columns`、`download_*`、`upsert_*`）。

**后果**：
- 任何改动都要在一个 5000 行文件里上下翻，认知负担极高；
- `import` 循环风险（已经在用 `from . import xxx` 规避，但脆弱）；
- Hot-reload 在含空格路径上"常抖"（AGENTS.md 自己记录的坑），根源之一就是单文件改动面太大；
- 已经踩过的坑：`606b377` 把无关 hunk 顺手带进 commit（AGENTS.md 反面教材），就是巨型文件下 `git add` 颗粒度失控的体现。

**建议拆分**（保留 `app/main.py` 作为聚合入口，仅做 `include_router`）：

```
backend/app/
├── main.py                  # 仅 ~80 行：create app、CORS、startup、挂载 routers、迁移调用
├── routers/                 # 新增
│   ├── __init__.py
│   ├── media.py             # /media /mobile/media /stream /manga /mobile/... (约 600 行)
│   ├── audio.py             # /audio/* (约 200 行) + 现有的 scan_audio_tracks / parse_lyrics_file
│   ├── auth.py              # /auth/* /users (约 150 行) + 登录限流
│   ├── external.py          # /external/* wnacg + asmr (约 1500 行 ← 最大)
│   ├── x_import.py          # /x/* (约 300 行)
│   ├── bd2.py               # /bd2/* (约 700 行 ← 第二大)
│   ├── dedup.py             # /dedup/* (约 150 行)
│   ├── auto_sync.py         # /auto-sync/* (约 150 行)
│   ├── recommend.py         # /recommend/* /ai/* (约 200 行)
│   ├── stats.py             # /stats/* (约 50 行，转调 stats 模块)
│   └── creators.py          # /creators /mobile/creators (约 50 行)
├── services/                # 新增：从 main.py 抽出的业务逻辑（无 HTTP 依赖，便于单测）
│   ├── downloads.py         # download_wnacg_item / run_wnacg_download_job / download_asmr_item ...
│   ├── external_media.py    # upsert_external_downloaded_media / ensure_external_*_library ...
│   ├── covers.py            # ensure_asmr_cover_file / ensure_external_cover_cache ...
│   └── thumbnail_cleanup.py # cleanup_orphaned_thumbnails
└── migrations.py            # 所有 ensure_*_columns / ensure_*_indexes 集中
```

**执行风险**：纯机械拆分，但 `main.py` 顶部有大量**模块级常量**（`DOWNLOAD_JOBS`、`MANGA_PROFILE_JOBS`、`EXTERNAL_COVERS_DIR`、`_BD2_DOWNLOAD_STATE`）和**闭包共享状态**，拆分时要把它们挪到 `services/state.py` 或对应模块，避免循环 import。

**预估工作量**：1~2 天，纯重构无功能变更，测试基线 36 通过即可验收。

---

### 🔴 P0 — `/media` 端点无分页 + N+1 查询

**现状**（`main.py:2809-2857`）：

```python
@app.get("/media", response_model=List[schemas.Media])
def list_media(...):
    query = db.query(models.Media)...
    return query.all()   # ← 一次性拉全部，无 limit/offset
```

`schemas.Media` 带 `tags: List[Tag]`，`response_model` 序列化时对每行触发一次 `media.tags` 懒加载 → **经典 N+1**。1000 条媒体 = 1001 次 SQL。

**后果**：库一大就卡（前端 `HomeView.fetchMedia` 一次性渲染全部卡片，DOM 也会爆）。`/mobile/media` 同样问题（`main.py:2860`）。

**建议**：
1. 加 `limit: int = 100, offset: int = 0` 参数（移动端已经有了 `limit` 信封的雏形，见 AGENTS.md `/mobile/media`，但 web 端没用上）。
2. 用 `joinedload(models.Media.tags)` 或 `selectinload` 消除 N+1：
   ```python
   from sqlalchemy.orm import selectinload
   query = query.options(selectinload(models.Media.tags))
   ```
3. 前端 `HomeView` 改为无限滚动 / 分页加载，配合 `IntersectionObserver`。

**预估工作量**：0.5 天后端 + 0.5 天前端。

---

### 🟠 P1 — 数据库迁移机制脆弱（手写 ALTER + 重复函数定义）

**现状**：
- 13 个 `ensure_*_columns()` / `ensure_*_indexes()` 函数在**模块导入时直接执行**（`main.py:556-712`），靠 `inspect()` 判断列是否存在来幂等。
- 全靠人肉维护，没有任何版本号 / 迁移历史。新增列必须记得同时改 `models.py`（ORM 声明）**和**对应的 `ensure_*`（运行时 ALTER），两处不一致就会"新装的环境有列，老库没列，跑一半报错"。
- `_premigrate_backup_20260602-232710/` 目录的存在本身就是迁移不可靠的证据。

**另一个具体 bug**：`main.py` 里有**两个** `cleanup_orphaned_thumbnails`：
- `main.py:2515` `def cleanup_orphaned_thumbnails():`（带 `@app.on_event("startup")` 装饰，**模块级独立函数**）
- `main.py:2515` 同名 + `main.py` 2514 行的 `@app.on_event("startup")` 挂的就是它

但 `main.py:2514` 上方还有一个 `def cleanup_orphaned_thumbnails():` 在 2515 行——后一个会**覆盖**前一个定义。需确认哪个是真正想跑的（看起来 startup 挂的是正确版本，但代码读起来很迷惑）。

**建议**：引入 **Alembic**（SQLAlchemy 官方迁移工具）：
```bash
pip install alembic
alembic init backend/alembic
alembic revision --autogenerate -m "baseline"
```
- 把现有 `ensure_*` 逻辑转成 baseline revision；
- 之后所有 schema 变更走 `alembic revision`，CI 里跑 `alembic upgrade head`；
- 顺带修复重复函数定义。

**注意**：`AGENTS.md` 明确写了"已建迁移用幂等 `ALTER TABLE`（对标 `sync_position` 写法），零结构迁移惯例"——这是**有意的项目约定**。引入 Alembic 是改变约定，建议先和项目负责人确认（见第 4 节决策点）。

**预估工作量**：1 天（含 baseline 生成 + 现有库验证 + 修重复函数）。

---

### 🟠 P1 — 模块导入时执行迁移（启动副作用）

**现状**：`main.py` 顶部 `ensure_*_columns()` 在 `import app.main` 时就跑 ALTER TABLE，意味着：
- 跑测试也会触发迁移（测试用临时库，污染）；
- 多 worker（虽然现在是单 uvicorn）启动会并发 ALTER；
- 任何 import 错误都会卡在迁移阶段，错误信息不直观。

**建议**：迁移移到显式的 startup hook（`@app.on_event("startup")` 或 lifespan），测试用独立 fixture 创建 schema。

---

### 🟠 P1 — `requirements.txt` 缺失 `sentence-transformers`

**现状**：`manga_vector.py:65` 和 `manga_profiles.py:410` 都 `from sentence_transformers import SentenceTransformer`（函数内懒加载），但 `requirements.txt` **没列这个包**。

**后果**：
- 全新机器 `pip install -r requirements.txt` 后，第一次访问 `/recommend/manga` 会 `ImportError`；
- Docker 镜像里也没有这个包（Dockerfile 只装 requirements.txt）；
- `manga_vector.py` 注释说"~117MB on disk + ~200MB RAM"——这本来是有意不预加载的，但**依赖本身必须声明**。

**建议**：
```diff
# requirements.txt
+ sentence-transformers==4.2.0   # 或当前实际用的版本
```
或者拆成 `requirements-optional.txt`（推荐系统专用），Dockerfile 按 `HE_ENABLE_RECOMMEND` 决定装不装。

**预估工作量**：10 分钟（确认版本 + 补依赖）。

---

## 2. 性能相关

### 🟡 P2 — 视频缩略图生成全局锁（单并发）

**现状**（`scanner.py:30`）：`THUMBNAIL_LOCK = threading.Lock()` + `get_video_thumbnail` 整个函数体在 `with THUMBNAIL_LOCK:` 内。也就是说**全库同时只能给 1 个视频生成缩略图**。

**后果**：扫一个大视频目录时，几百个视频串行处理，每个要 `cv2.VideoCapture` 逐帧 seek。100 个视频 × 平均 2 秒 = 3+ 分钟，期间扫描任务完全卡住。

**建议**：把锁从"全局串行"改成"信号量限并发"：
```python
import threading
THUMBNAIL_SEMAPHORE = threading.BoundedSemaphore(value=2)  # 2 并发，按 CPU 调
```
配合 `ProcessPoolExecutor` 更佳（cv2 释放 GIL 但 seek 本身是 IO+CPU 混合），但对个人库信号量已足够。

**注意**：cv2 多线程在某些 codec 上有竞态（已知 issue），先用信号量 2 并发验证。

---

### 🟡 P2 — `creators.py` 多次全表扫描

**现状**：`_x_creators()` 内部连调 `_media_counts` / `_display_names` / `_covers` / `_posts_known` / `_posts_in_library`，**每个都是一次独立的全表 GROUP BY 查询**。`stats._top_creators` 又会调 `_x_creators + _artist_creators`，所以一次 `/stats/highlights` = 至少 6 次 SQL。

**建议**：合并成 1~2 次查询（用 `with_entities` + 多列聚合），或给 creators 加 30s TTL 缓存（对齐 stats 的做法）。库当前才几百条影响不大，但 highlights 和 creators 页面是高频访问。

---

### 🟡 P2 — 前端路由无懒加载（首屏全量加载）

**现状**（`router/index.ts`）：除了 `Bd2SpineView` 的 embed 路由用了 `() => import(...)`，其余 10 个视图全是**静态 import**（顶部 `import HomeView from ...`）。

**后果**：`npm run build` 后首屏 chunk 包含 StatsView（846 行）、MediaDetail（962 行）、所有 external 面板——首次访问要下载全部 JS。

**建议**：全部改 `() => import('../views/XxxView.vue')`：
```typescript
{ path: '/', name: 'home', component: () => import('../views/HomeView.vue') }
```
Vite 会自动按路由分 chunk。StatsView、DedupView、Bd2SpineView 这种重页面拆出去收益最大。

**预估工作量**：30 分钟。

---

### 🟢 P3 — 流式响应的 `get_ranged_file_response` 每次都 `os.stat` + 全量读

**现状**（`main.py:54-105`）：每次 Range 请求都 `open(file_path, "rb")` + 手动 seek。对大视频（多 GB）每次 seek 都要重建文件句柄，HTTP/2 多路复用下可能抖。

**低优先建议**：FastAPI 有 `fastapi.responses.FileResponse`（底层用 `anyio` 支持自动 Range），可以替换手动实现，除非有特殊需求（看了下没有）。但**手动实现对 `206` 的边界处理写得是对的**，换掉前先回归测试 Media3 identity 播放（AGENTS.md 提到的坑）。

---

## 3. 安全 / 健壮性

### 🟡 P2 — `/auto-sync/*` 路由未列入 `ADMIN_PREFIXES`

**现状**：
```python
ADMIN_PREFIXES = ("/users", "/folders", "/search-folder", "/system", "/external", "/x", "/dedup")
```
`/auto-sync/proxy` 的 PATCH（`main.py:5116`）能**修改全局代理设置**——这是敏感操作，但 `/auto-sync` 不在 admin 前缀里，**普通用户（非 admin）登录后就能改全局代理**。

**建议**：把 `/auto-sync` 加进 `ADMIN_PREFIXES`，或者确认这是有意设计（毕竟项目说"无鉴权 web 依赖"用于 ASMR 端点）。
```python
ADMIN_PREFIXES = (..., "/auto-sync")
```

---

### 🟡 P2 — `LOGIN_FAILURES` 是进程内 dict，重启即清零 + 多 worker 不共享

**现状**（`main.py:1381`）：`LOGIN_FAILURES: dict[str, list[float]] = {}` 是模块级变量。uvicorn 重启（`--reload` 热重载！）就清空限流计数，攻击者只要触发一次重载就能无限重试。

**建议**：
- 个人项目影响小，但如果要暴露到公网（FRP 子域名），至少加 `HE_LOGIN_FAILURES_FILE` 持久化到磁盘；
- 或者依赖前端 nginx 的 `limit_req`（已经在用 nginx 反代）。

---

### 🟡 P2 — `/external/downloader/callback` 用 `payload: dict` 无 schema 校验

**现状**（`main.py:4846-4847`）：
```python
def downloader_callback(payload: dict, item_id: int, source_type: str = "wnacg", ...):
```
- 用 `dict` 而非 Pydantic model，所有字段都要手动 `(payload or {}).get(...)` + 类型检查；
- `job.get("dir")` 直接拿来做路径拼接（`external_item_download_dir`），虽然后面有 `upsert_*` 内部的路径处理，但**缺少对 `item_dir` 的路径约束校验**（不像 BD2 spine 那样有 `realpath` 守卫）；
- 而且 docker-compose 注释提到 `HE_CALLBACK_TOKEN`（admin token），但代码里**没看到对 callback 的 token 校验**——任何能访问该端点的人都能触发 upsert。

**建议**：
1. 定义 `schemas.DownloaderCallbackPayload`；
2. 在端点开头校验 `HE_CALLBACK_TOKEN`（query 或 header）；
3. 对 `item_dir` 做 `realpath` + 前缀校验，防止 `../` 逃逸。

---

### 🟢 P3 — `os.getcwd()` 依赖隐式工作目录

**现状**：大量 `THUMBNAIL_DIR = os.path.join(os.getcwd(), ".thumbnails")`（`main.py:739`）、`EXTERNAL_COVERS_DIR = os.path.abspath(os.path.join(os.getcwd(), "..", "covers"))`（`main.py:1376`）。Docker 里 `WORKDIR /srv` 所以 OK，但裸机跑 `python -m app.main` 时 cwd 不同就指向不同位置。

**建议**：统一用 `BASE_DIR = os.path.dirname(os.path.abspath(__file__))` 推导（`database.py` 已经这么做了），或加 `HE_DATA_DIR` 环境变量。

---

## 4. 代码质量 / 可维护性

### 🟢 P3 — Pydantic v1 风格的 `Config` 类

**现状**：所有 schema 用 `class Config: from_attributes = True`（`schemas.py`）。Pydantic v2（项目用 `pydantic==2.13.3`）推荐 `model_config = ConfigDict(from_attributes=True)`。当前写法仍兼容（v2 有兼容层），但 v3 会移除。

**建议**：批量替换为 `model_config = ConfigDict(from_attributes=True)`。低优先级。

---

### 🟢 P3 — `@app.on_event("startup")` 已废弃

**现状**（`main.py:2514`）：FastAPI 0.93+ 推荐用 `lifespan` context manager。当前 `fastapi==0.136.1` 仍支持但会 DeprecationWarning。

**建议**：
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_orphaned_thumbnails()  # startup
    auto_sync.init()               # 启动调度器（如果需要）
    yield
    # shutdown

app = FastAPI(lifespan=lifespan, ...)
```

---

### 🟢 P3 — 前端 `reactive` + 导出对象的 store 模式 vs Pinia

**现状**：`stores/*.ts` 用 `reactive` + 导出对象字面量（`asmrDownloadStore.ts:154`），是手写的"穷人版 Pinia"。项目没装 pinia。

**建议**：保持现状即可——对当前规模够用，迁移到 Pinia 收益不大。但如果 store 继续增长（>6 个且互相依赖），考虑引入 pinia 统一状态层。

---

### 🟢 P3 — 重复的"missing 自动修复"逻辑

**现状**：`_get_audio_media_or_404`、`stream_media`、`stream_mobile_media`、`get_media` 各自写了同样的 `if not os.path.exists(): media.is_missing = True ... elif media.is_missing: media.is_missing = False ...` 块（4 处重复）。

**建议**：抽成 `services/media_access.py::touch_media_presence(media, db)`。

---

## 5. 部署 / 运维

### 🟢 P3 — `.env` 进了 git？（需确认）

**现状**：`deploy_to_linux.py` 读 `.env` 拿 `DEPLOY_PASSWORD`，`.gitignore` 需确认是否忽略 `.env`。从 git status 看没追踪，但 `deploy.bat`、`deploy_to_linux.py` 引用了它。

**建议**：确认 `.env` 在 `.gitignore`，提供 `.env.example`。

---

### 🟢 P3 — Docker frontend 用 `nginx:1.27-alpine` 但没 healthcheck

**现状**：`docker-compose.yml` 两个服务都没 healthcheck，`restart: unless-stopped` 是唯一兜底。

**建议**：加 healthcheck（curl backend `/auth/status`），便于 NPM 反代健康检查。

---

### 🟢 P3 — `nginx.conf` 把所有非静态请求 fallback 到 backend

**现状**（`nginx.conf:13`）：`try_files $uri $uri/ @backend;`。SPA 的路由（如 `/stats`）刷新会先找文件找不到，回退 backend，backend 又 mount 了 `frontend/dist`（`main.py:5126`）。链路绕一圈。

**建议**：nginx 里显式处理 SPA fallback：
```nginx
location / {
    try_files $uri $uri/ /index.html;
}
location ~ ^/(api|media|stream|audio|thumbnails|mobile|bd2|external|x|dedup|auto-sync|auth|users|folders|recommend|stats|creators|ai) {
    proxy_pass http://he-manager:8010;
}
```
（需要先确认 nginx 前端容器是否在同网络能直接访问 backend——当前 `networks: npm-network` 共享，OK。）

---

## 6. 优化路线图（建议执行顺序）

| 阶段 | 任务 | 状态 | 备注 |
|------|------|------|------|
| **第 1 周** | 补 `sentence-transformers` 依赖（P1） | **✅ 已完成** | 已添加到 requirements.txt |
| | `/media` 加分页 + selectinload 消除 N+1（P0） | **✅ 已完成** | selectinload 已上，且完成前端滚动加载 |
| | `/auto-sync` 加入 ADMIN_PREFIXES（P2 安全） | **✅ 已完成** | 已纳入 ADMIN_PREFIXES 拦截 |
| **第 2 周** | 修复重复的 `cleanup_orphaned_thumbnails` 定义（P1） | **✅ 已完成** | 移至 lifespan 启动钩子内执行 |
| | 前端路由全量懒加载（P2） | **✅ 已完成** | 已转换路由为动态 import() |
| | `/external/downloader/callback` 加 schema + token + 路径校验（P2） | **✅ 已完成** | Token校验与 realpath 防越权已上 |
| **第 3-4 周** | **拆分 main.py** 到 routers/services（P0） | ⏳ **待 Code X 完成** | 本次暂未拆分，移交给 Code X |
| | 视频缩略图改信号量（P2） | **✅ 已完成** | 已替换为 BoundedSemaphore(2) |
| | `creators.py` 加 TTL 缓存 + 合并查询（P2） | ⏳ **待完成** | 可作为后续微调 |
| **长期** | 引入 Alembic 替代手写 ALTER（P1） | 🚫 **已取消** | 经负责人确认，保持 zero-tool 约定，但已将手写 SQL 归置到 migrations.py 并改为 lifespan 启动 |
| | lifespan 替代 on_event（P3） | **✅ 已完成** | 已引入 lifespan 并在启动时运行 metadata 创建与 migrations |
| | Pydantic v2 model_config（P3） | ⏳ **待完成** | 维持现状兼容层即可，后续可逐步替换 |
| | nginx SPA fallback 优化（P3） | ⏳ **待完成** | 视部署暴露情况按需调整 |


---

## 7. 决策点（需项目负责人确认）

以下改动**改变了 AGENTS.md 记录的项目约定**，动手前请确认：

1. **引入 Alembic**：AGENTS.md 明确写了"零结构迁移惯例，对标 `sync_position` 写法"。引入 Alembic 是改变这个约定，但带来的可追溯性收益很大。**建议改为 Alembic，但需你拍板**。

2. **`/media` 加分页**：会改变 web 前端现有"一次性渲染全部"的行为。前端需要同步改 `HomeView` 为虚拟滚动 / 分页。**默认建议做**（库总会长大）。

3. **`/auto-sync` 是否真要对 admin 锁**：如果设计意图是"登录用户都能看同步状态、改代理"（个人项目单用户场景），那现状没问题；只是 `/auto-sync/proxy` PATCH 改全局代理确实敏感。

4. **是否暴露到公网**：如果只内网用，P2 的几个安全项（LOGIN_FAILURES 持久化、callback token）优先级可降；如果走 FRP 公网（docker-compose 注释暗示），建议全做。

---

## 8. 不建议改的（写明理由，防止误伤）

- **`database.py` 的 SQLite pragma**（WAL / busy_timeout=5000 / wal_autocheckpoint=200）：注释写得很清楚，是踩过"database is locked"坑后的最优解，别动。
- **`get_ranged_file_response` 手动 206 实现**：虽然能换成 FileResponse，但当前实现对 Media3 identity 的边界处理是对的，换之前必须回归播放测试。
- **`scanner.py` 的 `THUMBNAIL_LOCK`**：建议改信号量，但**不要直接删锁改无限并发**——cv2 多线程有已知竞态。
- **curl_cffi 的 `_IMPERSONATIONS` 轮换**：是绕 Cloudflare JA3 指纹的必要手段，别简化成单一 profile。
- **`manga_vector.py` 不预加载模型的设计**：懒加载是有意的（测试启动速度），别改成 import 时加载。
- **前端手写 store（非 Pinia）**：当前规模够用，迁移收益不大。

---

## 9. 总结

**做得好的**：
- 注释质量极高，关键决策都有"为什么"；
- 安全意识在线（路径穿越守卫、登录限流、forwarded-for 不信任、pbkdf2+token hash）；
- SQLite 并发配置（WAL）处理得当；
- 测试基线稳定。

**最该先做的 3 件事**：
1. **补 `sentence-transformers` 依赖**（10 分钟，修潜在崩溃）；
2. **`/media` 分页 + N+1 修复**（1 天，防库膨胀）；
3. **拆分 `main.py`**（1.5 天，长期可维护性，也能减少 hot-reload 抖动）。

其余按路线图推进。所有改动**遵循 AGENTS.md 的硬规则**：改前 `git status`、commit/stash 干净工作区、`git diff --cached` 验证、不夹带无关 hunk。
