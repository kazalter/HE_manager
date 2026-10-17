const http = require("node:http"),
  fs = require("node:fs/promises"),
  path = require("node:path"),
  os = require("node:os");
const { ImageCache, dimensions } = require("./images.cjs");
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
module.exports = async ({ player, mpv, image, resources }) => {
  const report = {
    platform: process.platform,
    arch: process.arch,
    video: null,
    image: null,
  };
  const video = await fs.readFile(path.join(resources, "test", "sample.mp4")),
    png = await fs.readFile(path.join(resources, "test", "checkerboard.png"));
  const server = http.createServer((request, response) => {
    if (request.headers.authorization !== "Bearer he-selftest") {
      response.writeHead(401);
      response.end();
      return;
    }
    const isImage = request.url === "/stream/2",
      body = isImage ? png : video;
    const range = request.headers.range?.match(/^bytes=(\d+)-(\d*)$/);
    const start = range ? Number(range[1]) : 0,
      end =
        range && range[2]
          ? Math.min(Number(range[2]), body.length - 1)
          : body.length - 1;
    if (start > body.length - 1) {
      response.writeHead(416);
      response.end();
      return;
    }
    response.writeHead(range ? 206 : 200, {
      "Content-Type": isImage ? "image/png" : "video/mp4",
      "Accept-Ranges": "bytes",
      "Content-Length": end - start + 1,
      ...(range
        ? { "Content-Range": `bytes ${start}-${end}/${body.length}` }
        : {}),
    });
    response.end(body.subarray(start, end + 1));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}`;
  const source = (id) => ({
    url: base + "/stream/" + id,
    token: "he-selftest",
    headers: { Authorization: "Bearer he-selftest" },
  });
  const work = await fs.mkdtemp(path.join(os.tmpdir(), "he-native-test-"));
  try {
    if (mpv) {
      try {
        await player.open(
          mpv,
          source(1),
          "efficiency",
          0,
          "HE Manager · GPU 自检",
        );
        await delay(3500);
        const passes = await player.command(["get_property", "vo-passes"]);
        const shaders = JSON.stringify(passes).includes("Anime4K");
        const position = await player.command(["get_property", "time-pos"]);
        if (!shaders || position < 0.2)
          throw new Error("视频未渲染 Anime4K 着色器");
        report.video = {
          ok: true,
          position,
          shaders,
          droppedFrames: player.state.droppedFrames,
          hwdec: player.state.hwdec,
        };
        await player.setMode("off");
        if ((await player.command(["get_property", "glsl-shaders"])).length)
          throw new Error("无法切回原画");
      } catch (error) {
        report.video = { ok: false, error: error.message };
      } finally {
        await player.stop();
      }
    } else report.video = { ok: false, error: "mpv missing" };
    if (image) {
      try {
        const cache = new ImageCache(work),
          result = await cache.prepare(
            source(2),
            "anime",
            image,
            path.join(path.dirname(image), "models"),
          );
        const output = cache.file(
          new URL(result.url).pathname.split("/").pop(),
        );
        const [width, height] = dimensions(await fs.readFile(output));
        report.image = { ok: width === 256 && height === 256, width, height };
        const cached = await cache.prepare(
          source(2),
          "anime",
          image,
          path.join(path.dirname(image), "models"),
        );
        report.image.cacheHit = cached.cached;
      } catch (error) {
        report.image = { ok: false, error: error.message };
      }
    } else report.image = { ok: false, error: "image engine missing" };
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
    await fs.rm(work, { recursive: true, force: true });
  }
  return report;
};
