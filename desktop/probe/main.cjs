const { app, BrowserWindow, ipcMain, sharedTexture } = require('electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { pathToFileURL } = require('node:url');
const root = path.resolve(__dirname, '..');
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
app.setPath('userData', require('node:fs').mkdtempSync(path.join(require('node:os').tmpdir(), 'he-embedded-probe-')));
let window, native, session, timer, pumping = false, closing = false, suspendPump = false;
let generation = 1, launchOptions;
let exitReady = false, shutdownPromise;
let fullscreenActual = false;
const fullscreenEvents = [];
let receiverReady = false, displayedFrames = 0, menuInputs = 0, error = '', maxInFlight = 0;
const references = new Map();
const state = () => ({ ...native.state(session), displayedFrames, menuInputs, inFlight: references.size, maxInFlight, sessionGeneration: generation, error: error || native.state(session).error });
function trusted(event) {
  return window && !window.isDestroyed() && event.sender === window.webContents && event.senderFrame === window.webContents.mainFrame && event.senderFrame.url === pathToFileURL(path.join(__dirname, 'index.html')).href;
}
function action(action, value) {
  if (action === 'pause') native.send(session, 'command', ['cycle', 'pause']);
  else if (action === 'seek') native.send(session, 'command', ['seek', '1', 'relative+exact']);
  else if (action === 'mode') {
    const { shaderFiles } = require('../src/policy.cjs');
    native.send(session, 'shaders', shaderFiles(value, path.join(root, 'resources/shaders')));
  } else if (action === 'fullscreen') window.setFullScreen(!window.isFullScreen());
  else if (action === 'exit-fullscreen') window.setFullScreen(false);
  else if (action === 'menu-input') menuInputs++;
  else throw new Error('Unsupported probe action');
}
async function pump() {
  if (pumping || suspendPump || !receiverReady || closing || !window || window.isDestroyed()) return;
  const owner = session, epoch = generation;
  const frame = native.acquire(owner);
  if (!frame) return;
  pumping = true;
  let imported;
  try {
    imported = sharedTexture.importSharedTexture({
      textureInfo: {
        codedSize: { width: frame.width, height: frame.height }, pixelFormat: 'bgra',
        handle: process.platform === 'win32' ? { ntHandle: frame.handle } : { ioSurface: frame.handle },
        timestamp: frame.frame * 1000,
      },
      allReferencesReleased: () => { native.release(owner, frame.frame); references.delete(`${epoch}:${frame.frame}`); },
    });
    references.set(`${epoch}:${frame.frame}`, imported); maxInFlight = Math.max(maxInFlight, references.size);
    await sharedTexture.sendSharedTexture({ frame: window.webContents.mainFrame, importedSharedTexture: imported }, { frame: frame.frame, generation: epoch });
  } catch (failure) {
    error = `Texture transfer failed: ${failure.message}`;
    if (!imported) native.release(owner, frame.frame);
  } finally {
    imported?.release(); pumping = false;
  }
}
async function waitFor(test, description, timeout = 12000) {
  const until = Date.now() + timeout;
  while (Date.now() < until) {
    if (error || native.state(session).error) throw new Error(error || native.state(session).error);
    if (await test()) return;
    await delay(50);
  }
  throw new Error('Timed out: ' + description);
}
async function click(id) {
  const rectangle = await window.webContents.executeJavaScript(`(() => { const r=document.getElementById(${JSON.stringify(id)}).getBoundingClientRect(); return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}; })()`);
  // Native sendInputEvent requires the containing window to have focus.
  // Fullscreen transitions and interacting with the test runner can change it.
  app.focus({ steal: true }); window.focus(); window.webContents.focus();
  await waitFor(() => window.isFocused(), 'focus before native input');
  window.webContents.sendInputEvent({ type: 'mouseDown', button: 'left', clickCount: 1, ...rectangle });
  window.webContents.sendInputEvent({ type: 'mouseUp', button: 'left', clickCount: 1, ...rectangle });
}
async function stop() {
  closing = true; clearInterval(timer); native.close(session);
  await waitFor(() => native.state(session).stopped, 'native shutdown', 5000);
  await waitFor(() => references.size === 0, 'texture reference drain', 5000);
}
function shutdown() {
  if (shutdownPromise) return shutdownPromise;
  shutdownPromise = (async () => {
    let result;
    try {
      await stop();
      result = { status: 'passed', packaged: app.isPackaged, platform: process.platform, state: state() };
      if (!result.state.stopped || result.state.leases || result.state.surfaces) throw new Error('Resources did not drain');
    } catch (failure) { result = { status: 'failed', error: failure.message, state: state() }; }
    if (process.env.HE_PROBE_CLOSE_OUTPUT) {
      await fs.mkdir(path.dirname(process.env.HE_PROBE_CLOSE_OUTPUT), { recursive: true });
      await fs.writeFile(process.env.HE_PROBE_CLOSE_OUTPUT, JSON.stringify(result, null, 2) + '\n');
    }
    exitReady = true;
    if (result.status === 'failed') app.exit(1);
    else { if (window && !window.isDestroyed()) window.destroy(); app.quit(); }
  })().catch(() => app.exit(1));
  return shutdownPromise;
}
async function selftest(output) {
  const report = { phase: 'CP-01', status: 'running', platform: process.platform, arch: process.arch, checks: {} };
  try {
    const addon = path.join(root, 'native/build', `${process.platform}-${process.arch}`, 'he_embedded.node');
    report.artifact = {
      packaged: app.isPackaged, electron: process.versions.electron,
      sourceKind: /^https?:/.test(launchOptions.source) ? 'protected-http' : 'local-fixture',
      hasAuthorizationHeader: launchOptions.headers.some((header) => /^Authorization: Bearer /i.test(header)),
      runtimeWithinApp: !path.relative(root, launchOptions.library).startsWith('..'),
      files: {},
    };
    for (const file of [__filename, path.join(__dirname, 'preload.cjs'), addon, launchOptions.library])
      report.artifact.files[path.relative(root, file).split(path.sep).join('/')] = createHash('sha256').update(await fs.readFile(file)).digest('hex');
    report.artifact.nativeBuild = JSON.parse(await fs.readFile(path.join(path.dirname(addon), 'build-info.json'), 'utf8').then((text) => text.replace(/^\uFEFF/, '')));
    await waitFor(() => displayedFrames >= 5 && native.state(session).position > 0.3, 'actual video frames');
    report.checks.video = await window.webContents.executeJavaScript('window.heProbe.sample()');
    if (report.checks.video.spread < 40) throw new Error('Video image is blank or lacks the test pattern');
    if (configForTest.richFixture) {
      report.orientation = await window.webContents.executeJavaScript('window.heProbe.orientation()');
      report.checks.orientation = report.orientation.upright;
      if (!report.checks.orientation) throw new Error('Video orientation/color markers do not match the fixture');
    }
    await click('pause'); await waitFor(() => native.state(session).paused, 'DOM pause input');
    await click('menu-toggle');
    await waitFor(() => window.webContents.executeJavaScript('!document.getElementById("menu").hidden'), 'menu visible');
    await click('menu-action');
    await waitFor(() => menuInputs === 1, 'DOM menu input');
    report.checks.overlayInput = true;
    await click('menu-toggle');
    if (configForTest.richFixture) {
      native.send(session, 'command', ['set', 'aid', '2']);
      native.send(session, 'command', ['set', 'sid', '2']);
      native.send(session, 'command', ['set', 'speed', '1.25']);
      await waitFor(() => { const s = state(); return s.aid === '2' && s.sid === '2' && s.speed === 1.25; }, 'non-default tracks and speed');
    }
    const before = state();
    for (let i = 0; i < 3; i++) {
      await click('fullscreen'); await waitFor(() => fullscreenActual && window.isFullScreen(), 'enter fullscreen event');
      await delay(250);
      await click('fullscreen'); await waitFor(() => !fullscreenActual && !window.isFullScreen(), 'leave fullscreen event');
    }
    const afterFullscreen = state();
    report.checks.sameSessionFullscreen = afterFullscreen.sourceLoads === before.sourceLoads && afterFullscreen.paused && Math.abs(afterFullscreen.position - before.position) < 0.1 && afterFullscreen.aid === before.aid && afterFullscreen.sid === before.sid && afterFullscreen.speed === before.speed;
    report.fullscreenState = { before, after: afterFullscreen, richFixture: !!configForTest.richFixture };
    await click('seek'); await waitFor(() => native.state(session).position > before.position + 0.5, 'seek');
    report.seek = { before: before.position, after: native.state(session).position };
    report.checks.seek = report.seek.after > report.seek.before + 0.5;
    const shaderChecks = {};
    for (const mode of ['efficiency', 'quality', 'off']) {
      const oldFrame = native.state(session).renderedFrames;
      action('mode', mode);
      native.send(session, 'command', ['set', 'pause', 'no']);
      const expected = mode === 'off' ? (passes) => !/Anime4K/i.test(passes)
        : mode === 'quality' ? (passes) => /Restore-CNN-\(VL\)/i.test(passes)
          : (passes) => /Restore-CNN-\(M\)/i.test(passes) && !/Restore-CNN-\(VL\)/i.test(passes);
      await waitFor(() => native.state(session).renderedFrames > oldFrame + 2 && expected(native.state(session).passes), `${mode} actual shader passes`);
      native.send(session, 'command', ['set', 'pause', 'yes']);
      await waitFor(() => native.state(session).paused, 'pause after shader sample');
      const current = native.state(session);
      shaderChecks[mode] = { passes: current.passes, hasAnime4K: /Anime4K/i.test(current.passes), matched: expected(current.passes) };
    }
    report.checks.shaders = shaderChecks;
    suspendPump = true;
    native.send(session, 'command', ['set', 'pause', 'no']);
    await delay(1000);
    const stalled = state();
    report.consumerStall = { readyFrames: stalled.readyFrames, leases: stalled.leases, surfaces: stalled.surfaces };
    report.checks.completedFrameRetained = stalled.readyFrames >= 1 && stalled.surfaces <= 2;
    if (!report.checks.completedFrameRetained) throw new Error('No completed frame retained for a stalled consumer');
    suspendPump = false;
    const slowStart = displayedFrames;
    window.webContents.send('probe:hold', 250);
    native.send(session, 'command', ['set', 'pause', 'no']);
    await waitFor(() => displayedFrames >= slowStart + 3, 'slow consumer frames');
    const slow = state();
    report.slowConsumer = { delayMs: 250, maxInFlight, nativeLeases: slow.leases, nativeSurfaces: slow.surfaces,
      renderer: await window.webContents.executeJavaScript('window.heProbe.diagnostics()') };
    report.checks.slowConsumer = maxInFlight <= 2 && slow.leases <= 2 && slow.surfaces <= 2;
    window.webContents.send('probe:hold', 0);
    native.send(session, 'command', ['set', 'pause', 'yes']);
    await waitFor(() => native.state(session).paused, 'pause after slow consumer');
    const displayedBeforeMinimize = displayedFrames;
    window.minimize(); await delay(300); window.restore(); await delay(300);
    native.send(session, 'command', ['set', 'pause', 'no']);
    await waitFor(() => displayedFrames >= displayedBeforeMinimize + 3, 'frames after restore');
    report.checks.minimizeRestore = !window.isMinimized() && native.state(session).sourceLoads === before.sourceLoads;
    window.setContentSize(880, 640);
    const resizedFrames = displayedFrames;
    await waitFor(async () => {
      const sample = await window.webContents.executeJavaScript('window.heProbe.sample()');
      return displayedFrames >= resizedFrames + 3 && sample.width !== report.checks.video.width && sample.spread > 40;
    }, 'resized video region');
    report.resizedVideo = await window.webContents.executeJavaScript('window.heProbe.sample()');
    report.checks.resize = true;
    native.send(session, 'command', ['set', 'pause', 'yes']);
    await waitFor(() => native.state(session).paused, 'pause before resize');
    const pausedAt = native.state(session).position;
    window.setContentSize(940, 680);
    await waitFor(async () => {
      const sample = await window.webContents.executeJavaScript('window.heProbe.sample()');
      return sample.width !== report.resizedVideo.width && sample.spread > 40;
    }, 'paused frame resized');
    report.checks.pausedResize = native.state(session).paused && Math.abs(native.state(session).position - pausedAt) < 0.1;
    report.stateBeforeStop = state();
    await fs.mkdir(path.dirname(output), { recursive: true });
    await fs.writeFile(output.replace(/\.json$/i, '') + '.png', (await window.webContents.capturePage()).toPNG());
    await stop(); report.stateAfterStop = state();
    report.checks.boundedFrames = maxInFlight <= 2 && report.stateAfterStop.leases === 0 && report.stateAfterStop.surfaces === 0;
    report.checks.reopen = [];
    for (let index = 0; index < 3; index++) {
      generation++; closing = false; const seen = displayedFrames;
      session = native.create({ ...launchOptions, source: index % 2 === 0 && configForTest.secondSource ? configForTest.secondSource : launchOptions.source });
      native.send(session, 'command', ['set', 'loop-file', 'inf']);
      window.webContents.send('probe:generation', generation);
      timer = setInterval(() => { void pump(); }, 8);
      await waitFor(() => displayedFrames >= seen + 3 && native.state(session).position > 0.1, 'reopened media frames');
      const sample = await window.webContents.executeJavaScript('window.heProbe.sample()');
      await stop();
      const stopped = state();
      report.checks.reopen.push({ generation, spread: sample.spread, stopped });
      if (!stopped.stopped || stopped.leases || stopped.surfaces || sample.spread < 40) throw new Error('Reopened session did not render and release cleanly');
    }
    report.status = Object.entries(report.checks).filter(([key]) => !['video', 'shaders', 'reopen'].includes(key)).every(([, value]) => value === true) ? 'partial-pass' : 'failed';
    // Protected streams, packaging and the full final-shape matrix remain gates.
  } catch (failure) {
    report.status = 'failed'; report.error = failure.message; report.failureState = state();
    report.windowState = { fullscreenActual, fullscreen: window.isFullScreen(), minimized: window.isMinimized(),
      focused: window.isFocused(), bounds: window.getBounds(), events: fullscreenEvents };
    try { report.renderer = await window.webContents.executeJavaScript('window.heProbe.diagnostics()'); } catch {}
    native.close(session);
  }
  report.capturedAt = new Date().toISOString();
  await fs.mkdir(path.dirname(output), { recursive: true }); await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n');
  console.log('HE_EMBEDDED_PROBE ' + JSON.stringify({ status: report.status, output, error: report.error }));
  app.exit(report.status === 'failed' ? 1 : 0);
}
let configForTest = {};
app.whenReady().then(async () => {
  const config = process.env.HE_PROBE_CONFIG ? JSON.parse(await fs.readFile(process.env.HE_PROBE_CONFIG, 'utf8')) : {};
  if (!config.source) {
    const fixture = path.join(root, 'native/runtime/fixtures/acceptance.mkv');
    try { await fs.access(fixture); config.source = fixture; config.richFixture = true; } catch {}
  }
  configForTest = config;
  native = require(path.join(root, 'native/build', `${process.platform}-${process.arch}`, 'he_embedded.node'));
  const gpu = await app.getGPUInfo('complete'), active = gpu.gpuDevice?.find((device) => device.active) || {};
  launchOptions = {
    library: config.library || path.join(root, 'native/runtime', process.platform === 'darwin' ? 'darwin/libmpv.2.dylib' : 'win32/libmpv-2.dll'),
    source: config.source || path.join(root, 'resources/test/sample.mp4'),
    headers: config.headers || [], shaders: [], vendorId: active.vendorId || 0, deviceId: active.deviceId || 0,
  };
  session = native.create(launchOptions);
  if (process.env.HE_PROBE_OUTPUT) native.send(session, 'command', ['set', 'loop-file', 'inf']);
  ipcMain.handle('probe:state', (event) => { if (!trusted(event)) throw new Error('Untrusted frame'); return state(); });
  ipcMain.handle('probe:action', (event, name, value) => { if (!trusted(event)) throw new Error('Untrusted frame'); action(name, value); });
  ipcMain.on('probe:receiver-ready', (event) => { if (trusted(event)) receiverReady = true; });
  ipcMain.on('probe:displayed', (event, value) => { if (trusted(event) && value.generation === generation) displayedFrames++; });
  ipcMain.on('probe:resize', (event, value) => { if (trusted(event) && Number.isInteger(value.width) && Number.isInteger(value.height)) native.resize(session, value.width, value.height); });
  window = new BrowserWindow({ width: 1100, height: 760, minWidth: 640, minHeight: 480, title: 'HE Manager · 内嵌原型', webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, sandbox: true, nodeIntegration: false } });
  window.on('enter-full-screen', () => { fullscreenActual = true; fullscreenEvents.push({ event: 'enter', at: Date.now() }); });
  window.on('leave-full-screen', () => { fullscreenActual = false; fullscreenEvents.push({ event: 'leave', at: Date.now() }); });
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('will-navigate', (event) => event.preventDefault());
  window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  await window.loadFile(path.join(__dirname, 'index.html'));
  timer = setInterval(() => { void pump(); }, 8);
  window.on('close', (event) => { if (!exitReady) { event.preventDefault(); void shutdown(); } });
  if (process.env.HE_PROBE_OUTPUT) await selftest(process.env.HE_PROBE_OUTPUT);
  else if (process.env.HE_PROBE_CLOSE_OUTPUT) {
    await waitFor(() => displayedFrames >= 3, 'video before window close');
    window.close();
  }
}).catch((failure) => { console.error('HE_EMBEDDED_PROBE startup failed: ' + failure.message); app.exit(1); });
app.on('window-all-closed', () => app.quit());
app.on('before-quit', (event) => { if (session && !exitReady) { event.preventDefault(); void shutdown(); } });
if (process.env.HE_PROBE_OUTPUT || process.env.HE_PROBE_CLOSE_OUTPUT)
  setTimeout(() => { console.error('HE_EMBEDDED_PROBE deadline exceeded'); app.exit(1); }, 90000).unref();
