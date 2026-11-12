"""Run the existing local extractor; emit one JSON event per line."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

repo, output = map(Path, sys.argv[1:3])
known = set(json.loads(sys.stdin.readline()))
sys.path.insert(0, str(repo / 'scripts'))
import pull_bundles as bundles
import pull_lua
from l2d_selection import select_targets

def event(**value):
    print(json.dumps(value, ensure_ascii=False), flush=True)

def main():
    serial = bundles.resolve_serial()
    package = bundles.detect_package(serial, None)
    remote = bundles.list_remote_bundles(serial, package)
    targets = select_targets((name for name, _ in remote), known)
    event(message=f'发现 {len(targets)} 个未收录资源包（已跳过有普通版的和谐版）', total=len(targets))
    if not targets:
        event(done=True, files=[], failures=[])
        return
    # Replace the required metadata only after both downloads succeeded.
    downloaded = []
    with tempfile.TemporaryDirectory(dir=output) as temp:
        for rel in pull_lua.REQUIRED:
            url = f'{pull_lua.RAW}/CN/{rel}'
            request = urllib.request.Request(url, headers={'User-Agent': 'l2dviewer-pull_lua'})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
            if not data:
                raise RuntimeError(f'游戏配置为空: {rel}')
            file = Path(temp) / rel
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
            downloaded.append((file, repo / '.tmp' / 'lua' / 'CN' / rel))
        for src, dest in downloaded:
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(src, dest)
    files, failures = [], []
    for index, name in enumerate(targets, 1):
        event(message=f'正在解包 {index}/{len(targets)}：{name}')
        try:
            bundle = output / 'bundles' / name
            bundle.parent.mkdir(exist_ok=True)
            bundles.pull_one(f'/sdcard/Android/data/{package}/{bundles.REMOTE_FILES_DIR}/{name}', bundle, serial)
            dest = output / 'models' / name
            command = [sys.executable, str(repo / 'scripts' / 'extract.py'), str(bundle), str(dest)]
            if name.endswith('_hx'):
                command += ['--painting', name[:-3]]
            run = subprocess.run(command, cwd=repo, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if run.returncode or not (dest / f'{name}.model3.json').is_file():
                raise RuntimeError((run.stderr or run.stdout or '没有生成模型')[-1000:])
            archive = output / f'{name}.zip'
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
                for file in dest.rglob('*'):
                    if file.is_file():
                        z.write(file, file.relative_to(dest).as_posix())
            files.append(name)
            bundle.unlink()
            shutil.rmtree(dest)
        except (Exception, SystemExit) as exc:
            failures.append({'id': name, 'error': str(exc)})
    event(done=True, files=files, failures=failures)

try:
    main()
except (Exception, SystemExit) as exc:
    event(error=str(exc) or '设备或解包工具不可用')
    sys.exit(1)
