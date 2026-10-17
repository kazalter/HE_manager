const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { createHash } = require("node:crypto");
const { options, inventory, connection, writeReport } = require("../src/baseline.cjs");

test("baseline CLI rejects credential-bearing addresses and missing values", () => {
  assert.throws(() => options(["--baseline-server", "http://example.test/?token=secret"]));
  assert.throws(() => options(["--baseline-server", "http://user:secret@example.test"]));
  assert.throws(() => options(["--baseline-output", "--baseline"]));
  assert.equal(options(["--baseline-server", "http://example.test/"]).server, "http://example.test");
});

test("public status check has bounded, anonymous, non-redirected reads", async () => {
  let request;
  const result = await connection("http://example.test", async (url, init) => {
    request = { url, init };
    return Response.json({ has_users: true, privateField: "must-not-be-collected" });
  });
  assert.deepEqual(result, { server: "http://example.test", status: "reachable", hasUsers: true });
  assert.equal(request.url, "http://example.test/auth/status");
  assert.equal(request.init.redirect, "error");
  assert.equal(request.init.headers, undefined);
  assert.ok(request.init.signal instanceof AbortSignal);
});

test("baseline never saves failure response bodies or exception messages", async () => {
  for (const fetcher of [
    async () => new Response("private-token", { status: 401 }),
    async () => { throw new Error("private-token"); },
    async () => Response.json({ access_token: "private-token" }),
    async () => new Response("private-token".repeat(1000)),
  ]) {
    const report = await connection("http://example.test", fetcher);
    assert.notEqual(report.status, "reachable");
    assert.ok(!JSON.stringify(report).includes("private-token"));
  }
  assert.deepEqual(await connection(), { status: "not-requested" });
});

test("runtime inventory hashes bytes and does not follow external symlinks", async (t) => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "he-baseline-test-"));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const resources = path.join(directory, "resources");
  await fs.mkdir(path.join(resources, "runtime"), { recursive: true });
  await fs.writeFile(path.join(resources, "runtime", "mpv.bin"), "fixture");
  await fs.writeFile(path.join(directory, "private.txt"), "private-token");
  // Windows symlinks require privilege; directory junctions do not.
  await fs.symlink(directory, path.join(resources, "outside"), process.platform === "win32" ? "junction" : "dir");
  const report = await inventory(resources);
  assert.equal(report.files.length, 2);
  assert.deepEqual(report.files.find((file) => file.path === "runtime/mpv.bin"), {
    path: "runtime/mpv.bin", bytes: 7, sha256: createHash("sha256").update("fixture").digest("hex"),
  });
  assert.equal(report.files.find((file) => file.path === "outside").followed, false);
  assert.ok(!JSON.stringify(report).includes("private-token"));
  assert.deepEqual(await inventory(path.join(directory, "missing")), { status: "missing", files: [] });
});

test("baseline report is a complete JSON file after atomic replacement", async (t) => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "he-report-test-"));
  t.after(() => fs.rm(directory, { recursive: true, force: true }));
  const file = path.join(directory, "nested", "report.json");
  await writeReport(file, { schemaVersion: 1, shell: { status: "ready" } });
  await writeReport(file, { schemaVersion: 1, shell: { status: "timeout" } });
  assert.equal(JSON.parse(await fs.readFile(file)).shell.status, "timeout");
  await assert.rejects(fs.access(file + ".next"));
});
