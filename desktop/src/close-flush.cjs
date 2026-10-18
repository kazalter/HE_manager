const { randomUUID } = require('node:crypto');
// A bounded, owner-bound acknowledgement gives the renderer a chance to capture
// final media positions. Destruction and native cleanup are owned by main.
class CloseFlush {
  #pending = new WeakMap();
  constructor(send, timeout = 1500) { this.send = send; this.timeout = timeout; }
  request(owner) {
    const existing = this.#pending.get(owner);
    if (existing) return existing.promise;
    let resolve;
    const entry = { nonce: randomUUID(), promise: new Promise(done => { resolve = done; }) };
    entry.finish = value => {
      if (this.#pending.get(owner) !== entry) return;
      clearTimeout(entry.timer); this.#pending.delete(owner); resolve(value);
    };
    this.#pending.set(owner, entry);
    entry.timer = setTimeout(() => entry.finish(false), this.timeout);
    try { this.send(owner, entry.nonce); } catch { entry.finish(false); }
    return entry.promise;
  }
  acknowledge(owner, nonce) {
    const entry = this.#pending.get(owner);
    if (entry?.nonce === nonce) entry.finish(true);
  }
}
module.exports = { CloseFlush };
