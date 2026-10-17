# CP-01：双平台内嵌媒体原型

2026-10-18 完成实施方案 §7.4 的原型关卡。正式媒体库及播放器集成仍按 CP-02～CP-07 推进；本阶段不代表完整客户端已经交付。

## 选定的正式媒体路径

同一代码库、Electron **44.8.0**，主进程加载 Node-API 8 addon。每个会话包含控制和渲染两个原生线程，不维护另一套 helper 路径。

| 项目 | Windows x64 | macOS arm64 |
| --- | --- | --- |
| 实测系统 | Windows 11 build 26200 | macOS 27 / M1 Pro |
| 工程最低目标 | Windows 11 24H2 / build 26100 | macOS 15 |
| libmpv | v0.41.0-1200-gdde067107，API 2.6 | 稳定版 v0.41.0，API 2.5 |
| 原生出口 | gl_video / libmpv D3D11 render API | gl_video / libmpv OpenGL render API |
| 共享资源 | BGRA D3D11 NT HANDLE，无 keyed mutex | BGRA IOSurface / CGL FBO |
| 生产者完成同步 | D3D11 event query + Flush/GetData | glFinish |
| 实际硬解 | d3d11va | videotoolbox-copy |
| 页面出口 | sharedTexture → VideoFrame → canvas；DOM 覆盖 | 同左，按 devicePixelRatio 处理 Retina |

Windows 的 D3D11 render API 尚需开发版 mpv，固定 commit
`dde0671072723c311df874a32dc4e48b5197ca62`，升级须重跑两端矩阵。
Mac 使用 IINA 1.5.0 中稳定版 libmpv 的 **44 个 arm64 dylib** 依赖闭包；最小系统版本最高为 11.0，addon 以 15.0 为编译目标。没有采用要求 macOS 27 的本机 Homebrew 运行库。最低目标系统的实体安装验证仍属于 CP-07。

两个纹理槽采用 Free → Rendering → Ready → Leased → Free；完成帧保留到 acquire，消费者只取最新完成帧，旧的未租借完成帧才可丢弃。无空槽时跳过渲染，不排入无限队列。资源返回后重试占满时未完成的重画，包括暂停状态缩放。GPU 写入完成后才公布纹理，Electron 的 allReferencesReleased 才归还源资源。关闭先停止渲染并销毁 mpv，再等引用归还和原生资源释放；主线程等待上限分别为 5 秒，失败明确报错。

主进程只传句柄和尺寸/会话元数据，没有每帧 CPU 像素 JS IPC。这里不承诺全链路零拷贝：Mac 硬解使用 copy 模式，canvas 合成和生产者同步也有成本，CP-04 再测吞吐、功耗与复制成本。

## §7.4 验收证据

所有最终报告来自包含原生模块和运行库的打包程序。四次播放运行和两次普通关闭运行均通过；汇总脚本核对实际执行的 JS、原生构建源码和依赖二进制 SHA-256。

| 条件 | 结果与证据 |
| --- | --- |
| 主窗口内真实视频 | 两端本地与 HTTP 图像采样均非空；红色上角/蓝色下角标记验证方向和颜色；四张窗口截图位于 CP-01/ |
| 本地与受保护流、HTTP seek | 30 秒合成 H.264/AAC/SRT 文件；实际 HE FastAPI/auth/stream 路由提供 Bearer 流；匿名 401、鉴权 Range 206、非零 Range 与实际播放定位均通过 |
| DOM 覆盖和窗口尺寸 | 原生鼠标输入操作覆盖的视频控制条与弹出菜单；播放及暂停缩放、缩小后取样通过 |
| 硬解和增强 | 实际 hwdec-current 如上表；实际 vo-passes 分别显示原画无 Anime4K、效率 Restore-CNN-(M)、质量 Restore-CNN-(VL)，不以菜单状态代替 |
| 同会话全屏 | 每次运行进入/退出三轮；以原生 enter/leave-full-screen 事件确认；sourceLoads 保持 1，暂停/时间、aid=2、sid=2、speed=1.25 保持 |
| 生命周期与资源 | 停收一秒仍保留完成帧；每帧延迟 250 ms 后继续显示，最大在途 2；最小化恢复后有新图像；每次运行再打开三次，所有关闭状态 leases/surfaces/inFlight=0；普通窗口关闭也归零 |
| 无隐式开发动态库 | Mac 检查 addon + 44 dylib，只依赖包内 @loader_path 与系统路径；Windows /MT addon、延迟加载 Electron 宿主，DLL 导入检查与仅 System32/Windows PATH 运行通过 |

