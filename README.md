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
| **Android 15** | API 35 | `common-android15-6.6` | A15-GAPPS, A15-GAPIS, A15-AOSP (No 16KB Page) | `11987101` | Should use KernelSU `v3.2.0` or upper. syscall hardening cannot bypass. |
| **Android 16** | API 36.0 | `common-android16-6.12` | A16-GAPPS, A16-GAPIS, A16-AOSP (No 16KB Page) | `13070261` | Should use KernelSU `v3.2.0` or upper. syscall hardening cannot bypass. |

- KernelSU `v3.2.0` [Bring back x86_64 support with a catch by @hmtheboy154 in \#3328](https://github.com/tiann/KernelSU/pull/3328)
- See <https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/diff/arch/x86/entry/common.c?id=1e3ad78334a69b36e107232e337f9d693dcc9df2>

---

## Workflow Configurations (`build-gki.yml`)

When running the GitHub Action, you will configure:

| Input | Description |
| :--- | :--- |
| **Build ID Preset** | Select from pre-configured AVD builds (e.g. `9964412` for A14 6.1, `11987101` for A15 6.6) or choose `custom` to specify your own. |
| **Custom Build ID** | Required only if "custom" is selected in the preset. Enter the Build ID from [ci.android.com](https://ci.android.com/). |
| **KSU Version Tag** | The tag/commit in the KernelSU repo (e.g., `v3.0.0`). |
| **KSU Variant** | Choose between official `KernelSU` or `KernelSU-Next` (TODO). |
| **Target Architecture** | `x86_64` (for standard Windows/Linux Intel/AMD hosts) or `arm64` (for Apple Silicon or ARM64 hosts). |

---

## x86_64 Syscall Hardening and Bypass Mechanism

Modern Linux kernels (starting with Torvalds' commit [1e3ad783](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/diff/arch/x86/entry/common.c?id=1e3ad78334a69b36e107232e337f9d693dcc9df2)) abandoned the traditional `sys_call_table` lookup on x86_64 in favor of a switch-case conditional direct dispatch to mitigate speculative execution vulnerabilities.

KernelSU's x86_64 implementation (introduced in v3.2.0 via PR [#3328](https://github.com/tiann/KernelSU/pull/3328)) checks for a custom patched capability `X86_FEATURE_INDIRECT_SAFE` and aborts compilation or execution if it is missing:

1. **Compile-time check**: `#error "FATAL: Your kernel is missing the indirect syscall bypass patches!"`
2. **Runtime check**: `if (!boot_cpu_has(X86_FEATURE_INDIRECT_SAFE)) { ... return -ENOSYS; }`

### How the Workflow Handles this Automatically

The workflow dynamically detects the KernelSU version being compiled (using version tags and commit ancestry):

#### For Older KernelSU Versions (Tag < v3.2.0 or commit before [40e8fb7](https://github.com/tiann/KernelSU/commit/40e8fb7616bfd875babb45364f5262657538327a))

If the GKI kernel also doesn't have syscall hardening (e.g. Android 13/14 builds), KernelSU's checks are **automatically bypassed** by patching `drivers/kernelsu/core/init.c` using `sed` to remove the compile-time `#error` and runtime abort block. The kernel still uses traditional `sys_call_table` lookup, so KernelSU works 100% normally.

#### For Newer KernelSU Versions (Tag >= v3.2.0 or latest KernelSU)

The workflow **skips the bypass patch** to keep security checks intact. If you compile for newer AVD images (Android 15/16) that use hardened kernels, you **must**:

1. Manually patch your GKI kernel source code to add the `X86_FEATURE_INDIRECT_SAFE` patches.
2. Launch the emulator with the boot argument `-append "syscall_hardening=off"` to allow indirect syscall routing, otherwise the emulator will bootloop.

---

## How to Deploy Your Custom Kernel

1. Run the **Build AVD GKI Kernel** workflow in your forked repo actions tab.
2. Download the compiled zip artifact containing the kernel image (e.g., `bzImage` for x86_64, `Image` or `Image.gz` for arm64) and `build-info.txt`.
3. Sideload the matching **KernelSU Manager APK** (ensure the version tag matches the KSU version code reported in `build-info.txt`).
4. Boot your emulator from the command line pointing to the custom kernel:

```powershell
# For Windows PowerShell / Command Prompt
emulator -avd <Your_AVD_Name> -kernel C:\path\to\your\downloaded\bzImage -no-snapshot-load -show-kernel [-append "syscall_hardening=off"]
```

- You do not need to specify `-ramdisk` because the new kernel is fully compatible with the stock AVD ramdisk.

- `syscall_hardening=off` is only required for newer KernelSU versions (Tag >= v3.2.0 or latest KernelSU).
