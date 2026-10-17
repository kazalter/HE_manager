const { test } = require("node:test");
const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { installShutdown } = require("../src/lifecycle.cjs");
test("quit drains workers before retrying and exits if the OS leaves the app alive", async () => {
  const app = new EventEmitter(),
    calls = [];
  let drain, fallback, retry;
  app.quit = () => {
    calls.push("quit");
    app.emit("before-quit", {
      preventDefault() {
        calls.push("prevented twice");
      },
    });
  };
  app.exit = (code) => calls.push(`exit:${code}`);
  installShutdown(
    app,
    () =>
      new Promise((resolve) => {
        calls.push("cleanup");
        drain = resolve;
      }),
    {
      schedule: (callback) => {
        retry = callback;
      },
      fallback: (callback) => {
        fallback = callback;
      },
    },
  );
  app.emit("before-quit", {
    preventDefault() {
      calls.push("prevented");
    },
  });
  await new Promise(setImmediate);
  assert.deepEqual(calls, ["prevented", "cleanup"]);
  drain();
  await new Promise(setImmediate);
  retry();
  assert.deepEqual(calls, ["prevented", "cleanup", "quit"]);
  fallback();
  assert.equal(calls.at(-1), "exit:0");
});
