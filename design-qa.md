# 重复管理界面 Design QA

**对照目标**

- Source visual truth: `/opt/stacks/he-manager/volumes/audits/dedup-2026-07-18/selected-option-3.png`
- Implementation screenshot: `/opt/stacks/he-manager/volumes/audits/dedup-2026-07-18/05-implementation-desktop.png`
- Mobile screenshot: `/opt/stacks/he-manager/volumes/audits/dedup-2026-07-18/07-implementation-mobile.png`
- Delete modal screenshot: `/opt/stacks/he-manager/volumes/audits/dedup-2026-07-18/06-implementation-delete-modal.png`
- Viewport: source 1487×1058，按比例归一化到 1440×1024；实现 1440×1024；移动端 390×844。
- State: 午夜蓝主题、待处理列表、漫画候选行已选中并展开差异、检测任务运行中。

**对照证据**

- Full-view comparison: `/opt/stacks/he-manager/volumes/audits/dedup-2026-07-18/08-source-vs-implementation.png`
- Focused comparison: `/opt/stacks/he-manager/volumes/audits/dedup-2026-07-18/09-detail-comparison.png`，聚焦展开行、左右记录、逐项差异和操作层级。该区域是密集信息界面的核心，单靠全屏缩略图不足以检查字号、对齐与主次操作。

**Findings**

- 当前无可执行的 P0/P1/P2 问题。
- 字体与排版：沿用项目 Inter/system-ui 字体链；标题、表头、记录标题、辅助信息和路径形成清楚的五级层级。最小正文为 12px，未发现压缩、异常换行或截断主要信息。
- 间距与布局：侧栏、紧凑状态条、筛选条、候选表格和展开区与目标的密度和阅读顺序一致；主操作在首屏可见。390px 下改为单列卡片，无水平滚动，菜单按钮与标题不重叠。
- 色彩与视觉令牌：午夜蓝背景、低对比边框、琥珀差异提示、绿色文件状态、红色危险操作和靛蓝主操作映射正确；主操作计算样式为 `rgb(129, 140, 248)`，不再透明。
- 图像与资产：界面图标全部使用项目既有 Lucide 图标组件；当前浏览器夹具特意使用 `cover_path: null` 验证真实无封面回退态，生产数据有封面时仍使用已有缩略图接口渲染。没有用自制 SVG、CSS 图形或 emoji 替代图标。
- 文案与内容：动作明确区分“保留左侧记录”“采用右侧路径”“两者不是重复”“文件清理”，并解释数据库记录和磁盘文件的实际后果。
- 可访问性与交互：原生表单控件有可读标签；删除弹窗具有 `role=dialog`、`aria-modal=true`、描述关联、初始焦点、Tab 焦点约束、Esc 关闭和焦点恢复；危险动作需二次确认。

**Comparison History**

1. 第一轮：发现 P2 顶部标题/状态/筛选区域过高，且选中后的批量操作横幅会推挤主列表。修复为紧凑标题栏和单行筛选控件，将批量动作合并到分页信息区，并减小候选行垂直内边距。修复后证据：`08-source-vs-implementation.png`。
2. 第二轮：发现 P1 Tailwind 4 未自动加载旧版 JavaScript 配置，`bg-accent`、`bg-background` 等自定义颜色类未生成，主按钮背景实际透明。已在 `frontend/src/style.css` 显式加载 `tailwind.config.js`；重新构建后主操作计算背景为 `rgb(129, 140, 248)`。修复后证据：`08-source-vs-implementation.png` 与 `09-detail-comparison.png`。
3. 第三轮：按相同桌面状态重新对照，并补测 390×844 移动端和删除确认态；没有新的 P0/P1/P2 问题。

**Primary Interactions Tested**

- 展开/收起候选详情。
- 勾选候选并显示安全批量“不是重复”动作。
- 删除确认弹窗初始焦点、ARIA 语义和 Esc 关闭。
- 390px 移动端标题与侧栏菜单按钮碰撞检测。
- Browser console errors checked: `[]`。

**Implementation Checklist**

- [x] 桌面端密集列表与内联详情。
- [x] 移动端单列响应式结构。
- [x] 筛选、排序、分页和请求竞态保护。
- [x] 安全批量处理与独立危险文件清理。
- [x] 删除弹窗键盘和焦点管理。
- [x] 浏览器渲染、关键交互和控制台检查。

**Follow-up Polish**

- P3：若要制作演示素材，可用带真实漫画封面的专用测试数据再补一张展示截图；不影响实际封面渲染或本轮验收。

final result: passed
