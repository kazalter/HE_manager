const API = 'https://api.github.com/repos/kazalter/HE_manager/releases/latest';
const RELEASES = 'https://github.com/kazalter/HE_manager/releases';
function version(value) {
  const match = /^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.exec(value);
  return match ? match.slice(1).map(Number) : null;
}
async function checkUpdate(current, fetchImpl = fetch) {
  const response = await fetchImpl(API, { headers: { Accept: 'application/vnd.github+json' }, redirect: 'error', signal: AbortSignal.timeout(8000) });
  if (response.status === 404) return { status: 'no-release' };
  if (!response.ok) throw new Error('无法检查更新，请稍后重试');
  const data = await response.json();
  const installed = version(current), latest = version(typeof data.tag_name === 'string' ? data.tag_name : '');
  if (!installed || !latest || data.draft || data.prerelease) return { status: 'unknown' };
  const comparison = latest.findIndex((part, index) => part !== installed[index]);
  return { status: comparison >= 0 && latest[comparison] > installed[comparison] ? 'available' : 'current', version: latest.join('.') };
}
module.exports = { checkUpdate, RELEASES };
