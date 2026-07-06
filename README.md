# AVD GKI Kernel Compiler for KernelSU (x86_64)

This repository provides an automated, precise GitHub Actions workflow to build Generic Kernel Image (GKI) kernels with KernelSU integrated, specifically optimized for **Android Virtual Devices (AVD)**.

Unlike typical builders that sync the branch HEAD (which can lead to kernel-module mismatches and syscall table hardening issues), this workflow compiles the kernel using the **exact Android CI Build ID manifest** that your emulator image was built with.

---

## Features

- **Binary Compatibility (Zero Module Repacking)**: By syncing the exact Build ID manifest, the compiled kernel matches your AVD's pre-installed module signatures (vermagic) perfectly. You don't need to rebuild or repack `ramdisk.img`.
- **Resolves Sandbox versioning bug (Displays correct version instead of 16)**: Since Bazel compiles inside a sandbox without access to `.git`, KernelSU normally falls back to reporting version `16`. This workflow dynamically calculates the version based on git commit counts and injects it into the sandboxed source files prior to compiling.

<https://android.googlesource.com/kernel/manifest>

---

## AVD Versions & Common Kernels Presets

The following are the pre-configured AVD builds and their respective kernel versions:

| Android Version | API Level | Kernel Branch | Target AVDs | Build ID (Preset) | Note |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Android 13** | API 33 | `common-android13-5.15` | A13-GAPPS, A13-GAPIS, A13-AOSP | `10871489` | |
| **Android 14** | API 34 | `common-android14-6.1` | A14-GAPPS, A14-GAPIS, A14-AOSP | `9964412` | |
| **Android 15** | API 35 | `common-android15-6.6` | A15-GAPPS, A15-GAPIS, A15-AOSP (No 16KB Page) | `11987101` | Default to KernelSU `v3.1.0`; `v3.2.0+` is an experimental x86_64 path. |
| **Android 16** | API 36.0 | `common-android15-6.6-2025-02` | A16-GAPPS, A16-GAPIS, A16-AOSP (No 16KB Page) | `13070261` | API 36.0 AVD still uses android15-6.6-2025-02 GKI. Default to KernelSU `v3.1.0`. |
| **Android 16** | API 36.1 | `common-android16-6.12` | A16-GAPPS, A16-GAPIS, A16-AOSP (No 16KB Page) | `13996879` | API 36.1 moves to 6.12 GKI. Default to KernelSU `v3.1.0`. |

