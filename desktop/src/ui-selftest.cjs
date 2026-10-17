// Explicit diagnostic mode: a disposable profile, real backend and synthetic media.
// Credentials are read privately by main; they never enter reports or arguments.
const fs = require('node:fs/promises');
const path = require('node:path');
const { app, nativeTheme } = require('electron');
const { createHash } = require('node:crypto');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
module.exports = async ({ window, player, config, output }) => {
  if (!output) throw new Error('Diagnostic output path is required');
  const report = { phase: 'CP-02', status: 'running', platform: process.platform, packaged: app.isPackaged, checks: {}, screenshots: [], layouts: [] };
  let stage = 'login';
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
    const file = `${path.basename(output, '.json')}-${name}.png`;
    await fs.writeFile(path.join(path.dirname(output), file), (await window.webContents.capturePage()).toPNG());
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
      const resized = window.getContentSize().join('x') !== `${width}x${height}`;
      window.setContentSize(width, height); await sleep(300);
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
    for (const name of ['main.cjs', 'embedded-player.cjs', 'preload.cjs', 'ui-selftest.cjs']) report.sourceSha256[name] = createHash('sha256').update(await fs.readFile(path.join(__dirname, name))).digest('hex');
    const root = path.resolve(__dirname, '..');
    report.version = app.getVersion(); report.electron = process.versions.electron;
    report.uiSha256 = await hashTree(path.join(root, 'ui'));
    report.nativeBuild = JSON.parse((await fs.readFile(path.join(root, 'native/build', `${process.platform}-${process.arch}`, 'build-info.json'), 'utf8')).replace(/^\uFEFF/, ''));
    report.nativeSha256 = createHash('sha256').update(await fs.readFile(player.addon)).digest('hex');
    report.librarySha256 = createHash('sha256').update(await fs.readFile(player.library)).digest('hex');
    await evaluate(`window.heDesktop.connect(${JSON.stringify(config.server)})`);
    report.checks.directConnectivity = true;
    await wait(() => evaluate(`!!document.querySelector('input[autocomplete="username"]')`), 'Login form missing');
    await field('input[autocomplete="username"]', config.username);
    await field('input[type="password"]', config.password);
    await click('.he-auth-view button[type="submit"]');
    await wait(() => evaluate('document.querySelectorAll(".he-media-card").length >= 4'), 'Authenticated library missing');
    report.checks.loginAndLibrary = true;
    stage = 'library-appearance';
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
    stage = 'empty-search';
    await field('input[placeholder="搜索标题、文件名…"]', 'HE-NO-SUCH-FIXTURE-RESULT');
    await wait(() => evaluate('document.querySelectorAll(".he-media-card").length === 0 && document.body.innerText.includes("没有找到匹配的媒体")'), 'Search did not show empty result');
    report.checks.emptySearch = true;
    await field('input[placeholder="搜索标题、文件名…"]', '');
    await wait(() => evaluate('document.querySelectorAll(".he-media-card").length >= 4'), 'Library did not recover');
    stage = 'embedded-video';
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
    await key('Escape');
    await wait(() => evaluate('!document.querySelector(".ui-modal") && !!document.querySelector(".desktop-video")'), 'Escape closed viewer instead of settings');
    if (!await evaluate('document.activeElement?.matches("button[aria-label=\"播放设置\"]")')) throw new Error('Playback settings did not restore keyboard focus');
    await key('Enter');
    await wait(() => evaluate('!!document.querySelector(".ui-modal")'), 'Keyboard did not reopen playback settings');
    await key('Tab');
    if (!await evaluate('!!document.activeElement?.closest(".ui-modal")')) throw new Error('Playback settings lost keyboard focus');
    await key('Escape');
    report.checks.keyboardSettings = true;
    await click('.desktop-video button[aria-label="暂停"]');
    await wait(() => player.state.paused, 'Pause input failed');
    const before = player.native.state(player.owner);
    for (let index = 0; index < 3; index++) {
      await wait(() => evaluate('!!document.querySelector(".desktop-video button[aria-label=\"全屏\"]")'), 'Fullscreen control did not return to its normal state');
      await click('.desktop-video button[aria-label="全屏"]');
      await wait(() => window._heFullscreen, 'Fullscreen event missing');
      await key('Escape');
      await wait(() => !window._heFullscreen, 'Escape did not leave fullscreen');
    }
    const after = player.native.state(player.owner);
    report.checks.sameSessionFullscreen = before.sourceLoads === after.sourceLoads && before.aid === after.aid && before.sid === after.sid && before.speed === after.speed && after.paused;
    if (!report.checks.sameSessionFullscreen) throw new Error('Fullscreen changed the playback session');
    report.video = { hwdec: after.hwdec, tracks: after.tracks, position: after.position, sourceLoads: after.sourceLoads, speed: after.speed };
    await captureSizes('video', 'dark');
    const closedOwner = player.owner;
    await key('Escape');
    await wait(() => !player.state.running && !player.owner, 'Closing viewer did not release the player');
    const closed = player.native.state(closedOwner);
    report.closedPlayer = { stopped: closed.stopped, surfaces: closed.surfaces, leases: closed.leases, references: player.references.size };
    if (!closed.stopped || closed.surfaces || closed.leases || player.references.size) throw new Error('Closing viewer retained native resources');
    report.checks.viewerClose = true;
    stage = 'reader';
    await click(`.he-media-card[data-media-id="${config.mangaId}"]`);
    await wait(() => evaluate('document.querySelector(".he-reader-canvas-page img")?.naturalWidth > 0'), 'Reader did not display its page');
    await click('button[title="双页跨页模式"]');
    await wait(() => evaluate('document.querySelectorAll(".he-reader-canvas-page img").length === 2'), 'Double-page reader did not display both pages');
    await capture('reader-double-dark-1024');
    await click('button[title="连续卷轴模式 (条漫)"]');
    await wait(() => evaluate('document.querySelector(".he-reader-page img")?.naturalWidth > 0'), 'Scroll reader did not display a page');
    await capture('reader-scroll-dark-1024');
    await click('button[title="单页模式"]');
    await click('button[aria-label="放大"]');
    if (!await evaluate('!document.querySelector("button[aria-label=\"缩小\"]").disabled')) throw new Error('Reader zoom did not change');
    await click('button[aria-label="适应屏幕"]');
    report.checks.readerModesAndZoom = true;
    await captureSizes('reader', 'dark');
    if (!await evaluate('!document.querySelector("select[aria-label=\"图片增强\"]").disabled')) throw new Error('Bundled image enhancement is unavailable');
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
    stage = 'video-error';
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
  } catch (error) {
    report.status = 'failed'; report.stage = stage; report.error = error.message;
    report.playback = player.state;
    report.windowMetrics = { size: window.getSize(), contentSize: window.getContentSize(), minimum: window.getMinimumSize(), viewport: await evaluate('({width:innerWidth,height:innerHeight})') };
    try { await capture('failure'); } catch {}
  }
  report.capturedAt = new Date().toISOString();
  nativeTheme.themeSource = 'system';
  await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n');
  console.log('HE_UI_SELFTEST ' + JSON.stringify({ status: report.status, stage: report.stage, output }));
  return report.status !== 'failed';
};
