const { test } = require('node:test');
const assert = require('node:assert/strict');
const { EmbeddedPlayer } = require('../src/embedded-player.cjs');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function fixture() {
  const sessions = [], releases = [], imports = [];
  const native = {
    create(options) { const item = { options, stopped: false, closed: false, leases: 0, next: 1, position: 0, duration: 30, error: '', tracks: [{ id: 2, type: 'audio' }] }; sessions.push(item); return item; },
    state(owner) { return { ready: true, paused: false, ended: false, speed: 1, ...owner }; },
    acquire(owner) { if (owner.leases >= 2 || owner.closed) return null; owner.leases++; return { width: 640, height: 360, frame: owner.next++, handle: Buffer.alloc(8) }; },
    release(owner, frame) { releases.push({ owner, frame }); owner.leases--; if (owner.closed && !owner.leases) owner.stopped = true; },
    resize() {}, send(owner, kind, args) { owner.command = { kind, args }; if (args[0] === 'seek') owner.position = Number(args[1]); },
    close(owner) { owner.closed = true; if (!owner.leases) owner.stopped = true; },
  };
  const window = { isDestroyed: () => false, webContents: { mainFrame: {}, send() {} }, isFullScreen: () => false, setFullScreen() {} };
  const sharedTexture = {
    importSharedTexture(options) { const imported = { release() {}, complete: options.allReferencesReleased }; imports.push(imported); return imported; },
    async sendSharedTexture() {},
  };
  const player = new EmbeddedPlayer({ root: '/app', sharedTexture, getWindow: () => window, native });
  return { player, sessions, releases, imports, window };
}
test('stopping waits for consumer leases before the next media owns textures', async () => {
  const { player, sessions, releases, imports } = fixture();
  await player.open(null, { url: 'http://media/1', token: 'test-secret' }, 'off');
  player.ready(); await player.pump();
  assert.equal(imports.length, 1);
  const next = player.open(null, { url: 'http://media/2' }, 'off');
  await sleep(30);
  assert.equal(sessions.length, 1, 'do not create a new core while old textures are still leased');
  imports[0].complete();
  await next;
  assert.equal(releases[0].owner, sessions[0]);
  assert.equal(sessions[0].stopped, true);
  assert.equal(sessions.length, 2);
  assert.deepEqual(sessions[0].options.headers, ['Authorization: Bearer test-secret']);
  assert.deepEqual(sessions[1].options.headers, []);
  assert.equal(JSON.stringify(player.state).includes('test-secret'), false);
  player.receiverReady = false;
  for (const item of imports.slice(1)) item.complete();
  await player.stop();
});
test('queued opens are cancelled if the viewer closes before execution', async () => {
  const { player, sessions } = fixture();
  const first = player.open(null, { url: 'http://media/1' }, 'off');
  const closed = player.stop();
  await assert.rejects(first, /取消/);
  await closed;
  assert.equal(sessions.length, 0);
});
test('cleanup still drains a core that has reported a playback failure', async () => {
  const { player, sessions } = fixture();
  await player.open(null, { url: 'http://media/1' }, 'off');
  sessions[0].error = 'private engine failure';
  assert.equal(player.state.error.includes('private engine'), false);
  await player.stop();
  assert.equal(sessions[0].stopped, true);
});
test('controls reject invalid commands and unavailable tracks', async () => {
  const { player, sessions } = fixture();
  await player.open(null, { url: 'http://media/1' }, 'off', 12);
  assert.equal(player.state.position, 12);
  await assert.rejects(player.control('seek-to', NaN));
  await assert.rejects(player.control('speed', 500));
  await assert.rejects(player.control('audio-track', 999));
  await assert.rejects(player.control('run-shell-command', 'private'));
  await player.control('subtitle-track', 0);
  assert.deepEqual(sessions[0].command.args, ['set', 'sid', 'no']);
  await player.stop();
});

test('closing while GPU information is pending never starts a native media core', async () => {
  const { player, sessions, window } = fixture();
  let ready;
  window._heGpuReady = new Promise((resolve) => { ready = resolve; });
  const opening = player.open(null, { url: 'http://media/1' }, 'off');
  await sleep(10);
  const closing = player.stop();
  ready();
  await assert.rejects(opening, /取消/);
  await closing;
  assert.equal(sessions.length, 0);
  assert.equal(player.state.loading, false);
});

test('GPU discovery failure leaves an idle player that can be retried', async () => {
  const { player, sessions, window } = fixture();
  window._heGpuReady = Promise.reject(new Error('private GPU diagnostic'));
  await assert.rejects(player.open(null, { url: 'http://media/1' }, 'off'), /显卡信息/);
  assert.equal(player.state.loading, false);
  assert.equal(player.state.running, false);
  assert.equal(sessions.length, 0);
  window._heGpuReady = Promise.resolve();
  await player.open(null, { url: 'http://media/1' }, 'off');
  assert.equal(player.state.error, '');
  await player.stop();
});
