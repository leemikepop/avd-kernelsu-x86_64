# 上游 PR：tiann/KernelSU#3963

> 2026-11-01 送出，狀態：OPEN。

- PR：https://github.com/tiann/KernelSU/pull/3963
- 標題：`kernel: x86_64: fall back to patching do_syscall_64 when x64_sys_call is missing`
- 分支：`leemikepop/KernelSU:fix/x86_64-do_syscall_64-fallback`，只有 1 個 commit，base 是上游 main bec9c134。
- 內容和 `patches/kernelsu/x86_64-do_syscall_64-fallback.patch` 相同。背景和驗證見 [x86_64-syscall-hook-gap-6.1.md](x86_64-syscall-hook-gap-6.1.md)。

## 後續追蹤

- **[#3928](https://github.com/tiann/KernelSU/pull/3928)**：還沒合併，也改了同一個檔案，會把 `ksu_patch_text` 換成 `ksu_patch_memory`。如果它先合併，要 rebase 這個 PR、重新編譯，再 force-push。
- **KernelSU-Next**：上游合併後，再把同樣的修改同步到 KernelSU-Next。patch 能直接套上 dev，只有行號位移。
- **合併之後**：本 repo 的 `patches/kernelsu/` 可以在 KernelSU 新版發布後移除（`.github/avd-targets.json` 也要一起更新）。
