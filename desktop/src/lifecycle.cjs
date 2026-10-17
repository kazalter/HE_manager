// Drain native workers, then quit outside before-quit's event callback. A fallback
// prevents a cancelled/hung quit leaving a window with an aborted image queue.
function installShutdown(app, cleanup, options = {}) {
  let quitting = false;
  const schedule = options.schedule || setImmediate;
  const fallback =
    options.fallback ||
    ((callback) => {
      const timer = setTimeout(callback, 2000);
      timer.unref();
    });
  app.on("before-quit", (event) => {
    if (quitting) return;
    event.preventDefault();
    quitting = true;
    Promise.resolve()
      .then(cleanup)
      .catch(() => {})
      .finally(() => {
        fallback(() => app.exit(0));
        schedule(() => app.quit());
      });
  });
}
module.exports = { installShutdown };
