# HE Manager 跨平台桌面客户端 (v1.0.1)

HE Manager 跨平台桌面客户端，基于 **Vue 3 + TypeScript + Vite + Tailwind + Electron** 架构构建，专为 macOS Apple Silicon (arm64) 与 Windows 11 (x64) 双平台设计。

服务端（FastAPI / SQLite）仅提供基础 API 和原始媒体流；视频渲染（libmpv）、Anime4K 着色器与 Real-ESRGAN 图片超分均在客户端本地 GPU 上运行，不消耗服务端算力，不修改服务端原媒体。

---

## 核心特性与能力

### 1. 内嵌媒体播放器 (libmpv Embedded)
- **真机内嵌渲染**：通过原生 addon + 平台共享纹理（macOS `IOSurface`、Windows `D3D11 Texture / NT HANDLE`）直接将 libmpv 视频帧注入 DOM 画布。
- **DOM 控件与全屏覆盖**：Vue 控制条、菜单、弹层无缝覆盖于视频之上，支持同会话进入/退出全屏（保持进度、暂停状态、音轨、字幕与倍速，无需重新加载）。
- **完整播放控制**：
  - 播放 / 暂停、细粒度进度跳转；
  - 前进 10 秒（`RotateCw`）、后退 10 秒（`RotateCcw`）；
  - 上一项 / 下一项媒体快速切换；
  - 音轨与字幕通道切换、0.5x～2.0x 倍速调节；
  - 音量调节与静音控制。
- **Web 风格控制层**：闲置自动隐藏，鼠标移动唤回，暂停/调节时保持可见；提供四种播放模式、直接音量/倍速、画面比例与 PNG 截图保存。
- **Anime4K 着色器实时增强**：原画（off）、效率（efficiency）、质量（quality）三档切换。
- **掉帧率核验**：典型 1080p / 4K 播放维持 0 丢帧，资源占用可控。

### 2. 全局 PlayerSession 与音视频互斥
- **统一会话调度**：严格保证全应用同一时刻最多只有一个活动的音视频播放会话。
- **音视频互斥切换**：
  - 播放视频时，自动通知并停止活动音频，安全释放旧会话；
  - 开启音频作品时，自动关闭视频核心并彻底释放共享纹理与原生租约。
- **常驻音频播放器**：
  - 支持多曲目解析（`tracks` 列表）、音轨切换、上一曲/下一曲、顺序/循环/随机模式；
  - 可最小化为全局悬浮迷你播放条（`GlobalAudioPlayer`），在浏览媒体库时后台持续播放；
  - 桌面状态隔离：恢复进度按 `serverKey` + `userId` + `mediaId` 独立隔离。

### 3. 漫画阅读器与独立图片查看 (MangaReader)
- **三种阅读模式**：
  - **单页模式（Single Page）**：单页居中适应、滚轮切页、键盘快捷键（`← / →`、`+ / -`、`0`）。
  - **双页跨页模式（Double Page）**：双页并列展示、日漫从右往左翻页（RTL）与从左往右（LTR）一键切换。
  - **连续卷轴模式（Webtoon / 条漫）**：垂直滚动平滑阅读、视口锚定与翻页同步。
- **缩放与平移**：Ctrl + 滚轮缩放、双击适应屏幕、鼠标左键拖拽平移。
- **底部预览长条（Thumbnail Strip）**：支持拖拽快速导航与悬浮缩略图大图预览。
- **独立图片（image 类型）**：与漫画共享完整阅读器交互，支持列表批量加载。

### 4. 客户端 Real-ESRGAN 图片超分
- **双模超分**：
  - 动漫 2×：采用 `realesr-animevideov3`（scale 2）；
  - 图片 4×：采用 `realesrgan-x4plus`（scale 4）。
- **原生 Vulkan/Metal 加速**：在 Apple Silicon (Metal) 与 Windows (NVIDIA/AMD/Intel Vulkan) 上直接调用客户端 GPU 进行推理。
- **并发与资源安全**：
  - 推理任务串行化（并发上限为 1），有界在途队列；
  - 单张输出像素限制在 4000 万像素以内，动态图（acTL）与未知格式安全保留原图；
  - 打开视频时自动中止在途推理任务（`cancelPending`），视频播放中暂停图片超分。
