#!/usr/bin/env bash
# Boot-test a patched ramdisk on an AVD (does not modify the AVD's system image).
#   boot-test.sh <avd> <patched-ramdisk.img> <manager.apk> <package> <out-dir>
# Boot 1: module loaded, hooks installed; install + open the manager (installs /data/adb/ksud).
# Boot 2: ksud post-fs-data/services/boot-completed ran, `su` gives uid 0.
# Exit 0 only if boot 2 has root. Uses emulator port 5580 (override with PORT=).
# Boot 2 is a cold restart (emulator killed, started again without -wipe-data) rather than an
# in-guest `adb reboot`: Android Emulator 37.2.13 on Windows segfaults/hangs on guest reboot,
# even with a stock ramdisk.
set -u
AVD=$1; RD=$2; APK=$3; PKG=$4; OUT=$5
PORT=${PORT:-5580}
SDK=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$LOCALAPPDATA/Android/Sdk}}
winpath() { if command -v cygpath >/dev/null; then cygpath -w "$1"; else echo "$1"; fi; }
export MSYS_NO_PATHCONV=1
rm -rf "$OUT"; mkdir -p "$OUT"; LOG=$OUT/emulator.log
A="adb -s emulator-$PORT"
r() { echo "[$(basename "$OUT")] $*" | tee -a "$OUT/summary.txt"; }
wait_boot() {
  for i in $(seq 1 200); do
    sleep 3
    [ "$($A shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ] && { echo $((i * 3)); return 0; }
    grep -qa 'Kernel panic' "$LOG" && break
  done
  echo FAIL; return 1
}
open_manager() {   # retry until the manager is the focused window
  for _ in 1 2 3 4 5 6; do
    $A shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
    sleep 5
    $A shell dumpsys window 2>/dev/null | grep -q "mCurrentFocus=.*$PKG" && { sleep 10; return 0; }
  done
  return 1
}
start_emu() {   # start_emu [extra args...]; appends kernel/emulator output to $LOG
  "$SDK/emulator/emulator" -avd "$AVD" -ramdisk "$(winpath "$RD")" -no-snapshot "$@" -no-window \
    -no-audio -no-boot-anim -show-kernel -port "$PORT" >> "$LOG" 2>&1 &
  EMU_PID=$!
}
stop_emu() {
  timeout 30 $A emu kill >/dev/null 2>&1
  for _ in $(seq 1 20); do kill -0 "$EMU_PID" 2>/dev/null || return 0; sleep 2; done
  kill -9 "$EMU_PID" 2>/dev/null; sleep 3
}
finish() { stop_emu; exit "$1"; }

timeout 30 $A emu kill >/dev/null 2>&1; sleep 3
start_emu -wipe-data
t=$(wait_boot) || { r "BOOT1 FAIL"; grep -aE 'Kernel panic|KernelSU|ksuinit|RIP:|Call Trace' "$LOG" | tail -30 > "$OUT/fail.txt"; finish 1; }
r "boot1 ${t}s | $($A shell uname -r | tr -d '\r')"
r "module: $($A shell cat /proc/modules | grep -i kernelsu | tr -d '\r' | cut -c1-40)"
grep -aE 'welcome to KernelSU|x64_sys_call=|patching (x64_sys_call|do_syscall_64)|dispatcher installed|KernelSU.*(fail|error|invalid)|ksuinit.*(rror|fail)' "$LOG" \
  | grep -v 'load_allow_list\|modules.rc' | head -8 | sed 's/^/   /' | tee -a "$OUT/summary.txt"
# Wait for the package manager and launcher before installing / launching.
for _ in $(seq 1 40); do $A shell pm path android >/dev/null 2>&1 && break; sleep 3; done
$A install -r "$(winpath "$APK")" >/dev/null 2>&1 || { r "install failed"; finish 1; }
open_manager || r "warning: manager did not reach the foreground"
$A exec-out screencap -p > "$OUT/manager.png"

timeout 30 $A shell sync >/dev/null 2>&1
stop_emu
mark=$(wc -l < "$LOG")
start_emu
t=$(wait_boot) || { r "BOOT2 FAIL"; finish 1; }
r "boot2 ${t}s"
tail -n +"$mark" "$LOG" | grep -aE "Cannot find '/data/adb/ksud'|Service 'exec [0-9]+ \(/data/adb/ksud [a-z-]+\)'.*exited with status" \
  | sed -E 's/^\[ *[0-9.]+\] //' | head -6 | sed 's/^/   /' | tee -a "$OUT/summary.txt"
uid=$($A shell su -c 'id -u' 2>&1 | tr -d '\r')
r "su(boot2): uid=$uid selinux=$($A shell getenforce | tr -d '\r')"
open_manager >/dev/null; $A exec-out screencap -p > "$OUT/manager-boot2.png"
if [ "$uid" = 0 ]; then r PASS; finish 0; else r FAIL; finish 1; fi
