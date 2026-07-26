# HE Manager (多媒体智能推荐与检索系统)

一个本地优先、面向多终端的个人自用多媒体库管理器。支持视频播放、漫画/图片阅读、ASMR 音频播放以及外部收藏（X/Twitter、WNACG、ASMR）的同步与下载。系统集成大模型意图解析与双路召回（向量相似度 + BM25-lite）推荐引擎，打造高度智能的媒体治理体验。

本项目遵循 **“一套代码，跨平台适配”** 的工程原则，完美兼容 Windows 开发调试与 Linux Docker 生产部署。

---

## 功能特性

- **多模态媒体管理**：支持视频流畅播放、漫画分页读取、ASMR 歌词解析与背景播放、外部收藏数据去重与维护。
- **意图结构化解析**：集成 DeepSeek API，编写定制的 System Prompt 及格式约束，将用户模糊的自然语言偏好精准解析为作者、题材、风格等结构化过滤参数（Pydantic Schema）。
- **双路混合推荐**：自主手写设计向量相似度与 BM25-lite 关键字检索的两路召回推荐算法，围绕用户 Profile 与阅读进度构建定制化的多维特征排序。
- **流式传输与同步**：开发高效的音视频 Range 流式分块传输接口，支持 Web 端与 Android 客户端的实时播放与阅读进度多端同步。
- **自动化运维支持**：支持定时媒体文件全量扫描、元数据增量更新、封面图智能剪裁生成，并提供 SQLite 数据库启动自动备份与崩溃安全机制（WAL）。

---

## 技术栈

| 层次 | 技术选型 |
|---|---|
| **后端** | Python + FastAPI + SQLAlchemy + Uvicorn |
| **前端** | Vue 3 + TypeScript + Vite + Tailwind CSS |
| **客户端** | Android (Kotlin / Java + Jetpack Compose + Media3) |
| **数据库** | SQLite (WAL 模式，支持高并发读写) |
| **推荐与 AI** | DeepSeek API (兼容 OpenAI 协议) + 向量/BM25 检索 |
| **运维与部署**| Docker + docker-compose + deploy_to_linux.py (自动化打包发布) |

---

## 目录结构

```text
HE_manager/
├─ backend/             后端项目
│  ├─ app/              业务逻辑（数据库模型、扫描器、导入器）
│  │  ├─ api/           FastAPI 路由与接口
│  │  ├─ models/        SQLAlchemy 数据库实体
│  │  └─ services/      推荐算法与媒体处理服务
│  └─ tests/            pytest 单元与集成测试用例
├─ frontend/            Vue 3 前端项目
│  ├─ src/              组件与前端路由
│  └─ nginx.conf        Linux 前端容器内部 Nginx 配置
├─ scripts/             运维与管理辅助脚本
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
```

---

## 生产部署 (Linux Docker 环境)

项目默认生产部署路径为 `/opt/stacks/he-manager/`。

我们提供了自动化部署脚本，可一键完成：前端构建、代码打包、传输上传与远程容器重启。

```powershell
# 在 Windows 开发机下直接运行部署脚本（需提前配置 deploy_to_linux.py 中的 SSH 信息）
python .\deploy_to_linux.py
```

### 安全与数据防护
- 生产环境建议通过 Nginx Proxy Manager 等反代工具启用 HTTPS。
- Docker 将 SQLite、外部来源凭据、DeepSeek 配置和 HuggingFace 模型缓存持久化在 `./data`；重建后端容器不会清空这些配置。
- X/ASMR Cookie 与 DeepSeek API Key 是服务运行所需的可恢复凭据，保存在本机数据卷中且不会由状态 API 明文返回；应将 `data` 目录视为敏感数据，保持 owner-only 权限并纳入可信备份。
- `.env`、数据库、模型缓存以及 `covers/` 封面目录均被 Git 忽略，请定期检查 `backups/` 中的 SQLite 热备份。

