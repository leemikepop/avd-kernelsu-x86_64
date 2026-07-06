# KernelSU AVD (x86_64) 核心編譯與整合指南

本指南說明如何在乾淨的環境下，同步 Android Common Kernel 原始碼，整合 KernelSU 驅動程式，並編譯成適用於 AVD 模擬器的自定義核心。

---

## AVD versions / Common Kernels

### Android 13 API 33

* **kernel branch**: common-android13-5.15
* **AVD**: A13-GAPPS, A13-GAPIS, A13-AOSP
* **build id**: 10871489

### Android 14 API 34

* **kernel branch**: common-android14-6.1
* **AVD**: A14-GAPPS, A14-GAPIS, A14-AOSP
* **build id**: 9964412

### Android 15 API 35

* **kernel branch**: common-android15-6.6
* **AVD**: A15-GAPPS, A15-GAPIS, A15-AOSP (No 16KB Page)
* **build id**: 11987101

### Android 16 API 36.0

* **kernel branch**: common-android15-6.6-2025-02
* **AVD**: A16-GAPPS, A16-GAPIS, A16-AOSP (No 16KB Page)
* **build id**: 13070261
* **note**: Android 16 API 36.0 AVD still uses android15-6.6 GKI.

### Android 16 API 36.1

* **kernel branch**: common-android16-6.12
* **AVD**: A16-GAPPS, A16-GAPIS, A16-AOSP (No 16KB Page)
* **build id**: 13996879
* **note**: Android 16 API 36.1 moves to 6.12 GKI.

---

## 一、 核心源碼同步 (CI 精確同步)

為避免編譯出的核心與 AVD 現有驅動模組版本不相容（導致 Wi-Fi、音效失效），建議採用與 AVD 目前版本完全一致的 CI 構建同步：

1. **取得 AVD 的 Build ID**：
   在 AVD 啟動後，於終端機執行：

   ```bash
   adb shell uname -r
   # 輸出範例：5.15.119-android13-8-00034-gd34029c8258b-ab10871489
   # 其中 10871489 即為該 AVD 核心編譯時的 Build ID
   ```

2. **初始化與同步 Repo**：
   在 Linux 編譯伺服器上執行以下指令，精確還原該編譯點的原始碼：

   ```bash
   # 初始化分支
   # common-android13-5.15
   repo init -u https://android.googlesource.com/kernel/manifest -b common-android13-5.15

   # common-android14-6.1
   repo init -u https://android.googlesource.com/kernel/manifest -b common-android14-6.1

   # common-android15-6.6
   repo init -u https://android.googlesource.com/kernel/manifest -b common-android15-6.6

   # Android 16 API 36.0 AVD still uses common-android15-6.6-2025-02 GKI.
   repo init -u https://android.googlesource.com/kernel/manifest -b common-android15-6.6-2025-02

   # Android 16 API 36.1
   repo init -u https://android.googlesource.com/kernel/manifest -b common-android16-6.12

   # 下載對應 Build ID 的 manifest 檔並指定
   # common-android13-5.15
   curl -Lo .repo/manifests/manifest_10871489.xml https://ci.android.com/builds/submitted/10871489/kernel_virt_x86_64/latest/raw/manifest_10871489.xml
   repo init -m manifest_10871489.xml

   # common-android14-6.1
   curl -Lo .repo/manifests/manifest_9964412.xml https://ci.android.com/builds/submitted/9964412/kernel_virt_x86_64/latest/raw/manifest_9964412.xml
   repo init -m manifest_9964412.xml

   # common-android15-6.6
   curl -Lo .repo/manifests/manifest_11987101.xml https://ci.android.com/builds/submitted/11987101/kernel_virt_x86_64/latest/raw/manifest_11987101.xml
   repo init -m manifest_11987101.xml

   # Android 16 API 36.0 / common-android15-6.6 GKI
   curl -Lo .repo/manifests/manifest_13070261.xml https://ci.android.com/builds/submitted/13070261/kernel_virt_x86_64/latest/raw/manifest_13070261.xml
   repo init -m manifest_13070261.xml

   # Android 16 API 36.1 / common-android16-6.12 GKI
   curl -Lo .repo/manifests/manifest_13996879.xml https://ci.android.com/builds/submitted/13996879/kernel_virt_x86_64/latest/raw/manifest_13996879.xml
   repo init -m manifest_13996879.xml

   # 同步源碼
   repo sync -c -j$(nproc)
   # repo sync -c -j1 --fail-fast
   ```

