# KernelSU x86_64 LKM：A14（6.1.23）的 syscall hook 空窗

> 狀態（2026-11-01）：`< 6.7` 版 patch 已經送上游：https://github.com/tiann/KernelSU/pull/3963

## 症狀

在 A14 AVD（`6.1.23-android14-4-00257-g7e35917775b8-ab9964412`）上，用確切原始碼重編的 `kernelsu.ko` 可以正常載入：

- `dispatcher installed at slot 134`
- 各項 feature 都有初始化

但是 Manager 一直顯示「Not installed」。原因是 setresuid、execve 這類被導向的 syscall hook 從來沒有被呼叫：

- log 裡看不到授權 Manager 的紀錄、`packages.list` 的處理紀錄，也沒有 SELinux 規則注入的紀錄。
- `/data/adb/ksud` 一直沒有被安裝。重開機後，init 的三個 `exec /data/adb/ksud ...` 都失敗：`Cannot find '/data/adb/ksud'`。

開機 log 的關鍵行：

```
KernelSU: x64_sys_call=0x0
KernelSU: dispatcher installed at slot 134
```

`x64_sys_call=0x0` 之後完全沒有 `patching ...`，代表兩種 dispatcher patch 都沒有套上。

## 原因

x86_64 LKM（`CONFIG_KSU_X86_PATCH_SYSCALL_DISPATCHER`）要讓 KernelSU 的 `ksu_syscall_table` 真正接到 syscall，有兩條路：

