#!/system/bin/sh
# Installer hook, sourced by the KernelSU module installer ($MODPATH, $KSU, $ARCH, ui_print, abort).
[ "$KSU" = true ] || abort "- KernelSU (Next) required"
[ "$ARCH" = x64 ] || abort "- x86_64 AVDs only (this device: $ARCH)"

REL=$(cat /proc/sys/kernel/osrelease)
KO=
while read -r rel file; do
  [ "$rel" = "$REL" ] && KO=$file && break
done < "$MODPATH/kos"
if [ -n "$KO" ]; then
  ui_print "- kernel $REL -> $KO"
elif [ -d /sys/module/susfs_guard_lkm ]; then
  # A loaded SUSFS may spoof the release string, so a mismatch proves nothing here.
  ui_print "! kernel $REL is not in this module, but SUSFS is loaded and may spoof it"
  ui_print "! installing anyway; check load.log after a restart"
else
  ui_print "! no SUSFS build for kernel $REL. Supported:"
  while read -r rel file; do ui_print "    $rel"; done < "$MODPATH/kos"
  abort "- wrong AVD kernel for this release"
fi

# Older avd-ksu.py versions loaded SUSFS from a post-fs-data.d script; this module replaces it.
LEGACY=/data/adb/post-fs-data.d/50-susfs-guard.sh
if [ -f "$LEGACY" ] && grep -q 'insmod /data/adb/susfs_guard_lkm.ko' "$LEGACY"; then
  rm -f "$LEGACY" /data/adb/susfs_guard_lkm.ko
  ui_print "- removed the boot script of avd-ksu.py susfs --legacy"
fi

set_perm_recursive "$MODPATH" 0 0 0755 0644
for f in load.sh post-fs-data.sh service.sh; do set_perm "$MODPATH/$f" 0 0 0755; done
ui_print "- loads at every boot; the module card shows the result"
