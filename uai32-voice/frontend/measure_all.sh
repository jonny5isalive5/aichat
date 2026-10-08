#!/bin/sh
# measure_all.sh [OUTDIR] -- regenerate every number quoted in the report.  Sources and scripts are taken from
# the directory of this script; the frozen release ../../uai32/ supplies uai32.c and the 9,188-byte reference
# executable (never written to).  Everything is built in OUTDIR (default: ./build next to this script) and the
# log goes to OUTDIR/measurements.txt.  Needs cc, binutils, python3 + numpy.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
UAI32=${UAI32:-$HERE/../../uai32}
OUT=${1:-$HERE/build}
mkdir -p "$OUT"; cd "$OUT"
{
echo "toolchain: $(cc --version | head -1); $(ld --version | head -1); $(ldd --version | head -1)"
"$HERE/build.sh" "$UAI32/uai32.c" uai32.rebuilt; cmp uai32.rebuilt "$UAI32/uai32" && echo "baseline reproduced: 9188 bytes"
"$HERE/merge.sh" FE_BIQUAD uai32_biquad.c; "$HERE/merge.sh" FE_FFT uai32_fft.c
for b in "vfe_biquad $HERE/vfe.c -DFE_BIQUAD" "vfe_fft $HERE/vfe.c -DFE_FFT" "vfe_fft_sinonly $HERE/vfe.c -DFE_FFT -DSINONLY" \
         "uai32_biquad uai32_biquad.c" "uai32_fft uai32_fft.c" "uai32_fft_sinonly uai32_fft.c -DSINONLY" \
         "uai32_fft_12x10 uai32_fft.c -DNB=12 -DNT=10" "uai32_fft_16x16 uai32_fft.c -DNB=16 -DNT=16" \
         "uai32_biquad_12x10 uai32_biquad.c -DNB=12 -DNT=10" "uai32_biquad_16x16 uai32_biquad.c -DNB=16 -DNT=16"; do "$HERE/build_variant.sh" $b; done
echo "deltas over 9188: biquad +$(( $(wc -c < uai32_biquad) - 9188 ))  fft +$(( $(wc -c < uai32_fft) - 9188 ))  fft-sinonly +$(( $(wc -c < uai32_fft_sinonly) - 9188 ))"
nm -D --undefined-only uai32.rebuilt.elf | awk '{print $2}' | sort > syms.base
for v in uai32_biquad uai32_fft uai32_fft_sinonly; do nm -D --undefined-only $v.elf | awk '{print $2}' | sort > syms.$v; echo "$v imports added: $(comm -13 syms.base syms.$v | tr '\n' ' ')"; done
for v in vfe_biquad vfe_fft vfe_fft_sinonly; do nm -D --undefined-only $v.elf | awk '{print $2}' | sort > syms.$v; done
"$HERE/sizes.sh" uai32.rebuilt.elf uai32_biquad.elf uai32_fft.elf
for f in uai32_biquad uai32_fft; do printf '%-14s' $f; readelf -l -W $f | grep -E '^\s+LOAD' | awk '{printf "%s off=%s filesz=%s memsz=%s  ", $7$8, $2, $5, $6} END{print ""}'; done
# The bench builds warn "feat_main defined but not used" (main is replaced by the bench loop); the warning is harmless
# and is silenced here so the size line stays readable.  Run the line without 2>/dev/null to see it.
"$HERE/build_variant.sh" vfe_biquad_bench "$HERE/vfe.c" -DFE_BIQUAD -DBENCH=200 -D_POSIX_C_SOURCE=200809L 2>/dev/null
"$HERE/build_variant.sh" vfe_fft_bench "$HERE/vfe.c" -DFE_FFT -DBENCH=200 -D_POSIX_C_SOURCE=200809L 2>/dev/null
python3 -I "$HERE/synth_tests.py" "$PWD" > tests.log 2>&1 && tail -1 tests.log
for v in biquad fft; do for i in 1 2 3; do printf 'bench %-7s ' $v; ./vfe_${v}_bench tests/noise_fft.raw; done; done
} 2>&1 | tee measurements.txt