---

## 二、 整合 KernelSU 驅動 (繞過 Bazel 沙盒限制)

由於 Bazel/Kleaf 採用隔離的沙盒進行編譯，**不能**直接使用 `setup.sh` 預設產生的跨目錄軟連結。必須在執行 `setup.sh` 後，將 KernelSU / KernelSU-Next 的原始碼與 UAPI 檔案以**實體目錄**形式複製到 `common/` 中。

目前建議 AVD x86_64 測試先使用 **KernelSU v3.1.0（含）以下**。從 KernelSU v3.2.0 開始，x86_64 支援改走 PR #3328 的新路徑，會牽涉 `X86_FEATURE_INDIRECT_SAFE`、syscall hardening patch，以及 AVD 開機期間 ksud / sepolicy 載入時機；實測上所有 AVD target 都可能出現 manager 顯示 `not installed` 的問題。v3.1.0 仍是比較穩定的基準版本，等 v3.1.0 確認可用後，再另外測 v3.2.0+。

以下流程同時支援官方 KernelSU 和 KernelSU-Next。請先選擇 variant 與版本：

```bash
# 官方 KernelSU 範例：
KSU_VARIANT=KernelSU
KSU_REF=v3.1.0

# KernelSU-Next 範例：
KSU_VARIANT=KernelSU-Next
KSU_REF=v3.1.0
```

1. **複製/下載 KernelSU 原始碼**：
   在核心源碼根目錄下執行：

   ```bash
   case "$KSU_VARIANT" in
     KernelSU)
       KSU_REPO_URL="https://github.com/tiann/KernelSU.git"
       KSU_REPO_DIR="KernelSU"
       ;;
     KernelSU-Next)
       KSU_REPO_URL="https://github.com/KernelSU-Next/KernelSU-Next.git"
       KSU_REPO_DIR="KernelSU-Next"
       ;;
     *)
       echo "不支援的 KSU_VARIANT: $KSU_VARIANT"
       exit 1
       ;;
   esac

   git clone "$KSU_REPO_URL" "$KSU_REPO_DIR"
   ```

2. **執行 setup.sh 初始化設定**：
   此步驟會自動修改 `common/drivers/Kconfig` 與 `common/drivers/Makefile` 引入 KernelSU：

   ```bash
   "./$KSU_REPO_DIR/kernel/setup.sh" "$KSU_REF"
   ```

3. **將軟連結替換為實體目錄**：
   執行以下指令，刪除軟連結並將原始碼實體複製到 `common/drivers/kernelsu`，確保 Bazel 能夠在編譯時將檔案打包進沙盒中：

   ```bash
   # 1. 刪除由 setup.sh 建立的 drivers/kernelsu 軟連結
   rm -rf common/drivers/kernelsu

   # 2. 將 KernelSU/kernel 或 KernelSU-Next/kernel 目錄實體複製到 common/drivers/kernelsu
   cp -r "$KSU_REPO_DIR/kernel" common/drivers/kernelsu

   # 3. 部分新版 KernelSU / KernelSU-Next 會把 UAPI 放在 repo 根目錄
   if [ -d "$KSU_REPO_DIR/uapi" ] && [ -L "common/drivers/kernelsu/include/uapi" ]; then
     rm -f common/drivers/kernelsu/include/uapi
     cp -r "$KSU_REPO_DIR/uapi" common/drivers/kernelsu/include/uapi
   fi
   ```

