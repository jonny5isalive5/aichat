# Failures, abandoned variants, errors and limitations of the few-shot benchmark

Compiled on 2026-10-08 from `work/*.log`, the pilot scripts in `code/`, `results/*.txt` and the checks described in
`README.md`. Where a statement is an estimate rather than a measurement it says so.

## 1. uai32's printed softmax saturates, so a 1% operating point was often unreachable

`uai32 predict` prints each class probability with `%.3f` (`../../uai32/uai32.c`, line 210). The rejection score of
every MLP variant is the largest printed command probability. The per-draw operating point is the 11th-largest score
among the 1,000 development negatives, and a clip is accepted only if its score is strictly greater. When eleven or
more unfamiliar clips print `1.000`, the threshold becomes `1.000`, nothing can exceed it, and the method accepts
nothing: **0% recall and 0% false accepts**, which looks like perfect rejection and is in fact a dead operating point.

Evidence (3 pilot seeds 901–903, yes/no/stop, 5 enrolment clips per command; `work/pilot_mlp.log`,
`work/pilot2.log`, `work/pilot3.log`; "sat" is the fraction of the 1,000 test negatives that saturate):

| configuration | epochs | lr | sat | threshold (mean of 3) | recall @ dev-1%-FA | test FA | source |
|---|---:|---:|---:|---:|---:|---:|---|
| noaug (15 rows) | 300 | 0.05 | 3.2% (≥0.999) | 1.000 | 2.2% | 0.4% | pilot_mlp `noaug` |
| aug ×30 (465 rows) | 60 | 0.05 | 25.9% (≥0.999) | 1.000 | **0.0%** | 0.0% | pilot_mlp `aug30` |
| aug ×30, hidden 32 (10,638 B) | 60 | 0.05 | 24.4% (≥0.999) | 1.000 | **0.0%** | 0.0% | pilot_mlp `aug30_H32` |
| aug ×30 | 30 | 0.05 | 21.3% (≥0.999) | 1.000 | **0.0%** | 0.0% | pilot_mlp `aug30_E30` |
| aug ×30 + synthetic unknown (774 rows) | 60 | 0.05 | 5.8% (≥0.999) | 1.000 | **0.0%** | 0.0% | pilot_mlp `aug30_neg` |
| aug ×30 | 10 | 0.05 | 8.2% (= max) | 1.000 | **0.0%** | 0.0% | pilot2 `aug E10` |
| aug ×30 | 5 | 0.05 | 4.6% (= max) | 1.000 | **0.0%** | 0.0% | pilot2 `aug E5` |
| aug + unknown | 20 | 0.05 | 3.3% (= max) | 0.999 | 1.4% | 0.2% | pilot2 `aug_neg E20` |
| aug + unknown | 60 | 0.01 | 1.7% (= max) | 0.999 | 2.2% | 0.2% | pilot2 `aug_neg E60 lr.01` |
| aug ×30 | 3 | 0.05 | 2.5% (≥0.9995) | 1.000 | 2.0% | 0.3% | pilot3 `aug E3 lr.05` |
| aug ×30, L2-normalised inputs | 10 | 0.01 | 1.4% (≥0.9995) | 1.000 | 0.2% | 0.4% | pilot3 `aug E10 lr.01 L2` |
| **adopted**: plain | 300 | 0.01 | 0.6% (≥0.999) | 0.997 | 3.1% | 1.1% | pilot_mlp `noaug_lowlr` |
| **adopted**: aug ×30 | 5 | 0.01 | 0.1% (≥0.9995) | 0.993 | 5.1% | 1.3% | pilot3 `aug E5 lr.01` |
| **adopted**: aug + unknown | 20 | 0.01 | 0.3% (= max) | 0.987 | 5.7% | 0.9% | pilot2 `aug_neg E20 lr.01` |

The three scripts define "sat" differently: `pilot_mlp.py` counts scores ≥ 0.999, `pilot2.py` counts scores equal
to the largest test-negative score (which is 1.000 whenever any clip saturates), `pilot3.py` counts scores ≥ 0.9995.
The report quotes them side by side; the differences are at the 0.1% level and do not change the picture.

Saturation still occurred in reported runs even with the adopted settings:

* up/down/go, `C3_mlp_aug_neg`: the fixed threshold frozen from dev seeds 101–110 came out at exactly `1.000`;
  fixed-threshold recall 0.0%, false accepts 0/20,000 (`results/summary.txt`).
