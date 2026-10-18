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

test("cancelPending terminates in-flight inference and discards queued jobs", async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "he-cancel-test-"));
  try {
    const binary = path.join(directory, "mock-engine");
    await fs.writeFile(binary, "mock");
    let runStarted = false;
    let abortPromiseResolve;
    const abortSeen = new Promise((resolve) => { abortPromiseResolve = resolve; });
    const cache = new ImageCache(path.join(directory, "cache"), {
      fetch: async () => new Response(png(16, 16), { status: 200, headers: { "content-type": "image/png" } }),
      run: async (_binary, _args, _timeout, signal) => {
        runStarted = true;
        return new Promise((resolve, reject) => {
          signal?.addEventListener("abort", () => {
            abortPromiseResolve();
            reject(signal.reason instanceof Error ? signal.reason : new Error("超分已取消"));
          });
        });
      },
    });

    const task = cache.prepare(
      { url: "https://server/stream/1", token: "tok", headers: {} },
      "anime",
      binary,
      directory,
    );

    // Wait until inference task starts
    for (let i = 0; i < 20 && !runStarted; i++) {
      await new Promise((r) => setTimeout(r, 10));
    }
    assert.equal(runStarted, true);

    // Cancel pending inference (e.g. video open)
    cache.cancelPending("视频播放已开始，已取消图片超分");
    await abortSeen;
    await assert.rejects(task, /视频播放已开始/);
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test("native realesrgan engine verifies 2x anime and 4x photo representation", async () => {
  const runtime = process.platform === "darwin"
    ? path.join(__dirname, "../resources/runtime/darwin/realesrgan")
    : process.platform === "win32"
      ? path.join(__dirname, "../resources/runtime/win32/realesrgan")
      : null;
  if (!runtime) return;
  const binary = path.join(runtime, process.platform === "win32" ? "realesrgan-ncnn-vulkan.exe" : "realesrgan-ncnn-vulkan");
  const models = path.join(runtime, "models");
  try {
    await fs.access(binary);
    await fs.access(models);
  } catch {
    // Skip if binaries not populated in test environment
    return;
  }

  const samplePngPath = path.join(__dirname, "../../frontend/public/app-icons/he-180.png");
  let samplePng;
  try {
    samplePng = await fs.readFile(samplePngPath);
  } catch {
    return;
  }

  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "he-real-engine-"));
  try {
    const cache = new ImageCache(path.join(directory, "cache"), {
      fetch: async () => new Response(samplePng, { status: 200, headers: { "content-type": "image/png" } }),
    });

    // 2x anime mode (180x180 -> 360x360)
    const animeResult = await cache.prepare(
      { url: "https://server/manga/1/page/0", token: "t1", headers: {} },
      "anime",
      binary,
      models,
    );
    assert.equal(animeResult.scale, 2);
    assert.match(animeResult.url, /^he:\/\/app\/__cache\/[a-f0-9]{64}\.png$/);
    const animeFile = cache.file(animeResult.url.replace("he://app/__cache/", ""));
    const animeBytes = await fs.readFile(animeFile);
    assert.deepEqual(dimensions(animeBytes), [360, 360, "png"]);

    // 4x photo mode (180x180 -> 720x720)
    const photoResult = await cache.prepare(
      { url: "https://server/manga/1/page/1", token: "t1", headers: {} },
      "photo",
      binary,
      models,
    );
    assert.equal(photoResult.scale, 4);
    const photoFile = cache.file(photoResult.url.replace("he://app/__cache/", ""));
    const photoBytes = await fs.readFile(photoFile);
    assert.deepEqual(dimensions(photoBytes), [720, 720, "png"]);

    // Verify cache eviction trim
    await cache.trim();
    assert.ok(cache.allowed.size >= 2);
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});