4. **手動修改KSU_VERSION**:
   * 計算方法：

   ```bash
   cd "$KSU_REPO_DIR"
   KSU_GIT_VERSION=$(git rev-list --count HEAD)
   KSU_VERSION_TAG=$(git describe --tags --abbrev=0 2>/dev/null || printf '%s' "$KSU_REF")
   BASE_OFFSET=10000
   if grep -q "30000" kernel/Kbuild 2>/dev/null || grep -q "30000" kernel/Makefile 2>/dev/null; then
      BASE_OFFSET=30000
   elif grep -q "10000" kernel/Kbuild 2>/dev/null || grep -q "10000" kernel/Makefile 2>/dev/null; then
      BASE_OFFSET=10000
   fi
   KSU_VERSION=$((BASE_OFFSET + KSU_GIT_VERSION))
   echo "Calculated KSU_VERSION: $KSU_VERSION"
   echo "Resolved KSU_VERSION_TAG: $KSU_VERSION_TAG"
   cd ..
   ```

* 修改 `common/drivers/kernelsu/Kbuild` (新版 KernelSU / KernelSU-Next) 或 `common/drivers/kernelsu/Makefile` (舊版 KernelSU)：

   官方 KernelSU 常見 fallback 是 `16`；KernelSU-Next 在被實體複製進 `common/drivers/kernelsu` 後，無法再透過獨立 git repo 自動計算版本，會 fallback 成 `1` 與 `v0.0.1`，因此兩種情況都要處理。

   ```bash
   KSU_VERSION_TAG_SED=$(printf '%s' "$KSU_VERSION_TAG" | sed -e 's/[\/&]/\\&/g')

   for f in common/drivers/kernelsu/Makefile common/drivers/kernelsu/Kbuild; do
     [ -f "$f" ] || continue
     sed -i "s/ccflags-y += -DKSU_VERSION=16/ccflags-y += -DKSU_VERSION=$KSU_VERSION/g" "$f"
     sed -i "s/KSU_VERSION := 16/KSU_VERSION := $KSU_VERSION/g" "$f"
     sed -i "s/KSU_VERSION_FALLBACK := .*/KSU_VERSION_FALLBACK := $KSU_VERSION/g" "$f"
     sed -i "s/KSU_VERSION_TAG_FALLBACK := .*/KSU_VERSION_TAG_FALLBACK := $KSU_VERSION_TAG_SED/g" "$f"
   done
   ```

   ```makefile
   # 官方 KernelSU: 將原來的 ccflags-y += -DKSU_VERSION=16 替換為計算出的真實版本號：
   ccflags-y += -DKSU_VERSION=<calculated KSU_VERSION>

   # KernelSU-Next: 將 fallback 改成計算出的真實版本號與 tag：
   KSU_VERSION_FALLBACK := <calculated KSU_VERSION>
   KSU_VERSION_TAG_FALLBACK := v3.1.0
   ```

---

## **(KernelSU v3.2.0+ ONLY)** 三、 套用 x86_64 Syscall Hardening 與 KernelSU 相容修正

這一章只針對 **KernelSU v3.2.0（含）之後**。預設建議使用 **KernelSU v3.1.0（含）以下**，可以跳過本章；只有在你明確要測試 v3.2.0+ 的新版 x86_64 syscall dispatcher 時，才需要看這裡。

從 v3.2.0 開始，KernelSU 的 x86_64 syscall hook 會檢查 kernel 是否提供 `X86_FEATURE_INDIRECT_SAFE`。這是為了搭配新版 x86_64 syscall hardening，但在 AVD 上還會牽涉 early init、ksud 執行時機與 sepolicy domain 是否已經可用；目前實測所有 AVD target 都可能讓 manager 顯示 `not installed`。所以這章的內容是「進階相容修正」，不是建議預設路徑。

處理方式要看 GKI kernel 的 syscall 實作，不只看 Android 大版本：

