#!/bin/sh
# build.sh -- build the two pilot applications with EXACTLY the uai32 Makefile flags (CFLAGS, LDFLAGS, the
# -Wl,-z,nosectionheader detection) plus the .elf twins (same link with section headers, for readelf/nm), check that
# the shared front-end block is textually identical in both sources and that the linker added no page padding,
# then write SHA256SUMS.  Run from anywhere: it works in its own directory.
set -eu
cd "$(dirname "$0")"
CC=${CC:-cc}
CFLAGS="-std=c99 -Os -Wall -Wextra -pedantic -ffp-contract=off -U_FORTIFY_SOURCE -fno-asynchronous-unwind-tables \
 -fno-stack-protector -fno-ident -fno-pie -fno-plt -fcf-protection=none -fno-math-errno \
 -ffunction-sections -fdata-sections"
LDFLAGS="-s -no-pie -Wl,--gc-sections -Wl,-z,now -Wl,--build-id=none -Wl,-z,norelro -Wl,-z,noseparate-code \
 -Wl,--hash-style=gnu -Wl,-z,max-page-size=4096 -Wl,--no-eh-frame-hdr"
NOSH=$(printf 'int main(){return 0;}' | $CC -x c - -o /dev/null -Wl,-z,nosectionheader 2>/dev/null && echo -Wl,-z,nosectionheader)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
awk '/==== FRONT-END BEGIN/{p=1} p{print} /==== FRONT-END END/{p=0}' dtwapp.c > "$TMP/a"
awk '/==== FRONT-END BEGIN/{p=1} p{print} /==== FRONT-END END/{p=0}' netapp.c > "$TMP/b"
cmp "$TMP/a" "$TMP/b" || { echo "build.sh: the front-end block differs between dtwapp.c and netapp.c" >&2; exit 1; }
echo "front-end block: $(wc -l < "$TMP/a") lines, identical in dtwapp.c and netapp.c"
for p in dtwapp netapp; do
  $CC $CFLAGS $p.c -o $p $LDFLAGS $NOSH -lm
  $CC $CFLAGS $p.c -o $p.elf $LDFLAGS -lm
  # no page padding: the RW segment's file offset must equal the end of the RX segment (rounded to its alignment)
  set -- $(readelf -lW $p | awk '$1=="LOAD"{printf "%s %s ", $2, $5}')
  gap=$(( $3 - ($1 + $2) ))                                  # $1 $2 = RX offset, filesz; $3 = RW offset
  printf '%s: RX segment ends at 0x%x, RW segment starts at 0x%x, gap %d bytes (page padding would be hundreds)\n' $p $(( $1 + $2 )) $(( $3 )) $gap
  [ $gap -le 8 ] || { echo "build.sh: $p has linker page padding" >&2; exit 1; }
  printf '%s: %d bytes (%s.elf: %d bytes)\n' $p "$(wc -c < $p)" $p "$(wc -c < $p.elf)"
done
sha256sum dtwapp dtwapp.elf netapp netapp.elf > SHA256SUMS
cat SHA256SUMS
echo "toolchain: $($CC --version | head -1); $(ld --version | head -1); $(ldd --version | head -1); NOSH='${NOSH}'"
