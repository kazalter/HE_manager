# HE Manager Frontend

Vue 3 + TypeScript + Vite 前端。

## 本地开发

```powershell
npm install
npm run dev
npm run build
```

本地开发通常由根目录 `he.ps1` 同时启动后端和 Vite。

## 部署说明

- `frontend/dist` 由 Vite build 生成。
- `frontend/nginx.conf` 是前端容器内部 nginx 配置：服务静态文件，把 API/媒体路径转发到 Compose 服务 `backend:8010`，并让 Vue history 路由回落到 `/index.html`。
- 外层 Nginx Proxy Manager 配置不在本仓库维护。
