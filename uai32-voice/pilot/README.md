# Enrolled-speaker pilot: protocol, kit and the two complete applications

One speaker, one microphone, isolated one-second utterances.  Two complete command recognisers built with the frozen
uAI-32 release's flags share one audio front-end and are measured for bytes (application plus state at the declared
capacity) and peak RAM: arm 1 is DTW against uint8 templates (`dtwapp`), arm 2 is the uAI-32 network with the
front-end merged in (`netapp`).  The frozen release in `../../uai32/` is only read and executed here, never modified.

| file | what |
|---|---|
| `dtwapp.c`, `dtwapp`, `dtwapp.elf` | arm 1: DTW nearest-template recogniser, uint8 templates in a documented state file (`enrol`, `score`, `info`) |
| `netapp.c`, `netapp`, `netapp.elf` | arm 2: `uai32.c` plus the `feat` verb and a 6-decimal + logit-margin `predict`; train/test and the model format unchanged (`validation/netapp_vs_uai32.diff`) |
| `record.py` | the prompter/recorder: sealed label manifest, opaque clip ids, seeded prompt order, 1.5 s capture centred to 1.0 s, resume, hand-recording fallback |
| `run_pilot.py` | the runner: both arms, dev-phase threshold choice and freeze, the one-shot test (P2 twice, P3, P4), the H5 controls, the report |
| `measure.sh` | bytes, state at capacity, totals against 32,768, peak RSS per verb (validation mode and `--pilot` mode) |
| `RESULTS_TEMPLATE.md` | the report's shape and what each column means |
| `DRYRUN.md`, `dryrun/` | the kit exercised end to end on speaker-INDEPENDENT stand-in clips: proves it runs, not a result |
| `FRONTEND.md` | the shared feature recipe, exactly, and how closely it matches the benchmark's Python |
| `SIZES.md` | executable bytes, state bytes by formula and from real files, totals, peak RSS, the source-derived working set |
| `FAILURES.md` | what failed, was worked around, abandoned, or is estimated |
| `build.sh`, `SHA256SUMS` | the build (exact uai32 flags + `-Wl,-z,nosectionheader`), the hashes |
| `validate.sh`, `tools/`, `validation/`, `measurements/` | validation against the benchmark's own code, its logs, the real state/model files, raw size and RSS outputs |

## 1. The applications

Clip format for both apps: raw signed 16-bit little-endian mono PCM at 16 kHz, 1 s = 16,000 samples, on stdin; shorter
input is zero-padded at the end, longer is truncated; WAV, empty and odd-length input are refused.  Isolated utterances
only: the host centres the word (section 3).

```sh
./dtwapp enrol STATE LABEL < clip      # LABEL 0..15; creates STATE if absent (8 + 977 N bytes)
./dtwapp score STATE < clip            # -> best_label best_dist runnerup_dist margin
./dtwapp info  STATE
./netapp feat [LABEL] < clip           # -> 144 values [+ LABEL], one uai32 data row
./netapp train DATA MODEL [HIDDEN] [EPOCHS] [RATE] [SEED]; ./netapp test DATA MODEL
./netapp predict MODEL < rows          # -> class p0 .. p(NO-1) logit_margin (6 decimals)
```

Build and check: `./build.sh && sha256sum -c SHA256SUMS` (gcc 13.3 / binutils 2.42 / glibc 2.39 give `dtwapp` 7,416 and
`netapp` 11,500 bytes, byte-identical on rebuild).  Validation against the benchmark code and the byte/RSS measurements:
`validate.sh`, `measure.sh CLIPDIR WORKDIR` (see SIZES.md; the commands are at the top of each script).

## 2. The pilot protocol

What it establishes: the recognition-versus-rejection trade-off of each arm for one real enrolled speaker on one
microphone, which the speaker-independent benchmark (`../fewshot/`) could not.  It follows `../protocol/protocol.md`
scaled down to one speaker and isolated 1 s utterances; the differences are listed in 2.6.

### 2.1 Conditions

- **Enrolled speaker**: the person who records the enrolment clips is the only person whose clips are scored.
  Cross-speaker behaviour is not measured by this pilot.
- **Same microphone**: one device, one room, one distance (30-50 cm) for every session; AGC, noise suppression and
  echo cancellation off, fixed gain; the device and settings are written into the manifest (`--device`, `--notes`).
- **Isolated 1 s utterances**: one word per prompt, spoken once after the REC cue, inside a 1.5 s capture.

### 2.2 What is host-side, and disclosed

The counted executables receive exactly one 32,000-byte raw clip on stdin and read their own state file (the strace
list in the report shows nothing else).  Everything below happens outside the byte budget and is said so in every report:

