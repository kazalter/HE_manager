"""Extract the arm64 libmpv dependency closure from a pinned upstream bundle.

No Homebrew paths are retained. Original archive and transformed file hashes are
recorded separately; each dylib is signed after changing its dependency paths.
"""
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
URL = "https://github.com/iina/iina/releases/download/v1.5.0/IINA.v1.5.0.dmg"
SHA = "8fad50479b10e09645053457cec46bd53d054ced2242cfe68f74586735a20dc7"
archive = ROOT / ".downloads/IINA-v1.5.0.dmg"
archive.parent.mkdir(parents=True, exist_ok=True)
if not archive.exists():
    with urllib.request.urlopen(URL, timeout=60) as source, archive.open("wb") as target:
        shutil.copyfileobj(source, target)
if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA:
    raise RuntimeError("IINA runtime archive checksum mismatch")


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE)


with tempfile.TemporaryDirectory(prefix="he-libmpv-") as temporary:
    mount = pathlib.Path(temporary) / "volume"
    mount.mkdir()
    subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(archive)], check=True, stdout=subprocess.DEVNULL)
    try:
        source = mount / "IINA.app/Contents/Frameworks"
        closure = {}

        def dependencies(name):
            if name in closure:
                return
            file = source / name
            lines = run("otool", "-arch", "arm64", "-L", str(file)).splitlines()[2:]
            values = [line.strip().split(" (", 1)[0] for line in lines]
            closure[name] = values
            for dependency in values:
                if dependency.startswith("@rpath/"):
                    relative = dependency.removeprefix("@rpath/")
                    if pathlib.PurePosixPath(relative).name != relative:
                        raise RuntimeError("Unexpected nested dependency")
                    dependencies(relative)
                elif not dependency.startswith(("/usr/lib/", "/System/Library/")):
                    raise RuntimeError("Non-bundled dependency: " + dependency)

        dependencies("libmpv.2.dylib")
        final = ROOT / "runtime/darwin"
        final.parent.mkdir(parents=True, exist_ok=True)
        destination = pathlib.Path(tempfile.mkdtemp(prefix=".darwin-stage-", dir=final.parent))
        records = []
        for name, links in sorted(closure.items()):
            original = source / name
            target = destination / name
            architectures = run("lipo", "-info", str(original))
            if "arm64" not in architectures:
                raise RuntimeError("Missing arm64 runtime: " + name)
            if "Architectures in the fat file" in architectures:
                subprocess.run(["lipo", str(original), "-thin", "arm64", "-output", str(target)], check=True)
            else:
                shutil.copy2(original, target)
            target.chmod(0o755)
            for dependency in links:
                if dependency.startswith("@rpath/"):
                    run("install_name_tool", "-change", dependency, "@loader_path/" + dependency.removeprefix("@rpath/"), str(target))
            run("codesign", "--force", "--sign", "-", str(target))
            build_version = run("otool", "-l", str(target)).split("LC_BUILD_VERSION", 1)[-1].split("Load command", 1)[0].strip()
            minimum = re.search(r"\bminos\s+([\d.]+)", build_version)
            if not minimum or tuple(map(int, minimum[1].split("."))) > (15, 0):
                raise RuntimeError("Runtime exceeds the macOS 15 target: " + name)
            records.append({"file": name, "sourceSha256": hashlib.sha256(original.read_bytes()).hexdigest(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "minimumMacOS": minimum[1]})
        shutil.copy2(source.parent / "Resources/Credits.rtf", destination / "IINA-Credits.rtf")
        (destination / "runtime-manifest.json").write_text(json.dumps({"source": URL, "sourceSha256": SHA, "transforms": ["arm64-dependency-closure", "thin-arm64", "rpath-to-loader-path", "ad-hoc-sign"], "files": records}, indent=2) + "\n")
        previous = final.with_name(".darwin-previous")
        if previous.exists():
            raise RuntimeError("A previous runtime backup still exists")
        if final.exists():
            final.rename(previous)
        destination.rename(final)
        if previous.exists():
            shutil.rmtree(previous)
        print(f"Prepared {len(records)} arm64 libraries in {final}")
    finally:
        subprocess.run(["hdiutil", "detach", str(mount)], check=True, stdout=subprocess.DEVNULL)
