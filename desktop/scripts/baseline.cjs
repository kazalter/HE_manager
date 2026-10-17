const path = require("node:path");
const { spawn } = require("node:child_process");
const { electronArguments } = require("../src/baseline.cjs");

try {
  const child = spawn(require("electron"), electronArguments(process.argv.slice(2)), {
    cwd: path.resolve(__dirname, ".."),
    stdio: "inherit",
  });
  child.once("error", () => {
    console.error("Unable to start Electron; run npm ci in desktop first");
    process.exitCode = 1;
  });
  child.once("exit", (code) => { process.exitCode = code ?? 1; });
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
