# 上游 PR：tiann/KernelSU#3963

> 2026-11-01 送出，狀態：OPEN。

- PR：https://github.com/tiann/KernelSU/pull/3963
- 標題：`kernel: x86_64: fall back to patching do_syscall_64 when x64_sys_call is missing`
- 分支：`leemikepop/KernelSU:fix/x86_64-do_syscall_64-fallback`，base 是上游 main bec9c134。
- 對應本 repo 的 `patches/x86_64-do_syscall_64-fallback.patch`。這個 patch 是套在 `x86_64-seccomp-skip.patch`（#3966）之後的版本，已經包含 Copilot review 的 x32 修正；seccomp 的部分在 #3966。背景和驗證見 [x86_64-syscall-hook-gap-6.1.md](x86_64-syscall-hook-gap-6.1.md)。

## 後續追蹤

- **Copilot review（2026-11-01）**：兩則留言，修正已在本機驗證，還沒推送。
  - seccomp 繞過（High）：另開小 PR 處理，見下一節。#3963 等那個 PR 有結論後再同步。
  - x32（Medium）：5.16 以上開了 `CONFIG_X86_X32_ABI` 就不用 fallback。不實作 x32 分派，原因是 GKI/AVD 都沒開 X32、測不到，維護者也刻意忽略 x32。
- **[#3928](https://github.com/tiann/KernelSU/pull/3928)**：還沒合併，也改了同一個檔案，會把 `ksu_patch_text` 換成 `ksu_patch_memory`。如果它先合併，要 rebase 這個 PR、重新編譯，再 force-push。
- **KernelSU-Next**：上游合併後，再把同樣的修改同步到 KernelSU-Next。patch 能直接套上 dev，只有行號位移。KernelSU-Next dev 也有同一個 seccomp bug。
- **合併之後**：本 repo 的 `patches/` 可以在 KernelSU 新版發布後移除（`.github/avd-targets.json` 也要一起更新）。

## 另開的 seccomp 修正 PR：[#3966](https://github.com/tiann/KernelSU/pull/3966)

- 2026-11-02 送出，狀態：OPEN。
- 分支：`leemikepop/KernelSU:fix/x86_64-seccomp-skip`（本機 worktree `../KernelSU-pr-seccomp`），base 是上游 main 28db74f6，只有 1 個 commit（0f709311）。
- 修改：`my_do_syscall_64` 只在 `syscall_enter_from_user_mode` 沒有回傳 -1 時，才重新讀 syscall 編號。
- bug 來源：#3562（2026-07-11），v3.3.0、v3.3.1 都有。影響開了 `CONFIG_KSU_X86_PATCH_SYSCALL_DISPATCHER`（官方 LKM CI 有開）、kernel 在 5.16 以下的 x86_64。
- 驗證：AVD 13（5.15.119）和 AVD 14（6.1.23，搭配 #3963）的 seccomp `SECCOMP_RET_ERRNO` 測試，修正前 BYPASS，修正後 PASS，root 也正常。

## 待辦：5.10 的 `do_syscall_64` 參數順序（未驗證）

- Linux v5.10 的簽名是 `do_syscall_64(unsigned long nr, struct pt_regs *regs)`，5.15 則是 `(struct pt_regs *regs, int nr)`。
- 上游的 `my_do_syscall_64(regs, nr)` 照 5.15 的順序寫，但在 5.16 以下一律替換 `do_syscall_64`。上游 `kernel/build-all-x64.sh` 也有編 `android12-5.10`、`android13-5.10`。
- 如果 ACK 5.10 沒有 backport 參數順序的修改，x86_64 LKM 在 5.10 上很可能第一個 syscall 就 crash。
- 驗證方式：下載 android-32（Android 12L，5.10 kernel）的 system image，加一個 `a12` target 編 LKM，用 `scripts/boot-test.sh` 跑一次。
  - 先確認 ACK android12-5.10 的 `arch/x86/entry/common.c` 和 `entry_64.S` 實際的參數順序。
