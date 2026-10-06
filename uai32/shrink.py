#!/usr/bin/env python3
"""Remove the section header table from an ELF executable (what the classic `sstrip` tool does).

Section headers describe the file to linkers and debuggers; the kernel and the dynamic loader
only read the program headers, so a running program never needs them.  After `strip -s` they
are the largest piece of pure metadata left (~1.9 KB here).  We zero the three header fields
that point at them and cut the file after the last byte any program header loads.

  python3 shrink.py uai32        (edits the file in place, prints before/after sizes)
"""
import struct, sys

path = sys.argv[1]
d = bytearray(open(path, "rb").read())
assert d[:4] == b"\x7fELF" and d[4] == 2 and d[5] == 1, "need a little-endian ELF64 file"
e_phoff, = struct.unpack_from("<Q", d, 0x20)
e_phentsize, e_phnum = struct.unpack_from("<HH", d, 0x36)
end = 0
for i in range(e_phnum):
    p_offset, p_vaddr, p_paddr, p_filesz = struct.unpack_from("<QQQQ", d, e_phoff + i * e_phentsize + 8)
    end = max(end, p_offset + p_filesz)
struct.pack_into("<Q", d, 0x28, 0)        # e_shoff
struct.pack_into("<HH", d, 0x3C, 0, 0)    # e_shnum, e_shstrndx
before = len(d)
open(path, "wb").write(d[:end])
print(f"{path}: {before} -> {end} bytes (section headers removed)")
