const fs = require('node:fs/promises');
const path = require('node:path');

// Only main constructs this store. Electron 44's asynchronous encryptor keeps
// Keychain/DPAPI interaction off the main event loop. Sync ciphers are test-only.
class CredentialStore {
  constructor(file, cipher) { this.file = file; this.cipher = cipher; this.tail = Promise.resolve(); }
  async available() {
    try {
      return this.cipher.isAsyncEncryptionAvailable
        ? await this.cipher.isAsyncEncryptionAvailable()
        : this.cipher.isEncryptionAvailable();
    } catch { return false; }
  }
  async load(server) {
    try {
      // A fresh profile has no credential to decrypt and need not touch Keychain.
      const value = JSON.parse(await fs.readFile(this.file, 'utf8'));
      if (value.version !== 2 || value.server !== server || typeof value.encrypted !== 'string' || value.encrypted.length > 65536 || !await this.available()) return '';
      const bytes = Buffer.from(value.encrypted, 'base64');
      if (value.scheme === 'async' && this.cipher.decryptStringAsync) {
        const decoded = await this.cipher.decryptStringAsync(bytes);
        return typeof decoded.result === 'string' ? decoded.result : '';
      }
      if (value.scheme === 'sync' && !this.cipher.encryptStringAsync) return this.cipher.decryptString(bytes);
      return '';
    } catch { return ''; }
  }
  save(server, token) {
    // Capture now and serialize disk operations, so an old save cannot resurrect a logout.
    const task = this.tail.catch(() => {}).then(async () => {
      if (!token || !await this.available()) {
        await fs.rm(this.file, { force: true });
        return false;
      }
      const asynchronous = !!this.cipher.encryptStringAsync;
      const bytes = asynchronous ? await this.cipher.encryptStringAsync(token) : this.cipher.encryptString(token);
      const encrypted = bytes.toString('base64');
      await fs.mkdir(path.dirname(this.file), { recursive: true, mode: 0o700 });
      const temporary = this.file + '.next';
      await fs.writeFile(temporary, JSON.stringify({ version: 2, scheme: asynchronous ? 'async' : 'sync', server, encrypted }), { mode: 0o600 });
      await fs.rename(temporary, this.file);
      return true;
    });
    this.tail = task;
    return task;
  }
}
module.exports = { CredentialStore };
