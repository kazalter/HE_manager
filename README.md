# HE Manager

个人自用媒体库管理器，面向视频、漫画/图片文件夹、ASMR 音频和外部收藏同步。项目包含 FastAPI 后端、Vue 3 Web 前端、Android 客户端和 Linux Docker 部署配置。

## 运行约定

本项目维护 **一个代码库、一条 `main`**，不拆 Win/Linux 两套代码版本。

- **Windows 开发/测试画像**：PowerShell 7、`he.ps1`、`he-server.ps1`、本机 Python、Vite、Android 构建脚本。
- **Linux 部署画像**：`docker-compose.yml`、`frontend/nginx.conf`、`deploy_to_linux.py`、Nginx Proxy Manager 外层反代、服务器数据卷。
- 平台差异应放在配置、脚本和少量兼容层里；后端/前端业务代码要保持跨平台可测。

更多协作规则见 `AGENTS.md`。

## 功能

- 媒体扫描、封面生成、搜索、标签、收藏、播放进度。
- Web 端媒体库、统计页、去重页、创作者聚合页、外部同步页。
- Android 客户端局域网浏览、视频播放、ASMR 播放。
- WNACG、ASMR、X/Twitter 归档收藏同步与下载。
- SQLite 本地数据库，启动脚本自动备份。

## 目录

```text
backend/            FastAPI 后端、模型、扫描器、导入器、测试
frontend/           Vue 3 + TypeScript + Vite 前端
frontend/nginx.conf Linux 前端容器内部 nginx 配置
scripts/            辅助脚本
he.ps1              Windows Web 全栈开发启动脚本
he-server.ps1       Windows 仅后端 LAN 启动脚本
docker-compose.yml  Linux 部署编排
deploy_to_linux.py  构建、上传并重启 Linux Docker 服务
```

## 常用命令

```powershell
# Windows 本地开发
.\he.ps1
.\he-server.ps1

# 后端测试
cd backend
python -m pytest tests -q

# 前端构建
cd frontend
npm install
npm run build

# Android
.\android_preview.ps1
.\android_release.ps1
```

后端测试优先使用本机 Python 3.12：

```text
C:\Users\25768\AppData\Local\Programs\Python\Python312\python.exe
```

## Linux 部署

默认服务器目录：

```text
/opt/stacks/he-manager/
```

部署脚本：

```powershell
python .\deploy_to_linux.py
```

部署脚本会构建前端、上传 `frontend/dist`、后端源码、`docker-compose.yml`、`frontend/nginx.conf` 和 `backend/requirements.txt`，然后执行 `docker compose up -d --build`。

注意区分：

- `frontend/nginx.conf`：本仓库维护，属于 HE Manager 前端容器内部配置。
- Nginx Proxy Manager：Linux 外层反代入口，不在本仓库维护。

## 数据与密钥

不要提交本地数据和密钥。常见本地文件包括：

- `.env`
- `backend/app/library.db`、`*.db-wal`、`*.db-shm`
- `backend/backups/`
- `backend/instance/`
- `backend/x_archive_uploads/`
- `covers/`
- `logs/`
- Android/Gradle 构建产物

## 安全边界

HE Manager 默认面向本机、可信局域网和个人自托管场景。

- API 使用 bearer token，部分媒体 URL 会为播放器把 token 放入 query string。
- 外部服务 cookie/token 可能保存在本地数据库或浏览器 `localStorage`。
- 公网访问必须使用 HTTPS、收紧 CORS、保护数据库和 `.env`。
- Android 通过 Sakura/NPM 等外层入口访问时，传输层配置属于部署画像，不应拆出另一套代码版本。
