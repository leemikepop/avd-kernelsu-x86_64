#!/usr/bin/env python3
"""x86_icall_windows - check an x86_64 kernelsu.ko against the kernel's kCFI call-site rewrite.

On x86_64 kernels with the FineIBT/kCFI call-site rewrite (Linux 6.2+, so android15-6.6 and
android16-6.12; a module built for an older kernel is reported and passes), module_finalize() ->
apply_fineibt() walks .retpoline_sites and, for each indirect call, reads the 14 bytes in front
of it (cfi_disable_callers(), cfi_rand_callers()).  If they start with `41 ba` (movl $hash,%r10d)
or `eb 0c` (the disabled form) the kernel takes them for the kCFI caller sequence and rewrites
the four bytes after them.  A checked call really has that sequence there.  An unchecked call
(__nocfi) has whatever the compiler emitted, and when a relocation covers those bytes their
value depends on where the module was loaded, so some loads corrupt the code before the call.

patches/x86_64-kcfi-icall-trampoline.patch makes every unchecked call go through one
trampoline (KSU_ICALL -> ksu_icall8), and this tool asserts that on the built module:

  window  Every .retpoline_sites call is either checked (fixed `41 ba` in front) or has fixed,
          non-matching bytes in front: no relocation may cover the two bytes the kernel tests,
          and they must not be `41 ba` / `eb 0c`.
  trampo  Unchecked calls may only sit in the trampoline (default: ksu_icall8), so a new call
          that bypasses KSU_ICALL is caught even while its bytes happen to be safe.
  allow   With --allow, a CHECKED call outside the listed functions fails too (not used for
          kernelsu.ko, whose checked calls into the kernel are intended).

Usage:
    x86_icall_windows.py [--trampoline ksu_icall8] [--allow f1,f2] <ko> [<ko> ...]
Exit status 1 when any check fails.  Needs only the Python standard library.
"""
import argparse
import struct
import sys

SHT_SYMTAB, SHT_RELA = 2, 4
STT_FUNC = 2
R_X86_64_64, R_X86_64_PC64 = 1, 24
CALLER_SEQ = 14  # fineibt_caller_size in arch/x86/kernel/alternative.c
KCFI_CALLER = b'\x41\xba'  # movl $hash, %r10d
KCFI_DISABLED = b'\xeb\x0c'  # jmp.d8 +12, cfi_disable_callers()


