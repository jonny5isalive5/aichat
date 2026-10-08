#!/bin/sh
# extra_variants.sh [OUTDIR] -- the hand-run builds behind the report's side findings, reproduced in one go:
#   * the -n normalisation code cost (vfe_nonorm.c = vfe.c without the mean-removal loop),
#   * the NB=8 x NT=12 feature-size variant,
#   * the static-array layout (vfe_static.c) and the GNU ld page-padding it triggers at NB=12 (see FAILURES.md),
#   * the standalone vfe_biquad padding (RX segment ends before a page boundary, RW starts on the next page).
# Output: OUTDIR/extra_measurements.txt.  Needs the frozen ../../uai32/uai32.c.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-$HERE/build}
mkdir -p "$OUT"; cd "$OUT"
segs() { readelf -l -W "$1" | grep -E '^\s+LOAD' | awk '{printf "%s off=%s filesz=%s memsz=%s  ", $7$8, $2, $5, $6}'; }
{
echo "== -n code cost: merged builds from vfe_nonorm.c"
"$HERE/merge.sh" FE_BIQUAD uai32_biquad_nonorm.c "$HERE/vfe_nonorm.c"; "$HERE/merge.sh" FE_FFT uai32_fft_nonorm.c "$HERE/vfe_nonorm.c"
"$HERE/build_variant.sh" uai32_biquad_nonorm uai32_biquad_nonorm.c
"$HERE/build_variant.sh" uai32_fft_nonorm uai32_fft_nonorm.c
"$HERE/merge.sh" FE_BIQUAD uai32_biquad.c; "$HERE/merge.sh" FE_FFT uai32_fft.c
"$HERE/build_variant.sh" uai32_biquad uai32_biquad.c; "$HERE/build_variant.sh" uai32_fft uai32_fft.c
echo "-n cost: biquad $(( $(wc -c < uai32_biquad) - $(wc -c < uai32_biquad_nonorm) ))  fft $(( $(wc -c < uai32_fft) - $(wc -c < uai32_fft_nonorm) )) bytes"
echo "== NB=8 x NT=12"
"$HERE/build_variant.sh" uai32_fft_8x12 uai32_fft.c -DNB=8 -DNT=12
"$HERE/build_variant.sh" uai32_biquad_8x12 uai32_biquad.c -DNB=8 -DNT=12
echo "== static arrays (vfe_static.c): NB=16 NT=12 (default) and NB=12 NT=10"
"$HERE/merge.sh" FE_BIQUAD uai32_biquad_static.c "$HERE/vfe_static.c"; "$HERE/merge.sh" FE_FFT uai32_fft_static.c "$HERE/vfe_static.c"
for b in "uai32_biquad_static uai32_biquad_static.c" "uai32_fft_static uai32_fft_static.c" \
         "uai32_biquad_static_12x10 uai32_biquad_static.c -DNB=12 -DNT=10" "uai32_fft_static_12x10 uai32_fft_static.c -DNB=12 -DNT=10"; do "$HERE/build_variant.sh" $b; done
for f in uai32_biquad_static uai32_biquad_static_12x10 uai32_fft_static uai32_fft_static_12x10; do printf '%-26s %s\n' "$f" "$(segs $f)"; done
"$HERE/sizes.sh" uai32_biquad_static.elf uai32_biquad_static_12x10.elf uai32_fft_static.elf uai32_fft_static_12x10.elf
echo "padding: biquad_static_12x10 - biquad_static = $(( $(wc -c < uai32_biquad_static_12x10) - $(wc -c < uai32_biquad_static) )) bytes;  fft_static_12x10 - fft_static = $(( $(wc -c < uai32_fft_static_12x10) - $(wc -c < uai32_fft_static) )) bytes"
echo "== calloc layout at the same NB/NT for comparison (no padding expected)"
for f in uai32_biquad uai32_fft; do printf '%-26s %s\n' "$f" "$(segs $f)"; done
"$HERE/build_variant.sh" uai32_biquad_12x10 uai32_biquad.c -DNB=12 -DNT=10 > /dev/null; "$HERE/build_variant.sh" uai32_fft_12x10 uai32_fft.c -DNB=12 -DNT=10 > /dev/null
for f in uai32_biquad_12x10 uai32_fft_12x10; do printf '%-26s %s\n' "$f" "$(segs $f)"; done
echo "== standalone vfe_biquad: RX ends at 0xec4, RW placed at 0x1000 (316 bytes of padding); vfe_fft: none"
"$HERE/build_variant.sh" vfe_biquad "$HERE/vfe.c" -DFE_BIQUAD > /dev/null; "$HERE/build_variant.sh" vfe_fft "$HERE/vfe.c" -DFE_FFT > /dev/null
for f in vfe_biquad vfe_fft; do printf '%-26s %s\n' "$f" "$(segs $f)"; done
echo "== bench build warning that measure_all.sh silences"
"$HERE/build_variant.sh" vfe_fft_bench "$HERE/vfe.c" -DFE_FFT -DBENCH=200 -D_POSIX_C_SOURCE=200809L 2>&1 | grep -E 'warning|bytes' | sort -u
} 2>&1 | tee extra_measurements.txt
