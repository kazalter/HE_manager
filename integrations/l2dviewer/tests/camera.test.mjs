import assert from 'node:assert/strict'
import { test } from 'node:test'

globalThis.localStorage = { getItem: () => null, setItem: () => {} }
const { createCamera } = await import('../src/l2d/camera.js')

function fixture(withOffset = false) {
  let vertices = [100, 100, 900, 100, 900, 900, 100, 900]
  const model = {
    internalModel: {
      width: 1000, height: 1000, settings: {},
      coreModel: { getDrawableCount: () => 1, getDrawableId: () => 'body', getModel: () => ({ canvasinfo: { PixelsPerUnit: 100 } }) },
      getDrawableVertices: () => vertices,
    },
    scale: { x: 1, set(value) { this.x = value } },
    position: { x: 0, y: 0, set(x, y) { this.x = x; this.y = y } },
  }
  const ctx = { model, modelUrl: 'fixture', app: { screen: { width: 1200, height: 800 } }, fill: () => 1, l2dOffset: withOffset ? [0, 0, 0, 52] : null }
  return { ctx, model, camera: createCamera(ctx), setVertices(value) { vertices = value } }
}

for (const withOffset of [false, true]) {
  test(`viewport round trip preserves camera (${withOffset ? 'offset' : 'measured'} model)`, () => {
    const { ctx, model, camera, setVertices } = fixture(withOffset)
    camera.fitModel({ refreshScene: true })
    camera.zoomAt(1.7, 700, 300)
    camera.pan(110, -35)
    const original = [model.position.x, model.position.y, model.scale.x]
    // A later animation frame has different visible bounds; it must not redefine the framing.
    setVertices([300, 300, 600, 300, 600, 600, 300, 600])
    Object.assign(ctx.app.screen, { width: 1920, height: 1080 })
    camera.fitModel()
    Object.assign(ctx.app.screen, { width: 0, height: 0 })
    const beforeHidden = [model.position.x, model.position.y, model.scale.x]
    camera.fitModel()
    assert.deepEqual([model.position.x, model.position.y, model.scale.x], beforeHidden)
    Object.assign(ctx.app.screen, { width: 1200, height: 800 })
    camera.fitModel()
    for (const [actual, expected] of [model.position.x, model.position.y, model.scale.x].map((x, i) => [x, original[i]])) {
      assert.ok(Math.abs(actual - expected) < 1e-9, `${actual} != ${expected}`)
    }
  })
}
