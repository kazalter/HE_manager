# 手机 Web 卷轴阅读

2026-10-31。范围：手机竖屏 Web 的图片序列、漫画章节。

图片和漫画都从 `MediaDetail.vue` 进入同一个 `MangaReader.vue`。图片 URL、尺寸与进度来源不同，卷轴行为共用 `useWebtoonScroller.ts` 和 `useWebtoonDocument.ts`。

## WNACG 的实际实现

本次检查了 [WNACG 手机阅读页](https://www.wnacg.com/photos-slide-aid-400249.html)、[阅读器主脚本](https://www.wnacg.com/themes/mo/images/reader.m.mini.2026092201.js?v=1791550966)、[阅读器 CSS](https://www.wnacg.com/themes/mo/images/reader.m1.css) 和 reader-bar 脚本。只检查网页代码，没有保留或复用其漫画内容。

观察到：

- 阅读页 viewport 声明 `initial-scale=1.0, maximum-scale=5.0, user-scalable=yes`。
- HTML 内联样式针对竖向模式放开 body 的纵向滚动，把 `#viewport` 设为 `overflow:visible;height:auto;position:static`。只看外部 CSS 中的 `overflow-y:auto` 会漏掉这层覆盖。
- 阅读器主脚本不注册双指 touch/pinch/gesture 缩放处理。竖向模式跳页和自动滚动调用 `window.scrollTo` / `window.scrollBy`。
- 图片使用 `max-width:100%`，按原图尺寸预留高度；只挂载阅读位置附近的图片。

由此推断，卷轴的捏合与平移主要交给浏览器原生视口处理，而不是脚本在手指移动时缩放整列、松手再重排。这与之前 HE 的实现有实质区别。

REA parent Evidence：`ev_60a78c6e9b5eefb35f3999bcd842952408435b42061ba092e8e0c7c2cef8b005`。

REA 成功解析本地捕获的 5 个 JavaScript 文件、6329 个 AST 节点，无解析失败；静态语义仍有动态关系未知，不能把这些结果解释为完整的站点运行轨迹。上述 CSS/viewport 结论另经 HTML 和样式原文核对。

发布文件 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| 阅读页 HTML | `c098dd01888a3b4dab739a0ac461dc6857dd816d4193c21fed089a1fd93125f0` |
| reader 主脚本 | `290b91b012d0a60094213dee032a5a7dfb44bb1848a36eb057b78f22b8d6bf99` |
| reader CSS | `b8b59e81b50181dec7d6bd3b8ea8f1ae9bc26f390ad3ab1542d5ae23709712cd` |
| reader-bar 脚本 | `67160109301b45d19cbc53e94a2f0369d7d07367cfe26d765079c58d6ac3a00b` |

## HE 的实现

- 手机 Web 卷轴改用文档滚动和浏览器原生捏合，声明 1–5 倍视口缩放、`touch-action:manipulation`。浏览器负责缩放边界、平移与惯性。
- 不再拦截手机卷轴的 touchmove / Safari gesture，不冻结滚动，不在捏合或松手时改变图片列尺寸或 transform。
- 图片按屏宽布局，手机端不额外添加页缝、外边距和圆角。预留尺寸、解码缓存和前后预取仍复用原有实现。
- 从 `visualViewport.pageTop/height` 计算阅读位置和可见预取范围；放大平移时即使 `window.scrollY` 不变，也能更新进度。跳页补偿 `visualViewport.offsetTop`。
- 根滚动样式仅在手机 Web 卷轴激活期间启用；退出或切换模式时恢复滚动、监听器及原始 viewport 声明。放大状态退出时先改变 initial-scale，再恢复原声明，避免媒体库留在放大状态。
- 捏合、滚动、取消和触摸双击不会误触全屏。和 WNACG 的 manipulation 设置一致，手机卷轴以捏合缩放为主，触摸双击不再触发脚本 2 倍缩放。
- 桌面卷轴及单/双页继续使用 `useZoomScroller`，不改变原有翻页交互。

## 验证与边界

- 新增原生手势、viewport 声明、监听器清理、退出/快速重入测试。
- 更新 Home → verification → detail → reader 的手机回归，确认原生文档滚动期间不重建图片阅读器，不丢失滚动位置或隐藏工具栏状态。
- 新增 visualViewport 平移回归：文档 scrollY 不变也必须正确更新路由与阅读页码。
- Chrome 手机模拟（390 × 844、真实 CDP touch 输入、50 页自有模拟图片）验证两个入口：原生放大到 5 倍、图片列仍为 390px 且 transform 为空、纵向/横向平移、放大后进度、切换单页并返回原阅读位置、放大后关闭恢复 1 倍。
- 另以 Home Screen 的 `he-standalone` 布局重复验证文档滚动、放大平移和模式切换，避免已定位的 body 吞掉长卷轴滚动范围问题。
- 没有进行 iPhone Safari 真机测试。原生缩放的弹性、最大/最小值最终由浏览器实现，不再承诺脚本硬钳制的手感。

## 完整页面复核：iPhone Air / iOS 27.2 Safari 反馈

用户再次反馈松手跳动、滑动与缩放不顺滑。此前组件测试没有包含完整 Home/MediaDetail 外层，不能用来推断 Safari 手感。

这次对生产构建的完整页面做受控 API 回放：60 页 800×1200 图片、390×844 手机视口，保留真实 Home → verification → MediaDetail → MangaReader。旧版 a36676e 的首次打开结果：

| 几何指标 | 旧版 | 修复后 |
| --- | ---: | ---: |
| 第一页在文档中的 top | -17128px | 0px |
| 图片列高度 | 35100px | 35100px |
| 文档可滚动高度 | 17972px | 35100px |
| 后台媒体库是否参加布局/绘制 | 是 | 否 |

原因是 `.he-media-overlay` 仍保留 `display:flex; align-items:center`。把里面的阅读列改成 height:auto 后，外层仍只高一屏，会把长列竖直居中，前半列进入负坐标。不能只修改里面的 overflow。手机阅读入口现在让整个 Teleport 外壳也进入普通文档流，并暂时隐藏 `#app`，真正成为独立阅读文档；退出后恢复媒体库。

运行捕获 REA Evidence：`ev_166331e7f8ee325f373a38f82b096ba2f4e89410ed61aa826c87fca704518db0`。几何数字由独立 CDP/Playwright 探针取得；REA 用于记录当时的完整页面结构，不声称它执行了测量表达式。

第二个问题是生产数据缺尺寸：1994 张杂图中有 1992 张缺 width/height。读取这 1992 个原文件的图片头都成功，说明不是文件损坏。列表接口、单件打开和扫描现在会补齐缺失几何数据；`backend/scripts/backfill_image_dimensions.py` 可先 dry-run，再带数据库备份回填已有记录，只写 width/height。

第三个问题是解码缓存回收与 DOM 驻留绑定。大图使 96MiB 解码预算很快用完，邻页虽已下载却随缓存淘汰被拆掉。现在阅读窗口内已加载的图片保留 DOM，由浏览器管理像素缓存；远离窗口后仍会回收。

进一步用同一组 3.7–5.0MB JPEG、60 页混合横竖比例、100–300ms 模拟网络，执行六次滑动及一次捏合。修复后的完整 HE 页面与捕获的 WNACG 主脚本分别做本地受控回放；原始 layout-shift 条目 value 合计不作为正式 CLS 指标：

| 场景 | 布局次数 | 新增/移除图片 DOM | 原始 shift value 合计 |
| --- | ---: | ---: | ---: |
| HE 旧版，杂图缺尺寸 | 95 | 45 / 45 | 1.2322 |
| HE 修复后，杂图缺尺寸的压力场景 | 61 | 9 / 8 | 0.0001 |
| HE 旧版，漫画有尺寸 | 184 | 21 / 20 | 0.9785 |
| HE 修复后，漫画有尺寸 | 101 | 7 / 6 | 0.0006 |
| WNACG 主脚本参考回放 | 28 | 9 / 0 | 0 |

这些是单次桌面 Chrome 手机模拟结果，输入位置相同但旧版几何错误导致实际经过的页数不同，因此不能据此宣称同比性能提升比例。两者 rAF 帧间隔 P95 均约 16.8ms，这也不能证明 iPhone Safari 已达到相同流畅度。

另一个不可混淆的变量：本次抽查的 WNACG 章节 20 页均为 1133×1600，而 HE 最近图片包含 2K–4K 原图。即使采用同样的原生手势，解码/栅格化成本也会不同。本次没有通过降低原图分辨率掩盖问题。

### 可复跑的完整页面检查

先构建并启动 `frontend/dist` 静态服务器，再执行 `frontend/scripts/check-mobile-webtoon.cjs`。需要可用的 Playwright 和 Chromium；可通过 `HE_PLAYWRIGHT_MODULE`、`BROWSER_EXECUTABLE`、`HE_READER_BASE_URL` 指定环境。

检查覆盖图片/漫画 × 浏览器/主屏幕布局四种组合：首屏位置、完整滚动范围、后台库隐藏、路由进度不重建阅读器、原生捏合不改图片列 transform、关闭还原。它在旧生产版本 a36676e 上稳定因负坐标失败，在修复构建上通过。所有业务 API 都由脚本本地回放，不使用真实账号或写入真实进度。

本轮上线前已在 HDD2 保存一致性 SQLite 备份，回填 1992 条记录；回读确认 1994/1994 张杂图均有尺寸，未改原文件及进度/收藏等字段。验证：267 项前端测试、29 项相关后端测试，以及四种完整浏览器场景通过。
