#!/system/bin/sh
# Load the susfs_guard_lkm.ko built for this AVD's exact kernel, once per boot.
#   load.sh post-fs-data | service | now
# post-fs-data is the normal load; service retries a load that failed earlier in the boot;
# `now` is `avd-ksu.py susfs` loading a freshly installed (staged) copy without a restart.
# The outcome goes to load.log and to module.prop's description, which the manager shows on
# the module card.
MODDIR=${0%/*}
STAGE=${1:-post-fs-data}
KSUD=/data/adb/ksud

[ -f "$MODDIR/disable" ] && exit 0
[ -f "$MODDIR/remove" ] && exit 0
[ "$(getprop persist.sys.safemode)" = 1 ] && exit 0
[ "$(getprop ro.sys.safemode)" = 1 ] && exit 0

umask 077
if [ "$STAGE" = post-fs-data ]; then exec >"$MODDIR/load.log" 2>&1; else exec >>"$MODDIR/load.log" 2>&1; fi
echo "[$STAGE] $(date)"

set_description() {
  # '#' as the sed delimiter: the text contains '/' and '-' but never '#'.
  [ -f "$MODDIR/module.prop" ] && sed -i "s#^description=.*#description=$1#" "$MODDIR/module.prop"
}

loaded() { [ -d /sys/module/susfs_guard_lkm ] || [ -e /proc/susfs_path ]; }

if loaded; then
  echo "SUSFS is already loaded; nothing to do"
  # post-fs-data runs before anything of ours loaded it: someone else did (ksud's own SUSFS
  # auto-load, another module, a kernel with SUSFS built in).
  [ "$STAGE" = post-fs-data ] && set_description "SUSFS was already loaded by something else; this module did nothing"
  exit 0
fi

# kos: "<kernel release> <file in lib/>" per line, generated from avd-targets.json. The exact
# release string is the match, not the KMI: two AVD kernels of one KMI (6.6.30 and 6.6.66)
# need different builds.
REL=$(cat /proc/sys/kernel/osrelease)
KO=
while read -r rel file; do
  [ "$rel" = "$REL" ] && KO=$file && break
done < "$MODDIR/kos"
if [ -z "$KO" ]; then
  echo "no module for kernel $REL"
  set_description "❌ no SUSFS build for kernel $REL in this module"
  exit 1
fi

echo "kernel $REL -> lib/$KO"
"$KSUD" insmod "$MODDIR/lib/$KO"
rc=$?
if [ "$rc" = 0 ] && loaded; then
  ver=$("$KSUD" susfs version 2>/dev/null)
  echo "loaded (SUSFS $ver)"
  set_description "✅ SUSFS $ver loaded ($KO, $STAGE)"
  exit 0
fi
echo "ksud insmod failed: rc=$rc"
dmesg 2>/dev/null | grep -iE 'susfs|insmod|module' | tail -20
set_description "❌ load failed at $STAGE (ksud insmod rc=$rc, see load.log)"
exit 1
