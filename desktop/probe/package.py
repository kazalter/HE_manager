"""Build the CP-01 minimum app with native runtimes and no development tools."""
import hashlib
import json
import os
import pathlib
import plistlib
import shutil
import stat
import subprocess
import sys
import urllib.request
import zipfile

root = pathlib.Path(__file__).resolve().parents[1]
platform = sys.argv[1]
if platform not in {"darwin", "win32"}:
    raise SystemExit("Usage: package.py darwin|win32")
arch = "arm64" if platform == "darwin" else "x64"
build = root / "native/build" / f"{platform}-{arch}"
metadata = json.loads((build / "build-info.json").read_text(encoding="utf-8-sig"))
for name, expected in metadata["sourceSha256"].items():
    if hashlib.sha256((root / "native" / name).read_bytes()).hexdigest() != expected:
        raise RuntimeError("Rebuild the native module after changing " + name)
if hashlib.sha256((build / "he_embedded.node").read_bytes()).hexdigest() != metadata["addonSha256"]:
    raise RuntimeError("Native module checksum mismatch")
version = "44.8.0"
name = f"electron-v{version}-{platform}-{arch}.zip"
checksums = json.loads((root / "node_modules/electron/checksums.json").read_text())
archive = root / "native/.downloads" / name
if not archive.exists():
    with urllib.request.urlopen(f"https://github.com/electron/electron/releases/download/v{version}/{name}", timeout=90) as response, archive.open("wb") as output:
        shutil.copyfileobj(response, output)
if hashlib.sha256(archive.read_bytes()).hexdigest() != checksums[name]:
    raise RuntimeError("Electron archive checksum mismatch")
output = root / "native/release" / f"HE-Manager-CP01-{platform}-{arch}"
if output.exists():
    shutil.rmtree(output)
output.mkdir(parents=True)
with zipfile.ZipFile(archive) as package:
    for info in package.infolist():
        relative = pathlib.PurePosixPath(info.filename)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Invalid archive path")
        target = output / info.filename
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            target.parent.mkdir(parents=True, exist_ok=True)
            link = package.read(info).decode()
            if os.path.isabs(link):
                raise RuntimeError("Invalid archive symlink")
            target.symlink_to(link)
        else:
            package.extract(info, output)
            if target.is_file() and mode:
                target.chmod(mode & 0o777)
if platform == "darwin":
    bundle = output / "HE Manager CP01.app"
    (output / "Electron.app").rename(bundle)
    (bundle / "Contents/MacOS/Electron").rename(bundle / "Contents/MacOS/HE Manager CP01")
    plist = bundle / "Contents/Info.plist"
    info = plistlib.loads(plist.read_bytes())
    info.update(CFBundleExecutable="HE Manager CP01", CFBundleName="HE Manager CP01", CFBundleDisplayName="HE Manager CP01", CFBundleIdentifier="com.kaz.he-manager.cp01", CFBundleShortVersionString="0.2.0", CFBundleVersion="0.2.0", LSMinimumSystemVersion="15.0")
    plist.write_bytes(plistlib.dumps(info))
    resources = bundle / "Contents/Resources"
else:
    (output / "electron.exe").rename(output / "HE Manager CP01.exe")
    resources = output / "resources"
(resources / "default_app.asar").unlink(missing_ok=True)
destination = resources / "app"
destination.mkdir(parents=True)
(destination / "package.json").write_text(json.dumps({"name": "he-manager-cp01", "version": "0.2.0", "main": "probe/main.cjs", "private": True}))
shutil.copytree(root / "probe", destination / "probe", ignore=shutil.ignore_patterns("*.py", "__pycache__"))
for name in ["shaders", "licenses", "test"]:
    shutil.copytree(root / "resources" / name, destination / "resources" / name)
(destination / "src").mkdir()
shutil.copy2(root / "src/policy.cjs", destination / "src/policy.cjs")
native = destination / "native"
native.mkdir()
for name in ["runtime-lock.json", "header-lock.json", "README.md"]:
    shutil.copy2(root / "native" / name, native / name)
(native / "build" / f"{platform}-{arch}").mkdir(parents=True)
for name in ["he_embedded.node", "build-info.json"]:
    shutil.copy2(root / "native/build" / f"{platform}-{arch}" / name, native / "build" / f"{platform}-{arch}" / name)
shutil.copytree(root / "native/runtime" / platform, native / "runtime" / platform)
(native / "runtime/fixtures").mkdir(parents=True)
for name in ["acceptance.mkv", "fixture-manifest.json"]:
    shutil.copy2(root / "native/runtime/fixtures" / name, native / "runtime/fixtures" / name)
if platform == "darwin":
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
manifest = []
for file in sorted(destination.rglob("*")):
    if file.is_file():
        manifest.append({"path": file.relative_to(destination).as_posix(), "bytes": file.stat().st_size, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
(output / "app-manifest.json").write_text(json.dumps({"platform": platform, "arch": arch, "electron": version, "files": manifest}, indent=2) + "\n")
print(output)
portable = output.with_suffix(".zip")
with zipfile.ZipFile(portable, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5, allowZip64=True) as archive:
    for current, directories, files in os.walk(output, followlinks=False):
        for name in directories + files:
            file = pathlib.Path(current) / name
            relative = file.relative_to(output.parent)
            if file.is_symlink():
                info = zipfile.ZipInfo(relative.as_posix())
                info.create_system = 3
                info.external_attr = file.lstat().st_mode << 16
                archive.writestr(info, os.readlink(file))
            elif file.is_file():
                archive.write(file, relative)
print("ZIP", portable, "SHA256", hashlib.sha256(portable.read_bytes()).hexdigest())
