import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createTestClock } from './helpers/clock.mjs'
import { stubLocalStorage } from './helpers/fakes.mjs'

stubLocalStorage()

const { DragOrchestrator } = await import('../src/utils/dragmachine/index.js')
const { cubismCoreAvailable, loadCubismCore } = await import('./helpers/cubism.mjs')

function makeParamModel(paramDefs = {}, extraInternal = {}) {
  const ids = Object.keys(paramDefs)
  const values = ids.map((id) => paramDefs[id].default ?? 0)
  const mins = ids.map((id) => paramDefs[id].min ?? -100)
  const maxs = ids.map((id) => paramDefs[id].max ?? 100)
  const defs = ids.map((id) => paramDefs[id].default ?? 0)
  const core = {
    getParameterCount: () => ids.length,
    getParameterIndex: (id) => ids.indexOf(id),
    getParameterDefaultValue: (i) => defs[i] ?? 0,
    getParameterMinimumValue: (i) => mins[i] ?? 0,
    getParameterMaximumValue: (i) => maxs[i] ?? 1,
    getParameterValueByIndex: (i) => values[i],
    getParameterValueById: (id) => {
      const i = ids.indexOf(id)
      return i < 0 ? 0 : values[i]
    },
    setParameterValueByIndex: (i, v) => { values[i] = v },
    setParameterValueById: (id, v) => {
      const i = ids.indexOf(id)
      if (i >= 0) values[i] = v
    },
    addParameterValueById: (id, delta) => {
      const i = ids.indexOf(id)
      if (i >= 0) values[i] += delta
    },
    getModel: () => ({ canvasinfo: { PixelsPerUnit: 100 } }),
  }
  const model = {
    elapsedTime: 0,
    internalModel: {
      coreModel: core,
      width: 1000,
      height: 1000,
      focusController: { x: 0, y: 0, targetX: 0, targetY: 0, vx: 0, vy: 0, focus(tx, ty) { this.targetX = tx; this.targetY = ty } },
      settings: { motions: { idle: [{ File: 'idle.motion3.json' }] } },
      motionManager: { playing: false, groups: { idle: 'idle' }, state: {} },
      ...extraInternal,
    },
    toGlobal: (pt) => pt,
  }
  return { core, model }
}

async function advanceOrch(orch, model, clock, seconds, fps = 60) {
  const steps = Math.round(seconds * fps)
  const dt = 1 / fps
  for (let i = 0; i < steps; i++) {
    clock.advance(dt)
    model.elapsedTime = clock.nowMilliseconds()
    orch.step(dt)
    orch.restoreLayer(model.internalModel.coreModel)
    orch.applyLayer(model.internalModel.coreModel)
    await Promise.resolve()
    await Promise.resolve()
  }
}

test('react_condition (idle_on / idle_off) and react_pos_x/y gaze coupling', async () => {
  const clock = createTestClock(10).install()
  try {
    const { core, model } = makeParamModel({ Param3: { default: 0, min: -10, max: 10 } })
    const orch = new DragOrchestrator(
      model,
      {
        skin_id: 'react_test',
        entries: [
          { id: 1, parameter: '', mode: 1, range: [0, 1], react_condition: { idle_on: [1] } },
          { id: 2, parameter: '', mode: 1, range: [0, 1], react_condition: { idle_off: [2] } },
          { id: 3, parameter: 'Param3', mode: 2, range: [-10, 10], smooth: 0, react_pos_x: -7 },
          { id: 4, parameter: 'Param3', mode: 2, range: [-10, 10], smooth: 0, react_pos_x: 10 },
        ],
      },
      () => true,
    )
    assert.equal(orch.shouldIgnoreGaze(), true, 'idle=0 with idle_on=[1] should suppress gaze at startup')
    orch.changeIdleIndex(1, false)
    await advanceOrch(orch, model, clock, 0.05)
    assert.equal(orch.shouldIgnoreGaze(), false, 'idle=1 satisfies idle_on=[1]')

    model.internalModel.focusController.x = 0.5
    await advanceOrch(orch, model, clock, 0.05)
    // Machine 4 (react_pos_x=10) registered later has equal _writeSeq, wins additive Param3=5
    assert.ok(Math.abs(core.getParameterValueById('Param3') - 5) < 1e-6, `expected Param3=5, got ${core.getParameterValueById('Param3')}`)

    orch.changeIdleIndex(2, false)
    model.internalModel.focusController.x = -0.8
    await advanceOrch(orch, model, clock, 0.05)
    assert.equal(orch.shouldIgnoreGaze(), true, 'idle=2 triggers idle_off=[2]')
    assert.ok(Math.abs(core.getParameterValueById('Param3') - 5) < 1e-6, 'Param3 target freezes during react_condition suppress')
  } finally {
    clock.restore()
  }
})

