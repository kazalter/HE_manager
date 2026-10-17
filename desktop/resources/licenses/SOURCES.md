# Bundled runtime sources

- Anime4K v4.0.1: https://github.com/bloc97/Anime4K/tree/v4.0.1 — MIT / public-domain notices are retained in the respective shader headers.
- Real-ESRGAN NCNN/Vulkan: https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan and https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0 — BSD-3-Clause upstream license and bundled model distribution. Runtime includes NCNN and Vulkan/MoltenVK components; original archive READMEs are retained.
- mpv Mac build: https://github.com/mpv-player/mpv/commit/dde0671072 and https://github.com/mpv-player/mpv/releases/tag/git-release
- mpv Windows build: https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20261017 — source build recipes and dependency references. mpv is launched as an independent process. Upstream copyright/license notices are included; full corresponding sources and build recipes are available at those pinned upstream references.
- Electron 44.8.0: https://github.com/electron/electron/tree/v44.8.0 — its LICENSE and LICENSES.chromium.html remain in the packaged distribution.

Exact download URLs and content checksums: runtime-lock.json. The sample video and checkerboard used by native-selftest are synthetic test patterns generated for this repository.
