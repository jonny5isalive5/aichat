#!/bin/sh
# Rebuild bin/libdtw.so and bin/frontend from code/ and check them against bin/SHA256SUMS.
# (Added during preservation, 2026-10-08.  bin/uai32 is never built here: it is a copy of the frozen release
#  ../uai32/dist/uai32 and is only hash-checked.)  Toolchain used for the recorded hashes: gcc 13.3.0, binutils 2.42,
# glibc 2.39, x86-64 Linux.
set -eu
cd "$(dirname "$0")/.."
# libdtw.so: the command recorded in results/HOW_TO_RERUN.txt (plain -O2 shared object; it is a ctypes helper for the
# Python benchmark, not a size-measured artefact)
gcc -O2 -shared -fPIC -o bin/libdtw.so code/dtw.c -lm
# frontend: the uai32 Makefile CFLAGS/LDFLAGS *without* -std=c99 (with -std=c99 frontend.c fails on M_PI; see FAILURES.md)
CFLAGS="-Os -Wall -Wextra -pedantic -ffp-contract=off -U_FORTIFY_SOURCE -fno-asynchronous-unwind-tables -fno-stack-protector -fno-ident -fno-pie -fno-plt -fcf-protection=none -fno-math-errno -ffunction-sections -fdata-sections"
LDFLAGS="-s -no-pie -Wl,--gc-sections -Wl,-z,now -Wl,--build-id=none -Wl,-z,norelro -Wl,-z,noseparate-code -Wl,--hash-style=gnu -Wl,-z,max-page-size=4096 -Wl,--no-eh-frame-hdr"
NOSH=$(printf 'int main(){return 0;}' | ${CC:-gcc} -x c - -o /dev/null -Wl,-z,nosectionheader 2>/dev/null && echo -Wl,-z,nosectionheader)
gcc $CFLAGS code/frontend.c -o bin/frontend $LDFLAGS $NOSH -lm
# the two .text figures quoted in results/summary.txt (objects are not kept)
gcc -std=c99 $CFLAGS -c code/dtw.c -o /tmp/dtw_uai32flags.o && size /tmp/dtw_uai32flags.o | tail -1 | awk '{print "dtw.c  .text with the uai32 CFLAGS:", $1, "bytes (summary.txt says 546)"}'
gcc $CFLAGS -c code/frontend.c -o /tmp/frontend_uai32flags.o && size /tmp/frontend_uai32flags.o | tail -1 | awk '{print "frontend.c .text with the uai32 CFLAGS minus -std=c99:", $1, "bytes (summary.txt says 2,006)"}'
rm -f /tmp/dtw_uai32flags.o /tmp/frontend_uai32flags.o
wc -c bin/uai32 bin/libdtw.so bin/frontend
(cd bin && sha256sum -c SHA256SUMS)