test('offset_circle dial angle, shortest-arc wrap, and parts_data snap', async () => {
  const clock = createTestClock(20).install()
  try {
    const { core, model } = makeParamModel({ dial: { default: 0, min: 0, max: 4 } })
    const orch = new DragOrchestrator(
      model,
      {
        skin_id: 'circle_test',
        entries: [
          {
            id: 1,
            draw_able_name: 'DialZone',
            parameter: 'dial',
            mode: 1,
            range: [0, 4],
            range_abs: 1,
            smooth: 100,
            revert: -1,
            parts_data: { parts: [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4] },
            offset_circle: { start: 0, pos: [1, 1, 0] },
          },
        ],
      },
      () => true,
    )
    // Center in local/screen coords: (500 + 1*100, 500 - 1*100) = (600, 400)
    const center = orch.getCircleCenter([1, 1, 0], 'DialZone')
    assert.deepEqual(center, { x: 600, y: 400 })
    // Press at 3 o'clock (dx=+50, dy=0 -> 90 deg -> value = 1.0)
    orch.onDown('DialZone', { x: 650, y: 400 }, { x: 650, y: 400 })
    await advanceOrch(orch, model, clock, 0.4)
    assert.ok(Math.abs(core.getParameterValueById('dial') - 1.0) < 0.05, `3 o'clock should be ~1.0, got ${core.getParameterValueById('dial')}`)
    // Drag to ~351 deg (slightly left of 12 o'clock: dx=-8, dy=-50 in Y-down screen space) -> ~3.9
    orch.onMove({ x: 592, y: 350 }, { x: 592, y: 350 })
    await advanceOrch(orch, model, clock, 0.4)
    assert.ok(core.getParameterValueById('dial') > 3.7, `near 360deg should be >3.7, got ${core.getParameterValueById('dial')}`)
    // Cross 12 o'clock to +9 deg (dx=+8, dy=-50 -> target ~0.1): shortest-arc wrap goes UP across 4->0, never midpoint 2.0
    orch.onMove({ x: 608, y: 350 }, { x: 608, y: 350 })
    let sawMid = false
    for (let i = 0; i < 20; i++) {
      await advanceOrch(orch, model, clock, 1 / 60)
      const v = core.getParameterValueById('dial')
      if (v > 1.0 && v < 3.0) sawMid = true
    }
    assert.equal(sawMid, false, 'shortest-arc circle interpolation must wrap across 4/0, not rewind through 2.0')
    await advanceOrch(orch, model, clock, 0.3)
    assert.ok(Math.abs(core.getParameterValueById('dial') - 0.1) < 0.08)
    // Snap near 0.48 -> 0.5 on release
    orch.onMove({ x: 635, y: 352 }, { x: 635, y: 352 })
    await advanceOrch(orch, model, clock, 0.3)
    orch.onUp('DialZone', { x: 635, y: 352 })
    await advanceOrch(orch, model, clock, 0.3)
    assert.equal(orch.machines[0].parameterTargetValue, 0.5)
  } finally {
    clock.restore()
  }
})

