// Headless CP-03 service contract check, using an explicitly disposable HE server.
// This does not replace packaged host/renderer, safeStorage or identity-switch UI gates.
const fs = require('node:fs/promises');
const { createHash } = require('node:crypto');
const path = require('node:path');
const { DesktopSession } = require('../src/session.cjs');
(async () => {
  const output = process.env.HE_DESKTOP_TEST_OUTPUT;
  if (!output || !process.env.HE_DESKTOP_TEST_CONFIG) throw new Error('Private diagnostic configuration and output are required');
  const config = JSON.parse(await fs.readFile(process.env.HE_DESKTOP_TEST_CONFIG, 'utf8'));
  const requests = [], checks = {};
  let token = '';
  const session = new DesktopSession({ server: config.server,
    store: { load: async () => '', save: async (_server, value) => { token = value; return false; } },
    fetch: async (url, options) => {
      const parsed = new URL(url);
      if (parsed.searchParams.has('token')) throw new Error('Credential-bearing URL');
      requests.push({ method: options.method || 'GET', path: parsed.pathname, bearer: new Headers(options.headers).has('Authorization') });
      return fetch(url, options);
    },
  });
  const state = await session.login(config.username, config.password);
  checks.loginSnapshotHasNoCredential = !!state.user && !JSON.stringify(state).includes(token);
  const list = await session.request('/media?limit=60&offset=0', {}, state.generation);
  const items = await list.json(), total = Number(list.headers.get('x-total-count'));
  checks.pagedList = list.ok && Array.isArray(items) && items.length <= 60 && Number.isSafeInteger(total) && total >= items.length;
  const detail = await session.request('/media/' + config.videoId, {}, state.generation);
  const media = await detail.json(); checks.actualOpen = detail.ok && media.id === config.videoId && !!media.last_opened_at;
  const patch = await session.request('/media/' + media.id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ favorite: !media.favorite }) }, state.generation);
  const changed = await patch.json(); checks.narrowPatch = patch.ok && changed.favorite === !media.favorite && changed.progress === media.progress;
  await (await session.request('/media/' + media.id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ favorite: media.favorite }) }, state.generation)).body?.cancel();
  const stream = await session.request('/stream/' + media.id, { headers: { Range: 'bytes=100-199' } }, state.generation);
  checks.protectedRange = stream.status === 206 && /^bytes 100-199\//.test(stream.headers.get('content-range') || '') && (await stream.arrayBuffer()).byteLength === 100;
  const invalid = await session.request('/stream/' + media.id, { headers: { Range: 'bytes=999999999-' } }, state.generation);
  await invalid.body?.cancel(); checks.range416KeepsLogin = invalid.status === 416 && session.snapshot().user?.id === state.user.id;
  const oldToken = token; await session.logout(); checks.localLogout = !session.snapshot().user && token === '';
  const revoked = await fetch(config.server + '/auth/me', { headers: { Authorization: 'Bearer ' + oldToken }, redirect: 'error' });
  await revoked.body?.cancel(); checks.serverLogout = revoked.status === 401;
  const hashes = {};
  for (const name of ['session.cjs', 'credential-store.cjs']) hashes[name] = createHash('sha256').update(await fs.readFile(path.join(__dirname, '../src', name))).digest('hex');
  const report = { phase: 'CP-03', scope: 'Headless session service against the disposable real FastAPI backend; host/renderer integration and OS encryption pending', status: Object.values(checks).every(Boolean) ? 'partial-pass' : 'failed', node: process.version, checks, requests, sourceSha256: hashes, capturedAt: new Date().toISOString() };
  const text = JSON.stringify(report, null, 2);
  if (text.includes(oldToken) || text.includes(config.password)) throw new Error('Diagnostic contains a credential');
  await fs.writeFile(output, text + '\n');
  console.log(JSON.stringify({ status: report.status, checks }));
  if (report.status === 'failed') process.exitCode = 1;
})().catch(error => { console.error('Session contract diagnostic failed', { type: error.name, status: error.status }); process.exitCode = 1; });
