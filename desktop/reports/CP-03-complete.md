# CP-03：主进程身份、媒体会话连接与生命周期验收完成

2026-10-18 完成实施方案 CP-03。被测源码基线为 `6bef11c`，客户端版本为 `0.3.0`，Electron 固定为 `44.8.0`（Node API 8）。Windows x64 与 macOS arm64 均使用最终完整打包程序，双端均通过 20 项场景与鉴权检查、12 个视觉与布局组合、17 张状态截图，以及正常的窗口关闭进度刷写（close）与无凭据提交的会话恢复（restore）生命周期验收；双平台 ZIP 产物与实际执行内容的一致性审计状态均为 `passed`。

## 已完成的实现

1. **主进程身份与安全凭据管理**：
   - 接入 `DesktopSession` 与 `CredentialStore`。桌面登录、管理员初始化、凭据恢复与退出均通过窄化 IPC。
   - 凭据仅由主进程持有，渲染进程仅获取用户账号、会话代次（UUID generation）与非凭据状态；localStorage 与渲染进程中完全不含 JWT 或 access token。
   - 协议代理（`he://app/`）与 libmpv 请求由主进程统一注入 Bearer 鉴权头；媒体与缩略图 URL 仅携带非凭据会话代次查询参数，且主进程代理强制附加 `track_progress=false`。
   - 凭据存储使用 Electron 44 异步 `safeStorage` API（macOS Keychain / Windows DPAPI），写入版本标记为 `v2`、加密方案为 `async`；保存与删除操作串行化并采用 `.next` 临时文件原子替换，无加密能力时不写明文，新配置在无凭据文件时不触碰系统钥匙串。

2. **媒体库会话连接与场景隔离**：
   - 主媒体库采用桌面每页 60 项分页，正确读取并校验 `offset` 与 `X-Total-Count`。继续观看明确查询 `view_status=viewing` 与 `sort=opened`。
   - 列表、封面及悬停操作不触发详情接口；在进入播放器或阅读器前先通过只读方式验证媒体详情（带加载／失败反馈），详情验证未通过前不挂载播放器。
   - 切换账号或服务器时主动停止旧播放器、终止正在执行的图片超分任务并清除内存缓存授权。
   - 常驻业务 store（去重、漫画下载、ASMR 下载、外部导入）按会话代次隔离独立闭包，旧账号未决请求与任务键不与新会话混用。

3. **播放与阅读进度协同机制**：
   - 同一服务器与媒体 ID 的进度写入（PATCH）与打开详情（GET）共用串行队列；未发送的连续普通进度在同一会话及场景内合并。
   - 多页漫画第 0 页的 `progress=0` 重置与 `view_status=viewing` 修正在同一队列原子操作中执行，第二步仅在仍为最新意图时进行有限重试；单页漫画保留 `viewed`。
   - 窗口关闭时通过 `close-flush.cjs` 和 `session.flushWrites(2000)` 有界超时机制先通知渲染进程采集最新阅读/播放位置并完成服务端提交，随后由主进程安全释放 libmpv、表面租约与图片缓存。
   - 引入 `progress-outbox.cjs`，当网络发生临时故障时暂存最新一次进度意图，待网络连接恢复后仅重试最新意图，丢弃过期写入。

## 证据与测试矩阵

