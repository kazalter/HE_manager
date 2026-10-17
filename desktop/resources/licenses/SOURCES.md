# Bundled runtime sources

- Anime4K v4.0.1: https://github.com/bloc97/Anime4K/tree/v4.0.1 — MIT / public-domain notices are retained in the respective shader headers.
- Real-ESRGAN NCNN/Vulkan: https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan and https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0 — BSD-3-Clause upstream license and bundled model distribution. Runtime includes NCNN and Vulkan/MoltenVK components; original archive READMEs are retained.
- Legacy independent mpv Mac build: https://github.com/mpv-player/mpv/releases/tag/v0.41.0 — macOS 15 arm64 stable archive; replaces a removed rolling git-release asset. The embedded prototype uses its separately locked runtime below.
- mpv Windows build: https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20261017 — source build recipes and dependency references. mpv is launched as an independent process. Upstream copyright/license notices are included; full corresponding sources and build recipes are available at those pinned upstream references.
- Electron 44.8.0: https://github.com/electron/electron/tree/v44.8.0 — its LICENSE and LICENSES.chromium.html remain in the packaged distribution.

Exact download URLs and content checksums: runtime-lock.json. The sample video and checkerboard used by native-selftest are synthetic test patterns generated for this repository.

## CP-01 embedded prototype

The prototype under `desktop/probe` loads libmpv in process rather than launching
the legacy independent mpv executable. Its pinned sources and hashes are in
`desktop/native/runtime-lock.json` and `desktop/native/header-lock.json`.

- Windows: shinchiro 20261017 development build, mpv commit
  `dde0671072723c311df874a32dc4e48b5197ca62`, needed for libmpv D3D11 API 2.6.
- macOS arm64: stable mpv 0.41.0/API 2.5 from
  [IINA 1.5.0](https://github.com/iina/iina/releases/tag/v1.5.0).
  The package retains `IINA-Credits.rtf`; runtime-manifest records the complete
  44-library arm64 dependency closure and each transformed library hash.
  Source/build information: [IINA](https://github.com/iina/iina/tree/v1.5.0),
  [mpv 0.41.0](https://github.com/mpv-player/mpv/tree/v0.41.0), and the upstream
  component references retained in IINA's credits. No Homebrew runtime is bundled.
- Headers retain their upstream copyright and license text. Existing mpv/FFmpeg
  GPL notices are included. Electron's own LICENSE/Chromium notices remain in
  the app distribution; Anime4K shader headers and MIT license are retained.

`acceptance.mkv` is generated from the repository's synthetic video with synthetic
tones, subtitle labels and colored orientation markers. It contains no library
media or user credentials.
