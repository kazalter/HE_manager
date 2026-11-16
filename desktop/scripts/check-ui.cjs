// Fails fast when desktop/ui is missing assets that the Electron shell serves
// from disk. The Live2D viewer is built separately (integrations/l2dviewer
// build:manager → frontend/public/l2d) and a desktop package without it shows
// a raw JSON error page when opening 碧蓝航线.
const fs = require("node:fs");
const path = require("node:path");

const ui = path.resolve(process.argv[2] || path.join(__dirname, "..", "ui"));
const required = ["index.html", "l2d/index.html"];
const missing = required.filter((name) => {
  try {
    return !fs.statSync(path.join(ui, name)).isFile();
  } catch {
    return true;
  }
});
if (missing.length) {
  console.error(
    `desktop UI is incomplete (${ui}); missing: ${missing.join(", ")}.\n` +
      "Run `npm ci --prefix ../integrations/l2dviewer` once, then `npm run build:ui` in desktop/.",
  );
  process.exit(1);
}
console.log("desktop UI check passed:", required.join(", "));
