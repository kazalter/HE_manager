# HE Manager Windows 原生客户端

当前为 WN-01 可运行的内嵌播放原型；阶段验收状态见 [实测记录](reports/WN-01-2026-10-17.md)。主计划仍是仓库根 `PLAN.md`，完整范围见 `docs/windows-native-client-plan.md`。

本目录和 Linux `/opt/stacks/he-manager` 的现有业务代码共用同一仓库、同一 main。Windows 的 `C:\HEManagerBuild\windows-native` 是构建工作副本。此原型只播放本地测试片／用户选择的本地视频；账号、服务器媒体流和媒体库在后续阶段接入。

## 运行

打开构建目录 `.artifacts\x64\HEManager.Windows.exe`，或 Windows 桌面的「HE Manager 原生播放原型」快捷方式。程序默认播放既有 8 秒合成测试片，支持打开本地视频、播放／暂停、进度拖动、音量和 Anime4K 三档。F11 进入／退出全屏，Esc 退出全屏。控制条使用视频上方的原生 XAML 控件，视频由本进程 libmpv 渲染至 SwapChainPanel。

这是开发原型，尚未连接媒体库，也不是 WN-07 的正式分发包。保留整个输出目录一起运行。开发日志位于 `%LOCALAPPDATA%\HEManager\WN01\player.log`，每次启动覆盖。首次切换 Anime4K 需要编译着色器，可能短暂停顿；磁盘缓存位于 `%LOCALAPPDATA%\HEManager\shader-cache`，热缓存复测无渲染等待告警。当前尚未连接服务器。

## 重建

2026-10-17 真机构建环境：Windows 11 x64、.NET SDK 10.0.402、Windows App SDK 2.5.1、MSVC 14.44.35207、Windows SDK 10.0.26100.0。依赖来源与摘要见 `runtime-lock/dependencies.json`，NuGet 闭包见 `HEManager.Windows/packages.lock.json`。无浮动包版本。

工具在 `C:\HEManagerBuild\toolchain` 隔离安装，未加入用户／系统 PATH。Build Tools 含 VCTools 和 Windows SDK。首次准备时从锁文件 URL 下载对应 .NET ZIP 和 libmpv 开发包，并校验摘要；将 .NET ZIP 解压到 `toolchain\dotnet`，使用微软 Build Tools 准备对应 MSVC/SDK。VS bootstrapper 下载链接与哈希仅用于记录本次安装；其工作负载在线清单可能变化，重建时仍以实际 MSVC/SDK 版本为准。

在完整仓库的 Windows 工作副本中执行：

```powershell
.\windows-native\scripts\Prepare-Runtime.ps1 -Archive C:\HEManagerBuild\toolchain\mpv-dev.7z
.\windows-native\scripts\Build.ps1 -Locked
.\windows-native\scripts\Test-Smoke.ps1
```

`Prepare-Runtime` 校验 libmpv 归档／DLL，并从同一仓库 `desktop/resources` 复制原有测试片、着色器和许可，资源不重复入库。`Build` 检查 DLL、头文件和媒体资源哈希；使用 MSVC 构建薄桥，再通过锁定 NuGet 还原和 .NET 构建 WinUI。原生桥静态链接 C++ 运行时。首次修改包版本后需不带 `-Locked` 生成并审查新的锁文件，正常重建保持 `-Locked`。

`Test-Smoke` 在当前已登录 Windows 用户的交互会话中临时创建一次性测试任务，结束即删除。需要该用户已登录桌面；不在服务会话中假装完成 GUI 验收。测试期间自动开关超分、全屏20次并重载测试片，约30～60秒，超时上限180秒。它检查 GPU 纹理回读、渲染帧、实际硬解与 Anime4K 通道、会话和退出；不代替人工输入、DPI、多屏和长时间稳定性验收。

## 生命周期与边界

- `HEManager.Media` 封装进程内 libmpv C API、UTF-8 命令、事件排空及真实 render-pass 诊断。
- `HEManager.Graphics` 负责 D3D11 设备、DXGI composition swap chain、SwapChainPanel COM 绑定及渲染线程。render callback 只唤醒线程，不从回调重入 mpv。
- 渲染线程只调用 render API，不调用／等待播放器控制 API；使用 advanced control 提供真实通道诊断。正常关闭先停止解码并等待 idle，再停止渲染线程、释放 render context、detach panel，最后销毁 mpv core。
- 全屏只切换原 WinUI AppWindow presenter；保留同一个窗口、mpv core 和 render context。退出恢复原窗口位置尺寸。
- 原型选取硬件适配器，优先较大独立显存；使用 d3d11va。其他显卡、解码路径与格式仍须验证。不启动 mpv.exe，不复用 Electron IPC。
- GPU 纹理读取只在 `--smoke` 测试启用，不给正常播放增加 CPU readback。

## 第三方资源

libmpv 构建来自 shinchiro/mpv-winbuild-cmake 的固定 20261017 开发包，mpv 提交 `dde0671072723c311df874a32dc4e48b5197ca62`，实测 client API 2.6。归档漏带的 `render_d3d11.h` 从同一 mpv 提交补齐并单独校验。头文件保留上游许可；libmpv／FFmpeg、Anime4K 的许可和来源随输出目录 `resources/licenses` 保留，具体包来源同时见锁文件。未生成最终安装程序或进行正式签名。
