const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const { serverUrl } = require('../src/policy.cjs');
const { EmbeddedPlayer } = require('../src/embedded-player.cjs');

test('ui-audit: serverUrl rejects malformed and credential-bearing inputs with friendly message', () => {
  assert.equal(serverUrl('http://127.0.0.1:8010/'), 'http://127.0.0.1:8010');
  assert.equal(serverUrl('https://he.example.com:8443'), 'https://he.example.com:8443');

  // Friendly error message check on invalid URL
  assert.throws(() => serverUrl('not-a-valid-url'), /地址只允许 HTTP\/HTTPS/);
  assert.throws(() => serverUrl('ftp://example.com'), /地址只允许 HTTP\/HTTPS/);
  assert.throws(() => serverUrl('http://user:pass@127.0.0.1:8010'), /不要包含账号或参数/);
  assert.throws(() => serverUrl('http://127.0.0.1:8010?token=123'), /不要包含账号或参数/);
  assert.throws(() => serverUrl('http://127.0.0.1:8010#hash'), /不要包含账号或参数/);
  assert.throws(() => serverUrl(''), /请输入服务器地址/);
});

test('ui-audit: embedded-player state reflects both synchronous isFullScreen and asynchronous _heFullscreen', async () => {
  let isFull = false;
  const mockWindow = {
    isDestroyed: () => false,
    webContents: { mainFrame: {}, send() {} },
    isFullScreen: () => isFull,
    setFullScreen(val) { isFull = Boolean(val); },
  };

  const sessions = [];
  const native = {
    create() {
      const session = { stopped: false, paused: false, position: 0, duration: 100, droppedFrames: 0, hwdec: 'auto', ended: false, buffering: false, tracks: [], aid: '1', sid: 'no', speed: 1, command: null };
      sessions.push(session);
      return session;
    },
    resize() {},
    state(session) { return session; },
    acquire() { return null; },
    release() {},
    send(session, kind, args) { session.command = { kind, args }; },
    close(session) { session.stopped = true; },
  };

  const player = new EmbeddedPlayer({
    root: path.resolve(__dirname, '..'),
    sharedTexture: { importSharedTexture: () => ({ release() {} }), sendSharedTexture: async () => {} },
    getWindow: () => mockWindow,
    native,
  });

  await player.open(null, { url: 'http://test/stream/1' }, 'off');
  assert.equal(player.state.fullscreen, false);

  // When control('fullscreen') is called, window.isFullScreen becomes true
  await player.control('fullscreen');
  assert.equal(isFull, true);
  // player.state.fullscreen must be true even if _heFullscreen is not yet set
  assert.equal(player.state.fullscreen, true);

  // When control('exit-fullscreen') is called, window.isFullScreen becomes false
  await player.control('exit-fullscreen');
  assert.equal(isFull, false);
  assert.equal(player.state.fullscreen, false);

  // Verify asynchronous _heFullscreen flag also reflects true
  mockWindow._heFullscreen = true;
  assert.equal(player.state.fullscreen, true);
  mockWindow._heFullscreen = false;

  await player.stop();
});
