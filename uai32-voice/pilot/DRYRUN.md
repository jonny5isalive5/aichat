# DRY RUN of the pilot kit on speaker-INDEPENDENT stand-in clips

> **THESE ARE NOT PILOT RESULTS.**  Every clip below comes from Google mini_speech_commands: the "enrolled speaker" is
> 20 different crowd-sourced speakers, and every dev/test clip is from a speaker absent from enrolment, through unknown
> microphones.  The "own-voice confusables" are the words up/down and the "unrelated" words are left/right, chosen only
> so that every stratum of the report is exercised.  The numbers prove that record.py, run_pilot.py and measure.sh run
> end to end, refuse what they must refuse, and produce the report in the pre-registered shape.  They say nothing about
> an enrolled speaker on one microphone, which is what the pilot will measure.  Do not quote them as pilot results.

Produced by `tools/dryrun.sh` on 2026-10-08T07:53:48Z in 85 s (run_pilot.py all: 75 s) on x86_64, cc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, Python 3.13.16, numpy 2.5.3.

## Exact commands

```sh
cd uai32-voice/pilot && ./build.sh && sha256sum -c SHA256SUMS       # dtwapp c3cc4fc9..., netapp 4e575f75...
tools/dryrun.sh /path/mini_speech_commands.zip /scratch/pilot-dryrun   # zip sha256 49650f2341b26d886b46b3f4fb8fed59e30300b17550f1ee4a768b3106cf93a0
# which runs, in order:
python3 -I tools/standin_captures.py ZIP /scratch/pilot-dryrun/data 7            # sealed manifest + 580 stand-in 1.5 s captures
python3 -I record.py import /scratch/pilot-dryrun/data/manifest.json --from /scratch/pilot-dryrun/data/incoming
python3 -I run_pilot.py all /scratch/pilot-dryrun/data/manifest.json /scratch/pilot-dryrun/run --seed 1
./measure.sh --pilot /scratch/pilot-dryrun/run /scratch/pilot-dryrun/data/manifest.json
```

Everything is seeded: a repeat gives byte-identical clips, states, models and decisions (the SHA-256 values below); only the
manifest creation timestamp, hence its seal, and the freeze timestamp in thresholds.json differ between repeats.
Stand-in data: `dryrun/standin_sources.txt` lists every clip (id, phase, word, zip member, offset of the 1 s clip inside the
1.5 s capture, SHA-256 of the member); `dryrun/manifest.json.gz` + `SEALED.sha256` is the sealed manifest,
`dryrun/recordings.json.gz` the per-clip centring log (centre sample, active region, peak, QA warnings).

## What the dry run exercised

- `record.py`: `init` (a second, realistically pre-registered manifest: 4 commands, 12 confusables, 20 unrelated words),
  `status`, `import` of 580 hand-style WAV captures with the host-side centring and QA warnings, `centre`, the `manual`
  backend instructions, the refusals (missing arecord/sox when forced, unknown phase, existing manifest, 3 commands,
  edited manifest against its seal).  NOT exercised: the live `sounddevice`, `arecord` and `sox` capture paths (no
  audio device, module or tool in this container; see FAILURES.md).
- `run_pilot.py`: `dev` (P1, dev scoring, DET CSVs, freeze), `test` (P2 twice with features re-extracted, P3, P4,
  untrained / 5 constrained / 20 unconstrained permutation controls, strace, report), then the one-shot refusal and
  the changed-recipe refusal.
- `measure.sh --pilot`: bytes of exactly the tested states and peak RSS of every verb.