* 20 enrolment clips per command (`enrol20mlp_yes_no_stop_test.npz`): the two non-augmented variants trained for
  300 epochs on 60 and 120 rows (`C0_mlp_plain`, `C2_mlp_neg`) saturated in every one of the 10 draws:
  per-draw threshold `1.000`, 0 accepts out of 10,000 negatives, 0% recall, although closed-set accuracy was 79.0%
  and 78.0%.
* Fixed thresholds of the other MLP variants sit between 0.983 and 0.9995, i.e. within 1 to 17 print steps of the
  ceiling, so their rejection numbers are partly a resolution artefact of the `%.3f` output rather than a property
  of the network. Even the oracle recall at 1% FA (threshold set on the test negatives themselves) never exceeded
  5% for any MLP variant, so the artefact does not hide a good result.

Consequence for the pilot: the network application prints six-decimal probabilities and the logit margin
(`../pilot/netapp.c`); the release binary's output is unchanged.

## 2. Abandoned hyper-parameter and recipe variants

Choices were made on pilot seeds 901–905 (yes/no/stop) and never revisited on the reported seeds.

Logged (`work/pilot_mlp.log`, `pilot2.log`, `pilot3.log`):

* lr 0.05 for any MLP variant: saturates (section 1). Abandoned for lr 0.01.
* Hidden layer 32 (`aug30_H32`, 10,638-byte model): same saturation and accuracy as hidden 16 (71.1% closed-set
  both). Abandoned; 144-32-(k+1) appears in the byte table only.
* 30 and 60 epochs with 30× augmentation: saturate; 5 epochs adopted. 10 epochs at lr 0.01: sat 1.0%,
  recall 4.0% versus 5.1% at 5 epochs; 20 epochs at lr 0.005: recall 4.4%. Not adopted.
* Synthetic unknown class without augmentation (`neg_only`, 15 + 60 rows, 300 epochs, lr 0.05): AUC 0.848,
  recall 4.3%; the `C2_mlp_neg` variant kept the idea with 15 negatives at lr 0.01.
* L2-normalised input vectors (`pilot3`, three configurations): recall 0.2–0.8% versus 3.1–5.7% unnormalised.
  Abandoned.
* Synthetic negative *templates* for the template methods (`pilot2`: prototype `negmargin`, `negratio`,
  `4class-ratio`; DTW `negmargin`, `negratio` with 45 negative templates): all worse than the plain scores
  (DTW margin 16.3% recall at the dev threshold versus 3.6–4.8% with negative templates; prototype 8.0% versus
  0.7–1.0%). Abandoned.

Not logged (the scripts are preserved, their stdout was not; only the choices they led to survive in the defaults):

* `pilot.py`: prototype grid of normalisation {cmn, peak} × pooling {grid, center, vad} × metric {cos, euc};
  DTW normalisation {cmn, peak} × trimming {full, vad with energy drop 3.0 or 2.0 nat}; five MLP configurations at
  lr 0.05/0.02 including a two-stage run with a 20-epoch lr 0.01 continuation (`fewshot.uai32_run(extra=...)`).
  Outcome: centre pooling, cmn-type normalisation, untrimmed 61-frame CMVN sequences for DTW.
* `pilot_vec.py`: pooled-vector variants (DCT c1–c12 centre-pooled, adopted; grid pooling; with c0; 15 and
  8 coefficients).
* `diag.py`, `diag2.py`: feature families logmel_cmn, logmel_cmvn, lmclamp_cmn, mfcc_cmn, mfcc_cmvn, mfcc_raw ×
  calibrations min / margin / ratio / tnorm for prototypes (cosine and Euclidean) and DTW; cosine-margin prototypes;
  DTW class-mean-of-five scoring. Outcome: mfcc_raw pooled vectors for A and C, logmel_cmvn frames for B,
  calibrations min + ratio (A), min + margin (B); `tnorm`, Euclidean and mean-of-five dropped.
* Library code that is preserved but unused by any reported run: `fewshot.trim_sequences` (`vad` mode),
  `features.normalise('peak')`, `features.pool('grid'|'vad')`, `fewshot.proto_score('euc'|'cos_margin')`,
  `feats2.calibrate('tnorm')`, `fewshot.dtw_dist` (numpy DTW, replaced by the C version), the `extra` argument of
  `uai32_run`.

## 3. Things that errored, did not build, or were estimated

