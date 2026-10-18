// Actual FastAPI matrix over two explicitly disposable diagnostic configurations.
// This is service evidence; packaged UI and OS persistence have separate gates.
const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { DesktopSession } = require('../src/session.cjs');
(async () => {
  const output = process.env.HE_DESKTOP_MATRIX_OUTPUT;
  if (!output || !process.env.HE_DESKTOP_MATRIX_A || !process.env.HE_DESKTOP_MATRIX_B) throw new Error('Explicit private matrix configurations required');
  const configs = await Promise.all([process.env.HE_DESKTOP_MATRIX_A, process.env.HE_DESKTOP_MATRIX_B].map(async name => JSON.parse(await fs.readFile(name, 'utf8'))));
  if (configs.some(config => !config.expectedTotal || !config.secondaryUser) || configs[0].server === configs[1].server) throw new Error('Independent matrix fixtures required');
  const checks = {}, requests = [], credentials = [];
  let record = null, offline = false, held = null;
  const store = {
    load: async server => record?.server === server ? record.token : '',
    save: async (server, token) => { record = token ? { server, token } : null; if (token) credentials.push({ server, token }); return !!token; },
  };
  const fetcher = async (url, options) => {
    if (offline) throw new Error('Synthetic offline transport');
    const parsed = new URL(url);
    requests.push({ server: parsed.origin === new URL(configs[0].server).origin ? 'A' : 'B', method: options.method || 'GET', path: parsed.pathname, credentialInUrl: parsed.searchParams.has('token'), bearer: new Headers(options.headers).has('Authorization') });
    const response = await fetch(url, { ...options, signal: AbortSignal.any([AbortSignal.timeout(10000), ...(options.signal ? [options.signal] : [])]) });
    if (held && parsed.pathname === '/media' && parsed.searchParams.get('limit') === '1') {
      held.ready(); await held.promise;
    }
    return response;
  };
  const makeSession = server => new DesktopSession({ server, store, fetch: fetcher });
  const session = makeSession(configs[0].server);
  const check = (name, condition) => { checks[name] = !!condition; if (!condition) throw new Error(name); };
  const read = async (route, current = session) => {
    const response = await current.request(route, {}, current.snapshot().generation);
    const data = await response.json(); if (!response.ok) throw new Error('Unexpected service response');
    return { data, total: Number(response.headers.get('x-total-count')) };
  };
  const patch = async (id, value) => {
    const response = await session.request('/media/' + id, { method: 'PATCH', headers: { 'Content-Type': 'application/json', 'X-HE-Media-Session': 'matrix-scene' }, body: JSON.stringify(value) }, session.snapshot().generation);
    if (!response.ok) throw new Error('Unexpected patch response');
    return response.json();
  };
  let stage = 'login';
  try {
    const [a, b] = configs;
    const initial = await session.login(a.username, a.password);
    stage = 'pagination-and-filters';
    const first = await read('/media?limit=60&offset=0'), second = await read('/media?limit=60&offset=60');
    check('realPaginationBeyond60', first.total === a.expectedTotal && first.data.length === 60 && second.data.length === a.expectedTotal - 60 && new Set([...first.data, ...second.data].map(item => item.id)).size === a.expectedTotal);
    check('listDoesNotOpenDetails', !requests.some(request => /^\/media\/\d+$/.test(request.path)));
    const query = async params => read('/media?' + new URLSearchParams({ limit: '60', offset: '0', ...params }));
    const search = await query({ search: 'CP-03 A paged image' });
    check('searchTotalAndPageBound', search.total === 62 && search.data.length === 60 && search.data.every(item => item.title.includes('CP-03 A paged image')));
    const filtered = await query({ media_type: 'image', favorite: 'true', tag: 'CP03-A', source_site: 'local', view_status: 'unviewed' });
    check('combinedFiltersUseActualFields', filtered.total === 11 && filtered.data.every(item => item.media_type === 'image' && item.favorite && item.tags.some(tag => tag.name === 'CP03-A') && item.source_site === null && item.view_status === 'unviewed'));
    const remote = await query({ source_site: 'pixiv', tag: 'CP03-B' });
    check('sourceAndNamedTagFilter', remote.total === 31 && remote.data.every(item => item.source_site === 'pixiv' && item.tags.some(tag => tag.name === 'CP03-B')));
    const ordered = await query({ sort: 'rating' });
    check('ratingOrder', ordered.data.every((item, index, all) => !index || all[index - 1].rating >= item.rating));
    const titles = await query({ sort: 'title' });
    check('titleOrder', titles.data.every((item, index, all) => !index || all[index - 1].title <= item.title));
    const continuing = await query({ sort: 'opened', view_status: 'viewing' });
    check('continuationUsesViewingOpened', continuing.data.every(item => item.view_status === 'viewing') && continuing.data[0].id === a.videoId);
    stage = 'actual-open-and-narrow-metadata';
    const unopened = session.snapshot().generation;
    let blocked = false; try { session.mediaSource('he://app/stream/' + a.videoId + '?he_session=' + unopened); } catch (error) { blocked = error.status === 403; }
    check('listCannotAuthorizeNativePlayback', blocked);
    const detail = (await read('/media/' + a.videoId)).data;
    check('actualDetailUpdatesOpened', !!detail.last_opened_at && detail.view_status === 'viewing');
    const changed = await patch(a.videoId, { favorite: !detail.favorite });
    const rated = await patch(a.videoId, { rating: 5 });
    check('favoriteRatingPreserveProgress', changed.favorite === !detail.favorite && changed.progress === detail.progress && rated.rating === 5 && rated.progress === detail.progress && rated.duration === detail.duration);
    await patch(a.videoId, { favorite: detail.favorite, rating: detail.rating });
    stage = 'single-page-and-prefetch';
    const manga = (await read('/media/' + a.singleMangaId)).data;
    const single = await patch(manga.id, { progress: 0 });
    check('singlePageKeepsServerViewed', single.progress === 0 && single.view_status === 'viewed');
    const before = (await query({ media_type: 'manga' })).data.find(item => item.id === a.mangaId);
    const page = await session.request('/manga/' + a.mangaId + '/page/0?track_progress=false', {}, session.snapshot().generation);
    const cover = await session.request('/thumbnails/cp02-portrait.png', {}, session.snapshot().generation);
    check('protectedPageAndCoverRead', page.ok && cover.ok && (await page.arrayBuffer()).byteLength > 0 && (await cover.arrayBuffer()).byteLength > 0);
    const after = (await query({ media_type: 'manga' })).data.find(item => item.id === a.mangaId);
    check('prefetchPreservesUnopenedMedia', after.progress === before.progress && after.view_status === before.view_status && after.last_opened_at === before.last_opened_at);
    stage = 'late-401-and-account-switch';
    const token = record.token, oldGeneration = session.snapshot().generation;
    await (await fetch(a.server + '/auth/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + token } })).body?.cancel();
    let release, ready;
    const readyPromise = new Promise(resolve => { ready = resolve; });
    held = { promise: new Promise(resolve => { release = resolve; }), ready, release: () => release() };
    const oldRequest = session.request('/media?limit=1', {}, oldGeneration).then(() => false, error => error.status === 409);
    await Promise.race([readyPromise, oldRequest.then(() => { throw new Error('Late response did not arrive'); })]);
    const account = await session.login(a.secondaryUser.username, a.secondaryUser.password);
    release(); held = null;
    check('lateReal401CannotExpireNewAccount', await oldRequest && session.snapshot().user.id === account.user.id);
    check('differentAccountHasFreshIdentity', account.generation !== oldGeneration && account.user.id !== initial.user.id);
    let oldResource = false; try { session.mediaSource('he://app/stream/' + a.videoId + '?he_session=' + oldGeneration); } catch (error) { oldResource = error.status === 409; }
    check('oldAccountResourceIsRejected', oldResource);
    offline = true;
    const disconnected = await session.request('/media?limit=60', {}, account.generation).then(() => false, error => error.status === 503);
    check('offlineReadKeepsIdentity', disconnected && session.snapshot().user.id === account.user.id);
    offline = false;
    check('networkRecoveryUsesCurrentIdentity', (await read('/media?limit=60')).data.length === 60);
    stage = 'server-switch-and-restore';
    const other = await session.connect(b.server);
    check('switchServerClearsAccount', !other.user && other.server === b.server && other.generation !== account.generation);
    await session.login(b.username, b.password);
    const otherItems = await read('/media?limit=60&search=CP-03%20B%20paged%20image');
    check('otherServerDataIsSeparate', otherItems.total === 62 && otherItems.data.every(item => item.title.includes('CP-03 B ')));
    const restored = makeSession(b.server);
    offline = true;
    const unavailable = await restored.restore();
    check('offlineRestoreKeepsCipherRecordWithoutUser', !unavailable.user && !!unavailable.error && !!record?.token);
    offline = false;
    const state = await restored.restore();
    check('retryRestoreVerifiesActualAccount', !!state.user && state.persistent && !state.restoring);
    const activeToken = record.token;
    await (await fetch(b.server + '/auth/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + activeToken } })).body?.cancel();
    const expired = await restored.request('/media?limit=60', {}, state.generation); await expired.body?.cancel();
    check('realCurrent401ClearsAccountAndRecord', expired.status === 401 && !restored.snapshot().user && !record);
    check('noCredentialURLsOrReports', requests.every(request => !request.credentialInUrl));
  } catch (error) {
    checks[stage + ':completed'] = false;
    console.error('Matrix diagnostic failed', { stage, type: error.name, check: Object.hasOwn(checks, error.message) ? error.message : undefined });
  } finally {
    offline = false;
    if (held) { held.release(); held = null; }
    for (const credential of credentials) try { await (await fetch(credential.server + '/auth/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + credential.token }, signal: AbortSignal.timeout(3000) })).body?.cancel(); } catch {}
    const hashes = {};
    for (const name of ['session.cjs', 'credential-store.cjs', 'media-queue.cjs']) hashes[name] = createHash('sha256').update(await fs.readFile(path.join(__dirname, '../src', name))).digest('hex');
    const report = { phase: 'CP-03', scope: 'Headless DesktopSession over two disposable real FastAPI servers with 69 items and two accounts each; packaged identity UI and OS restart are separate gates', status: Object.values(checks).every(Boolean) ? 'partial-pass' : 'failed', node: process.version, probeSha256: createHash('sha256').update(await fs.readFile(__filename)).digest('hex'), checks, requests, sourceSha256: hashes, capturedAt: new Date().toISOString() };
    const text = JSON.stringify(report, null, 2);
    for (const credential of credentials) if (text.includes(credential.token)) throw new Error('Credential in diagnostic');
    for (const config of configs) if (text.includes(config.password) || text.includes(config.secondaryUser.password)) throw new Error('Credential in diagnostic');
    await fs.writeFile(output, text + '\n');
    console.log(JSON.stringify({ status: report.status, checks }));
    if (report.status === 'failed') process.exitCode = 1;
  }
})().catch(error => { console.error('Matrix startup failed', { type: error.name }); process.exitCode = 1; });