验收服务器使用当前项目的真实后端实现和独立临时数据库/账号/合成媒体，在 Windows 回环地址运行，Mac 经 SSH 本地转发访问。没有读取或更改生产数据库、生产凭证和原媒体；该结果不代表已经在当前离线的 Linux 生产主机完成联调。Linux 实际媒体库接入和业务状态回归继续在 CP-03 验证。

Windows 固定 libmpv 硬依赖 `vulkan-1.dll`，测试机来自 `C:\Windows\System32`、版本 1.4.341.0。客户端不依赖 Vulkan SDK/CUDA 工具包，但需要供应商显卡驱动提供 loader；后续能力检测须给出明确缺失提示。

中间诊断发现并修复：Windows 共享纹理创建标志、Mac 画面上下翻转、完成帧被渲染线程持续抢占、资源指针与状态读取竞争、占满后暂停重画遗漏。Mac 自动化输入需要聚焦窗口，最终包使用正常 LaunchServices 应用启动，并在注入输入前确认焦点；直接从终端启动失焦的失败不作为通过证据。一次受限环境启动没有产生本地报告，其后同一包的正常启动及带日志的受限环境本地复验均完成；最终本地/网络/关闭报告完整，未产出的运行不纳入汇总。

## 复现与交付

构建、资源来源、线程与释放规则见 [native/README](../native/README.md)；来源/版本/工具链及原始归档校验位于 [runtime-lock](../native/runtime-lock.json) 和 [header-lock](../native/header-lock.json)。构建信息、最终包 manifest、fixture manifest 记录各自产物的实际哈希。Mac ad-hoc 签名，Windows 暂未签名；正式安装器、签名/公证仍属于 CP-07。

```sh
python3 desktop/probe/verify-evidence.py desktop/reports/CP-01
npm test --prefix desktop
```

本地打包输出位于 `desktop/native/release/`，不把大型二进制提交到 Git。最终 SHA-256 和大小见 [CP-01-packages.json](CP-01/CP-01-packages.json)。Windows 的同一 ZIP 已复制到目标机并解压验证。

- Windows：`HE-Manager-CP01-win32-x64.zip`，212,087,473 bytes。
- macOS：`HE-Manager-CP01-darwin-arm64.zip`，155,747,667 bytes。
- 汇总：[CP-01-verification.json](CP-01/CP-01-verification.json)。
- 桌面原有回归：19/19 通过；新增桥接原型语法检查进入桌面 CI。原生编译和图形验收在两台目标实体机完成，普通 CI 不替代 GPU/窗口验收。Windows toolset 目录版本为 14.44.35207，实际 cl.exe 文件版本为 19.44.35229.0，SDK 为 10.0.26100.0。

维护成本：约一层薄 C++ 图形互操作及两套平台构建脚本；sharedTexture 仍是实验性接口，固定版本并在升级时重验。原生崩溃会影响主进程；若未来转 helper，必须重新验证进程间资源转移和本关卡。Mac OpenGL 已被 Apple 弃用，未来更换出口也须重验。

本阶段合成样例覆盖可行性。完整格式/字幕矩阵、实际声音与音量、长时播放、GPU 设备丢失、功耗/内存压力、最终业务会话集成和分发均不记为已完成，按后续阶段验收。
