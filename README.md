# AVD GKI Kernel Compiler for KernelSU (x86_64 & arm64)

This repository provides an automated, precise GitHub Actions workflow to build Generic Kernel Image (GKI) kernels with KernelSU or KernelSU-Next integrated, specifically optimized for **Android Virtual Devices (AVD)**.

Unlike typical builders that sync the branch HEAD (which can lead to kernel-module mismatches and syscall table hardening issues), this workflow compiles the kernel using the **exact Android CI Build ID manifest** that your emulator image was built with.

---

## Features

- **Binary Compatibility (Zero Module Repacking)**: By syncing the exact Build ID manifest, the compiled kernel matches your AVD's pre-installed module signatures (vermagic) perfectly. You don't need to rebuild or repack `ramdisk.img`.
- **Bypasses Syscall Hardening**: Older GKI builds (like API 34 Build `9964412`) do not have upstream system call hardening. Syncing the exact historical source code allows you to run KernelSU without dealing with indirect syscall routing panics.
- **Resolves Sandbox versioning bug (Displays correct version instead of 16)**: Since Bazel compiles inside a sandbox without access to `.git`, KernelSU normally falls back to reporting version `16`. This workflow dynamically calculates the version based on git commit counts and injects it into the sandboxed source files prior to compiling.
- **Support for custom Build IDs**: You can choose from pre-defined AVD targets (Android 13, 14, 15) or manually supply any historical or future Android CI Build ID (e.g. Android 16).

---

## Workflow Configurations (`build-gki.yml`)

When running the GitHub Action, you will configure:

| Input | Description |
| :--- | :--- |
| **Build ID Preset** | Select from pre-configured AVD builds (e.g. `9964412` for A14 6.1, `11987101` for A15 6.6) or choose `custom` to specify your own. |
| **Custom Build ID** | Required only if "custom" is selected in the preset. Enter the Build ID from [ci.android.com](https://ci.android.com/). |
| **KSU Version Tag** | The tag/commit in the KernelSU repo (e.g., `v0.9.5`, `v3.0.0` or a specific Git Hash). |
| **KSU Variant** | Choose between official `KernelSU` or `KernelSU-Next`. |
| **Target Architecture** | `x86_64` (for standard Windows/Linux Intel/AMD hosts) or `arm64` (for Apple Silicon or ARM64 hosts). |

---

## How to Deploy Your Custom Kernel

1. Run the **Build AVD GKI Kernel** workflow in your forked repo actions tab.
2. Download the compiled zip artifact containing the kernel image (e.g., `bzImage` for x86_64, `Image` or `Image.gz` for arm64) and `build-info.txt`.
3. Sideload the matching **KernelSU Manager APK** (ensure the version tag matches the KSU version code reported in `build-info.txt`).
4. Boot your emulator from the command line pointing to the custom kernel:

```powershell
# For Windows PowerShell / Command Prompt
emulator -avd <Your_AVD_Name> -kernel C:\path\to\your\downloaded\bzImage -no-snapshot-load -show-kernel
```

*Note: You do not need to specify `-ramdisk` because the new kernel is fully compatible with the stock AVD ramdisk.*