// CP-00 diagnostics: no credentials, media requests, or machine identifiers.
const fs = require("node:fs/promises");
const { createReadStream } = require("node:fs");
const { createHash } = require("node:crypto");
const path = require("node:path");
const os = require("node:os");
const { execFile } = require("node:child_process");
const { promisify } = require("node:util");
const { serverUrl } = require("./policy.cjs");
const execute = promisify(execFile);

function options(argv) {
  const result = {};
  for (const name of ["output", "server", "resources"]) {
    const flag = `--baseline-${name}`;
    const index = argv.indexOf(flag);
    if (index < 0) continue;
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) throw new Error(`${flag} requires a value`);
    result[name] = name === "server" ? serverUrl(value) : path.resolve(value);
  }
  return result;
}

async function sha256(file) {
  const hash = createHash("sha256");
  for await (const bytes of createReadStream(file)) hash.update(bytes);
  return hash.digest("hex");
}

async function inventory(root) {
  const files = [];
  async function visit(directory) {
    let entries;
    try { entries = await fs.readdir(directory, { withFileTypes: true }); }
    catch (error) { if (error.code === "ENOENT") return; throw error; }
    for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name, "en"))) {
      const file = path.join(directory, entry.name);
      const relative = path.relative(root, file).split(path.sep).join("/");
      // Never follow links out of a runtime bundle, or include their absolute targets.
      if (entry.isSymbolicLink()) files.push({ path: relative, kind: "symlink", followed: false });
      else if (entry.isDirectory()) await visit(file);
      else if (entry.isFile()) {
        const stat = await fs.stat(file);
        files.push({ path: relative, bytes: stat.size, sha256: await sha256(file) });
      }
    }
  }
  await visit(root);
  return { status: files.length ? "observed" : "missing", files };
}

async function connection(base, fetcher = fetch) {
  if (!base) return { status: "not-requested" };
  const server = serverUrl(base);
  try {
    const response = await fetcher(server + "/auth/status", {
      redirect: "error", signal: AbortSignal.timeout(8000),
    });
    // Do not collect arbitrary response bodies/errors: they may contain private data.
    if (!response.ok) {
      await response.body?.cancel();
      return { server, status: "http-error", httpStatus: response.status };
    }
    // Bound the public status response, including chunked responses.
    const reader = response.body?.getReader();
    if (!reader) return { server, status: "invalid-response" };
    let bytes = Buffer.alloc(0);
    try {
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        if (bytes.length + part.value.length > 4096) return { server, status: "invalid-response" };
        bytes = Buffer.concat([bytes, part.value]);
      }
    } finally { await reader.cancel(); }
    let body;
    try { body = JSON.parse(bytes.toString("utf8")); } catch { return { server, status: "invalid-response" }; }
    return typeof body.has_users === "boolean"
      ? { server, status: "reachable", hasUsers: body.has_users }
      : { server, status: "invalid-response" };
  } catch { return { server, status: "connection-error" }; }
}

async function command(file, args, cwd) {
  try {
    const result = await execute(file, args, { cwd, timeout: 8000, maxBuffer: 128 * 1024, windowsHide: true });
    return result.stdout.trim();
  } catch { return null; }
}

async function hostDetails() {
  if (process.platform === "win32") {
    const output = await command("powershell.exe", ["-NoProfile", "-NonInteractive", "-Command",
      "[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); $o=Get-CimInstance Win32_OperatingSystem; $g=Get-CimInstance Win32_VideoController; @{os=@{caption=$o.Caption;version=$o.Version;build=$o.BuildNumber};gpus=@($g | ForEach-Object {@{name=$_.Name;driver=$_.DriverVersion}})} | ConvertTo-Json -Depth 4 -Compress"]);
    try { return JSON.parse(output); } catch { return { status: "unavailable" }; }
  }
  if (process.platform === "darwin") return {
    productVersion: await command("/usr/bin/sw_vers", ["-productVersion"]),
    build: await command("/usr/bin/sw_vers", ["-buildVersion"]),
    model: await command("/usr/sbin/sysctl", ["-n", "hw.model"]),
    compiler: (await command("/usr/bin/clang", ["--version"]))?.split("\n")[0] || null,
  };
  return { status: "non-target-platform" };
}