1. **Centring** (the one piece of segmentation in the pilot): `record.py` finds the energy centre of the utterance in
   the 1.5 s capture, the midpoint of the 10 ms frames whose energy is within 25 dB of the loudest frame, and writes
   the 1.0 s window centred on it.  No gain change, trimming, filtering or denoising.  The centre, the active region,
   the peak level and any QA warning are logged per clip in `recordings.json`.
2. **The network's training data**: 30 waveform-augmented copies per enrolment clip (shift +-0.1 s, gain +-6 dB,
   white/brown noise at 10-30 dB SNR) and a synthetic "unknown" class (time-reversed clips, spliced halves of two
   different commands, noise-only clips, segment-shuffled feature rows), made in numpy from the enrolment audio only,
   then turned into rows by `netapp feat`.  The device would need the same code, or the rows, to do this itself.
3. **Retraining for the fourth command**: the network is retrained from the retained enrolment audio with capacity
   4 commands + unknown (`netapp train` on a fresh model); the rows or audio it needs are counted and reported
   separately from the model file.  DTW needs nothing retained: it appends five templates.
4. **Thresholding**: both arms print a score; the comparison with the frozen threshold is done by `run_pilot.py`.

### 2.3 Phases, counts, prompts

Per speaker, each phase on a separate day if at all possible (same microphone and room every time):

| phase | positives | negatives | purpose |
|---|---|---|---|
| enrol | 5 x 4 commands = 20 | 0 | 15 clips of commands 1-3 make state A; the 5 clips of command 4 are held back until P3 |
| dev | 10 x 4 commands = 40 | 100 own-voice | the only data on which the score kind and threshold are chosen; the dev DET curve |
| test | 30 x 4 commands = 120 | 300 own-voice | scored once, after the freeze |

Negatives are pre-registered in the manifest **before any recording**: 3 own-voice confusables per command (minimal
pairs or rhymes: stop -> top, shop, stock) and a list of unrelated words; `record.py init` spreads them 60% / 40% and
cycles each list so every word is used as evenly as possible (12 confusables and 20 unrelated words give 15 and 6
repeats each in the test phase).  The prompt order of every phase is a seeded permutation with positives and
negatives interleaved; file names are opaque 12-hex-digit ids; the label lives only in `manifest.json`, whose SHA-256
is sealed in `SEALED.sha256` at `init` and checked by every later step.  Command 4's dev and test clips are scored
with state A as an extra "unfamiliar speech" stratum (reported, not pooled with the own-voice negatives).

Recording QA: the recorder warns when a capture is clipped, very quiet, has a low signal-to-floor ratio, an active
region longer than 1 s, or an utterance touching a capture edge; retake (`r`) until clean, and note the retake counts
(`recordings.json`) in the report.

### 2.4 Freeze rule

Everything that can be tuned is fixed before the test clips are scored:

- The executables (`SHA256SUMS`), the front-end and all hyperparameters (hidden 16, epochs 20, rate 0.01, 30
  augmented copies, the training seed, the score kind of each arm) are what `run_pilot.py dev` records in
  `thresholds.json` together with the SHA-256 of the manifest seal, of state A and model A, and of the dev decisions.
- The threshold of each arm is chosen on the dev phase only: accept at most floor(1% x 100) = 1 of the 100 dev
  negatives, i.e. the threshold is the second-largest dev-negative score, accept when strictly above.  The full dev DET
  curve is saved as CSV for both candidate scores of each arm, so a reader can see whether a joint operating point
  for recall and false accepts existed before the freeze.  The alternative score (DTW `min`, network `margin`) is
  reported for attribution, never used for a second attempt.
- `run_pilot.py test` refuses to run without `thresholds.json`, refuses if any hashed thing changed, and refuses if
  the recipe arguments differ from the frozen ones.
- The same frozen thresholds apply to state B (after the fourth command) and to every control.

### 2.5 One-shot rule

The test stage runs exactly once per output directory.  `run_pilot.py test` writes `TEST_RUNS.json` when it starts and
refuses a second run; `--force-rerun` is possible but every report it then writes begins with a POST-HOC RERUN banner
and does not count.  A change to anything after the test (executable, recipe, threshold, manifest) requires new test
recordings.  Dev and test clips are never swapped.

### 2.6 Differences from protocol.md, on purpose

One speaker, not three to four; 1 s isolated clips centred by the host instead of 2.5 s clips with the word anywhere
(segmentation deferred, section 5); own-voice negatives only (300, not 600 with public strata), so the negative set
is the hard stratum only and the bound it can demonstrate is at best 0.99% (0 of 300); recall is reported per command
over 30 clips from one session, not 3 sessions.  The pass rules of protocol.md section I are therefore not applied as
gates; the report gives the counts and intervals they would need.

## 3. How to run

