const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { L2dCache, canCache } = require('../src/l2d-cache.cjs');

test('canCache admits model assets and rejects manifest, session, import, and traversal paths', () => {
  assert.equal(canCache('/l2d/models/lafei/lafeiii_3/lafeiii_3.moc3'), true);
  assert.equal(canCache('/l2d/models/lafei/lafeiii_3/textures/texture_00.png'), true);
  assert.equal(canCache('/l2d/models/manifest.json'), false);
  assert.equal(canCache('/l2d/models/session'), false);
  assert.equal(canCache('/l2d/models/import/lafeiii_3'), false);
  assert.equal(canCache('/l2d/models/lafei/../secret'), false);
  assert.equal(canCache('/media/1'), false);
});

test('L2dCache stores, reads, isolates by server, and clears entries', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'he-l2d-cache-'));
  try {
    const cache = new L2dCache(dir);
    const payload = Buffer.from('moc3-binary-data');
    assert.equal(await cache.get('https://a.example', '/l2d/models/c/s/s.moc3'), null);
    assert.equal(await cache.put('https://a.example', '/l2d/models/c/s/s.moc3', 'application/octet-stream', payload), true);
    const hit = await cache.get('https://a.example', '/l2d/models/c/s/s.moc3');
    assert.equal(hit.contentType, 'application/octet-stream');
    assert.deepEqual(hit.body, payload);
    assert.equal(await cache.get('https://b.example', '/l2d/models/c/s/s.moc3'), null);
    await cache.clear();
    assert.equal(await cache.get('https://a.example', '/l2d/models/c/s/s.moc3'), null);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
});
