const { test } = require('node:test');
const assert = require('node:assert/strict');
const { CloseFlush } = require('../src/close-flush.cjs');
test('close acknowledgement is bound to its window and nonce, and concurrent closes share a request', async () => {
  const sent = [], owner = {}, other = {};
  const flush = new CloseFlush((window, nonce) => sent.push({ window, nonce }));
  const first = flush.request(owner), duplicate = flush.request(owner);
  assert.equal(first, duplicate); assert.equal(sent.length, 1);
  let complete = false; void first.then(() => { complete = true; });
  flush.acknowledge(other, sent[0].nonce); flush.acknowledge(owner, 'old-request');
  await new Promise(setImmediate); assert.equal(complete, false);
  flush.acknowledge(owner, sent[0].nonce); assert.equal(await first, true);
});
test('a missing renderer acknowledgement has a bounded fallback and never reports success', async () => {
  const flush = new CloseFlush(() => {}, 10);
  assert.equal(await flush.request({}), false);
});
test('destroyed webContents are treated as an unavailable renderer', async () => {
  const flush = new CloseFlush(() => { throw new Error('destroyed'); });
  assert.equal(await flush.request({}), false);
});
