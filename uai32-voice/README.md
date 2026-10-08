# µAI-32 voice feasibility: preserved artifacts and the enrolled-speaker pilot

This directory preserves the work done on 7 October 2026 to answer one question: can a trainable
spoken-command recogniser (few examples per command, rejection of unfamiliar speech, state that survives a
restart) fit the µAI-32 budget of 32,768 bytes for executable plus persistent state? It also contains the
kit for the next experiment, an enrolled-speaker pilot. The frozen, independently audited µAI-32 release in
`../uai32/` is untouched by anything here; the applications in `pilot/` are separate programs that copy its
source.

| directory | what it holds | status |
|---|---|---|
| `reports/` | the three investigation reports, verbatim | record |
| `frontend/` | audio front-end in C (biquad bank and FFT/mel), merged into a copy of `uai32.c`, with byte measurements, build scripts, binaries and hashes | measured |
| `fewshot/` | few-example benchmark on real speech (Google mini Speech Commands): DTW, nearest-mean, 1-NN and the real `uai32` binary on identical features; code, manifests, raw per-draw results, logs | measured, speaker-independent only |
| `protocol/` | statistical review of the proposed acceptance conditions and a corrected, numbered protocol | proposal |
| `pilot/` | the enrolled-speaker, same-microphone pilot kit: complete DTW and network applications sharing one front-end, recorder, runner, size and RAM measurement, dry run (`pilot/dryrun/`, stand-in data, not results) | ready to record |

Every sub-directory has its own README with exact commands, and a FAILURES.md listing what did not work,
what was abandoned, and what is estimated rather than measured.

## What was established

1. **Audio processing fits.** A 256-point FFT with 16 mel bands computed from formulas, merged into a copy
   of `uai32.c` and built with the µAI-32 flags, costs 2,224 bytes (11,412-byte executable, imports only
   `sinf`/`sincosf`), processes one second of audio in about 1.3 ms, and matches a float64 reference on 188
   synthetic checks. A 16-filter biquad bank costs 1,704 bytes but separates neighbouring bands far worse.
   Details and the feature-row format: `frontend/README.md`.
