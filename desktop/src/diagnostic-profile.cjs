const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
function diagnosticProfile(requested, temporaryRoot = os.tmpdir()) {
  if (!requested) return fs.mkdtempSync(path.join(temporaryRoot, 'he-baseline-'));
  const root = fs.realpathSync(temporaryRoot), directory = fs.realpathSync(requested);
  if (path.dirname(directory) !== root || !path.basename(directory).startsWith('he-desktop-test-')) throw new Error('Use an explicitly marked disposable profile');
  const stat = fs.statSync(directory), marker = path.join(directory, '.he-desktop-test-profile.json');
  if (!stat.isDirectory() || typeof process.getuid === 'function' && stat.uid !== process.getuid()) throw new Error('Diagnostic profile has another owner');
  if (!fs.lstatSync(marker).isFile() || JSON.parse(fs.readFileSync(marker, 'utf8')).version !== 1) throw new Error('Diagnostic profile marker is missing');
  return directory;
}
module.exports = { diagnosticProfile };
