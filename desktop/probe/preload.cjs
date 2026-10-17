const { contextBridge, ipcRenderer, sharedTexture } = require('electron');
let displayed = 0;
let generation = 1;
let holdMilliseconds = 0;
let delayStarted = 0, delayFired = 0, delayContinued = 0;
ipcRenderer.on('probe:generation', (_event, value) => { generation = value; });
ipcRenderer.on('probe:hold', (_event, value) => { holdMilliseconds = Math.min(500, Math.max(0, Number(value) || 0)); });
sharedTexture.setSharedTextureReceiver(async ({ importedSharedTexture }, metadata) => {
  let frame;
  try {
    frame = importedSharedTexture.getVideoFrame();
    if (holdMilliseconds) {
      delayStarted++;
      await new Promise((resolve) => setTimeout(() => { delayFired++; resolve(); }, holdMilliseconds));
      delayContinued++;
    }
    const canvas = document.getElementById('video');
    if (!canvas || metadata.generation !== generation) return;
    if (canvas.width !== frame.displayWidth || canvas.height !== frame.displayHeight) {
      canvas.width = frame.displayWidth; canvas.height = frame.displayHeight;
    }
    const context = canvas.getContext('2d', { alpha: false });
    context.drawImage(frame, 0, 0);
    displayed++;
    ipcRenderer.send('probe:displayed', { frame: metadata.frame, generation: metadata.generation });
  } finally {
    frame?.close();
    importedSharedTexture.release();
  }
});
contextBridge.exposeInMainWorld('heProbe', {
  action: (action, value) => ipcRenderer.invoke('probe:action', action, value),
  state: () => ipcRenderer.invoke('probe:state'),
  diagnostics: () => ({ delayStarted, delayFired, delayContinued, visibility: document.visibilityState }),
  sample: () => {
    const canvas = document.getElementById('video');
    const preview = document.createElement('canvas'); preview.width = preview.height = 32;
    const context = preview.getContext('2d'); context.drawImage(canvas, 0, 0, 32, 32);
    const data = context.getImageData(0, 0, 32, 32).data;
    let min = 255, max = 0, sum = 0;
    for (let i = 0; i < data.length; i++) if (i % 4 !== 3) { min = Math.min(min, data[i]); max = Math.max(max, data[i]); sum += data[i]; }
    return { displayed, width: canvas.width, height: canvas.height, spread: max - min, mean: sum / (32 * 32 * 3) };
  },
  orientation: () => {
    const canvas = document.getElementById('video'), context = canvas.getContext('2d');
    const scale = Math.min(canvas.width / 640, canvas.height / 360);
    const left = (canvas.width - 640 * scale) / 2, top = (canvas.height - 360 * scale) / 2;
    const pixel = (x, y) => Array.from(context.getImageData(Math.round(left + x * scale), Math.round(top + y * scale), 1, 1).data).slice(0, 3);
    const upper = pixel(600, 18), lower = pixel(600, 342);
    return { upper, lower, upright: upper[0] > 150 && upper[1] < 100 && upper[2] < 100 && lower[2] > 150 && lower[0] < 100 && lower[1] < 100 };
  },
});
window.addEventListener('DOMContentLoaded', () => {
  new ResizeObserver(() => {
    const rectangle = document.querySelector('.stage').getBoundingClientRect();
    ipcRenderer.send('probe:resize', {
      width: Math.min(3840, Math.max(32, Math.round(rectangle.width * devicePixelRatio))),
      height: Math.min(2160, Math.max(32, Math.round(rectangle.height * devicePixelRatio))),
    });
  }).observe(document.querySelector('.stage'));
  ipcRenderer.send('probe:receiver-ready');
});
