# HE Manager Desktop 0.1.1

Mac Apple Silicon（arm64）与 Windows x64 共用 Electron/Vue 客户端。服务器只提供原始媒体和 API；mpv + Anime4K 和 Real-ESRGAN 在客户端 GPU 上运行。

## 新路线开工（2026-10-17）

按[跨平台实施方案](../docs/desktop-client-plan.md)推进，Windows 优先，保持 Mac arm64 共用实现。CP-00 已完成，当前进入 CP-01。旧版独立 mpv 播放不等于 CP-01 内嵌播放通过，旧 WinUI 原型也不再继续。阶段状态见根目录 `PLAN.md` 和 [CP-00 交付](reports/CP-00-complete.md)。

新增 `--baseline`，在临时用户目录启动实际界面，记录系统/GPU/DPI、Electron/Node、界面就绪时间、公共连接检查及资源文件 SHA-256；不读取正常客户端的账号、缓存或配置。新安装和无效配置默认原画，已有合法增强偏好保持不变。

开发采集（Node 22，先执行 `npm ci` 和 `npm run build:ui`）：

```sh
cd desktop
npm run baseline -- --baseline-server http://192.168.0.101:8011 --baseline-output /absolute/path/baseline.json
```

Windows 包直接运行：

```powershell
& '.\HE Manager.exe' --baseline --baseline-server=http://192.168.0.101:8011 --baseline-output=C:\HEManagerBuild\baseline.json
```

`--baseline-resources` 可指定另一份已安装客户端的 `resources` 目录，仅用于盘点其文件，不会加载其中的引擎。省略输出路径时保存到“文档/HE Manager Diagnostics”。采集有 60 秒上限，退出码 0 仅表示报告已写出且界面就绪；连接、资源和 CP-01 必须分别检查报告状态。资源哈希是实际文件清单，不代表已经匹配下载来源或完成新媒体链路验收。界面时间来自进程启动及 Electron ready，不是控制系统缓存后的冷启动性能。

Windows 安装包参数使用 `--名称=值`。独立 URL 后再追加开关会在 Electron 的应用入口之前被拒绝；npm 采集脚本自动规范化参数，允许普通的空格分隔写法。

本机 Node 26 会使现有 Vitest/happy-dom 测试中的 `localStorage` 不可用；开发与 CI 使用 Node 22。Electron 内置 Node 与开发用 Node 分开记录。

## 使用

1. Mac 解压后打开 HE Manager.app；Windows 解压整个目录后打开 HE Manager.exe，不要单独移动 exe。
2. 在「连接与超分」中填写 HE Manager 网页地址，例如 `http://192.168.0.101:8011`，保存后使用现有账号登录。
3. 打开本地库视频时，会出现受客户端管理的独立 mpv 窗口。应用内可暂停、跳转、全屏和切换原画／Anime4K 效率档／质量档；原生窗口也有播放控件。
4. M1 Pro 8 核 CPU、14 核 GPU、16GB 优先试效率档；RTX 5070 Laptop 可以试质量档，以掉帧统计和实际观感为准。普通真人视频建议选择原画。
5. 图片与漫画可选动漫 2× 或通用图片 4×。当前版本处理静态 JPG、PNG；其他格式保留原图。只处理当前可见的页／双页，翻页预加载仍使用原图。处理完成前继续显示原图，失败或超过输出 4000 万像素也保留原图。

体验包内含播放器、着色器、图片引擎和模型，无需安装 CUDA、Python 或 Homebrew。当前 mpv Mac 构建要求 macOS 15+。Linux 构建的 Mac 包需先在 Mac 执行 `bash scripts/sign-macos.sh "/path/HE Manager.app"` 完成本地 ad-hoc 签名，再按 `scripts/archive.py` 归档。当前交付到用户 Mac 的体验包已完成本地签名验证，但没有 Apple Developer ID 公证；Windows 未做发布者代码签名。

图片结果只存客户端用户目录，缓存约 1GB，超限淘汰旧文件。缓存键隔离服务器、账号凭证、原图内容、模型和引擎版本；命中前仍向服务器验证读取权限。更换服务器清除当前登录状态。原图和服务器媒体文件不会被覆盖。

## 0.1.1 修复

- 为应用自身页面放行 Fullscreen API，图片／漫画全屏时隐藏信息侧栏；不开放其他站点或设备权限。
- 退出时先停止播放器与图片任务，再结束应用；增加退出兜底，防止留下超分队列已关闭的旧进程。更新应用后必须完整退出并重新启动。
- 图片读取中止、超时显示中文提示并保留原图，不再暴露 Electron IPC 错误。
- `--fullscreen-selftest` 验证实际窗口进入和退出全屏；原生自检追加通用模型 4× 及缓存测试。

## 从 Linux 服务器构建

开发目录 `/opt/stacks/he-manager`。Node.js 22.12+、Python 3.12+、7-Zip。

```sh
cd frontend
npm ci
npm test
cd ../desktop
npm ci
npm test
npm run build:ui
python3 scripts/prepare-runtimes.py all
npm run package -- darwin
npm run package -- win32
```

生成 `desktop/release/HE-Manager-0.1.1-darwin-arm64.zip` 与 `HE-Manager-0.1.1-win32-x64.zip`。下载来源和 SHA-256 固定在 `runtime-lock.json`，校验失败会停止。Electron 下载由官方包的校验清单验证。依赖、模型、打包输出不提交 Git。

`.github/workflows/desktop.yml` 为两种包提供独立的构建检查和构件上传。打包成功不代表客户端 GPU 性能验收通过。

## 验证

- `npm test`：原生桥接范围、路径／URL 校验、秘密不进入播放器命令行、mpv JSON IPC、缓存权限与账号隔离、失败恢复、输出尺寸与资源上限。
- `cd ../frontend && npm test`：原有 Web 回归、图片超分前显示原图、跳页后丢弃过期结果、关闭增强恢复原图。
- Linux 无 GPU 启动检查：`xvfb-run -a node_modules/.bin/electron --no-sandbox --disable-gpu . --smoke-test`。`--no-sandbox` 只用于构建机无显示环境测试，正常安装包不禁用沙箱。
- 客户端执行 `HE Manager --native-selftest`：使用随包合成测试片验证真实 mpv 渲染通道是否含 Anime4K、切回原画、实际图片 2×／4× 推理与缓存。结果写入用户数据目录 `native-test-report.json`。不访问私人媒体，不需要登录，也不修改服务器。

## 实测记录

2026-10-17：Mac arm64 和 RTX 5070 Laptop Windows x64 的原生自检通过，包含真正的 Anime4K 渲染通道、切回原画、图片 128×128 → 256×256 推理和二次缓存命中。Mac 客户端已在实际界面连接现有服务器。详见 [验证记录](VALIDATION.md)。这不是 1080p/4K 长视频性能或主观画质验收。

## 当前边界

首版覆盖本地库视频、图片和漫画。Pawchive 独立媒体查看器暂未接入原生超分；普通视频的专用 AI 增强、内嵌原生视频渲染、字幕／音轨选项与桌面自动更新是后续迭代。Anime4K 只用于动漫增强，不会恢复已丢失的真实细节；不做所有素材实时 4K 的性能承诺。
