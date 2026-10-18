const { test } = require('node:test');
const assert = require('node:assert/strict');
const { DesktopSession } = require('../src/session.cjs');
const { CredentialStore } = require('../src/credential-store.cjs');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { createCipheriv, createDecipheriv, randomBytes } = require('node:crypto');
const user = (id = 1) => ({ id, username: 'account-' + id, is_admin: false, created_at: '2026-10-18' });
const json = (data, status = 200) => Response.json(data, { status });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const tick = () => new Promise(resolve => setImmediate(resolve));
function setup(handler = () => json([])) {
  const calls = [], saved = [];
  const session = new DesktopSession({ server: 'https://he.example', store: { load: async () => '', save: async (server, token) => { saved.push({ server, token }); return !!token; } }, fetch: async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith('/auth/status')) return json({ has_users: true });
    if (url.endsWith('/auth/login')) { const { username } = JSON.parse(options.body); const id = Number(username); return json({ access_token: 'opaque-secret-' + id, user: user(id) }); }
    if (url.endsWith('/auth/logout')) return json({});
    return handler(url, options);
  } });
  return { session, calls, saved };
}
test('desktop login keeps the opaque credential out of public snapshots and captures host headers', async () => {
  let requestHeaders;
  const { session, saved } = setup((_url, options) => { requestHeaders = options.headers; return new Response(null, { status: 416, headers: { 'Content-Range': 'bytes */30' } }); });
  const state = await session.login('1', 'private-password');
  assert.equal(state.user.id, 1); assert.equal(state.persistent, true);
  assert.ok(!JSON.stringify(state).includes('opaque-secret')); assert.ok(!JSON.stringify(state).includes('private-password'));
  const response = await session.request('/stream/3', { headers: { Range: 'bytes=99-', Authorization: 'Bearer injected', Cookie: 'injected', 'X-HE-Generation': state.generation } }, state.generation);
  assert.equal(response.status, 416); assert.equal(response.headers.get('Content-Range'), 'bytes */30');
  assert.equal(requestHeaders.get('Authorization'), 'Bearer opaque-secret-1');
  assert.equal(requestHeaders.get('Range'), 'bytes=99-'); assert.equal(requestHeaders.get('Cookie'), null);
  assert.equal(requestHeaders.get('X-HE-Generation'), null); assert.equal(session.snapshot().user.id, 1);
  assert.equal(saved.at(-1).token, 'opaque-secret-1');
  for (const route of ['https://evil.example/media', '//evil.example/media', '/auth/login', '/stream/3?token=secret']) await assert.rejects(session.request(route, {}, state.generation), { status: 400 });
});
test('a late old 401 cannot expire a new login, and old generation requests never retarget', async () => {
  const pending = deferred(); const { session, calls } = setup(() => pending.promise);
  const first = await session.login('1', 'pw');
  const old = session.request('/media', {}, first.generation); const oldResult = assert.rejects(old, { status: 409 });
  const second = await session.login('2', 'pw');
  pending.resolve(json({ detail: 'old unauthorized' }, 401)); await oldResult;
  assert.equal(session.snapshot().user.id, 2);
  assert.equal(calls.find(item => item.url.endsWith('/media')).options.headers.get('Authorization'), 'Bearer opaque-secret-1');
  const count = calls.length;
  await assert.rejects(session.request('/media', {}, first.generation), { status: 409 });
  assert.equal(calls.length, count); assert.notEqual(first.generation, second.generation);
});
test('same server/media writes remain serialized across account changes and discard unsent old intents', async () => {
  const pending = deferred(), writes = [];
  const { session } = setup((url, options) => {
    writes.push({ url, token: options.headers.get('Authorization'), body: JSON.parse(options.body) });
    return writes.length === 1 ? pending.promise : json({});
  });
  const first = await session.login('1', 'pw');
  const old = session.request('/media/9', { method: 'PATCH', body: '{"progress":10}' }, first.generation);
  const oldResult = assert.rejects(old, { status: 409 }); await tick();
  const queued = session.request('/media/9', { method: 'PATCH', body: '{"progress":11}' }, first.generation);
  const queuedResult = assert.rejects(queued, { status: 409 });
  const second = await session.login('2', 'pw');
  const current = session.request('/media/9', { method: 'PATCH', body: '{"progress":20}' }, second.generation);
  await tick(); assert.equal(writes.length, 1, 'new account must wait for old in-flight write');
  pending.resolve(json({})); await Promise.all([oldResult, queuedResult, current]);
  assert.deepEqual(writes.map(item => [item.token, item.body.progress]), [['Bearer opaque-secret-1', 10], ['Bearer opaque-secret-2', 20]]);
});
test('401 clears only current authorization and notifies host cleanup; 503 keeps the authorized identity', async () => {
  let status = 503; const cleanups = [];
  const { session, saved } = setup(() => json({}, status)); session.onInvalidate = reason => cleanups.push(reason);
  const state = await session.login('1', 'pw');
  assert.equal((await session.request('/media', {}, state.generation)).status, 503);
  assert.equal(session.snapshot().user.id, 1);
  status = 401; assert.equal((await session.request('/media', {}, state.generation)).status, 401);
  assert.equal(session.snapshot().user, null); assert.equal(saved.at(-1).token, ''); assert.equal(cleanups.at(-1), 'expired');
});
test('server switch clears authorization, cancels the old signal and rejects stale media resources', async () => {
  const { session, saved } = setup(); const first = await session.login('1', 'pw'); const identity = session.identity(first.generation);
  const state = await session.connect('https://other.example/');
  assert.equal(state.server, 'https://other.example'); assert.equal(state.user, null); assert.equal(identity.signal.aborted, true);
  assert.equal(saved.at(-1).token, ''); assert.equal(saved.at(-1).server, state.server);
  assert.throws(() => session.identity(first.generation), { status: 409 });
});
test('offline restore retains encrypted credential without admitting an unverified cached user', async () => {
  const { session, saved } = setup(); let online = false;
  session.store.load = async () => 'still-private';
  session.fetch = async url => {
    if (!online) throw new Error('offline');
    return url.endsWith('/auth/status') ? json({ has_users: true }) : json(user(3));
  };
  const offline = await session.restore(); assert.equal(offline.user, null); assert.ok(offline.error); assert.equal(saved.length, 0);
  online = true; const restored = await session.restore(); assert.equal(restored.user.id, 3); assert.equal(restored.persistent, true);
  assert.ok(!JSON.stringify(restored).includes('still-private'));
});
test('offline logout removes local login and never revokes a concurrent new identity', async () => {
  const { session, saved } = setup(); await session.login('1', 'pw');
  const pending = deferred(), revoked = [];
  const original = session.fetch;
  session.fetch = async (url, options) => {
    if (url.endsWith('/auth/logout')) { revoked.push(options.headers.Authorization); return pending.promise; }
    return original(url, options);
  };
  const logout = session.logout(); assert.equal(session.snapshot().user, null);
  await tick(); assert.equal(saved.at(-1).token, '');
  await session.login('2', 'pw'); pending.resolve(json({})); await logout;
  assert.equal(session.snapshot().user.id, 2); assert.deepEqual(revoked, ['Bearer opaque-secret-1']);
});
test('overlapping login responses cannot resurrect the earlier account', async () => {
  const { session } = setup(); const first = deferred(), second = deferred(); let count = 0;
  session.fetch = async () => (++count === 1 ? first.promise : second.promise);
  const one = session.login('1', 'pw'); const firstResult = assert.rejects(one, { status: 409 }); await tick();
  const two = session.login('2', 'pw'); await tick();
  second.resolve(json({ access_token: 'opaque-second', user: user(2) })); await two;
  first.resolve(json({ access_token: 'opaque-first', user: user(1) })); await firstResult;
  assert.equal(session.snapshot().user.id, 2);
});
test('credential file contains ciphertext, is server-bound, and an ordered logout cannot be overwritten', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'he-vault-test-')), file = path.join(directory, 'login.json');
  const key = randomBytes(32), iv = randomBytes(16);
  const cipher = { isEncryptionAvailable: () => true,
    encryptString: value => { const c = createCipheriv('aes-256-cbc', key, iv); return Buffer.concat([c.update(value, 'utf8'), c.final()]); },
    decryptString: value => { const c = createDecipheriv('aes-256-cbc', key, iv); return Buffer.concat([c.update(value), c.final()]).toString(); } };
  try {
    const store = new CredentialStore(file, cipher);
    await store.save('https://he.example', 'opaque-file-secret');
    assert.ok(!(await fs.readFile(file, 'utf8')).includes('opaque-file-secret'));
    assert.equal(await store.load('https://he.example'), 'opaque-file-secret'); assert.equal(await store.load('https://other.example'), '');
    if (process.platform !== 'win32') assert.equal((await fs.stat(file)).mode & 0o777, 0o600);
    await Promise.all([store.save('https://he.example', 'older-login'), store.save('https://he.example', '')]);
    await assert.rejects(fs.access(file));
    cipher.isEncryptionAvailable = () => false;
    assert.equal(await store.save('https://he.example', 'never-plaintext'), false); await assert.rejects(fs.access(file));
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
});
test('native media is admitted only after actual detail verification in the current identity', async () => {
  const { session } = setup(() => json({ id: 7 }));
  const state = await session.login('1', 'pw');
  const resource = 'he://app/manga/7/page/0?track_progress=true&he_session=' + state.generation;
  assert.throws(() => session.mediaSource(resource), { status: 403 });
  await session.request('/media?limit=60&offset=0', {}, state.generation);
  assert.throws(() => session.mediaSource(resource), { status: 403 }, 'listing/preloading never admits a native open');
  await session.request('/media/7', {}, state.generation);
  const source = session.mediaSource(resource);
  assert.equal(new URL(source.url).searchParams.get('track_progress'), 'false');
  assert.equal(new URL(source.url).searchParams.has('he_session'), false);
  assert.equal(source.headers.Authorization, 'Bearer opaque-secret-1');
  assert.throws(() => session.mediaSource(resource + '&token=leaked'), { status: 400 });
  await session.logout(); const next = await session.login('2', 'pw');
  assert.throws(() => session.mediaSource(resource), { status: 409 });
  assert.throws(() => session.mediaSource('he://app/stream/7?he_session=' + next.generation), { status: 403 });
});
test('OS encryption uses async methods and a new profile does not query Keychain', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'he-async-vault-'));
  const availability = deferred(); let requests = 0;
  const cipher = {
    isAsyncEncryptionAvailable: () => { requests++; return availability.promise; },
    encryptStringAsync: async token => Buffer.from('cipher:' + token),
    decryptStringAsync: async bytes => ({ result: bytes.toString().slice(7), shouldReEncrypt: false }),
    isEncryptionAvailable: () => { throw new Error('Synchronous OS access must not run'); },
    encryptString: () => { throw new Error('Synchronous encryption must not run'); },
  };
  try {
    const store = new CredentialStore(path.join(directory, 'login.json'), cipher);
    assert.equal(await store.load('https://he.example'), ''); assert.equal(requests, 0);
    const save = store.save('https://he.example', 'test-private'); await tick(); assert.equal(requests, 1);
    availability.resolve(true); await save;
    assert.equal(await store.load('https://he.example'), 'test-private');
    assert.equal(JSON.parse(await fs.readFile(store.file, 'utf8')).scheme, 'async');
    await store.save('https://he.example', '');
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
});
test('restore exposes a recoverable terminal state if host cleanup fails', async () => {
  const { session } = setup();
  session.onInvalidate = async () => { throw new Error('Host cleanup failed'); };
  const state = await session.restore(); assert.equal(state.restoring, false); assert.equal(state.user, null); assert.ok(state.error);
});

