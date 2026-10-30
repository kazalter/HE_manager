#!/usr/bin/env bash
set -euo pipefail

# Keep both the build context and the isolated daemon's image storage off the
# system disk. The caller must start the dedicated daemon on this mount first.
mount_root="${HE_GAME_STORAGE_MOUNT:-/mnt/hdd2}"
docker_socket="${HE_GAME_DOCKER_SOCKET:-/run/he-game-docker/docker.sock}"
mountpoint -q -- "$mount_root" || { echo "Game disk is not mounted: $mount_root" >&2; exit 1; }
[[ "$(stat -c '%d' -- "$mount_root")" != "$(stat -c '%d' /)" ]] || { echo 'Game storage must not be on the system filesystem' >&2; exit 1; }
[[ -S "$docker_socket" ]] || { echo "Dedicated game Docker socket is unavailable" >&2; exit 1; }
actual_root="$(docker -H "unix://$docker_socket" info --format '{{.DockerRootDir}}')"
mount_real="$(realpath -- "$mount_root")"
actual_real="$(realpath -- "$actual_root")"
case "$actual_real/" in "$mount_real"/*) ;; *) echo 'Docker storage is not on the game disk' >&2; exit 1 ;; esac
# With Docker's containerd image store, layers live in containerd's root,
# which is independent of DockerRootDir. Reject a daemon attached to the
# machine's system containerd even if its DockerRootDir points at the HDD.
containerd_socket="$(docker -H "unix://$docker_socket" info --format '{{.Containerd.Address}}')"
python3 - "$containerd_socket" "$mount_real" <<'PY'
import os, pathlib, sys
address, mount = sys.argv[1:]
mount = pathlib.Path(mount).resolve()
for entry in pathlib.Path('/proc').iterdir():
    if not entry.name.isdigit():
        continue
    try:
        args = (entry / 'cmdline').read_bytes().decode().strip('\0').split('\0')
    except (OSError, UnicodeError):
        continue
    if not args or pathlib.Path(args[0]).name != 'containerd':
        continue
    def option(name):
        for i, arg in enumerate(args):
            if arg == name and i + 1 < len(args): return args[i + 1]
            if arg.startswith(name + '='): return arg.split('=', 1)[1]
        return None
    if option('--address') == address:
        root = option('--root')
        if root and mount in pathlib.Path(root).resolve().parents:
            break
        raise SystemExit('Containerd storage is not on the game disk')
else:
    raise SystemExit('Cannot verify the dedicated containerd storage')
PY

free_bytes="$(df -PB1 -- "$mount_root" | awk 'NR==2 {print $4}')"
(( free_bytes >= 15 * 1024 * 1024 * 1024 )) || { echo 'At least 15 GiB free on the game disk is required for image preparation' >&2; exit 1; }
context="$mount_real/he-game-runtime-build"
mkdir -p -- "$context/debs"
cp -- "$(dirname -- "$0")/Dockerfile" "$context/Dockerfile"
cp -- "$(dirname -- "$0")/stream-relay.py" "$context/stream-relay.py"
base='https://mirrors.aliyun.com/debian/pool/main'
fetch() {
  local url="$1" target="$2" digest="$3" temporary="$2.download"
  if [[ -f "$target" ]] && printf '%s  %s\n' "$digest" "$target" | sha256sum -c --status; then return; fi
  curl --fail --location --retry 3 --output "$temporary" "$url"
  printf '%s  %s\n' "$digest" "$temporary" | sha256sum -c --status || { echo 'Package verification failed' >&2; exit 1; }
  mv -- "$temporary" "$target"
}
fetch "$base/libz/libz-mingw-w64/libz-mingw-w64_1.2.13+dfsg-1_all.deb" "$context/debs/libz.deb" b9e73ca486bc2aa66da86b5724220d2dd7c8299636b1df74c3414757a2170615
fetch "$base/w/wine/libwine_8.0~repack-4_i386.deb" "$context/debs/libwine.deb" c992aad6a47d81b719514f5d06c5df10267f1e40a6f4f3b4e3f655cbbf308d57
fetch "$base/w/wine/wine32_8.0~repack-4_i386.deb" "$context/debs/wine32.deb" 8d2ea88c4f45e813401e10f139456098f21a9a68440b36ea0da4644a2cbe21f8
docker -H "unix://$docker_socket" build --network=none -t he-game-runtime:wine8 "$context"
