# CP-01 embedded media bridge

This prototype uses Electron 44.8.0, a Node-API 8 addon in the main process,
and two native worker threads per media session. The control thread owns mpv
commands/events; the render thread owns the graphics context and render API.
Windows renders into D3D11 shared NT textures; macOS renders OpenGL into IOSurface.
Electron sharedTexture transfers GPU resources to a sandboxed preload, which draws
VideoFrames into the DOM canvas. No decoded pixel buffer crosses JavaScript IPC.

Two slots move through Free → Rendering → Ready → Leased → Free. Ready frames
remain available until acquired; acquire drops older unleased Ready frames.
Leased resources are immutable until Electron's allReferencesReleased callback.
Producer completion is synchronized on the native render thread. Closing first
stops rendering, destroys the mpv context/core, and drains outstanding leases
before freeing surfaces. Generation and owner are captured in each release
callback. Main-thread polling never waits synchronously for mpv or GPU completion.

`sharedTexture` is experimental and locked to Electron 44.8.0. Upgrades require
both platform acceptance matrices again. Windows needs the pinned mpv development
build for the D3D11 render API 2.6; macOS uses stable mpv 0.41/API 2.5 from the
IINA 1.5.0 dependency closure. Downloads, SHA-256, build versions and reasons are
recorded in `runtime-lock.json` and `header-lock.json`. No Homebrew dylib is shipped.

## Build

Download the exact header tarball to `.downloads/electron-headers.tar.gz` from
`runtime-lock.json`; Windows additionally needs `.downloads/node.lib` and the
pinned `.downloads/libmpv-win.7z`. Checksums are checked before compilation.
Install the repository's locked desktop npm dependencies first (`npm ci`).

On Apple Silicon with Xcode command-line tools and Python 3.12+:

```sh
python3 desktop/native/prepare-macos.py
python3 desktop/native/build-macos.py
python3 desktop/probe/make-fixture.py
python3 desktop/probe/package.py darwin
```

On Windows x64 with the specified MSVC and SDK installed:

```powershell
& .\desktop\native\build-windows.ps1 -BuildTools C:\HEManagerBuild\toolchain\BuildTools
python .\desktop\probe\make-fixture.py
python .\desktop\probe\package.py win32
```

Fixture generation needs ffmpeg on the build machine. Packaging needs Python and
locked desktop dependencies, with each platform's built addon and runtime staged.
End users only run the extracted app; Node, Python, compilers, ffmpeg and Homebrew
are build/test tools. Builds and large runtime files live in ignored directories.
Windows still needs a functioning vendor graphics driver. This pinned libmpv
imports `vulkan-1.dll` even when using D3D11; the validation host supplies the
Vulkan loader through `C:\Windows\System32` (driver loader 1.4.341.0). A machine
without that loader needs its vendor driver installed; a Vulkan SDK is not needed.
Generated build-info records source hashes and the exact addon, and packaging
rejects stale native builds. Runtime preparation records original and transformed
library hashes. The app manifest records the final signed/copied payload.

## Acceptance

Set `HE_PROBE_OUTPUT` to an absolute JSON path and run the packaged executable.
For an HTTP test, `HE_PROBE_CONFIG` points to a private JSON file containing
`source`, optional `secondSource`, `headers` and `richFixture`. Tokens never enter
arguments, page state or reports. `test-server.py` uses the actual HE FastAPI,
authentication and stream routes in a mandatory disposable database/work directory.
It writes sanitized Range evidence and an owner-only client configuration file.
Run `HE_PROBE_CLOSE_OUTPUT` instead for the ordinary window-close shutdown test.

The integration run checks actual images and orientation markers, DOM inputs,
three fullscreen transitions with non-default tracks and speed, seek, actual
Anime4K passes, a stalled/slow consumer, minimize/restore, resize and three fresh
sessions with zero remaining surfaces/leases. An individual run is a partial pass:
CP-01 additionally requires both packaged platforms, local and protected HTTP,
normal close, dependency inspection, and a consolidated report. This is the media
feasibility gate; the full library/UI, format matrix, long playback and installers
belong to the subsequent phases.

The prototype starts muted to keep automated tests quiet. Formal audio/volume
behavior is CP-04. The current producer fence waits for GPU completion, and macOS
uses videotoolbox-copy; CPU/GPU copies, throughput and power need CP-04 measurement.
Mac OpenGL is deprecated by Apple; a future replacement changes this verified
rendering path and therefore requires a fresh two-platform gate.
