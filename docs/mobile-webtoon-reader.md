# 手机 Web 卷轴阅读

2026-10-31。范围：手机竖屏 Web 的图片序列、漫画章节。

## 共用入口

`MediaDetail.vue` 的图片和漫画都使用 `MangaReader.vue`，仅图片 URL、页数、尺寸和进度来源不同。卷轴手势集中在 `useWebtoonScroller.ts`，它调用 `useZoomScroller.ts`；不要为图片再复制一套卷轴缩放。

- 100% 按视口宽度显示；手机端不加页间缝、外边距或圆角。
- 新的单指手势使用原生滚动，保留浏览器的惯性。
- 双指捏合使用临时 transform，结束时落成实际宽高和匹配的 scrollTop/scrollLeft，保持手指锚点，静止时清晰显示图片。
- 卷轴捏合在手指未离开时就限制在 1–5 倍，拖动也限制在内容边界内。每次移动重新建立基准，越界后反向操作立即响应。
- 捏合结束不再播放回弹。只抬起一指时，剩余手指继续平移；全部松手后恢复普通原生滚动。
- 双击在 100% 与 200% 之间切换。滚动、捏合和取消手势之后的合成 click 不切换工具栏。
- 图片尺寸占位、解码缓存、预加载、进度跟踪继续复用阅读器已有实现。

## 公开站点参考

以下为公开发布代码的静态观察，不代表真机运行轨迹。独立实现上述行为，没有引入第三方站点的代码。

### WEBTOON 手机站

[阅读页面](https://m.webtoons.com/en/canvas/creator-collabs/intro-episode/viewer?episode_no=1&readingLanguageCode=en&title_no=1013154)；[当日 viewer bundle](https://m.webtoons.com/static/bundle/webToAppScrollViewer-da3437f33dac99d5acbf.js)。

`_getSizeInfo` 读取屏宽，以原图宽高计算显示高度和累计高度；`_makePanels` 先建立图片 DOM 和尺寸占位，再按滚动位置加载。此页面最终 viewport 声明允许 1–2 倍浏览器缩放。不能因这个 bundle 没有自定义 pinch 就断言整个站点没有。

- bundle SHA-256：`ffafa71ac6bef37e4c84e6e97024e7318f491a336bb3fa426bc7530c17a44b60`
- REA parent Evidence：`ev_3f66ec4d2d55171eea78412a54bd2a287ef765d6cf411e820acb09bef2e8ea19`
- AST 解析成功；语义图达到节点上限，覆盖不完整。

### MANGA Plus

[站点](https://mangaplus.shueisha.co.jp/)；[当日 app bundle](https://mangaplus.shueisha.co.jp/js/app.b51a50c2.js)。

纵向 surface 设置 `overflowY="scroll"` 并从 scroll 事件更新页码。公共 zoom setter 把比例限制为至少 1、至多 maxPageZoom；`setTransform` 限制 x/y 平移，pinch 事件更新 zoom。这里的缩放代码属于通用阅读器容器，不能据此认定它和 HE 的整列缩放、锚点策略完全相同。

- bundle SHA-256：`008623e2f29adcf4be3e263d7ef43ee6716ad59e1c694995bb1501ba48a244e1`
- REA parent Evidence：`ev_67c2d82470e20832c93917914025356282589b068bae077f7a5dd0367abaace2`
- REA AST 解析成功，后续语义分析耗尽 worker heap，图仅部分可用；上述细节另经直接检查发布代码确认。

HE 的设计取舍：沿用适配屏宽、原生纵向滚动、尺寸占位和实时边界限制；为满足内容最小 100%、工具栏固定及长章节进度跟踪，继续使用阅读器内部缩放。

## 验证

- `zoom-scroller.test.ts`：实时最小/最大比例、边界反向响应、长章节锚点、双指转单指、取消和监听器回收。
- `reader-images.test.ts`：图片/漫画两个入口在手机宽度下使用同样的卷轴和手势点击抑制。
- Chrome 手机模拟（390 × 844，真实 CDP touch 输入，50 页模拟内容）：图片与漫画均通过深处放大/缩小、即时边界反向、单指接续、新手势原生滚动、双击还原检查；提交布局前后页位置偏差约 0.55px，无页面异常。
- 没有进行 iPhone Safari 真机测试。
