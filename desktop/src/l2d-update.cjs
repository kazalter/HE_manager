const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const readline = require('node:readline');

class L2dUpdate {
  constructor({ session, repo, script }) {
    this.session = session; this.repo = repo; this.script = script;
    this.state = { running: false, message: '', failures: [] };
  }
  snapshot() { return { ...this.state, failures: [...this.state.failures] }; }
  start() {
    if (this.state.running) return this.snapshot();
    const snapshot = this.session.snapshot();
    if (!snapshot.user?.is_admin) throw new Error('请先使用管理员账号登录');
    const identity = this.session.identity(snapshot.generation);
    this.state = { running: true, message: '正在检查已有图鉴…', failures: [] };
    void this.run(identity).catch(error => {
      this.state.message = `更新失败：${error.message}`;
    }).finally(() => { this.state.running = false; });
    return this.snapshot();
  }
  async run(identity) {
    const python = path.join(this.repo, '.venv', 'Scripts', 'python.exe');
    try { await fs.access(python); await fs.access(path.join(this.repo, 'scripts', 'extract.py')); }
    catch { throw new Error('找不到本机 L2Dviewer 解包工具或其 Python 环境，请检查桌面 HE_Project/L2Dviewer'); }
    const response = await this.session.request('/l2d/models/manifest.json', {}, identity.generation);
    if (!response.ok) throw new Error(`无法读取图鉴（${response.status}）`);
    const manifest = await response.json();
    if (!Array.isArray(manifest)) throw new Error('图鉴清单格式无效');
    const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'he-l2d-'));
    try {
      const result = await new Promise((resolve, reject) => {
        const child = spawn(python, ['-u', this.script, this.repo, temp], { windowsHide: true, env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
        let final, error = '', stderr = '';
        const abort = () => child.kill();
        identity.signal.addEventListener('abort', abort, { once: true });
        child.stderr.setEncoding('utf8'); child.stderr.on('data', data => { stderr = (stderr + data).slice(-2000); });
        readline.createInterface({ input: child.stdout }).on('line', line => {
          let event; try { event = JSON.parse(line); } catch { return; }
          if (event.message) this.state.message = event.message;
          if (event.error) error = event.error;
          if (event.done) final = event;
        });
        child.on('error', reject);
        child.on('close', code => {
          identity.signal.removeEventListener('abort', abort);
          if (identity.signal.aborted) reject(new Error('登录或服务器已改变'));
          else if (code !== 0 || !final) reject(new Error(error || stderr || '解包进程异常退出'));
          else resolve(final);
        });
        child.stdin.end(JSON.stringify(manifest.map(item => item.id)) + '\n');
      });
      const failures = result.failures || []; let added = 0, skipped = 0;
      for (const [index, id] of result.files.entries()) {
        this.state.message = `正在添加 ${index + 1}/${result.files.length}：${id}`;
        try {
          const bytes = await fs.readFile(path.join(temp, `${id}.zip`));
          const form = new FormData(); form.set('archive', new Blob([bytes], { type: 'application/zip' }), `${id}.zip`);
          const uploaded = await this.session.request(`/l2d/models/import/${id}`, { method: 'POST', body: form }, identity.generation);
          if (uploaded.status === 409) skipped++;
          else if (!uploaded.ok) throw new Error(`服务器返回 ${uploaded.status}`);
          else added++;
          await uploaded.body?.cancel();
        } catch (error) { failures.push({ id, error: error.message }); }
      }
      this.state.failures = failures;
      this.state.message = `完成：新增 ${added} 个，已存在 ${skipped} 个，失败 ${failures.length} 个。`;
    } finally { await fs.rm(temp, { recursive: true, force: true }); }
  }
}
module.exports = { L2dUpdate };
