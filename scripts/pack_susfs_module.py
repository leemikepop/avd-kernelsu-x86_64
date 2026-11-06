#!/usr/bin/env python3
"""Pack the SUSFS guard LKMs of a kernelsu-next-susfs build into a KernelSU module zip.

  pack_susfs_module.py --ko-dir DIR --version V --out FILE.zip [--source TEXT]

DIR holds one <target-id>_..._susfs_guard_lkm.ko per target of .github/avd-targets.json (the
CI artifact names <target>_susfs_guard_lkm.ko and the release names
<target>_kernelsu-next-susfs-<version>_susfs_guard_lkm.ko both work). The module loads the
build whose kernel_release equals the running kernel's, so every target must be present.
Standard library only; the output is reproducible (fixed timestamps, sorted entries).
"""
import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_ID = "susfs_guard_lkm_avd"
SCRIPTS = ("customize.sh", "load.sh", "post-fs-data.sh", "service.sh")
EPOCH = (1980, 1, 1, 0, 0, 0)


def version_code(v):
    """v3.4.2 -> 30402000, v3.4.2-110-g2eed7e95 -> 30402110 (git describe distance in the
    last three digits, so later commits on the same base sort higher)."""
    m = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)(?:-(\d+)-g[0-9a-f]+)?", v)
    if not m:
        sys.exit(f"unexpected version {v!r}: want vX.Y.Z or vX.Y.Z-N-gHASH")
    major, minor, patch, n = (int(x or 0) for x in m.groups())
    if minor > 99 or patch > 99 or n > 999:
        sys.exit(f"version {v!r} does not fit the versionCode scheme")
    return major * 10_000_000 + minor * 100_000 + patch * 1_000 + n


def add(z, name, data, mode=0o644):
    info = zipfile.ZipInfo(name, EPOCH)
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(info, data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ko-dir", required=True)
    ap.add_argument("--version", required=True, help="release version, e.g. v3.4.2-110-g2eed7e95")
    ap.add_argument("--out", required=True)
    ap.add_argument("--targets", default=str(ROOT / ".github" / "avd-targets.json"))
    ap.add_argument("--source", default="", help="provenance line(s) for SOURCES.txt")
    a = ap.parse_args()

    targets = json.loads(Path(a.targets).read_text(encoding="utf-8"))["targets"]
    kos = sorted(Path(a.ko_dir).glob("*_susfs_guard_lkm.ko"))
    files, kos_lines, missing = {}, [], []
    for t in targets:
        found = [p for p in kos if p.name.startswith(t["id"] + "_")]
        if len(found) != 1:
            missing.append(f"{t['id']} ({len(found)} matches)")
            continue
        name = f"{t['id']}.ko"
        files[f"lib/{name}"] = found[0].read_bytes()
        kos_lines.append(f"{t['kernel_release']} {name}\n")
    if missing:
        sys.exit(f"need exactly one *_susfs_guard_lkm.ko per target in {a.ko_dir}; bad: {', '.join(missing)}")

    labels = ", ".join(t["label"] for t in targets)
    prop = (f"id={MODULE_ID}\n"
            "name=SUSFS guard LKM (AVD x86_64)\n"
            f"version={a.version}\n"
            f"versionCode={version_code(a.version)}\n"
            "author=leemikepop/avd-kernelsu-x86_64\n"
            "description=Not loaded yet. Loads the SUSFS guard LKM built for this AVD's exact kernel "
            "at every boot (kernelsu-next-susfs preview). Loader only, no rules.\n")
    sources = (f"SUSFS guard LKM module, kernelsu-next-susfs {a.version}\n"
               f"Kernels: {labels}\n"
               "lib/*.ko: GPL-2.0-only. Scripts: Apache-2.0, from "
               "https://github.com/leemikepop/avd-kernelsu-x86_64/tree/main/susfs-module\n"
               + (a.source.rstrip("\n") + "\n" if a.source else ""))

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w") as z:
        add(z, "module.prop", prop)
        add(z, "kos", "".join(kos_lines))
        add(z, "skip_mount", "")
        add(z, "SOURCES.txt", sources)
        for s in SCRIPTS:
            text = (ROOT / "susfs-module" / s).read_text(encoding="utf-8").replace("\r\n", "\n")
            add(z, s, text, 0o755)
        for name in sorted(files):
            add(z, name, files[name])
    print(f"{out}: {len(files)} kernels, versionCode {version_code(a.version)}")


if __name__ == "__main__":
    main()