| AVD / GKI | syscall 實作 | KernelSU v3.2.0+ 實驗作法 |
| --- | --- | --- |
| Android 13 API 33 / `common-android13-5.15` | 還在使用 syscall table | 註解或移除 KernelSU 的 `X86_FEATURE_INDIRECT_SAFE` 檢查 |
| Android 14 API 34 / `common-android14-6.1` | 還在使用 syscall table | 註解或移除 KernelSU 的 `X86_FEATURE_INDIRECT_SAFE` 檢查 |
| Android 15 API 35 / `common-android15-6.6` | 已改成 switch-case hardening | 保留 KernelSU 檢查，套用 kernel patch |
| Android 16 API 36.0 / `common-android15-6.6` | 已改成 switch-case hardening | 保留 KernelSU 檢查，套用 kernel patch |
| Android 16 API 36.1 / `common-android16-6.12` | 已改成 switch-case hardening | 保留 KernelSU 檢查，套用 kernel patch |

Android 16 不一定等於 kernel 6.12；例如 API 36.0 AVD 仍使用 android15-6.6 GKI。手動操作時以實際 kernel source 或 `common-*` 分支為準。

### 1. 修正 x86_64 syscall hardening 檢查

### **newer GKI(A15+)**

<details>

適用 `common-android15-6.6`、`common-android16-6.12`，以及之後同樣採用 switch-case syscall hardening 的 x86_64 GKI。這條路徑只給 **KernelSU v3.2.0+** 使用；如果你使用建議的 v3.1.0（含）以下，請不要套這些 patch。

v3.2.0+ 測試時要**保留 KernelSU 的 `X86_FEATURE_INDIRECT_SAFE` 檢查**，並依 kernel 版本套用對應 patch，讓 kernel 支援 `X86_FEATURE_INDIRECT_SAFE`。Android Emulator 目前沒有穩定的頂層 `-append` kernel cmdline 參數；直接加 `-append "syscall_hardening=off"` 會出現 unknown option。因此 AVD 測試建議在編譯時把 `syscall_hardening` 預設改成 `off`。

在 kernel source root 或 `common/` 目錄內執行都可以：

