/**
 * 游戏拖拽参数机（Lua 控制层 Live2dDrag / Live2D）的 Web 还原。
 * 数据源是 extract.py 烘焙的 <id>.l2d.json（pg.ship_l2d 配置 + idle 变体表），每个条目描述一个可交互分区（draw_able_name，如 TouchIdle1/TouchDrag3）绑定的参数机：点击/拖拽驱动 parameter，按 range 钳制、smooth 平滑、松手后按 revert 回弹（-1 = 不回弹且持久化，游戏存 PlayerPrefs，这里存 localStorage）、parts_data 档位吸附；action_trigger.type 决定触发方式，触发后播放 action（可为随机数组）并应用 action_trigger_active（动作白名单/黑名单 + idle 变体切换）。字段语义与控制层逻辑的对照见 docs/azurlane.md 第 3 节。
 * 与 interaction.js 状态机的关系：这套机器接管"分区 -> 动作"的路由（游戏里就是 Lua 层在做的事），命中机器分区的手势不再走 playHitMotion 的组名近似路径；interaction.json 的参数门控继续负责没有机器的分区（摸头/普通触摸等 C# 层路径）。白名单/黑名单对一切动作播放生效（游戏 checkEnablePlay 语义）。
 * 触发类型扩展点：TRIGGER_HANDLERS 现已完整对齐 live2ddrag.lua（含 type 1-16、relation 101-104、offset_circle 圆盘拖拽、react_pos_x/y、react_condition、gyro、l2d_para_range、l2d_drag_rate、l2d_ignore_drag）。
 * 文件划分：machine.js 单台参数机（DragMachine）、orchestrator.js 编排器（DragOrchestrator + loadL2dConfig）、triggers.js 触发处理器表。保持零 npm 依赖（测试在 Node 下静态 import）。
 */
export { DragMachine } from './machine.js'
export { DragOrchestrator, loadL2dConfig } from './orchestrator.js'
