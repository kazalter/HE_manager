const net = require("node:net"),
  fs = require("node:fs/promises"),
  os = require("node:os"),
  path = require("node:path");
const { spawn } = require("node:child_process"),
  { randomUUID } = require("node:crypto"),
  { shaderFiles } = require("./policy.cjs");
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
class Player {
  constructor(shaderRoot) {
    this.shaderRoot = shaderRoot;
    this.state = {
      running: false,
      paused: true,
      position: 0,
      duration: 0,
      droppedFrames: 0,
      hwdec: "",
      ended: false,
      mode: "off",
      error: "",
    };
    this.sequence = 0;
    this.pending = new Map();
    this.operation = Promise.resolve();
  }
  command(command) {
    if (!this.socket || this.socket.destroyed)
      return Promise.reject(new Error("本机播放器未连接"));
    const request_id = ++this.sequence;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(request_id);
        reject(new Error("播放器响应超时"));
      }, 5000);
      this.pending.set(request_id, { resolve, reject, timer });
      this.socket.write(JSON.stringify({ command, request_id }) + "\n");
    });
  }
  receive(data) {
    this.buffer += data.toString();
    if (this.buffer.length > 1024 * 1024) {
      this.buffer = "";
      return;
    }
    let end;
    while ((end = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, end);
      this.buffer = this.buffer.slice(end + 1);
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        continue;
      }
      if (message.request_id && this.pending.has(message.request_id)) {
        const task = this.pending.get(message.request_id);
        this.pending.delete(message.request_id);
        clearTimeout(task.timer);
        message.error === "success"
          ? task.resolve(message.data)
          : task.reject(new Error("播放器操作失败：" + message.error));
      }
      if (message.event === "property-change") {
        const key = {
          "time-pos": "position",
          duration: "duration",
          pause: "paused",
          "frame-drop-count": "droppedFrames",
          "hwdec-current": "hwdec",
          "eof-reached": "ended",
        }[message.name];
        if (key && message.data !== undefined && message.data !== null)
          this.state[key] = message.data;
      }
      if (message.event === "end-file" && message.reason === "error")
        this.state.error = "媒体无法播放，请检查文件、网络或编码格式";
    }
  }
  async ensure(binary) {
    if (this.socket && !this.socket.destroyed) return;
    this.directory = await fs.mkdtemp(path.join(os.tmpdir(), "he-player-"));
    await fs.chmod(this.directory, 0o700);
    const ipc =
      process.platform === "win32"
        ? ["", "", ".", "pipe", "he-manager-" + randomUUID()].join(
            String.fromCharCode(92),
          )
        : path.join(this.directory, "ipc");
    this.buffer = "";
    this.state.error = "";
    const args = [
      "--no-config",
      "--load-scripts=no",
      "--ytdl=no",
      "--terminal=no",
      "--idle=yes",
      "--force-window=no",
      "--keep-open=yes",
      "--osc=yes",
      process.platform === "darwin"
        ? "--hwdec=videotoolbox-copy"
        : "--hwdec=auto-safe",
      "--vo=gpu-next",
      "--input-ipc-server=" + ipc,
      "--title=HE Manager · 本机播放器",
    ];
    this.child = spawn(binary, args, { stdio: "ignore", windowsHide: true });
    const child = this.child;
    let spawnError = null;
    child.once("error", () => {
      spawnError = new Error("本机播放器启动失败，请检查 mpv 安装");
      this.state.error = spawnError.message;
    });
    child.once("exit", () => {
      if (this.child === child) {
        this.state.running = false;
        this.state.paused = true;
        this.socket?.destroy();
        this.child = null;
      }
    });
    for (let i = 0; i < 60; i++) {
      if (spawnError) throw spawnError;
      if (child.exitCode !== null)
        throw new Error("mpv 启动后退出，请检查 GPU 驱动或运行库");
      try {
        this.socket = await new Promise((resolve, reject) => {
          const socket = net.createConnection(ipc);
          socket.once("error", reject);
          socket.once("connect", () => {
            socket.removeListener("error", reject);
            resolve(socket);
          });
        });
        break;
      } catch {
        await delay(100);
      }
    }
    if (!this.socket || this.socket.destroyed) {
      await this.stop();
      throw new Error("无法连接本机播放器");
    }
    const socket = this.socket;
    socket.on("data", (data) => {
      if (this.socket === socket) this.receive(data);
    });
    this.socket.on("error", () => {});
    this.socket.on("close", () => {
      if (this.socket !== socket) return;
      for (const task of this.pending.values()) {
        clearTimeout(task.timer);
        task.reject(new Error("播放器已关闭"));
      }
      this.pending.clear();
    });
    this.state.running = true;
    for (const [i, name] of [
      "time-pos",
      "duration",
      "pause",
      "frame-drop-count",
      "hwdec-current",
      "eof-reached",
    ].entries())
      await this.command(["observe_property", i, name]);
  }
  open(binary, source, mode, start, title) {
    const operation = this.operation
      .catch(() => {})
      .then(async () => {
        await this.ensure(binary);
        await this.setMode(mode);
        await this.command([
          "set_property",
          "http-header-fields",
          source.token ? [`Authorization: Bearer ${source.token}`] : [],
        ]);
        await this.command([
          "set_property",
          "title",
          String(title || "HE Manager").slice(0, 200),
        ]);
        this.state.position = 0;
        this.state.duration = 0;
        this.state.ended = false;
        await this.command([
          "loadfile",
          source.url,
          "replace",
          -1,
          { start: String(Math.max(0, Number(start) || 0)) },
        ]);
        await this.command(["set_property", "pause", false]);
        return { ...this.state };
      });
    this.operation = operation;
    return operation;
  }
  async setMode(mode) {
    const shaders = shaderFiles(mode, this.shaderRoot);
    for (const file of shaders) await fs.access(file);
    await this.command(["set_property", "glsl-shaders", shaders]);
    this.state.mode = mode;
  }
  async control(action, value) {
    switch (action) {
      case "pause":
        await this.command(["cycle", "pause"]);
        break;
      case "seek":
        if (!Number.isFinite(value) || Math.abs(value) > 86400)
          throw new Error("无效的跳转时间");
        await this.command(["seek", value, "relative"]);
        break;
      case "fullscreen":
        await this.command(["cycle", "fullscreen"]);
        break;
      case "mode":
        await this.setMode(value);
        break;
      default:
        throw new Error("不支持的播放器操作");
    }
    return { ...this.state };
  }
  async stop() {
    const child = this.child;
    const directory = this.directory;
    this.directory = null;
    this.child = null;
    this.socket?.destroy();
    this.socket = null;
    this.state.running = false;
    this.state.paused = true;
    for (const task of this.pending.values()) {
      clearTimeout(task.timer);
      task.reject(new Error("播放器已关闭"));
    }
    this.pending.clear();
    if (child && child.exitCode === null) {
      child.kill();
      await Promise.race([
        new Promise((resolve) => child.once("exit", resolve)),
        delay(1500),
      ]);
      if (child.exitCode === null) child.kill("SIGKILL");
    }
    if (directory) {
      await fs.rm(directory, { recursive: true, force: true }).catch(() => {});
    }
  }
}
module.exports = { Player };
