import hashlib
import json
import pathlib
import subprocess
import tarfile

root = pathlib.Path(__file__).resolve().parent
lock = json.loads((root / "header-lock.json").read_text())
download = root / ".downloads"
archive = download / "electron-headers.tar.gz"
if hashlib.sha256(archive.read_bytes()).hexdigest() != lock["electronHeadersSha256"]:
    raise RuntimeError("Electron header checksum mismatch")
for directory, files in [("mpv", lock["files"]), ("mpv-stable", lock["darwin"]["files"])]:
    for name, expected in files.items():
        if hashlib.sha256((root / "include" / directory / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("mpv header checksum mismatch: " + name)
with tarfile.open(archive) as package:
    package.extractall(download / "headers", filter="data")
out = root / "build/darwin-arm64"
out.mkdir(parents=True, exist_ok=True)
arguments = ["clang++", "-std=c++17", "-O2", "-shared", "-fPIC", "-undefined", "dynamic_lookup", "-mmacosx-version-min=15.0", "-DNAPI_VERSION=8", "-DNODE_GYP_MODULE_NAME=he_embedded", "-I", str(download / "headers/node_headers/include/node"), "-framework", "OpenGL", "-framework", "IOSurface", "-framework", "CoreFoundation", str(root / "embedded.cpp"), "-o", str(out / "he_embedded.node")]
subprocess.run(arguments, check=True)
files = [root / "embedded.cpp", root / "surface.h", root / "header-lock.json"]
metadata = {"platform": "darwin-arm64", "electron": lock["electron"], "nodeAPI": 8, "minimumMacOS": "15.0", "compiler": subprocess.check_output(["clang++", "--version"], text=True).splitlines()[0], "sourceSha256": {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in files}, "addonSha256": hashlib.sha256((out / "he_embedded.node").read_bytes()).hexdigest()}
(out / "build-info.json").write_text(json.dumps(metadata, indent=2) + "\n")
print("Built", out / "he_embedded.node")
