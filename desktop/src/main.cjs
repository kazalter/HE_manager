const {
  app,
  BrowserWindow,
  protocol,
  net,
  ipcMain,
  dialog,
  Menu,
} = require("electron");
const path = require("node:path"),
  fs = require("node:fs/promises"),
  { pathToFileURL } = require("node:url");
const {
    serverUrl,
    mediaRequest,
    staticPath,
    API_PATH,
    allowPermission,
  } = require("./policy.cjs"),
  { Player } = require("./player.cjs"),
  { EmbeddedPlayer } = require("./embedded-player.cjs"),
  { ImageCache } = require("./images.cjs");
protocol.registerSchemesAsPrivileged([
  {
    scheme: "he",
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
    },
  },
]);
const root = path.resolve(__dirname, ".."),
  ui = path.join(root, "ui"),
  runtime = path.join(root, "resources/runtime");
const baselineMode = process.argv.includes("--baseline");
const uiTestConfigPath = process.env.HE_DESKTOP_TEST_CONFIG;
function diagnosticStage(stage) {
  if (uiTestConfigPath && process.env.HE_DESKTOP_TEST_OUTPUT) {
    require('node:fs').appendFileSync(process.env.HE_DESKTOP_TEST_OUTPUT + '.startup.log', stage + '\n');
  }
}
diagnosticStage('module-loaded');
// Diagnostics must never load the user's login, cache, or normal Chromium profile.
if (baselineMode || uiTestConfigPath) {
  const directory = require("node:fs").mkdtempSync(
    path.join(require("node:os").tmpdir(), "he-baseline-"),
  );
  app.setPath("userData", directory);
  app.setPath("sessionData", directory);
  setTimeout(() => {
    console.error("HE desktop diagnostic deadline exceeded");
    app.exit(1);
  }, uiTestConfigPath ? 180000 : 60000).unref();
}
let window, cache, settings, settingsFile;
let applicationReady = false;
const player = new EmbeddedPlayer({ root, sharedTexture: require('electron').sharedTexture, getWindow: () => window });
const legacyPlayer = new Player(path.join(root, "resources/shaders"));
const defaults = {
  server: "",
  videoMode: "off",
  imageMode: "off",
  engines: {},
};
async function saveSettings() {
  const temp = settingsFile + ".next";
  await fs.writeFile(temp, JSON.stringify(settings, null, 2), { mode: 0o600 });
  await fs.rename(temp, settingsFile);
}
async function engine(kind) {
  const candidates =
    kind === "mpv"
      ? [
          settings.engines?.mpv,
          path.join(
            runtime,
            "mpv",
            process.platform === "win32"
              ? "mpv.exe"
              : "mpv.app/Contents/MacOS/mpv",
          ),
          "/opt/homebrew/bin/mpv",
          "/usr/local/bin/mpv",
          ...(process.platform === "linux" ? ["/usr/bin/mpv"] : []),
        ]
      : [
          settings.engines?.image,
          path.join(
            runtime,
            "realesrgan",
            process.platform === "win32"
              ? "realesrgan-ncnn-vulkan.exe"
              : "realesrgan-ncnn-vulkan",
          ),
        ];
  for (const file of candidates.filter(Boolean)) {
    try {
      if ((await fs.stat(file)).isFile()) return file;
    } catch {}
  }
  return null;
}
async function configuration() {
  return {
    server: settings.server,
    videoMode: settings.videoMode,
    imageMode: settings.imageMode,
    platform: process.platform,
    arch: process.arch,
    version: app.getVersion(),
    mpv: player.available(),
    videoPresentation: 'embedded',
    image: !!(await engine("image")),
  };
}
function trusted(event) {
  return window && !window.isDestroyed() && event.sender === window.webContents
    && event.senderFrame === window.webContents.mainFrame && event.senderFrame.url.startsWith('he://app/');
}
function handle(name, callback) {
  ipcMain.handle(name, async (event, ...args) => {
    if (
      !trusted(event)
    )
      throw new Error("不允许的桌面调用");
    try {
      return await callback(...args);
    } catch (error) {
      throw new Error(
        (error.cause?.code
          ? `${error.message} (${error.cause.code})`
          : error.message
        )?.replace(
          /(?:token|authorization)=[^\s&]+/gi,
          "credential=[redacted]",
        ) || "操作失败",
      );
    }
  });
}
function registerIPC() {
  ipcMain.on('he:video-ready', (event) => { if (trusted(event)) player.ready(); });
  ipcMain.on('he:video-size', (event, value) => { if (trusted(event)) player.resize(value); });
  handle("he:configuration", configuration);
  handle("he:connect", async (value) => {
    const server = serverUrl(value);
    const response = await fetch(server + "/auth/status", {
      redirect: "error",
      signal: AbortSignal.timeout(8000),
    });
    if (!response.ok) throw new Error("连接失败，请检查地址与端口");
    const data = await response.json();
    if (typeof data.has_users !== "boolean")
      throw new Error("这个地址不是 HE Manager 服务");
    await player.stop();
    settings.server = server;
    await saveSettings();
    cache.allowed.clear();
    return configuration();
  });
  handle("he:choose-engine", async (kind) => {
    if (!["mpv", "image"].includes(kind)) throw new Error("未知的引擎类型");
    const result = await dialog.showOpenDialog(window, {
      title:
        kind === "mpv"
          ? "选择 mpv 可执行文件或 mpv.app"
          : "选择 realesrgan-ncnn-vulkan 可执行文件",
      properties: ["openFile"],
      filters:
        process.platform === "win32"
          ? [{ name: "可执行文件", extensions: ["exe"] }]
          : [],
    });
    if (!result.canceled && result.filePaths[0]) {
      let selected = result.filePaths[0];
      if (kind === "mpv" && selected.endsWith(".app"))
        selected = path.join(selected, "Contents/MacOS/mpv");
      if (!(await fs.stat(selected)).isFile())
        throw new Error("请选择引擎可执行文件");
      settings.engines = { ...settings.engines, [kind]: selected };
      await saveSettings();
    }
    return configuration();
  });
  handle("he:preferences", async (value) => {
    if (
      !value ||
      !["off", "efficiency", "quality"].includes(value.videoMode) ||
      !["off", "anime", "photo"].includes(value.imageMode)
    )
      throw new Error("无效的超分配置");
    if (player.state.running) await player.setMode(value.videoMode);
    settings.videoMode = value.videoMode;
    settings.imageMode = value.imageMode;
    await saveSettings();
    return configuration();
  });
  handle("he:video-open", async (options) => {
    if (!options || typeof options.url !== "string")
      throw new Error("无效的播放请求");
    const source = mediaRequest(settings.server, options.url);
    return player.open(
      null,
      source,
      settings.videoMode,
      options.start,
      options.title,
    );
  });
  handle("he:video-control", (action, value) => player.control(action, value));
  handle("he:video-state", () => ({ ...player.state }));
  handle("he:video-stop", () => player.stop());
  handle("he:image", async (options) => {
    if (!options || !["anime", "photo"].includes(options.mode))
      throw new Error("请选择图片超分类型");
    const binary = await engine("image");
    if (!binary) throw new Error("未找到图片超分引擎，请在桌面设置中选择引擎");
    return cache.prepare(
      mediaRequest(settings.server, options.url),
      options.mode,
      binary,
      path.join(path.dirname(binary), "models"),
    );
  });
}
async function protocolHandler(request) {
  const url = new URL(request.url);
  let operation = 'route';
  if (
    url.host !== "app" ||
    (request.initiatorOrigin && request.initiatorOrigin !== "he://app")
  )
    return new Response("Forbidden", { status: 403 });
  try {
    if (
      url.pathname === "/__fullscreen-test" &&
      process.argv.includes("--fullscreen-selftest")
    )
      return new Response(
        "<!doctype html><title>HE Manager fullscreen test</title><h1>Fullscreen self-test</h1>",
        { headers: { "content-type": "text/html; charset=utf-8" } },
      );
    if (url.pathname.startsWith("/__cache/"))
      return net.fetch(pathToFileURL(cache.file(url.pathname.slice(9))).href);
    if (API_PATH.test(url.pathname)) {
      if (!settings.server)
        return Response.json({ detail: "请先配置服务器地址" }, { status: 503 });
      operation = 'proxy-headers';
      const headers = new Headers(request.headers);
      for (const key of [
        "host",
        "origin",
        "referer",
        "connection",
        "accept-encoding",
        "cookie",
      ])
        headers.delete(key);
      const options = {
        method: request.method,
        headers,
        redirect: "manual",
        signal: request.signal,
      };
      if (!["GET", "HEAD"].includes(request.method))
        options.body = await request.arrayBuffer();
      operation = 'proxy-fetch';
      const response = await fetch(
        settings.server + url.pathname + url.search,
        options,
      );
      diagnosticStage(`proxy-status-${request.method}-${url.pathname}-${response.status}`);
      if (response.status >= 300 && response.status < 400) {
        await response.body?.cancel();
        return Response.json(
          { detail: "服务器返回跳转，请使用最终服务地址" },
          { status: 502 },
        );
      }
      operation = 'proxy-response-headers';
      const outgoing = new Headers(response.headers);
      for (const key of [
        "content-encoding",
        "content-length",
        "set-cookie",
        "content-security-policy",
        "access-control-allow-origin",
      ])
        outgoing.delete(key);
      outgoing.set("Cache-Control", "no-store");
      operation = 'proxy-response';
      return new Response(response.body, {
        status: response.status,
        headers: outgoing,
      });
    }
    const response = await net.fetch(
        pathToFileURL(staticPath(ui, url.pathname)).href,
      ),
      headers = new Headers(response.headers);
    headers.set(
      "Content-Security-Policy",
      "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https: http:; media-src 'self' blob:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-src 'none'",
    );
    return new Response(response.body, { status: response.status, headers });
  } catch (error) {
    diagnosticStage(`protocol-error-${operation}-${error.name}-${error.cause?.code || error.code || 'none'}`);
    return Response.json(
      { detail: "读取失败，请检查服务器连接或本地文件" },
      { status: 502 },
    );
  }
}
async function createWindow(test = false) {
  diagnosticStage('create-window');
  window = new BrowserWindow({
    width: 1360,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    title: "HE Manager",
    backgroundColor: "#0a0a0d",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
    },
  });
  diagnosticStage('window-created');
  const ownerWindow = window;
  let adjustingMinimum = false;
  function syncMinimumContent() {
    if (adjustingMinimum || ownerWindow.isDestroyed() || ownerWindow.isFullScreen()
      || ownerWindow._heFullscreen || ownerWindow.isMaximized() || ownerWindow.isMinimized()) return;
    const outer = ownerWindow.getSize(), content = ownerWindow.getContentSize();
    const minimum = [1024 + outer[0] - content[0], 640 + outer[1] - content[1]];
    adjustingMinimum = true;
    try {
      if (ownerWindow.getMinimumSize().some((size, index) => size !== minimum[index])) ownerWindow.setMinimumSize(...minimum);
      if (outer.some((size, index) => size < minimum[index])) ownerWindow.setSize(Math.max(outer[0], minimum[0]), Math.max(outer[1], minimum[1]));
    } finally { adjustingMinimum = false; }
  }
  // Native menus can attach after the first load on Windows. Recompute from
  // the current content area when the chrome or display metrics settle.
  ownerWindow.on('resize', syncMinimumContent);
  ownerWindow.once('ready-to-show', syncMinimumContent);
  ownerWindow._heGpuReady = app.getGPUInfo('basic').then((gpu) => {
    ownerWindow._heGpu = gpu.gpuDevice?.find((device) => device.active) || {};
  });
  void ownerWindow._heGpuReady.catch(() => {});
  window._heFullscreen = false;
  window.on('enter-full-screen', () => { ownerWindow._heFullscreen = true; });
  window.on('leave-full-screen', () => { ownerWindow._heFullscreen = false; syncMinimumContent(); });
  player.receiverReady = false;
  window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  window.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith("he://app/")) event.preventDefault();
  });
  window.webContents.session.setPermissionRequestHandler(
    (wc, permission, callback, details) =>
      callback(
        wc === window?.webContents &&
          details.isMainFrame !== false &&
          allowPermission(permission, details.requestingUrl || wc.getURL()),
      ),
  );
  window.webContents.session.setPermissionCheckHandler(
    (wc, permission, origin, details) =>
      wc === window?.webContents &&
      details.isMainFrame !== false &&
      allowPermission(
        permission,
        details.requestingUrl || origin || wc.getURL(),
      ),
  );
  window.webContents.session.on("will-download", (event) =>
    event.preventDefault(),
  );
  window.on('close', (event) => {
    if (ownerWindow._heClosing) return;
    event.preventDefault(); ownerWindow._heClosing = true;
    void player.stop().catch(() => {}).finally(() => ownerWindow.destroy());
  });
  window.on("closed", () => {
    window = null;
  });
  diagnosticStage('load-window');
  await ownerWindow.loadURL(test ? "he://app/__fullscreen-test" : "he://app/");
  syncMinimumContent();
  diagnosticStage('window-loaded');
  diagnosticStage('window-ready');
}
app.whenReady().then(async () => {
  diagnosticStage('app-ready');
  const readyAt = performance.now();
  const baselineOptions = baselineMode
    ? require("./baseline.cjs").options(process.argv)
    : null;
  app.setAccessibilitySupportEnabled(true);
  diagnosticStage('accessibility-ready');
  settingsFile = path.join(app.getPath("userData"), "desktop-settings.json");
  await fs.mkdir(app.getPath("userData"), { recursive: true });
  settings = { ...defaults, engines: {} };
  if (!baselineMode && !uiTestConfigPath) try {
    const stored = JSON.parse(await fs.readFile(settingsFile, "utf8"));
    settings = { ...settings, ...stored };
    if (settings.server) settings.server = serverUrl(settings.server);
  } catch {}
  if (!["off", "efficiency", "quality"].includes(settings.videoMode))
    settings.videoMode = "off";
  if (!["off", "anime", "photo"].includes(settings.imageMode))
    settings.imageMode = "off";
  if (baselineOptions?.server) settings.server = baselineOptions.server;
  diagnosticStage('settings-loaded');
  const uiTestConfig = uiTestConfigPath ? JSON.parse(await fs.readFile(uiTestConfigPath, 'utf8')) : null;
  if (uiTestConfig) { settings.server = serverUrl(uiTestConfig.server); player.volume = 0; }
  diagnosticStage('config-loaded');
  cache = new ImageCache(path.join(app.getPath("userData"), "image-cache"));
  protocol.handle("he", protocolHandler);
  registerIPC();
  diagnosticStage('services-registered');
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      { label: "HE Manager", submenu: [{ role: "about" }, { role: "quit" }] },
      {
        label: "编辑",
        submenu: [
          { role: "undo" },
          { role: "redo" },
          { role: "copy" },
          { role: "paste" },
          { role: "selectAll" },
        ],
      },
      {
        label: "窗口",
        submenu: [
          { role: "minimize" },
          { role: "zoom" },
          { role: "reload" },
          { role: "toggleDevTools" },
        ],
      },
    ]),
  );
  diagnosticStage('menu-ready');
  applicationReady = true;
  if (uiTestConfig) {
    await createWindow();
    diagnosticStage('selftest-start');
    let passed = false;
    try { passed = await require('./ui-selftest.cjs')({ window, player, config: uiTestConfig, output: process.env.HE_DESKTOP_TEST_OUTPUT }); }
    finally { await player.stop(); await cache.close(); }
    app.exit(passed ? 0 : 1);
    return;
  }
  if (baselineMode) {
    let stage = "create-window";
    try {
      await createWindow();
      let shell;
      for (let attempt = 0; attempt < 100; attempt++) {
        shell = await window.webContents.executeJavaScript(`({
          bridge: !!window.heDesktop,
          toolbar: !!document.querySelector('.he-desktop-toolbar'),
          viewport: {width: innerWidth, height: innerHeight, devicePixelRatio},
          videoFrameAPI: typeof VideoFrame === 'function'
        })`);
        if (shell.bridge && shell.toolbar) break;
        await new Promise((resolve) => setTimeout(resolve, 100));
      }
      shell.status = shell.bridge && shell.toolbar ? "ready" : "timeout";
      shell.readyToShellMs = Math.round(performance.now() - readyAt);
      shell.processUptimeToShellMs = Math.round(process.uptime() * 1000);
      shell.profile = "isolated-temporary-profile";
      shell.defaults = { videoMode: settings.videoMode, imageMode: settings.imageMode };
      // Let authentication status and the first compositor frame settle before
      // taking a visual/resource baseline. Startup timing above stays separate.
      await new Promise((resolve) => setTimeout(resolve, 1500));
      stage = "login-form";
      shell.loginForm = await window.webContents.executeJavaScript(
        "!!document.querySelector('.he-auth-view input[autocomplete=username]')",
      );
      const output = baselineOptions.output || path.join(
        app.getPath("documents"), "HE Manager Diagnostics",
        `baseline-${process.platform}-${process.arch}-${Date.now()}.json`,
      );
      const screenshot = output.replace(/\.json$/i, "") + ".png";
      stage = "screenshot";
      await fs.mkdir(path.dirname(screenshot), { recursive: true });
      await fs.writeFile(screenshot, (await window.webContents.capturePage()).toPNG());
      shell.screenshot = path.basename(screenshot);
      const diagnostics = require("./baseline.cjs");
      stage = "collect";
      const report = await diagnostics.collect({
        app, root, shell,
        screen: require("electron").screen,
        sharedTexture: require("electron").sharedTexture,
        server: baselineOptions.server,
        resourceRoot: baselineOptions.resources,
      });
      stage = "write-report";
      await diagnostics.writeReport(output, report);
      console.log("HE_BASELINE " + JSON.stringify({ output, shell: shell.status, server: report.server.status, cp01: report.cp01.status }));
      app.exit(shell.status === "ready" ? 0 : 1);
    } catch (error) {
      // No raw errors: network/file errors may contain private paths or URLs.
      console.error(`HE_BASELINE failed at ${stage} (${error.code || error.name || "Error"})`);
      app.exit(1);
    }
    return;
  }
  if (process.argv.includes("--fullscreen-selftest")) {
    try {
      await createWindow(true);
      await window.webContents.executeJavaScript(
        "document.documentElement.requestFullscreen()",
        true,
      );
      for (let attempt = 0; attempt < 60 && !window.isFullScreen(); attempt++)
        await new Promise((resolve) => setTimeout(resolve, 100));
      const entered =
        window.isFullScreen() &&
        (await window.webContents.executeJavaScript(
          "!!document.fullscreenElement",
        ));
      await window.webContents.executeJavaScript(
        "document.exitFullscreen()",
        true,
      );
      for (let attempt = 0; attempt < 60 && window.isFullScreen(); attempt++)
        await new Promise((resolve) => setTimeout(resolve, 100));
      const exited =
        !window.isFullScreen() &&
        (await window.webContents.executeJavaScript(
          "!document.fullscreenElement",
        ));
      console.log("HE_FULLSCREEN_TEST " + JSON.stringify({ entered, exited }));
      app.exit(entered && exited ? 0 : 1);
    } catch (error) {
      console.log(
        "HE_FULLSCREEN_TEST " + JSON.stringify({ error: error.message }),
      );
      app.exit(1);
    }
    return;
  }
  if (process.argv.includes("--native-selftest")) {
    const report = await require("./native-selftest.cjs")({
      player: legacyPlayer,
      mpv: await engine("mpv"),
      image: await engine("image"),
      resources: path.join(root, "resources"),
    });
    await fs.writeFile(
      path.join(app.getPath("userData"), "native-test-report.json"),
      JSON.stringify(report, null, 2),
    );
    console.log("HE_NATIVE_TEST " + JSON.stringify(report));
    app.exit(0);
    return;
  }
  if (process.argv.includes("--smoke-test")) {
    await createWindow();
    for (let attempt = 0; attempt < 100; attempt++) {
      if (
        await window.webContents.executeJavaScript(
          "!!document.querySelector('.he-desktop-toolbar')",
        )
      )
        break;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    const report = await window.webContents.executeJavaScript(
      `JSON.stringify({title:document.title,bridge:!!window.heDesktop,body:document.body.innerText.slice(0,300)})`,
    );
    console.log("HE_DESKTOP_SMOKE " + report);
    app.exit(0);
  } else await createWindow();
}).catch(() => {
  console.error("HE Manager startup failed; check configuration and runtime resources");
  app.exit(1);
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
app.on("activate", () => {
  if (applicationReady && !BrowserWindow.getAllWindows().length) void createWindow().catch(() => {
    console.error("HE Manager window could not reopen");
  });
});
require("./lifecycle.cjs").installShutdown(app, () =>
  Promise.allSettled([player.stop(), legacyPlayer.stop(), cache?.close()]),
);
