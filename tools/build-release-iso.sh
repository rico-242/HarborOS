#!/bin/bash
# Build a fresh, offline-installable ISO in a dedicated directory; no physical disks.
set -euo pipefail
source=$(cd "$(dirname "$0")/.." && pwd)
work=${HARBOR_ISO_WORK:?Set HARBOR_ISO_WORK to a new dedicated build directory}
artifacts=${HARBOR_ARTIFACTS:-$source/dist}
test "$(id -u)" = 0 || { echo 'Run with sudo on an amd64 Linux build host.' >&2; exit 1; }
test "$(uname -m)" = x86_64
test ! -e "$work" || { echo 'A fresh build directory is required.' >&2; exit 1; }
case "$work" in /*) ;; *) echo 'Build path must be absolute.' >&2; exit 1;; esac
mkdir -p "$work/root" "$artifacts"
export HARBOR_SOURCE="$source" HARBOR_TARGET="$work/root" HARBOR_ISO_WORK="$work" HARBOR_ARTIFACTS="$artifacts"
bash "$source/os/build-rootfs.sh"
touch "$work/root-ready"
bash "$source/os/prepare-live-root.sh"
bash "$source/tools/prepare-graphical-root.sh"
bash "$source/os/build-iso.sh"