async function collect({ app, screen, sharedTexture, root, resourceRoot, server, shell }) {
  const [gpu, resources, source, dirty, host, sourceFiles, externalNode] = await Promise.all([
    app.getGPUInfo("complete"), inventory(resourceRoot || path.join(root, "resources")),
    command("git", ["rev-parse", "HEAD"], root),
    command("git", ["status", "--porcelain", "--untracked-files=no"], root), hostDetails(),
    Promise.all(["src/main.cjs", "src/baseline.cjs", "src/preload.cjs", "package.json", "runtime-lock.json", "ui/index.html", "ui/version.json"].map(async (file) => {
      try { return { path: file, sha256: await sha256(path.join(root, file)) }; }
      catch { return { path: file, status: "missing" }; }
    })),
    command("node", ["--version"]),
  ]);
  const runtime = resources.files.filter((file) => file.path.startsWith("runtime/"));
  const cp01 = {
    status: "not-validated",
    sharedTextureAPI: typeof sharedTexture?.importSharedTexture === "function" && typeof sharedTexture?.sendSharedTexture === "function",
    libmpvPresent: runtime.some((file) => /(?:libmpv[^/]*\.(?:dll|dylib)|mpv\.framework\/)/i.test(file.path)),
    required: ["native-render-thread", "shared-texture-import", "DOM-overlay-input", "protected-stream-seek", "same-session-fullscreen", "bounded-frame-lifetime", "packaged-target-tests"],
  };
  return {
    schemaVersion: 1, phase: "CP-00", capturedAt: new Date().toISOString(),
    source: { revision: /^[a-f0-9]{40}$/.test(source || "") ? source : null, trackedChanges: dirty === null ? null : Boolean(dirty), files: sourceFiles },
    runtime: { app: app.getVersion(), electron: process.versions.electron, node: process.versions.node, chrome: process.versions.chrome, v8: process.versions.v8 },
    host: { platform: process.platform, arch: process.arch, osRelease: os.release(), osVersion: os.version(), cpu: os.cpus()[0]?.model, logicalCpus: os.cpus().length, memoryBytes: os.totalmem(), details: host },
    toolchain: { externalNode, compiler: host.compiler || null, nativeAddon: "not-built" },
    displays: screen.getAllDisplays().map((display) => ({ bounds: display.bounds, workArea: display.workArea, scaleFactor: display.scaleFactor, rotation: display.rotation, internal: display.internal })),
    gpu: {
      featureStatus: app.getGPUFeatureStatus(),
      devices: (gpu.gpuDevice || []).map(({ vendorId, deviceId, active, driverVendor, driverVersion, deviceString }) => ({ vendorId, deviceId, active, driverVendor, driverVersion, deviceString })),
      renderer: gpu.auxAttributes?.glRenderer || null,
    },
    shell,
    server: await connection(server),
    resources: { ...resources, verification: "observed-file-hashes-only", runtimePresent: runtime.length > 0 },
    cp01,
    unmeasured: ["authenticated-library-performance", "representative-video-playback", "frame-drop-rate", "decoded-image-memory", "GPU-memory-trend", "enhancement-latency", "cold-start-with-controlled-OS-cache"],
  };
}

async function writeReport(file, report) {
  await fs.mkdir(path.dirname(file), { recursive: true });
  const temporary = file + ".next";
  await fs.writeFile(temporary, JSON.stringify(report, null, 2) + "\n", { mode: 0o600 });
  await fs.rename(temporary, file);
}

module.exports = { options, sha256, inventory, connection, collect, writeReport };
