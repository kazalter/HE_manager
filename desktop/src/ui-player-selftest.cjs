// Explicit diagnostics only: the real embedded player with synthetic server media.
const fs = require('node:fs/promises');
const path = require('node:path');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
module.exports = async ({ window, player, config, report, evaluate, wait, click, field, capture, key, output }) => {
  // Windows can mark capture-driven windows occluded. Keep diagnostic paints/timers running.
  window.webContents.setBackgroundThrottling(false);
  report.testScheduling = 'background-throttling-disabled-for-window-capture';
  await evaluate("localStorage.setItem('he_play_mode', 'stop')");
  await click('.he-media-card[data-media-id="' + config.videoId + '"]');
  await wait(() => evaluate('Number(document.querySelector(".desktop-video canvas")?.dataset.heVideoFrames) >= 5'), 'Native video did not draw');
  const owner = player.owner, generation = player.state.generation;
  async function moveToCanvas() {
    await evaluate('document.activeElement?.blur()');
    const point = await evaluate('(() => {const r=document.querySelector(".desktop-video canvas").getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)}})()');
    window.webContents.sendInputEvent({ type: 'mouseMove', ...point });
    await sleep(100);
  }
  await moveToCanvas();
  await click('.desktop-video button[aria-label="暂停"]');
  await wait(() => player.state.paused, 'Pause failed');
  await capture('controls-visible');
  for (const [width, height] of [[1024, 640], [1280, 800]]) {
    window.setContentSize(width, height); await sleep(400);
    const fits = await evaluate('(() => {const bar=document.querySelector(".player-control-row"), buttons=[...bar.querySelectorAll("button, select")];const r=bar.getBoundingClientRect();return buttons.every(b=>{const x=b.getBoundingClientRect();return x.left>=r.left-1&&x.right<=r.right+1})})()');
    if (!fits) throw new Error('Player controls overflow at ' + width);
    await capture('controls-' + width);
    report.layouts.push({ scene: 'player', width, height, controlsFit: fits });
  }
  await field('.player-volume input[type="range"]', 25);
  await wait(() => evaluate('!!document.querySelector(".desktop-video button[aria-label=静音]")'), 'Volume did not reach the UI');
  await click('.desktop-video button[aria-label="静音"]');
  await wait(async () => player.state.volume === 0 && await evaluate('!!document.querySelector(".desktop-video button[aria-label=取消静音]")'), 'Mute failed');
  await click('.desktop-video button[aria-label="取消静音"]');
  await wait(() => player.state.volume === 25, 'Mute restore failed');
  await field('.player-volume input[type="range"]', 0);
  await field('.desktop-video select[aria-label="播放速度"]', 1.5);
  await wait(() => player.state.speed === 1.5, 'Speed failed');
  await click('.desktop-video button[aria-label="播放设置"]');
  await field('.ui-modal select[aria-label="画面比例"]', 4 / 3);
  await wait(() => player.state.aspectRatio === 4 / 3, 'Aspect control failed');
  await sleep(2800);
  if (!await evaluate('document.querySelector(".desktop-video").dataset.controlsVisible === "true"')) throw new Error('Settings disappeared while active');
  await capture('settings');
  await field('.ui-modal select[aria-label="画面比例"]', 0);
  await evaluate('window.__hePlayerKeys=[];window.addEventListener("keydown",e=>window.__hePlayerKeys.push({key:e.key,target:e.target?.tagName,modal:!!e.target?.closest(".ui-modal")}),{capture:true});document.querySelector(".ui-modal-panel").focus()');
  await key('Escape');
  report.settingsExit = await evaluate('({keys:window.__hePlayerKeys,modal:!!document.querySelector(".ui-modal"),active:document.activeElement?.tagName,hidden:document.hidden})');
  await wait(() => evaluate('!document.querySelector(".ui-modal")'), 'Escape did not close playback settings');
  await field('.desktop-video select[aria-label="播放速度"]', 1);
  await moveToCanvas();
  await click('.desktop-video button[aria-label="全屏"]');
  await wait(() => window._heFullscreen, 'Fullscreen event missing');
  await wait(() => evaluate('!document.querySelector(".he-metadata-panel") && document.querySelector(".desktop-video").getBoundingClientRect().width > innerWidth - 2'), 'Fullscreen retained sidebar');
  await moveToCanvas();
  await sleep(2800);
  if (!await evaluate('document.querySelector(".desktop-video").dataset.controlsVisible === "true"')) throw new Error('Paused fullscreen controls hid');
  await capture('fullscreen-paused');
  await click('.desktop-video button[aria-label="播放"]');
  await moveToCanvas();
  await wait(() => evaluate('document.querySelector(".desktop-video").dataset.controlsVisible === "false"'), 'Idle fullscreen chrome did not hide');
  await sleep(300);
  const hidden = await evaluate('(() => {const e=document.querySelector(".player-controls"),h=document.querySelector(".he-viewer-header");return {controls:getComputedStyle(e).opacity,header:getComputedStyle(h).opacity,inert:e.inert,cursor:getComputedStyle(document.querySelector(".desktop-video canvas")).cursor}})()');
  if (hidden.controls !== '0' || hidden.header !== '0' || !hidden.inert || hidden.cursor !== 'none') throw new Error('Fullscreen chrome still visible: ' + JSON.stringify(hidden));
  report.hiddenChrome = hidden;
  await capture('fullscreen-hidden');
  await moveToCanvas();
  await wait(() => evaluate('document.querySelector(".desktop-video").dataset.controlsVisible === "true"'), 'Pointer did not reveal controls');
  await capture('fullscreen-revealed');
  await key('Escape');
  await wait(() => !window._heFullscreen, 'Escape did not exit fullscreen');
  await moveToCanvas();
  await click('.desktop-video button[aria-label="播放模式：播放完暂停"]');
  await field('.desktop-video input[type="range"]', 28);
  await wait(() => player.state.position > 27, 'Loop seek did not reach the end');
  await wait(() => player.state.position < 10 && !player.state.ended, 'Single-video loop did not restart', 6000);
  if (player.owner !== owner || player.state.generation !== generation) throw new Error('Loop/fullscreen recreated the native session');
  report.checks.playerLoopSameSession = true;
  await moveToCanvas();
  // Verify the screenshot is actually downloadable, with a deterministic diagnostic destination.
  const screenshotPath = path.join(path.dirname(output), path.basename(output, '.json') + '-saved-frame.png');
  const downloaded = new Promise((resolve, reject) => {
    window.webContents.session.once('will-download', (_event, item) => {
      item.setSavePath(screenshotPath);
      item.once('done', (_event, state) => state === 'completed' ? resolve() : reject(new Error('Screenshot download ' + state)));
    });
  });
  await click('.desktop-video button[aria-label="保存视频截图"]');
  await Promise.race([downloaded, sleep(5000).then(() => { throw new Error('Screenshot download timed out'); })]);
  const png = await fs.readFile(screenshotPath);
  if (png.subarray(1, 4).toString() !== 'PNG') throw new Error('Screenshot is not PNG');
  report.checks.screenshotDownload = true;
  report.checks.playerChrome = true;
  report.checks.playerControls = true;
  await key('Escape');
  await wait(() => !player.owner, 'Player did not release after closing');
  const closed = player.native.state(owner);
  if (!closed.stopped || closed.surfaces || closed.leases || player.references.size) throw new Error('Player retained resources');
  report.closedPlayer = { stopped: closed.stopped, surfaces: closed.surfaces, leases: closed.leases, references: player.references.size };
};
