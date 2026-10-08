# Pilot byte and memory accounting

All numbers below were produced by `build.sh`, `validate.sh` and `measure.sh` on 2026-10-08 with
gcc 13.3.0 / GNU ld 2.42 / glibc 2.39, x86-64, Intel Xeon 2.10 GHz (4 cores), Linux 6.18; raw outputs are in
`measurements/sizes.txt`, `measurements/rss.txt` and `validation/validate.log`.  Build flags: exactly the
`uai32/Makefile` CFLAGS and LDFLAGS (Linux branch) plus `-Wl,-z,nosectionheader`, which this binutils accepts.
Every build is warning-free under `-Wall -Wextra -pedantic`, and rebuilding gives byte-identical files.

## 1. Executables (`wc -c`)

| file | bytes | SHA-256 |
|---|---:|---|
| `dtwapp` (nosectionheader) | **7,416** | c3cc4fc9a55f259183072a09392c73b35efc36942d9e6978daacbf0317f1674d |
| `dtwapp.elf` (same link, with section headers) | 9,152 | be742b13bc6a8ec63443e9ee1d8457339185e77efd9c79c8947150298b856950 |
| `netapp` (nosectionheader) | **11,500** | 4e575f757b6f5683b24b7cef3db0bfdf2eabfeda64a2cc356b3e513cddaf50b5 |
| `netapp.elf` | 13,304 | abc6684bd958588ac998b10ed3500a43e371799c40da500511c5faa730d4d39d |
| frozen `uai32/uai32`, for reference | 9,188 | 996d73cba9676e8932206b9c80493becde6d04b6a57b70839999b0824c0186cb |

`netapp` is uai32 + 2,312 bytes (the shared front-end block, the `feat` verb and the 6-decimal/margin
predict output).  Sections (`readelf -S` on the .elf twins): dtwapp .text 3,275 .rodata 968 .bss 112;
netapp .text 6,955 .rodata 1,296 .bss 216.  Imports added over uai32: `cosf`, `sincosf` (both), `memmove`
(both), `fread`, `fwrite`, `fflush`, `rewind` (dtwapp only); dtwapp does not need `getline`, `realloc`,
`strtod`, `strtof`.  `build.sh` checks that the RW segment starts 4 bytes after the RX segment ends
(no linker page padding, the trap described in reports/frontend-bytes.md).

## 2. State at the declared capacity (4 commands x 5 examples)

| arm | state | formula | from the formula | real file (`wc -c`) | SHA-256 |
|---|---|---|---:|---:|---|
| DTW | `validation/pilot.state`, 20 templates | 8 + 977 N | 8 + 977 x 20 = **19,548** | 19,548 | f41a140bc93e952776b3a945a3a408bdb958ce485f22bb2e398655f9fa79f264 |
| net | `validation/model4.bin`, 144-16-4 | 8 + 8 NI + 2 (NH (NI+1) + NO (NH+1)) | 8 + 1,152 + 2 (2,320 + 68) = **5,936** | 5,936 | 4515b2931873264a6be77fffca2cb0e9456a9e78206855485c63295ccf7eaba1 |
| net | `validation/model5.bin`, 144-16-5 (class 4 = synthetic unknown) | same | 8 + 1,152 + 2 (2,320 + 85) = **5,970** | 5,970 | 168232c83f5aae7946bb3753ee379622b16e33153a02dbb84d28f685d3fb25ce |

The real files were made by `validate.sh`: `dtwapp enrol` of the 20 enrolment clips (manifest with the
SHA-256 of every raw clip: `validation/clips.txt`, from `tools/select_clips.py` seed 1, words yes/no/stop/go), and
`netapp train validation/train4.txt model4.bin 16 300 0.01 1` (20 rows) and the same on `train5.txt`
(the 20 rows plus 20 time-reversed enrolment clips labelled 4).  Both models are byte-identical to the ones
the frozen `uai32/uai32` produces from the same command (`cmp` in validate.log), which is the proof that
`train` and the model format are unchanged.  Per DTW template: 1 label byte + 61 x 16 uint8 = 977 bytes, so
each additional enrolment costs 977 bytes; the network's state does not grow with examples.  For the DTW
arm, 4 x 5 is a convention, not a limit: 16 labels and 65,535 templates fit the header.

## 3. Complete application + state against 32,768

