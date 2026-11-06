#!/system/bin/sh
# Retry a load that failed at post-fs-data; load.sh does nothing when SUSFS is already up.
[ -d /sys/module/susfs_guard_lkm ] || [ -e /proc/susfs_path ] && exit 0
exec /system/bin/sh "${0%/*}/load.sh" service