- **磁盘缓存治理**：
  - 本地缓存位于用户目录 `image-cache`，严格基于服务器、账号、原图哈希与模型参数隔离；
  - 自动执行 LRU 清理，缓存上限 1 GiB。

### 5. 双平台收敛与系统集成 (CP-06)
- **原生菜单规范**：
  - macOS 端提供标准 App、编辑、视图（含全屏、缩放、调试）、窗口（前置、最小化）菜单；
  - Windows 端提供文件（退出）、编辑、视图（F11 全屏、重置缩放）、窗口菜单。
- **窗口与多屏弹性**：
  - 严格保持 1024×640 最小内容区域，跨 DPI / 标题栏边框动态自适应；
  - 监听屏幕断开与缩放事件，断开外接显示器自动校准回主屏工作区，防止窗口移出可视区域。
- **层级化 Esc 与 F11 快捷键契约**：
  - `Esc`：优先关闭最上层模态弹框 → 退出当前窗口全屏 → 关闭媒体查看器返回媒体库；
  - `F11`：全局全屏切换，支持视频与漫画阅读无缝进入/退出沉浸模式。

---

## 快捷键说明

| 功能 | 快捷键 | 适用场景 |
| --- | --- | --- |
| 播放 / 暂停 | `空格键` / `K` | 视频播放 |
| 退出全屏 / 关闭查看器 / 关闭弹层 | `Esc` | 全局（层级：优先关闭弹层，次之退出全屏，再次关闭查看器） |
| 全屏切换 | `F11` (Win) / `Ctrl+Cmd+F` (Mac) | 视频、漫画阅读、全应用 |
| 快进 10 秒 / 下一页 | `→` (方向右键) | 视频 / 漫画 |
| 快退 10 秒 / 上一页 | `←` (方向左键) | 视频 / 漫画 |
| 静音切换 / 音量 | M / ↑、↓ | 视频画布聚焦时 |
| 视频全屏切换 | F | 视频画布聚焦时 |
| 放大画面 | `+` / `Ctrl + 滚轮向上` | 漫画阅读器 / 图片查看 |
| 缩小画面 | `-` / `Ctrl + 滚轮向下` | 漫画阅读器 / 图片查看 |
| 重置缩放 / 适应屏幕 | `0` / 双击画面 | 漫画阅读器 / 图片查看 |

---

## 构建与打包

### 环境要求
- Node.js 22.x
- Python 3.10+
- macOS (Xcode Command Line Tools) 或 Windows 11 (MSVC / C++ 生成工具)

### 1. 构建前端静态资源
```sh
cd frontend
npm ci
npm test
npm run build
```

### 2. 构建桌面端 UI
```sh
cd ../desktop
npm ci
npm test
npm run build:ui
```

### 3. 生成安装分发包
```sh
# 打包 macOS Apple Silicon (arm64)
npm run package -- darwin
bash scripts/sign-macos.sh "release/HE Manager-darwin-arm64/HE Manager.app"
python3 scripts/archive.py "release/HE Manager-darwin-arm64" "release/HE-Manager-1.0.1-darwin-arm64.zip" darwin

# 打包 Windows (x64)
npm run package -- win32
```

产物输出于 `desktop/release/`：
- `HE-Manager-1.0.1-darwin-arm64.zip`
- `HE-Manager-1.0.1-win32-x64.zip`

---

## 阶段验收报告索引

- CP-00 基线与范围：[`reports/CP-00-complete.md`](reports/CP-00-complete.md)
- CP-01 双平台媒体原型：[`reports/CP-01-complete.md`](reports/CP-01-complete.md)
- CP-02 视觉与应用基础：[`reports/CP-02-complete.md`](reports/CP-02-complete.md)
- CP-03 媒体库与连接：[`reports/CP-03-complete.md`](reports/CP-03-complete.md)
- CP-04 视频与音频：[`reports/CP-04-complete.md`](reports/CP-04-complete.md)
- CP-05 阅读与超分：[`reports/CP-05-complete.md`](reports/CP-05-complete.md)
- CP-06～07 平台收敛与最终交付：[`reports/CP-06-07-complete.md`](reports/CP-06-07-complete.md)


- v1.0.1 播放器 UI 对齐：[验收记录](reports/player-ui-1.0.1.md)