```bash
if [ -f common/Makefile ]; then
  COMMON_DIR=common
elif [ -f Makefile ] && [ -d arch ]; then
  COMMON_DIR=.
else
  echo "請在 kernel source root 或 common/ 目錄內執行"
  exit 1
fi

KERNEL_VERSION="$(awk '/^VERSION =/{v=$3} /^PATCHLEVEL =/{p=$3} END{print v "." p}' "$COMMON_DIR/Makefile")"
echo "Detected kernel version: $KERNEL_VERSION"
cd "$COMMON_DIR"

PATCH_MODE=standard
case "$KERNEL_VERSION" in
  6.6)
    PATCH_URLS=(
      "https://github.com/android-generic/kernel_common/commit/fe9a9b4c320577c30e1f22d04039e414c6a3cdec.patch"
      "https://github.com/android-generic/kernel_common/commit/df772e99e392f24b395ceaf7b26974e3e4828ee9.patch"
    )
    ;;
  6.12)
    PATCH_MODE=android16_6_12
    PATCH_URLS=(
      "https://github.com/android-generic/kernel-zenith/commit/dd2c602268fdc81f4d3b662f6a15142ac0ec7bcd.patch"
      "https://github.com/android-generic/kernel-zenith/commit/7d99237ae5da61c19447138da3282ae37d43857b.patch"
    )
    ;;
  6.18)
    PATCH_URLS=(
      "https://github.com/android-generic/kernel-zenith/commit/40b1c323d1ad29c86e041d665c7f089b9a3ccfb5.patch"
      "https://github.com/android-generic/kernel-zenith/commit/f5813e10b7630e1ccd86fc2c4cf30eef60b64a82.patch"
    )
    ;;
  5.15|6.1)
    PATCH_URLS=()
    echo "Kernel $KERNEL_VERSION 通常仍使用 syscall table；KernelSU v3.2.0+ 請改走上一節註解 KernelSU 檢查。"
    ;;
  *)
    echo "尚未整理 kernel $KERNEL_VERSION 的 KernelSU x86_64 patch。"
    exit 1
    ;;
esac

if [ "${#PATCH_URLS[@]}" -gt 0 ]; then
  if grep -q 'X86_FEATURE_INDIRECT_SAFE' arch/x86/include/asm/cpufeatures.h \
    && grep -q 'syscall_hardening' arch/x86/kernel/cpu/common.c \
    && grep -q 'sys_call_table\[unr\]' arch/x86/entry/common.c; then
    echo "KernelSU x86_64 syscall hardening patches 已存在，略過套用。"
  elif [ "$PATCH_MODE" = "android16_6_12" ]; then
    echo "Applying Android 16 6.12-compatible KernelSU x86_64 syscall hardening patches..."

    if ! grep -q 'X86_FEATURE_INDIRECT_SAFE' arch/x86/include/asm/cpufeatures.h; then
      sed -i '/X86_FEATURE_INDIRECT_THUNK_ITS/a #define X86_FEATURE_INDIRECT_SAFE\t(21*32 + 7) /* "" Indirect branches can be used for syscalls */' arch/x86/include/asm/cpufeatures.h
    fi
    if ! grep -q 'X86_FEATURE_INDIRECT_SAFE' arch/x86/include/asm/cpufeatures.h; then
      echo "Failed to add X86_FEATURE_INDIRECT_SAFE to cpufeatures.h"
      exit 1
    fi

    if ! grep -q 'cpu_show_syscall_hardening' include/linux/cpu.h; then
      sed -i '/extern ssize_t cpu_show_tsa/i #if defined(CONFIG_X86) || defined(CONFIG_X86_64)\nextern ssize_t cpu_show_syscall_hardening(struct device *dev,\n\t\t\t\t\t       struct device_attribute *attr, char *buf);\n#endif\n' include/linux/cpu.h
    fi
    if ! grep -q 'cpu_show_syscall_hardening' include/linux/cpu.h; then
      echo "Failed to add cpu_show_syscall_hardening declaration to include/linux/cpu.h"
      exit 1
    fi

    curl -L "${PATCH_URLS[0]}" -o /tmp/ksu-x86-syscall-hardening-1.patch
    git apply --check --whitespace=fix \
      --exclude=arch/x86/include/asm/cpufeatures.h \
      --exclude=arch/x86/kernel/cpu/bugs.c \
      /tmp/ksu-x86-syscall-hardening-1.patch
    git apply --whitespace=fix \
      --exclude=arch/x86/include/asm/cpufeatures.h \
      --exclude=arch/x86/kernel/cpu/bugs.c \
      /tmp/ksu-x86-syscall-hardening-1.patch

    curl -L "${PATCH_URLS[1]}" -o /tmp/ksu-x86-syscall-hardening-2.patch
    git apply --check --whitespace=fix \
      --exclude=arch/x86/kernel/cpu/bugs.c \
      --exclude=include/linux/cpu.h \
      /tmp/ksu-x86-syscall-hardening-2.patch
    git apply --whitespace=fix \
      --exclude=arch/x86/kernel/cpu/bugs.c \
      --exclude=include/linux/cpu.h \
      /tmp/ksu-x86-syscall-hardening-2.patch
  else
    for patch_url in "${PATCH_URLS[@]}"; do
      echo "Applying $patch_url"
      curl -L "$patch_url" -o /tmp/ksu-x86-syscall-hardening.patch
      git apply --check --whitespace=fix /tmp/ksu-x86-syscall-hardening.patch
      git apply --whitespace=fix /tmp/ksu-x86-syscall-hardening.patch
    done
  fi
fi

if grep -q 'syscall_hardening __ro_after_init = SYSCALL_HARDENING_ON;' arch/x86/kernel/cpu/common.c; then
  sed -i 's/syscall_hardening __ro_after_init = SYSCALL_HARDENING_ON;/syscall_hardening __ro_after_init = SYSCALL_HARDENING_OFF;/' arch/x86/kernel/cpu/common.c
fi
if ! grep -q 'syscall_hardening __ro_after_init = SYSCALL_HARDENING_OFF;' arch/x86/kernel/cpu/common.c; then
  echo "Expected syscall_hardening to default to off for Android Emulator."
  exit 1
fi

git diff --check -- arch/x86 include/linux/cpu.h drivers/base/cpu.c
```

