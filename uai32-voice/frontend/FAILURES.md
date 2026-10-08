# Failed, surprising and abandoned steps in the front-end investigation

Everything below was observed with gcc 13.3.0 / GNU ld 2.42 / glibc 2.39 on x86-64 Linux, using the
exact uAI-32 Makefile flags.  Each item gives the command that showed it; the commands are collected in
`extra_variants.sh`, whose output is `extra_measurements.txt` (re-run on 2026-10-08 from this directory).

## 1. GNU ld page padding with static `.bss` arrays (abandoned layout)

The first layout (`vfe_static.c`) kept every buffer as a static array: `pcm[16000]` shorts,
`band[124][NB]`, `feat`, `edge` and (FFT) `re/im/win/twr/twi` floats, about 40-45 KB of `.bss`.
At the default NB=16 x NT=12 the merged executables were 96 / 192 bytes *smaller* than the calloc
versions (10,796 biquad, 11,220 FFT, versus 10,892 / 11,412), because the pointer loads and the
`alloc_fe` call disappear.  But at NB=12 x NT=10 the *same* sources gave 12,964 / 12,972 bytes with
*identical* section sizes: GNU ld placed the RW segment at file offset 0x3000 (the next page boundary)
instead of right after the RX segment, writing 2,168 / 1,752 bytes of zeros into the file.

```
./merge.sh FE_BIQUAD uai32_biquad_static.c vfe_static.c
./merge.sh FE_FFT    uai32_fft_static.c    vfe_static.c
./build_variant.sh uai32_biquad_static       uai32_biquad_static.c
./build_variant.sh uai32_fft_static          uai32_fft_static.c
./build_variant.sh uai32_biquad_static_12x10 uai32_biquad_static.c -DNB=12 -DNT=10
./build_variant.sh uai32_fft_static_12x10    uai32_fft_static.c    -DNB=12 -DNT=10
readelf -l -W uai32_biquad_static uai32_biquad_static_12x10 uai32_fft_static uai32_fft_static_12x10 | grep LOAD
./sizes.sh uai32_biquad_static.elf uai32_biquad_static_12x10.elf uai32_fft_static.elf uai32_fft_static_12x10.elf
```

| build | file bytes | RX filesz | RW file offset | RW memsz | .text | .bss |
|---|---|---|---|---|---|---|
| uai32_biquad_static (16x12) | 10,796 | 0x2784 | 0x2788 (no padding) | 0xa2d8 | 6,497 | 40,992 |
| uai32_biquad_static_12x10 | **12,964** | 0x2774 | **0x3000** (+2,168 padding) | 0x99e0 | 6,481 | 38,688 |
| uai32_fft_static (16x12) | 11,220 | 0x2924 | 0x2928 (no padding) | 0xb2d8 | 6,849 | 45,088 |
| uai32_fft_static_12x10 | **12,972** | 0x2924 | **0x3000** (+1,752 padding) | 0xa9e0 | 6,849 | 42,784 |

Section sizes of the FFT pair are byte-for-byte the same (`.text` 6,849, `.bss` differs only by the
array sizes); the whole 1,752-byte difference is the file offset of the RW segment.  The cause is the
`-z noseparate-code -z max-page-size=4096` layout: ld wants `offset mod 4096 == vaddr mod 4096` for the
RW segment, and with a large `.bss` the virtual address it picks for the RW segment can land on a
different page than the end of the RX data, so the file offset jumps to the next page.  Which
`.bss` sizes trigger it is not predictable from the sizes alone.

Resolution: `vfe.c` takes every buffer from **one `calloc`** (as `uai32.c` does), leaving `.bss` at
200 / 240 bytes.  With that layout none of the eight NB/NT configurations tried (16x12, 12x10, 16x16,
8x12, with and without `-n`, with and without `SINONLY`) showed any padding; the RW segment starts
4 bytes after the RX segment in every one:

```
uai32_biquad        RE off=0x000000 filesz=0x0027e4   RW off=0x0027e8 filesz=0x0002a4 memsz=0x000380
uai32_fft           RE off=0x000000 filesz=0x0029e4   RW off=0x0029e8 filesz=0x0002ac memsz=0x0003a8
uai32_biquad_12x10  RE off=0x000000 filesz=0x0027e4   RW off=0x0027e8
uai32_fft_12x10     RE off=0x000000 filesz=0x0029e4   RW off=0x0029e8
```