```
## record.py status (before import)
enrol    0/ 20 recorded (0 positives, 0 negatives), 0 with QA warnings
dev      0/140 recorded (0 positives, 0 negatives), 0 with QA warnings
test     0/420 recorded (0 positives, 0 negatives), 0 with QA warnings
speaker standin-speaker-independent, seed 7, commands ['yes', 'no', 'stop', 'go'], held back: go
## record.py import (host-side centring of every stand-in capture; QA warnings are expected on crowd-sourced clips)
imported 580 captures; 0 items still without a capture
## record.py status (after import)
enrol   20/ 20 recorded (20 positives, 0 negatives), 10 with QA warnings
dev    140/140 recorded (40 positives, 100 negatives), 47 with QA warnings
test   420/420 recorded (120 positives, 300 negatives), 161 with QA warnings
speaker standin-speaker-independent, seed 7, commands ['yes', 'no', 'stop', 'go'], held back: go
## record.py centre on one stand-in capture
{"centre_sample": 9760, "active_first_ms": 370, "active_last_ms": 850, "active_ms": 480, "peak_dbfs": -1.1, "floor_db": -100.0, "peak_db": -8.5, "edge": false, "window_start_sample": 1760, "padded_samples": 0}
32000
## record.py init of a second, pre-registered manifest (the real pilot's shape) and the manual-recording instructions
sealed manifest /tmp/claude-0/-home-user-aichat/809e473e-6ead-51f0-b725-4e01dff2b821/scratchpad/pilot-dryrun3/rec-smoke/manifest.json: speaker spk01, seed 11, 580 items (enrol 20, dev 140, test 420); sha256 241e0641e369d0f7ab166a76a91073ece8598d9b10d42be802c900fb8ab983ad
commands ['stop', 'go', 'left', 'right'] (the 4th, 'right', is held back until the fourth-command step); confusables ['top', 'shop', 'stock', 'no', 'so', 'goat', 'lift', 'let', 'laughed', 'write', 'light', 'ride']; unrelated ['apple', 'window', 'seven', 'coffee', 'river', 'paper', 'yellow', 'music', 'table', 'garden', 'pencil', 'orange', 'summer', 'bottle', 'jacket', 'silver', 'candle', 'button', 'ladder', 'rocket']
phase enrol: 20 items, 0 recorded, 20 to do
backend: manual 
No capture backend (python module sounddevice, arecord, sox/rec) is available.  Record by hand:
  1. For each id below, record ONE 1.5 s WAV: 16,000 Hz, mono, 16-bit PCM, named incoming/<id>.wav under /tmp/claude-0/-home-user-aichat/809e473e-6ead-51f0-b725-4e01dff2b821/scratchpad/pilot-dryrun3/rec-smoke
     e.g.  arecord -f S16_LE -r 16000 -c 1 -d 2 incoming/<id>.wav   (any length >= 1.5 s is accepted; only the
     first 1.5 s is used).  Same microphone, same room, same distance, AGC/noise suppression OFF for every clip.
  2. Prompt yourself in EXACTLY this order and say only the word shown, once, after a beep or count-in:
     942996130a22  STOP
     07f25754c12c  RIGHT
     ... (20 prompts)
## error paths (each must refuse)
arecord is not installed: use --backend auto (picks what exists) or manual
sox is not installed: use --backend auto (picks what exists) or manual
PHASE is one of enrol, dev, test
/tmp/claude-0/-home-user-aichat/809e473e-6ead-51f0-b725-4e01dff2b821/scratchpad/pilot-dryrun3/rec-smoke/manifest.json exists; a sealed manifest is never overwritten (choose another directory)
exactly 4 commands: three enrolled first and the fourth held back
manifest hash f818076b6b74deb2 does not match SEALED.sha256 241e0641e369d0f7: the label manifest was edited after sealing
## one-shot rule: a second test stage on the same directory must be refused
the test stage already ran on /tmp/claude-0/-home-user-aichat/809e473e-6ead-51f0-b725-4e01dff2b821/scratchpad/pilot-dryrun3/run at 2026-10-08T07:52:36Z: the one-shot rule forbids a second run (--force-rerun labels it POST-HOC)
## recipe change after the freeze must be refused
seed=2 differs from the frozen recipe 1
```

## The report run_pilot.py wrote (dryrun/.. holds the inputs it cites)

# [DRY RUN, speaker-independent stand-ins] Pilot results: speaker standin-speaker-independent, 2026-10-08T07:53:45Z

Manifest seal 819cc21ef7dc325b; dtwapp c3cc4fc9a55f2591; netapp 4e575f757b6f5683; thresholds frozen 2026-10-08T07:52:34Z (dev decisions sha256 5fafd2db6c8811ea).  Recipe: DTW score margin; network 16 hidden, 20 epochs, rate 0.01, 30 augmented copies, seed 1, score prob; target dev false-accept rate 1.0%.
Commands: 0=yes, 1=no, 2=stop, 3=go; held back until P3: go.  Every rate is k/n with the exact two-sided 95% Clopper-Pearson interval.

## 1. Bytes: complete application plus required state (`wc -c`)

| arm | executable | state A (3 commands) | state B (4 commands, declared capacity) | application + state B | spare under 32,768 |
|---|---:|---:|---:|---:|---:|
| DTW | 7416 | 14663 (sha256 5c93f6a95f63) | 19548 (359660e865ae) | **26964** | 5804 |
| network | 11500 | 5936 (4d83f381eb2c) | 5970 (329fd6bc8214) | **17470** | 15298 |

The network was retrained for the 4th command from retained enrolment data (disclosed): the 20 enrolment rows are 24592 bytes as `netapp feat` text (11520 as float32), the 20 raw clips 640000 bytes; neither is inside the model file.  Peak RSS: `measure.sh --pilot OUTDIR` (see SIZES.md section 4 for why RSS is glibc-dominated).

Network training set A: 774 rows = 15 enrolment + 450 augmented + 232 synthetic-unknown waveforms + 77 segment-shuffled rows; new model: 144 inputs, 16 hidden, 4 classes, 2676 parameters; epoch 20/20  train loss 0.0873  accuracy 762/774 = 98.4%.

Network training set B: 1033 rows = 20 enrolment + 600 augmented + 310 synthetic-unknown waveforms + 103 segment-shuffled rows; new model: 144 inputs, 16 hidden, 5 classes, 2693 parameters; epoch 20/20  train loss 0.0924  accuracy 1016/1033 = 98.4%.

## 2. Development phase (thresholds chosen here, then frozen)