test('type 13 DRAG_WITH_PARAMETER_MOVE and type 14 DRAG_MOVE_DOWN_UP', async () => {
  const clock = createTestClock(30).install()
  try {
    const played = []
    const { core, model } = makeParamModel({
      TTA: { default: 0, min: 0, max: 5 },
      TTB: { default: 0, min: 0, max: 1 },
      Lever: { default: 0, min: 0, max: 10 },
      WatchP: { default: 0, min: 0, max: 10 },
    })
    const orch = new DragOrchestrator(
      model,
      {
        skin_id: 't13_t14_test',
        entries: [
          {
            id: 1,
            draw_able_name: 'Zone13',
            parameter: 'TTB',
            mode: 1,
            range: [0, 1],
            smooth: 0,
            revert: -1,
            action_trigger: { type: 13, parameter: 'TTA', rate: 0.4, num: 1, action: 'act13' },
          },
          {
            id: 2,
            draw_able_name: 'Zone14A',
            parameter: 'Lever',
            mode: 1,
            range: [0, 10],
            offset_x: 10,
            smooth: 0,
            revert: -1,
            action_trigger: { type: 14, active: 1, range: [4, 10], action: 'act14_up' },
          },
          {
            id: 3,
            draw_able_name: 'Zone14B',
            parameter: '',
            mode: 1,
            range: [0, 10],
            action_trigger: { type: 14, active: 0, parameter: 'WatchP', range: [2, 6], action: 'act14_release' },
          },
        ],
      },
      async (clip) => { played.push(clip); return true },
    )
    assert.equal(orch.zoneInteractable('Zone13'), false, 'type 13 should be passive, never orange')
    // Type 13: baseline sample at 10/30s, then move TTA by 2.5 -> +2.5 * 0.4 = +1.0 -> triggers act13
    await advanceOrch(orch, model, clock, 0.35)
    core.setParameterValueById('TTA', 2.5)
    await advanceOrch(orch, model, clock, 0.4)
    assert.ok(played.includes('act13'), `expected act13 to trigger, played=${played}`)

    // Type 14 active=1: drag into (4, 10] fires once without killing active drag
    orch.onDown('Zone14A', { x: 0, y: 0 })
    orch.onMove({ x: 50, y: 0 }) // Lever = 5 in (4, 10]
    await advanceOrch(orch, model, clock, 0.05)
    assert.equal(played.filter((x) => x === 'act14_up').length, 1)
    assert.equal(orch.machines[1]._active, true, 'type 14 isApplyStopDrag must remain active during trigger')
    await advanceOrch(orch, model, clock, 0.2)
    assert.equal(played.filter((x) => x === 'act14_up').length, 1, 'type 14 must not re-fire while held')
    orch.onUp('Zone14A', { x: 50, y: 0 })

    // Type 14 active=0: fires on firstStop when WatchP in (2, 6]
    core.setParameterValueById('WatchP', 3.5)
    orch.onDown('Zone14B', { x: 0, y: 0 })
    await advanceOrch(orch, model, clock, 0.05)
    assert.equal(played.includes('act14_release'), false)
    orch.onUp('Zone14B', { x: 0, y: 0 })
    await advanceOrch(orch, model, clock, 0.05)
    assert.equal(played.includes('act14_release'), true)
  } finally {
    clock.restore()
  }
})

