#!/bin/sh
# merge.sh VARIANT OUT.c [VFE.c] -- splice the VFE block of vfe.c into a copy of uai32.c and add the `feat` verb.
# VARIANT is FE_BIQUAD or FE_FFT.  The result is one self-contained C file (the real combined program).
# Paths: VFE.c defaults to vfe.c next to this script; uai32.c is taken from the frozen release
# ../../uai32/uai32.c (override with UAI32_C=...).  OUT.c is written where you say (relative to the cwd).
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=${3:-$HERE/vfe.c}
UAI32_C=${UAI32_C:-$HERE/../../uai32/uai32.c}
V=$1; OUT=$2; BLK=$(mktemp)
trap 'rm -f "$BLK"' EXIT
awk '/==== VFE BEGIN ====/{p=1} p{print} /==== VFE END ====/{p=0}' "$SRC" > "$BLK"
{
  printf '/* %s -- uai32.c with the voice front-end of vfe.c (%s) merged in: adds the verb\n' "$(basename "$OUT")" "$V"
  printf ' *   uai32 feat [-n] [WAV|-] [LABEL]   (one second of 16 kHz 16-bit mono PCM -> one data row). */\n'
  printf '#define %s\n' "$V"
  awk -v blk="$BLK" '{ print } /^#include <limits.h>/ { while ((getline l < blk) > 0) print l }' "$UAI32_C"
} | sed \
  -e 's|^    if (argc < 3) usage();$|    if (argc > 1 \&\& !strcmp(argv[1], "feat")) return feat_main(argc - 2, argv + 2);\n    if (argc < 3) usage();|' \
  -e 's|  uai32 predict MODEL < rows");|  uai32 predict MODEL < rows\\n  uai32 feat [-n] [WAV\|-] [LABEL]");|' > "$OUT"
grep -q 'feat_main(argc - 2' "$OUT" && grep -q 'uai32 feat \[-n\]' "$OUT" || { echo "merge failed" >&2; exit 1; }
