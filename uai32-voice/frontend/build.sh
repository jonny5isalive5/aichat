#!/bin/sh
# build.sh SRC OUT  -- compile SRC with EXACTLY the uai32 Makefile flags (Linux branch, with -z nosectionheader).
# Also produces OUT.elf (same link with section headers) for nm/readelf.
set -eu
SRC=$1; OUT=$2
CFLAGS="-std=c99 -Os -Wall -Wextra -pedantic -ffp-contract=off -U_FORTIFY_SOURCE -fno-asynchronous-unwind-tables \
 -fno-stack-protector -fno-ident -fno-pie -fno-plt -fcf-protection=none -fno-math-errno \
 -ffunction-sections -fdata-sections"
LDFLAGS="-s -no-pie -Wl,--gc-sections -Wl,-z,now -Wl,--build-id=none -Wl,-z,norelro -Wl,-z,noseparate-code \
 -Wl,--hash-style=gnu -Wl,-z,max-page-size=4096 -Wl,--no-eh-frame-hdr"
NOSH=-Wl,-z,nosectionheader
LDLIBS=-lm
cc $CFLAGS "$SRC" -o "$OUT" $LDFLAGS $NOSH $LDLIBS
cc $CFLAGS "$SRC" -o "$OUT.elf" $LDFLAGS $LDLIBS
printf '%s: %d bytes (%s.elf: %d bytes)\n' "$OUT" "$(wc -c < "$OUT")" "$OUT" "$(wc -c < "$OUT.elf")"
