const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('resize retains the last video image until a frame of the new size arrives', () => {
  let receiver, observer, bridge;
  const listeners = {}, sent = [], drawn = [], released = [];
  class Canvas {
    constructor() { this.width = 640; this.height = 360; this.isConnected = true; this.dataset = {}; this.rect = { width: 640, height: 360 }; }
    getBoundingClientRect() { return this.rect; }
    getContext() { return { drawImage: frame => drawn.push([frame.displayWidth, frame.displayHeight]) }; }
  }
  const canvas = new Canvas();
  const electron = {
    contextBridge: { exposeInMainWorld: (_name, api) => { bridge = api; } },
    ipcRenderer: { on: (name, cb) => { listeners[name] = cb; }, send: (...args) => sent.push(args) },
    sharedTexture: { setSharedTextureReceiver: cb => { receiver = cb; } },
  };
  class Observer { constructor(cb) { observer = cb; } observe() {} disconnect() {} }
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../src/preload.cjs'), 'utf8'), {
    require: () => electron, document: { getElementById: () => canvas }, HTMLCanvasElement: Canvas,
    ResizeObserver: Observer, devicePixelRatio: 1, Promise, Error, Number, String, Object,
  });
  bridge.mountVideoSurface('test');
  listeners['he:video-generation']({}, 1);
  observer();
  function send(width, height) {
    const frame = { displayWidth: width, displayHeight: height, close() { released.push('frame'); } };
    receiver({ importedSharedTexture: { getVideoFrame: () => frame, release() { released.push('texture'); } } }, { generation: 1 });
  }
  send(640, 360);
  canvas.rect = { width: 1920, height: 1080 };
  observer();
  send(640, 360); // still in flight from the old surface
  assert.deepEqual(drawn, [[640, 360]]);
  assert.equal(canvas.width, 640);
  send(1920, 1080);
  send(640, 360); // an older leased frame arrives late
  assert.deepEqual(drawn, [[640, 360], [1920, 1080]]);
  assert.equal(canvas.width, 1920);
  assert.equal(released.length, 8);
  assert.equal(sent.filter(([name]) => name === 'he:video-size').length, 2);
});
