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
## Releases

Each release corresponds to one upstream version and is tagged `<variant>-<version>`, e.g.
`kernelsu-v3.3.1`, `kernelsu-next-v3.4.2`. Assets:

| Asset | Content |
| :--- | :--- |
| `<target>_<variant>-<version>_kernelsu.ko` | LKM for one AVD kernel |
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
4. applies the target's patches from [`patches/`](patches/) and fails if the config drifts from the device.

Local build (Docker): `scripts/build-target.sh <target> <kernelsu|kernelsu-next> <upstream-repo> <ref> <work-dir>`.

### Patches

- `x86_64-do_syscall_64-fallback.patch` (A14 only): the 6.1.23 AVD kernel has neither `x64_sys_call`
  nor commit fb13b11d, but upstream only falls back to replacing `do_syscall_64` on kernels < 5.16, so
  the module loads but its syscall hooks never fire. See
  [docs/notes/x86_64-syscall-hook-gap-6.1.md](docs/notes/x86_64-syscall-hook-gap-6.1.md).

## Adding an AVD kernel

1. Add an entry to `.github/avd-targets.json`: `kernel_release` and `build_id` from
   `python avd-ksu.py list`, `kmi`, and `probe_image` (zip name in Google's
   [sys-img repository](https://dl.google.com/android/repository/sys-img/google_apis_playstore/sys-img2-3.xml)).
2. Run **Build AVD LKMs** for that target and boot-test it.

## Credits

- [5ec1cff, "在 AVD 上使用 KernelSU"](https://5ec1cff.github.io/my-blog/2024/01/16/avd-ksu/) and the
  x86_64 LKM work in KernelSU [#3562](https://github.com/tiann/KernelSU/pull/3562) / [#3570](https://github.com/tiann/KernelSU/pull/3570).
- [nzaar9/avd-kernelsu](https://github.com/nzaar9/avd-kernelsu) for early release packaging ideas.
- DDK images by [Ylarod](https://github.com/Ylarod).
