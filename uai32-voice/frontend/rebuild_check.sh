#!/bin/bash
# rebuild_check.sh [OUTDIR] -- prove that bin/* rebuild byte-identically from the preserved sources and scripts.
# Runs measure_all.sh into OUTDIR (default ./build), then compares every file listed in bin/SHA256SUMS, the
# generated merged sources uai32_fft.c / uai32_biquad.c, and measurements.txt (minus the timing lines, which
# vary run to run) against the preserved copies.  Exit status 0 only if everything matches.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-$HERE/build}
"$HERE/measure_all.sh" "$OUT" > /dev/null 2>&1 || { echo "measure_all.sh FAILED (see $OUT/measurements.txt)"; exit 1; }
fail=0
echo "== binaries: sha256 of the rebuilt file vs bin/SHA256SUMS"
while read -r sum name; do
  got=$(sha256sum "$OUT/$name" | awk '{print $1}')
  if [ "$got" = "$sum" ]; then echo "IDENTICAL  $name  $(wc -c < "$OUT/$name") bytes  $sum"
  else echo "DIFFERENT  $name  preserved $sum  rebuilt $got"; fail=1; fi
done < "$HERE/bin/SHA256SUMS"
echo "== generated merged sources"
for c in uai32_fft.c uai32_biquad.c; do
  if cmp -s "$OUT/$c" "$HERE/$c"; then echo "IDENTICAL  $c"; else echo "DIFFERENT  $c"; fail=1; fi
done
echo "== import lists"
for s in syms.base syms.uai32_biquad syms.uai32_fft syms.uai32_fft_sinonly syms.vfe_biquad syms.vfe_fft syms.vfe_fft_sinonly; do
  if cmp -s "$OUT/$s" "$HERE/$s"; then echo "IDENTICAL  $s"; else echo "DIFFERENT  $s"; fail=1; fi
done
echo "== measurements.txt without the 'bench' timing lines"
if diff <(grep -v '^bench ' "$HERE/measurements.txt") <(grep -v '^bench ' "$OUT/measurements.txt"); then echo "IDENTICAL  measurements.txt (all non-timing lines)"; else echo "DIFFERENT  measurements.txt"; fail=1; fi
echo "== tests.log: last line"; tail -1 "$OUT/tests.log"
grep -q '^ALL CHECKS PASSED' "$OUT/tests.log" || fail=1
echo "== timing lines of this run"; grep '^bench ' "$OUT/measurements.txt"
[ $fail = 0 ] && echo "REBUILD CHECK PASSED" || echo "REBUILD CHECK FAILED"
exit $fail