| arm | executable | state | total | spare |
|---|---:|---:|---:|---:|
| DTW: `dtwapp` + 20 uint8 templates | 7,416 | 19,548 | **26,964** | 5,804 |
| network: `netapp` + 144-16-4 model | 11,500 | 5,936 | **17,436** | 15,332 |
| network: `netapp` + 144-16-5 model (with unknown class) | 11,500 | 5,970 | **17,470** | 15,298 |

Nothing else is needed at run time: no scripts, tables or configuration files; the host only supplies the
1 s clip on stdin and reads one output line.  (The benchmark report's estimate of "front-end ELF + DTW +
uint8 templates = 25,000 for 4 commands" is replaced by the measured 26,964, which includes the state-file
code, input validation and the 8-byte header plus 20 label bytes.)

## 4. Peak RAM

### (a) Measured peak RSS of each verb

`/usr/bin/time` is not installed here and the `time` package is not in this image's apt sources, so
`tools/maxrss.py` runs the verb as a child and prints `ru_maxrss` from `wait4` -- the same kernel counter
that `/usr/bin/time -v` prints as "Maximum resident set size (kbytes)".  Three runs each, kB
(`measurements/rss.txt`):

| command | run 1 | run 2 | run 3 | cpu ms |
|---|---:|---:|---:|---:|
| empty `int main(){return 0;}` built with the same flags | 11,080 | 11,128 | 11,144 | 1.0-1.1 |
| frozen `uai32 predict model4.bin` (60 rows) | 11,120 | 11,060 | 11,160 | 2.6-3.1 |
| `dtwapp info pilot.state` | 11,144 | 11,144 | 11,136 | 1.2 |
| `dtwapp score pilot.state < clip` (20 templates) | 11,092 | 11,092 | 11,148 | 4.9-5.3 |
| `dtwapp enrol copy.state 0 < clip` | 11,164 | 11,108 | 11,120 | 2.0-2.9 |
| `netapp feat 0 < clip` | 11,104 | 11,088 | 11,108 | 2.5-4.0 |
| `netapp train train4.txt m 16 300 0.01 1` (20 rows) | 11,156 | 11,112 | 11,144 | 25.7-26.1 |
| `netapp train train5.txt m 16 300 0.01 1` (40 rows) | 11,124 | 11,132 | 11,144 | 50.6-53.2 |
| `netapp test test4.txt model5.bin` (40 rows) | 11,088 | 11,140 | 11,112 | 2.2-2.7 |
| `netapp predict model5.bin < queries.txt` (60 rows) | 11,140 | 11,092 | 11,132 | 2.9-3.7 |
| `netapp predict model5.bin < one row` | 11,132 | 11,136 | 11,156 | 1.2-1.3 |

Every figure, including the empty program, is 11.06-11.16 MB: the resident set is glibc, the dynamic loader
and their mappings as this kernel accounts them, and the applications' own buffers (10-35 KB, below) are
inside the run-to-run noise of about 100 kB.  Peak RSS therefore says nothing about the microcontroller
case; the number that matters is (b).

### (b) Working set computed from the source

Assumptions: `float` and `int` 4 bytes, `short` 2 bytes, pointers 8 bytes (x86-64; 4 on a 32-bit MCU),
NI = 144, NH = 16, NO = 4 or 5, 20 templates; glibc's stdio buffers (4,096 bytes per open stream here) and
`FILE` structures are listed separately because an MCU port replaces them with direct flash/ADC access;
stack use is a few hundred bytes (locals and printf) and is not itemised.

Shared front-end block, one `calloc` (both apps, every verb that reads a clip):

| buffer | elements | bytes |
|---|---:|---:|
| `buf` sliding sample window (1 + 512 shorts) | 513 | 1,026 (1,028 with padding) |
| `re`, `im` FFT frame | 2 x 512 floats | 4,096 |
| `lm` log-mel matrix | 61 x 16 floats | 3,904 |
| `bin` filter edges | 18 ints | 72 |
| **total** | 2,275 floats | **9,100** |

dtwapp (`D` first, then the record, one `calloc`): DTW row 62 floats 248 + record 977 (padded to 980) =
1,228 bytes; `cmin[16]`/`count[16]` 64 bytes each on the stack.

