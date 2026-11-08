import test from 'node:test'
import assert from 'node:assert/strict'
import { routeWallpaperPointer } from '../src/l2d/wallpaperPointer.js'

test('desktop gestures reach the Live2D gesture handlers in viewport coordinates', () => {
  const received = []
  const view = {}
  const gestures = {
    onPointerDown: (event) => received.push(['down', event]),
    onPointerMove: (event) => received.push(['move', event]),
    onPointerUp: (event) => received.push(['up', event]),
    onPointerCancel: () => received.push(['cancel']),
  }
  for (const type of ['down', 'move', 'up', 'cancel']) routeWallpaperPointer(gestures, view, { type, x: 123, y: 456 })
  assert.deepEqual(received.map(([type]) => type), ['down', 'move', 'up', 'cancel'])
  assert.deepEqual(received[0][1], { clientX: 123, clientY: 456, target: view, pointerId: 1 })
  routeWallpaperPointer(gestures, view, { type: 'down', x: NaN, y: 2 })
  assert.equal(received.length, 4)
})
