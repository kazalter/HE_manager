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
      const request = { method: options.method || 'GET', path: parsed.pathname, bearer: new Headers(options.headers).has('Authorization') };
      if (request.method === 'PATCH' && /^\/media\/\d+$/.test(parsed.pathname)) {
        const body = JSON.parse(typeof options.body === 'string' ? options.body : Buffer.from(options.body).toString());
        request.fields = Object.keys(body);
        if (Number.isSafeInteger(body.progress)) request.progress = body.progress;
        if (['unviewed', 'viewing', 'viewed'].includes(body.view_status)) request.viewStatus = body.view_status;
      }
      requests.push(request);
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
  if (config.mangaId) {
    const route = '/media/' + config.mangaId;
    const opened = await session.request(route, {}, state.generation); const manga = await opened.json();
    const progress = value => session.request(route, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-HE-Media-Session': 'contract-reader' }, body: new TextEncoder().encode(JSON.stringify({ progress: value })).buffer }, state.generation);
    const zero = await progress(0); const firstPage = await zero.json();
    checks.zeroPageCompatibility = zero.ok && firstPage.progress === 0 && firstPage.view_status === (manga.page_count > 1 ? 'viewing' : 'viewed');
    const last = await progress(manga.page_count - 1); const lastPage = await last.json();
    checks.lastPageAuthoritative = last.ok && lastPage.progress === manga.page_count - 1 && lastPage.view_status === 'viewed';
    const lastIndex = requests.length - 1;
    const reopened = await session.request(route, {}, state.generation);
    checks.reopenedLatestProgress = (await reopened.json()).progress === manga.page_count - 1;
    const source = session.mediaSource('he://app/manga/' + manga.id + '/page/0?track_progress=true&he_session=' + state.generation);
    const page = await fetch(source.url, { headers: source.headers }); await page.arrayBuffer();
    const afterPrefetch = await session.request(route, {}, state.generation);
    checks.prefetchDoesNotChangeProgress = page.ok && (await afterPrefetch.json()).progress === manga.page_count - 1;
    checks.zeroWritesOrdered = requests.slice(0, lastIndex).some((request, index, all) => request.path === route && request.method === 'PATCH' && request.progress === 0 && all[index + 1]?.path === route && all[index + 1]?.method === 'PATCH' && all[index + 1]?.viewStatus === 'viewing');
    await (await progress(manga.progress || 0)).body?.cancel();
    await (await session.request(route, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ view_status: manga.view_status }) }, state.generation)).body?.cancel();
  }
  const oldToken = token; await session.logout(); checks.localLogout = !session.snapshot().user && token === '';
  const revoked = await fetch(config.server + '/auth/me', { headers: { Authorization: 'Bearer ' + oldToken }, redirect: 'error' });
  await revoked.body?.cancel(); checks.serverLogout = revoked.status === 401;
  const hashes = {};
  for (const name of ['session.cjs', 'credential-store.cjs', 'media-queue.cjs']) hashes[name] = createHash('sha256').update(await fs.readFile(path.join(__dirname, '../src', name))).digest('hex');
  const report = { phase: 'CP-03', scope: 'Headless session service against the disposable real FastAPI backend; host/renderer integration and OS encryption pending', status: Object.values(checks).every(Boolean) ? 'partial-pass' : 'failed', node: process.version, checks, requests, sourceSha256: hashes, capturedAt: new Date().toISOString() };
  const text = JSON.stringify(report, null, 2);
  if (text.includes(oldToken) || text.includes(config.password)) throw new Error('Diagnostic contains a credential');
  await fs.writeFile(output, text + '\n');
  console.log(JSON.stringify({ status: report.status, checks }));
  if (report.status === 'failed') process.exitCode = 1;
})().catch(error => { console.error('Session contract diagnostic failed', { type: error.name, status: error.status }); process.exitCode = 1; });
