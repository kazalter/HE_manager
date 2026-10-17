// Explicit diagnostic mode: a disposable profile, real backend and synthetic media.
// Credentials are read privately by main; they never enter reports or arguments.
const fs = require('node:fs/promises');
const path = require('node:path');
const { app } = require('electron');
const { createHash } = require('node:crypto');
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
module.exports = async ({ window, player, config, output }) => {
  if (!output) throw new Error('Diagnostic output path is required');
  const report = { phase: 'CP-02', status: 'running', platform: process.platform, packaged: app.isPackaged, checks: {}, screenshots: [] };
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
    app.focus({ steal: true }); window.focus();
    window.webContents.sendInputEvent({ type: 'keyDown', keyCode });
    window.webContents.sendInputEvent({ type: 'keyUp', keyCode });
    await sleep(150);
  }
  async function capture(name) {
    const file = `${path.basename(output, '.json')}-${name}.png`;
    await fs.writeFile(path.join(path.dirname(output), file), (await window.webContents.capturePage()).toPNG());
    report.screenshots.push(file);
  }
  try {
    await fs.mkdir(path.dirname(output), { recursive: true });
    report.sourceSha256 = {};
    for (const name of ['main.cjs', 'embedded-player.cjs', 'preload.cjs']) report.sourceSha256[name] = createHash('sha256').update(await fs.readFile(path.join(__dirname, name))).digest('hex');
    await wait(() => evaluate(`!!document.querySelector('input[autocomplete="username"]')`), 'Login form missing');
    await field('input[autocomplete="username"]', config.username);
    await field('input[type="password"]', config.password);
    await click('.he-auth-view button[type="submit"]');
    await wait(() => evaluate('document.querySelectorAll(".he-media-card").length >= 4'), 'Authenticated library missing');
    report.checks.loginAndLibrary = true;
    stage = 'library-appearance';
    for (const mode of ['light', 'dark']) {
      await click('.he-desktop-toolbar button');
      await click(`[aria-label="外观模式"] button:nth-child(${mode === 'light' ? 1 : 2})`);
      await wait(() => evaluate(`document.documentElement.dataset.colorMode === '${mode}'`), 'Theme did not apply');
      await key('Escape');
      await wait(() => evaluate('!document.querySelector(".ui-modal")'), 'Settings did not close');
      for (const [width, height] of [[1280, 800], [1024, 640]]) {
        window.setContentSize(width, height); await sleep(300);
        const dimensions = await evaluate('({width:innerWidth,height:innerHeight,overflow:document.documentElement.scrollWidth>innerWidth+1})');
        if (dimensions.overflow) throw new Error('Library overflows the window');
        await capture(`library-${mode}-${width}`);
      }
    }
    report.checks.libraryAppearance = true;
    stage = 'empty-search';
    await field('input[placeholder="搜索标题、文件名…"]', 'HE-NO-SUCH-FIXTURE-RESULT');
    await wait(() => evaluate('document.querySelectorAll(".he-media-card").length === 0'), 'Search did not show empty result');
    report.checks.emptySearch = true;
    await field('input[placeholder="搜索标题、文件名…"]', '');
    await wait(() => evaluate('document.querySelectorAll(".he-media-card").length >= 4'), 'Library did not recover');
    stage = 'embedded-video';
    // Card activation follows the same deep-link query used by normal media opening.
    await evaluate(`location.hash='#/?media=${config.videoId}'`);
    await wait(() => evaluate('Number(document.querySelector(".desktop-video canvas")?.dataset.heVideoFrames) >= 5'), 'Embedded video did not display frames');
    await wait(() => player.state.tracks.filter((track) => track.type === 'audio').length === 2, 'Audio track list missing');
    report.checks.embeddedVideo = true;
    await click('button[aria-label="播放设置"]');
    await wait(() => evaluate('!!document.querySelector(".ui-modal select")'), 'Playback settings missing');
    await field('.ui-modal select:nth-of-type(1)', 2);
    await evaluate(`(() => {const fields=document.querySelectorAll('.ui-modal select');fields[1].value='2';fields[1].dispatchEvent(new Event('change',{bubbles:true}));fields[2].value='1.25';fields[2].dispatchEvent(new Event('change',{bubbles:true}));})()`);
    await wait(() => player.state.aid === '2' && player.state.sid === '2' && player.state.speed === 1.25, 'Track/speed choices did not apply');
    await key('Escape');
    await wait(() => evaluate('!document.querySelector(".ui-modal") && !!document.querySelector(".desktop-video")'), 'Escape closed viewer instead of settings');
    await click('.desktop-video button[aria-label="暂停"]');
    await wait(() => player.state.paused, 'Pause input failed');
    const before = player.native.state(player.owner);
    await click('.desktop-video button[aria-label="全屏"]');
    await wait(() => window._heFullscreen, 'Fullscreen event missing');
    await key('Escape');
    await wait(() => !window._heFullscreen, 'Escape did not leave fullscreen');
    const after = player.native.state(player.owner);
    report.checks.sameSessionFullscreen = before.sourceLoads === after.sourceLoads && before.aid === after.aid && before.sid === after.sid && before.speed === after.speed && after.paused;
    if (!report.checks.sameSessionFullscreen) throw new Error('Fullscreen changed the playback session');
    report.video = { hwdec: after.hwdec, tracks: after.tracks, position: after.position, sourceLoads: after.sourceLoads, speed: after.speed };
    await capture('video-dark-1024');
    await key('Escape');
    await wait(() => !player.state.running && !player.owner, 'Closing viewer did not release the player');
    report.checks.viewerClose = true;
    stage = 'reader';
    await evaluate(`location.hash='#/?media=${config.mangaId}'`);
    await wait(() => evaluate('document.querySelector(".he-reader-canvas-page img")?.naturalWidth > 0'), 'Reader did not display its page');
    await sleep(600); await capture('reader-dark-1024');
    report.checks.readerOpened = true;
    report.status = 'partial-pass';
  } catch (error) {
    report.status = 'failed'; report.stage = stage; report.error = error.message;
    try { await capture('failure'); } catch {}
  }
  report.capturedAt = new Date().toISOString();
  await fs.writeFile(output, JSON.stringify(report, null, 2) + '\n');
  console.log('HE_UI_SELFTEST ' + JSON.stringify({ status: report.status, stage: report.stage, output }));
  return report.status !== 'failed';
};
