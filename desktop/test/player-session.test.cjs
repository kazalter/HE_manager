const { test } = require('node:test');
const assert = require('node:assert/strict');
const { PlayerSession } = require('../src/player-session.cjs');

function mockEmbeddedPlayer() {
  let running = false, position = 0, duration = 30, stopped = false, leases = 0;
  const stateObj = {
    running: false, paused: true, position: 0, duration: 30, droppedFrames: 0,
    hwdec: 'test', ended: false, mode: 'off', error: '', loading: false,
    buffering: false, tracks: [], aid: '', sid: '', speed: 1, volume: 75,
    generation: 1, fullscreen: false,
  };
  return {
    state: stateObj,
    native: { state: () => ({ stopped, leases }) },
    owner: { id: 'mock-owner' },
    addon: '/mock/addon.node',
    library: '/mock/libmpv.dylib',
    size: { width: 640, height: 360 },
    references: new Map(),
    receiverReady: true,
    volume: 75,
    available: () => true,
    ready: () => {},
    resize: () => {},
    setMode: async (mode) => { stateObj.mode = mode; return stateObj; },
    wait: async () => {},
    open: async (unused, source, mode, start = 0, title = '') => {
      running = true;
      stateObj.running = true;
      stateObj.position = start;
      stateObj.mode = mode;
      return { ...stateObj };
    },
    control: async (action, value) => {
      if (action === 'seek-to') stateObj.position = value;
      if (action === 'volume') stateObj.volume = value;
      return { ...stateObj };
    },
    stop: async () => {
      running = false;
      stateObj.running = false;
      stopped = true;
    },
  };
}

test('PlayerSession enforces mutual exclusion between video and audio sessions', async () => {
  const embedded = mockEmbeddedPlayer();
  const session = new PlayerSession({ embeddedPlayer: embedded });

  assert.equal(session.activeKind, 'none');

  // Start audio session
  await session.beginAudio({ mediaId: 101, title: '测试曲目 1', url: 'http://test/audio/1' });
  assert.equal(session.activeKind, 'audio');
  assert.equal(session.activeMedia.id, 101);
  assert.equal(session.sessionState().activeKind, 'audio');

  // Opening video automatically ends audio session
  const videoState = await session.openVideo(null, { url: 'http://test/video/1' }, 'off', 5, '测试视频');
  assert.equal(session.activeKind, 'video');
  assert.equal(session.activeMedia.title, '测试视频');
  assert.equal(videoState.sessionKind, 'video');
  assert.equal(embedded.state.running, true);

  // Starting audio automatically stops active video
  await session.beginAudio({ mediaId: 102, title: '测试曲目 2' });
  assert.equal(session.activeKind, 'audio');
  assert.equal(session.activeMedia.id, 102);
  assert.equal(embedded.state.running, false);

  // Stop audio
  session.stopAudio();
  assert.equal(session.activeKind, 'none');
  assert.equal(session.activeMedia, null);
});

test('PlayerSession delegates controls and exposes complete compatibility properties', async () => {
  const embedded = mockEmbeddedPlayer();
  const session = new PlayerSession({ embeddedPlayer: embedded });

  assert.equal(session.native.state().leases, 0);
  assert.equal(session.owner.id, 'mock-owner');
  assert.equal(session.addon, '/mock/addon.node');
  assert.equal(session.library, '/mock/libmpv.dylib');

  await session.open(null, { url: 'http://test/video/1' }, 'efficiency', 10, '高画质视频');
  assert.equal(session.state.position, 10);
  assert.equal(session.state.mode, 'efficiency');

  await session.control('seek-to', 25);
  assert.equal(session.state.position, 25);

  await session.control('volume', 90);
  assert.equal(session.state.volume, 90);

  await session.stop();
  assert.equal(session.activeKind, 'none');
  assert.equal(embedded.state.running, false);

  await session.openVideo(null, { url: 'http://test/video/2' }, 'off', 0, '视频2');
  assert.equal(session.activeKind, 'video');
  await session.stopAll();
  assert.equal(session.activeKind, 'none');
  assert.equal(embedded.state.running, false);
});

test('PlayerSession recovers cleanly when openVideo fails', async () => {
  const embedded = mockEmbeddedPlayer();
  embedded.open = async () => { throw new Error('网络连接中断'); };
  const session = new PlayerSession({ embeddedPlayer: embedded });

  session.beginAudio({ mediaId: 50 });
  assert.equal(session.activeKind, 'audio');

  await assert.rejects(session.openVideo(null, { url: 'http://test/bad' }, 'off'), /网络连接中断/);
  assert.equal(session.activeKind, 'none');
  assert.equal(session.activeMedia, null);
});
