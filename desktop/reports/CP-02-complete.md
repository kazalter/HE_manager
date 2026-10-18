# CP-02：双平台视觉与应用基础验收完成

2026-10-18 完成实施方案 CP-02。被测源码为 `152db35`，客户端版本为 `0.2.0`。Windows 与 Mac 均使用最终完整打包程序，各通过 19 项检查、12 个视觉组合和 17 张状态截图；双平台 ZIP 与实际执行内容一致性审计通过。Linux 生产服务的更新及提交后 CI 记录另行补充，不能用本机验收代替远端构建结果。

## 已完成的实现

同一 Vue 界面接入正式内嵌播放器，使用集中定义的桌面能力类型。视频提供实际音轨、字幕、倍速、定位、音量、增强设置、缓冲与失败反馈；关闭与全屏继续使用已选定的原生纹理链路。复用主题变量、按钮、弹层、菜单样式、卡片与空状态，补充共用滑块、加载与 Toast。

媒体库、视频和阅读器都支持浅色、深色及跟随系统。阅读器保留单页、双页、卷轴与缩放，并显示增强排队反馈。桌面阅读器的模式文字保持单行，缩放控件移到右上方以免遮挡页码进度条。

真机联调修复了进度小数导致的后端 422、对不存在的漫画缩略图生成接口的请求、Windows 菜单栏导致的内容区高度不足，以及滑块在同一事件轮次内提交旧值的问题。滑块回归测试在旧实现中得到 `3` 而非用户选择的 `20`，修复后通过；真机也验证了明显不同位置之间的实际定位。

## 证据与范围

| 项目 | 当前结果 |
| --- | --- |
| Windows 打包程序 | 19 项检查通过；12 个场景／主题／逻辑尺寸组合，17 张状态截图 |
| 内容尺寸 | 1280×800、1024×640；本机 100% 缩放下最小外框 1040×705，内容区 1024×640 |
| 视频 | 实际 D3D11VA；两条音轨与两条字幕；1.25×；三档实际着色器；暂停后 3 轮全屏保持会话与位置 |
| 定位 | 从约 5.958 秒选择 20 秒，实际读回 20.083 秒；关闭后原生表面、租约与 JS 引用归零 |
| 阅读器 | 单页／双页／卷轴、缩放、工具条不重叠、增强排队与完成；本次动漫 2× 生成成功 |
| 界面状态 | 登录、继续观看、长标题、横竖封面、缺封面、空搜索、加载、失败重试与返回 |
| HTTP | 本次界面代理无意外 4xx／5xx；后端为独立的真实 FastAPI＋合成媒体，不使用生产数据 |
| 自动测试 | 桌面 25 项；前端完整 121 项；最终阅读器布局修正后相关 16 项及类型检查通过；构建通过 |
| Mac 图片服务补充检查 | 最终包内同一引擎输出 960×1440 的 2× 结果；不作为 Mac 界面或 CP-05 验收 |
| Mac 包静态检查 | 主进程与 67 个 UI 文件和 Windows 包字节一致；原生模块为 arm64，源码哈希吻合；同时读取最终 ZIP 核对实际运行模块 |
| Mac 完整场景 | 19 项检查通过，12 个视觉组合、17 张状态截图；实际 videotoolbox-copy、两音轨／两字幕、1.25×、M／VL／原画；定位到 20 秒、3 轮全屏保持位置，关闭资源归零；实际 2× 图片增强成功 |

[Windows 执行报告](CP-02/CP-02-windows.json)、[Mac 执行报告](CP-02/CP-02-mac.json)记录实际执行的主进程、UI、原生模块与 libmpv 哈希。[双平台审计](CP-02/CP-02-verification.json)状态为 `passed`；每个原始执行报告的 `partial-pass` 只表示单平台。审计同时读取两个最终 ZIP，拒绝执行代码与交付包不一致。

两端输入均通过聚焦后的真实 Electron 鼠标／键盘事件执行。Mac 首轮复核发现截图领先合成器提交，补充双 requestAnimationFrame 与绘制等待，并检查选中模式和两页实际加载；重新打包、签名后双端复验，最终双页与卷轴截图均正确。系统主题检查使用 Electron 的 `nativeTheme` 覆盖来验证跟随系统的响应，未修改用户的全局系统主题。真机截图已经复核；完整触控板、DPI、多屏、性能和压力矩阵仍属于 CP-06。

## 构建与复验

前端使用 Node 22.22；Electron 固定 44.8.0。Windows 原生模块使用 MSVC 14.44.35207（cl 19.44.35229）与 SDK 10.0.26100.0；Mac 使用 Apple clang 21，明确编译并检查 arm64。其余运行资源沿用锁定清单。Mac 包为本地 ad-hoc 签名，正式分发验收属于 CP-07。

```sh
# 在 frontend/：类型检查后生成两端共用的 UI
node node_modules/vue-tsc/bin/vue-tsc.js -b
node node_modules/vite/bin/vite.js build --outDir ../desktop/ui --emptyOutDir
# 在 desktop/：使用目标机编译的原生模块与已验证的运行资源
node scripts/package.mjs win32
node scripts/package.mjs darwin
bash scripts/sign-macos.sh 'release/HE Manager-darwin-arm64/HE Manager.app'
python3 scripts/archive.py 'release/HE Manager-darwin-arm64' release/HE-Manager-0.2.0-darwin-arm64.zip darwin
```

每次真机运行前重启独立测试服务：`HE_PROBE_UI_FIXTURES=1`、`HE_PROBE_UI_STREAM_DELAY=1`，使用重新生成的私有 `client-access.json`。通过 `HE_DESKTOP_TEST_CONFIG` 和 `HE_DESKTOP_TEST_OUTPUT` 启动包内程序；Mac 的配置和输出放在权限受限的临时目录，避免读取外部 Desktop 文件时等待系统目录授权。账号、密码与 token 不写入报告或进程参数。

```sh
python3 desktop/probe/verify-ui-evidence.py desktop/reports/CP-02 \
  --revision 152db35
# 历史 CP-01 使用当时的源码，不拿新实现替换历史证据：
python3 desktop/probe/verify-evidence.py desktop/reports/CP-01 \
  --revision 1f80c57 --output desktop/.diagnostics/cp01-historical-audit.json
```

| 本地产物 | 字节数 | SHA-256 |
| --- | ---: | --- |
| HE-Manager-0.2.0-win32-x64.zip | 304500152 | `170565a7a16af0f712d7b9499d9e7836282cc2a00902a8a5be3bd0ead204c464` |
| HE-Manager-0.2.0-darwin-arm64.zip | 246353000 | `950f0a5bf1df164442d597ffd4ff3c79879cf9c76b9ff8145c935ec67da9babf` |

本阶段提交并推送后，检查新增原生构建 CI，进入 CP-03 的连接、身份隔离与媒体库契约。完整登录隔离、分页、预取不改观看状态属于 CP-03；音频和长时视频属于 CP-04，4× 图片／缓存质量属于 CP-05，多屏／性能压力属于 CP-06，安装器及正式分发属于 CP-07。
