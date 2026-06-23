# HE Manager 功能路线图

> 代码即真相：已完成项只保留摘要；未完成项保留可执行说明。

## 当前状态

| # | 计划 | 状态 |
|---|------|------|
| ① | 个人数据看板 `/stats/*` + StatsView | ✅ 完成 |
| ② | 标签体系、命名空间、自动打标、回填 | ✅ 完成 |
| ③ | 创作者聚合页 | ✅ 完成 |
| ④ | 感知哈希近似去重 | ✅ 完成；跨标题 LSH 可选 |
| ⑤ | 标签管理界面 | ✅ 完成 |
| ⑥ | ASMR 同步、下载、播放、字幕、打标、镜像、体积控制 | ✅ 完成 |
| ⑦ | 手机端传输优化 | 🟡 后端完成；Android 分页搁置 |
| ⑧ | Android 性能 | ✅ release + BaselineProfile；滑动 Option B |
| ⑨ | 公网/FRP 安全加固 | ✅ 代码完成；安卓实际链路经 HTTPS |

## 剩余任务

1. **拆分 `backend/app/main.py`**
   见 `CODE_REVIEW_PLAN.md`。这是当前最主要的维护性任务。

2. **⑦ Android 分页**
   后端 `/mobile/media` 分页已兼容。Android `LibraryScreenV2` 当前整库拉取 + 客户端筛选/计数/搜索 + RecyclerView，接分页需要重写主屏数据流，回归风险高，暂缓。

3. **⑧ Option A**
   若滑动仍不够顺，再把卡片模式 RecyclerView + ComposeView 迁到 Compose `LazyVerticalGrid`；杂图保留原生 TileHolder。

4. **④ 可选后续**
   pHash 目前依赖 `normalized_title` 候选过滤，只抓同标题近似重复。跨标题改名/重编码副本需要 LSH/BK-tree 全库近邻。

5. **⑥ 可选后续**
   Baseline Profile 可升级为 baselineprofile 插件 + macrobenchmark 设备生成；当前手写 profile 已够用。

## 保留事实

- ASMR 用户喜欢是私有播放列表，不是 mark；同步必须使用本人 token。
- ASMR 镜像由客户端多镜像 fallback，用户配置 base 存 `source.favorites_url`。
- Android release 才能判断真实性能；debug 卡顿不能作为结论。
- 运维坑：改后端后确认 8010 无僵尸 uvicorn；watchfiles 在含空格路径上热重载容易抖。
