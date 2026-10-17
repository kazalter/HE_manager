const path = require('node:path');
const fs = require('node:fs');
const { shaderFiles } = require('./policy.cjs');
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const idle = () => ({ running: false, paused: true, position: 0, duration: 0, droppedFrames: 0,
  hwdec: '', ended: false, mode: 'off', error: '', loading: false, buffering: false,
  tracks: [], aid: '', sid: '', speed: 1, volume: 75, generation: 0, fullscreen: false });

class EmbeddedPlayer {
  constructor({ root, sharedTexture, getWindow, native, platform = process.platform, arch = process.arch }) {
    this.root = root; this.sharedTexture = sharedTexture; this.getWindow = getWindow;
    this.native = native; this.platform = platform;
    this.addon = path.join(root, 'native/build', `${platform}-${arch}`, 'he_embedded.node');
    this.library = path.join(root, 'native/runtime', platform === 'darwin' ? 'darwin/libmpv.2.dylib' : 'win32/libmpv-2.dll');
    this.operation = Promise.resolve(); this.owner = null; this.snapshot = idle();
    this.references = new Map(); this.generation = 0; this.closing = true; this.pumping = false;
    this.receiverReady = false; this.size = { width: 640, height: 360 };
    this.intent = 0;
    this.volume = 75;
  }
  available() { return !!this.native || (fs.existsSync(this.addon) && fs.existsSync(this.library)); }
  get state() {
    if (!this.owner) return { ...this.snapshot };
    const current = this.native.state(this.owner);
    return { ...this.snapshot, running: !current.stopped && !this.closing, paused: current.paused,
      position: current.position, duration: current.duration, droppedFrames: current.droppedFrames,
      hwdec: current.hwdec, ended: current.ended, buffering: current.buffering,
      tracks: current.tracks || [], aid: current.aid, sid: current.sid, speed: current.speed,
      fullscreen: Boolean(this.getWindow()?._heFullscreen),
      error: this.snapshot.error || (current.error ? '播放器无法读取或显示此媒体，请重试。' : '') };
  }
  serialize(task) { const next = this.operation.catch(() => {}).then(task); this.operation = next; return next; }
  async wait(test, label, timeout = 12000) {
    const until = Date.now() + timeout;
    while (Date.now() < until) {
      if (this.owner && this.native.state(this.owner).error) throw new Error('播放器无法读取或显示此媒体，请检查文件与服务器连接。');
      if (this.closing) throw new Error('播放已取消。');
      if (test()) return;
      await delay(25);
    }
    throw new Error(label);
  }
  ready() { this.receiverReady = true; }
  resize(value) {
    if (!value || !Number.isInteger(value.width) || !Number.isInteger(value.height)
      || value.width < 32 || value.height < 32 || value.width > 3840 || value.height > 2160) return;
    this.size = { width: value.width, height: value.height };
    if (this.owner && !this.closing) this.native.resize(this.owner, value.width, value.height);
  }
  open(_unused, source, mode, start = 0) {
    const intent = ++this.intent;
    return this.serialize(async () => {
      if (intent !== this.intent) throw new Error('播放已取消。');
      await this.stopInternal();
      if (intent !== this.intent) throw new Error('播放已取消。');
      if (!this.available()) throw new Error('当前安装包缺少内嵌播放器运行库，请重新安装完整客户端。');
      if (!this.native) this.native = require(this.addon);
      this.snapshot = { ...idle(), volume: this.volume, loading: true, mode, generation: ++this.generation };
      this.closing = false;
      const window = this.getWindow();
      if (!window || window.isDestroyed()) throw new Error('播放窗口已关闭。');
      const gpu = window._heGpu || {};
      try {
        this.owner = this.native.create({ library: this.library, source: source.url,
          headers: source.token ? [`Authorization: Bearer ${source.token}`] : [],
          shaders: shaderFiles(mode, path.join(this.root, 'resources/shaders')),
          vendorId: gpu.vendorId || 0, deviceId: gpu.deviceId || 0 });
        this.native.resize(this.owner, this.size.width, this.size.height);
        window.webContents.send('he:video-generation', this.generation);
        this.timer = setInterval(() => { void this.pump(); }, 8);
        await this.wait(() => this.native.state(this.owner).duration > 0, '读取视频超时，请重试。');
        if (Number.isFinite(start) && start > 0) {
          const target = Math.min(start, Math.max(0, this.native.state(this.owner).duration - 0.1));
          this.native.send(this.owner, 'command', ['seek', String(target), 'absolute+exact']);
          await this.wait(() => Math.abs(this.native.state(this.owner).position - target) < 1, '恢复播放位置超时。');
        }
        this.native.send(this.owner, 'command', ['set', 'volume', String(this.snapshot.volume)]);
        this.snapshot.loading = false;
        return this.state;
      } catch (error) {
        this.snapshot.error = error.message; this.snapshot.loading = false;
        await this.stopInternal(); throw error;
      }
    });
  }
  async pump() {
    const window = this.getWindow();
    if (this.pumping || this.closing || !this.receiverReady || !window || window.isDestroyed()) return;
    const owner = this.owner, generation = this.generation;
    const frame = this.native.acquire(owner);
    if (!frame) return;
    this.pumping = true;
    let imported;
    try {
      imported = this.sharedTexture.importSharedTexture({ textureInfo: {
        codedSize: { width: frame.width, height: frame.height }, pixelFormat: 'bgra',
        handle: this.platform === 'win32' ? { ntHandle: frame.handle } : { ioSurface: frame.handle },
        timestamp: frame.frame * 1000,
      }, allReferencesReleased: () => {
        this.native.release(owner, frame.frame); this.references.delete(`${generation}:${frame.frame}`);
      } });
      this.references.set(`${generation}:${frame.frame}`, imported);
      await this.sharedTexture.sendSharedTexture({ frame: window.webContents.mainFrame, importedSharedTexture: imported }, { frame: frame.frame, generation });
    } catch {
      this.snapshot.error = '视频显示中断，请重新打开此媒体。';
      if (!imported) this.native.release(owner, frame.frame);
    } finally { imported?.release(); this.pumping = false; }
  }
  async setMode(mode) {
    const files = shaderFiles(mode, path.join(this.root, 'resources/shaders'));
    if (this.owner && !this.closing) this.native.send(this.owner, 'shaders', files);
    this.snapshot.mode = mode; return this.state;
  }
  async control(action, value) {
    if (!this.owner || this.closing) throw new Error('当前没有正在播放的媒体。');
    let command;
    if (action === 'pause') command = ['cycle', 'pause'];
    else if (action === 'seek' || action === 'seek-to') {
      if (!Number.isFinite(value)) throw new Error('无效的播放位置。');
      command = ['seek', String(action === 'seek-to' ? Math.min(Math.max(0, value), this.state.duration) : value), action === 'seek-to' ? 'absolute+exact' : 'relative+exact'];
    } else if (action === 'audio-track' || action === 'subtitle-track') {
      const type = action === 'audio-track' ? 'audio' : 'sub';
      if (!(type === 'sub' && value === 0) && !this.state.tracks.some((track) => track.type === type && track.id === value)) throw new Error('所选轨道已不可用。');
      command = ['set', type === 'audio' ? 'aid' : 'sid', value === 0 ? 'no' : String(value)];
    } else if (action === 'speed') {
      if (![0.5, 0.75, 1, 1.25, 1.5, 2].includes(value)) throw new Error('无效的播放速度。');
      command = ['set', 'speed', String(value)];
    } else if (action === 'volume') {
      if (!Number.isFinite(value) || value < 0 || value > 100) throw new Error('无效的音量。');
      this.volume = value; this.snapshot.volume = value; command = ['set', 'volume', String(value)];
    } else if (action === 'mode') return this.setMode(value);
    else if (action === 'fullscreen' || action === 'exit-fullscreen') {
      const window = this.getWindow();
      if (window && !window.isDestroyed()) window.setFullScreen(action === 'fullscreen' && !window.isFullScreen());
      return this.state;
    } else throw new Error('不支持的播放操作。');
    this.native.send(this.owner, 'command', command); return this.state;
  }
  async stopInternal() {
    this.closing = true; clearInterval(this.timer);
    if (!this.owner) return;
    const window = this.getWindow();
    if (window && !window.isDestroyed()) window.webContents.send('he:video-flush');
    const owner = this.owner;
    this.native.close(owner);
    // Cleanup must keep draining leases even after a playback error.
    const until = Date.now() + 5000;
    while ((!this.native.state(owner).stopped || this.references.size || this.pumping) && Date.now() < until) await delay(20);
    if (!this.native.state(owner).stopped || this.references.size || this.pumping) throw new Error('播放器资源释放超时，请退出并重新打开客户端。');
    this.snapshot = { ...this.state, running: false, loading: false };
    this.owner = null;
  }
  stop() {
    ++this.intent;
    this.closing = true; clearInterval(this.timer);
    if (this.owner) this.native.close(this.owner);
    return this.serialize(() => this.stopInternal());
  }
}
module.exports = { EmbeddedPlayer };