| arm | score | frozen threshold | dev false accepts | dev recall (commands 1-3) | per command | dev closed-set (ignoring the threshold) | held-back command accepted |
|---|---|---:|---|---|---|---|---|
| DTW (`dtwapp`) | margin | 0.530625 | 1.0% [0.0%, 5.4%] | 6.7% [0.8%, 22.1%] | yes 1/10, no 0/10, stop 1/10 | 27/30 | 0/10 |
| network (`netapp`) | prob | 0.995762 | 1.0% [0.0%, 5.4%] | 3.3% [0.1%, 17.2%] | yes 1/10, no 0/10, stop 0/10 | 17/30 | 0/10 |

Dev DET curves (every unique score as a threshold; false-accept rate on the dev negatives, recall on the dev positives): `dev_det_dtw_margin.csv`, `dev_det_dtw_min.csv`, `dev_det_net_prob.csv`, `dev_det_net_margin.csv`.  Recall at dev false-accept rates <= 0 / 1 / 2 / 5 / 10%:

- dtw / margin (frozen): 2/30 / 2/30 / 3/30 / 14/30 / 18/30
- dtw / min: 7/30 / 8/30 / 8/30 / 10/30 / 16/30
- net / prob (frozen): 0/30 / 1/30 / 2/30 / 2/30 / 3/30
- net / margin: 0/30 / 0/30 / 1/30 / 2/30 / 3/30

## 3. Test with state A (commands 1-3), P2: the pre-registered one-shot result

### Recall per command (decision = the enrolled command; a substitution or a REJECT is an error)

| command | DTW correct k/n [95% CI] | DTW closed-set | DTW substituted / rejected | network correct k/n [95% CI] | network closed-set | network substituted / rejected |
|---|---|---|---|---|---|---|
| yes | 9/30 30.0% [14.7%, 49.4%] | 30/30 | 0 / 21 | 3/30 10.0% [2.1%, 26.5%] | 26/30 | 0 / 27 |
| no | 2/30 6.7% [0.8%, 22.1%] | 28/30 | 0 / 28 | 0/30 0.0% [0.0%, 11.6%] | 24/30 | 0 / 30 |
| stop | 5/30 16.7% [5.6%, 34.7%] | 28/30 | 1 / 24 | 0/30 0.0% [0.0%, 11.6%] | 14/30 | 0 / 30 |
| **pooled** | 16/90 17.8% [10.5%, 27.3%] | 86/90 | 1 / 73 | 3/90 3.3% [0.7%, 9.4%] | 64/90 | 0 / 87 |

### False accepts on the own-voice negatives (measured rate and demonstrated bound are different quantities)

| arm | stratum | accepts k/n | measured false-accept rate: point estimate [95% CI] | bound demonstrated: one-sided 95% upper limit | n needed for the bound to reach 1%: at this count / at this rate |
|---|---|---|---|---|---|
| DTW (`dtwapp`) | confusable | 2/180 | 1.1% [0.1%, 4.0%] | 3.5% | 628 / never (rate >= 1%) |
| DTW (`dtwapp`) | unrelated | 1/120 | 0.8% [0.0%, 4.6%] | 3.9% | 473 / 10390 |
| DTW (`dtwapp`) | all own-voice negatives | 3/300 | 1.0% [0.2%, 2.9%] | 2.6% | 773 / never (rate >= 1%) |
| network (`netapp`) | confusable | 9/180 | 5.0% [2.3%, 9.3%] | 8.6% | 1568 / never (rate >= 1%) |
| network (`netapp`) | unrelated | 0/120 | 0.0% [0.0%, 3.0%] | 2.5% | 299 / 299 |
| network (`netapp`) | all own-voice negatives | 9/300 | 3.0% [1.4%, 5.6%] | 5.2% | 1568 / never (rate >= 1%) |

The held-back command 'go' as unfamiliar speech at P2 (extra stratum, not pooled above): DTW accepted 0/30, network accepted 0/30.

### Restart test (P2 run twice: fresh processes loading only the saved state)

- DTW (`dtwapp`): raw outputs of the two runs (score line per clip) **byte-identical** (sha256 1b43be863dca21de); state file unchanged by scoring.
- network (`netapp`): raw outputs of the two runs (predict line plus the sha256 of the feat row per clip, features re-extracted in run 2) **byte-identical** (sha256 633f8b7a74b4e26f); state file unchanged by scoring.

## 4. Test with state B (all 4 commands), P4

### Recall per command (decision = the enrolled command; a substitution or a REJECT is an error)

| command | DTW correct k/n [95% CI] | DTW closed-set | DTW substituted / rejected | network correct k/n [95% CI] | network closed-set | network substituted / rejected |
|---|---|---|---|---|---|---|
| yes | 9/30 30.0% [14.7%, 49.4%] | 30/30 | 0 / 21 | 1/30 3.3% [0.1%, 17.2%] | 22/30 | 0 / 29 |
| no | 0/30 0.0% [0.0%, 11.6%] | 12/30 | 0 / 30 | 0/30 0.0% [0.0%, 11.6%] | 7/30 | 2 / 28 |
| stop | 1/30 3.3% [0.1%, 17.2%] | 25/30 | 1 / 28 | 1/30 3.3% [0.1%, 17.2%] | 15/30 | 0 / 29 |
| go | 0/30 0.0% [0.0%, 11.6%] | 21/30 | 0 / 30 | 0/30 0.0% [0.0%, 11.6%] | 17/30 | 0 / 30 |
| **pooled** | 10/120 8.3% [4.1%, 14.8%] | 88/120 | 1 / 109 | 2/120 1.7% [0.2%, 5.9%] | 61/120 | 2 / 116 |

