const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { diagnosticProfile } = require('../src/diagnostic-profile.cjs');
test('persistent diagnostics can reuse only marked disposable directories, never the normal app profile', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'he-profile-policy-'));
  try {
    const normal = path.join(root, 'HE Manager'); fs.mkdirSync(normal);
    fs.writeFileSync(path.join(normal, 'login.json'), 'untouched');
    assert.throws(() => diagnosticProfile(normal, root));
    assert.equal(fs.readFileSync(path.join(normal, 'login.json'), 'utf8'), 'untouched');
    const allowed = fs.mkdtempSync(path.join(root, 'he-desktop-test-'));
    assert.throws(() => diagnosticProfile(allowed, root));
    fs.writeFileSync(path.join(allowed, '.he-desktop-test-profile.json'), '{"version":1}');
    assert.equal(diagnosticProfile(allowed, root), fs.realpathSync(allowed));
    const fresh = diagnosticProfile(undefined, root);
    assert.ok(path.basename(fresh).startsWith('he-baseline-')); assert.notEqual(fresh, allowed);
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
