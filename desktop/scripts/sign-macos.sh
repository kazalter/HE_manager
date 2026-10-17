#!/bin/sh
# Local/ad-hoc signing of a build created on Linux; does not disable Gatekeeper.
set -eu
app_bundle=${1:?Usage: sign-macos.sh /path/to/HE\ Manager.app}
codesign --force --deep --sign - "$app_bundle"
codesign --verify --deep --strict "$app_bundle"
