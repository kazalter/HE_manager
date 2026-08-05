# AGENTS.md - HE Manager

个人自用媒体库：FastAPI 后端、Vue 3 Web 前端、Android 客户端。当前优化任务统一以 `PLAN.md` 为准；功能现状见 `FEATURE_PLANS.md`，历史结构审查见 `CODE_REVIEW_PLAN.md`。

## 核心原则

- **一个代码库，一条 `main`。不要拆 Win/Linux 两套代码或长期分支。**
- 代码必须跨平台可运行：Windows 本地开发和测试不能被 Linux-only 依赖打断；Linux 部署差异放在配置、脚本和 Docker 文件里。
- 运行画像分开维护：
  - **Windows 开发/测试画像**：PowerShell 7、`he.ps1`、`he-server.ps1`、本机 Python、Vite、Android 构建脚本。
  - **Linux 部署画像**：`docker-compose.yml`、`frontend/nginx.conf`、`deploy_to_linux.py`、NPM 外层反代、服务器数据卷。
- 修改后端或网页前端时，若用户没特别说明，默认最终目标是 Linux 服务器 `/opt/stacks/he-manager/` 的 Docker 化服务；先本地改和验证，再按需部署。

## Git 硬规则

### 防丢改动

在执行 `git reset --hard`、`git checkout -- <path>`、脏工作区切分支、`git stash drop`、`git clean -fd*`、删未合并分支、强制移除 worktree 前：

1. 先跑 `git status`。
2. 如有 `M` 或源码类 `??`，先 commit；用户不想 commit 时至少 `git stash push -u -m "preflight"` 并记录 stash。
3. 工作区被保护好后再做破坏性操作。

### 防夹带无关改动

在 `git add` / `git commit` 前：

1. 先跑 `git status`，确认哪些文件是本轮已有改动。
2. 目标文件若来之前已是 `M`，不要直接整文件 `git add`；先把已有改动 commit/stash，或用 patch 只 stage 自己的 hunk。
3. commit 前必须看 `git diff --cached`。
4. 会话结束前保持工作区干净：改动要么 commit，要么 stash，要么明确忽略。

这些规则来自两次事故：一次 `reset --hard` 覆盖了未提交 ASMR/audio 代码；一次 `git add backend/app/main.py` 把无关 hunk 混进提交。

## 常用命令

Windows 开发优先用 PowerShell 7。

```powershell
.\he.ps1                 # Web 全栈开发：后端 reload + Vite + 浏览器
.\he-server.ps1          # 仅后端 LAN 服务，给手机/Android 用
cd backend; python -m pytest tests -q
cd frontend; npm run build
.\android_preview.ps1
.\android_release.ps1
```

后端测试解释器优先用：

```text
C:\Users\25768\AppData\Local\Programs\Python\Python312\python.exe
```

`D:\Hermes\venv` 有 pytest 但缺后端依赖，别用。

## 部署边界

- Linux 服务器：`192.168.50.1`。
- 远端目录：`/opt/stacks/he-manager/`。
- 前端容器内部 nginx 配置：`frontend/nginx.conf`。
- Nginx Proxy Manager 是外层入口，不在本仓库直接维护。
- `deploy_to_linux.py` 会构建前端、上传 `frontend/dist`、后端源码、`docker-compose.yml`、`frontend/nginx.conf`、后端 requirements，并执行 `docker compose up -d --build`。

## 改动边界

- `/mobile/*` 是手机专用命名空间，可独立优化；Web 走 `/media`、`/stream`、`/audio`，不要混改。
- Android 主列表是 `LibraryScreenV2`；老 `LibraryScreen` 基本是死代码。
- Android 播放器/漫画页改动风险高，除非任务明确，不碰 `MangaActivity` 和 `player/PlayerActivity`。
- 结构迁移继续用幂等 `ALTER TABLE` + `migrations.py`，不引入 Alembic，除非用户重新拍板。

## 已知坑

- Windows 本地测试不能依赖 Linux-only 模块；需要平台适配，例如文件锁在 Linux 用 `fcntl`，Windows 用 `msvcrt`。
- watchfiles 在含空格路径上热重载容易抖；必要时退出脚本，确认 8010 无僵尸 uvicorn，再重启。
- Kotlin/KDoc 里不要写会形成嵌套注释的 `/audio/*`。
- 前端路由组件必须单根；App.vue transition 遇到 dev 注释 vnode 可能导致空白页。
- gzip 中间件只压 JSON，故意放行流式/206，保护 Web `<video>` Range 和 Media3 identity。
