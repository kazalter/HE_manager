import fs from 'node:fs'
import path from 'node:path'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createTestClock } from './helpers/clock.mjs'
import { cubismCoreAvailable, loadCubismCore } from './helpers/cubism.mjs'
import { createEngineModel } from './helpers/engine.mjs'
import { makeCoreModel, makeModel, stubLocalStorage } from './helpers/fakes.mjs'

stubLocalStorage()

const HAS_CORE = cubismCoreAvailable()
const LOCAL_MODELS = path.resolve('../../../L2Dviewer/models')
const HAS_MODELS = HAS_CORE && fs.existsSync(LOCAL_MODELS)

test('DragMachine smooths continuously from live parameterValue and resolves shared-parameter contention', () => {
  return import('../src/utils/dragmachine/index.js').then(({ DragOrchestrator }) => {
    const params = { slide: 0, xAxis: 0, yAxis: 0, shared: 0 }
    const core = {
      getParameterIndex: (id) => Object.keys(params).indexOf(id),
      getParameterValueByIndex: (i) => params[Object.keys(params)[i]],
      setParameterValueByIndex: (i, v) => { params[Object.keys(params)[i]] = v },
    }
    const orch = new DragOrchestrator(
      { internalModel: { coreModel: core } },
      {
        skin_id: 'smooth_test',
        entries: [
          // Drag machine with 200ms smooth (333ms effective with 0.6 SMOOTH_RATE)
          { id: 1, draw_able_name: 'Slider', parameter: 'slide', mode: 1, range: [0, 10], offset_x: 10, smooth: 200, revert: -1 },
          // Dual-axis baifeng_2 pattern: machine parameter collides with relation 101 (additive mode 2)
          {
            id: 2,
            draw_able_name: 'Dual',
            parameter: 'xAxis',
            mode: 2,
            range: [-10, 10],
            offset_x: 10,
            offset_y: 10,
            smooth: 0,
            relation_parameter: { list: [{ type: 101, name: 'xAxis' }, { type: 102, name: 'yAxis' }] },
          },
          // Two mode-1 machines sharing 'shared'
          { id: 3, draw_able_name: 'OpenA', parameter: 'shared', mode: 1, range: [0, 1], action_trigger: { type: 2, target: 1 } },
          { id: 4, draw_able_name: 'CloseB', parameter: 'shared', mode: 1, range: [0, 1], action_trigger: { type: 2, target: 0 } },
        ],
      },
      () => true,
    )
    const [mSlide, mDual, mOpen, mClose] = orch.machines

    // 1. Holding or moving during smooth drag must not teleport to target in 2 frames.
    mSlide.onDown({ x: 0, y: 0 }, false)
    orch.onMove({ x: 50, y: 0 }) // target = 5
    const now = performance.now() / 1000
    mSlide.step(1 / 60, now, false, '')
    const afterFrame1 = mSlide.parameterValue
    assert.ok(afterFrame1 > 0 && afterFrame1 < 0.5, `frame 1 should be early in smooth curve, got ${afterFrame1}`)
    mSlide.step(1 / 60, now + 1 / 60, false, '')
    const afterFrame2 = mSlide.parameterValue
    assert.ok(afterFrame2 > afterFrame1 && afterFrame2 < 0.8, `frame 2 must NOT teleport to target, got ${afterFrame2}`)

    // Reversing drag target mid-flight must start from live parameterValue, never jumping to old target first.
    orch.onMove({ x: 0, y: 0 })
    mSlide.step(1 / 60, now + 2 / 60, false, '')
    assert.ok(
      mSlide.parameterValue < afterFrame2 && mSlide.parameterValue > 0.4,
      `reversal must move smoothly downward from ${afterFrame2}, got ${mSlide.parameterValue}`,
    )

    // 2. Dual-axis additive collision must restore clean base and write X->xAxis, Y->yAxis without runaway accumulation.
    mDual.onDown({ x: 0, y: 0 }, false)
    orch.onMove({ x: 30, y: -40 }) // deltaX = +3, deltaY = +4 (browser y inverted)
    for (let i = 0; i < 60; i++) mDual.step(1 / 60, now + i / 60, false, '')
    for (let i = 0; i < 60; i++) {
      orch.restoreLayer(core)
      params.xAxis = 0
      params.yAxis = 0
      orch.applyLayer(core)
    }
    assert.ok(Math.abs(params.xAxis - 3) < 0.05, `xAxis should be ~3 without double-add or explosion, got ${params.xAxis}`)
    assert.ok(Math.abs(params.yAxis - 4) < 0.05, `yAxis should track inverted Y ~4, got ${params.yAxis}`)

    // 3. Shared parameter contention: clicking OpenA must not be clobbered by untouched CloseB.
    mOpen.setTargetValue(1)
    for (let i = 0; i < 5; i++) mOpen.step(1 / 60, now + i / 60, false, '')
    orch.applyLayer(core)
    assert.equal(params.shared, 1)
    mClose.setTargetValue(0)
    for (let i = 0; i < 5; i++) mClose.step(1 / 60, now + i / 60, false, '')
    orch.applyLayer(core)
    assert.equal(params.shared, 0)
  })
})

