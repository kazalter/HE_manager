// Pure policy shared by the Windows wallpaper controller and its tests.
// Unknown foreground or locked session must never forward desktop input.
function wallpaperActivity({ enabled, desktopForeground, pauseWhenCovered, sessionLocked, displayAsleep }) {
  const active = enabled === true && sessionLocked !== true && displayAsleep !== true;
  const desktopActive = active && desktopForeground === true;
  return {
    animate: active && (pauseWhenCovered !== true || desktopActive),
    forwardInput: desktopActive,
  };
}

// A desktop icon or another shell control owns its click even when a model is
// visible under it. An unknown hit is treated as occupied rather than guessed.
function shouldForwardPointer(activity, shellHit) {
  return activity?.forwardInput === true && shellHit === 'background';
}

module.exports = { wallpaperActivity, shouldForwardPointer };
