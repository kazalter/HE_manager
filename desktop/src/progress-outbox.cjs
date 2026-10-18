// Only the current failed progress per server/media can be retried. Tokens and
// disk storage stay outside this transient outbox; a new identity clears it.
class ProgressOutbox {
  #intents = new Map(); #timer; #stopped = false;
  constructor({ retryDelay = 1000 } = {}) { this.retryDelay = retryDelay; }
  current(intent) { return !!intent && this.#intents.get(intent.key) === intent; }
  capture(key, send) {
    const intent = { key, send, failed: false, sending: false, attempts: 0, retryAt: 0 };
    this.#intents.set(key, intent); this.#schedule(); return intent;
  }
  peek(key) { return this.#intents.get(key); }
  complete(intent) { if (this.current(intent)) { this.#intents.delete(intent.key); this.#schedule(); } }
  fail(intent) {
    if (!this.current(intent) || this.#stopped) return;
    intent.failed = true;
    intent.retryAt = Date.now() + Math.min(10000, this.retryDelay * 2 ** Math.min(intent.attempts++, 4));
    this.#schedule();
  }
  #schedule() {
    clearTimeout(this.#timer);
    const pending = [...this.#intents.values()].filter(intent => intent.failed && !intent.sending);
    if (this.#stopped || !pending.length) return;
    const wait = Math.max(25, Math.min(...pending.map(intent => intent.retryAt)) - Date.now());
    this.#timer = setTimeout(() => { void this.retry(false); }, wait); this.#timer.unref?.();
  }
  retry(force = true, key) {
    const requests = [];
    for (const intent of this.#intents.values()) {
      if (!intent.failed || intent.sending || (key !== undefined && intent.key !== key) || (!force && intent.retryAt > Date.now())) continue;
      if (this.#stopped) break;
      intent.sending = true;
      // Enqueue synchronously so a following actual-open GET is a barrier.
      let request;
      try { request = intent.send(intent); } catch (error) { request = Promise.reject(error); }
      requests.push(Promise.resolve(request).catch(() => {}).finally(() => { intent.sending = false; this.#schedule(); }));
    }
    this.#schedule();
    return Promise.all(requests).then(() => {});
  }
  clear() { clearTimeout(this.#timer); this.#intents.clear(); }
  close() { this.#stopped = true; this.clear(); }
}
module.exports = { ProgressOutbox };