test('gestures gate gaze below 3px, track proportionally without 180deg flip, and honor ignore_react', async () => {
  const { createGestures } = await import('../src/l2d/gestures.js')
  let targetX = 0
  let targetY = 0
  let ignoreReact = false
  const ctx = {
    app: {
      screen: { width: 1000, height: 800 },
      view: { getBoundingClientRect: () => ({ left: 0, top: 0 }) },
    },
    model: {
      visible: true,
      internalModel: {
        coreModel: { getDrawableVertexIndices: () => [] },
        hitAreas: { touch_head: { index: 0 } },
        getDrawableVertices: () => [480, 180, 520, 180, 520, 220, 480, 220], // center = (500, 200)
        focusController: {
          focus: (tx, ty) => { targetX = tx; targetY = ty },
        },
      },
      toGlobal: (p) => p,
      toModelPosition: (p) => p,
    },
    orch: {
      zoneOrder: () => -1,
      onUp: () => false,
      onMove: () => {},
      shouldIgnoreGaze: () => ignoreReact,
    },
    actions: { handleHitAreas: () => {} },
    dragScale: 1,
    lastGesture: 'tap',
  }
  const g = createGestures(ctx)
  const ev = (x, y) => ({ clientX: x, clientY: y, pointerId: 1, target: {} })

  // Move <= 3px -> tap jitter must NOT move gaze
  g.onPointerDown(ev(500, 200))
  g.onPointerMove(ev(502, 201))
  assert.deepEqual([targetX, targetY], [0, 0])

  // Move 28px right of head center -> proportional gaze (radius = 800*0.35 = 280 -> tx = +0.1)
  g.onPointerMove(ev(528, 200))
  assert.ok(Math.abs(targetX - 0.1) < 1e-6 && Math.abs(targetY) < 1e-6, `expected proportional tx=0.1, got ${targetX}`)

  // Cross center to 28px left -> smoothly moves to -0.1, never snaps to -1
  g.onPointerMove(ev(472, 200))
  assert.ok(Math.abs(targetX + 0.1) < 1e-6, `expected smooth crossing tx=-0.1, got ${targetX}`)

  // Active ignore_react machine must suppress gaze
  ignoreReact = true
  g.onPointerMove(ev(650, 200))
  assert.deepEqual([targetX, targetY], [0, 0])

  g.onPointerUp(ev(650, 200))
  assert.deepEqual([targetX, targetY], [0, 0])
})

test('InteractionRuntime tracks PartOpacity defaults, syncs cached boundaries synchronously, and ambient samples PartOpacity', async () => {
  if (!HAS_CORE) return
  await loadCubismCore()
  const { InteractionRuntime } = await import('../src/utils/interaction/runtime.js')
  const { loadAmbient } = await import('../src/utils/ambient.js')

  const paramVals = [0]
  const partVals = [1, 1]
  const partIds = ['PartA', 'PartB']
  const core = {
    ...makeCoreModel({ ParamX: { default: 0, min: -10, max: 10 } }),
    getPartCount: () => 2,
    getPartIndex: (id) => partIds.indexOf(id),
    getPartOpacityByIndex: (i) => partVals[i],
    setPartOpacityByIndex: (i, v) => { partVals[i] = v },
  }
  const motions = {
    idle: [{ File: 'm/idle.motion3.json' }],
    home: [{ File: 'm/home.motion3.json' }],
  }
  const files = {
    '/m/m/idle.motion3.json': { Meta: { Duration: 1 }, Curves: [{ Target: 'Parameter', Id: 'ParamX', Segments: [0, 0, 2, 1, 0] }] },
    '/m/m/home.motion3.json': {
      Meta: { Duration: 1 },
      Curves: [
        { Target: 'Parameter', Id: 'ParamX', Segments: [0, 0, 2, 1, 0] },
        { Target: 'PartOpacity', Id: 'PartB', Segments: [0, 0, 2, 1, 0] },
      ],
    },
    '/m/m/effect.motion3.json': {
      Meta: { Duration: 1 },
      Curves: [{ Target: 'PartOpacity', Id: 'PartA', Segments: [0, 0, 2, 1, 0] }],
    },
  }
  const origFetch = globalThis.fetch
  const origWindow = globalThis.window
  globalThis.window = { location: { href: 'http://localhost/' } }
  globalThis.fetch = async (url) => {
    const key = new URL(url, 'http://localhost/').pathname
    const body = files[key]
    return body ? { ok: true, json: async () => body } : { ok: false }
  }
  try {
    const model = makeModel(core, { motions })
    model.elapsedTime = 1000
    const rt = new InteractionRuntime(model, {
      clips: {
        home: { carry: { ParamX: [0, 5] } },
        idle: { carry: { ParamX: [0, 0] } },
      },
    })
    await rt.attachMotions('/m/model.model3.json')

    // Synchronous boundary sync: after attachMotions, applyEnd('idle') updates ParamX=0 without awaiting microtasks.
    rt.node.set('ParamX', 5)
    rt.applyEnd('idle')
    assert.equal(rt.node.get('ParamX'), 0)

    // Simulate home leaving PartB at 0; transitioning back to idle (which omits PartB) must smoothly restore PartB -> 1.
    partVals[1] = 0
    rt.beginSmoothReset(0.5, 'idle')
    model.elapsedTime = 1250
    rt.applySmoothReset()
    assert.ok(Math.abs(partVals[1] - 0.5) < 1e-6, `expected PartB midpoint 0.5, got ${partVals[1]}`)
    model.elapsedTime = 1500
    rt.applySmoothReset()
    assert.equal(partVals[1], 1)

    const ambient = await loadAmbient('/m/model.model3.json', { motions: { effect: [{ File: 'm/effect.motion3.json' }] } })
    ambient.apply(core, 0.2)
    assert.equal(partVals[0], 0)
  } finally {
    globalThis.fetch = origFetch
    globalThis.window = origWindow
  }
})