### False accepts on the own-voice negatives (measured rate and demonstrated bound are different quantities)

| arm | stratum | accepts k/n | measured false-accept rate: point estimate [95% CI] | bound demonstrated: one-sided 95% upper limit | n needed for the bound to reach 1%: at this count / at this rate |
|---|---|---|---|---|---|
| DTW (`dtwapp`) | confusable | 1/180 | 0.6% [0.0%, 3.1%] | 2.6% | 473 / 1693 |
| DTW (`dtwapp`) | unrelated | 0/120 | 0.0% [0.0%, 3.0%] | 2.5% | 299 / 299 |
| DTW (`dtwapp`) | all own-voice negatives | 1/300 | 0.3% [0.0%, 1.8%] | 1.6% | 473 / 773 |
| network (`netapp`) | confusable | 3/180 | 1.7% [0.3%, 4.8%] | 4.3% | 773 / never (rate >= 1%) |
| network (`netapp`) | unrelated | 2/120 | 1.7% [0.2%, 5.9%] | 5.2% | 628 / never (rate >= 1%) |
| network (`netapp`) | all own-voice negatives | 5/300 | 1.7% [0.5%, 3.8%] | 3.5% | 1049 / never (rate >= 1%) |

### Forgetting on the 90 original test clips of commands 1-3 (P2 -> P4)

| arm | errors before | errors after | became wrong | became right | net change | exact McNemar one-sided p (more became wrong) |
|---|---:|---:|---:|---:|---:|---:|
| DTW (`dtwapp`) | 74 | 80 | 6 | 0 | +6 | 0.016 |
| network (`netapp`) | 87 | 88 | 3 | 2 | +1 | 0.500 |

## 5. Controls (same clips, same frozen thresholds)

Chance for 90 positives at 1/3 is 33.3%; the 99.9th percentile of chance is 45/90 (a learner that ignores labels should stay at or below it).

| control | DTW accuracy | DTW closed-set | DTW false accepts | network accuracy | network closed-set | network false accepts |
|---|---|---|---|---|---|---|
| untrained (no state / 0 epochs) | 0/90 | 0/90 | 0/300 | 0/90 | 34/90 | 0/300 |
| constrained permutation seed 0 (labels 112002122110020) | 1/90 | 13/90 | 1/300 | 2/90 | 31/90 | 11/300 |
| constrained permutation seed 1 (labels 220011022102110) | 1/90 | 26/90 | 1/300 | 0/90 | 24/90 | 8/300 |
| constrained permutation seed 2 (labels 120210020201121) | 0/90 | 12/90 | 1/300 | 1/90 | 27/90 | 10/300 |
| constrained permutation seed 3 (labels 221002012110102) | 1/90 | 21/90 | 2/300 | 0/90 | 19/90 | 3/300 |
| constrained permutation seed 4 (labels 212001202210011) | 1/90 | 33/90 | 1/300 | 3/90 | 30/90 | 12/300 |

