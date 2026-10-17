const { test } = require("node:test"),
  assert = require("node:assert/strict"),
  path = require("node:path");
const {
  serverUrl,
  mediaRequest,
  staticPath,
  shaderFiles,
} = require("../src/policy.cjs");
test("connection URLs reject credentials, executable schemes and query credentials", () => {
  assert.equal(
    serverUrl("http://192.168.0.101:8011/"),
    "http://192.168.0.101:8011",
  );
  for (const value of [
    "file:///etc/passwd",
    "javascript:alert(1)",
    "https://user:secret@example.com",
    "http://host?token=secret",
    "http://host/#x",
  ])
    assert.throws(() => serverUrl(value));
});
test("native media stays on the configured server and strips secrets out of URLs", () => {
  const value = mediaRequest(
    "https://example.com/he",
    "he://app/stream/42?token=secret&track=1",
  );
  assert.equal(value.url, "https://example.com/he/stream/42?track=1");
  assert.equal(value.headers.Authorization, "Bearer secret");
  assert.equal(
    mediaRequest(
      "https://example.com/he",
      "https://example.com/he/manga/1/page/2?token=x",
    ).url,
    "https://example.com/he/manga/1/page/2",
  );
  for (const url of [
    "https://attacker.example/stream/1?token=x",
    "file:///stream/1",
    "he://evil/stream/1",
    "he://app/auth/me",
    "he://app/stream/1?token=x%0aInjected:y",
    "he://app/stream/%2fsecret",
  ])
    assert.throws(() => mediaRequest("https://example.com", url));
});
test("bundle paths cannot escape the UI root", () => {
  const root = path.resolve("/tmp/ui");
  assert.equal(staticPath(root, "/"), path.join(root, "index.html"));
  for (const url of ["/../secret", "/%2e%2e/secret", "/%2f../../secret"])
    assert.throws(() => staticPath(root, url));
});
test("profiles use only bundled Anime4K shaders and off clears the chain", () => {
  assert.deepEqual(shaderFiles("off", "/shaders"), []);
  assert.ok(
    shaderFiles("efficiency", "/shaders").every((file) =>
      file.startsWith(path.join("/shaders", "Anime4K_")),
    ),
  );
  assert.ok(
    shaderFiles("quality", "/shaders").some((file) => file.includes("VL")),
  );
  assert.throws(() => shaderFiles("../../bin/sh", "/shaders"));
});

test("only the bundled app can request fullscreen; other permissions stay denied", () => {
  const { allowPermission } = require("../src/policy.cjs");
  assert.equal(allowPermission("fullscreen", "he://app/"), true);
  for (const url of [
    "he://evil/",
    "https://app/",
    "he://app.evil/",
    "he://user@app/",
    "invalid",
  ])
    assert.equal(allowPermission("fullscreen", url), false);
  for (const permission of [
    "media",
    "geolocation",
    "notifications",
    "automatic-fullscreen",
    "unknown",
  ])
    assert.equal(allowPermission(permission, "he://app/"), false);
});
