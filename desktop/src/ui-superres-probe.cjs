// Disposable-profile diagnostic using the synthetic video fixture, never user media.
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const { screen, app } = require('electron');
module.exports = async ({ window, player, config, report, evaluate, wait, click }) => {
  window.webContents.setBackgroundThrottling(false);
  await click(`.he-media-card[data-media-id="${config.videoId}"]`);
  await wait(() => evaluate('Number(document.querySelector(".desktop-video canvas")?.dataset.heVideoFrames) >= 5'), 'Video did not draw');
  await evaluate(`(() => {window.__heResizeTrace=[];const end=performance.now()+2500;function sample(){const c=document.querySelector('.desktop-video canvas');if(!c)return;const r=c.getBoundingClientRect();window.__heResizeTrace.push({time:performance.now(),width:c.width,height:c.height,boxWidth:r.width,boxHeight:r.height,fit:getComputedStyle(c).objectFit,frames:Number(c.dataset.heVideoFrames)||0});if(performance.now()<end)requestAnimationFrame(sample)}requestAnimationFrame(sample)})()`);
  await click('.desktop-video button[aria-label="全屏"]');
  await wait(() => window.isFullScreen() || window._heFullscreen, 'Fullscreen event missing');
  await wait(() => evaluate('document.querySelector(".desktop-video")?.getBoundingClientRect().width > innerWidth - 2'), 'Video did not fill fullscreen');
  const owner = player.owner;
  player.native.send(owner, 'command', ['set', 'loop-file', 'inf']);
  const gpuInfo = await app.getGPUInfo('basic');
  report.superResolutionEnvironment = { selectedGpu: window._heGpu, devices: gpuInfo.gpuDevice, display: screen.getDisplayMatching(window.getBounds()).size };
  report.fullscreenResize = await evaluate('window.__heResizeTrace');
  const results = {};
  for (const mode of config.superResolutionMode ? [config.superResolutionMode] : ['off', 'efficiency', 'quality']) {
    await evaluate(`window.heDesktop.setPreferences({videoMode:${JSON.stringify(mode)},imageMode:'off'})`);
    await sleep(1300);
    player.native.send(owner, 'command', ['set', 'pause', 'no']);
    await evaluate('document.activeElement?.blur()');
    const bounds = await evaluate(`(() => { const r=document.querySelector('.desktop-video canvas').getBoundingClientRect();return {x:Math.round(r.x+r.width/2),y:Math.round(r.y+r.height/2)} })()`);
    window.webContents.sendInputEvent({ type: 'mouseMove', ...bounds });
    await wait(() => evaluate('document.querySelector(".desktop-video").dataset.controlsVisible === "true"'), 'Controls did not reveal');
    const samples = [], before = player.native.state(owner);
    if (config.highFrequencyCapture) await sleep(2100);
    const sample = async count => {
      for (let i=0;i<count;i++) {
        const meta = await evaluate(`(() => {const e=document.querySelector('.desktop-video'); const c=e.querySelector('canvas'); const r=c.getBoundingClientRect();return {visible:e.dataset.controlsVisible,frames:Number(c.dataset.heVideoFrames)||0,width:c.width,height:c.height,boxWidth:r.width,boxHeight:r.height}})()`);
        const shot = await window.webContents.capturePage({x:bounds.x-16,y:bounds.y-16,width:32,height:32});
        const pixels = shot.toBitmap(); let total=0,max=0;
        for(let p=0;p<pixels.length;p+=4) { const v=(pixels[p]+pixels[p+1]+pixels[p+2])/3; total+=v; max=Math.max(max,v); }
        samples.push({t:Date.now(), ...meta, mean:total/(pixels.length/4), max});
        if (!config.highFrequencyCapture) await sleep(32);
      }
    };
    await sample(config.highFrequencyCapture ? 300 : 95);
    window.webContents.sendInputEvent({ type: 'mouseMove', x: bounds.x + 3, y: bounds.y + 3 });
    await sample(25);
    const after = player.native.state(owner);
    if (!samples.some(sample => sample.visible === 'false')) throw new Error(mode + ': controls did not hide during sampling');
    if (samples.at(-1).visible !== 'true') throw new Error(mode + ': controls did not reveal during sampling');
    if (after.renderedFrames - before.renderedFrames < 5) throw new Error(mode + ': video did not advance during sampling');
    results[mode] = {samples, before: {renderedFrames:before.renderedFrames,sourceLoads:before.sourceLoads,droppedFrames:before.droppedFrames}, after:{renderedFrames:after.renderedFrames,sourceLoads:after.sourceLoads,droppedFrames:after.droppedFrames,passes:after.passes}};
  }
  report.superResolutionProbe = results;
  await player.control('exit-fullscreen');
};
