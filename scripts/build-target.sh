#!/usr/bin/env bash
# Host-side driver (CI and local): resolve a target, then build kernelsu.ko in the DDK container.
# Usage: scripts/build-target.sh <target-id> <kernelsu|kernelsu-next> <ksu-repo-dir> <ksu-ref> <work-dir>
# Output: <work-dir>/<target-id>/out-<variant>/kernelsu.ko
set -euo pipefail
TARGET=$1; VARIANT=$2; KSU_REPO=$3; KSU_REF=$4; WORK=$5
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PY=${PYTHON:-python3}; "$PY" -c pass 2>/dev/null || PY=python
# Docker Desktop on Windows (Git Bash) needs Windows paths and no MSYS path mangling.
winpath() { if command -v cygpath >/dev/null; then cygpath -w "$1"; else echo "$1"; fi; }
export MSYS_NO_PATHCONV=1

TDIR=$WORK/$TARGET; mkdir -p "$TDIR"
"$PY" -I "$(winpath "$ROOT/scripts/fetch_kernel_source.py")" --target "$TARGET" --out "$(winpath "$TDIR")"
# shellcheck disable=SC1090,SC1091
source <(tr -d '\r' < "$TDIR/target.env")
PVAR=PATCHES_$(echo "$VARIANT" | tr 'a-z-' 'A-Z_')
[ -n "${!PVAR+x}" ] || { echo "unknown variant $VARIANT"; exit 1; }
read -r -a PATCHES <<< "${!PVAR}"

echo "== $TARGET / $VARIANT @ $KSU_REF in $DDK_IMAGE (patches: ${PATCHES[*]:-none})"
docker run --rm \
  -e KERNEL_RELEASE="$KERNEL_RELEASE" \
  -v "$(winpath "$TDIR"):/in" \
  -v "$(winpath "$KSU_REPO"):/ksu:ro" \
  -v "$(winpath "$ROOT/patches"):/patches:ro" \
  -v "$(winpath "$ROOT/scripts/build-lkm.sh"):/build-lkm.sh:ro" \
  "$DDK_IMAGE" bash /build-lkm.sh "$SRC_TGZ" "$KSU_REF" "out-$VARIANT" ${PATCHES[@]+"${PATCHES[@]}"}

# A kernel with the kCFI caller rewrite (6.2+) patches bytes in front of unchecked indirect
# calls at load time; fail the build if any could be mistaken for a kCFI sequence.
"$PY" -I "$(winpath "$ROOT/scripts/x86_icall_windows.py")" "$(winpath "$TDIR/out-$VARIANT/kernelsu.ko")"
