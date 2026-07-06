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
| **Android 13** | API 33 | `common-android13-5.15` | A13-GAPPS, A13-GAPIS, A13-AOSP | `10871489` | Auto default: KernelSU `v3.1.0`. |
| **Android 14** | API 34 | `common-android14-6.1` | A14-GAPPS, A14-GAPIS, A14-AOSP | `9964412` | Auto default: KernelSU `v3.1.0`. |
| **Android 15** | API 35 | `common-android15-6.6` | A15-GAPPS, A15-GAPIS, A15-AOSP (No 16KB Page) | `11987101` | Auto default: KernelSU `v3.2.0` with x86_64 hardening patches baked in. |
| **Android 16** | API 36.0 | `common-android15-6.6-2025-02` | A16-GAPPS, A16-GAPIS, A16-AOSP (No 16KB Page) | `13070261` | API 36.0 AVD still uses android15-6.6-2025-02 GKI. Auto default: KernelSU `v3.2.0`. |
| **Android 16** | API 36.1 | `common-android16-6.12` | A16-GAPPS, A16-GAPIS, A16-AOSP (No 16KB Page) | `13996879` | API 36.1 moves to 6.12 GKI. Auto default: KernelSU `v3.2.0`. |

- KernelSU `v3.2.0` introduced [Bring back x86_64 support with a catch by @hmtheboy154 in \#3328](https://github.com/tiann/KernelSU/pull/3328). This workflow keeps A13/A14 on `v3.1.0` by default, and uses `v3.2.0` for A15+ where the syscall hardening patch path is applied.
- See <https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/diff/arch/x86/entry/common.c?id=1e3ad78334a69b36e107232e337f9d693dcc9df2>

---

## Workflow Configurations

There are two user-facing GitHub Actions workflows:

- **Build AVD GKI Kernels** (`build-gki.yml`): artifact-only builds for testing. This workflow accepts `auto`, tags, branches, or commit refs.
- **Release AVD GKI Kernels** (`release-gki.yml`): GitHub Release publishing. This workflow only accepts explicit KernelSU / KernelSU-Next version tags in `vX.Y.Z` format.

The shared build implementation lives in `_build-gki-core.yml` and is called by both workflows.

### Artifact Builds

| Input | Description |
| :--- | :--- |
| **AVD Target** | Select `all` to build the preset set for the selected mode, or select one target such as `a14-api34-6.1`. |
| **KSU Ref** | `auto` uses per-target defaults (`v3.1.0` for A13/A14, `v3.2.0` for A15+). You may also provide a tag, branch, or commit ref for testing. |
| **KSU Variant** | Choose between official `KernelSU` or `KernelSU-Next`. |
| **Target Architecture** | `x86_64` (for standard Windows/Linux Intel/AMD hosts), `arm64` (for Apple Silicon or ARM64 hosts), or `both`. |

Artifacts include Android/API, kernel version, architecture, Build ID, and KernelSU version in their name, e.g. `dist-A16-API36.0-6.6-x86_64-13070261-v320`. This keeps Android 16 API 36.0 (`6.6`) distinct from Android 16 API 36.1 (`6.12`), and avoids collisions when building both architectures.

### Release Builds

Use **Release AVD GKI Kernels** for publishing. Select the KernelSU project and enter a version tag such as `v3.1.0`, `v3.2.0`, or `v3.3.0`.

- KernelSU / KernelSU-Next `v3.1.x` or older: publishes A13, A14, A15, A16 API 36.0, and A16 API 36.1.
- KernelSU / KernelSU-Next `v3.2.0` or newer: publishes only A15, A16 API 36.0, and A16 API 36.1.
- `auto`, branches, and commit hashes are intentionally rejected by the release workflow so one GitHub Release maps to one upstream version tag.
- Release tags use the form `KernelSU-v3.2.0` or `KernelSU-Next-v3.3.0`; reruns append `-r2`, `-r3`, and so on if the base tag already exists.

---

## x86_64 Syscall Hardening and Bypass Mechanism

Modern Linux kernels (starting with Torvalds' commit [1e3ad783](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/diff/arch/x86/entry/common.c?id=1e3ad78334a69b36e107232e337f9d693dcc9df2)) abandoned the traditional `sys_call_table` lookup on x86_64 in favor of a switch-case conditional direct dispatch to mitigate speculative execution vulnerabilities.

For AVD x86_64 testing, `auto` now defaults to **KernelSU `v3.1.0` for A13/A14** and **KernelSU `v3.2.0` for A15+**. A13/A14 still use the older syscall table path, while A15+ uses the newer switch-case hardening path that needs the additional kernel patching.

KernelSU's newer x86_64 implementation (introduced in v3.2.0 via PR [#3328](https://github.com/tiann/KernelSU/pull/3328)) checks for a custom patched capability `X86_FEATURE_INDIRECT_SAFE` and aborts compilation or execution if it is missing:

1. **Compile-time check**: `#error "FATAL: Your kernel is missing the indirect syscall bypass patches!"`
2. **Runtime check**: `if (!boot_cpu_has(X86_FEATURE_INDIRECT_SAFE)) { ... return -ENOSYS; }`

### How the Workflow Handles this Automatically

The workflow first integrates KernelSU and detects whether the selected ref contains the `X86_FEATURE_INDIRECT_SAFE` checks. With `v3.1.0`, these checks are absent, so the workflow skips the syscall hardening patch path entirely.

For KernelSU v3.2.0 or newer:

- Android 13/14 GKI (`5.15` / `6.1`) still uses the syscall table path, so the workflow removes KernelSU's `X86_FEATURE_INDIRECT_SAFE` checks.
- Android 15+ GKI (`6.6` / `6.12`) uses switch-case syscall hardening, so the workflow keeps KernelSU's checks and patches the GKI kernel.

Android Emulator does not expose a stable top-level `-append` option for kernel cmdline arguments. For v3.2.0+ x86_64 builds, the workflow therefore bakes the testing choice into the kernel by defaulting `syscall_hardening` to `off` after applying the patch set. The generated `build-info.txt` records this as `x86_64 Syscall Hardening Default Off: true` and `Required Emulator Boot Arg: none`.

For manual builds and exact patch commands, see [the manual guide](avd-kernelsu-x86_64-manual.md).

---

## How to Deploy Your Custom Kernel

1. Run the **Build AVD GKI Kernels** workflow in your forked repo actions tab, or download from a published **Release AVD GKI Kernels** run.
2. Download the compiled zip artifact containing the kernel image (e.g., `bzImage` for x86_64, `Image` or `Image.gz` for arm64) and `build-info.txt`.
3. Sideload the matching **KernelSU Manager APK** (ensure the version tag matches the KSU version code reported in `build-info.txt`).
4. Boot your emulator from the command line pointing to the custom kernel:

```powershell
# For Windows PowerShell / Command Prompt
emulator -avd <Your_AVD_Name> -kernel C:\path\to\your\downloaded\bzImage -no-snapshot-load -show-kernel
```

- You do not need to specify `-ramdisk` because the new kernel is fully compatible with the stock AVD ramdisk.

- For Android 16 API 36.1 with LSPosed/Zygisk, use at least 4096 MB RAM. A 2 GB AVD can make `lspd` abort during ART startup with `Failed to allocate LinearAlloc` / anonymous `mmap(..., 2147479552, ...)` out-of-memory errors:

```powershell
emulator -avd <Your_AVD_Name> -memory 4096 -kernel C:\path\to\your\downloaded\bzImage -no-snapshot-load -show-kernel
```

- Do not pass `-append "syscall_hardening=off"` directly to `emulator`; current Android Emulator builds report it as an unknown option.

---

## Credits

- Workflow structure and release packaging ideas were inspired by [nzaar9/avd-kernelsu](https://github.com/nzaar9/avd-kernelsu), an AVD KernelSU builder for Android 14/15/16.
- Early AVD KernelSU build and module compatibility notes were inspired by [5ec1cff's "在 AVD 上使用 KernelSU"](https://5ec1cff.github.io/my-blog/2024/01/16/avd-ksu/).
