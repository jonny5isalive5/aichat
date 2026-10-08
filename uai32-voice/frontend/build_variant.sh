#!/bin/sh
# build_variant.sh OUT SRC [extra cc flags...] -- exact uai32 Makefile flags + extras; prints size; warnings are fatal to notice
set -eu
OUT=$1; SRC=$2; shift 2
CFLAGS="-std=c99 -Os -Wall -Wextra -pedantic -ffp-contract=off -U_FORTIFY_SOURCE -fno-asynchronous-unwind-tables \
 -fno-stack-protector -fno-ident -fno-pie -fno-plt -fcf-protection=none -fno-math-errno \
 -ffunction-sections -fdata-sections"
LDFLAGS="-s -no-pie -Wl,--gc-sections -Wl,-z,now -Wl,--build-id=none -Wl,-z,norelro -Wl,-z,noseparate-code \
 -Wl,--hash-style=gnu -Wl,-z,max-page-size=4096 -Wl,--no-eh-frame-hdr"
cc $CFLAGS "$@" "$SRC" -o "$OUT" $LDFLAGS -Wl,-z,nosectionheader -lm
cc $CFLAGS "$@" "$SRC" -o "$OUT.elf" $LDFLAGS -lm
printf '%-22s %6d bytes   (.elf with section headers: %d)\n' "$OUT" "$(wc -c < "$OUT")" "$(wc -c < "$OUT.elf")"
