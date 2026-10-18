const fs = require("node:fs/promises"),
  path = require("node:path"),
  { createHash } = require("node:crypto"),
  { spawn } = require("node:child_process");
const hash = (value) => createHash("sha256").update(value).digest("hex");
function dimensions(buffer) {
  if (
    buffer.length >= 24 &&
    buffer.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
  ) {
    let offset = 8;
    while (offset + 12 <= buffer.length) {
      const size = buffer.readUInt32BE(offset),
        type = buffer.toString("ascii", offset + 4, offset + 8);
      if (type === "acTL") throw new Error("动态图保留原图");
      offset += size + 12;
      if (type === "IEND") break;
    }
    return [buffer.readUInt32BE(16), buffer.readUInt32BE(20), "png"];
  }
  if (buffer[0] === 255 && buffer[1] === 216) {
    let offset = 2;
    while (offset + 8 < buffer.length) {
      if (buffer[offset] !== 255) {
        offset++;
        continue;
      }
      const marker = buffer[offset + 1];
      offset += 2;
      if (marker === 0xd9 || marker === 0xda) break;
      if (
        marker === 0 ||
        marker === 0xff ||
        marker === 0xd8 ||
        (marker >= 0xd0 && marker <= 0xd7)
      )
        continue;
      const length = buffer.readUInt16BE(offset);
      if (length < 2 || offset + length > buffer.length) break;
      if (
        [
          0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd,
          0xce, 0xcf,
        ].includes(marker)
      )
        return [
          buffer.readUInt16BE(offset + 5),
          buffer.readUInt16BE(offset + 3),
          "jpg",
        ];
      offset += length;
    }
  }
  throw new Error("首版图片超分支持静态 JPG、PNG；当前格式继续显示原图");
}
async function readLimited(response, limit = 32 * 1024 * 1024) {
  if (Number(response.headers.get("content-length")) > limit) {
    await response.body?.cancel();
    throw new Error("图片文件过大，继续显示原图");
  }
  const chunks = [];
  let length = 0;
  for await (const chunk of response.body) {
    length += chunk.byteLength;
    if (length > limit) throw new Error("图片文件过大，继续显示原图");
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks);
}
function run(binary, args, timeout = 120000, signal) {
  return new Promise((resolve, reject) => {
    const errorForAbort = () => {
      if (signal?.reason instanceof Error && signal.reason.name !== "AbortError") {
        return signal.reason;
      }
      return new Error("客户端已关闭");
    };
    if (signal?.aborted) {
      reject(errorForAbort());
      return;
    }
    const child = spawn(binary, args, { stdio: "ignore", windowsHide: true });
    const abort = () => {
      child.kill("SIGKILL");
      reject(errorForAbort());
    };
    signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      reject(new Error("图片超分超时，继续显示原图"));
    }, timeout);
    child.once("error", () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      reject(new Error("图片超分引擎启动失败"));
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
      code === 0
        ? resolve()
        : reject(new Error("图片超分失败，请检查 GPU 驱动与模型文件"));
    });
  });
}
class ImageCache {
  constructor(directory, options = {}) {
    this.abort = new AbortController();
    this.directory = directory;
    this.fetch = options.fetch || fetch;
    this.run = options.run || run;
    this.jobs = new Map();
    this.controllers = new Map();
    this.tail = Promise.resolve();
    this.allowed = new Set();
  }
  cancelPending(reason = "视频播放已开始，已取消图片超分") {
    for (const controller of this.controllers.values()) {
      controller.abort(new Error(reason));
    }
    this.controllers.clear();
  }
  async prepare(source, mode, binary, models) {
    if (this.abort.signal.aborted)
      throw new Error("客户端正在退出，请重新打开后重试超分");
    if (!["anime", "photo"].includes(mode))
      throw new Error("未知的图片超分模式");
    if (this.jobs.size >= 8) throw new Error("超分队列已满，稍后重试");
    const timeout = AbortSignal.timeout(30000);
    let response, buffer;
    try {
      response = await this.fetch(source.url, {
        headers: source.headers,
        redirect: "error",
        signal: AbortSignal.any([timeout, this.abort.signal]),
      });
      if (!response.ok) {
        await response.body?.cancel();
        throw new Error(
          response.status === 401 ? "登录已过期，请重新登录" : "无法读取原图",
        );
      }
      if (!response.headers.get("content-type")?.startsWith("image/")) {
        await response.body?.cancel();
        throw new Error("此内容不是图片");
      }
      buffer = await readLimited(response);
    } catch (error) {
      if (this.abort.signal.aborted)
        throw new Error("客户端正在退出，请重新打开后重试超分");
      if (timeout.aborted || error.name === "TimeoutError")
        throw new Error("读取原图超时，当前显示原图，请稍后重试");
      if (error.name === "AbortError")
        throw new Error("读取原图已中止，当前显示原图，请重试");
      throw error;
    }
    const [width, height, extension] = dimensions(buffer),
      scale = mode === "anime" ? 2 : 4;
    if (
      !width ||
      !height ||
      width > 20000 ||
      height > 20000 ||
      width * height * scale * scale > 40_000_000
    )
      throw new Error("放大后超过 4000 万像素，继续显示原图");
    const model =
        mode === "anime" ? "realesr-animevideov3" : "realesrgan-x4plus",
      stat = await fs.stat(binary);
    const id = hash(
      source.url +
        "\0" +
        hash(source.token) +
        "\0" +
        hash(buffer) +
        "\0" +
        model +
        "\0" +
        stat.size +
        ":" +
        stat.mtimeMs,
    );
    const output = path.join(this.directory, id + ".png");
    await fs.mkdir(this.directory, { recursive: true, mode: 0o700 });
    try {
      await fs.access(output);
      this.allowed.add(id);
      return { url: `he://app/__cache/${id}.png`, cached: true, scale };
    } catch {}
    if (!this.jobs.has(id)) {
      const jobController = new AbortController();
      this.controllers.set(id, jobController);
      const jobSignal = AbortSignal.any([this.abort.signal, jobController.signal]);
      const task = this.tail
        .catch(() => {})
        .then(async () => {
          if (jobSignal.aborted) {
            const err = jobSignal.reason instanceof Error && jobSignal.reason.name !== "AbortError"
              ? jobSignal.reason
              : new Error("客户端已关闭");
            throw err;
          }
          const work = await fs.mkdtemp(path.join(this.directory, "work-"));
          try {
            const input = path.join(work, "input." + extension),
              temporary = path.join(work, "output.png");
            await fs.writeFile(input, buffer, { mode: 0o600 });
            await this.run(
              binary,
              [
                "-i",
                input,
                "-o",
                temporary,
                "-m",
                models,
                "-n",
                model,
                "-s",
                String(scale),
                "-t",
                "256",
                "-j",
                "1:1:1",
                "-f",
                "png",
              ],
              120000,
              jobSignal,
            );
            const [outWidth, outHeight] = dimensions(
              await fs.readFile(temporary),
            );
            if (outWidth !== width * scale || outHeight !== height * scale)
              throw new Error("超分输出尺寸不符合预期，保留原图");
            await fs.rename(temporary, output);
            this.allowed.add(id);
            await this.trim();
          } finally {
            await fs.rm(work, { recursive: true, force: true });
          }
        });
      this.tail = task;
      this.jobs.set(id, task);
      task
        .finally(() => {
          this.jobs.delete(id);
          this.controllers.delete(id);
        })
        .catch(() => {});
    }
    await this.jobs.get(id);
    return { url: `he://app/__cache/${id}.png`, cached: false, scale };
  }
  async close() {
    this.abort.abort(new Error("客户端正在退出，请重新打开后重试超分"));
    this.cancelPending("客户端正在退出，请重新打开后重试超分");
    await this.tail.catch(() => {});
  }
  async trim() {
    const entries = await fs.readdir(this.directory);
    const files = await Promise.all(
      entries
        .filter((name) => /^[a-f0-9]{64}\.png$/.test(name))
        .map(async (name) => ({
          name,
          ...(await fs.stat(path.join(this.directory, name))),
        })),
    );
    let total = files.reduce((sum, file) => sum + file.size, 0);
    for (const file of files.sort((a, b) => a.mtimeMs - b.mtimeMs)) {
      if (total <= 1024 ** 3) break;
      await fs.rm(path.join(this.directory, file.name), { force: true });
      total -= file.size;
      this.allowed.delete(file.name.slice(0, -4));
    }
  }
  file(name) {
    if (
      !/^[a-f0-9]{64}\.png$/.test(name) ||
      !this.allowed.has(name.slice(0, -4))
    )
      throw new Error("缓存不可用");
    return path.join(this.directory, name);
  }
}
module.exports = { ImageCache, dimensions, readLimited, run };
