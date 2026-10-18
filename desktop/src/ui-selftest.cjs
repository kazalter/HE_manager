// Explicit diagnostic mode: a disposable profile, real backend and synthetic media.
// Credentials are read privately by main; they never enter reports or arguments.
const fs = require('node:fs/promises');
const path = require('node:path');
const { app, nativeTheme } = require('electron');
const { createHash } = require('node:crypto');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
module.exports = async ({ window, player, session, config, output }) => {
  if (!output) throw new Error('Diagnostic output path is required');
  const report = { phase: config.phase || 'CP-05', status: 'running', platform: process.platform, packaged: app.isPackaged, checks: {}, screenshots: [], layouts: [] };
  let stage = 'login';
  const enterStage = (value) => { stage = value; console.log('HE_UI_STAGE ' + value); };
  const evaluate = (script) => window.webContents.executeJavaScript(script);
  async function wait(test, label, timeout = 15000) {
    const until = Date.now() + timeout;
    while (Date.now() < until) { if (await test()) return; await sleep(50); }
    throw new Error(label);
  }
  async function click(selector) {
    const point = await evaluate(`(() => {const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw new Error('Missing control');e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)};})()`);
    app.focus({ steal: true }); window.focus(); window.webContents.focus();
    await wait(() => window.isFocused(), 'Window did not focus');
    window.webContents.sendInputEvent({ type: 'mouseDown', button: 'left', clickCount: 1, ...point });
    window.webContents.sendInputEvent({ type: 'mouseUp', button: 'left', clickCount: 1, ...point });
    await sleep(100);
  }
  async function field(selector, value) {
    await evaluate(`(() => {const e=document.querySelector(${JSON.stringify(selector)}); const prototype=e.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(prototype,'value').set.call(e,${JSON.stringify(String(value))});e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await sleep(100);
  }
  async function key(keyCode) {
    app.focus({ steal: true }); window.focus(); window.webContents.focus();
    await wait(() => window.isFocused(), 'Window did not focus for keyboard input');
    window.webContents.sendInputEvent({ type: 'keyDown', keyCode });
    if (keyCode === 'Enter') window.webContents.sendInputEvent({ type: 'char', keyCode: '\r' });
    window.webContents.sendInputEvent({ type: 'keyUp', keyCode });
    await sleep(150);
  }
  async function capture(name) {
    // DOM state can lead the macOS compositor. Wait through a paint before capture.
    await Promise.race([evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))'), sleep(750)]);
    await sleep(250);
    const file = `${path.basename(output, '.json')}-${name}.png`;
    const page = await Promise.race([window.webContents.capturePage(), sleep(5000).then(() => { throw new Error('Window capture timed out'); })]);
    await fs.writeFile(path.join(path.dirname(output), file), page.toPNG());
    report.screenshots.push(file);
  }
  async function hashTree(directory) {
    const files = {};
    async function visit(relative) {
      const entries = await fs.readdir(path.join(directory, relative), { withFileTypes: true });
      for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
        const name = relative ? relative + '/' + entry.name : entry.name;
        if (entry.isDirectory()) await visit(name);
        else if (entry.isFile()) files[name] = createHash('sha256').update(await fs.readFile(path.join(directory, name))).digest('hex');
      }
    }
    await visit(''); return files;
  }
  async function appearance(mode) {
    await click('.he-desktop-toolbar button');
    await click(`[aria-label="外观模式"] button:nth-child(${mode === 'light' ? 1 : mode === 'dark' ? 2 : 3})`);
    if (mode !== 'system') await wait(() => evaluate(`document.documentElement.dataset.colorMode === '${mode}'`), 'Theme did not apply');
    await key('Escape');
    await wait(() => evaluate('!document.querySelector(".ui-modal")'), 'Settings did not close');
  }
  async function captureSizes(scene, mode) {
    for (const [width, height] of [[1280, 800], [1024, 640]]) {
      const previous = await evaluate('Number(document.querySelector(".desktop-video canvas")?.dataset.heVideoFrames) || 0');
      const beforeCanvas = scene === 'video' ? await evaluate(`(() => {const c=document.querySelector('.desktop-video canvas'), r=c.getBoundingClientRect();return {width:r.width,height:r.height,pixels:[c.width,c.height],frames:Number(c.dataset.heVideoFrames)||0,hidden:document.hidden};})()`) : null;
      const resized = window.getContentSize().join('x') !== `${width}x${height}`;
      window.setContentSize(width, height); await sleep(300);
      if (scene === 'video') {
        report.videoResizes ||= []; report.videoResizes.push({ width, height, previous, beforeCanvas, nativeBefore: player.native.state(player.owner), requested: { ...player.size } });
      }
      if (scene === 'video' && resized) await wait(() => evaluate(`Number(document.querySelector('.desktop-video canvas')?.dataset.heVideoFrames) > ${previous}`), 'Video did not redraw after resizing');
      const dimensions = await evaluate('({width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth+1})');
      if (dimensions.overflow) throw new Error(scene + ' overflows the window');
      report.layouts.push({ scene, mode, ...dimensions });
      await capture(`${scene}-${mode}-${width}`);
    }
  }
  try {
    await fs.mkdir(path.dirname(output), { recursive: true });
    report.sourceSha256 = {};
    for (const name of (await fs.readdir(__dirname)).filter(name => name.endsWith('.cjs')).sort()) report.sourceSha256[name] = createHash('sha256').update(await fs.readFile(path.join(__dirname, name))).digest('hex');
    const root = path.resolve(__dirname, '..');
    report.version = app.getVersion(); report.electron = process.versions.electron;
    report.uiSha256 = await hashTree(path.join(root, 'ui'));
    report.nativeBuild = JSON.parse((await fs.readFile(path.join(root, 'native/build', `${process.platform}-${process.arch}`, 'build-info.json'), 'utf8')).replace(/^\uFEFF/, ''));
    report.nativeSha256 = createHash('sha256').update(await fs.readFile(player.addon)).digest('hex');
    report.librarySha256 = createHash('sha256').update(await fs.readFile(player.library)).digest('hex');
    if (config.lifecycleStep === 'restore') {
      await wait(() => !!session.snapshot().user, 'Encrypted login did not restore', 120000);
    } else {
      await evaluate(`window.heDesktop.connect(${JSON.stringify(config.server)})`);
      report.checks.directConnectivity = true;
      await wait(() => evaluate(`!!document.querySelector('input[autocomplete="username"]')`), 'Login form missing');
      await field('input[autocomplete="username"]', config.username);
      await field('input[type="password"]', config.password);
      await click('.he-auth-view button[type="submit"]');
    }
    await wait(() => evaluate('document.querySelectorAll(".he-media-card").length >= 4'), 'Authenticated library missing', 120000);
    report.checks.loginAndLibrary = true;
    const authentication = session.snapshot();
    const credential = session.identity(authentication.generation).token;
    const encryptedFile = await fs.readFile(path.join(app.getPath('userData'), 'desktop-login.json'), 'utf8');
    const storedCredential = JSON.parse(encryptedFile);
    report.authentication = {
      persistent: authentication.persistent,
      noPageToken: await evaluate("!localStorage.getItem('he_manager_token')") && !JSON.stringify(authentication).includes(credential),
      encryptedFile: storedCredential.version === 2 && typeof storedCredential.encrypted === 'string' && !encryptedFile.includes(credential),
      systemRoundTrip: await session.store.load(session.server) === credential,
      scopedResources: await evaluate(`[...document.querySelectorAll('img[src]')].filter(img => ['thumbnails','stream','manga'].includes(new URL(img.src).pathname.split('/')[1])).every(img => new URL(img.src).searchParams.get('he_session') === ${JSON.stringify(authentication.generation)} && !new URL(img.src).searchParams.has('token'))`),
    };
    if (!Object.values(report.authentication).every(Boolean)) throw new Error('Desktop authentication integration failed');
    report.checks.desktopAuthentication = true;
    if (config.lifecycleStep) {
      await require('./ui-lifecycle-selftest.cjs')({ window, player, session, config, report, evaluate, wait, click, field, capture, enterStage });
      report.status = 'partial-pass';
    } else {
    await wait(() => evaluate(`!!document.querySelector('section[aria-label="继续观看"] button')`), 'Continue-watching fixture is missing; reseed the disposable test server before each run');
    report.checks.continueWatching = true;
    enterStage('library-appearance');
    window.setSize(800, 500);
    await wait(() => evaluate('innerWidth >= 1024 && innerHeight >= 640'), 'Minimum content area is too small');
    report.minimumContent = await evaluate('({width:innerWidth,height:innerHeight})');
    if (report.minimumContent.width !== 1024 || report.minimumContent.height !== 640) throw new Error('Minimum content area differs from the verified design');
    report.checks.minimumContent = true;
    for (const mode of ['light', 'dark']) {
      await appearance(mode);
      await captureSizes('library', mode);
    }
    report.checks.libraryAppearance = true;
    await appearance('system');
    for (const mode of ['light', 'dark']) {
      nativeTheme.themeSource = mode;
      await wait(() => evaluate(`document.documentElement.dataset.colorMode === '${mode}'`), 'Following system theme did not update');
    }
    nativeTheme.themeSource = 'system';
    report.checks.systemAppearance = true;
    await appearance('dark');
    enterStage('empty-search');
    await field('input[placeholder="搜索标题、文件名…"]', 'HE-NO-SUCH-FIXTURE-RESULT');
    await wait(() => evaluate('document.querySelectorAll(".he-media-card").length === 0 && document.body.innerText.includes("没有找到匹配的媒体")'), 'Search did not show empty result');
    report.checks.emptySearch = true;
    await field('input[placeholder="搜索标题、文件名…"]', '');
    await wait(() => evaluate('document.querySelectorAll(".he-media-card").length >= 4'), 'Library did not recover');
    enterStage('embedded-video');
    await click(`.he-media-card[data-media-id="${config.videoId}"]`);
    if (config.expectVideoLoading) {
      await wait(() => evaluate('document.querySelector(".desktop-video")?.innerText.includes("正在打开视频")'), 'Video loading feedback did not appear');
      await capture('video-loading');
      report.checks.videoLoading = true;
    }
    await wait(() => evaluate('Number(document.querySelector(".desktop-video canvas")?.dataset.heVideoFrames) >= 5'), 'Embedded video did not display frames');
    await wait(() => player.state.tracks.filter((track) => track.type === 'audio').length === 2, 'Audio track list missing');
    report.checks.embeddedVideo = true;
    await click('button[aria-label="播放设置"]');
    await wait(() => evaluate('!!document.querySelector(".ui-modal select")'), 'Playback settings missing');
    await wait(() => evaluate(`(() => { const fields=document.querySelectorAll('.ui-modal select');return fields[0]?.querySelector('option[value="2"]') && fields[1]?.querySelector('option[value="2"]'); })()`), 'Track options did not reach the settings UI');
    await field('.ui-modal select:nth-of-type(1)', 2);
    await evaluate(`(() => {const fields=document.querySelectorAll('.ui-modal select');fields[1].value='2';fields[1].dispatchEvent(new Event('change',{bubbles:true}));fields[2].value='1.25';fields[2].dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await wait(() => player.state.aid === '2' && player.state.sid === '2' && player.state.speed === 1.25, 'Track/speed choices did not apply');
    report.shaderModes = [];
    for (const mode of ['efficiency', 'quality', 'off']) {
      const frames = player.native.state(player.owner).renderedFrames;
      await evaluate(`(() => {const field=document.querySelectorAll('.ui-modal select')[3];field.value=${JSON.stringify(mode)};field.dispatchEvent(new Event('change',{bubbles:true}));})()`);
      const matches = (passes) => mode === 'off' ? !/Anime4K/i.test(passes)
        : mode === 'quality' ? /Restore-CNN-\(VL\)/i.test(passes)
          : /Restore-CNN-\(M\)/i.test(passes) && !/Restore-CNN-\(VL\)/i.test(passes);
      await wait(() => { const native = player.native.state(player.owner); return player.state.mode === mode && native.renderedFrames > frames + 2 && matches(native.passes); }, 'Video enhancement did not apply actual shader passes');
      const native = player.native.state(player.owner);
      report.shaderModes.push({ mode, passes: native.passes, sourceLoads: native.sourceLoads, hwdec: native.hwdec });
    }
    report.checks.videoEnhancement = true;
    enterStage('playback-keyboard');
    await key('Escape');
    await wait(() => evaluate('!document.querySelector(".ui-modal") && !!document.querySelector(".desktop-video")'), 'Escape closed viewer instead of settings');
    if (!await evaluate(`document.activeElement?.matches('button[aria-label="播放设置"]')`)) throw new Error('Playback settings did not restore keyboard focus');
    await key('Enter');
    await wait(() => evaluate('!!document.querySelector(".ui-modal")'), 'Keyboard did not reopen playback settings');
    await key('Tab');
    if (!await evaluate('!!document.activeElement?.closest(".ui-modal")')) throw new Error('Playback settings lost keyboard focus');
    await key('Escape');
    report.checks.keyboardSettings = true;
    const seekBefore = player.state.position, seekTarget = seekBefore < 12 ? 20 : 5;
    await field('.desktop-video input[type="range"]', seekTarget);
    await wait(() => Math.abs(player.state.position - seekTarget) < 0.2, 'Seeking through the playback slider failed');
    report.seek = { before: seekBefore, target: seekTarget, after: player.state.position };
    report.checks.seek = true;
    if (player.state.paused) {
      await wait(() => evaluate(`!!document.querySelector('.desktop-video button[aria-label="播放"]')`), 'Play control missing');
      await click('.desktop-video button[aria-label="播放"]');
      await wait(() => !player.state.paused, 'Play input failed');
    }
    const forwardBefore = player.state.position;
    await click('.desktop-video button[aria-label="前进十秒"]');
    await wait(() => player.state.position > forwardBefore + 3 || Math.abs(player.state.position - player.state.duration) < 1, 'Forward 10s did not seek forward');
    const rewindBefore = player.state.position;
    await click('.desktop-video button[aria-label="后退十秒"]');
    await wait(() => player.state.position < rewindBefore - 3 || player.state.position < 5, 'Rewind 10s did not seek backward');
    await wait(() => evaluate(`!!document.querySelector('.desktop-video button[aria-label="下一项"]')`), 'Next media button missing');
    await wait(() => evaluate(`!!document.querySelector('.desktop-video button[aria-label="上一项"]')`), 'Prev media button missing');
    await wait(() => evaluate(`!!document.querySelector('.desktop-video button[aria-label="暂停"]')`), 'Pause control missing');
    await click('.desktop-video button[aria-label="暂停"]');
    await wait(() => player.state.paused, 'Pause input failed');
    enterStage('video-fullscreen');
    const before = player.native.state(player.owner);
    if (Math.abs(before.position - seekTarget) > 1) throw new Error('Paused playback differs from the selected position');
    for (let index = 0; index < 3; index++) {
      await wait(() => evaluate(`!!document.querySelector('.desktop-video button[aria-label="全屏"]')`), 'Fullscreen control did not return to its normal state');
      await click('.desktop-video button[aria-label="全屏"]');
      await wait(() => window._heFullscreen, 'Fullscreen event missing');
      await key('Escape');
      await wait(() => !window._heFullscreen, 'Escape did not leave fullscreen');
    }
    const after = player.native.state(player.owner);
    report.checks.sameSessionFullscreen = before.sourceLoads === after.sourceLoads && before.aid === after.aid && before.sid === after.sid && before.speed === after.speed && after.paused && Math.abs(before.position - after.position) < 0.1 && before.position < before.duration - 3;
    if (!report.checks.sameSessionFullscreen) throw new Error('Fullscreen changed the playback session');
    report.video = { hwdec: after.hwdec, tracks: after.tracks, position: after.position, sourceLoads: after.sourceLoads, speed: after.speed, droppedFrames: player.state.droppedFrames || 0 };
    report.checks.videoControlsAndDroppedFrames = (player.state.droppedFrames || 0) <= 5;
    await captureSizes('video', 'dark');
    const closedOwner = player.owner;
    await key('Escape');
    await wait(() => !player.state.running && !player.owner, 'Closing viewer did not release the player');
    const closed = player.native.state(closedOwner);
    report.closedPlayer = { stopped: closed.stopped, surfaces: closed.surfaces, leases: closed.leases, references: player.references.size };
    if (!closed.stopped || closed.surfaces || closed.leases || player.references.size) throw new Error('Closing viewer retained native resources');
    report.checks.viewerClose = true;
    if (config.audioId) {
      enterStage('audio-playback');
      await click(`.he-media-card[data-media-id="${config.audioId}"]`);
      await wait(() => evaluate('!!document.querySelector(".he-audio-panel")'), 'Audio panel missing');
      await wait(() => evaluate('document.querySelectorAll(".he-audio-tracks button").length >= 2'), 'Audio tracks missing');
      await capture('audio-panel-dark');
      await wait(() => evaluate('!!document.querySelector(".he-audio-controls")'), 'Audio controls missing');
      if (await evaluate('!document.querySelector("audio") || document.querySelector("audio").paused')) {
        await click('.he-audio-controls button[aria-label="播放"]');
        await wait(() => evaluate('!document.querySelector("audio")?.paused'), 'Audio did not start playing');
      }
      await click('.he-audio-controls button[aria-label="下一首"]');
      await wait(() => evaluate('document.querySelector(".he-audio-tracks button[aria-current=\\"true\\"]")?.innerText.includes("02")'), 'Audio next track did not advance');
      await click('button[aria-label="收起播放器，继续播放"]');
      await wait(() => evaluate('!!document.querySelector(".he-mini-player")'), 'Mini player missing after minimize');
      await capture('audio-mini-player');
      const wasPlaying = await evaluate('!document.querySelector("audio")?.paused');
      if (wasPlaying) {
        await click('.he-mini-player button[aria-label="暂停音频"]');
        await wait(() => evaluate('document.querySelector("audio")?.paused'), 'Mini player pause failed');
        await click('.he-mini-player button[aria-label="播放音频"]');
        await wait(() => evaluate('!document.querySelector("audio")?.paused'), 'Mini player resume failed');
      }
      enterStage('session-mutual-exclusion');
      await click(`.he-media-card[data-media-id="${config.videoId}"]`);
      await wait(() => evaluate('Number(document.querySelector(".desktop-video canvas")?.dataset.heVideoFrames) >= 3'), 'Video did not start');
      await wait(() => evaluate('!document.querySelector(".he-audio-host") || !document.querySelector(".he-mini-player")'), 'Active audio was not stopped by opening video');
      await key('Escape');
      await wait(() => !player.state.running && !player.owner, 'Closing video did not release player');
      report.checks.audioPlaybackAndMiniPlayer = true;
      report.checks.playerSessionMutualExclusion = true;
    }
    enterStage('reader');
    await click(`.he-media-card[data-media-id="${config.mangaId}"]`);
    await wait(() => evaluate('document.querySelector(".he-reader-canvas-page img")?.naturalWidth > 0'), 'Reader did not display its page');
    await click('button[title="双页跨页模式"]');
    await wait(() => evaluate(`document.querySelector('button[title="双页跨页模式"]').getAttribute('aria-pressed') === 'true' && document.querySelectorAll('.he-reader-canvas-page img').length === 2 && [...document.querySelectorAll('.he-reader-canvas-page img')].every(img => img.complete && img.naturalWidth > 0)`), 'Double-page reader did not display both pages');
    report.checks.readerControlsFit = await evaluate(`(() => { const bar=document.querySelector('.he-manga-controls'), a=bar.getBoundingClientRect(), b=document.querySelector('.he-manga-zoom').getBoundingClientRect();const separate=a.right<=b.left || a.left>=b.right || a.bottom<=b.top || a.top>=b.bottom;return separate && bar.scrollWidth <= bar.clientWidth+1 && [...bar.querySelectorAll('[aria-label="阅读模式"] span')].every(label => label.getClientRects().length===1); })()`);
    if (!report.checks.readerControlsFit) throw new Error('Reader controls overflow or wrap inside a mode label');
    await capture('reader-double-dark-1024');
    await click('button[title="连续卷轴模式 (条漫)"]');
    await wait(() => evaluate(`document.querySelector('button[title="连续卷轴模式 (条漫)"]').getAttribute('aria-pressed') === 'true' && document.querySelector('.he-reader-page img')?.naturalWidth > 0`), 'Scroll reader did not display a page');
    await capture('reader-scroll-dark-1024');
    await click('button[title="单页模式"]');
    await click('button[aria-label="放大"]');
    if (!await evaluate(`!document.querySelector('button[aria-label="缩小"]').disabled`)) throw new Error('Reader zoom did not change');
    await click('button[aria-label="适应屏幕"]');
    report.checks.readerModesAndZoom = true;
    await captureSizes('reader', 'dark');
    enterStage('reader-enhancement');
    if (!await evaluate(`!document.querySelector('select[aria-label="图片增强"]').disabled`)) throw new Error('Bundled image enhancement is unavailable');
    await field('select[aria-label="图片增强"]', 'anime');
    await wait(() => evaluate('document.querySelector(".he-manga-reader").innerText.includes("排队或处理") || document.querySelector(".he-manga-reader img")?.src.includes("/__cache/")'), 'Enhancement feedback did not appear');
    report.checks.enhancementFeedback = true;
    await capture('reader-enhancement-feedback');
    await wait(() => evaluate('document.querySelector(".he-manga-reader img")?.src.includes("/__cache/") || /失败|无法|超时|中止/.test(document.querySelector(".he-manga-reader").innerText)'), 'Enhancement did not produce a terminal UI state', 45000);
    report.imageEnhanced = await evaluate('!!document.querySelector(".he-manga-reader img")?.src.includes("/__cache/")');
    await field('select[aria-label="图片增强"]', 'off');
    await click('button[aria-label="返回媒体列表"]');
    await wait(() => evaluate('!document.querySelector(".he-media-overlay")'), 'Reader did not close');
    await appearance('light');
    await click(`.he-media-card[data-media-id="${config.videoId}"]`);
    await wait(() => evaluate('Number(document.querySelector(".desktop-video canvas")?.dataset.heVideoFrames) >= 3'), 'Light video did not display');
    await captureSizes('video', 'light');
    await key('Escape');
    await wait(() => !player.owner, 'Light video did not release');
    await click(`.he-media-card[data-media-id="${config.mangaId}"]`);
    await wait(() => evaluate('document.querySelector(".he-reader-canvas-page img")?.naturalWidth > 0'), 'Light reader did not display');
    await captureSizes('reader', 'light');
    report.checks.readerOpened = true;
    await click('button[aria-label="返回媒体列表"]');
    enterStage('video-error');
    if (!config.errorVideoId) throw new Error('Unreadable media fixture is missing');
    await click(`.he-media-card[data-media-id="${config.errorVideoId}"]`);
    await wait(() => evaluate('document.querySelector(".desktop-video")?.innerText.includes("视频暂时无法播放")'), 'Unreadable video did not show an actionable error');
    await capture('video-error');
    await click('button[aria-label="重新打开视频"]');
    await wait(async () => await evaluate('document.querySelector(".desktop-video")?.innerText.includes("视频暂时无法播放")') && !player.owner, 'Retry did not settle with released resources');
    await click('button[aria-label="返回媒体列表"]');
    await wait(() => evaluate('!document.querySelector(".he-media-overlay")'), 'Error viewer could not return to library');
    report.checks.videoErrorAndRetry = true;
    report.status = 'partial-pass';
    }
  } catch (error) {
    report.status = 'failed'; report.stage = stage; report.error = error.message;
    report.playback = player.state;
    report.nativeFailure = player.owner ? player.native.state(player.owner) : null;
    if (!window.isDestroyed()) {
      report.canvasFailure = await evaluate(`(() => {const c=document.querySelector('.desktop-video canvas'), r=c?.getBoundingClientRect();return {exists:!!c,width:r?.width,height:r?.height,frames:Number(c?.dataset.heVideoFrames)||0,hidden:document.hidden};})()`);
      report.windowMetrics = { size: window.getSize(), contentSize: window.getContentSize(), minimum: window.getMinimumSize(), viewport: await evaluate('({width:innerWidth,height:innerHeight})') };
      try { await capture('failure'); } catch {}
    } else report.windowClosed = true;
  }
  report.httpRequests = session.diagnosticRequests;
  report.capturedAt = new Date().toISOString();
  nativeTheme.themeSource = 'system';
  await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n');
  console.log('HE_UI_SELFTEST ' + JSON.stringify({ status: report.status, stage: report.stage, output }));
  return report.status !== 'failed';
};