20 unconstrained example-level permutations of the 15 enrolment labels (reported, not gated; permutation p = (1 + #{permuted accuracy >= observed}) / 21):

| arm | accuracy under permutation, min / median / max of 90 | closed-set, min / median / max | false accepts, min / median / max of 300 | observed P2 accuracy | permutation p |
|---|---|---|---|---|---:|
| DTW (`dtwapp`) | 0 / 0 / 1 | 2 / 28 / 61 | 1 / 1 / 2 | 16 | 0.048 |
| network (`netapp`) | 0 / 1 / 4 | 10 / 30 / 64 | 3 / 8 / 10 | 3 | 0.190 |

"Closed-set" = the label of the best class ignoring the threshold; "accuracy" applies the frozen threshold.  The untrained DTW rejects everything by construction (no templates), which is why the recall and false-accept gates are both needed.

## 6. DTW versus network, paired on identical clips (exact McNemar)

- P2: DTW 16/90 correct, network 3/90 correct; DTW-only correct 15, network-only correct 2, two-sided p = 0.002.
- P4: DTW 10/120 correct, network 2/120 correct; DTW-only correct 9, network-only correct 1, two-sided p = 0.021.

## 7. Disclosures

- Host-side segmentation: the recorder centres each 1.0 s clip on the energy centre of the 1.5 s capture (record.py, logged per clip in recordings.json).  Isolated utterances only; segmentation of a longer stream is a deferred experiment.
- The network arm's augmentation and synthetic unknown class are computed in numpy on the host from the enrolment audio only, then fed through `netapp feat`; the model is retrained from scratch for the 4th command (continual learning deferred).
- The DTW arm never sees a label other than at `enrol`; the network sees labels only in its training rows.  Thresholds were frozen before the test clips were scored (thresholds.json).
- strace (one dtw decision in an empty directory) opened: /etc/ld.so.cache, PILOT/dtwapp, /lib/x86_64-linux-gnu/libc.so.6, /lib/x86_64-linux-gnu/libm.so.6, OUTDIR/stateB.dtw.
- strace (one net decision in an empty directory) opened: /etc/ld.so.cache, PILOT/netapp, /lib/x86_64-linux-gnu/libc.so.6, /lib/x86_64-linux-gnu/libm.so.6, OUTDIR/modelB.bin.
- Raw decision table: `decisions.csv` (stage x arm x clip); states and models: `stateA.dtw`, `stateB.dtw`, `modelA.bin`, `modelB.bin`; machine-readable numbers: `summary.json`; the run log: `log.txt`.

## Fresh measurements (`measure.sh --pilot`, dryrun/measurements/)

```
# measure.sh 2026-10-08T07:53:46Z, x86_64, cc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0, mode pilot
# wc -c of every file that counts
 7416 dtwapp
 9152 dtwapp.elf
11500 netapp
13304 netapp.elf
14663 stateA.dtw
19548 stateB.dtw
 5936 modelA.bin
 5970 modelB.bin
 9188 ../../uai32/uai32
96677 total
# formulas
dtw state = 8 + 977 * N: N = 20 -> 19548 (real file: 19548)
model = 8 + 8*NI + 2*(NH*(NI+1) + NO*(NH+1)): NI=144 NH=16 NO=4 -> 5936 (real file, model A: 3 commands + unknown, NO=4: 5936); NO=5 -> 5970 (real file, model B: 4 commands + unknown, NO=5, declared capacity: 5970)
# totals against 32768
dtwapp + state(20) = 7416 + 19548 = 26964; spare 5804
netapp + model(model A: 3 commands + unknown, NO=4) = 11500 + 5936 = 17436; spare 15332
netapp + model(model B: 4 commands + unknown, NO=5, declared capacity) = 11500 + 5970 = 17470; spare 15298
retained for retraining the network (host side, disclosed, not in the model): enrolment rows 24592 bytes as feat text, 11520 as float32
# sections (readelf -S on the .elf twins)
dtwapp: .init=0x00001b .text=0x000ccb .fini=0x00000d .rodata=0x0003c8 .eh_frame=0x000044 .init_array=0x000008 .fini_array=0x000008 .dynamic=0x0001c0 .got=0x0000c0 .got.plt=0x000018 .bss=0x000070 .comment=0x00002d .shstrtab=0x0000d5 
netapp: .init=0x00001b .text=0x001b2b .fini=0x00000d .rodata=0x000510 .eh_frame=0x000044 .init_array=0x000008 .fini_array=0x000008 .dynamic=0x0001c0 .got=0x0000c8 .got.plt=0x000018 .data=0x000004 .bss=0x0000d8 .comment=0x00002d .shstrtab=0x0000db 
# libc/libm imports (nm -D --undefined-only)
dtwapp: __errno_location __gmon_start__ __libc_start_main calloc cosf exit expf fclose fflush fopen fprintf fread fseek ftell fwrite getc logf memmove printf putc rewind sincosf strcmp strtoul 
netapp: __errno_location __gmon_start__ __libc_start_main calloc cosf exit expf fclose fopen fprintf fseek ftell getc getline logf memmove printf putc puts realloc sincosf strcmp strtod strtof strtoul 
# sha256
c3cc4fc9a55f259183072a09392c73b35efc36942d9e6978daacbf0317f1674d  dtwapp
4e575f757b6f5683b24b7cef3db0bfdf2eabfeda64a2cc356b3e513cddaf50b5  netapp
5c93f6a95f63b1f34c73c624d45fc925e44553dedacb9b3ca7cac40f065595ad  stateA.dtw
359660e865ae02d59443e4c49f3ee5608a4ca67057d834f75fd06ec364717570  stateB.dtw
4d83f381eb2c58d5459be1219e2899773a367ae7eb8ae0252e129e073750c941  modelA.bin
329fd6bc8214c3aa296b544f945afc69eb7ba13edea5171fd40b63ec3442fb4a  modelB.bin

# measure.sh 2026-10-08T07:53:46Z: ru_maxrss (kB) of each child process via wait4, 3 runs each; cpu = user+system; clip = clips_first_enrol.raw
maxrss_kb=11220 cpu_ms=1.4 wall_ms=1.7 exit=0 cmd=measure_work/nop
maxrss_kb=11220 cpu_ms=20.1 wall_ms=20.4 exit=0 cmd=../../uai32/uai32 predict modelA.bin
maxrss_kb=11192 cpu_ms=1.4 wall_ms=1.7 exit=0 cmd=dtwapp info stateB.dtw
maxrss_kb=11188 cpu_ms=5.6 wall_ms=7.1 exit=0 cmd=dtwapp score stateB.dtw
maxrss_kb=11116 cpu_ms=2.4 wall_ms=2.7 exit=0 cmd=dtwapp enrol measure_work/enrol.state 0
maxrss_kb=11192 cpu_ms=2.8 wall_ms=3.1 exit=0 cmd=netapp feat 0
maxrss_kb=11144 cpu_ms=83.4 wall_ms=83.8 exit=0 cmd=netapp train trainsets/A_rows.txt measure_work/m4.bin 16 20 0.01 1
maxrss_kb=11116 cpu_ms=103.6 wall_ms=104.0 exit=0 cmd=netapp train trainsets/B_rows.txt measure_work/m5.bin 16 20 0.01 1
maxrss_kb=11116 cpu_ms=2.0 wall_ms=2.2 exit=0 cmd=netapp test enrol_rows_B.txt modelB.bin
maxrss_kb=11144 cpu_ms=16.4 wall_ms=16.7 exit=0 cmd=netapp predict modelB.bin
maxrss_kb=11212 cpu_ms=1.4 wall_ms=1.6 exit=0 cmd=netapp predict modelB.bin
maxrss_kb=11184 cpu_ms=1.0 wall_ms=1.2 exit=0 cmd=measure_work/nop
maxrss_kb=11136 cpu_ms=17.2 wall_ms=17.4 exit=0 cmd=../../uai32/uai32 predict modelA.bin
maxrss_kb=11236 cpu_ms=1.2 wall_ms=1.5 exit=0 cmd=dtwapp info stateB.dtw
maxrss_kb=11232 cpu_ms=4.7 wall_ms=5.0 exit=0 cmd=dtwapp score stateB.dtw
maxrss_kb=11148 cpu_ms=2.8 wall_ms=3.0 exit=0 cmd=dtwapp enrol measure_work/enrol.state 0
maxrss_kb=11232 cpu_ms=2.7 wall_ms=2.9 exit=0 cmd=netapp feat 0
maxrss_kb=11108 cpu_ms=97.5 wall_ms=98.4 exit=0 cmd=netapp train trainsets/A_rows.txt measure_work/m4.bin 16 20 0.01 1
maxrss_kb=11212 cpu_ms=117.8 wall_ms=121.7 exit=0 cmd=netapp train trainsets/B_rows.txt measure_work/m5.bin 16 20 0.01 1
maxrss_kb=11236 cpu_ms=2.1 wall_ms=2.5 exit=0 cmd=netapp test enrol_rows_B.txt modelB.bin
maxrss_kb=11232 cpu_ms=16.0 wall_ms=16.3 exit=0 cmd=netapp predict modelB.bin
maxrss_kb=11192 cpu_ms=1.4 wall_ms=1.5 exit=0 cmd=netapp predict modelB.bin
maxrss_kb=11128 cpu_ms=1.1 wall_ms=1.3 exit=0 cmd=measure_work/nop
maxrss_kb=11232 cpu_ms=16.8 wall_ms=17.5 exit=0 cmd=../../uai32/uai32 predict modelA.bin
maxrss_kb=11116 cpu_ms=1.3 wall_ms=1.5 exit=0 cmd=dtwapp info stateB.dtw
maxrss_kb=11152 cpu_ms=5.2 wall_ms=5.4 exit=0 cmd=dtwapp score stateB.dtw
maxrss_kb=11192 cpu_ms=2.4 wall_ms=2.7 exit=0 cmd=dtwapp enrol measure_work/enrol.state 0
maxrss_kb=11136 cpu_ms=2.8 wall_ms=3.0 exit=0 cmd=netapp feat 0
maxrss_kb=11188 cpu_ms=89.6 wall_ms=90.7 exit=0 cmd=netapp train trainsets/A_rows.txt measure_work/m4.bin 16 20 0.01 1
maxrss_kb=11128 cpu_ms=111.1 wall_ms=112.8 exit=0 cmd=netapp train trainsets/B_rows.txt measure_work/m5.bin 16 20 0.01 1
maxrss_kb=11128 cpu_ms=1.8 wall_ms=2.0 exit=0 cmd=netapp test enrol_rows_B.txt modelB.bin
maxrss_kb=11132 cpu_ms=16.9 wall_ms=28.3 exit=0 cmd=netapp predict modelB.bin
maxrss_kb=11184 cpu_ms=1.3 wall_ms=1.5 exit=0 cmd=netapp predict modelB.bin
```

## Run log of run_pilot.py (dryrun/run_all.log)

```
# run_pilot.py dev 2026-10-08T07:52:31Z  argv: all SCRATCH/data/manifest.json SCRATCH/run --seed 1
clips: 580 verified against recordings.json (32,000 bytes each, sha256 equal)
executables: dtwapp c3cc4fc9a55f2591 (7416 bytes), netapp 4e575f757b6f5683 (11500 bytes); manifest seal 819cc21ef7dc325b; speaker standin-speaker-independent; commands ['yes', 'no', 'stop', 'go'] (held back: go)

== P1: enrol commands 1-3 from 15 clips (yes, no, stop) ==
dtwapp: state A 14663 bytes, sha256 5c93f6a95f63b1f3 (0.06 s); info: templates 15, file bytes 14663 = 8 + 977 * 15, per label: 0:5 1:5 2:5
training set A: 15 enrol + 450 augmented + 232 synthetic waveforms + 77 segment-shuffled rows = 774 rows (2.8 s)
netapp: model A 5936 bytes, sha256 4d83f381eb2c58d5 (0.11 s): new model: 144 inputs, 16 hidden, 4 classes, 2676 parameters; epoch 20/20  train loss 0.0873  accuracy 762/774 = 98.4%

== dev phase: 30 positives (commands 1-3), 100 own-voice negatives, 10 clips of the held-back command (go) ==
dtw/margin DET on dev: recall at FA <=0%: 2/30, <=1%: 2/30, <=2%: 3/30, <=5%: 14/30, <=10%: 18/30  (dev_det_dtw_margin.csv)
dtw/min DET on dev: recall at FA <=0%: 7/30, <=1%: 8/30, <=2%: 8/30, <=5%: 10/30, <=10%: 16/30  (dev_det_dtw_min.csv)
dtw: FROZEN threshold 0.530625 on score margin -> dev false accepts 1/100, dev recall 2/30 (yes 1/10, no 0/10, stop 1/10), held-back command accepted 0/10
net/prob DET on dev: recall at FA <=0%: 0/30, <=1%: 1/30, <=2%: 2/30, <=5%: 2/30, <=10%: 3/30  (dev_det_net_prob.csv)
net/margin DET on dev: recall at FA <=0%: 0/30, <=1%: 0/30, <=2%: 1/30, <=5%: 2/30, <=10%: 3/30  (dev_det_net_margin.csv)
net: FROZEN threshold 0.995762 on score prob -> dev false accepts 1/100, dev recall 1/30 (yes 1/10, no 0/10, stop 0/10), held-back command accepted 0/10
thresholds frozen in OUTDIR/thresholds.json (sha256 91ee4de76e66d329)
# run_pilot.py test 2026-10-08T07:52:36Z  argv: all SCRATCH/data/manifest.json SCRATCH/run --seed 1
clips: 580 verified against recordings.json (32,000 bytes each, sha256 equal)
executables: dtwapp c3cc4fc9a55f2591 (7416 bytes), netapp 4e575f757b6f5683 (11500 bytes); manifest seal 819cc21ef7dc325b; speaker standin-speaker-independent; commands ['yes', 'no', 'stop', 'go'] (held back: go)

== TEST (one shot): thresholds dtw 0.530625 (margin), net 0.995762 (prob) frozen 2026-10-08T07:52:34Z ==

== P2: state A on 90 positives (commands 1-3), 300 negatives, 30 clips of the held-back 'go'; run twice ==
dtw P2 run 1: 420 decisions in 2.2 s (one fresh process per clip), raw output sha256 1b43be863dca21de
dtw P2 run 2: 420 decisions in 2.2 s (one fresh process per clip), raw output sha256 1b43be863dca21de
dtw restart test: outputs byte-identical, state unchanged
net P2 run 1: 420 decisions in 1.5 s (feat in one fresh process per clip, predict in one), raw output sha256 633f8b7a74b4e26f
net P2 run 2: 420 decisions in 1.6 s (feat in one fresh process per clip, re-extracted, predict in one), raw output sha256 633f8b7a74b4e26f
net restart test: outputs byte-identical, state unchanged

== P3: enrol the 4th command 'go' from 5 clips (fresh process from state A) ==
dtwapp: state B 19548 bytes, sha256 359660e865ae02d5; templates 20, file bytes 19548 = 8 + 977 * 20, per label: 0:5 1:5 2:5 3:5
training set B: 20 enrol + 600 augmented + 310 synthetic waveforms + 103 segment-shuffled rows = 1033 rows (3.6 s)
netapp: model B 5970 bytes, sha256 329fd6bc8214c3aa (retrained from the retained enrolment audio, capacity 4 commands + unknown): new model: 144 inputs, 16 hidden, 5 classes, 2693 parameters; epoch 20/20  train loss 0.0924  accuracy 1016/1033 = 98.4%

== P4: state B on 120 positives (4 commands) and 300 negatives ==
dtw P4: 420 decisions in 2.4 s
net P4: 420 decisions in 0.0 s

== controls (H5) ==
untrained network: 0 epochs on the P1 rows (new model: 144 inputs, 16 hidden, 4 classes, 2676 parameters), 5936 bytes
untrained dtw: accuracy 0/90, closed-set (label of the best, ignoring the threshold) 0/90, false accepts 0/300
untrained net: accuracy 0/90, closed-set (label of the best, ignoring the threshold) 34/90, false accepts 0/300
constrained permutation 0 (112002122110020, 14 draws): dtw accuracy 1/90 closed 13/90 FA 1/300; net accuracy 2/90 closed 31/90 FA 11/300
constrained permutation 1 (220011022102110, 44 draws): dtw accuracy 1/90 closed 26/90 FA 1/300; net accuracy 0/90 closed 24/90 FA 8/300
constrained permutation 2 (120210020201121, 30 draws): dtw accuracy 0/90 closed 12/90 FA 1/300; net accuracy 1/90 closed 27/90 FA 10/300
constrained permutation 3 (221002012110102, 46 draws): dtw accuracy 1/90 closed 21/90 FA 2/300; net accuracy 0/90 closed 19/90 FA 3/300
constrained permutation 4 (212001202210011, 13 draws): dtw accuracy 1/90 closed 33/90 FA 1/300; net accuracy 3/90 closed 30/90 FA 12/300
unconstrained permutation 0 (010100202211212, 1 draws): dtw accuracy 1/90 closed 2/90 FA 1/300; net accuracy 0/90 closed 10/90 FA 8/300
unconstrained permutation 1 (020201121102012, 1 draws): dtw accuracy 0/90 closed 39/90 FA 1/300; net accuracy 1/90 closed 29/90 FA 9/300
unconstrained permutation 2 (221021010101202, 1 draws): dtw accuracy 0/90 closed 58/90 FA 1/300; net accuracy 0/90 closed 26/90 FA 6/300
unconstrained permutation 3 (101102122010220, 1 draws): dtw accuracy 1/90 closed 13/90 FA 1/300; net accuracy 1/90 closed 31/90 FA 8/300
unconstrained permutation 4 (020001112122102, 1 draws): dtw accuracy 1/90 closed 43/90 FA 1/300; net accuracy 1/90 closed 29/90 FA 3/300
unconstrained permutation 5 (111200222210001, 1 draws): dtw accuracy 1/90 closed 30/90 FA 1/300; net accuracy 1/90 closed 36/90 FA 10/300
unconstrained permutation 6 (202201122001101, 1 draws): dtw accuracy 1/90 closed 61/90 FA 1/300; net accuracy 4/90 closed 64/90 FA 10/300
unconstrained permutation 7 (000020212121121, 1 draws): dtw accuracy 1/90 closed 33/90 FA 1/300; net accuracy 1/90 closed 28/90 FA 4/300
unconstrained permutation 8 (102020011222101, 1 draws): dtw accuracy 0/90 closed 49/90 FA 2/300; net accuracy 2/90 closed 35/90 FA 9/300
unconstrained permutation 9 (100001022211122, 1 draws): dtw accuracy 1/90 closed 35/90 FA 1/300; net accuracy 0/90 closed 23/90 FA 6/300
unconstrained permutation 10 (102112000012221, 1 draws): dtw accuracy 0/90 closed 16/90 FA 1/300; net accuracy 0/90 closed 30/90 FA 9/300
unconstrained permutation 11 (120120002202111, 1 draws): dtw accuracy 1/90 closed 19/90 FA 1/300; net accuracy 0/90 closed 27/90 FA 10/300
unconstrained permutation 12 (112002102210012, 1 draws): dtw accuracy 1/90 closed 12/90 FA 1/300; net accuracy 1/90 closed 28/90 FA 9/300
unconstrained permutation 13 (211122001012002, 1 draws): dtw accuracy 0/90 closed 34/90 FA 1/300; net accuracy 1/90 closed 30/90 FA 6/300
unconstrained permutation 14 (200222211101010, 1 draws): dtw accuracy 0/90 closed 47/90 FA 1/300; net accuracy 2/90 closed 51/90 FA 3/300
unconstrained permutation 15 (002212201101210, 1 draws): dtw accuracy 0/90 closed 26/90 FA 1/300; net accuracy 4/90 closed 26/90 FA 10/300
unconstrained permutation 16 (011000011122222, 1 draws): dtw accuracy 0/90 closed 7/90 FA 1/300; net accuracy 0/90 closed 16/90 FA 7/300
unconstrained permutation 17 (220000111221210, 1 draws): dtw accuracy 0/90 closed 6/90 FA 1/300; net accuracy 0/90 closed 30/90 FA 6/300
unconstrained permutation 18 (010202210012211, 1 draws): dtw accuracy 0/90 closed 15/90 FA 2/300; net accuracy 3/90 closed 30/90 FA 9/300
unconstrained permutation 19 (102210201100221, 1 draws): dtw accuracy 0/90 closed 27/90 FA 1/300; net accuracy 1/90 closed 37/90 FA 8/300
strace dtw: files opened: /etc/ld.so.cache, dtwapp, /lib/x86_64-linux-gnu/libc.so.6, /lib/x86_64-linux-gnu/libm.so.6, stateB.dtw
strace net: files opened: /etc/ld.so.cache, netapp, /lib/x86_64-linux-gnu/libc.so.6, /lib/x86_64-linux-gnu/libm.so.6, modelB.bin
report: OUTDIR/RESULTS.md
```

## Artifacts copied to dryrun/ (SHA-256 in dryrun/SHA256SUMS)

States and models (`stateA.dtw` 14,663, `stateB.dtw` 19,548, `modelA.bin` 5,936, `modelB.bin` 5,970 bytes), `thresholds.json`,
`summary.json`, the four dev DET curves, `decisions_core.csv.gz` (dev, P2, P4 and the untrained control; P2_rerun is
byte-identical to P2 and the 25 permutation controls are only in the full decisions.csv, whose hash is in `decisions_full.sha256`),
the strace logs, `log.txt`, `run_all.log`, `kit_checks.log`, `measurements/`.  The 580 clips (18.6 MB) and the training-row
caches are not copied: `standin_sources.txt` + the zip + the seeds regenerate them exactly.
