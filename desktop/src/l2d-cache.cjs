const fs = require('node:fs/promises');
const path = require('node:path');
const { createHash } = require('node:crypto');

const MAX_ENTRY_BYTES = 64 * 1024 * 1024;
const BLOCKED_ROUTES = new Set(['/l2d/models/manifest.json', '/l2d/models/session']);

function canCache(pathname) {
  if (typeof pathname !== 'string' || !pathname.startsWith('/l2d/models/')) return false;
  if (BLOCKED_ROUTES.has(pathname) || pathname.startsWith('/l2d/models/import/')) return false;
  if (pathname.includes('..') || pathname.includes('\\')) return false;
  const segments = pathname.slice('/l2d/models/'.length).split('/').filter(Boolean);
  return segments.length >= 2;
}

function hashKey(server, pathname) {
  return createHash('sha256').update(`${server || ''}\0${pathname}`).digest('hex');
}

class L2dCache {
  constructor(directory) {
    this.directory = directory;
    this.writes = new Map();
  }

  canCache(pathname) {
    return canCache(pathname);
  }

  entryPaths(server, pathname) {
    const key = hashKey(server, pathname);
    const folder = path.join(this.directory, key.slice(0, 2));
    return {
      key,
      folder,
      data: path.join(folder, `${key}.bin`),
      meta: path.join(folder, `${key}.json`),
    };
  }

  async get(server, pathname) {
    if (!canCache(pathname)) return null;
    const { data, meta } = this.entryPaths(server, pathname);
    try {
      const [metaText, body] = await Promise.all([fs.readFile(meta, 'utf8'), fs.readFile(data)]);
      const parsed = JSON.parse(metaText);
      if (!parsed || typeof parsed.contentType !== 'string' || parsed.size !== body.length) return null;
      return { contentType: parsed.contentType, body };
    } catch {
      return null;
    }
  }

  async put(server, pathname, contentType, body) {
    if (!canCache(pathname) || !Buffer.isBuffer(body) || body.length === 0 || body.length > MAX_ENTRY_BYTES) return false;
    const paths = this.entryPaths(server, pathname);
    const previous = this.writes.get(paths.key) || Promise.resolve();
    const job = previous.catch(() => {}).then(async () => {
      await fs.mkdir(paths.folder, { recursive: true });
      const dataTemp = `${paths.data}.${process.pid}.${Date.now()}.next`;
      const metaTemp = `${paths.meta}.${process.pid}.${Date.now()}.next`;
      try {
        await fs.writeFile(dataTemp, body);
        await fs.writeFile(metaTemp, JSON.stringify({
          contentType: contentType || 'application/octet-stream',
          size: body.length,
        }));
        await fs.rename(dataTemp, paths.data);
        await fs.rename(metaTemp, paths.meta);
        return true;
      } catch {
        await Promise.allSettled([fs.unlink(dataTemp), fs.unlink(metaTemp)]);
        return false;
      }
    });
    this.writes.set(paths.key, job);
    try {
      return await job;
    } finally {
      if (this.writes.get(paths.key) === job) this.writes.delete(paths.key);
    }
  }

  async clear() {
    await Promise.allSettled([...this.writes.values()]);
    await fs.rm(this.directory, { recursive: true, force: true });
  }
}

module.exports = { L2dCache, canCache };
