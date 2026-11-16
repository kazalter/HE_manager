const path = require('node:path');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const { wallpaperActivity } = require('./wallpaper-policy.cjs');

class Wallpaper {
  constructor({ BrowserWindow, screen, powerMonitor, root, platform = process.platform, spawnProcess = spawn, onStateChange = null }) {
    Object.assign(this, { BrowserWindow, screen, powerMonitor, root, platform, spawnProcess, onStateChange });
    this.window = null; this.helper = null; this.handoff = null;
    this.pauseWhenCovered = true; this.muted = true; this.displayId = null; this.activeBounds = null;
    this.foreground = false; this.locked = false; this.asleep = false; this.pressed = false;
    this.operation = 0; this.playing = null; this.lastAnimate = null;
    this.onLock = () => { this.locked = true; this.updateActivity(); };
    this.onUnlock = () => { this.locked = false; this.updateActivity(); };
    this.onSuspend = () => { this.asleep = true; this.updateActivity(); };
    this.onResume = () => { this.asleep = false; this.updateActivity(); };
    powerMonitor.on('lock-screen', this.onLock); powerMonitor.on('unlock-screen', this.onUnlock);
    powerMonitor.on('suspend', this.onSuspend); powerMonitor.on('resume', this.onResume);
  }
  displays() {
    if (this.platform !== 'win32') return [];
    const primaryId = this.screen.getPrimaryDisplay().id;
    const all = typeof this.screen.getAllDisplays === 'function' ? this.screen.getAllDisplays() : [this.screen.getPrimaryDisplay()];
    return all.map((display, index) => ({
      id: display.id ?? index,
      label: display.label || `显示器 ${index + 1}`,
      width: display.bounds.width,
      height: display.bounds.height,
      primary: display.id === primaryId || (!display.id && index === 0),
      bounds: display.bounds,
    }));
  }
  resolveDisplay(displayId) {
    const primary = this.screen.getPrimaryDisplay();
    if (displayId == null || typeof this.screen.getAllDisplays !== 'function') return primary;
    return this.screen.getAllDisplays().find((item) => item.id === displayId) || primary;
  }
  state() {
    const active = (this.window && !this.window.isDestroyed()) ? this : (this.handoff?.window && !this.handoff.window.isDestroyed() ? this.handoff : null);
    return {
      running: !!active,
      modelId: active ? (active.modelId || '') : '',
      pauseWhenCovered: this.pauseWhenCovered,
      muted: this.muted,
      displayId: active ? (active.displayId ?? null) : this.displayId,
      playing: active ? (active.playing ?? null) : null,
    };
  }
  notifyChange() {
    try { this.onStateChange?.(this.state()); } catch {}
  }
  updateActivity(force = false) {
    const hasWindow = !!this.window && !this.window.isDestroyed();
    const activity = wallpaperActivity({ enabled: hasWindow, desktopForeground: this.foreground,
      pauseWhenCovered: this.pauseWhenCovered, sessionLocked: this.locked, displayAsleep: this.asleep });
    if (hasWindow && (force || activity.animate !== this.lastAnimate)) {
      this.window.webContents.send('he:wallpaper-activity', activity.animate);
      this.lastAnimate = activity.animate;
    }
    if (!activity.forwardInput && this.pressed) this.release(true);
    this.activity = activity;
  }
  release(cancel = false) {
    if (this.window && !this.window.isDestroyed() && this.lastPoint)
      this.window.webContents.send('he:wallpaper-pointer', { type: cancel ? 'cancel' : 'up', ...this.lastPoint });
    this.pressed = false;
  }
  parse(line, owner) {
    if (this.window !== owner || owner.isDestroyed()) return;
    const match = /^state ([01]) (-?\d+) (-?\d+) ([01]) ([01])$/.exec(line);
    if (!match) return;
    const foreground = match[1] === '1', down = match[4] === '1', allowed = match[5] === '1';
    if (foreground !== this.foreground) { this.foreground = foreground; this.updateActivity(); }
    const dip = this.screen.screenToDipPoint({ x: Number(match[2]), y: Number(match[3]) });
    const bounds = this.activeBounds || this.screen.getPrimaryDisplay().bounds;
    const point = { x: Math.round(dip.x - bounds.x), y: Math.round(dip.y - bounds.y) };
    const inside = point.x >= 0 && point.y >= 0 && point.x < bounds.width && point.y < bounds.height;
    if (this.activity?.forwardInput && inside && (this.pressed || allowed)) {
      this.lastPoint = point;
      if (down && !this.pressed && allowed) {
        owner.webContents.send('he:wallpaper-pointer', { type: 'down', ...point });
        this.pressed = true;
      } else if (!down && this.pressed) this.release();
      else if (down && this.pressed) owner.webContents.send('he:wallpaper-pointer', { type: 'move', ...point });
    } else if (this.pressed && (!down || !inside)) this.release(!inside);
  }
  disposeHandoff() {
    const old = this.handoff;
    this.handoff = null;
    if (!old) return;
    if (old.window && !old.window.isDestroyed()) old.window.destroy();
    old.helper?.kill();
  }
  restoreHandoff() {
    const old = this.handoff;
    if (!old) return false;
    this.handoff = null;
    if (!old.window || old.window.isDestroyed()) {
      old.helper?.kill();
      return false;
    }
    this.window = old.window;
    this.helper = old.helper;
    this.modelId = old.modelId;
    this.displayId = old.displayId;
    this.activeBounds = old.activeBounds;
    this.playing = old.playing;
    this.foreground = old.foreground;
    this.lastAnimate = null;
    this.window.webContents.setAudioMuted(this.muted);
    this.updateActivity(true);
    return true;
  }
  async start(modelId, optionsOrPause) {
    if (this.platform !== 'win32') throw new Error('桌面壁纸仅支持 Windows');
    if (typeof modelId !== 'string' || !modelId || modelId.length > 256 || /[\u0000-\u001f]/.test(modelId)) throw new Error('请先选择皮肤');
    const opts = typeof optionsOrPause === 'object' && optionsOrPause !== null ? optionsOrPause : { pauseWhenCovered: optionsOrPause };
    const operation = ++this.operation;
    if (this.pendingModel || !this.window || this.window.isDestroyed()) {
      await this.closeCurrent({ keepHandoff: true });
    } else {
      if (this.pressed) this.release(true);
      this.handoff = {
        window: this.window,
        helper: this.helper,
        modelId: this.modelId,
        displayId: this.displayId,
        activeBounds: this.activeBounds,
        playing: this.playing,
        foreground: this.foreground,
      };
      this.window = null; this.helper = null; this.playing = null; this.lastAnimate = null;
    }
    if (operation !== this.operation) throw new Error('壁纸启动已取消');
    this.modelId = modelId;
    if (typeof opts.pauseWhenCovered === 'boolean') this.pauseWhenCovered = opts.pauseWhenCovered;
    else if (opts.pauseWhenCovered !== undefined) this.pauseWhenCovered = opts.pauseWhenCovered !== false;
    if (typeof opts.muted === 'boolean') this.muted = opts.muted;
    const display = this.resolveDisplay(opts.displayId !== undefined ? opts.displayId : this.displayId);
    this.displayId = display.id ?? null;
    this.activeBounds = display.bounds;
    const owner = new this.BrowserWindow({
      ...display.bounds,
      show: false,
      frame: false,
      resizable: false,
      thickFrame: false,
      hasShadow: false,
      roundedCorners: false,
      minimizable: false,
      maximizable: false,
      focusable: false,
      skipTaskbar: true,
      backgroundColor: '#101014',
      webPreferences: {
        preload: path.join(__dirname, 'wallpaper-preload.cjs'),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        webSecurity: true,
        backgroundThrottling: false,
      },
    });
    this.window = owner; this.foreground = false; this.lastAnimate = null; this.updateActivity();
    owner.setMenuBarVisibility(false); owner.webContents.setAudioMuted(this.muted);
    owner.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    owner.webContents.on('will-navigate', (event, url) => { if (!url.startsWith('he://app/l2d/')) event.preventDefault(); });
    owner.on('closed', () => {
      if (this.window === owner) void this.stop();
    });
    const modelReady = new Promise((resolve, reject) => {
      const pending = { owner, resolve, reject, timer: null };
      pending.timer = setTimeout(() => {
        if (this.pendingModel === pending) this.pendingModel = null;
        reject(new Error('壁纸皮肤加载超时，请检查服务器连接'));
      }, 45000);
      this.pendingModel = pending;
    });
    // The viewer can report failure while the native host is still starting.
    // Attach a rejection handler immediately, then await the original promise.
    void modelReady.catch(() => {});
    try {
      const url = new URL('he://app/l2d/'); url.searchParams.set('wallpaper', '1'); url.searchParams.set('model', modelId);
      await owner.loadURL(url.toString());
      if (operation !== this.operation || this.window !== owner || owner.isDestroyed()) throw new Error('壁纸已关闭');
      const handle = owner.getNativeWindowHandle().readBigUInt64LE().toString();
      const args = [handle, String(process.pid)];
      if (this.handoff?.window && !this.handoff.window.isDestroyed() && this.handoff.displayId === this.displayId) {
        args.push(this.handoff.window.getNativeWindowHandle().readBigUInt64LE().toString());
      }
      const helper = this.spawnProcess(path.join(this.root, 'native/build/win32-x64/he_wallpaper.exe'),
        args, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
      this.helper = helper;
      const lines = readline.createInterface({ input: helper.stdout });
      await new Promise((resolve, reject) => {
        let ready = false;
        const timer = setTimeout(() => reject(new Error('连接 Windows 桌面超时')), 5000);
        lines.on('line', (line) => {
          if (line === 'ready' && !ready) { ready = true; clearTimeout(timer); resolve(); return; }
          if (ready) this.parse(line, owner);
        });
        helper.once('error', (error) => { clearTimeout(timer); reject(error); });
        helper.once('exit', (code) => {
          clearTimeout(timer);
          if (!ready) reject(new Error(operation !== this.operation ? '壁纸启动已取消' : `无法连接 Windows 桌面 (${code ?? '退出'})`));
          else if (this.window === owner) void this.stop();
        });
      });
      // Native reparenting can show the HWND without updating Electron's
      // visibility bookkeeping. Notify Electron after attachment so Chromium
      // produces frames for the non-activating wallpaper window.
      if (operation !== this.operation || this.window !== owner || owner.isDestroyed()) throw new Error('壁纸启动已取消');
      owner.showInactive();
      await modelReady;
      if (operation !== this.operation || this.window !== owner || owner.isDestroyed()) throw new Error('壁纸启动已取消');
      this.disposeHandoff();
      this.updateActivity(true);
      this.notifyChange();
      return this.state();
    } catch (error) {
      if (this.window === owner) {
        await this.closeCurrent({ keepHandoff: true });
        if (operation === this.operation && !this.restoreHandoff()) {
          this.notifyChange();
        }
      }
      throw error;
    }
  }
  setPauseWhenCovered(value) {
    this.pauseWhenCovered = value === true;
    this.updateActivity();
    const state = this.state();
    this.notifyChange();
    return state;
  }
  setMuted(value) {
    this.muted = value !== false;
    if (this.window && !this.window.isDestroyed()) this.window.webContents.setAudioMuted(this.muted);
    if (this.handoff?.window && !this.handoff.window.isDestroyed()) this.handoff.window.webContents.setAudioMuted(this.muted);
    const state = this.state();
    this.notifyChange();
    return state;
  }
  modelResult(event, success) {
    const pending = this.pendingModel;
    if (!pending || event.sender !== pending.owner.webContents || event.senderFrame !== pending.owner.webContents.mainFrame || typeof success !== 'boolean') return;
    this.pendingModel = null; clearTimeout(pending.timer);
    if (success) pending.resolve();
    else pending.reject(new Error('壁纸皮肤加载失败，请检查资源和服务器连接'));
  }
  playbackResult(event, playing) {
    const owner = this.window;
    if (!owner || owner.isDestroyed() || event.sender !== owner.webContents || event.senderFrame !== owner.webContents.mainFrame || typeof playing !== 'boolean') return;
    const changed = this.playing !== playing;
    this.playing = playing;
    if (changed) this.notifyChange();
  }
  async stop() { ++this.operation; return this.closeCurrent({ keepHandoff: false }); }
  async closeCurrent({ keepHandoff = false } = {}) {
    if (this.pendingModel) {
      const pending = this.pendingModel; this.pendingModel = null;
      clearTimeout(pending.timer); pending.reject(new Error('壁纸启动已取消'));
    }
    if (this.pressed) this.release(true);
    const owner = this.window; this.window = null;
    const helper = this.helper; this.helper = null;
    if (owner && !owner.isDestroyed()) owner.destroy();
    helper?.kill();
    this.foreground = false; this.modelId = ''; this.playing = null; this.lastAnimate = null;
    if (!keepHandoff) {
      this.disposeHandoff();
      this.notifyChange();
    }
    return this.state();
  }
}
module.exports = { Wallpaper };