test('type 15/16 xiaqi tic-tac-toe flow, AI delay, win trigger, and listener reset', async () => {
  const clock = createTestClock(50).install()
  try {
    const played = []
    const params = {}
    const entries = []
    const names = ['a1', 'a2', 'a3', 'b1', 'b2', 'b3', 'c1', 'c2', 'c3']
    names.forEach((p, idx) => {
      params[p] = { default: 0, min: -1, max: 1 }
      entries.push({
        id: 100 + idx,
        draw_able_name: `TouchDrag${14 + idx}`,
        parameter: p,
        mode: 1,
        range: [-1, 1],
        smooth: 0,
        revert: -1,
        listener_data: { type: 1, change: [[2, ['touch_idle8'], 0]] },
        action_trigger: { type: 15, index: idx + 1 },
      })
    })
    entries.push({
      id: 200,
      draw_able_name: 'TouchDrag14',
      parameter: '',
      mode: 1,
      range: [-1, 1],
      action_trigger: { type: 16, win: 1, action: 'touch_idle6' },
      action_trigger_active: { idle: 7, enable: {}, ignore: {} },
    })
    entries.push({
      id: 201,
      draw_able_name: 'TouchDrag14',
      parameter: '',
      mode: 1,
      range: [-1, 1],
      action_trigger: { type: 16, win: 0, action: 'touch_idle9' },
      action_trigger_active: { idle: 10, enable: {}, ignore: {} },
    })
    const { core, model } = makeParamModel(params)
    const orch = new DragOrchestrator(
      model,
      { skin_id: 'xiaqi_test', idle_index: { 0: 'idle', 7: 'idle7', 10: 'idle10' }, entries },
      async (clip) => { played.push(clip); return true },
    )
    // Click cell 1 (TouchDrag14): after 0.1s confirm, a1 -> 1; AI sets one cell -1 after 0.2s
    orch.onDown('TouchDrag14', { x: 0, y: 0 })
    orch.onUp('TouchDrag14', { x: 0, y: 0 })
    await advanceOrch(orch, model, clock, 0.15)
    assert.equal(core.getParameterValueById('a1'), 1)
    assert.equal(orch.machines.slice(0, 9).filter((m) => m.parameterTargetValue === -1).length, 1, 'AI picked 1 response cell')
    await advanceOrch(orch, model, clock, 0.25)
    assert.equal(orch.machines.slice(0, 9).filter((m) => m.parameterValue === -1).length, 1, 'AI cell parameter applied after 0.2s delay')

    // Pre-fill top row (a2=1, a1=1, make sure a3=0) and win on TouchDrag16 after 1s cooldown
    orch.machines.slice(0, 9).forEach((m) => { m.setParameterValue(0); m.setTargetValue(0) })
    orch.machines[0].setParameterValue(1); orch.machines[0].setTargetValue(1)
    orch.machines[1].setParameterValue(1); orch.machines[1].setTargetValue(1)
    orch.machines[3].setParameterValue(-1); orch.machines[3].setTargetValue(-1)
    orch.machines[4].setParameterValue(-1); orch.machines[4].setTargetValue(-1)
    await advanceOrch(orch, model, clock, 1.1)
    orch.onDown('TouchDrag16', { x: 0, y: 0 })
    orch.onUp('TouchDrag16', { x: 0, y: 0 })
    await advanceOrch(orch, model, clock, 0.7) // 0.1s confirm + 0.5s xiaqi result delay
    assert.ok(played.includes('touch_idle6'), `win should play touch_idle6, played=${played}`)
    assert.equal(orch.idleIndex, 7)

    // touch_idle8 notice clears board
    orch.notice(1, { action: 'touch_idle8' })
    await advanceOrch(orch, model, clock, 0.05)
    assert.equal(core.getParameterValueById('a1'), 0)
  } finally {
    clock.restore()
  }
})