| verb | application buffers | glibc stdio in this build |
|---|---:|---|
| `dtwapp enrol` | 9,100 + 1,228 = **10,328** (the DTW row is allocated but unused) | stdin 4,096 + state FILE 4,096 |
| `dtwapp score` | 9,100 + 1,228 + 64 = **10,392** | stdin, state FILE, stdout: 3 x 4,096 |
| `dtwapp info` | 1,228 + 64 = **1,292** | state FILE, stdout |

Templates are streamed one record at a time from the state file, so the working set does not grow with the
number of templates (the state lives in flash on an MCU); the sample buffer means the whole 1 s clip
(32,000 bytes) is never held.

netapp: uai32's own allocations are unchanged, and two of them are sized for a desktop, not for the data:
`read_data` starts with room for 256 rows (`X` = 256 x 144 x 4 = 147,456 bytes, `Y` 1,024 bytes) however
few rows arrive, and `getline` grows its buffer to the longest line (about 1,300 bytes for 144 `%.5g`
values).  The table gives the bytes this build allocates and, in the last column, what the same algorithm
needs when allocated exactly (the MCU figure).

| verb | buffers | allocated by this build | needed exactly |
|---|---|---:|---:|
| `netapp feat` | front-end 9,100 + energy `e` 2 x 61 floats 488 | **9,588** | 9,588 |
| `netapp predict` (1 row, NO = 5) | model `P` 2,693 floats 10,772; `xn/hid/dh/z/out` 186 floats 744; `row` 145 floats 580; `X` 147,456 (1 row = 576 used); `Y` 1,024 (4 used); line buffer ~1,300 | **161,876** | 10,772 + 744 + 580 + 576 + 4 = **12,676** |
| `netapp predict` (NO = 4) | `P` 2,676 floats 10,704; `xn` block 184 floats 736; rest as above | 161,800 | **12,600** |
| `netapp train` (20 rows, NO = 4) | `P` 10,704; `xn` block 736; `row` 580; `X` 147,456 (11,520 used); `Y` 1,024 (80 used); `idx` 80; line buffer ~1,300 | **161,880** | 10,704 + 736 + 580 + 11,520 + 80 + 80 = **23,700** |
| `netapp train` (40 rows, NO = 5) | `P` 10,772; `xn` 744; `X` 23,040 used; `Y` 160 used; `idx` 160 | 162,036 | **35,456** |
| `netapp test` (40 rows, NO = 5) | as train without `idx` | 161,876 | 35,296 |

(The 147,456-byte `X` is `realloc`ed but mostly untouched, which is why it does not show in RSS: untouched
pages are never resident.)  For the pilot, then: the DTW arm runs in about **10.4 KB** of application RAM
plus the 19.5 KB state in flash; the network arm needs about **9.6 KB** to extract features, **12.7 KB** to
recognise, and **24-36 KB** to train from 20-40 stored feature rows (the stored rows themselves, 576 bytes
each, are state the device must keep if it is to retrain after a fourth command is added, which uai32's
fixed NO otherwise prevents -- see reports/fewshot-accuracy.md).

## 5. Speed (same runs, wall clock of the whole process including start-up)

`dtwapp score` 5.4-6.0 ms for 20 templates (61 x 61 x 16 cells each); `netapp feat` 2.8-4.2 ms;
`netapp train` 300 epochs on 20 rows 26 ms, on 40 rows 51-55 ms; `netapp predict` 60 rows 3-4 ms.

## 6. Pilot-mode re-measurement (`measure.sh --pilot RUNDIR MANIFEST`, 2026-10-08)

The same measurements on exactly the states `run_pilot.py` tested, written to `RUNDIR/measurements/`; the dry run's copy is
`dryrun/measurements/` (stand-in clips, see DRYRUN.md).  Bytes are the same files as above by construction: state A
8 + 977 x 15 = 14,663 (3 commands), state B 19,548 (4 commands), model A 5,936 (3 commands + unknown), model B 5,970
(4 commands + unknown), totals 26,964 and 17,470.  Peak RSS of every verb stayed at the glibc floor (11.11-11.24 MB, empty
program 11.13-11.22 MB).  What differs from the validation run is only CPU time: `netapp train` on the pilot's augmented
training sets takes 83-98 ms (774 rows, 20 epochs, model A) and 104-118 ms (1,033 rows, model B) against 26-53 ms on the
validation's 20-40 rows; `dtwapp score` 4.7-5.6 ms with 20 templates; `netapp predict` of 580 rows 16-17 ms.
