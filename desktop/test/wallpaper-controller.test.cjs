const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const { Wallpaper } = require('../src/wallpaper.cjs');

class FakeWindow extends EventEmitter {
  static all = [];
  constructor(options) {
    super(); this.options = options; this.destroyed = false; this.events = []; this.messages = [];
    this.webContents = new EventEmitter();
    this.webContents.mainFrame = {};
    this.webContents.send = (...args) => {
      this.messages.push(args);
      if (args[0] === 'he:wallpaper-pointer') this.events.push(args[1]);
    };
    this.webContents.setAudioMuted = (value) => { this.muted = value; };
    this.webContents.setWindowOpenHandler = () => {};
    FakeWindow.all.push(this);
  }
  setMenuBarVisibility() {}
  showInactive() { this.shownInactive = true; }
  loadURL(url) { this.url = url; return Promise.resolve(); }
  getNativeWindowHandle() { const b = Buffer.alloc(8); b.writeBigUInt64LE(123n); return b; }
  isDestroyed() { return this.destroyed; }
  destroy() { this.destroyed = true; this.emit('closed'); }
}
function fixture(modelSuccess = true) {
  FakeWindow.all = [];
  const children = [];
  let wallpaper;
  const spawnProcess = () => {
    const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    child.kill = () => { child.killed = true; child.emit('exit', 0); };
    children.push(child); setImmediate(() => {
      child.stdout.write('ready\n');
      const owner = wallpaper.window;
      if (owner && typeof modelSuccess === 'boolean') wallpaper.modelResult({ sender: owner.webContents, senderFrame: owner.webContents.mainFrame }, modelSuccess);
    });
    return child;
  };
  const screen = { getPrimaryDisplay: () => ({ bounds: { x: 0, y: 0, width: 1000, height: 800 } }), screenToDipPoint: (p) => p };
  const powerMonitor = new EventEmitter();
  wallpaper = new Wallpaper({ BrowserWindow: FakeWindow, screen, powerMonitor, root: '.', platform: 'win32', spawnProcess });
  return { wallpaper, powerMonitor, children };
}

test('wallpaper forwards background gestures only while desktop is active and releases on focus loss', async () => {
  const { wallpaper, powerMonitor, children } = fixture();
  await wallpaper.start('test_1', true);
  const owner = FakeWindow.all[0];
  assert.match(owner.url, /wallpaper=1&model=test_1/);
  assert.equal(owner.shownInactive, true);
  wallpaper.parse('state 1 250 300 1 0', owner); // shell icon
  assert.equal(owner.events.length, 0);
  wallpaper.parse('state 1 250 300 1 1', owner);
  wallpaper.parse('state 1 260 310 1 1', owner);
  assert.deepEqual(owner.events.map((event) => event.type), ['down', 'move']);
  wallpaper.parse('state 0 270 320 1 0', owner);
  assert.equal(owner.events.at(-1).type, 'cancel');
  assert.deepEqual(owner.messages.filter(([channel]) => channel === 'he:wallpaper-activity').at(-1), ['he:wallpaper-activity', false]);
  powerMonitor.emit('lock-screen');
  wallpaper.parse('state 1 250 300 1 1', owner);
  assert.equal(owner.events.filter((event) => event.type === 'down').length, 1);
  await wallpaper.stop();
  assert.equal(owner.destroyed, true);
  assert.equal(children[0].killed, true);
  assert.equal(wallpaper.state().running, false);
});

test('a desktop click is delivered without focusing the wallpaper window', async () => {
  const { wallpaper } = fixture();
  await wallpaper.start('test_1', true);
  const owner = FakeWindow.all[0];
  assert.equal(owner.options.focusable, false);
  wallpaper.parse('state 1 100 200 1 1', owner);
  wallpaper.parse('state 1 105 205 0 1', owner);
  assert.deepEqual(owner.events, [
    { type: 'down', x: 100, y: 200 },
    { type: 'up', x: 105, y: 205 },
  ]);
  await wallpaper.stop();
});

test('a failed model load is reported and the native host is stopped', async () => {
  const { wallpaper, children } = fixture(false);
  await assert.rejects(wallpaper.start('missing', true), /皮肤加载失败/);
  assert.equal(wallpaper.state().running, false);
  assert.equal(FakeWindow.all[0].destroyed, true);
  assert.equal(children[0].killed, true);
});

test('unexpected window destruction cancels a pending model load immediately', async () => {
  const { wallpaper, children } = fixture(null);
  const starting = wallpaper.start('pending', true);
  const rejected = assert.rejects(starting, /取消|关闭/);
  await new Promise((resolve) => setImmediate(resolve));
  FakeWindow.all[0].destroy();
  await rejected;
  assert.equal(wallpaper.state().running, false);
  assert.equal(children[0].killed, true);
});

test('only the wallpaper main frame can confirm a loaded model', async () => {
  const { wallpaper } = fixture(null);
  let settled = false;
  const starting = wallpaper.start('safe', true).then((value) => { settled = true; return value; });
  await new Promise((resolve) => setImmediate(resolve));
  const owner = FakeWindow.all[0];
  wallpaper.modelResult({ sender: {}, senderFrame: owner.webContents.mainFrame }, true);
  wallpaper.modelResult({ sender: owner.webContents, senderFrame: {} }, true);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(settled, false);
  wallpaper.modelResult({ sender: owner.webContents, senderFrame: owner.webContents.mainFrame }, true);
  await starting;
  assert.equal(settled, true);
  await wallpaper.stop();
});