const patch = (session, generation, progress, scene = 'scene-a') => session.request('/media/7', {
  method: 'PATCH', body: new TextEncoder().encode(JSON.stringify({ progress })).buffer,
  headers: { 'Content-Type': 'application/json', 'X-HE-Media-Session': scene },
}, generation);
test('slow progress coalesces pending ArrayBuffer bodies, with independent responses and metadata barriers', async () => {
  const pending = deferred(), sent = [];
  const { session } = setup((_url, options) => {
    assert.equal(options.headers.get('X-HE-Media-Session'), null);
    const value = JSON.parse(typeof options.body === 'string' ? options.body : Buffer.from(options.body).toString());
    sent.push(value); return sent.length === 1 ? pending.promise : json({ id: 7, ...value });
  });
  const { generation } = await session.login('1', 'pw');
  const first = patch(session, generation, 1);
  const second = patch(session, generation, 2), third = patch(session, generation, 3);
  const metadata = session.request('/media/7', { method: 'PATCH', body: '{"favorite":true}' }, generation);
  const fourth = patch(session, generation, 4), fifth = patch(session, generation, 5);
  assert.deepEqual(sent, [{ progress: 1 }]);
  pending.resolve(json({ id: 7, progress: 1 }));
  const result = await Promise.all([first, second, third, metadata, fourth, fifth]);
  assert.deepEqual(sent, [{ progress: 1 }, { progress: 3 }, { favorite: true }, { progress: 5 }]);
  assert.deepEqual(await Promise.all(result.map(response => response.json())), [
    { id: 7, progress: 1 }, { id: 7, progress: 3 }, { id: 7, progress: 3 }, { id: 7, favorite: true }, { id: 7, progress: 5 }, { id: 7, progress: 5 },
  ]);
});
test('different player scenes never merge; a re-open waits for old writes before verifying detail', async () => {
  const pending = deferred(), sent = []; let position = 0;
  const { session } = setup((_url, options) => {
    if (options.method === 'PATCH') {
      const value = JSON.parse(Buffer.from(options.body).toString()); sent.push(value.progress);
      if (sent.length === 1) return pending.promise.then(() => { position = value.progress; return json({ id: 7, progress: position }); });
      position = value.progress;
    } else sent.push('open');
    return json({ id: 7, progress: position });
  });
  const { generation } = await session.login('1', 'pw');
  const first = patch(session, generation, 1);
  const oldScene = patch(session, generation, 2, 'old');
  const newScene = patch(session, generation, 3, 'new');
  const open = session.request('/media/7', {}, generation);
  await tick(); assert.deepEqual(sent, [1]);
  pending.resolve(); await Promise.all([first, oldScene, newScene]);
  assert.equal((await (await open).json()).progress, 3); assert.deepEqual(sent, [1, 2, 3, 'open']);
});
test('multi-page zero and its viewing repair are one logical write; single-page keeps viewed', async () => {
  const repair = deferred(), sent = []; let pages = 4;
  const { session } = setup((_url, options) => {
    const body = JSON.parse(typeof options.body === 'string' ? options.body : Buffer.from(options.body).toString()); sent.push(body);
    if (body.view_status) return repair.promise;
    return json({ id: 7, media_type: 'manga', page_count: pages, progress: body.progress, view_status: pages === 1 ? 'viewed' : 'unviewed' });
  });
  const { generation } = await session.login('1', 'pw');
  const zero = patch(session, generation, 0); await tick();
  assert.deepEqual(sent, [{ progress: 0 }, { view_status: 'viewing' }]);
  const last = patch(session, generation, 3); await tick(); assert.equal(sent.length, 2);
  repair.resolve(json({ id: 7, progress: 0, view_status: 'viewing' }));
  assert.equal((await (await zero).json()).view_status, 'viewing'); await last;
  assert.deepEqual(sent.at(-1), { progress: 3 });
  pages = 1;
  const single = await patch(session, generation, 0);
  assert.equal((await single.json()).view_status, 'viewed'); assert.equal(sent.length, 4);
});
test('a superseded zero-page repair never retries over a newer last-page intent', async () => {
  const failed = deferred(), sent = [];
  const { session } = setup((_url, options) => {
    const body = JSON.parse(typeof options.body === 'string' ? options.body : Buffer.from(options.body).toString()); sent.push(body);
    if (body.view_status) return failed.promise;
    return json({ id: 7, media_type: 'manga', page_count: 4, progress: body.progress, view_status: body.progress === 3 ? 'viewed' : 'unviewed' });
  });
  const { generation } = await session.login('1', 'pw');
  const zero = patch(session, generation, 0); await tick();
  const last = patch(session, generation, 3);
  failed.resolve(json({ detail: 'temporary' }, 503)); await zero;
  assert.equal((await (await last).json()).view_status, 'viewed');
  assert.deepEqual(sent, [{ progress: 0 }, { view_status: 'viewing' }, { progress: 3 }]);
});
test('a still-current zero-page repair retries a temporary server failure', async () => {
  const sent = [];
  const { session } = setup((_url, options) => {
    const body = JSON.parse(typeof options.body === 'string' ? options.body : Buffer.from(options.body).toString()); sent.push(body);
    if (body.view_status) return sent.length === 2 ? json({}, 503) : json({ id: 7, progress: 0, view_status: 'viewing' });
    return json({ id: 7, media_type: 'manga', page_count: 4, progress: 0, view_status: 'unviewed' });
  });
  const { generation } = await session.login('1', 'pw');
  assert.equal((await (await patch(session, generation, 0)).json()).view_status, 'viewing');
  assert.equal(sent.length, 3);
});
test('aborted queued opens do not mark a media item opened or issue a side-effecting GET', async () => {
  const pending = deferred(); let opens = 0;
  const { session } = setup((_url, options) => {
    if (options.method === 'PATCH') return pending.promise;
    opens++; return json({ id: 7 });
  });
  const { generation } = await session.login('1', 'pw');
  const write = patch(session, generation, 4), abort = new AbortController();
  const opening = session.request('/media/7', { signal: abort.signal }, generation);
  const rejected = assert.rejects(opening, { status: 409 }); abort.abort();
  pending.resolve(json({ id: 7 })); await Promise.all([write, rejected]);
  assert.equal(opens, 0);
  assert.throws(() => session.mediaSource('he://app/stream/7?he_session=' + generation), { status: 403 });
});

test('finite detail 401 is buffered before identity cancellation and still clears login', async () => {
  const { session } = setup(() => json({ detail: 'expired' }, 401));
  const { generation } = await session.login('1', 'pw');
  const response = await session.request('/media/7', {}, generation);
  assert.equal(response.status, 401); assert.deepEqual(await response.json(), { detail: 'expired' });
  assert.equal(session.snapshot().user, null);
});