2. **Five examples per command is the hard part, and at five examples templates beat the network.** On real
   crowd-sourced speech, speaker-independent (strictly harder than the pilot's enrolled-speaker setting),
   closed-set accuracy for yes/no/stop was DTW 91.1%, nearest-mean 79.3%, µAI-32 MLP 65 to 70%. With the
   operating point set to admit 1% of unfamiliar words, recall fell to 14.6% (DTW), 12.2% (nearest-mean) and
   3 to 4% (MLP). Details, seeds and raw per-draw scores: `fewshot/`.
3. **µAI-32's printed probabilities cannot serve as a rejection score.** Three-decimal softmax output
   saturates at 1.000 for 4 to 26% of unfamiliar words depending on epochs. The pilot's network application
   therefore prints six-decimal probabilities and the logit margin.
4. **The proposed acceptance conditions need rework** (sample sizes, per-cell rules, negative-set design,
   the definition of "initially untrained", the shuffled-label control). The corrected protocol is in
   `protocol/protocol.md` with its arithmetic in `protocol/intervals.py`.

## Reconciliation of the network size figures

Three different network sizes were quoted, for three different things. All follow the µAI-32 model-file
formula `bytes = 8 + 8·NI + 2·(NH·(NI+1) + NO·(NH+1))` (float32 mean and scale per input, bfloat16 weights).

| configuration | bytes | what it is |
|---|---:|---|
| 192-44-6 | 19,068 | the **budget ceiling**: the largest hidden layer that keeps the 11,412-byte FFT executable plus model under 32,768 with 2,000 bytes spare (total 30,480). Never trained or benchmarked. |
| 192-16-4 | 7,856 | the model used in the front-end investigation's synthetic end-to-end run (feat → train → test, 40/40 correct). Not a speech result. |
| 144-16-3 / 144-16-4 | 5,902 / 5,936 | the model actually **benchmarked on speech** in `fewshot/` (144 DCT features of 12 time segments; 3 commands, or 3 commands plus a synthetic "unknown" class). |
| 144-16-5 | 5,970 | the same with 4 commands plus the "unknown" class: the pilot's declared capacity. |

So the accurate statement is: the network that was measured on speech is about 6 KB, the executable that
carries it is about 11.5 KB, and roughly 15 KB of budget could still be spent on a larger hidden layer if
that ever proved useful. Note also that two front-end recipes exist: `frontend/` measured the byte cost of a
256-point FFT with 192 pooled log-energies, while the benchmark and the pilot applications use the recipe the
accuracy numbers were produced with (512-point frames, 16 mel bands, 144 DCT values for the network, 61×16
normalised frames for DTW). The pilot's `SIZES.md` measures the real files.

## Complete applications, measured (pilot kit, same toolchain and flags as the release)

| arm | application | state at capacity (4 commands × 5 examples) | total | spare |
|---|---:|---:|---:|---:|
| quantised-template DTW (`dtwapp`) | 7,416 B | 19,548 B (20 uint8 templates of 61×16, 977 B each) | 26,964 B | 5,804 B |
| µAI-32 network (`netapp`) | 11,500 B | 5,970 B (144-16-5 model, synthetic "unknown" class) | 17,470 B | 15,298 B |

Both executables rebuild byte-identically (`pilot/build.sh`, `pilot/SHA256SUMS`). `dtwapp` reproduces the
benchmark's DTW decisions on 60 of 60 checked queries; `netapp` keeps µAI-32's train/test/predict and model
format unchanged (models byte-identical to the frozen release's) and adds `feat` plus six-decimal
probabilities and the logit margin.

**Peak RAM.** Process peak RSS is not a usable number here: measured through a Python harness it reads
about 11 MB for every verb and for an empty program; measured through `posix_spawn` it reads 2.2 to 2.4 MB
with a 1.4 MB floor for `/bin/true`. Both are glibc and loader, not the application. The figure that matters
for a microcontroller is the source-derived working set, listed buffer by buffer in `pilot/SIZES.md`: about
10.4 KB for `dtwapp` score or enrol, 9.6 KB for `netapp feat`, 12.7 KB for `netapp predict`, and 24 to 36 KB
for `netapp train` (plus a 147 KB initial row reservation inherited from `uai32.c` that an embedded port
would size exactly). The protocol's board gate requires measuring this on the board with stack painting.

## Measured false-accept rates versus confidence-bound requirements

These are different quantities and the pilot report keeps them in separate columns.

- A **measured false-accept rate** is a count: `k` accepts out of `n` unfamiliar clips, reported with an exact
  two-sided 95% Clopper-Pearson interval. In the benchmark, operating points chosen on development draws to
  admit 1% of development negatives produced measured test rates of 0.9 to 1.3% (and 0.46 to 1.54% when the
  threshold was frozen from separate seeds).
- A **bound demonstrated** is the one-sided 95% upper limit implied by that count: with 0 accepts in 300 clips
  the bound is 0.99%; with 3 in 300 it is 2.56%; with 18 in 1,800 it is 1.48%.
- A **requirement** phrased as "false accepts ≤ 1%" is ambiguous. If it means the point estimate, 3 of 300
  passes while a system whose true rate is 2% also passes 15% of the time. If it means the demonstrated
  bound, zero accepts in at least 299 clips (or at most 4 in 1,800) are needed, and a system whose true
  rate is 0.5% fails that test 94% of the time. The protocol recommends stating the claim as "point estimate
  ≤ 1.0%, demonstrated below 1.5% at 95% confidence" with 1,800 negatives, 600 of them own-voice.

The pilot runner prints both columns and the `n` that the bound would need to reach 1%.

## The next experiment: enrolled-speaker pilot (`pilot/`)

One speaker, one microphone, isolated one-second utterances. Enrol 5 clips per command (3 commands, a 4th
held back); choose each arm's operating point on a development set of 10 clips per command plus 100
own-voice negatives; freeze; test once on 30 clips per command plus 300 own-voice negatives. Both arms are
complete applications built with the µAI-32 flags and measured for bytes (application + state at the
declared capacity of 4 commands × 5 examples) and peak RAM: quantised-template DTW (`dtwapp`) and the
µAI-32 network (`netapp`) on the same front-end. The restart test and the fourth-command step follow the
protocol. What the pilot establishes is the recognition-versus-rejection trade-off for a real enrolled
speaker, which the speaker-independent benchmark could not.

Explicitly deferred until that trade-off is known: **segmentation** (finding the word in a longer stream;
the pilot's recorder centres the utterance on the host, and says so) and **continual learning** (growing the
example set after deployment, where the fixed-size network has its one structural advantage over
templates). In the pilot, the fourth command is added to the network by retraining from the retained
enrolment audio, which is disclosed; µAI-32 cannot add an output class to a saved model.

## Provenance and reproducibility

Every binary in this tree has a SHA-256 in a `SHA256SUMS` file next to it and a script that rebuilds it;
the rebuilds were repeated on 8 October 2026 and were byte-identical (`frontend/rebuild_check.log`,
`pilot/build.sh`). The benchmark's 120 draws are regenerated exactly from the seeds
(`fewshot/manifests/draws.json.gz`, verified against every stored split), a seed-1 rerun reproduced all nine
methods' scores bit for bit, and the dataset archive is pinned by SHA-256 in `fewshot/manifests/dataset.txt`.
What is estimated rather than measured, what failed, and what was abandoned is in each directory's
`FAILURES.md`.
