# HE Manager (多媒体智能推荐与检索系统)

一个本地优先、面向多终端的个人自用多媒体库管理器。支持视频播放、漫画/图片阅读、ASMR 音频播放以及外部收藏（X/Twitter、WNACG、ASMR）的同步与下载。系统集成大模型意图解析与双路召回（向量相似度 + BM25-lite）推荐引擎，打造高度智能的媒体治理体验。

本项目遵循 **“一套代码，跨平台适配”** 的工程原则，完美兼容 Windows 开发调试与 Linux Docker 生产部署。

---

## 功能特性

- **多模态媒体管理**：支持视频流畅播放、漫画分页读取、ASMR 歌词解析与背景播放、外部收藏数据去重与维护。
- **意图结构化解析**：集成 DeepSeek API，编写定制的 System Prompt 及格式约束，将用户模糊的自然语言偏好精准解析为作者、题材、风格等结构化过滤参数（Pydantic Schema）。
- **双路混合推荐**：自主手写设计向量相似度与 BM25-lite 关键字检索的两路召回推荐算法，围绕用户 Profile 与阅读进度构建定制化的多维特征排序。
- **流式传输与同步**：开发高效的音视频 Range 流式分块传输接口，支持 Web 端与 Android 客户端的实时播放与阅读进度多端同步。
- **存储安全与 Sentinel 保护**：内置 `storage_guard` 存储哨兵，防止外置 HDD 掉盘或未挂载时误写系统根分区或误将已有媒体批量标记为失效。
- **自动化运维与监控**：支持定时媒体扫描、元数据增量更新、封面图智能剪裁生成；内置 SQLite 在线热备份、备份新鲜度监控与容器分级健康检查。

---

## 技术栈

| 层次 | 技术选型 |
|---|---|
| **后端** | Python 3.12 + FastAPI + SQLAlchemy + Uvicorn |
| **前端** | Vue 3 + TypeScript + Vite + Tailwind CSS + Vitest |
| **客户端** | Android (Kotlin / Java + Jetpack Compose + Media3) |
| **数据库** | SQLite (WAL 模式，自动 Checkpoint 优化) |
| **推荐与 AI** | DeepSeek API (兼容 OpenAI 协议) + CPU-only Sentence-Transformers / 向量检索 |
| **运维与部署**| Docker + docker-compose + deploy_to_linux.py (自动化打包发布) |

---

## 目录结构

```text
HE_manager/
├─ backend/             后端项目
│  ├─ app/              业务逻辑（API 路由、数据库模型、扫描器、导入器、服务）
│  │  ├─ routers/       FastAPI 模块化路由
│  │  ├─ models.py      SQLAlchemy 数据库实体
│  │  ├─ scanners/      多媒体扫描与缩略图生成器
│  │  └─ services/      推荐算法、存储守护、在线备份与生命周期管理
│  └─ tests/            pytest 单元与集成测试用例
├─ frontend/            Vue 3 前端项目
│  ├─ src/              组件与前端路由
│  └─ nginx.conf        Linux 前端容器内部 Nginx 配置
├─ scripts/             运维与管理辅助脚本 (备份、新鲜度检测)
├─ he.ps1               Windows 全栈开发一键启动脚本
├─ he-server.ps1        Windows 仅后端（局域网服务）启动脚本
├─ docker-compose.yml   Linux 生产环境部署编排
└─ deploy_to_linux.py   构建、上传并重启 Linux Docker 服务的部署脚本
```

---

## 快速开始 (Windows 开发环境)

### 1. 初始化后端
进入后端目录，安装相关依赖并配置环境变量：
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
copy .env.example .env
```
修改 `.env` 配置文件，填入您的 `DEEPSEEK_API_KEY` 及媒体库本地路径。

### 2. 常用开发命令
本项目提供了一键式脚本，方便本地调试：
```powershell
# Windows 全栈（前端 + 后端）一键启动
.\he.ps1

# Windows 仅启动后端（面向局域网/Android App 联调）
.\he-server.ps1

# 运行后端单元测试
cd backend
python -m pytest tests -q

# 运行前端测试与构建
cd frontend
npm run test
npm run build
```

---

## 生产部署与运维指南 (Linux Docker 环境)

项目默认生产部署路径为 `/opt/stacks/he-manager/`。

### 1. 镜像构建与瘦身 (CPU-only PyTorch)
针对 N100 等无独立 GPU 的小型主机/服务器，后端 Dockerfile 采用官方 CPU-only PyTorch Wheel 构建分层：
```dockerfile
ARG TORCH_VERSION=2.9.1+cpu
RUN pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        "torch==${TORCH_VERSION}" \
    && pip install --no-cache-dir -r requirements.txt
