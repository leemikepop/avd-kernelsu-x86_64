#!/usr/bin/env python3
"""avd-ksu: root a stock Android Studio AVD (x86_64) with KernelSU / KernelSU-Next LKM.

Only the system image's ramdisk.img is patched; the kernel stays stock. The kernelsu.ko
for each AVD kernel is built in CI against that kernel's exact source and published in
this repository's GitHub Releases, together with host ksud binaries.

  python avd-ksu.py list
  python avd-ksu.py patch  --avd <name> [--variant kernelsu|kernelsu-next] [--version vX.Y.Z]
  python avd-ksu.py restore --avd <name>
  python avd-ksu.py status --avd <name>

Standard library only. Python 3.8+.
"""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = os.environ.get("AVD_KSU_REPO", "leemikepop/avd-kernelsu-x86_64")
VARIANTS = ("kernelsu", "kernelsu-next")
STOCK_SUFFIX = ".stock"          # our backup of the untouched ramdisk
STAMP = ".avd-ksu.json"          # written next to ramdisk.img after patching
CACHE = Path(os.environ.get("AVD_KSU_CACHE", Path.home() / ".cache" / "avd-ksu"))


def die(msg):
    sys.exit(f"error: {msg}")


# ---------------------------------------------------------------- SDK / AVD discovery
def sdk_root():
    for k in ("ANDROID_SDK_ROOT", "ANDROID_HOME"):
        if os.environ.get(k) and Path(os.environ[k]).is_dir():
            return Path(os.environ[k])
    home = Path.home()
    for p in (Path(os.environ.get("LOCALAPPDATA", home)) / "Android" / "Sdk",
              home / "Library" / "Android" / "sdk", home / "Android" / "Sdk"):
        if p.is_dir():
            return p
    die("Android SDK not found; set ANDROID_SDK_ROOT")


def avd_home():
    if os.environ.get("ANDROID_AVD_HOME"):
        return Path(os.environ["ANDROID_AVD_HOME"])
    base = Path(os.environ.get("ANDROID_USER_HOME", Path.home() / ".android"))
    return base / "avd"


def read_ini(p):
    out = {}
    for line in Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def list_avds():
    avds = {}
    home = avd_home()
    for ini in sorted(home.glob("*.ini")):
        meta = read_ini(ini)
        path = Path(meta.get("path", home / (ini.stem + ".avd")))
        if not path.is_dir():
            path = home / (ini.stem + ".avd")
        cfg = path / "config.ini"
        if cfg.exists():
            avds[ini.stem] = read_ini(cfg)
    return avds


def image_dir_of(avd_cfg):
    sysdir = avd_cfg.get("image.sysdir.1", "").replace("\\", "/").strip("/")
    if not sysdir:
        die("AVD config has no image.sysdir.1")
    p = sdk_root() / sysdir
    if not (p / "kernel-ranchu").exists():
        die(f"{p} has no kernel-ranchu")
    return p


def kernel_release(kernel_path):
    d = Path(kernel_path).read_bytes()[:0x10000]
    if d[0x202:0x206] != b"HdrS":
        die(f"{kernel_path} is not an x86 bzImage (arm64 AVDs are not supported)")
    off = struct.unpack_from("<H", d, 0x20E)[0] + 0x200
    return d[off:d.index(b"\0", off)].decode().split(" ")[0]


# ---------------------------------------------------------------- release assets
def http_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "avd-ksu"})
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def version_key(ver):
    """'v3.4.2' -> (3, 4, 2); non-numeric parts sort first."""
    return tuple(int(p) if p.isdigit() else -1 for p in re.split(r"[.\-]", ver.lstrip("v")))