class Ko:
    def __init__(self, path):
        self.path = path
        b = self.b = open(path, 'rb').read()
        if b[:4] != b'\x7fELF' or b[4] != 2 or b[5] != 1 or struct.unpack_from('<H', b, 18)[0] != 62:
            raise SystemExit(f'{path}: not a little-endian ELF64 x86_64 object')
        shoff, = struct.unpack_from('<Q', b, 0x28)
        shentsize, shnum, shstrndx = struct.unpack_from('<HHH', b, 0x3a)
        self.secs = [struct.unpack_from('<IIQQQQIIQQ', b, shoff + i * shentsize) for i in range(shnum)]
        names = self.secs[shstrndx][4]
        self.names = [self._str(names, s[0]) for s in self.secs]
        symtab = next(i for i, s in enumerate(self.secs) if s[1] == SHT_SYMTAB)
        st = self.secs[symtab]
        self.strtab = self.secs[st[6]][4]
        self.syms = [struct.unpack_from('<IBBHQQ', b, st[4] + i * 24) for i in range(st[5] // 24)]
        self.rela = {}
        for s in self.secs:
            if s[1] == SHT_RELA:
                self.rela[s[7]] = [struct.unpack_from('<QQq', b, s[4] + i * 24) for i in range(s[5] // 24)]
        self.funcs = sorted((y[3], y[4], y[5], self._str(self.strtab, y[0]))
                            for y in self.syms if y[1] & 0xf == STT_FUNC)

    def _str(self, base, off):
        return self.b[base + off:self.b.index(b'\0', base + off)].decode()

    def func_at(self, sec, off):
        for s, v, size, name in self.funcs:
            if s == sec and v <= off < v + max(size, 1):
                return name, off - v
        return '?', off

    def sites(self):
        """(section index, offset) of every .retpoline_sites entry."""
        if '.retpoline_sites' not in self.names:
            return []
        rs = self.names.index('.retpoline_sites')
        out = []
        for _, info, addend in self.rela.get(rs, []):
            sym = self.syms[info >> 32]
            out.append((sym[3], sym[4] + addend))
        return out

    def covering(self, sec, start, end):
        """Relocations in @sec that write any byte in [start, end)."""
        hits = []
        for off, info, _ in self.rela.get(sec, []):
            width = 8 if info & 0xffffffff in (R_X86_64_64, R_X86_64_PC64) else 4
            if off < end and start < off + width:
                sym = self.syms[info >> 32]
                hits.append(self._str(self.strtab, sym[0]) or self.names[sym[3]])
        return hits


def kernel_version(ko):
    """(major, minor) from .modinfo's vermagic, or None."""
    if '.modinfo' not in ko.names:
        return None
    s = ko.secs[ko.names.index('.modinfo')]
    for field in ko.b[s[4]:s[4] + s[5]].split(b'\0'):
        if field.startswith(b'vermagic='):
            parts = field[9:].split(b'.')
            try:
                return int(parts[0]), int(parts[1].split(b'-')[0].split(b' ')[0])
            except (IndexError, ValueError):
                return None
    return None


def check(path, allow, trampolines, force):
    ko = Ko(path)
    ver = kernel_version(ko)
    # The caller rewrite came with FineIBT (Linux 6.2); android13-5.15 and android14-6.1 do not
    # have it, so there is nothing to protect against there.
    if not force and ver is not None and ver < (6, 2):
        print(f'{path}: kernel {ver[0]}.{ver[1]} has no kCFI caller rewrite (6.2+), nothing to check')
        return True
    hint = f'call it through {"/".join(sorted(trampolines))}'
    sites = ko.sites()
    errors, checked, unchecked = [], 0, 0
    for sec, off in sites:
        fn, rel = ko.func_at(sec, off)
        where = f'{ko.names[sec]}+{off:#x} {fn}+{rel:#x}'
        start = off - CALLER_SEQ
        data = ko.secs[sec][4]
        if start < 0:
            errors.append(f'{where}: caller window starts before its section')
            continue
        relocs = ko.covering(sec, start, start + 2)
        window = ko.b[data + start:data + start + 2]
        if relocs:
            errors.append(f'{where}: caller window overlaps a relocation ({", ".join(relocs)}) - {hint}')
        elif window == KCFI_CALLER:
            checked += 1
            if allow is not None and fn not in allow:
                errors.append(f'{where}: CFI-checked indirect call outside the allow-list')
        elif window == KCFI_DISABLED:
            errors.append(f'{where}: fixed bytes eb 0c in front of an unchecked call')
        else:
            unchecked += 1
            if fn not in trampolines:
                errors.append(f'{where}: unchecked indirect call outside the trampoline - {hint}')
    print(f'{path}: {len(sites)} retpoline sites, {checked} checked, {unchecked} unchecked, '
          f'{len(errors)} problem(s)')
    for e in errors:
        print(f'  {e}')
    return not errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--allow', help='comma-separated functions allowed to make CFI-checked calls')
    ap.add_argument('--trampoline', default='ksu_icall8',
                    help='comma-separated functions allowed to make unchecked calls')
    ap.add_argument('--force', action='store_true',
                    help='check even when vermagic names a kernel older than 6.2')
    ap.add_argument('ko', nargs='+')
    a = ap.parse_args()
    allow = set(a.allow.split(',')) if a.allow else None
    ok = all([check(p, allow, set(a.trampoline.split(',')), a.force) for p in a.ko])
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
