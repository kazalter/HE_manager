// Real engine: measure the rendered handoff, rather than only checking eventual recovery.
import fs from 'node:fs'
import assert from 'node:assert/strict'
import { createEngineModel } from './helpers/engine.mjs'
import { createTestClock } from './helpers/clock.mjs'
import { stubLocalStorage } from './helpers/fakes.mjs'
stubLocalStorage()
for (const [ship, skin] of [['dafeng', 'dafeng_6'], ['lafeiii', 'lafeiii_3']]) {
  const dir = `${process.argv[2] ?? 'models'}/${ship}/${skin}`
  const { internal, settings } = await createEngineModel(dir)
  const { InteractionRuntime } = await import('../src/utils/interaction/runtime.js')
  const { DragOrchestrator } = await import('../src/utils/dragmachine/orchestrator.js')
  const { createActions } = await import('../src/l2d/actions.js')
  const { installMotionPatches } = await import('../src/l2d/motionPatches.js')
  const manager = internal.motionManager
  manager.groups.idle = 'idle'
  const clock = createTestClock(10).install()
  const model = { internalModel: internal, elapsedTime: 10000, motion: (g, i, p) => manager.startMotion(g, i, p) }
  const ctx = { model, currentMotion: { value: '' }, fades: JSON.parse(fs.readFileSync(`${dir}/${skin}.fades.json`)) }
  installMotionPatches(ctx)
  ctx.runtime = new InteractionRuntime(model, JSON.parse(fs.readFileSync(`${dir}/${skin}.interaction.json`)))
  ctx.actions = createActions(ctx)
  ctx.orch = new DragOrchestrator(model, JSON.parse(fs.readFileSync(`${dir}/${skin}.l2d.json`)), ctx.actions.playLuaAction)
  manager.on('motionStart', (g, i) => ctx.orch.noteMotionStart(ctx.runtime.clipOf(g, i), g === 'idle'))
  manager.on('motionFinish', () => ctx.orch.noteMotionFinish())
  const flush = () => new Promise(resolve => setImmediate(resolve))
  let finishAt = null, idleAt = null, empty = 0
  manager.on('motionFinish', () => { finishAt = model.elapsedTime })
  manager.on('motionStart', g => { if (g === 'idle' && finishAt !== null) idleAt = model.elapsedTime })
  try {
    const core = internal.coreModel
    const idx = 0, target = core.getParameterDefaultValue(idx)
    core.setParameterValueByIndex(idx, target + 1)
    ctx.runtime.beginSmoothReset(0.5)
    model.elapsedTime += 100
    ctx.runtime.applySmoothReset()
    const partial = core.getParameterValueByIndex(idx)
    clock.advance(10) // wallpaper paused: wall clock advances; model clock does not
    ctx.runtime.applySmoothReset()
    assert.equal(core.getParameterValueByIndex(idx), partial, 'pause must freeze parameter reset')
    model.elapsedTime += 500
    ctx.runtime.applySmoothReset()
    assert.equal(core.getParameterValueByIndex(idx), target, 'resume completes reset on animation time')
    console.log(`${skin}: parameter reset pauses with animation`)
    await ctx.actions.playLuaAction('idle')
    await ctx.actions.playLuaAction('touch_head')
    for (let i = 0; i < 1800 && idleAt === null; i++) {
      model.elapsedTime = clock.advance(1 / 60) * 1000
      const updated = manager.update(internal.coreModel, model.elapsedTime / 1000)
      if (finishAt !== null && !updated) empty++
      await flush()
    }
    console.log(`${skin}: finish=${finishAt}, idleStart=${idleAt}, empty rendered motion frames=${empty}`)
    assert.notEqual(idleAt, null, 'must resume idle')
    assert.equal(empty, 0, 'natural completion must not render an empty motion tick')
  } finally { clock.restore(); internal.destroy() }
}
