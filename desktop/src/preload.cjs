const { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld(
  "heDesktop",
  Object.freeze({
    configuration: () => ipcRenderer.invoke("he:configuration"),
    connect: (server) => ipcRenderer.invoke("he:connect", server),
    chooseEngine: (kind) => ipcRenderer.invoke("he:choose-engine", kind),
    setPreferences: (value) => ipcRenderer.invoke("he:preferences", value),
    openVideo: (options) => ipcRenderer.invoke("he:video-open", options),
    controlVideo: (action, value) =>
      ipcRenderer.invoke("he:video-control", action, value),
    videoState: () => ipcRenderer.invoke("he:video-state"),
    stopVideo: () => ipcRenderer.invoke("he:video-stop"),
    enhanceImage: (options) => ipcRenderer.invoke("he:image", options),
  }),
);
