const { randomUUID } = require('node:crypto');
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
  #operation = 0; #save = Promise.resolve(); #cleanup = Promise.resolve(); #writes = new Map();
  constructor({ server = '', store, fetch: fetcher = fetch, onInvalidate = () => {}, onChange = () => {} }) {
    this.server = server ? serverUrl(server) : ''; this.store = store; this.fetch = fetcher;
    this.onInvalidate = onInvalidate; this.onChange = onChange; this.hasUsers = true; this.error = ''; this.persisted = false;
  }
  snapshot() {
    return { server: this.server, generation: this.#generation, revision: this.#revision, user: this.#user ? { ...this.#user } : null,
      hasUsers: this.hasUsers, error: this.error, persistent: this.persisted };
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
    this.#token = ''; this.#user = null; this.#opened.clear(); this.error = reason === 'expired' ? '登录已过期，请重新登录' : ''; this.persisted = false;
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
    await this.#cleanup; this.#current(generation);
    if (!this.server) return this.snapshot();
    const token = await this.store.load(this.server);
    this.#current(generation);
    if (operation !== this.#operation) throw stale();
    try {
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
      this.error = '';
    } catch (error) {
      this.#current(generation);
      // A network outage does not delete the encrypted login; no cached identity is admitted.
      this.error = error instanceof SessionError ? error.message : '无法验证登录状态，请重试';
    }
    this.#publish(); return this.snapshot();
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
    for (const name of ['authorization', 'cookie', 'host', 'origin', 'referer', 'connection', 'accept-encoding', 'x-he-generation']) headers.delete(name);
    headers.set('Authorization', 'Bearer ' + identity.token);
    const execute = async (writing) => {
      this.#current(generation);
      const response = await this.#send(identity.server, pathname, { ...options, headers, signal: writing ? undefined : options.signal }, writing ? undefined : identity.signal);
      if (generation !== this.#generation) { await response.body?.cancel(); throw stale(); }
      if (response.status === 401) {
        await this.expire(generation);
      }
      if ((options.method || 'GET').toUpperCase() === 'GET' && /^\/media\/\d+$/.test(parsed.pathname) && response.ok) {
        const media = await response.clone().json(); this.#current(generation);
        if (Number.isSafeInteger(media.id)) this.#opened.add(media.id);
      }
      return response;
    };
    const media = /^\/media\/(\d+)$/.exec(parsed.pathname);
    if (options.method?.toUpperCase() !== 'PATCH' || !media) return execute(false);
    // The lock survives identity changes. Queued old writes are discarded at dispatch;
    // the old in-flight write retains its old server/token and drains before a new one.
    const key = identity.server + '\0' + media[1], previous = this.#writes.get(key) || Promise.resolve();
    const current = previous.catch(() => {}).then(() => execute(true));
    this.#writes.set(key, current);
    current.finally(() => { if (this.#writes.get(key) === current) this.#writes.delete(key); }).catch(() => {});
    return current;
  }
}
module.exports = { DesktopSession, SessionError };