| 平台 / 检查项目 | 范围与执行条件 | 结果 |
| --- | --- | --- |
| **Linux 核心单元测试** | 54 项 Node.js 原生测试 (`desktop/test/*.test.cjs`) | **全部通过** (54/54) |
| **Linux 前端完整测试** | 31 个测试文件、140 项 Vitest 测试 (`npm test`) | **全部通过** (140/140) |
| **Linux 大库与多账号矩阵** | 双独立 FastAPI 容器（各 69 项媒体）、两套账号，验证 60 项分页、组合筛选、搜索、401/416 保持及服务器切换 (`session-matrix.cjs`) | **全部通过** (25/25) |
| **Linux 写入契约验证** | 验证无凭据快照、Range 206 鉴权、多页第 0 页两步修正、末页 viewed、重开位置及预取零副作用 (`session-contract.cjs`) | **全部通过** (13/13) |
| **macOS 打包场景与鉴权** | 完整打包 `HE Manager.app`，连接独立测试服务 18011；20 项场景检查、12 个布局、17 张截图，Videotoolbox 硬解、libmpv 暂停缩放、三轮全屏及资源归零 | **全部通过** (`partial-pass`, 20/20) |
| **macOS 正常关闭进度保存** | 独立 marked disposable profile，定位视频到 12 秒后执行正常窗口关闭，验证服务端媒体进度已刷写为 12、资源彻底释放且保持登录 | **全部通过** (6/6 checks) |
| **macOS 会话恢复无需密码** | 指向上述同一 profile 重新启动程序，验证在无 `/auth/login` 或 `/auth/bootstrap` 请求下通过 `/auth/me` 成功恢复身份，视频自动恢复至 12 秒 | **全部通过** (7/7 checks) |
| **Windows 打包场景与鉴权** | 完整打包 `HE Manager.exe`，通过 SSH 隧道连接测试服务 18012；20 项场景检查、12 个布局、17 张截图，D3D11VA 硬解、音轨/字幕、着色器及关闭释放 | **全部通过** (`partial-pass`, 20/20) |
| **Windows 正常关闭进度保存** | 独立 disposable profile，定位视频到 12 秒后触发正常关闭，验证服务端媒体进度刷写为 12、租约归零、DPAPI 凭据保留 | **全部通过** (6/6 checks) |
| **Windows 会话恢复无需密码** | 指向同一 profile 重启，验证无需用户输入账号密码即直接通过 `/auth/me` 恢复登录，视频进度恢复至 12 秒 | **全部通过** (7/7 checks) |
| **双平台审计** | 校验实际运行的 17 个 host 脚本、92 个 UI 文件、原生模块、ZIP SHA256 与各平台生命周期测试报告 | **全部通过** (`passed`) |

## 产物与交付清单

| 产物文件 | 平台与架构 | SHA-256 Checksum |
| --- | --- | --- |
| `HE-Manager-0.3.0-darwin-arm64.zip` | macOS (Apple Silicon arm64) | `b3b574954d9526b7c8880d116ef61e11d107e60db4cb4ffc03580a20bebf9f45` |
| `HE-Manager-0.3.0-win32-x64.zip` | Windows (x64) | `984315db0bc6b5bad3bba6688910f099ac4a20254d5cda19be98517db594ede9` |

### 验收与审计报告索引

- 双平台综合审计报告：[`desktop/reports/CP-03/CP-03-verification.json`](CP-03/CP-03-verification.json)
- macOS 详细场景报告：[`desktop/reports/CP-03/CP-03-mac-integration.json`](CP-03/CP-03-mac-integration.json)
- macOS 审计报告：[`desktop/reports/CP-03/CP-03-mac-integration-audit.json`](CP-03/CP-03-mac-integration-audit.json)
- macOS 关闭测试报告：[`desktop/reports/CP-03/CP-03-mac-lifecycle-close.json`](CP-03/CP-03-mac-lifecycle-close.json)
- macOS 恢复测试报告：[`desktop/reports/CP-03/CP-03-mac-lifecycle-restore.json`](CP-03/CP-03-mac-lifecycle-restore.json)
- Windows 详细场景报告：[`desktop/reports/CP-03/CP-03-windows-integration.json`](CP-03/CP-03-windows-integration.json)
- Windows 审计报告：[`desktop/reports/CP-03/CP-03-windows-integration-audit.json`](CP-03/CP-03-windows-integration-audit.json)
- Windows 关闭测试报告：[`desktop/reports/CP-03/CP-03-windows-lifecycle-close.json`](CP-03/CP-03-windows-lifecycle-close.json)
- Windows 恢复测试报告：[`desktop/reports/CP-03/CP-03-windows-lifecycle-restore.json`](CP-03/CP-03-windows-lifecycle-restore.json)