Rule kept from this: on every budgeted build run `readelf -l -W EXE | grep LOAD` and check that the RW
offset equals the end of the RX segment (rounded to 8).  Any change of buffer sizes, compiler or
binutils version must be re-checked; the file size is a property of the linker layout, not only of the
code.

## 2. The standalone `vfe_biquad` contains 316 bytes of the same padding

`vfe_biquad` (4,688 bytes) is not a clean measurement: its RX segment ends at file offset 0xec4 and ld
placed the RW segment at 0x1000, so 316 bytes of the file are zeros.  `vfe_fft` (4,896) has no padding
(RX ends 0x10c4, RW at 0x10c8).  That is why the report treats the standalone sizes as less meaningful
than the merged ones, and why the biquad/FFT difference looks like 208 bytes standalone but is 520 bytes
merged.

```
./build_variant.sh vfe_biquad vfe.c -DFE_BIQUAD; ./build_variant.sh vfe_fft vfe.c -DFE_FFT
readelf -l -W vfe_biquad vfe_fft | grep LOAD
vfe_biquad  RE off=0x000000 filesz=0x000ec4   RW off=0x001000 filesz=0x000250 memsz=0x0002b0
vfe_fft     RE off=0x000000 filesz=0x0010c4   RW off=0x0010c8 filesz=0x000258 memsz=0x0002d0
```

## 3. `cosf` + `sinf` were fused into a `sincosf` import (surprise, then a measured alternative)

The FFT twiddle loop computes `cosf(2*pi*j/FL)` and `sinf(2*pi*j/FL)` of the same argument.  Under
`-fno-math-errno` gcc 13 replaces the pair by one call to `sincosf`, so the import list of
`uai32_fft` gains `sincosf` *and* `sinf` (the window uses `sinf` alone), not `cosf`:

```
nm -D --undefined-only uai32_fft.elf | awk '{print $2}' | sort | comm -13 syms.base -
sincosf@GLIBC_2.2.5
sinf@GLIBC_2.2.5
```

Each extra dynamic import costs about 65-80 bytes of `.dynsym`/`.dynstr`/`.gnu.version`/`.rela.dyn`/
`.got`.  Writing the cosine as a shifted sine (`-DSINONLY`: `twr[j] = sinf(PI/2 - 2*PI*j/FL)`) removes
the `sincosf` import and saves 72 bytes (11,340 instead of 11,412) at the cost of one more `sinf` call per
twiddle at start-up.  The report keeps 11,412 as the headline number and 11,340 as the option; the
preserved `uai32_fft_sinonly` is that build.  Another compiler may import `cosf` and `sinf` instead
(still two imports, same order of bytes); `sinf` from a different libm could change low bits of the
features but not the accuracy.

```
./build_variant.sh uai32_fft_sinonly uai32_fft.c -DSINONLY     # 11340 bytes, imports added: sinf only
```

## 4. Builds that warn

* The `BENCH` builds (`-DBENCH=200`, used only for timing) warn
  `vfe.c:179:12: warning: 'feat_main' defined but not used [-Wunused-function]` because the bench
  `main` replaces the normal one.  `measure_all.sh` silences this with `2>/dev/null`; run the line
  without it to see the warning.  The benchmark binaries are not part of the deliverable.
* The `vfe_nonorm.c` builds (used only to price the `-n` code) warn
  `pool: unused parameter 'norm' [-Wunused-parameter]`, because the mean-removal loop was deleted but the
  parameter kept so that `merge.sh` and `feat_main` are unchanged.  The deliverable sources `vfe.c`,
  `uai32_fft.c`, `uai32_biquad.c` compile with zero warnings under
  `-Wall -Wextra -pedantic` (checked by `rebuild_check.sh`: `build.sh`/`build_variant.sh` print any
  warning, and the preserved `measurements.txt` contains none).

## 5. `tests.log`: nothing failed, but two results needed care

`tests.log` contains 188 `ok` lines and no `FAIL` line, on the first and only run of the final
`synth_tests.py` (and again, identically, on the 2026-10-08 re-run in `rebuild_check.sh`).  Two entries
are not perfect scores and are reported as such:

* **e2e/biquad 39/40 = 97.5 %** (the FFT variant scores 40/40) on the synthetic 4-class tone-pair task
  with a 192-16-4 model trained 40 epochs at rate 0.05, seed 1.  The threshold in the test is 90 %,
  so it passes, but it is the evidence behind the report's remark that the biquad bank (neighbour bands
  only 1.4-2.0 nats down) discriminates less well than the mel/FFT bank (10-13 nats down).
* **FFT peak level tolerance had to be 0.60 nat** where the biquad tolerance is 0.05 nat: a 0.5-amplitude
  tone at a band centre gives -1.302..-1.017 instead of ln(0.25) = -1.386, because the Hann main lobe
  spreads the tone over 2-3 FFT bins and the triangular filters weight those bins differently depending
  on where the tone falls relative to the 62.5 Hz bin grid.  The spread is up to 0.3 nat (2.5 dB)
  between tones; it is deterministic and harmless after training, but visible in raw features.

The numpy-reference comparison tolerances are 0.02 nat for features more than ln(100) above the floor
and 0.5 nat near the floor; the measured maxima were 0.0005 in both regions, i.e. the three-decimal
print resolution.

## 6. Known limitation that was documented rather than fixed

`read_pcm` walks WAV chunks to `data` and then reads samples until 16,000 are collected or EOF, without
honouring the `data` chunk length.  A WAV shorter than 1 s that has further chunks *after* `data` would
mix those chunk bytes into the zero-padded tail.  No test exercises this (the `LIST` chunk test puts the
extra chunk before `data`).  Fixing it costs a few bytes and was left out of the measured 1,704 / 2,224.

## 7. Not measured, only estimated

* Per-process wall time for one `feat` run (3.5-4.8 ms in the report) is dominated by dynamic loading
  and varies with the container; it was re-measured on 2026-10-08 (see README, "Time and RAM") on a
  different Xeon model than the original run (2.10 GHz nominal here, 2.80 GHz reported then).
* **The report's peak-RSS figure (11,192-11,256 KB, "the same as the baseline uai32, glibc dominated")
  is a measurement artefact and is withdrawn.**  It was taken as `ru_maxrss` of a child forked from a
  Python harness; a forked child shares the parent's address space until `exec`, and the kernel charges
  those pages to the child, so every command measured that way, including `/bin/true`, reports the
  Python parent's 11 MB (reproduced on 2026-10-08: `/bin/true` 11,112-11,164 KB from python3).
  Re-measured with `maxrss.c` (`posix_spawn`, no address-space copy): `/bin/true` 1,376 KB floor,
  `uai32_fft feat` 2,272-2,376 KB, `uai32_biquad feat` 2,280-2,300 KB, the frozen `uai32 predict`
  2,204-2,328 KB (`ram_time.txt`).  The front-end's own buffers are 40,776 / 44,872 bytes (one `calloc`);
  the rest is glibc + libm + the loader.  The "same as the baseline" conclusion survives (feat and predict
  are both about 2.3 MB), the absolute number does not.
* Nothing in this directory measures recognition accuracy on speech, speaker variation, false-accept
  rates, or segmentation; all correctness evidence is on synthetic signals.

## 8. Steps in this preservation (2026-10-08)

* The original `merge.sh` and `measure_all.sh` referenced `uai32.c`, `uai32.baseline` and `vfe.c` in the
  current directory; they now resolve `vfe.c` next to the script and `uai32.c` / the 9,188-byte
  reference in the frozen release `../../uai32/` (read only), and build into a separate output directory
  (`./build` by default, git-ignored).  `merge.sh` puts `basename OUT` in the generated header comment
  so that the merged `.c` is the same text wherever it is written.  With these changes every preserved
  binary and generated source rebuilt byte-identically (`rebuild_check.log`).
* A first version of my `extra_variants.sh` had a redundant merge-or-build fallback line and
  `rebuild_check.sh` used bash process substitution under `#!/bin/sh`; both were corrected before the
  logged runs.
* The generated `tests/` signals, the `e2e_*` text files and the two 7,856-byte `e2e_*.model` files were
  deliberately not copied: `synth_tests.py DIR` regenerates all of them in `DIR/tests` (about 6 MB) and
  `tests.log` is their complete record.
