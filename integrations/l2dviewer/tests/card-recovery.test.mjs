// 真实 Cubism 动作队列 + 真实配置，覆盖 lafeiii_3 展牌/选牌/收牌链。
import fs from 'node:fs'
import assert from 'node:assert/strict'
import { createEngineModel } from './helpers/engine.mjs'
import { createTestClock } from './helpers/clock.mjs'
import { stubLocalStorage } from './helpers/fakes.mjs'

stubLocalStorage()
const dir = process.argv[2] ?? 'models/lafeiii/lafeiii_3'
const { internal, coreModel, settings } = await createEngineModel(dir)
internal.motionManager.groups.idle = 'idle' // 与生产 Live2DModel.from(idleMotionGroup: 'idle') 一致
const { InteractionRuntime } = await import('../src/utils/interaction/runtime.js')
const { DragOrchestrator } = await import('../src/utils/dragmachine/orchestrator.js')
const { createActions } = await import('../src/l2d/actions.js')
const { installMotionPatches } = await import('../src/l2d/motionPatches.js')
const config = JSON.parse(fs.readFileSync(`${dir}/lafeiii_3.l2d.json`, 'utf8'))
const data = JSON.parse(fs.readFileSync(`${dir}/lafeiii_3.interaction.json`, 'utf8'))
const model = { internalModel: internal, motion: (g, i, p) => internal.motionManager.startMotion(g, i, p) }
const ctx = { model, currentMotion: { value: '' }, fades: { default: 0.3 } }
installMotionPatches(ctx)
ctx.runtime = new InteractionRuntime(model, data)
ctx.actions = createActions(ctx)
ctx.orch = new DragOrchestrator(model, config, ctx.actions.playLuaAction)
ctx.runtime.checkEnable = (clip) => ctx.orch.checkEnablePlay(clip)
internal.motionManager.on('motionStart', (g, i) => ctx.orch.noteMotionStart(ctx.runtime.clipOf(g, i), g === 'idle'))
internal.motionManager.on('motionFinish', () => ctx.orch.noteMotionFinish())
internal.on('beforeMotionUpdate', () => ctx.orch.restoreLayer(coreModel))
internal.on('afterMotionUpdate', () => ctx.orch.applyLayer(coreModel))
const clock = createTestClock(10).install()
const flush = () => new Promise((resolve) => setImmediate(resolve))
async function advance(seconds) {
  for (let f = 0; f < seconds * 60; f++) {
    ctx.orch.step(1 / 60)
    internal.update(1000 / 60, clock.advance(1 / 60) * 1000)
    await flush()
  }
}
async function click(zone, drag = false) {
  assert.equal(ctx.orch.zoneInteractable(zone), true, `${zone} must be available`)
  ctx.orch.onDown(zone, { x: 0, y: 0 })
  if (drag) ctx.orch.onMove({ x: 0, y: -250 })
  await advance(0.3)
  ctx.orch.onUp(zone, { x: 0, y: 0 })
  await flush()
}
try {
  for (const [zone, variant, close] of [['touch_idle4', 4, 'touch_idle7'], ['touch_idle5', 5, 'touch_idle8'], ['touch_idle6', 6, 'touch_idle9']]) {
    ctx.orch.resetAll(); ctx.runtime.resetState(); internal.motionManager.stopAllMotions()
    await ctx.actions.playLuaAction('idle'); await advance(0.5)
    await click('touch_idle1'); await advance(9)
    assert.ok([1, 2, 3].includes(ctx.orch.idleIndex), 'opening cards selects a waiting idle')
    await click(zone, true); await advance(6)
    assert.equal(ctx.orch.idleIndex, variant)
    assert.equal(ctx.runtime.pending, `idle${variant}`)
    assert.equal(ctx.orch.isPlaying, false)
    const before = Array.from({ length: coreModel.getParameterCount() }, (_, i) => coreModel.getParameterValueByIndex(i))
    await advance(0.7)
    const changed = before.some((v, i) => Math.abs(v - coreModel.getParameterValueByIndex(i)) > 0.001)
    assert.ok(changed, 'idle must continue moving after card selection')
    await click(close); await advance(3)
    assert.equal(ctx.orch.idleIndex, 0)
    assert.equal(ctx.runtime.pending, 'idle')
    assert.equal(ctx.orch.zoneInteractable('touch_idle1'), true, 'cards can be opened again')
    console.log(`PASS ${zone} -> idle${variant} -> ${close} -> idle; animation and next interaction available`)
  }
} finally { clock.restore(); internal.destroy() }