test('crossfade produces identical progress at 60Hz and 144Hz and PartOpacity writes apply on real models', async () => {
  if (!HAS_MODELS) return

  // 1. Crossfade FPS independence on lafeiii_3 (0.5s transition from idle -> touch_head)
  async function sampleMidpointAtFps(fps) {
    const dir = path.join(LOCAL_MODELS, 'lafeiii/lafeiii_3')
    const { internal, coreModel } = await createEngineModel(dir)
    const { CubismConfig } = await import('pixi-live2d-display/cubism4')
    assert.equal(CubismConfig.setOpacityFromMotion, true)
    internal.motionManager.groups.idle = 'idle'
    const clock = createTestClock(10).install()
    try {
      await internal.motionManager.startMotion('idle', 0, 3)
      for (let i = 0; i < fps; i++) internal.update(1000 / fps, clock.advance(1 / fps) * 1000)
      const before = Array.from({ length: coreModel.getParameterCount() }, (_, i) => coreModel.getParameterValueByIndex(i))

      // Start touch_head (0.5s fadeIn) and step exactly 0.25s (halfway)
      await internal.motionManager.startMotion('touch_head', 0, 3)
      const headJson = JSON.parse(fs.readFileSync(path.join(dir, 'motions/touch_head.motion3.json'), 'utf8'))
      const driven = new Set(headJson.Curves.filter((c) => c.Target === 'Parameter').map((c) => c.Id))
      const steps = Math.round(fps * 0.25)
      for (let i = 0; i <= steps; i++) internal.update(1000 / fps, clock.advance(i === 0 ? 0 : 1 / fps) * 1000)
      const mid = {}
      for (let i = 0; i < coreModel.getParameterCount(); i++) {
        const id = coreModel._parameterIds[i]
        if (driven.has(id)) mid[id] = coreModel.getParameterValueByIndex(i)
      }
      return { before, mid }
    } finally {
      clock.restore()
      internal.destroy()
    }
  }

  const at60 = await sampleMidpointAtFps(60)
  const at144 = await sampleMidpointAtFps(144)
  let maxDiff = 0
  for (const id of Object.keys(at60.mid)) {
    maxDiff = Math.max(maxDiff, Math.abs(at60.mid[id] - at144.mid[id]))
  }
  // Note: 0.25s aligns closely on both 60Hz (15 frames) and 144Hz (36 frames); with compound decay
  // the 144Hz midpoint would diverge heavily from 60Hz, whereas true crossfade matches closely.
  assert.ok(maxDiff < 0.35, `60Hz vs 144Hz crossfade midpoint diverged by ${maxDiff}`)

  // 2. PartOpacity curve writes take effect on aidang_2 (Part28 must become 0 under idle, not stay at moc=1)
  const aidangDir = path.join(LOCAL_MODELS, 'aidang/aidang_2')
  if (fs.existsSync(aidangDir)) {
    const { internal, coreModel } = await createEngineModel(aidangDir)
    const clock = createTestClock(10).install()
    try {
      internal.motionManager.groups.idle = 'idle'
      await internal.motionManager.startMotion('idle', 0, 3)
      for (let i = 0; i < 5; i++) internal.update(1000 / 60, clock.advance(1 / 60) * 1000)
      assert.equal(coreModel.getPartOpacityById('Part28'), 0, 'aidang_2 idle must hide Part28')
    } finally {
      clock.restore()
      internal.destroy()
    }
  }
})
