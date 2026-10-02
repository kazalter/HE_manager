# HE Manager

HE Manager 是一个可自托管的个人多媒体库。它索引保存在本机或服务器磁盘上的媒体文件，并通过 Web 界面统一浏览、搜索、整理和播放视频、图片/漫画与音频。媒体文件留在配置的存储目录中；媒体信息、用户、标签和播放进度等数据保存在 SQLite 数据库。

项目包含 FastAPI 后端和 Vue 3 Web 前端，支持 Windows 本地开发与 Linux Docker Compose 部署。

## 功能

- 管理视频、图片/漫画和 ASMR 音频；扫描媒体目录并生成缩略图。
- 按类型、标签、创作者和来源浏览媒体，查看个人统计信息。
- 在 Web 端播放视频和音频、阅读图片与漫画；支持手机屏幕布局。
- 通过感知哈希查找重复或相似媒体，并管理匹配结果。
- 提供基于媒体信息和用户偏好的推荐；可配置 DeepSeek，为自然语言查找和推荐提供支持。
- 按需接入 X、WNACG、ASMR 与 Pawchive 等外部来源；下载内容前由用户选择。
- 使用 SQLite 持久化资料，并在扫描或写入外置存储时检查挂载状态，减少磁盘未挂载造成的误操作。

## 技术组成

| 部分 | 技术 |
| --- | --- |
| 后端 API | Python 3.12、FastAPI、SQLAlchemy、Uvicorn |
| Web 前端 | Vue 3、TypeScript、Vite、Tailwind CSS |
| 数据库 | SQLite（WAL） |
| 推荐与检索 | Sentence Transformers 向量检索；可选 DeepSeek API |
| 部署 | Docker Compose、Nginx |

## Windows 本地开发

需要 PowerShell 7、Python 3.12 和 Node.js 22。以下命令在仓库根目录的 PowerShell 中执行：

```powershell
# 安装后端依赖
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt

# 安装前端依赖
cd ..\frontend
npm ci

# 启动前后端开发服务；脚本会打开浏览器
cd ..
.\he.ps1
```

首次打开登录页时，按提示创建管理员账号。`he.ps1` 启动 Web 前端和后端；如只需要局域网 API 服务，可运行 `he-server.ps1`。DeepSeek 是可选项，可在应用设置中配置。

常用检查命令：

```powershell
cd backend
python -m pytest

cd ..\frontend
npm run test
npm run build
```

## Linux Docker Compose 部署

项目根目录的 `docker-compose.yml` 启动后端 API 和 Nginx 前端。需要 Docker Engine、Docker Compose 插件、Node.js 22，以及可用的媒体存储目录。

1. 确保宿主机媒体盘已挂载。Compose 默认将宿主机 `/mnt/hdd` 映射到容器内相同路径；如果要更换位置，请一并调整 Compose 映射，并确保数据库中记录的媒体路径在容器内仍然有效。
2. 在项目根目录创建 `.env`，将前端绑定地址设为这台服务器的局域网地址：

   ```dotenv
   HE_FRONTEND_BIND_IP=<服务器的局域网 IP>
   HE_FRONTEND_PORT=8011
   ```

3. 构建前端和后端并启动服务：

   ```bash
   cd frontend
   npm ci
   npm run build
   cd ..

   docker compose build
   docker compose up -d
   docker compose ps
   ```

Web 界面地址为 `http://<服务器 IP>:8011`，后端 API 端口为 `8010`，健康检查地址为 `http://<服务器 IP>:8010/healthz`。首次打开 Web 界面时创建管理员账号。

Compose 将 `./data` 挂载到容器的 `/data`，用于保存 SQLite 数据库、DeepSeek 配置和模型缓存；缩略图与封面缓存分别保存在 `./volumes/thumbnails`、`./volumes/covers`。升级镜像或重建容器时保留这些数据目录及媒体盘。

### 可选配置

- 在应用设置中配置 DeepSeek API Key、模型和服务地址；Linux Compose 会将配置保存在 `./data/deepseek.json`。
- Pawchive 默认关闭。需要启用时，在项目根目录 `.env` 中配置下载目录和挂载哨兵，并按运维文档确认磁盘及网络设置：

  ```dotenv
  HE_PAWCHIVE_ENABLED=1
  HE_PAWCHIVE_DOWNLOAD_ROOT=/mnt/hdd/hhh
  HE_PAWCHIVE_STORAGE_SENTINEL=.mounted
  ```

  更多说明见 [Pawchive 运维文档](docs/pawchive-operations.md)。

## 数据与备份

SQLite 数据库是媒体索引、用户、收藏、标签和播放记录的主要存储。Linux Compose 默认数据库路径为 `./data/library.db`；媒体原文件保存在配置的媒体目录中。备份时同时考虑数据库和媒体盘。`scripts/backup_db.py` 提供 SQLite 在线备份与备份新鲜度检查；例如：

```bash
python scripts/backup_db.py --db-path /path/to/data/library.db --backup
python scripts/backup_db.py --db-path /path/to/data/library.db --check-freshness --max-age-hours 24
```

执行脚本的 Python 环境需已安装 `backend/requirements.txt` 中的依赖。查看完整参数：`python scripts/backup_db.py --help`。

## 目录结构

```text
backend/                 FastAPI API、数据库、扫描器与推荐服务
  app/routers/           API 路由
  app/scanners/          视频、图片/漫画和音频扫描器
  app/services/          存储保护、备份、媒体访问等服务
  tests/                 后端测试
frontend/                Vue 3 Web 前端
docs/                    Pawchive API 与运维文档
scripts/backup_db.py     SQLite 备份与新鲜度检查
Dockerfile               后端镜像
docker-compose.yml        Linux 服务编排
he.ps1                   Windows 前后端开发启动脚本
he-server.ps1             Windows 后端服务启动脚本
```

## 相关文档

- [Pawchive 运维文档](docs/pawchive-operations.md)
- [Pawchive API 契约](docs/pawchive-api-contract.md)
- [功能状态与后续计划](FEATURE_PLANS.md) · [当前计划](PLAN.md)
