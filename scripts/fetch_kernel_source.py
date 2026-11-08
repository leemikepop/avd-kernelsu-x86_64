#!/usr/bin/env python3
"""Resolve one AVD target to its exact kernel source.

Steps (no device, no full image download):
  1. Range-read `kernel-ranchu` out of the Google system image zip.
  2. Check its version string against the target's kernel_release / build_id.
  3. Read the ci.android.com manifest for that Build ID and take the kernel/common revision.
  4. Download that revision as a gitiles tarball.

Outputs in --out: kernel-ranchu, manifest.xml, common-<sha>.tar.gz, target.env
(target.env is shell-sourceable: TARGET_ID, KMI, BUILD_ID, COMMON_SHA, SRC_TGZ, DDK_IMAGE,
 PATCHES_KERNELSU, PATCHES_KERNELSU_NEXT, PATCHES_KERNELSU_NEXT_SUSFS, PATCHES_FINASU).
"""
import argparse
import io
import json
import re
import shutil
import struct
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / ".github" / "avd-targets.json"
MANIFEST_URL = "https://ci.android.com/builds/submitted/{bid}/kernel_virt_x86_64/latest/raw/manifest_{bid}.xml"
TARBALL_URL = "https://android.googlesource.com/kernel/common/+archive/{sha}.tar.gz"
UA = {"User-Agent": "avd-kernelsu-x86_64"}


def http_get(url, headers=None, retries=4):
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={**UA, **(headers or {})})
            return urllib.request.urlopen(req, timeout=120)
        except Exception as e:  # noqa: BLE001 - network retry
            if i == retries - 1:
                raise
            print(f"  retry {url}: {e}", file=sys.stderr)
            time.sleep(5 * (i + 1))


class HttpRangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP Range requests (enough for zipfile)."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        with http_get(url, {"Range": "bytes=0-0"}) as r:
            cr = r.headers.get("Content-Range", "")
            if not cr.startswith("bytes "):
                raise RuntimeError(f"server does not support Range: {url}")
            self.size = int(cr.rsplit("/", 1)[1])

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, off, whence=0):
        self.pos = {0: off, 1: self.pos + off, 2: self.size + off}[whence]
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size or len(b) == 0:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        with http_get(self.url, {"Range": f"bytes={self.pos}-{end}"}) as r:
            data = r.read()
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def kernel_release(bzimage: bytes) -> str:
    """Version string of an x86 bzImage (boot protocol: kernel_version at 0x20E)."""
    off = struct.unpack_from("<H", bzimage, 0x20E)[0] + 0x200
    return bzimage[off: bzimage.index(b"\0", off)].decode().split(" ")[0]


def load_target(tid):
    cfg = json.loads(TARGETS.read_text(encoding="utf-8"))
    for t in cfg["targets"]:
        if t["id"] == tid:
            return cfg, t
    sys.exit(f"unknown target {tid}; known: {[t['id'] for t in cfg['targets']]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--skip-tarball", action="store_true", help="only resolve, do not download source")
    a = ap.parse_args()
    cfg, t = load_target(a.target)
    a.out.mkdir(parents=True, exist_ok=True)

    url = cfg["image_base_url"] + t["probe_image"]
    print(f"== kernel-ranchu from {url}")
    with zipfile.ZipFile(io.BufferedReader(HttpRangeFile(url), 1 << 20)) as z:
        name = next(n for n in z.namelist() if n.endswith("/kernel-ranchu") or n == "kernel-ranchu")
        kernel = z.read(name)
    (a.out / "kernel-ranchu").write_bytes(kernel)
    rel = kernel_release(kernel)
    print(f"   {rel}")
    if rel != t["kernel_release"] or not rel.endswith("-ab" + t["build_id"]):
        sys.exit(f"kernel mismatch: image has {rel}, target expects {t['kernel_release']}")

    print(f"== manifest for build {t['build_id']}")
    manifest = http_get(MANIFEST_URL.format(bid=t["build_id"])).read()
    (a.out / "manifest.xml").write_bytes(manifest)
    common = next(p for p in ET.fromstring(manifest).iter("project") if p.get("name") == "kernel/common")
    sha = common.get("revision")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        sys.exit(f"unexpected kernel/common revision {sha!r}")
    if f"-g{sha[:12]}" not in rel:
        sys.exit(f"manifest revision {sha} does not match kernel release {rel}")
    print(f"   kernel/common {sha}")

    tgz = a.out / f"common-{sha}.tar.gz"
    if not a.skip_tarball and not tgz.exists():
        print(f"== source tarball {TARBALL_URL.format(sha=sha)}")
        tmp = tgz.with_suffix(".part")
        with http_get(TARBALL_URL.format(sha=sha)) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
        tmp.rename(tgz)
        print(f"   {tgz.stat().st_size // (1 << 20)} MiB")

    env = {
        "TARGET_ID": t["id"], "KMI": t["kmi"], "BUILD_ID": t["build_id"],
        "KERNEL_RELEASE": rel, "COMMON_SHA": sha, "SRC_TGZ": tgz.name,
        "DDK_IMAGE": f"ghcr.io/ylarod/ddk-min:{t['kmi']}-{cfg['ddk_release']}",
    }
    for variant in ("kernelsu", "kernelsu-next", "kernelsu-next-susfs", "finasu"):
        key = "PATCHES_" + variant.upper().replace("-", "_")
        env[key] = '"' + " ".join(t.get("patches", {}).get(variant, [])) + '"'
    (a.out / "target.env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    print((a.out / "target.env").read_text())


if __name__ == "__main__":
    main()
