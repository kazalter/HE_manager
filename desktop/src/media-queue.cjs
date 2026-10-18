// One lock per server/media survives account and player changes. Only adjacent,
// unsent progress from the same scene may collapse; metadata and opens are barriers.
class MediaQueue {
  #queues = new Map();
  enqueue(key, { kind, scope, run }) {
    let queue = this.#queues.get(key);
    if (!queue) { queue = { pending: [], running: false, latest: null }; this.#queues.set(key, queue); }
    return new Promise((resolve, reject) => {
      let item = queue.pending.at(-1);
      if (kind !== 'progress' || item?.kind !== kind || item.scope !== scope) {
        item = { kind, scope, waiters: [] }; queue.pending.push(item);
      }
      item.run = run;
      item.intent = Symbol();
      if (kind === 'progress' || kind === 'open') queue.latest = item.intent;
      item.waiters.push({ resolve, reject });
      if (!queue.running) void this.#drain(key, queue);
    });
  }
  async #drain(key, queue) {
    queue.running = true;
    while (queue.pending.length) {
      const item = queue.pending.shift();
      try {
        const value = await item.run(() => queue.latest === item.intent);
        for (const waiter of item.waiters) waiter.resolve(value);
      } catch (error) { for (const waiter of item.waiters) waiter.reject(error); }
    }
    queue.running = false;
    if (this.#queues.get(key) === queue) this.#queues.delete(key);
  }
}
module.exports = { MediaQueue };