這組 patch 會加入 `X86_FEATURE_INDIRECT_SAFE`，並把 `syscall_hardening` 預設改成 `off`。因此啟動 A15+ AVD 時不需要加 `-append "syscall_hardening=off"`。

</details>

### **older GKI(A14-)**

<details>

適用 `common-android13-5.15` 和 `common-android14-6.1`。這類 kernel 沒有新版 switch-case syscall hardening，不需要套 `X86_FEATURE_INDIRECT_SAFE` kernel patch。使用建議的 v3.1.0（含）以下時也不需要修改這裡；只有使用 KernelSU v3.2.0+ 時，才在整合 KernelSU 之後把 KernelSU 端的檢查註解或移除。

編輯 `common/drivers/kernelsu/core/init.c`（部分版本在 `common/drivers/kernelsu/ksu.c`）。

* **移除編譯期檢查**：
  將以下區塊註解或刪除：

  ```c
  #ifndef X86_FEATURE_INDIRECT_SAFE
  // #error "FATAL: Your kernel is missing the indirect syscall bypass patches!"
  #endif
  ```

* **移除執行期檢查**：
  將 `kernelsu_init` 函式中的下列檢查註解或刪除，避免舊版 GKI 因不支援、也不需要 `X86_FEATURE_INDIRECT_SAFE` 而載入失敗傳回 `-ENOSYS`：

  ```c
  #if defined(__x86_64__)
      /*
      if (!boot_cpu_has(X86_FEATURE_INDIRECT_SAFE)) {
          pr_alert("*************************************************************");
          pr_alert("**     NOTICE NOTICE NOTICE NOTICE NOTICE NOTICE NOTICE    **");
          ...
          return -ENOSYS;
      }
      */
  #endif
  ```

不要在 Android 15 以上這類 switch-case hardened kernel 用這個方式略過檢查；那會掩蓋真正需要 kernel patch 的問題。

</details>

### 2. 編譯 include 相容性修正 (只在遇到對應錯誤時使用)

這一節不是每次都要跑。先編譯一次，遇到對應錯誤時再套對應的小修正；不要把所有修正都當成固定步驟。

#### 部分新版 KernelSU-Next `sulog.h` 缺少 `<linux/init.h>`

如果遇到下面錯誤：

```text
feature/sulog.h:7:6: error: variable has incomplete type 'void'
void __init ksu_sulog_init(void);
     ^
feature/sulog.h:8:6: error: variable has incomplete type 'void'
void __exit ksu_sulog_exit(void);
     ^
```

補上 `__init` / `__exit` 所需的 header：

```bash
if [ -f common/drivers/kernelsu/feature/sulog.h ]; then
  if grep -Eq '__init|__exit' common/drivers/kernelsu/feature/sulog.h \
    && ! grep -qxF '#include <linux/init.h>' common/drivers/kernelsu/feature/sulog.h; then
    sed -i '/#include <linux\/types.h>/a #include <linux/init.h>' common/drivers/kernelsu/feature/sulog.h
  fi
fi
```

#### x86_64 syscall hook / patch memory include 錯誤

