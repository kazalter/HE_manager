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
