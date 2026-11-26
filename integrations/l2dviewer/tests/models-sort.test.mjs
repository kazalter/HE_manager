import assert from 'node:assert/strict'
import test from 'node:test'

globalThis.window ??= { location: { origin: 'http://localhost' } }

const { sortModels } = await import('../src/utils/models.js')

test('sortModels orders newest shop_id first and places zero/missing shop_id at the end', () => {
  const sorted = sortModels([
    { id: 'biaoqiang', name: '标枪', shop_id: 0 },
    { id: 'aidang_2', name: '盛夏进行曲', shop_id: 70009 },
    { id: 'unknown_skin', name: '未知皮肤' },
    { id: 'nabulesi_3', name: '误入纯白迷途', shop_id: 71424 },
    { id: 'antu_2', name: '午夜的瑰色电梯', shop_id: 71398 },
  ])

  assert.deepEqual(
    sorted.map((m) => m.id),
    ['nabulesi_3', 'antu_2', 'aidang_2', 'biaoqiang', 'unknown_skin'],
  )
})
