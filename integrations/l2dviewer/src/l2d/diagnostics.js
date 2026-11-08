import { Ticker } from 'pixi.js'
// Bounded trace for comparing motion handoff, parameter layers and wallpaper pauses.
export function installMotionDiagnostics(ctx, model) {
  const frames = [], events = []
  const manager = model.internalModel.motionManager
  const core = model.internalModel.coreModel
  let enabled = false, previous = null, motionValues = null, wall = null
  const push = (list, value, limit) => { list.push(value); if (list.length > limit) list.shift() }
  const event = (type, detail = {}) => push(events, {
    type, wall: performance.now(), elapsed: model.elapsedTime, ...detail,
  }, 128)
  ctx.traceEvent = event
  const api = {
    start() { enabled = true; previous = null; wall = null; frames.length = 0; event('trace-start') },
    stop() { enabled = false },
    read() { return { model: ctx.modelUrl, enabled, events: [...events], frames: [...frames] } },
  }
  if (typeof window !== 'undefined') window.__l2dDiagnostics = api
  manager.on('motionStart', (group, index) => event('motion-start', {
    group, index, clip: ctx.runtime?.clipOf(group, index), idleVariant: ctx.orch?.idleIndex,
  }))
  manager.on('motionFinish', () => event('motion-finish', { clip: ctx.runtime?.pending }))
  model.internalModel.on('afterMotionUpdate', () => {
    if (enabled) motionValues = Array.from({ length: core.getParameterCount() }, (_, i) => core.getParameterValueByIndex(i))
  })
  model.internalModel.on('beforeModelUpdate', () => {
    if (!enabled || !motionValues) return
    const now = performance.now()
    let motionDelta = 0, postMotionDelta = 0
    for (let i = 0; i < motionValues.length; i++) {
      const range = core.getParameterMaximumValue(i) - core.getParameterMinimumValue(i) || 1
      motionDelta = Math.max(motionDelta, previous ? Math.abs(motionValues[i] - previous[i]) / range : 0)
      postMotionDelta = Math.max(postMotionDelta, Math.abs(core.getParameterValueByIndex(i) - motionValues[i]) / range)
    }
    push(frames, {
      wall: now, wallDelta: wall === null ? 0 : now - wall, elapsed: model.elapsedTime,
      ticker: ctx.app?.ticker.started, sharedTicker: Ticker.shared.started,
      clip: ctx.runtime?.pending, reset: ctx.runtime?.resetPending,
      motionDelta, postMotionDelta,
      queue: manager.queueManager._motions.map(e => ({
        time: model.elapsedTime / 1000 - e._startTimeSeconds, weight: e._stateWeight,
      })),
    }, 600)
    previous = motionValues; wall = now
  })
  model.once('destroy', () => { if (typeof window !== 'undefined' && window.__l2dDiagnostics === api) delete window.__l2dDiagnostics })
}