```sh
cd uai32-voice/pilot && ./build.sh && sha256sum -c SHA256SUMS           # the frozen executables
# day 0: pre-register and seal the manifest (commands, confusables, unrelated words, seed, device), never edited after
python3 -I record.py init /data/spk01/manifest.json --speaker spk01 --seed 11 --commands stop,go,left,right \
    --confusables top,shop,stock,no,so,goat,lift,let,laughed,write,light,ride \
    --unrelated apple,window,seven,coffee,river,paper,yellow,music,table,garden,pencil,orange,summer,bottle,jacket,silver,candle,button,ladder,rocket \
    --device "USB mic X, 40 cm, AGC off, gain 50%"
# day 1, 2, 3: record (resumable; Enter keep, r retake, q quit); backend auto = sounddevice > arecord > sox > manual instructions
python3 -I record.py record /data/spk01/manifest.json enrol
python3 -I record.py record /data/spk01/manifest.json dev
python3 -I record.py record /data/spk01/manifest.json test
python3 -I record.py status /data/spk01/manifest.json
# hand-recorded 1.5 s WAVs (16 kHz mono 16-bit, named incoming/<id>.wav as the manual backend prints) are imported with
python3 -I record.py import /data/spk01/manifest.json --from /data/spk01/incoming
# after the dev phase: P1 + dev scoring + freeze (writes thresholds.json, dev_det_*.csv, stateA.dtw, modelA.bin)
python3 -I run_pilot.py dev  /data/spk01/manifest.json /data/spk01/run --seed 1
# after the test phase, once: P2 x2, P3, P4, controls, RESULTS.md, decisions.csv, summary.json
python3 -I run_pilot.py test /data/spk01/manifest.json /data/spk01/run --seed 1
# fresh byte and RSS numbers for exactly the states that were tested
./measure.sh --pilot /data/spk01/run /data/spk01/manifest.json
```

`run_pilot.py` options: `--dtw-score margin|min`, `--net-score prob|margin`, `--target-fa 0.01`, `--hidden 16
--epochs 20 --lr 0.01 --aug 30 --seed S` (the benchmark's best recipe), `--constrained 5 --perms 20` (control seeds),
`--no-strace`, `--no-hash-check` (only for a build that is deliberately not the frozen one, and say so).  Python 3 with
numpy is all it needs; run everything with `python3 -I`.  Run time for one speaker on this container: dev about 5 s,
test about 75 s (the 25 permutation controls are most of it).

## 4. What the report must contain

`run_pilot.py` writes it (`RESULTS_TEMPLATE.md` shows the shape); the pilot report quotes it and adds the recording
facts.  Required, in this order:

1. Provenance: manifest seal, executable hashes, the frozen recipe and thresholds with their timestamp, the device
   and settings, the dates of the three sessions, retake and QA-warning counts.
2. Bytes: executable + state B for each arm against 32,768 (DTW 7,416 + 19,548 = 26,964; network 11,500 + 5,970 =
   17,470), the retained enrolment data the network needs to retrain, and peak RSS from `measure.sh --pilot` with the
   source-derived working set from SIZES.md.
3. Dev: frozen threshold, dev false accepts and recall, closed-set accuracy, the DET CSVs.
4. P2 (state A): recall per command and pooled as k/n with exact 95% intervals, with closed-set / substituted /
   rejected counts; false accepts per stratum and pooled in two separate columns that are never merged:
   **measured false-accept rate** (point estimate and interval) and **bound demonstrated** (one-sided 95% upper
   limit), plus the n needed for the bound to reach 1%; the held-back command as unfamiliar speech; the restart test
   (byte-identical outputs from fresh processes, state unchanged).
5. P4 (state B): the same over 4 commands, and forgetting on the 90 original clips with the exact McNemar p.
6. Controls: untrained, 5 constrained permutations (each at or below the chance bound), the unconstrained
   permutation distribution with its p-value.
7. The paired DTW-versus-network McNemar, the disclosures of section 2.2, and the strace file list.

Interpretation is pre-registered in protocol.md section K: if DTW passes and the network fails, the method-agnostic
claim stands and "a trainable network is the right tool at five shots" is falsified for this task; the report says so
rather than promoting the network on a secondary metric.

## 5. Out of scope: the two deferred experiments

- **Segmentation.** The pilot centres each word on the host.  Finding the word inside a 2.5 s capture (or a stream)
  with the word anywhere, plosive onsets and noise, is the hidden hard part (protocol.md F3) and has its own byte and
  RAM cost; it is a separate experiment with its own onset-error distribution, run after this pilot has established
  the recognition-and-rejection trade-off on centred words.
- **Continual learning.** The fourth command is added here by appending templates (DTW) or retraining from retained
  enrolment data (network).  Growing the example set after deployment, continuing training of a saved model (uai32's
  `train` on an existing model, which cannot add an output class), and what must be retained for that are a separate
  experiment; it is where the fixed-size network has its one structural advantage over templates, and it is not tested
  by this pilot.
