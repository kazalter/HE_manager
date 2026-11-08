const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('heWallpaper', Object.freeze({
  report: (success) => ipcRenderer.send('he:wallpaper-model', success === true),
  reportPlayback: (playing) => ipcRenderer.send('he:wallpaper-playback', playing === true),
}));
ipcRenderer.on('he:wallpaper-activity', (_event, animate) => {
  window.postMessage({ type: 'he:wallpaper-activity', animate: animate === true }, location.origin);
});
ipcRenderer.on('he:wallpaper-pointer', (_event, pointer) => {
  window.postMessage({ type: 'he:wallpaper-pointer', pointer }, location.origin);
});