def find_release(variant, version):
    """The release for an exact version, or the highest non-prerelease version."""
    prefix = f"{variant}-"
    candidates = []
    for page in range(1, 11):
        rels = http_json(f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={page}")
        for rel in rels:
            tag = rel["tag_name"]
            if rel.get("draft") or not tag.startswith(prefix):
                continue
            ver = tag[len(prefix):]
            if not ver.startswith("v"):          # "kernelsu-" must not match "kernelsu-next-..."
                continue
            if version is not None:
                if ver == version:
                    return rel
            elif not rel.get("prerelease"):
                candidates.append((version_key(ver), rel))
        if len(rels) < 100:
            break
    if candidates:
        return max(candidates, key=lambda c: c[0])[1]
    die(f"no release for {variant} {version or '(latest)'} in {REPO}")


class Assets:
    """Release assets, from GitHub or from a local directory (--assets-dir)."""

    def __init__(self, variant, version, local_dir=None):
        self.local = Path(local_dir) if local_dir else None
        if self.local:
            self.files = {p.name: p for p in self.local.iterdir()}
            self.version = version or self._guess_version(variant)
        else:
            rel = find_release(variant, version)
            self.version = rel["tag_name"][len(variant) + 1:]
            self.files = {a["name"]: a["browser_download_url"] for a in rel["assets"]}
            print(f"release: {rel['tag_name']}  ({rel['html_url']})")
        self.variant = variant
        self.sums = {}
        if "SHA256SUMS" in self.files:
            # Always fetched fresh: a release re-published with --clobber changes it.
            for line in self.get("SHA256SUMS", fresh=True).read_text().splitlines():
                h, n = line.split(maxsplit=1)
                self.sums[n.lstrip("*")] = h

    def _guess_version(self, variant):
        for n in self.files:
            if n.startswith(f"ksud-{variant}-v"):
                return n[len(f"ksud-{variant}-"):].split("-")[0]
        die("cannot determine version from --assets-dir; pass --version")

    def _download(self, name, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        print(f"download {name}")
        tmp = path.with_suffix(path.suffix + ".part")
        with urllib.request.urlopen(self.files[name], timeout=300) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.replace(path)

    def _hash_ok(self, name, path):
        return name not in self.sums or hashlib.sha256(path.read_bytes()).hexdigest() == self.sums[name]

    def get(self, name, fresh=False):
        if name not in self.files:
            die(f"asset {name} not in release (available: {', '.join(sorted(self.files))})")
        if self.local:
            path = self.files[name]
            if not self._hash_ok(name, path):
                die(f"sha256 mismatch for {name}")
            return path
        path = CACHE / self.variant / self.version / name
        downloaded = fresh or not path.exists()
        if downloaded:
            self._download(name, path)
        if not self._hash_ok(name, path) and not downloaded:
            # Cached copy from an earlier publish of this release: fetch it again once.
            self._download(name, path)
        if not self._hash_ok(name, path):
            path.unlink()
            die(f"sha256 mismatch for {name}")
        return path


def manager_name(variant):
    return "KernelSU" if variant == "kernelsu" else "KernelSU Next"


def host_triple():
    m = platform.machine().lower()
    arch = "aarch64" if m in ("arm64", "aarch64") else "x86_64"
    if sys.platform == "win32":
        return "x86_64-pc-windows-gnu", ".exe"
    if sys.platform == "darwin":
        return f"{arch}-apple-darwin", ""
    return f"{arch}-unknown-linux-musl", ""


def match_target(targets, release):
    for t in targets["targets"]:
        if release == t["kernel_release"] or release.endswith("-ab" + t["build_id"]):
            return t
    known = "\n  ".join(f"{t['id']}: {t['kernel_release']}" for t in targets["targets"])
    die(f"no prebuilt LKM for kernel {release}.\nSupported kernels:\n  {known}\n"
        "Update the system image in SDK Manager, or open an issue with this kernel string.")


# ---------------------------------------------------------------- commands
def resolve_image(a):
    if a.image_dir:
        return Path(a.image_dir)
    if not a.avd:
        die("pass --avd <name> (see `list`) or --image-dir")
    avds = list_avds()
    if a.avd not in avds:
        die(f"AVD {a.avd!r} not found in {avd_home()}; known: {', '.join(avds)}")
    return image_dir_of(avds[a.avd])


def ramdisk_state(img):
    rd = img / "ramdisk.img"
    stamp = img / STAMP
    if stamp.exists():
        s = json.loads(stamp.read_text())
        return f"patched with {s['variant']} {s['version']} ({s['target']})"
    if (img / ("ramdisk.img" + STOCK_SUFFIX)).exists():
        return "has avd-ksu backup but no stamp (unknown state)"
    if (img / "ramdisk.img.backup").exists():
        return "probably patched by rootAVD/Magisk (ramdisk.img.backup present)"
    return "stock" if rd.exists() else "missing ramdisk.img"


def cmd_list(a):
    avds = list_avds()
    if not avds:
        print(f"no AVDs in {avd_home()}")
    for name, cfg in avds.items():
        try:
            img = image_dir_of(cfg)
            rel = kernel_release(img / "kernel-ranchu")
            print(f"{name:24} {cfg.get('abi.type', '?'):8} {rel}\n{'':24} {img}\n{'':24} ramdisk: {ramdisk_state(img)}")
        except SystemExit as e:
            print(f"{name:24} ({e})")


def cmd_status(a):
    img = resolve_image(a)
    print(f"image:   {img}\nkernel:  {kernel_release(img / 'kernel-ranchu')}\nramdisk: {ramdisk_state(img)}")


def stock_source(img):
    """Pick the untouched ramdisk to patch from."""
    ours = img / ("ramdisk.img" + STOCK_SUFFIX)
    if ours.exists():
        return ours
    if (img / "ramdisk.img.backup").exists():
        print("note: ramdisk.img.backup found (rootAVD/Magisk); using it as the stock ramdisk")
        return img / "ramdisk.img.backup"
    return img / "ramdisk.img"


def cmd_patch(a):
    img = resolve_image(a)
    rel = kernel_release(img / "kernel-ranchu")
    assets = Assets(a.variant, a.version, a.assets_dir)
    targets = json.loads(assets.get("avd-targets.json").read_text(encoding="utf-8"))
    t = match_target(targets, rel)
    print(f"kernel {rel} -> target {t['id']} (KMI {t['kmi']})")
    cmdline = img / "kernel_cmdline.txt"
    if a.variant == "kernelsu-next" and cmdline.exists() and "page_shift=14" in cmdline.read_text():
        print("warning: this is a 16 KB page-size image. KernelSU-Next v3.4.2's manager ships a ksud that is "
              "not 16 KB aligned, so root will not activate (KernelSU works). Continuing anyway.")

    v = assets.version
    ko = Path(a.ko) if a.ko else assets.get(f"{t['id']}_{a.variant}-{v}_kernelsu.ko")
    triple, ext = host_triple()
    ksud = Path(a.ksud) if a.ksud else assets.get(f"ksud-{a.variant}-{v}-{triple}{ext}")
    ksuinit = assets.get(f"ksuinit-x86_64-{a.variant}-{v}")
    if os.name != "nt":
        ksud.chmod(ksud.stat().st_mode | stat.S_IEXEC)

    src = stock_source(img)
    with tempfile.TemporaryDirectory() as tmp:
        work_in = Path(tmp) / "ramdisk.img"
        shutil.copy2(src, work_in)
        cmd = [str(ksud), "boot-patch", "-b", str(work_in), "--ramdisk", "--arch", "x86_64",
               "-m", str(ko), "-i", str(ksuinit), "--kmi", t["kmi"], "-o", tmp, "--out-name", "patched.img"]
        if a.allow_shell:
            cmd.append("--allow-shell")
        print("$ " + " ".join(cmd))
        r = subprocess.run(cmd)
        out = Path(tmp) / "patched.img"
        if r.returncode != 0 or not out.exists():
            die("ksud boot-patch failed (a Magisk-patched ramdisk needs its original; see README)")
        if a.out:
            shutil.copy2(out, a.out)
            print(f"\nwrote {a.out}\nNext steps:\n"
                  f"  1. emulator -avd <name> -ramdisk \"{a.out}\" -no-snapshot-load\n"
                  f"  2. Install and open the {manager_name(a.variant)} manager ({assets.version}).\n"
                  "  3. Close the emulator and start it again with the same command "
                  "(avoid in-guest reboot: Emulator 37.2.13 can crash on it).")
            return
        backup = img / ("ramdisk.img" + STOCK_SUFFIX)
        if not backup.exists():
            shutil.copy2(src, backup)
            print(f"backup: {backup}")
        shutil.copy2(out, img / "ramdisk.img")
    (img / STAMP).write_text(json.dumps({"variant": a.variant, "version": v, "target": t["id"],
                                         "kernel": rel}, indent=2))
    print(f"\npatched {img / 'ramdisk.img'}\n"
          "Every AVD using this system image is affected. Next steps:\n"
          "  1. Cold boot the AVD (Device Manager > Cold Boot Now, or emulator -no-snapshot-load).\n"
          f"  2. Install and open the {manager_name(a.variant)} manager ({v}), then close the emulator\n"
          "     and cold-boot it again (avoid in-guest reboot: Emulator 37.2.13 can crash on it).\n"
          "  3. Undo any time with: python avd-ksu.py restore --avd <name>")


def cmd_restore(a):
    img = resolve_image(a)
    backup = img / ("ramdisk.img" + STOCK_SUFFIX)
    if not backup.exists():
        die(f"no {backup.name} in {img}; nothing to restore")
    shutil.copy2(backup, img / "ramdisk.img")
    backup.unlink()
    (img / STAMP).unlink(missing_ok=True)
    print(f"restored stock ramdisk in {img}; cold boot the AVD")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list AVDs, their kernels and ramdisk state")
    for name in ("patch", "restore", "status"):
        p = sub.add_parser(name)
        p.add_argument("--avd", help="AVD name (see `list`)")
        p.add_argument("--image-dir", help="system image dir instead of --avd")
        if name == "patch":
            p.add_argument("--variant", choices=VARIANTS, default="kernelsu")
            p.add_argument("--version", help="upstream version tag, e.g. v3.3.1 (default: latest)")
            p.add_argument("--out", help="write the patched ramdisk here instead of replacing the SDK one")
            p.add_argument("--allow-shell", action="store_true", help="pass --allow-shell to ksud")
            p.add_argument("--assets-dir", help=argparse.SUPPRESS)  # local release assets (testing)
            p.add_argument("--ko", help=argparse.SUPPRESS)
            p.add_argument("--ksud", help=argparse.SUPPRESS)
    a = ap.parse_args()
    {"list": cmd_list, "patch": cmd_patch, "restore": cmd_restore, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    main()
