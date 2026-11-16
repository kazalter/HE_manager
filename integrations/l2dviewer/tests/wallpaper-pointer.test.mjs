import test from 'node:test'
import assert from 'node:assert/strict'
import { routeWallpaperPointer } from '../src/l2d/wallpaperPointer.js'

test('desktop gestures reach the Live2D gesture handlers in viewport coordinates', () => {
  const received = []
  const ripples = []
  const view = {}
  const gestures = {
    onPointerDown: (event) => received.push(['down', event]),
    onPointerMove: (event) => received.push(['move', event]),
    onPointerUp: (event) => received.push(['up', event]),
    onPointerCancel: () => received.push(['cancel']),
  }
  const rippleCtl = {
    onPointerDown: (event) => ripples.push(['down', event]),
    onPointerMove: (event) => ripples.push(['move', event]),
    onPointerUp: () => ripples.push(['up']),
  }
  for (const type of ['down', 'move', 'up', 'cancel']) routeWallpaperPointer(gestures, view, { type, x: 123, y: 456 }, rippleCtl)
  assert.deepEqual(received.map(([type]) => type), ['down', 'move', 'up', 'cancel'])
  assert.deepEqual(ripples.map(([type]) => type), ['down', 'move', 'up', 'up'])
  assert.deepEqual(received[0][1], { clientX: 123, clientY: 456, target: view, pointerId: 1 })
  routeWallpaperPointer(gestures, view, { type: 'down', x: NaN, y: 2 }, rippleCtl)
  assert.equal(received.length, 4)
  assert.equal(ripples.length, 4)
})
