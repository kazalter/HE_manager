const path = require('node:path');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const { wallpaperActivity } = require('./wallpaper-policy.cjs');

class Wallpaper {
  constructor({ BrowserWindow, screen, powerMonitor, root, platform = process.platform, spawnProcess = spawn }) {
    Object.assign(this, { BrowserWindow, screen, powerMonitor, root, platform, spawnProcess });
    this.window = null; this.helper = null; this.pauseWhenCovered = true;
    this.foreground = false; this.locked = false; this.asleep = false; this.pressed = false;
    this.operation = 0; this.playing = null;
    this.onLock = () => { this.locked = true; this.updateActivity(); };
    this.onUnlock = () => { this.locked = false; this.updateActivity(); };
    this.onSuspend = () => { this.asleep = true; this.updateActivity(); };
    this.onResume = () => { this.asleep = false; this.updateActivity(); };
    powerMonitor.on('lock-screen', this.onLock); powerMonitor.on('unlock-screen', this.onUnlock);
    powerMonitor.on('suspend', this.onSuspend); powerMonitor.on('resume', this.onResume);
  }
  state() { return { running: !!this.window && !this.window.isDestroyed(), modelId: this.modelId || '', pauseWhenCovered: this.pauseWhenCovered, playing: this.playing }; }
  updateActivity() {
    const activity = wallpaperActivity({ enabled: this.state().running, desktopForeground: this.foreground,
      pauseWhenCovered: this.pauseWhenCovered, sessionLocked: this.locked, displayAsleep: this.asleep });
    if (this.window && !this.window.isDestroyed()) this.window.webContents.send('he:wallpaper-activity', activity.animate);
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
    const bounds = this.screen.getPrimaryDisplay().bounds;
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
  async start(modelId, pauseWhenCovered) {
    if (this.platform !== 'win32') throw new Error('桌面壁纸仅支持 Windows');
    if (typeof modelId !== 'string' || !modelId || modelId.length > 256 || /[\u0000-\u001f]/.test(modelId)) throw new Error('请先选择皮肤');
    const operation = ++this.operation;
    await this.closeCurrent();
    if (operation !== this.operation) throw new Error('壁纸启动已取消');
    this.modelId = modelId; this.pauseWhenCovered = pauseWhenCovered !== false;
    const bounds = this.screen.getPrimaryDisplay().bounds;
    const owner = new this.BrowserWindow({ ...bounds, show: false, frame: false, focusable: false,
      skipTaskbar: true, backgroundColor: '#101014', webPreferences: {
        preload: path.join(__dirname, 'wallpaper-preload.cjs'), contextIsolation: true,
        nodeIntegration: false, sandbox: true, webSecurity: true, backgroundThrottling: false,
      } });
    this.window = owner; this.foreground = false; this.updateActivity();
    owner.setMenuBarVisibility(false); owner.webContents.setAudioMuted(true);
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
      const helper = this.spawnProcess(path.join(this.root, 'native/build/win32-x64/he_wallpaper.exe'),
        [handle, String(process.pid)], { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
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
      this.updateActivity();
      // The viewer loads the authenticated manifest asynchronously. Re-send
      // activity after mounting so a message emitted before its listener was
      // installed cannot leave a covered wallpaper animating indefinitely.
      this.activityTimer = setInterval(() => this.updateActivity(), 1000);
      this.activityTimer.unref();
      return this.state();
    } catch (error) { if (this.window === owner) await this.closeCurrent(); throw error; }
  }
  setPauseWhenCovered(value) { this.pauseWhenCovered = value === true; this.updateActivity(); return this.state(); }
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
    this.playing = playing;
  }
  async stop() { ++this.operation; return this.closeCurrent(); }
  async closeCurrent() {
    clearInterval(this.activityTimer); this.activityTimer = null;
    if (this.pendingModel) {
      const pending = this.pendingModel; this.pendingModel = null;
      clearTimeout(pending.timer); pending.reject(new Error('壁纸启动已取消'));
    }
    if (this.pressed) this.release(true); const owner = this.window; this.window = null;
    const helper = this.helper; this.helper = null;
    if (owner && !owner.isDestroyed()) owner.destroy();
    helper?.kill(); this.foreground = false; this.modelId = ''; this.playing = null;
    return this.state();
  }
}
module.exports = { Wallpaper };