```bash
if [ -f common/drivers/kernelsu/syscall_hook_manager.c ]; then
  if ! grep -qxF '#include <linux/sched/task_stack.h>' common/drivers/kernelsu/syscall_hook_manager.c; then
    sed -i '/#include <linux\/tracepoint.h>/a #include <linux/sched/task_stack.h>' common/drivers/kernelsu/syscall_hook_manager.c
  fi

  if ! grep -qxF '#include <asm/compat.h>' common/drivers/kernelsu/syscall_hook_manager.c; then
    sed -i '/#include <asm\/syscall.h>/a #if defined(__x86_64__)\n#include <asm/compat.h>\n#endif' common/drivers/kernelsu/syscall_hook_manager.c
  fi
fi

if [ -f common/drivers/kernelsu/hook/patch_memory.h ]; then
  if ! grep -qxF '#include <linux/bug.h>' common/drivers/kernelsu/hook/patch_memory.h; then
    sed -i '/#include <linux\/types.h>/a #include <linux/bug.h>' common/drivers/kernelsu/hook/patch_memory.h
  fi

  sed -i 's|"asm/patching.h"|"asm/text-patching.h"|g' common/drivers/kernelsu/hook/patch_memory.h
fi

git -C common diff --check
```

這段修正只對應下面幾類編譯錯誤：

```text
call to undeclared function 'in_compat_syscall'
call to undeclared function 'task_stack_page'
fatal error: 'asm/patching.h' file not found
BUG_ON implicit declaration
```

---

## 四、 編譯與部署

1. **執行編譯指令**：
   在核心源碼根目錄下執行：

  ```bash
  detect_dist_arg() {
    local target="$1"
    local help_output

    help_output=$(tools/bazel run --config=fast --lto=none "$target" -- -h 2>&1 || true)
    printf '%s\n' "$help_output" >&2

    if grep -q -- '--destdir' <<< "$help_output"; then
      echo "--destdir"
    elif grep -q -- '--dist_dir' <<< "$help_output"; then
      echo "--dist_dir"
    else
      echo "無法判斷 $target 使用 --destdir 或 --dist_dir" >&2
      return 1
    fi
  }

  DIST_ARG="$(detect_dist_arg //common:kernel_x86_64_dist)"
  VIRT_DIST_ARG="$(detect_dist_arg //common-modules/virtual-device:virtual_device_x86_64_dist)"

  # 編譯核心本體 (bzImage)
  tools/bazel run --config=fast --lto=none //common:kernel_x86_64_dist -- "${DIST_ARG}=out/dist-13070261-A16-API36.0-6.6-x86_64-v310/"

  # 編譯 AVD 虛擬裝置驅動模組 (*.ko)，這是讓 AVD 擁有網路與音效的關鍵
  tools/bazel run --config=fast --lto=none //common-modules/virtual-device:virtual_device_x86_64_dist -- "${VIRT_DIST_ARG}=out/dist-13070261-A16-API36.0-6.6-x86_64-v310/"
  ```

1. **替換 AVD 內核**：

  ```powershell
  emulator -avd <AVD_NAME> -kernel <path\to\bzImage> -no-snapshot-load -show-kernel 2>&1 | Tee-Object -FilePath "${avd_name}.log"
  ```

  不要直接加 `-append "syscall_hardening=off"`；目前 Android Emulator wrapper 會回報 unknown option。若測試 KernelSU v3.2.0+ 且 A15+ GKI，請在編譯階段照第三章把 `syscall_hardening` 預設改成 `off`。

---

## 五、 常見指令與工具

* 切換KernelSU版本需先清除快取：

     ```bash
     # 完整清除所有 bazel 產物與快取
     tools/bazel clean --expunge

     # 或者只清除特定的 build 產物目錄
     rm -rf out/dist

     # 恢復所有 repo 的修改
     repo forall -c "git checkout ."

     # 徹底清除所有 repo 的本地變更
     repo forall -c "git clean -fdx"
     ```

* emulator 相關指令

   ```powershell
   # 列出所有 avd
   emulator -list-avds

   # 啟動 avd
   emulator -avd <avd_name>

   # 啟動 avd 並使用指定的核心
   emulator -avd <avd_name> -kernel <kernel_path> [-ramdisk <ramdisk_path>] -no-snapshot-load -show-kernel 2>&1 | Tee-Object -FilePath "${avd_name}.log"
   ```
