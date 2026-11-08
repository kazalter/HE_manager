const test = require('node:test');
const assert = require('node:assert/strict');
const { wallpaperActivity, shouldForwardPointer } = require('../src/wallpaper-policy.cjs');

test('desktop is interactive, but another foreground application never receives forwarded input', () => {
  const desktop = wallpaperActivity({ enabled: true, desktopForeground: true, pauseWhenCovered: true });
  assert.deepEqual(desktop, { animate: true, forwardInput: true });
  assert.equal(shouldForwardPointer(desktop, 'background'), true);
  assert.equal(shouldForwardPointer(desktop, 'icon'), false);
  assert.equal(shouldForwardPointer(desktop, 'unknown'), false);
  const covered = wallpaperActivity({ enabled: true, desktopForeground: false, pauseWhenCovered: true });
  assert.deepEqual(covered, { animate: false, forwardInput: false });
});

test('continuing animation while covered never enables input; sleep and lock always pause', () => {
  assert.deepEqual(wallpaperActivity({ enabled: true, desktopForeground: false, pauseWhenCovered: false }), { animate: true, forwardInput: false });
  for (const state of [{ sessionLocked: true }, { displayAsleep: true }, { enabled: false }]) {
    assert.deepEqual(wallpaperActivity({ enabled: true, desktopForeground: true, ...state }), { animate: false, forwardInput: false });
  }
  assert.equal(shouldForwardPointer(wallpaperActivity({ enabled: true }), 'background'), false);
});