- KernelSU `v3.2.0` introduced [Bring back x86_64 support with a catch by @hmtheboy154 in \#3328](https://github.com/tiann/KernelSU/pull/3328). For AVD testing, start from `v3.1.0` or older first.
- See <https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/diff/arch/x86/entry/common.c?id=1e3ad78334a69b36e107232e337f9d693dcc9df2>

---

## Workflow Configurations (`build-gki.yml`)

When running the GitHub Action, you will configure:

| Input | Description |
| :--- | :--- |
| **AVD Target** | Select `all` to build every preset in `.github/avd-targets.json`, or select one target such as `a14-api34-6.1`. |
| **KSU Version Tag** | The tag/commit in the KernelSU repo. The default is `v3.1.0`; use `v3.2.0+` only when testing the newer x86_64 path. |
| **KSU Variant** | Choose between official `KernelSU` or `KernelSU-Next`. |
| **Target Architecture** | `x86_64` (for standard Windows/Linux Intel/AMD hosts), `arm64` (for Apple Silicon or ARM64 hosts), or `both`. |
| **Release Type** | `Actions` uploads workflow artifacts only. `Pre-Release` and `Release` collect all matrix artifacts into a GitHub Release. |

Artifacts include Android/API, kernel version, architecture, Build ID, and KernelSU version in their name, e.g. `dist-A16-API36.0-6.6-x86_64-13070261-v310`. This keeps Android 16 API 36.0 (`6.6`) distinct from Android 16 API 36.1 (`6.12`), and avoids collisions when building both architectures.

---

## x86_64 Syscall Hardening and Bypass Mechanism

Modern Linux kernels (starting with Torvalds' commit [1e3ad783](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/diff/arch/x86/entry/common.c?id=1e3ad78334a69b36e107232e337f9d693dcc9df2)) abandoned the traditional `sys_call_table` lookup on x86_64 in favor of a switch-case conditional direct dispatch to mitigate speculative execution vulnerabilities.

For AVD x86_64 testing, this project now defaults to **KernelSU `v3.1.0`**. In local testing, KernelSU `v3.2.0+` / newer KernelSU-Next builds can initialize the kernel hook but still fail later in the AVD boot flow, causing the manager to report "not installed". The practical baseline is therefore `v3.1.0` or older first, then test `v3.2.0+` only as an explicit experiment.

KernelSU's newer x86_64 implementation (introduced in v3.2.0 via PR [#3328](https://github.com/tiann/KernelSU/pull/3328)) checks for a custom patched capability `X86_FEATURE_INDIRECT_SAFE` and aborts compilation or execution if it is missing:

1. **Compile-time check**: `#error "FATAL: Your kernel is missing the indirect syscall bypass patches!"`
2. **Runtime check**: `if (!boot_cpu_has(X86_FEATURE_INDIRECT_SAFE)) { ... return -ENOSYS; }`

### How the Workflow Handles this Automatically

The workflow first integrates KernelSU and detects whether the selected ref contains the `X86_FEATURE_INDIRECT_SAFE` checks. With the default `v3.1.0`, these checks are absent, so the workflow skips the syscall hardening patch path entirely.

For KernelSU v3.2.0 or newer:

- Android 13/14 GKI (`5.15` / `6.1`) still uses the syscall table path, so the workflow removes KernelSU's `X86_FEATURE_INDIRECT_SAFE` checks.
- Android 15+ GKI (`6.6` / `6.12`) uses switch-case syscall hardening, so the workflow keeps KernelSU's checks and patches the GKI kernel.

Android Emulator does not expose a stable top-level `-append` option for kernel cmdline arguments. For v3.2.0+ experimental x86_64 builds, the workflow therefore bakes the testing choice into the kernel by defaulting `syscall_hardening` to `off` after applying the patch set. The generated `build-info.txt` records this as `x86_64 Syscall Hardening Default Off: true` and `Required Emulator Boot Arg: none`.

For manual builds and exact patch commands, see [the manual guide](avd-kernelsu-x86_64-manual.md).

---

## How to Deploy Your Custom Kernel

1. Run the **Build AVD GKI Kernels with KernelSU** workflow in your forked repo actions tab.
2. Download the compiled zip artifact containing the kernel image (e.g., `bzImage` for x86_64, `Image` or `Image.gz` for arm64) and `build-info.txt`.
3. Sideload the matching **KernelSU Manager APK** (ensure the version tag matches the KSU version code reported in `build-info.txt`).
4. Boot your emulator from the command line pointing to the custom kernel:

```powershell
# For Windows PowerShell / Command Prompt
emulator -avd <Your_AVD_Name> -kernel C:\path\to\your\downloaded\bzImage -no-snapshot-load -show-kernel
```

- You do not need to specify `-ramdisk` because the new kernel is fully compatible with the stock AVD ramdisk.

- Do not pass `-append "syscall_hardening=off"` directly to `emulator`; current Android Emulator builds report it as an unknown option.

---

## Credits

- Workflow structure and release packaging ideas were inspired by [nzaar9/avd-kernelsu](https://github.com/nzaar9/avd-kernelsu), an AVD KernelSU builder for Android 14/15/16.
- Early AVD KernelSU build and module compatibility notes were inspired by [5ec1cff's "在 AVD 上使用 KernelSU"](https://5ec1cff.github.io/my-blog/2024/01/16/avd-ksu/).