test('playback state is accepted only from the current wallpaper renderer', async () => {
  const { wallpaper } = fixture();
  await wallpaper.start('test_1', true);
  const owner = FakeWindow.all[0];
  wallpaper.playbackResult({ sender: {}, senderFrame: owner.webContents.mainFrame }, true);
  assert.equal(wallpaper.state().playing, null);
  wallpaper.playbackResult({ sender: owner.webContents, senderFrame: owner.webContents.mainFrame }, true);
  assert.equal(wallpaper.state().playing, true);
  wallpaper.playbackResult({ sender: owner.webContents, senderFrame: owner.webContents.mainFrame }, false);
  assert.equal(wallpaper.state().playing, false);
  await wallpaper.stop();
  assert.equal(wallpaper.state().playing, null);
});

test('a cancelled loading window cannot replace or destroy a newer wallpaper', async () => {
  const { wallpaper } = fixture();
  let release;
  const original = FakeWindow.prototype.loadURL;
  FakeWindow.prototype.loadURL = function (url) {
    this.url = url;
    return FakeWindow.all.length === 1 ? new Promise((resolve) => { release = resolve; }) : Promise.resolve();
  };
  try {
    const first = wallpaper.start('first', true);
    await new Promise((resolve) => setImmediate(resolve));
    const second = wallpaper.start('second', true);
    await second;
    release();
    await assert.rejects(first, /关闭|取消/);
    assert.equal(wallpaper.state().modelId, 'second');
    assert.equal(wallpaper.state().running, true);
    await wallpaper.stop();
  } finally { FakeWindow.prototype.loadURL = original; }
});

test('wallpaper creates borderless non-resizable window and deduplicates unchanged activity messages', async () => {
  const { wallpaper } = fixture();
  await wallpaper.start('test_1', true);
  const owner = FakeWindow.all[0];
  assert.equal(owner.options.resizable, false);
  assert.equal(owner.options.thickFrame, false);
  assert.equal(owner.options.hasShadow, false);
  assert.equal(owner.options.roundedCorners, false);
  const before = owner.messages.filter(([c]) => c === 'he:wallpaper-activity').length;
  wallpaper.parse('state 0 10 10 0 0', owner);
  wallpaper.updateActivity();
  const after = owner.messages.filter(([c]) => c === 'he:wallpaper-activity').length;
  assert.equal(after, before);
  wallpaper.setMuted(false);
  assert.equal(owner.muted, false);
  assert.equal(wallpaper.state().muted, false);
  await wallpaper.stop();
});

test('switching wallpaper keeps previous window until replacement model is ready and restores on failure', async () => {
  FakeWindow.all = [];
  const children = [];
  const spawnArgs = [];
  let wallpaper;
  let autoReport = true;
  const spawnProcess = (_bin, args) => {
    spawnArgs.push(args);
    const child = new EventEmitter(); child.stdout = new PassThrough(); child.stderr = new PassThrough();
    child.kill = () => { child.killed = true; child.emit('exit', 0); };
    children.push(child); setImmediate(() => {
      child.stdout.write('ready\n');
      const owner = wallpaper.window;
      if (owner && autoReport) wallpaper.modelResult({ sender: owner.webContents, senderFrame: owner.webContents.mainFrame }, true);
    });
    return child;
  };
  const screen = { getPrimaryDisplay: () => ({ id: 1, bounds: { x: 0, y: 0, width: 1000, height: 800 } }), screenToDipPoint: (p) => p };
  const powerMonitor = new EventEmitter();
  wallpaper = new Wallpaper({ BrowserWindow: FakeWindow, screen, powerMonitor, root: '.', platform: 'win32', spawnProcess });

  await wallpaper.start('first', true);
  const firstWindow = FakeWindow.all[0];
  const firstChild = children[0];
  autoReport = false;
  const switching = wallpaper.start('second', true);
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(firstWindow.destroyed, false);
  assert.equal(firstChild.killed, undefined);
  assert.equal(spawnArgs[1][2], '123');
  const secondWindow = FakeWindow.all[1];
  wallpaper.modelResult({ sender: secondWindow.webContents, senderFrame: secondWindow.webContents.mainFrame }, true);
  await switching;
  assert.equal(firstWindow.destroyed, true);
  assert.equal(firstChild.killed, true);
  assert.equal(wallpaper.state().modelId, 'second');

  // Failing switch restores the previous running wallpaper.
  const failing = wallpaper.start('broken', true);
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));
  const thirdWindow = FakeWindow.all[2];
  wallpaper.modelResult({ sender: thirdWindow.webContents, senderFrame: thirdWindow.webContents.mainFrame }, false);
  await assert.rejects(failing, /皮肤加载失败/);
  assert.equal(thirdWindow.destroyed, true);
  assert.equal(secondWindow.destroyed, false);
  assert.equal(wallpaper.state().running, true);
  assert.equal(wallpaper.state().modelId, 'second');
  await wallpaper.stop();
});
