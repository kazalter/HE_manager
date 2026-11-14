const fs = require('node:fs');
const [file, expected] = process.argv.slice(2);
if (!file || !/^[a-f0-9]{40}$/i.test(expected || '')) throw new Error('A manifest and full expected commit are required');
const info = JSON.parse(fs.readFileSync(file, 'utf8'));
if (info.sourceRevision !== expected || info.sourceDirty !== false || !info.buildId) {
  throw new Error(`Build provenance does not match a clean ${expected} checkout`);
}
console.log(`Verified clean build from ${expected}`);
