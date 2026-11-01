#!/usr/bin/env bash
# Build kernelsu.ko (KernelSU or KernelSU-Next) against the exact kernel/common source of
# an AVD kernel. Runs inside ghcr.io/ylarod/ddk-min:<kmi>-<release> (clang matches GKI).
#
# Mounts: /in  = dir from fetch_kernel_source.py (kernel-ranchu, common-<sha>.tar.gz)
#         /ksu = KernelSU / KernelSU-Next git repo (read-only is fine; it is cloned)
#         /patches = this repo's patches/ dir (optional)
# Usage:  build-lkm.sh <src.tgz> <ksu-ref> <out-dir-under-/in> [patch-relative-to-/patches ...]
set -euo pipefail
SRC_TGZ=/in/$1; KSU_REF=$2; OUT=/in/$3; shift 3; PATCHES=("$@")
unset CROSS_COMPILE; export ARCH=x86_64 LLVM=1 LLVM_IAS=1
W=/work; KSRC=$W/common; KDIR=$W/kdir; mkdir -p "$KSRC" "$KDIR" "$OUT"

echo "== extract kernel source"
tar xzf "$SRC_TGZ" -C "$KSRC"
cd "$KSRC"

echo "== kernel config from kernel-ranchu (CONFIG_IKCONFIG=y)"
CONFIG=$OUT/device.config
sh scripts/extract-ikconfig /in/kernel-ranchu > "$CONFIG"
grep -q '^CONFIG_X86_64=y' "$CONFIG" || { echo "config extraction failed"; exit 1; }

# Same modpost relaxation as the upstream ddk-lkm workflows (no Module.symvers here).
sed -i -E 's/^([[:space:]]*)check_exports\(mod\);/\1\/\/ check_exports(mod);/' scripts/mod/modpost.c
sed -i -E 's/^([[:space:]]*)s->module = exp->module;/\1\/\/ s->module = exp->module;/' scripts/mod/modpost.c
sed -i 's/^static void check_exports(/static void __attribute__((unused)) check_exports(/' scripts/mod/modpost.c
sed -i 's/__version_ext_names\\") =\\n/__version_ext_names\\") = \\"\\"\\n/' scripts/mod/modpost.c

# Device kernels built with CONFIG_RUST=y have different C codegen (kCFI integer
# normalization, no entry padding / FineIBT, CONSTRUCTORS). There is no rustc in the
# DDK image, so Kconfig would silently drop RUST and the module would fail kCFI checks.
# Mark Rust available and skip the rust/ prepare steps; only C is compiled.
if grep -q '^CONFIG_RUST=y' "$CONFIG"; then
  echo "== keep CONFIG_RUST=y semantics without rustc"
  sed -i -E '/^config RUST_IS_AVAILABLE/,/^$/ s/^(\s*def_bool).*/\1 y/' init/Kconfig
  sed -i '/^prepare: prepare0/,/^endif/ s/^ifdef CONFIG_RUST$/ifdef CONFIG_RUST_BUILD_SKIPPED_FOR_LKM/' Makefile
  sed -i 's/^always-\$(CONFIG_RUST)\(\s*+= target.json\)/always-$(CONFIG_RUST_BUILD_SKIPPED_FOR_LKM)\1/' scripts/Makefile
fi

echo "== olddefconfig"
cp "$CONFIG" "$KDIR/.config"
make O="$KDIR" olddefconfig >/dev/null
# Only toolchain-version strings may differ; anything else means codegen drift.
DRIFT=$(diff <(grep -E '^CONFIG_' "$CONFIG" | sort) <(grep -E '^CONFIG_' "$KDIR/.config" | sort) \
  | grep -E '^[<>]' | grep -vE 'CONFIG_(CC_VERSION_TEXT|CLANG_VERSION|LLD_VERSION|AS_VERSION|PAHOLE_VERSION|RUSTC_VERSION_TEXT|BINDGEN_VERSION_TEXT|RUSTC_VERSION|RUSTC_LLVM_VERSION|GCC_ASM_GOTO_OUTPUT_WORKAROUND)=' || true)
if [ -n "$DRIFT" ]; then echo "!! config drift vs device:"; echo "$DRIFT" | head -40; exit 1; fi

echo "== modules_prepare"
make O="$KDIR" -j"$(nproc)" modules_prepare > "$OUT/modules_prepare.log" 2>&1 \
  || { grep -nE 'rror|\*\*\*' "$OUT/modules_prepare.log" | head -20; exit 1; }
make O="$KDIR" -j"$(nproc)" security/selinux/built-in.a > /dev/null

echo "== KernelSU source @ $KSU_REF"
git config --global --add safe.directory '*'
# --shared keeps every object of /ksu reachable, so tags, branches and bare SHAs all work,
# and the full history stays available for the version number (30000 + commit count).
KSU_SHA=$(git -C /ksu rev-parse --verify "$KSU_REF^{commit}")
git clone -q --shared --no-checkout /ksu "$W/KernelSU"
cd "$W/KernelSU"
git checkout -q --detach "$KSU_SHA"
echo "   $(git describe --tags --always) ($KSU_SHA), $(git rev-list --count HEAD) commits"
for p in "${PATCHES[@]}"; do echo "== apply $p"; git apply -v "/patches/$p"; done

cd kernel
make -C "$KDIR" M="$PWD" src="$PWD" -j"$(nproc)" modules \
  CONFIG_KSU=m CONFIG_KSU_X86_PATCH_SYSCALL_DISPATCHER=y > "$OUT/module.log" 2>&1 \
  || { grep -nE 'error' "$OUT/module.log" | head -20; exit 1; }
grep -E 'version' "$OUT/module.log" | sort -u | head -3
llvm-strip -d kernelsu.ko
cp kernelsu.ko "$OUT/kernelsu.ko"
VERMAGIC=$(modinfo -F vermagic "$OUT/kernelsu.ko" 2>/dev/null || strings kernelsu.ko | grep -m1 '^vermagic=' | cut -d= -f2)
echo "vermagic: $VERMAGIC"
ls -la "$OUT/kernelsu.ko"
