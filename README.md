# KernelSU LKM for Android Studio AVDs (x86_64)

Root a **stock** Android Studio emulator image with [KernelSU](https://github.com/tiann/KernelSU) or
[KernelSU-Next](https://github.com/KernelSU-Next/KernelSU-Next) in LKM mode. The kernel is never replaced:
only the system image's `ramdisk.img` is patched to load `kernelsu.ko` at boot.

> Looking for the old approach that rebuilds the whole GKI kernel (`bzImage`), or for arm64 hosts?
> It lives on the [`legacy-gki-build`](../../tree/legacy-gki-build) branch.

## Why per-AVD modules

x86_64 GKI kernels have no KMI stability guarantee, and the LKMs attached to upstream releases are built
from the latest DDK source. On some AVD kernels they fail to load (A14) or trip kCFI and panic (A15).
This repository builds `kernelsu.ko` for each AVD kernel against the **exact** `kernel/common` revision
named in that kernel's Android CI build manifest, with the kernel's own config (read from `kernel-ranchu`,
`CONFIG_IKCONFIG=y`) and the matching DDK clang.

## Supported AVDs

| AVD | Kernel | Build ID |
| :--- | :--- | :--- |
| Android 13 (API 33) | `5.15.119-android13-8` | 10871489 |
| Android 14 (API 34) | `6.1.23-android14-4` | 9964412 |
| Android 15 (API 35) | `6.6.30-android15-8` | 11987101 |
| Android 16 (API 36.0) | `6.6.66-android15-8` | 13070261 |
| Android 16 QPR (API 36.1) | `6.12.38-android16-5` | 13996879 |
| Android 17 (API 37.0), and API 37.2 16 KB page size | `6.12.81-android16-6` | 16167562 |
| Android 17 (API 37.1, 16 KB page size) | `6.12.69-android16-6` | 15053784 |

The 16 KB images (`google_apis_playstore_ps16k`) boot the same kernel binary with `page_shift=14`.
**KernelSU-Next v3.4.2 does not work on 16 KB images**: its manager APK ships `libksud.so` (the
`/data/adb/ksud` binary) without 16 KB-aligned LOAD segments, so ksud is never installed. The module itself
loads fine. KernelSU v3.3.1 works on 16 KB images.

x86_64 `google_apis_playstore` images at their latest SDK revision. Other variants of the same API level
(`google_apis`, `default`, `*_ps16k`, `-extNN`) may ship a different kernel; `avd-ksu.py list` shows yours
and `patch` refuses kernels that are not in the table. Minimum upstream versions: **KernelSU v3.3.0**, **KernelSU-Next v3.4.0**.

## Usage

Requires Python 3.8+ and an x86_64 AVD.

### Get `avd-ksu.py`

`avd-ksu.py` is a single file with no dependencies beyond the Python standard library. Download it
from the [latest release](../../releases/latest) (every release attaches it), or clone this repository.

```sh
# macOS / Linux
curl -LO https://github.com/leemikepop/avd-kernelsu-x86_64/releases/latest/download/avd-ksu.py
```

```powershell
# Windows (PowerShell)
Invoke-WebRequest https://github.com/leemikepop/avd-kernelsu-x86_64/releases/latest/download/avd-ksu.py -OutFile avd-ksu.py
```

On first use it downloads the `kernelsu.ko` for your AVD's kernel and the `ksud` / `ksuinit` binaries
for your host from this repository's [Releases](../../releases) (verified against `SHA256SUMS`) and
caches them in `~/.cache/avd-ksu` (override with `AVD_KSU_CACHE`). Without `--version` it uses the
newest stable release of the chosen variant: `kernelsu-vX.Y.Z` or `kernelsu-next-vX.Y.Z` (for the
`kernelsu-next-susfs` preview, which only has prereleases, the newest prerelease).

### Recommended: a separate patched ramdisk (`--out` + `-ramdisk`)

The SDK's `ramdisk.img` is shared by **every AVD that uses the same system image**. Writing the patched
ramdisk to its own file leaves the SDK untouched, so stock and rooted AVDs can live side by side and
undoing it is just booting without `-ramdisk`.

Suggested naming: one AVD per API level, `API<level>-GAPPS` (e.g. `API33-GAPPS`, `API34-GAPPS`,
`API35-GAPPS`, `API36.0-GAPPS`, `API36.1-GAPPS`; keep `.0`/`.1` because 36.0 and 36.1 use different kernels).

```sh
python avd-ksu.py list                                   # AVDs, kernels, ramdisk state

# KernelSU (latest release) / KernelSU-Next (pinned version)
python avd-ksu.py patch --avd API35-GAPPS --out ksu-API35.img
python avd-ksu.py patch --avd API35-GAPPS --variant kernelsu-next --version v3.4.2 --out ksun-API35.img

# boot with it (cold boot; a Quick Boot snapshot would restore the old state)
emulator -avd API35-GAPPS -ramdisk ksu-API35.img -no-snapshot-load
```

Then install and open the manager APK of the **same upstream version**, close the emulator and start
it again with the same command. The manager shows *Working (LKM)*; apps can request root.

Tips:

- Prefer restarting the emulator over rebooting inside Android: Android Emulator 37.2.13 on Windows
  can crash or hang during an in-guest reboot (`adb reboot`, power menu), with or without root.
- Always start the rooted AVD from the command line with `-ramdisk`; starting it from Android Studio's
  Device Manager boots the stock ramdisk (no root, nothing broken).
- `adb shell su` is denied until you grant the Shell app in the manager. Add `--allow-shell` when
  patching to allow it from the start (convenient for testing).
- Re-run `patch` after updating the system image in SDK Manager: a new image revision can come with a
  new kernel, and `patch` refuses kernels it has no module for.
- For Android 16 API 36.1 with LSPosed/Zygisk, give the AVD at least 4096 MB RAM.

### Alternative: patch the SDK ramdisk in place

Without `--out`, `patch` replaces the SDK `ramdisk.img` (original kept as `ramdisk.img.stock`), so the AVD
is rooted even when started from Android Studio, and so is every other AVD on that image.
`python avd-ksu.py restore --avd <name>` puts the stock ramdisk back. A ramdisk already patched by
rootAVD/Magisk is detected through its `ramdisk.img.backup`, which is used as the stock source.

### Preview: KernelSU-Next + SUSFS (`kernelsu-next-susfs`)

KernelSU-Next with the x86_64 port of the SUSFS guard LKM (`susfs_guard_lkm.ko`). It is **not an upstream
release**: it is built from the `susfs-x64-avd` branch of
[leemikepop/KernelSU-Next](https://github.com/leemikepop/KernelSU-Next/tree/susfs-x64-avd), and its
releases are prereleases tagged `kernelsu-next-susfs-v<describe>`, e.g. `kernelsu-next-susfs-v3.4.2-108-gfe10a39f`.
Its kernel module needs a newer manager than KernelSU-Next v3.4.2, so each release attaches the official
KernelSU-Next CI manager build of the upstream commit the branch is based on.

```sh
python avd-ksu.py patch --avd API36.0-GAPPS --variant kernelsu-next-susfs --out ksun-susfs-API36.0.img
emulator -avd API36.0-GAPPS -ramdisk ksun-susfs-API36.0.img -no-snapshot-load
# install + open the release's manager APK, restart the emulator, then (AVD running, rooted):
python avd-ksu.py susfs --avd API36.0-GAPPS     # copy to /data/adb, load now and at every boot
python avd-ksu.py susfs --remove                # unload, stop loading at boot
```

`susfs` needs `adb` (from the SDK's `platform-tools`) and root for the shell; it loads the module with
`/data/adb/ksud insmod` from `/data/adb/post-fs-data.d/50-susfs-guard.sh`. `ksud susfs version` /
`support` show its state; rules are set through the module's interfaces (SUSFS supercalls as used by
`ksu_susfs`, and procfs files such as `/proc/susfs_path`).

Tested on temporary AVDs (root, `susfs` install, autoload after a cold boot, `--remove`, a hidden path
as seen by an app, `uname` spoofing):

| AVD | Status |
| :--- | :--- |
| A15 (API 35), A16 (API 36.0), A16 QPR (API 36.1), A17 (API 37.0) | everything works |
| A13 (API 33), A14 (API 34) | root and SUSFS load, but only partial hiding: `stat`/`open`/`access`/`statx` return `ENOENT`, while `O_PATH` opens, `mkdir` (`EEXIST`) and directory listings still reveal the path. These kernels have no IBT, and SUSFS's x86_64 syscall hooks need an `endbr64`/`__fentry__` landing pad, so its opath, kstat and create layers stay off |
| 16 KB images (API 37.1, API 37.2) | no root: the manager's `libksud.so` is only 4 KB aligned, so `/data/adb/ksud` is never installed (the same limitation as KernelSU-Next v3.4.2). The module loads and the AVD boots |

## Releases

Each release corresponds to one upstream version and is tagged `<variant>-<version>`, e.g.
`kernelsu-v3.3.1`, `kernelsu-next-v3.4.2`. Assets:

| Asset | Content |
| :--- | :--- |
| `<target>_<variant>-<version>_kernelsu.ko` | LKM for one AVD kernel |
| `<target>_kernelsu-next-susfs-<version>_susfs_guard_lkm.ko` | SUSFS guard LKM (`kernelsu-next-susfs` only) |
| `KernelSU_Next_*.apk` | official upstream CI manager build (`kernelsu-next-susfs` only) |
| `ksud-<variant>-<version>-<triple>[.exe]` | host `ksud` (Windows, Linux, macOS) used for `boot-patch` |
| `ksuinit-x86_64-<variant>-<version>` | `ksuinit` placed into the ramdisk as `/init` |
| `avd-targets.json`, `avd-ksu.py`, `SHA256SUMS` | target list, patch tool, checksums |

KernelSU host tools come from the upstream release; KernelSU-Next does not publish host `ksud`
or `ksuinit-x86_64`, so they are built here from the same tag.

## Workflows

- **Build AVD LKMs** (`build-lkm.yml`): any upstream tag, branch or commit → artifacts.
- **Release AVD LKMs** (`release-lkm.yml`): an upstream `vX.Y.Z` tag → GitHub Release.

Per target, CI:

1. reads `kernel-ranchu` straight out of the Google system image zip with HTTP range requests and checks
   its version string against `.github/avd-targets.json`;
2. takes the `kernel/common` revision from `ci.android.com` manifest of that Build ID and downloads that
   revision as a tarball;
3. builds in `ghcr.io/ylarod/ddk-min:<kmi>` with the kernel's own config
   ([`scripts/build-lkm.sh`](scripts/build-lkm.sh)), keeping `CONFIG_RUST=y` code generation even though
   the image has no `rustc` (it changes kCFI hashing and function entry padding);
4. applies the target's patches from [`patches/`](patches/) and fails if the config drifts from the device;
5. checks the module with [`scripts/x86_icall_windows.py`](scripts/x86_icall_windows.py): on 6.2+
   kernels no indirect call may have bytes in front of it that the kernel could take for a kCFI
   sequence and rewrite at load time (see `x86_64-kcfi-icall-trampoline.patch` below).

Local build (Docker): `scripts/build-target.sh <target> <kernelsu|kernelsu-next> <upstream-repo> <ref> <work-dir>`.

### Patches

Applied in the order listed in `.github/avd-targets.json`. A patch that upstream has already merged
applies in reverse and is skipped.

- `x86_64-seccomp-skip.patch` (A13, A14; upstream
  [tiann/KernelSU#3966](https://github.com/tiann/KernelSU/pull/3966)): the `do_syscall_64`
  replacement re-read the syscall number even when seccomp had denied the syscall, so the
  syscall ran anyway. This affects upstream v3.3.0 and v3.3.1 on kernels < 5.16.
- `x86_64-do_syscall_64-fallback.patch` (A14 only; upstream
  [tiann/KernelSU#3963](https://github.com/tiann/KernelSU/pull/3963)): the 6.1.23 AVD kernel has
  neither `x64_sys_call` nor commit fb13b11d, but upstream only falls back to replacing
  `do_syscall_64` on kernels < 5.16, so the module loads but its syscall hooks never fire. See
  [docs/notes/x86_64-syscall-hook-gap-6.1.md](docs/notes/x86_64-syscall-hook-gap-6.1.md).
- `x86_64-kcfi-icall-trampoline.patch` (A15, A16, A17; not upstream yet): on 6.2+ x86_64 kernels
  `module_finalize()` rewrites the four bytes after a `41 ba` / `eb 0c` found 14 bytes in front of
  any indirect call, taking it for the kCFI caller sequence. In front of a `__nocfi` call those bytes
  are arbitrary, and in six places they come from a relocation, so they depend on where the module was
  loaded: in `ksu_hook_execve_common()` an unlucky load (estimated at most 1 in 32768) would corrupt the
  code before the call to the original `execve`. The patch routes every unchecked call through one
  `noinline __nocfi` trampoline, `ksu_icall8()`, whose call has fixed bytes in front of it.

## Adding an AVD kernel

1. Add an entry to `.github/avd-targets.json`: `kernel_release` and `build_id` from
   `python avd-ksu.py list`, `kmi`, and `probe_image` (zip name in Google's
   [sys-img repository](https://dl.google.com/android/repository/sys-img/google_apis_playstore/sys-img2-3.xml)).
2. Run **Build AVD LKMs** for that target and boot-test it on a dedicated test AVD
   (boot 1 wipes the AVD's user data):
   `ALLOW_WIPE=1 scripts/boot-test.sh <test-avd> <patched-ramdisk.img> <manager.apk> <package> <out-dir>`.

## Credits

- [5ec1cff, "在 AVD 上使用 KernelSU"](https://5ec1cff.github.io/my-blog/2024/01/16/avd-ksu/) and the
  x86_64 LKM work in KernelSU [#3562](https://github.com/tiann/KernelSU/pull/3562) / [#3570](https://github.com/tiann/KernelSU/pull/3570).
- [nzaar9/avd-kernelsu](https://github.com/nzaar9/avd-kernelsu) for early release packaging ideas.
- DDK images by [Ylarod](https://github.com/Ylarod).

## License

- This repository (scripts, workflows, `avd-ksu.py`, docs) is [Apache-2.0](LICENSE).
- [`patches/`](patches/) modify KernelSU's `kernel/` directory and are
  [GPL-2.0-only](patches/LICENSE), like the code they change.
- Release assets keep their upstream licenses: `*_kernelsu.ko` is GPL-2.0-only, and `ksud` /
  `ksuinit` are GPL-3.0-or-later. Each release's notes link the exact upstream commit, patches,
  `kernel/common` commit and build scripts used to build it.
