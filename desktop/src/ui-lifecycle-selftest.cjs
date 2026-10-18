const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { app } = require('electron');
module.exports = async ({ window, player, session, config, report, evaluate, wait, click, field, capture, enterStage }) => {
  const restoring = config.lifecycleStep === 'restore';
  if (!['close', 'restore'].includes(config.lifecycleStep)) throw new Error('Unknown lifecycle step');
  if (!process.env.HE_DESKTOP_TEST_PROFILE) throw new Error('Lifecycle test requires a marked disposable profile');
  const file = path.join(app.getPath('userData'), 'lifecycle-state.json');
  const previous = restoring ? JSON.parse(await fs.readFile(file, 'utf8')) : null;
  const generation = session.snapshot().generation, userId = session.snapshot().user.id;
  const target = restoring ? previous.position : 12;
  enterStage(restoring ? 'restored-login' : 'normal-close-progress');
  if (restoring) {
    report.checks.loginRestoredWithoutSubmission = previous.userId === userId && previous.authGeneration !== generation &&
      session.diagnosticRequests.some(request => request.path === '/auth/me') &&
      !session.diagnosticRequests.some(request => request.path === '/auth/login' || request.path === '/auth/bootstrap');
    if (!report.checks.loginRestoredWithoutSubmission) throw new Error('Login was not independently restored');
  } else {
    const reset = await session.request('/media/' + config.videoId, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ progress: 3, duration: 30 }) }, generation);
    if (!reset.ok) throw new Error('Could not reset the synthetic close fixture');
    await reset.body?.cancel();
  }
  await click(`.he-media-card[data-media-id="${config.videoId}"]`);
  await wait(() => evaluate('Number(document.querySelector(".desktop-video canvas")?.dataset.heVideoFrames) >= 3'), 'Lifecycle video did not display');
  if (!player.state.paused) {
    await wait(() => evaluate(`!!document.querySelector('.desktop-video button[aria-label="暂停"]')`), 'Pause control missing');
    await click('.desktop-video button[aria-label="暂停"]');
    await wait(() => player.state.paused, 'Lifecycle video did not pause');
  }
  if (restoring) {
    report.checks.videoRestoredAtSavedPosition = Math.abs(player.state.position - target) < 1;
    if (!report.checks.videoRestoredAtSavedPosition) throw new Error('Video did not restore saved position');
  } else {
    await field('.desktop-video input[type="range"]', target);
    await wait(() => Math.abs(player.state.position - target) < 0.2, 'Close test seek failed');
  }
  const before = await session.request('/media?limit=60&offset=0', {}, generation);
  const beforeMedia = (await before.json()).find(media => media.id === config.videoId);
  if (!restoring && Math.floor(beforeMedia.progress) === target) throw new Error('Close position was already persisted before the close hook');
  await capture(restoring ? 'restored-video' : 'before-normal-close');
  const owner = player.owner, started = Date.now();
  window.close();
  await wait(() => window.isDestroyed(), 'Normal window close did not finish', 15000);
  const after = await session.request('/media?limit=60&offset=0', {}, generation);
  const media = (await after.json()).find(media => media.id === config.videoId);
  const native = player.native.state(owner);
  report.checks.normalCloseSavedFinalPosition = media.progress === target;
  report.checks.normalCloseReleasedResources = !player.owner && native.stopped && !native.leases && !native.surfaces && !player.references.size;
  report.checks.normalCloseRetainedLogin = session.snapshot().persistent && session.snapshot().user?.id === userId;
  if (!report.checks.normalCloseSavedFinalPosition || !report.checks.normalCloseReleasedResources || !report.checks.normalCloseRetainedLogin) throw new Error('Normal-close acceptance failed');
  const saved = previous || { runId: randomUUID(), userId, authGeneration: generation, position: target, mediaId: config.videoId };
  if (!restoring) await fs.writeFile(file, JSON.stringify(saved), { mode: 0o600 });
  report.lifecycle = { step: config.lifecycleStep, runId: saved.runId, processId: process.pid,
    beforePosition: beforeMedia.progress, savedPosition: media.progress, duration: media.duration,
    closeMilliseconds: Date.now() - started, stopped: native.stopped, surfaces: native.surfaces, leases: native.leases,
    note: 'Normal window close hooks; diagnostic delays application quit until the report is written. Persistent profile is explicitly disposable.' };
};