test('relation 104 (idle+time), type 5 remove_com_list, type 10 parameter_range, reset_index_action, gyro, and focus para_range/ignore_drag', async () => {
  const clock = createTestClock(70).install()
  try {
    const played = []
    const { core, model } = makeParamModel({
      relTarget: { default: 0, min: 0, max: 1 },
      Param90: { default: 0, min: 0, max: 1 },
      gateVal: { default: 150, min: 0, max: 200 },
      gyroP: { default: 0, min: -10, max: 10 },
      ParamAngleX: { default: 0, min: -30, max: 30 },
    })
    const orch = new DragOrchestrator(
      model,
      {
        skin_id: 'misc_parity_test',
        idle_index: { 0: 'idle', 4: 'idle4', 7: 'idle7' },
        l2d_para_range: { ParamAngleX: [-12, 12] },
        l2d_drag_rate: [0.5, 0.5, 0.5],
        entries: [
          {
            id: 1,
            draw_able_name: 'Zone104',
            parameter: '',
            mode: 1,
            range: [0, 1],
            action_trigger: { type: 2, action: 'touch_idle1' },
            action_trigger_active: { idle: 4, enable: {}, ignore: {} },
            relation_parameter: { list: [{ type: 104, name: 'relTarget', mode: 1, idle: 4, time: 0.5, target: 1 }] },
          },
          {
            id: 2,
            parameter: 'Param90',
            mode: 1,
            range: [0, 1],
            action_trigger: { type: 5, const_fit: [{ idle: 0, target: 1 }], remove_com_list: ['touch_idle1'] },
          },
          {
            id: 3,
            parameter: '',
            mode: 1,
            range: [0, 1],
            action_trigger: { type: 10, trigger_name: 'idle', trigger_index: 7, trigger_rate: 0.5, parameter_range: ['gateVal', [120, 201]], action: 'branch_hi' },
          },
          {
            id: 4,
            parameter: '',
            mode: 1,
            range: [0, 1],
            action_trigger: { type: 10, trigger_name: 'idle', trigger_index: 7, trigger_rate: 0.5, parameter_range: ['gateVal', [0, 120]], action: 'branch_lo' },
          },
          {
            id: 5,
            draw_able_name: 'ZoneResetIdx',
            parameter: 'relTarget',
            mode: 1,
            range: [0, 1],
            action_trigger: { type: 6, reset_index_action: ['touch_drag8'], action_list: [{ action: '' }, { action: '' }] },
          },
          {
            id: 6,
            parameter: 'gyroP',
            mode: 1,
            range: [-10, 10],
            smooth: 0,
            gyro: 1,
            gyro_x: 1,
          },
        ],
      },
      async (clip) => { played.push(clip); return true },
    )
    orch.clipDurationOf = () => 1

    // Initially idle=0: Param90=1 written by type 5; relTarget stays 0
    await advanceOrch(orch, model, clock, 0.05)
    assert.equal(core.getParameterValueById('Param90'), 1)

    // Playing touch_idle1 (in remove_com_list) yields Param90, and activates rel 104 after 0.5s
    model.internalModel.motionManager.playing = true
    orch.noteMotionStart('touch_idle1', false)
    core.setParameterValueById('Param90', 0.25)
    orch.changeIdleIndex(4, false)
    await advanceOrch(orch, model, clock, 0.2)
    assert.equal(core.getParameterValueById('Param90'), 0.25, 'remove_com_list must not overwrite Param90 during touch_idle1')
    assert.equal(core.getParameterValueById('relTarget'), 0, 'relation 104 waits 0.5s')
    await advanceOrch(orch, model, clock, 0.4)
    assert.equal(core.getParameterValueById('relTarget'), 1, 'relation 104 writes target=1 after 0.5s')

    // reset_index_action
    orch.machines[4].actionListIndex = 2
    orch.noteMotionStart('touch_drag8', false)
    await advanceOrch(orch, model, clock, 0.05)
    assert.equal(orch.machines[4].actionListIndex, 1)

    // type 10 parameter_range disambiguation
    model.internalModel.motionManager.playing = false
    orch.noteMotionFinish()
    orch.changeIdleIndex(7, false)
    orch.noteMotionStart('idle7', true)
    await advanceOrch(orch, model, clock, 0.6)
    assert.ok(played.includes('branch_hi') && !played.includes('branch_lo'))

    // Gyro off -> 0; gyro on -> mapped value
    assert.equal(core.getParameterValueById('gyroP'), 0)
    orch.setGyro(true, { y: 0.125 }) // 0.125 * 4 = 0.5 -> (0.5 + 0.5) * 20 - 10 = 10
    await advanceOrch(orch, model, clock, 0.05)
    assert.ok(Math.abs(core.getParameterValueById('gyroP') - 10) < 1e-6)

    // Real Cubism4InternalModel.prototype.updateFocus para_range clamping
    if (cubismCoreAvailable()) {
      await loadCubismCore()
      const { Cubism4InternalModel } = await import('pixi-live2d-display/cubism4')
      const { installMotionPatches } = await import('../src/l2d/motionPatches.js')
      installMotionPatches({ orch, fades: { default: 0.3 } })
      Object.assign(model.internalModel, {
        idParamEyeBallX: 'ParamEyeBallX',
        idParamEyeBallY: 'ParamEyeBallY',
        idParamAngleX: 'ParamAngleX',
        idParamAngleY: 'ParamAngleY',
        idParamBodyAngleX: 'ParamBodyAngleX',
      })
      model.internalModel.focusController.x = 1
      model.internalModel.focusController.y = 0
      core.setParameterValueById('ParamAngleX', 0)
      Cubism4InternalModel.prototype.updateFocus.call(model.internalModel)
      assert.equal(core.getParameterValueById('ParamAngleX'), 12, 'l2d_para_range clamps 30*1 to max 12')
    }
  } finally {
    clock.restore()
  }
})
