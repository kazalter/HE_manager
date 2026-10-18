const fs = require('node:fs/promises');
const path = require('node:path');

// Only main constructs this store. Its cipher is Electron safeStorage (DPAPI/Keychain).
class CredentialStore {
  constructor(file, cipher) { this.file = file; this.cipher = cipher; this.tail = Promise.resolve(); }
  available() {
    try { return this.cipher.isEncryptionAvailable(); } catch { return false; }
  }
  async load(server) {
    if (!this.available()) return '';
    try {
      const value = JSON.parse(await fs.readFile(this.file, 'utf8'));
      if (value.version !== 1 || value.server !== server || typeof value.encrypted !== 'string' || value.encrypted.length > 65536) return '';
      return this.cipher.decryptString(Buffer.from(value.encrypted, 'base64'));
    } catch { return ''; }
  }
  save(server, token) {
    // Capture now and serialize disk operations, so an old save cannot resurrect a logout.
    const task = this.tail.catch(() => {}).then(async () => {
      if (!token || !this.available()) {
        await fs.rm(this.file, { force: true });
        return false;
      }
      const encrypted = this.cipher.encryptString(token).toString('base64');
      await fs.mkdir(path.dirname(this.file), { recursive: true, mode: 0o700 });
      const temporary = this.file + '.next';
      await fs.writeFile(temporary, JSON.stringify({ version: 1, server, encrypted }), { mode: 0o600 });
      await fs.rename(temporary, this.file);
      return true;
    });
    this.tail = task;
    return task;
  }
}
module.exports = { CredentialStore };
