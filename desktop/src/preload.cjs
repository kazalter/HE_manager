const { contextBridge, ipcRenderer, sharedTexture } = require("electron");
// Keep Electron's IPC method names and stack decoration out of product errors.
const invoke = (channel, ...args) => ipcRenderer.invoke(channel, ...args).catch((error) => {
  const message = String(error?.message || '').replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '');
  throw new Error(message || '操作失败，请重试。');
});
const closeHandlers = new Set();
ipcRenderer.on('he:before-close', (_event, nonce) => {
  if (typeof nonce !== 'string' || nonce.length > 128) return;
  Promise.allSettled([...closeHandlers].map(callback => Promise.resolve().then(callback)))
    .then(() => ipcRenderer.send('he:close-ready', nonce));
});
let videoCanvas = null, videoObserver = null, videoGeneration = 0;
function detachVideoSurface() {
  videoObserver?.disconnect(); videoObserver = null;
  if (videoCanvas) videoCanvas.width = videoCanvas.width;
  videoCanvas = null;
}
ipcRenderer.on('he:video-generation', (_event, value) => { videoGeneration = value; });
ipcRenderer.on('he:video-flush', () => {
  videoGeneration = 0;
  if (videoCanvas) videoCanvas.width = videoCanvas.width;
});
sharedTexture.setSharedTextureReceiver(({ importedSharedTexture }, metadata) => {
  let frame;
  try {
    frame = importedSharedTexture.getVideoFrame();
    if (!videoCanvas?.isConnected || metadata.generation !== videoGeneration) return;
    if (videoCanvas.width !== frame.displayWidth || videoCanvas.height !== frame.displayHeight) {
      videoCanvas.width = frame.displayWidth; videoCanvas.height = frame.displayHeight;
    }
    videoCanvas.getContext('2d', { alpha: false }).drawImage(frame, 0, 0);
    videoCanvas.dataset.heVideoFrames = String((Number(videoCanvas.dataset.heVideoFrames) || 0) + 1);
  } finally { frame?.close(); importedSharedTexture.release(); }
});
function mountVideoSurface(id) {
  if (typeof id !== 'string' || id.length > 128) throw new Error('无效的视频区域');
  const canvas = document.getElementById(id);
  if (!(canvas instanceof HTMLCanvasElement)) throw new Error('视频区域尚未就绪');
  detachVideoSurface(); videoCanvas = canvas;
  videoObserver = new ResizeObserver(() => {
    const rectangle = canvas.getBoundingClientRect();
    if (rectangle.width <= 0 || rectangle.height <= 0) return;
    ipcRenderer.send('he:video-size', {
      width: Math.min(3840, Math.max(32, Math.round(rectangle.width * devicePixelRatio))),
      height: Math.min(2160, Math.max(32, Math.round(rectangle.height * devicePixelRatio))),
    });
  });
  videoObserver.observe(canvas);
  ipcRenderer.send('he:video-ready');
}

contextBridge.exposeInMainWorld(
  "heDesktop",
  Object.freeze({
    configuration: () => invoke("he:configuration"),
    authentication: () => invoke('he:authentication'),
    login: (value) => invoke('he:login', value),
    logout: () => invoke('he:logout'),
    restoreLogin: () => invoke('he:restore-login'),
    retryProgress: () => invoke('he:retry-progress'),
    onBeforeClose: (callback) => {
      if (typeof callback !== 'function') throw new Error('无效的关闭监听器');
      closeHandlers.add(callback);
      return () => closeHandlers.delete(callback);
    },
    onSessionChanged: (callback) => {
      if (typeof callback !== 'function') throw new Error('无效的会话监听器');
      const listener = (_event, value) => callback(value);
      ipcRenderer.on('he:session-changed', listener);
      return () => ipcRenderer.removeListener('he:session-changed', listener);
    },
    connect: (server) => invoke("he:connect", server),
    chooseEngine: (kind) => invoke("he:choose-engine", kind),
    setPreferences: (value) => invoke("he:preferences", value),
    openVideo: (options) => invoke("he:video-open", options),
    controlVideo: (action, value) =>
      invoke("he:video-control", action, value),
    videoState: () => invoke("he:video-state"),
    mountVideoSurface,
    unmountVideoSurface: detachVideoSurface,
    stopVideo: (generation) => invoke("he:video-stop", generation),
    notifyAudioStart: (options) => invoke("he:audio-start", options),
    notifyAudioStop: () => invoke("he:audio-stop"),
    playerSessionState: () => invoke("he:player-session-state"),
    onPlayerSessionChanged: (callback) => {
      if (typeof callback !== 'function') throw new Error('无效的会话监听器');
      const listener = (_event, value) => callback(value);
      ipcRenderer.on('he:player-session-changed', listener);
      return () => ipcRenderer.removeListener('he:player-session-changed', listener);
    },
    enhanceImage: (options) => invoke("he:image", options),
  }),
);