* **`code/frontend.c` does not compile with the uai32 Makefile CFLAGS.** `-std=c99` hides `M_PI`
  (`error: 'M_PI' undeclared`, lines 25, 52, 86). `results/summary.txt` says the front end was "built with the uai32
  flags"; the object and ELF that were measured (`.text` 2,006 B; 4,680-byte stripped ELF, SHA-256
  `51202620…`) are reproduced byte for byte with the same flags minus `-std=c99` (equivalently `-std=gnu99`, or
  `-std=c99 -D_GNU_SOURCE`). `code/build_bins.sh` does this. The compile also emits a `-Wmisleading-indentation`
  warning at line 74 (a `for` followed by a statement on the same line; the code is correct as written).
* **No front-end + DTW executable was ever built.** The scratch file `work/frontend_dtw` was byte-identical to
  `work/frontend` (same SHA-256), so the "TOTAL B: front end+DTW ELF + uint8 templates 20,120 / 25,000 B" row in
  `results/summary.txt` is `4,680 + 800 + templates`, with 800 B an **assumed** cost of linking `dtw.c` in. The DTW
  `.text` alone is measured (546 B with the uai32 CFLAGS; 779 B with `-Os -ffunction-sections -fdata-sections` only,
  the difference being mostly the `sqrtf` errno path removed by `-fno-math-errno`).
* **"Merged into uai32.c it would add ~2–2.5 KB"** (summary table note, report Risks) is an estimate; the
  benchmark's recipe was never merged into the release source. (The different recipe in `../frontend/` was.)
* **`results/uint8_dtw_check.txt` prints a hard-coded `0.025`** for "max |quantisation error|": it is the
  round-to-nearest bound for a 0.05 step, not a measured maximum. The quantiser in `code/check_uint8_dtw.py` clips
  to `[-127, 128]` steps, i.e. values in [−6.35, 6.40] (the table says "clipped to ±6"), and keeps the result as
  float32 for the DTW call; no actual uint8 template file was written. The closed-set and recall equality
  (92.0% / 12.0% for both) is measured over seeds 1–10.
* `code/lane1.sh` and `code/lane2.sh` contain absolute scratch-space paths and cannot be run from here; they are
  kept verbatim and `code/rerun_all.sh` (relative paths, sequential) replaces them.
* `results/HOW_TO_RERUN.txt` copies `bin/uai32` from the build tree `/home/user/aichat/uai32/uai32`, not from
  `dist/`; the two files are byte-identical (same SHA-256 as `../../uai32/dist/SHA256SUMS`).
* `work/*_q.txt`, `*_train.txt`, `*.model` and `cache/` were not preserved (sizes 0.3–256 MB); they are regenerated
  exactly by the commands in `README.md` (uai32 training verified deterministic).
* No preserved log contains an error trace; `work/lane1.done` and `lane2.done` were written, i.e. all 20 runs
  completed. The pilot runs `pilot.py`, `pilot_vec.py`, `diag.py`, `diag2.py` left no log (section 2).
* During the 2026-10-08 checks `/usr/bin/time` was absent on the machine; the 7.5 s timing of the seed-1 rerun used
  `date`, and no peak-RSS figure was taken for the Python benchmark (the pilot measures RAM for the C applications).

## 4. Limitations of every number in this directory

* **Speaker-independent only.** Enrolment and test speakers always differ (`manifests/dataset.txt`: no speaker has
  five recordings of every word of yes/no/stop, up/down/go or yes/no/stop/go). The challenge's enrolled-speaker,
  same-microphone setting is easier by an unknown margin; these numbers are a lower bound on it, not a prediction.
* Crowd-sourced audio with heterogeneous microphones and noise; 822 of 8,000 clips are shorter than 1 s and
  zero-padded; utterances are roughly centred by the dataset, not by any segmentation of ours.
* Draws share recordings (100 test positives per command are drawn from ~700 per word), so pooled Wilson intervals
  are optimistic; the ± sd across draws is the honest spread (e.g. DTW-margin recall 14.6 ± 7.8%).
* Hyper-parameters and feature choices were tuned on yes/no/stop pilot seeds; up/down/go and the 4-command set are
  the cleaner tests of them. The search was small (section 2).
* The MLP rejection score is quantised to 0.001 by the release binary's output (section 1).
* Synthetic negatives were built only from the five enrolment clips per command; the "initially untrained" rule
  forbids real negatives, and a shipped generic unknown-template set was not tried.
* uint8 template storage was verified lossless only for the DTW-margin score on yes/no/stop; the DTW code size
  assumes no banding, and DTW cost grows linearly with the template count.
* The benchmark's feature recipe (512-point FFT, 32 ms frames, 144 DCT features) is not the recipe of the merged
  front-end in `../frontend/` (256-point FFT, 16 ms frames, 192 log-energies); accuracy was never measured on the
  latter.
