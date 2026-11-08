const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('heWallpaper', Object.freeze({
  report: (success) => ipcRenderer.send('he:wallpaper-model', success === true),
}));
ipcRenderer.on('he:wallpaper-activity', (_event, animate) => {
  window.postMessage({ type: 'he:wallpaper-activity', animate: animate === true }, location.origin);
});
