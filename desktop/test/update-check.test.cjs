const { test } = require('node:test');
const assert = require('node:assert/strict');
const { checkUpdate, RELEASES } = require('../src/update-check.cjs');
const result = (data, status = 200) => async (url, options) => {
  assert.equal(url, 'https://api.github.com/repos/kazalter/HE_manager/releases/latest');
  assert.equal(options.redirect, 'error');
  return { status, ok: status === 200, json: async () => data };
};
test('compares stable release versions and never trusts a release URL', async () => {
  assert.deepEqual(await checkUpdate('1.0.3', result({ tag_name: 'v1.1.0', html_url: 'https://evil.invalid' })), { status: 'available', version: '1.1.0' });
  assert.deepEqual(await checkUpdate('1.2.0', result({ tag_name: 'v1.1.0' })), { status: 'current', version: '1.1.0' });
  assert.equal(RELEASES, 'https://github.com/kazalter/HE_manager/releases');
});
test('does not claim a version is current when comparison is not reliable', async () => {
  assert.deepEqual(await checkUpdate('1.0.3', result({ tag_name: 'v1.2.0-rc1' })), { status: 'unknown' });
  assert.deepEqual(await checkUpdate('dev', result({ tag_name: '1.2.0' })), { status: 'unknown' });
  assert.deepEqual(await checkUpdate('1.0.3', result({}, 404)), { status: 'no-release' });
  await assert.rejects(checkUpdate('1.0.3', result({}, 403)));
});
