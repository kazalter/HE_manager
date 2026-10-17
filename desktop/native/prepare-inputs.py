"""Fetch pinned build inputs before compiling the native bridge on either host."""
import hashlib
import json
import pathlib
import sys
import urllib.request

root = pathlib.Path(__file__).resolve().parent
platform = sys.argv[1]
if platform not in {'darwin', 'win32'}:
    raise SystemExit('Usage: prepare-inputs.py darwin|win32')
lock = json.loads((root / 'runtime-lock.json').read_text())
electron = lock['electron']
items = [('electron-headers.tar.gz', electron['headersUrl'], electron['headersSha256'])]
if platform == 'win32':
    windows = lock['win32-x64']
    items += [('node.lib', electron['windowsImportLibraryUrl'], electron['windowsImportLibrarySha256']),
              ('libmpv-win.7z', windows['url'], windows['archiveSha256'])]
destination = root / '.downloads'
destination.mkdir(parents=True, exist_ok=True)
for name, url, expected in items:
    target = destination / name
    if target.exists():
        with target.open('rb') as file:
            if hashlib.file_digest(file, 'sha256').hexdigest() == expected:
                print('Verified cached', name)
                continue
    temporary = target.with_suffix(target.suffix + '.partial')
    try:
        digest = hashlib.sha256()
        size = 0
        with urllib.request.urlopen(url, timeout=90) as response, temporary.open('wb') as file:
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 512 * 1024 * 1024:
                    raise RuntimeError('Build input exceeds the download budget: ' + name)
                digest.update(chunk)
                file.write(chunk)
        if digest.hexdigest() != expected:
            raise RuntimeError('Build input checksum mismatch: ' + name)
        temporary.replace(target)
        print('Downloaded and verified', name)
    finally:
        temporary.unlink(missing_ok=True)
