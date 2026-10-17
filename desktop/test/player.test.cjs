const { test } = require("node:test"),
  assert = require("node:assert/strict");
const { Player } = require("../src/player.cjs");
test("mpv IPC reassembles fragmented messages and resolves matching requests", async () => {
  const player = new Player("/shaders");
  player.buffer = "";
  player.socket = {
    destroyed: false,
    write(line) {
      const req = JSON.parse(line);
      setImmediate(() => {
        player.receive(
          Buffer.from(
            JSON.stringify({
              request_id: req.request_id,
              error: "success",
              data: 123,
            }).slice(0, 10),
          ),
        );
        player.receive(
          Buffer.from(
            JSON.stringify({
              request_id: req.request_id,
              error: "success",
              data: 123,
            }).slice(10) + "\n",
          ),
        );
      });
    },
  };
  assert.equal(await player.command(["get_property", "duration"]), 123);
  player.receive(
    Buffer.from(
      JSON.stringify({ event: "property-change", name: "time-pos", data: 42 }) +
        "\n",
    ),
  );
  player.receive(
    Buffer.from(
      JSON.stringify({ event: "property-change", name: "pause", data: false }) +
        "\n",
    ),
  );
  assert.equal(player.state.position, 42);
  assert.equal(player.state.paused, false);
  await assert.rejects(player.control("run-shell-command", "evil"));
  await assert.rejects(player.control("seek", Infinity));
});

test("closing the previous player does not delete a newer IPC directory", async () => {
  const fs = require("node:fs/promises"),
    os = require("node:os"),
    path = require("node:path");
  const { EventEmitter } = require("node:events");
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "he-player-stop-test-"));
  const oldDirectory = path.join(root, "old"),
    nextDirectory = path.join(root, "next");
  await fs.mkdir(oldDirectory);
  await fs.mkdir(nextDirectory);
  const child = new EventEmitter();
  child.exitCode = null;
  child.kill = () => {
    setTimeout(() => {
      child.exitCode = 0;
      child.emit("exit", 0);
    }, 10);
    return true;
  };
  const player = new Player("/shaders");
  player.child = child;
  player.directory = oldDirectory;
  const stopping = player.stop();
  player.directory = nextDirectory;
  await stopping;
  await assert.rejects(fs.access(oldDirectory));
  await fs.access(nextDirectory);
  assert.equal(player.directory, nextDirectory);
  await fs.rm(root, { recursive: true, force: true });
});
