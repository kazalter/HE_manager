const { test } = require("node:test"),
  assert = require("node:assert/strict"),
  fs = require("node:fs/promises"),
  path = require("node:path"),
  os = require("node:os");
const { ImageCache, dimensions, readLimited } = require("../src/images.cjs");
function png(width, height, animated = false) {
  const buffer = Buffer.alloc(animated ? 45 : 33);
  Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]).copy(buffer);
  buffer.writeUInt32BE(13, 8);
  buffer.write("IHDR", 12);
  buffer.writeUInt32BE(width, 16);
  buffer.writeUInt32BE(height, 20);
  if (animated) {
    buffer.writeUInt32BE(0, 33);
    buffer.write("acTL", 37);
  }
  return buffer;
}
test("image inspection rejects animation and unreasonable formats", () => {
  assert.deepEqual(dimensions(png(100, 200)), [100, 200, "png"]);
  assert.throws(() => dimensions(png(100, 200, true)));
  assert.throws(() => dimensions(Buffer.from("GIF89a")));
});
test("streaming input size limits apply even without Content-Length", async () => {
  await assert.rejects(readLimited(new Response(Buffer.alloc(100)), 50));
  await assert.rejects(
    readLimited(
      new Response("test", { headers: { "content-length": "999" } }),
      50,
    ),
  );
});
test("cache reauthorizes, isolates accounts and recovers after failed jobs", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "he-cache-test-"));
  try {
    const binary = path.join(directory, "engine");
    await fs.writeFile(binary, "test");
    let calls = 0,
      authorized = true,
      fail = false,
      source = png(10, 10);
    const cache = new ImageCache(path.join(directory, "cache"), {
      fetch: async () =>
        new Response(authorized ? source : "denied", {
          status: authorized ? 200 : 401,
          headers: { "content-type": "image/png" },
        }),
      run: async (_binary, args) => {
        calls++;
        if (fail) throw new Error("GPU unavailable");
        assert.equal(args[args.indexOf("-t") + 1], "256");
        const scale = Number(args[args.indexOf("-s") + 1]);
        await fs.writeFile(
          args[args.indexOf("-o") + 1],
          png(10 * scale, 10 * scale),
        );
      },
    });
    const request = {
      url: "https://server/stream/1",
      token: "account-a",
      headers: { Authorization: "Bearer account-a" },
    };
    const [first, duplicate] = await Promise.all([
      cache.prepare(request, "anime", binary, directory),
      cache.prepare(request, "anime", binary, directory),
    ]);
    assert.equal(first.url, duplicate.url);
    assert.equal(calls, 1);
    assert.equal(
      (await cache.prepare(request, "anime", binary, directory)).cached,
      true,
    );
    authorized = false;
    await assert.rejects(
      cache.prepare(request, "anime", binary, directory),
      /登录/,
    );
    authorized = true;
    const other = await cache.prepare(
      { ...request, token: "account-b" },
      "anime",
      binary,
      directory,
    );
    assert.notEqual(other.url, first.url);
    assert.equal(calls, 2);
    fail = true;
    await assert.rejects(cache.prepare(request, "photo", binary, directory));
    fail = false;
    const recovered = await cache.prepare(request, "photo", binary, directory);
    assert.equal(recovered.scale, 4);
    assert.throws(() => cache.file("../desktop-settings.json"));
    assert.throws(() => cache.file("a".repeat(64) + ".png"));
    source = png(20000, 20000);
    await assert.rejects(
      cache.prepare(request, "anime", binary, directory),
      /像素/,
    );
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test("closing the client terminates an in-flight image worker", async () => {
  const controller = new AbortController();
  const work = require("../src/images.cjs").run(
    process.execPath,
    ["-e", "setTimeout(() => {}, 10000)"],
    15000,
    controller.signal,
  );
  controller.abort();
  await assert.rejects(work, /关闭/);
});
