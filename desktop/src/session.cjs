const { randomUUID } = require('node:crypto');
const { MediaQueue } = require('./media-queue.cjs');
const { setTimeout: delay } = require('node:timers/promises');
const { serverUrl, mediaRequest, API_PATH } = require('./policy.cjs');
class SessionError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
const stale = () => new SessionError(409, '登录或服务器已改变，请重试');
function userValue(value) {
  if (!value || !Number.isSafeInteger(value.id) || value.id < 1 || typeof value.username !== 'string' || typeof value.is_admin !== 'boolean') throw new SessionError(502, '服务器返回的账号信息无效');
  return { id: value.id, username: value.username, is_admin: value.is_admin, is_active: value.is_active !== false, created_at: value.created_at };
}
// This object belongs to main. snapshot() is the only page-facing representation.
class DesktopSession {
  #token = ''; #user = null; #generation = randomUUID(); #cancel = new AbortController();
  #revision = 0; #opened = new Set();
  #operation = 0; #save = Promise.resolve(); #cleanup = Promise.resolve(); #writes = new MediaQueue();
  constructor({ server = '', store, fetch: fetcher = fetch, onInvalidate = () => {}, onChange = () => {} }) {
    this.server = server ? serverUrl(server) : ''; this.store = store; this.fetch = fetcher;
    this.onInvalidate = onInvalidate; this.onChange = onChange; this.restoring = false; this.hasUsers = true; this.error = ''; this.persisted = false;
  }
  snapshot() {
    return { server: this.server, generation: this.#generation, revision: this.#revision, user: this.#user ? { ...this.#user } : null,
      hasUsers: this.hasUsers, error: this.error, persistent: this.persisted, restoring: this.restoring };
  }
  #publish() { ++this.#revision; this.onChange(this.snapshot()); }
  #persist() {
    const server = this.server, token = this.#token;
    this.#save = this.#save.catch(() => {}).then(async () => {
      try { const saved = await this.store.save(server, token); if (this.server === server && this.#token === token) this.persisted = saved; }
      catch { if (this.server === server && this.#token === token) this.persisted = false; }
    });
    return this.#save;
  }
  #invalidate(reason) {
    this.#cancel.abort(); this.#cancel = new AbortController(); this.#generation = randomUUID();
    this.#token = ''; this.#user = null; this.#opened.clear(); this.restoring = reason === 'restore'; this.error = reason === 'expired' ? '登录已过期，请重新登录' : ''; this.persisted = false;
    this.#cleanup = this.#cleanup.catch(() => {}).then(() => this.onInvalidate(reason));
    this.#publish();
  }
  #current(generation) { if (generation !== this.#generation) throw stale(); }
  async #send(server, route, options = {}, signal) {
    const timeout = new AbortController();
    const timer = setTimeout(() => timeout.abort(), 15000); timer.unref?.();
    try { return await this.fetch(server + route, { ...options, redirect: 'error', signal: AbortSignal.any([timeout.signal, ...(signal ? [signal] : []), ...(options.signal ? [options.signal] : [])]) }); }
    catch {
      if (signal?.aborted || options.signal?.aborted) throw stale();
      throw new SessionError(503, timeout.signal.aborted ? '连接服务器超时，请重试' : '无法连接服务器，请检查网络');
    } finally { clearTimeout(timer); } // Bound headers, not the lifetime of audio/SSE response bodies.
  }
  async #status(server, signal) {
    const response = await this.#send(server, '/auth/status', {}, signal);
    if (!response.ok) { await response.body?.cancel(); throw new SessionError(502, '无法读取服务器登录状态'); }
    let data;
    try { data = await response.json(); } catch { throw new SessionError(502, '这个地址不是 HE Manager 服务'); }
    if (typeof data.has_users !== 'boolean') throw new SessionError(502, '这个地址不是 HE Manager 服务');
    return data.has_users;
  }
  async connect(value) {
    const server = serverUrl(value), operation = ++this.#operation;
    const hasUsers = await this.#status(server);
    if (operation !== this.#operation) throw stale();
    this.#invalidate('server'); this.server = server; this.hasUsers = hasUsers;
    await this.#persist(); await this.#cleanup;
    this.#publish(); return this.snapshot();
  }
  async restore() {
    const operation = ++this.#operation;
    this.#invalidate('restore'); const generation = this.#generation;
    try {
      await this.#cleanup; this.#current(generation);
      if (this.server) {
        const token = await this.store.load(this.server);
        this.#current(generation);
        if (operation !== this.#operation) throw stale();
        this.hasUsers = await this.#status(this.server, this.#cancel.signal);
        this.#current(generation);
        if (token) {
          const response = await this.#send(this.server, '/auth/me', { headers: { Authorization: 'Bearer ' + token } }, this.#cancel.signal);
          this.#current(generation);
          if (response.status === 401) {
            await response.body?.cancel(); await this.store.save(this.server, '');
          } else if (!response.ok) {
            await response.body?.cancel(); throw new SessionError(response.status, '无法验证登录状态，请重试');
          } else {
            const user = userValue(await response.json()); this.#current(generation);
            this.#token = token; this.#user = user; this.persisted = true;
          }
        }
      }
      this.error = '';
    } catch (error) {
      this.#current(generation);
      // A network outage does not delete the encrypted login; no cached identity is admitted.
      this.error = error instanceof SessionError ? error.message : '无法验证登录状态，请重试';
    }
    this.restoring = false; this.#publish(); return this.snapshot();
  }
  async login(username, password, bootstrap = false) {
    if (!this.server) throw new SessionError(503, '请先连接 HE Manager 服务器');
    if (typeof username !== 'string' || !username.trim() || username.length > 256 || typeof password !== 'string' || !password || password.length > 4096) throw new SessionError(400, '请输入用户名和密码');
    ++this.#operation; this.#invalidate('login'); const generation = this.#generation;
    await this.#persist(); await this.#cleanup; this.#current(generation);
    const response = await this.#send(this.server, bootstrap ? '/auth/bootstrap' : '/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.trim(), password, ...(bootstrap ? { is_admin: true } : {}) }),
    }, this.#cancel.signal);
    this.#current(generation);
    if (!response.ok) {
      await response.body?.cancel();
      throw new SessionError(response.status, response.status === 401 ? '用户名或密码错误' : response.status === 429 ? '登录失败次数过多，请稍后再试' : '登录失败，请重试');
    }
    let data;
    try { data = await response.json(); } catch { throw new SessionError(502, '服务器返回的登录信息无效'); }
    this.#current(generation);
    if (typeof data.access_token !== 'string' || !data.access_token || data.access_token.length > 16000 || /[\r\n]/.test(data.access_token)) throw new SessionError(502, '服务器返回的登录信息无效');
    const user = userValue(data.user);
    this.#token = data.access_token; this.#user = user; this.hasUsers = true;
    await this.#persist(); this.#current(generation); this.#publish(); return this.snapshot();
  }
  async logout() {
    const server = this.server, token = this.#token;
    ++this.#operation; this.#invalidate('logout');
    const local = Promise.all([this.#persist(), this.#cleanup]);
    // Revoke the captured old identity; a concurrent new login must never be revoked.
    const revoke = token ? this.#send(server, '/auth/logout', { method: 'POST', headers: { Authorization: 'Bearer ' + token } }, AbortSignal.timeout(4000)).then(response => response.body?.cancel()).catch(() => {}) : Promise.resolve();
    await Promise.all([local, revoke]); return this.snapshot();
  }
  identity(generation) {
    this.#current(generation);
    if (!this.#user || !this.#token) throw new SessionError(401, '请先登录');
    return { server: this.server, userId: this.#user.id, generation, token: this.#token, signal: this.#cancel.signal };
  }
  async expire(generation) {
    if (generation !== this.#generation) return;
    this.#invalidate('expired'); await this.#persist(); await this.#cleanup;
  }
  mediaSource(value) {
    const url = new URL(value, 'he://app');
    if (url.searchParams.has('token')) throw new SessionError(400, '媒体地址不能包含登录凭据');
    const generation = url.searchParams.get('he_session');
    const identity = this.identity(generation);
    url.searchParams.delete('he_session');
    const source = mediaRequest(identity.server, url.href);
    const pathname = new URL(source.url).pathname.slice(new URL(identity.server).pathname.replace(/\/$/, '').length);
    const mediaId = /^\/(?:stream|manga)\/(\d+)/.exec(pathname)?.[1];
    if (mediaId && !this.#opened.has(Number(mediaId))) throw new SessionError(403, '请先打开并验证作品');
    if (/^\/manga\/\d+\/page\/\d+$/.test(pathname)) {
      const target = new URL(source.url); target.searchParams.set('track_progress', 'false'); source.url = target.href;
    }
    return { ...source, token: identity.token, headers: { Authorization: 'Bearer ' + identity.token }, generation };
  }
  async request(route, options = {}, generation) {
    const identity = this.identity(generation), parsed = new URL(route, 'he://app');
    if (parsed.protocol !== 'he:' || parsed.host !== 'app' || parsed.username || parsed.password || !API_PATH.test(parsed.pathname) || parsed.pathname.startsWith('/auth') || parsed.searchParams.has('token') || parsed.hash) throw new SessionError(400, '不允许的服务器请求');
    const pathname = parsed.pathname + parsed.search;
    const headers = new Headers(options.headers);
    const scene = headers.get('x-he-media-session') || '';
    for (const name of ['authorization', 'cookie', 'host', 'origin', 'referer', 'connection', 'accept-encoding', 'content-length', 'x-he-generation', 'x-he-media-session']) headers.delete(name);
    headers.set('Authorization', 'Bearer ' + identity.token);
    const method = (options.method || 'GET').toUpperCase();
    const media = /^\/media\/(\d+)$/.exec(parsed.pathname);
    const writing = method === 'PATCH' && !!media;
    const opening = method === 'GET' && !!media;
    const execute = async (body = options.body, signal) => {
      this.#current(generation);
      const response = await this.#send(identity.server, pathname, { ...options, body, headers,
        signal: signal || (writing ? undefined : options.signal) }, writing ? undefined : identity.signal);
      if (generation !== this.#generation || signal?.aborted) { await response.body?.cancel(); throw stale(); }
      if (response.status === 401 && !writing && !opening) await this.expire(generation);
      return response;
    };
    if (!writing && !opening) return execute();
    let payload;
    if (writing && options.body !== undefined) {
      try {
        const text = typeof options.body === 'string' ? options.body :
          options.body instanceof ArrayBuffer ? Buffer.from(options.body).toString('utf8') :
          ArrayBuffer.isView(options.body) ? Buffer.from(options.body.buffer, options.body.byteOffset, options.body.byteLength).toString('utf8') : '';
        payload = JSON.parse(text);
      } catch { /* Invalid JSON is rejected by the server. */ }
    }
    const progress = payload && typeof payload === 'object' && !Array.isArray(payload) &&
      Object.hasOwn(payload, 'progress') && Object.keys(payload).every(key => ['progress', 'duration'].includes(key));
    const packet = await this.#writes.enqueue(identity.server + '\0' + media[1], {
      kind: opening ? 'open' : progress ? 'progress' : 'metadata', scope: generation + '\0' + scene,
      run: async isLatest => {
        this.#current(generation);
        if (opening && options.signal?.aborted) throw stale();
        const timeout = new AbortController();
        // Headers and the finite JSON body are bounded; media/SSE bodies use the streaming path above.
        const signal = AbortSignal.any([timeout.signal, ...(opening ? [identity.signal, ...(options.signal ? [options.signal] : [])] : [])]);
        let timer;
        const expired = new Promise((_, reject) => {
          timer = setTimeout(() => { timeout.abort(); reject(new SessionError(503, '保存或读取作品超时，请重试')); }, 30000);
          timer.unref?.();
        });
        const collect = async response => {
          const chunks = []; let size = 0;
          const reader = response.body?.getReader();
          const cancel = () => { void reader?.cancel().catch(() => {}); };
          signal.addEventListener('abort', cancel, { once: true });
          try {
            if (reader) while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              if (signal.aborted) throw stale();
              size += value.byteLength;
              if (size > 4 * 1024 * 1024) throw new SessionError(502, '作品响应过大');
              chunks.push(Buffer.from(value));
            }
          } catch (error) { cancel(); throw error; }
          finally { signal.removeEventListener('abort', cancel); }
          if (signal.aborted) throw stale();
          const bytes = Buffer.concat(chunks);
          let data;
          try { data = JSON.parse(bytes.toString('utf8')); } catch { /* Keep the original HTTP response. */ }
          return { status: response.status, statusText: response.statusText, headers: [...response.headers], bytes, data };
        };
        const operation = async () => {
          let result = await collect(await execute(options.body, signal));
          if (result.status >= 200 && result.status < 300) {
            this.#current(generation);
            if (opening && result.data?.id === Number(media[1])) this.#opened.add(result.data.id);
            // A zero page is a real reading intent. Keep both compatibility writes
            // under this lock; a later page/open makes an old repair obsolete.
            if (progress && payload.progress === 0 && result.data?.media_type === 'manga' && result.data.page_count > 1) {
              for (let attempt = 0; attempt < 3; ++attempt) {
                if (!isLatest() || signal.aborted || generation !== this.#generation) break;
                try {
                  const repaired = await collect(await execute(JSON.stringify({ view_status: 'viewing' }), signal));
                  if (repaired.status < 500) { result = repaired; break; }
                  if (attempt === 2) result = repaired;
                } catch (error) { if (attempt === 2 || signal.aborted || generation !== this.#generation) throw error; }
                if (attempt < 2 && isLatest()) await delay(250 * (attempt + 1), undefined, { signal });
              }
            }
          }
          if (result.status === 401) await this.expire(generation);
          else this.#current(generation);
          return result;
        };
        try { return await Promise.race([operation(), expired]); }
        finally { clearTimeout(timer); }
      },
    });
    // Coalesced callers each own a body; never share a consumed Response stream.
    return new Response([204, 205, 304].includes(packet.status) ? null : packet.bytes,
      { status: packet.status, statusText: packet.statusText, headers: packet.headers });
  }
}
module.exports = { DesktopSession, SessionError };
