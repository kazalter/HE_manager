# Web 与桌面前端维护

Web 与桌面使用同一个 `frontend/`。媒体浏览、阅读器和通用交互应共享实现；Electron 私有接口在 `desktop/src/preload.cjs` 和 `frontend/src/desktop-contract.ts` 中定义。新增能力优先通过 `frontend/src/platform/capabilities.ts` 暴露，并对不支持该能力的 Web 或旧桌面壳保留可用的原始功能。图片增强是首个迁移的能力；已有桌面判断逐步迁移，不应一次重写播放器、鉴权或会话隔离。

## 修改和验证

1. 从服务器和 GitHub 对齐后的同一个提交开始，检查工作区状态。共享交互修改同时覆盖 Web 和桌面路径；涉及外层验证组件时，测试整个组件链，不能只 mock 掉外层。
2. 运行 `npm --prefix frontend test` 和 `npm --prefix desktop test`。构建 Web 使用 `npm --prefix frontend run build`；桌面包使用 `npm --prefix desktop run build:ui` 和桌面打包流程。涉及 Electron 桥、原生播放器或硬件时，还要在对应真实平台运行打包程序验证。
3. 两种构建的 `version.json` 都包含 `buildId`、`sourceRevision` 和 `sourceDirty`。设置页和桌面设置显示界面源码版本。`sourceDirty: true` 表示构建时存在已跟踪文件的未提交修改；它不检查未跟踪文件。无法识别 Git 时版本显示未知，不能据此声称两端一致。`buildId` 仍用于 Web 更新提醒，与源码提交号用途不同。
4. CI 对 Web 和桌面构建分别校验完整源码提交号及干净的已跟踪文件；只比较同一提交的两个构建，部署状态仍需另行确认。GitHub 发布流程应从该提交生成正式包并记录平台、版本及验证结果；用户安装新版桌面包后桌面代码才会更新。

桌面设置的“检查桌面更新”由用户手动触发，仅检查 GitHub 最新公开正式 Release 的三段版本号，下载页面固定为本项目的 Releases。它不下载、安装或自动重启。没有正式 Release、版本无法比较或网络失败时不会假报已更新。老桌面壳没有该接口时，界面会提示客户端需要更新；不要让新版界面依赖旧壳不存在的功能。应用版本与前端源码提交号分别记录，不能用前者证明 Web 和桌面源码一致。