| 路徑 | 條件（上游寫法） | 用途 |
| :--- | :--- | :--- |
| patch `x64_sys_call` | 永遠會嘗試 | kernel 有 [1e3ad78334a6](https://github.com/torvalds/linux/commit/1e3ad78334a69b36e107232e337f9d693dcc9df2)（mainline 6.9 引入，多數 GKI 有 backport）時，syscall 都經過它 |
| 整個替換 `do_syscall_64` | `#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 16, 0)` | 給 A13 5.15 用：該版本缺 [fb13b11d5387](https://github.com/torvalds/linux/commit/fb13b11d53875e28e7fbf0c26b288e4ea676aa9f)，sys_enter tracepoint 改寫的 nr 不會被重讀 |

上游的隱含假設是「5.16 以上一定有 `x64_sys_call`」，但 AVD A14 的 6.1.23（2023-04 編譯）兩樣都沒有：

- 沒有 `x64_sys_call`，因為 backport 比這個 build 晚。
- 版本 ≥ 5.16，所以 `do_syscall_64` 的替換在編譯期就被 `#if` 拿掉了。
- 也缺 fb13b11d。KernelSU 靠 sys_enter tracepoint 改寫 nr，把 syscall 導向 dispatcher，但 kernel 不會重讀改寫後的 nr，所以這些 hook 一個都沒觸發。

影響範圍（2026-10-31 檢查）：

- **KernelSU**：v3.3.0 起，到 `origin/main`（cefb048b）的 `kernel/hook/x86_64/syscall_hook.c` 都是這個寫法。
- **KernelSU-Next**：v3.4.0 起，到 `origin/dev` 都一樣，邏輯與 KernelSU 完全相同，只有排版不同。

## Patch

| 檔案 | 適用版本 |
| :--- | :--- |
| `patches/kernelsu/x86_64-do_syscall_64-fallback.patch` | KernelSU v3.3.1 / main |
| `patches/kernelsu-next/x86_64-do_syscall_64-fallback.patch` | KernelSU-Next v3.4.2 / dev |

（最早驗證的版本是完全拿掉版本 gate；後來改成下方的 `< 6.7` 版本，兩個 patch 目錄現在放的都是 `< 6.7` 版。）

做法：

1. 拿掉 `do_syscall_64` 替換函式外面的 `< 5.16` 編譯期 gate。
2. 在 init 時，`x64_sys_call` patch 失敗（`x64_sys_call_patch_addr == NULL`）就改成 patch `do_syscall_64`。
3. exit 的還原原本就以 `do_syscall_64_patch_addr` 判斷，所以只需要拿掉外面的 gate。

行為變化：

- **有 `x64_sys_call` 的 kernel**（A15 6.6.30、A16 6.6.66、A16.1 6.12.38）：不變，不會走到 fallback。
- **A13 5.15**：有一點不同。上游的寫法是兩個都 patch，套用 patch 後只有在 `x64_sys_call` 不存在時才 patch `do_syscall_64`。A13 5.15.119 本來就沒有 `x64_sys_call`，所以實際行為不變。

修正後 A14 的 log：

```
KernelSU: x64_sys_call=0x0
KernelSU: syscall_enter_from_user_mode: 0x..., syscall_exit_to_user_mode: 0x...
KernelSU: patching do_syscall_64
```

ksud 的 post-fs-data、services、boot-completed 三個階段都以 exit 0 結束，`su` 拿到 uid 0，SELinux 維持 Enforcing。

已驗證的組合（皆為對確切原始碼重編）：

| AVD | KernelSU v3.3.1 | KernelSU-Next v3.4.2 |
| :--- | :---: | :---: |
| A14 6.1.23，加 patch | ✅ `patching do_syscall_64` | ✅ `patching do_syscall_64` |
| A14 6.1.23，不加 patch | ❌ 模組有載入，但 hook 都沒觸發 | 未測，程式碼和 KernelSU 相同 |
| A15 6.6.30，不需要 patch | ✅ `patching x64_sys_call` | ✅ `patching x64_sys_call` |

## 待討論

1. **是否送上游 PR**（tiann/KernelSU，KernelSU-Next 通常會跟著同步）。這只影響「確切原始碼重編」的使用情境：release 附的 A14 LKM 在 AVD 上連 `init_module` 都過不了，要先解決 KMI 不符的問題，才會碰到這個 bug。
2. **gate 的寫法**（已決定 `< 6.7`，見下一節）：AVD 用的 patch 是完全拿掉版本 gate，只靠 runtime 判斷。要注意 `do_syscall_64` 的簽名會變。以下是直接比對 mainline 原始碼（2026-11-01）的結果：

   | mainline | `do_syscall_64` | `x64_sys_call` | fb13b11d |
   | :--- | :--- | :---: | :---: |
   | ≤ 6.6 | `void do_syscall_64(struct pt_regs *, int)` | 無 | 無 |
   | 6.7、6.8 | `bool do_syscall_64(...)` | 無 | 無 |
   | ≥ 6.9 | `bool` | 有 | 有 |

   - 回傳值決定走 SYSRET 還是 IRET。`my_do_syscall_64` 回傳 `void`，所以不能替換 6.7 以上的版本。
   - 對應的 GKI：`android14-6.1` 和 `android15-6.6` 是 `void`，`android16-6.12` 是 `bool`。
   - 先前寫「6.12 才改成 `bool`」是錯的。`< 6.9` 的 gate 會在 6.7、6.8 的 kernel 上（沒有 `x64_sys_call`，一定會走 fallback）編進 `void` 版本，結果出錯。Android 沒有 6.7、6.8 的 GKI，所以 AVD 測不到。
3. **偵測方式**：目前用「`x64_sys_call` 存不存在」判斷，間接推測 kernel 是否缺 fb13b11d。是否該直接偵測 fb13b11d（例如檢查 `do_syscall_64` 是否重讀 nr）？目前看起來沒必要，替換 `do_syscall_64` 在有或沒有 fb13b11d 的 kernel 上都正確。

## 上游 PR 候選版本（< 6.7 gate）

`patches/kernelsu/x86_64-do_syscall_64-fallback.patch` 對 KernelSU main（bec9c134）製作，已送上游 [tiann/KernelSU#3963](https://github.com/tiann/KernelSU/pull/3963)。這個檔案在 v3.3.1 和 main 上內容相同，KernelSU-Next dev 也能套上（只有行號位移）。它取代先前的 `< 6.9` 版本。

改法：

- 三處 `#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 16, 0)` 都改成 `< KERNEL_VERSION(6, 7, 0)`。
- init 時改成只在 `x64_sys_call` patch 失敗時，才替換 `do_syscall_64`。
- 註解說明：缺 `x64_sys_call` 的 kernel 可能也缺 fb13b11d（兩者都在 6.9 進 mainline）。限制在 `< 6.7`，是因為 6.7 起 `do_syscall_64` 回傳 `bool`。
- 6.7、6.8 沒有 `x64_sys_call` 的 kernel 不在支援範圍內，行為和 patch 前一樣。

上游 PR 前的待確認事項：還沒合併的 [tiann/KernelSU#3928](https://github.com/tiann/KernelSU/pull/3928) 也修改了這個檔案，會把 `ksu_patch_text` 換成 `ksu_patch_memory`。如果它先合併，我們要 rebase。

驗證進度：見下方「`< 6.7` 版驗證」。

### `< 6.7` 版驗證（2026-11-01）

編譯：KernelSU main（bec9c134）和 v3.3.1 各加這個 patch，以下 4 個 kernel 都編譯成功，沒有 warning：A13 5.15.119、A14 6.1.23、A15 6.6.30、A16.1 6.12.38。用 `.ko` 裡的字串確認過：5.15、6.1、6.6 有編進 fallback 程式碼，6.12 沒有。

開機測試：用 v3.3.1 加 patch，ksud 和 Manager 是 v3.3.1 release 版。AVD 是 API33/34/35/36.1 的 google_apis_playstore x86_64 原廠 image。

| AVD | hook 路徑 | 第一次開機 | 重開機（ksud 三個階段、`su`） |
| :--- | :--- | :---: | :---: |
| A14 6.1.23 | `x64_sys_call=0x0` → `patching do_syscall_64` | ✅ | ✅ 三個階段都 exit 0，uid=0，Enforcing |
| A13 5.15.119 | `x64_sys_call=0x0` → `patching do_syscall_64` | ✅ | ✅ 三個階段都 exit 0，uid=0，Enforcing |
| A15 6.6.30 | `patching x64_sys_call` | ✅ | ✅ 補測時改成關掉 emulator 再重開；三個階段都 exit 0，uid=0，Enforcing |
| A16.1 6.12.38 | `patching x64_sys_call` | ✅ | ✅ 同上（補測） |

關機卡住的問題和這個 patch 無關：

- A15 和 A16.1 都走 `x64_sys_call`，根本不會用到這次修改的 fallback。
- 另一輪測試用重編的原版 v3.3.1（沒加這個 patch）在 A13 上也遇過兩次一樣的情況。
- release 版 LKM 和重編的 KernelSU-Next 都沒有出現這個問題。
- 現象：init 開始關機後，log 停在對某個 service 送出 SIGKILL 之後，emulator 卡死，`adb emu kill` 也沒有反應。

**已查明（2026-11-01）：問題出在 Android Emulator，不是 KernelSU，也不是我們的編譯設定。**

- 用 API35-GAPPS 加 SDK 原廠 ramdisk（完全沒有 KernelSU），只開一台 emulator、主機閒置，第一次 `adb reboot` 就讓 emulator.exe 在關機途中 segfault。log 停在 init 結束 service 的階段，和前面幾次卡住的情況一樣。
- emulator 在 2026-11-01 00:43 更新到 37.2.13。在這之前的重開機測試全部通過，之後每一次卡住都發生在更新後。主機負載只會影響發生機率。
- 第一次開機時 emulator 直接 segfault 的那兩次（A13、A15），應該也是同一個原因。
- 結論：patch 不用改，PR 描述裡也不要寫「重編版會在重開機時卡住」。之後的開機測試，改成直接關掉 emulator 再重新開機，不再從 guest 裡下 `adb reboot`。

先前的相關討論：upstream 兩個 repo 都沒有找到回報這個問題的 issue 或 PR。

- 引入現有邏輯的 PR 是 [tiann/KernelSU#3562](https://github.com/tiann/KernelSU/pull/3562)，作者 5ec1cff，只測過 AVD 13 5.15 以及有 `x64_sys_call` 的 kernel。
- KernelSU-Next 透過 [#1397](https://github.com/KernelSU-Next/KernelSU-Next/pull/1397) 同步了這段程式碼。

## 重現方式

- 確切原始碼：ci.android.com 上 `kernel_virt_x86_64` build 9964412 的 manifest，對應 `kernel/common` 7e35917775b8。
- 編譯設定：AVD 的 `/proc/config.gz`。
- 編譯環境：`ghcr.io/ylarod/ddk-min:android14-6.1-20260828`，內含 clang r487747c，和原廠 kernel 的 LLVM commit 相同。
- 驗證步驟：用 `ksud boot-patch --ramdisk` 修補 AVD 的 `ramdisk.img`，再用 `emulator -ramdisk` 開機。重開機後檢查 ksud 三個階段是否成功，以及 `su -c id -u` 是否回傳 0。