```
> **优化效果**：剥离无用的 CUDA / Triton 运行时，后端 Docker 镜像体积由 **8.94 GB 精简至 2.47 GB**，内存占用与构建速度大幅提升。

### 2. 持久化卷规划与权限
在 `docker-compose.yml` 中规划了严格的持久化目录划分：
- `./data` -> `/data`：持久化保存核心业务 SQLite 数据库 `library.db`（及 WAL/SHM）、DeepSeek 配置文件 `deepseek.json`、外部配置与 HuggingFace 离线模型缓存。
- `./volumes/thumbnails` -> `/srv/.thumbnails`：缓存视频/漫画/音频缩略图。
- `./volumes/covers` -> `/covers`：外部数据源下载的封面缓存。
- `/mnt/hdd` -> `/mnt/hdd`：外置媒体硬盘挂载点（容器内外路径一致，数据库无需二次重写路径）。

**权限防护**：系统在启动时自动执行 `secure_data_permissions()`，对敏感目录设置 `0700`、数据库及凭据文件设置 `0600` 属主独占权限，保护 SQLite 与 API 凭据安全。

### 3. 外置存储挂载保护 (Storage Guard & Sentinel)
为防止外置 HDD 离线/未挂载时，下载或全量扫描将数据误写进 Linux 系统根盘（或导致扫描器误将媒体标记为 `is_missing`），系统内置存储守卫：
- **挂载点检查**：自动识别 `/mnt/*` 与 `/media/*` 是否为真实挂载点（`os.path.ismount`）。
- **哨兵文件机制**：在外置硬盘根目录下创建哨兵文件：
  ```bash
  touch /mnt/hdd/.mounted
  ```
- **环境变量控制**：可通过环境变量 `HE_STORAGE_SENTINEL=.mounted` 或 `HE_REQUIRE_STORAGE_MOUNT=1` 启用强制保护。若挂载点异常，系统将直接拦截写入并拒绝执行误标空库的扫描。

---

## 数据库备份、恢复与运维监控

### 1. SQLite 在线热备份 (Zero-Downtime Hot Backup)
系统采用 SQLite 原生在线备份协议（`sqlite3.backup` API），支持在高并发读写及 WAL 模式下进行无损、事务一致的热备份。

执行一次手动在线备份：
```bash
# 宿主机直接运行（或容器内执行）
python scripts/backup_db.py --backup

# 或通过 Docker 执行
docker exec he-manager python /srv/scripts/backup_db.py --backup
```
备份文件将以时间戳命名保存至 `/data/backups/library-YYYYMMDD-HHMMSS.db`，默认自动轮转保留最新的 7 份快照。

### 2. 备份新鲜度监控与告警 (Freshness Check)
为防止定时备份静默失败，提供新鲜度检测机制：
```bash
# 检查备份是否在过去 24 小时内更新（正常退出码 0，过期/缺失退出码 1）
docker exec he-manager python /srv/scripts/backup_db.py --check-freshness --max-age-hours 24
```
**Crontab 定时备份与监控示例**：
```cron
# 每天凌晨 3 点执行备份并记录日志
0 3 * * * docker exec he-manager python /srv/scripts/backup_db.py --backup >> /var/log/he_backup.log 2>&1

# 每天早晨 8 点检查备份新鲜度，过期则触发运维告警
0 8 * * * docker exec he-manager python /srv/scripts/backup_db.py --check-freshness --max-age-hours 26 || echo "HE Manager 数据库备份过期！" | mail -s "HE Manager Alert" admin@example.com
```

### 3. 数据库还原流程
若发生数据异常需回滚到历史快照：
1. 停止后端容器：
   ```bash
   docker compose stop backend
   ```
2. 使用备份快照替换数据目录中的数据库文件：
   ```bash
   cp data/backups/library-20260830-155237.db data/library.db
   rm -f data/library.db-wal data/library.db-shm
   ```
3. 重启服务：
   ```bash
   docker compose up -d backend
   ```

### 4. 容器健康检查与运维 API
- **容器健康状态检查**：
  ```bash
  docker compose ps
  # 或查看详细健康诊断：
  docker inspect --format '{{json .State.Health}}' he-manager
  ```
- **系统健康接口**：
  - `GET /healthz`：基础存活检查与 SQLite 连通性测试（`SELECT 1`）。
  - `GET /system/backup/status`：管理员接口，返回现有备份列表、最新备份时间与新鲜度指标。
  - `POST /system/backup/run`：管理员接口，在线触发一次热备份。
  - `GET /system/storage/status`：管理员接口，返回当前存储守卫与哨兵配置状态。
