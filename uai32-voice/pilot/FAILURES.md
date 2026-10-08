# What failed, was worked around, abandoned, or is estimated rather than measured

1. **`/usr/bin/time -v` is not available.**  The binary is absent and `apt-get install time` answers
   "Unable to locate package time" (this image's apt sources do not carry it).  Peak RSS was measured
   instead with `tools/maxrss.py`, which runs each verb as a child process and reports `ru_maxrss` from
   `wait4`, the same kernel counter that GNU time prints as "Maximum resident set size (kbytes)".  The
   result (11.06-11.16 MB for every verb and for an empty program) is a measurement of glibc and the
   loader, not of the applications; the application working set in SIZES.md section 4(b) is computed from
   the source, not measured.

2. **First validation run scored queries against an incomplete state.**  The clip manifest interleaves each
   command's 5 enrolment clips with its 10 queries, and the first version of `validate.sh` processed it in
   one pass, so the "yes" queries were scored when only the "yes" templates existed (printed `inf`
   runner-up, 55/60 decision agreement, an inflated 35/40 closed-set figure).  The best distances already
   matched the reference to 1e-6, which located the fault in the script.  Fixed by enrolling all 20 clips
   first; the reported run (`validation/validate.log`) is the fixed one.  The faulty run's log was
   overwritten, not kept.

3. **Two faults in `build.sh`'s page-padding check before it worked.**  The first version used awk's
   `strtonum`, which this system's awk (mawk) lacks; the second read the RW segment's file size instead of
   its offset from `readelf -l` and printed a negative "gap".  The final check (RW offset minus RX end, 4
   bytes for both executables) is the one recorded in the build output.  The executables themselves were
   byte-identical across all three attempts.

4. **An allocation bug in `dtwapp.c` found by inspection before any measurement.**  The first draft placed
   the 4-byte-aligned DTW row after the 977-byte record inside a `calloc(977 + 248)`; the alignment pushed
   the row 3 bytes past the end.  Fixed by allocating the row first and the record after it (one
   `calloc(307 floats)`).  No build with the bug was measured or kept.

5. **Not exercised:** the `state file full` path (65,535 templates = 64 MB) and the `rate`/`integer` overflow
   paths inherited from uai32; both are reads of the source, not tests.  WAV input is detected only by the
   leading "RIFF" tag; any other header would be read as samples.

6. **The enrolled-speaker condition itself was not simulated.**  As reports/fewshot-accuracy.md found, no
   speaker in mini_speech_commands has five recordings of each command, so the 80 validation clips are
   speaker-independent (queries from speakers absent from enrolment).  They were used only to show that the
   two applications run end to end and reproduce the benchmark's implementation; the accuracies in
   `validation/validate.log` (DTW 30/40, net 21/40 and 14/40 closed-set) are software checks on 40 clips,
   not pilot results, and must not be quoted as such.

7. **uint8 versus float32 agreement is shown on 60 queries x 20 templates here**, plus the benchmark's own
   earlier check over seeds 1-10; all 60 decisions agree both ways, with distances differing by at most
   0.0098 (float32 reference) and 2e-6 (uint8 reference).  The claim "uint8 is lossless" rests on these two
   checks only.

8. **The network's "unknown" class in `model5.bin` is one synthetic kind only** (time-reversed enrolment
   clips), used to make a real 144-16-5 model file of the right size; it is not the benchmark's three-kind
   negative set and says nothing about rejection.

9. **Numerical agreement with the numpy reference is close but not bit-exact:** log-mel max |diff| 1.3e-4,
   144-vectors max |diff| 5.1e-4 (70.8% of printed `%.5g` tokens identical), DTW distances within 2e-6 of
   the benchmark C DTW on the same uint8 templates.  The differences come from float32 `cosf`/`sinf`
   twiddles and summation order; no clip changed its energy-crop start or its DTW decision.

10. **Timing and RSS come from one shared cloud container** (Xeon 2.10 GHz, 4 cores) with visible
    run-to-run variance (about 30% in time, about 100 kB in RSS); they are indicative, not benchmarks.

## Pilot kit (record.py, run_pilot.py, measure.sh --pilot, the dry run), 2026-10-08

11. **No microphone, no capture tool, no `sounddevice` in this container.**  `python3 -c "import sounddevice"` fails
    (module not installed), and `arecord`, `sox`/`rec` are absent (`which` finds only `ffmpeg`).  The three live capture
    backends of `record.py` are therefore written from their documented command lines (`sd.rec`, `arecord -t raw -s
    24000`, `rec ... trim 0 1.5`) and **were never executed against a device**; what was exercised is the backend
    selection, the clean refusal when a forced backend is missing, the `manual` instructions, `import` of 1.5 s WAVs,
    the centring, the QA warnings, resume and the seal check (`dryrun/kit_checks.log`).  The first live use of
    `record.py record` must be a short session that is listened to before any real phase is recorded.

12. **The dry run is speaker-independent and its numbers mean nothing as pilot results.**  No speaker in
    mini_speech_commands has 5 clips of each command (reports/fewshot-accuracy.md), so the "enrolled speaker" of
    `DRYRUN.md` is 20 different speakers and every dev/test clip is from a speaker absent from enrolment; the
    "confusable" and "unrelated" strata are the words up/down and left/right, placeholders chosen only so every row of
    the report is produced.  The recall figures (DTW 16/90, network 3/90 at P2) are the benchmark's speaker-independent
    regime, not an estimate of the pilot's outcome.

13. **Stand-in captures are synthetic 1.5 s captures, not recordings.**  Each 1 s zip clip was placed at a seeded offset
    (0-0.5 s) inside digital silence; the centring therefore saw a -100 dB floor, 122 of 580 windows left the capture and
    were zero-padded (up to 2,640 samples), 33 utterances touched a capture edge, and 218 captures raised at least one
    QA warning (clipped, quiet, long active region).  On real captures these warnings trigger a retake; here they were
    accepted on purpose to exercise the warning paths, and `recordings.json.gz` records every one.

14. **Three bugs found and fixed during the dry run** (the first run's terminal output was not kept; the second run's
    report was overwritten by the third): (a) `%%` written literally in two report headers (`[95%% CI]`); (b) the
    network restart test's second run reused the cached feature rows, so only `predict` ran in a fresh process; fixed to
    re-extract every row with `netapp feat` into a separate cache and to compare the predict line plus the SHA-256 of
    the feat row per clip; (c) the first `decisions.csv` was 17 MB because the network's raw column carried the whole
    144-value row; it now carries the predict line and the row's hash (3.3 MB for 23,080 rows).  None of these changed
    any decision: states, models and decisions are byte-identical across the three runs (dryrun/SHA256SUMS).

15. **The permutation controls permute only the positive rows' labels.**  The synthetic "unknown" rows are built once from
    the enrolment audio with the true labels (the splice kind needs two clips of different commands) and keep the label
    k under every permutation; the augmented copies inherit their source clip's permuted label.  A control that also
    rebuilt the splices from the permuted labels would differ in 1/3 of 232 synthetic rows; it was not run.

16. **Augmented and synthetic waveforms are quantised to int16 before `netapp feat`** (the benchmark fed float32 arrays
    to its numpy front-end).  The difference is one LSB of 16-bit audio per sample and is not measured separately; it
    is one more reason the pilot's network rows are not bit-identical to the benchmark's, on top of item 9.

17. **The `strace` check of protocol B4 covers one decision per arm, not every phase**, and runs in an empty directory
    with absolute paths to the state file; the logs show only `ld.so.cache`, libc, libm, the executable and the state
    (`dryrun/strace_*.log`).  A full-phase strace would be 1,000+ processes and was not done.

18. **The "n needed for the bound to reach 1% at this rate" column is a projection**, computed by holding the observed
    rate fixed while n grows (count rounded up); it says "never" whenever the observed rate is at or above 1%, which is
    arithmetic, not a judgement about the system.

19. **`measure.sh --pilot` reuses the validation-mode method**: `ru_maxrss` of each child (GNU time still unavailable,
    item 1), so the peak RSS of every pilot verb is again the 11.1-11.2 MB glibc floor; the application working set in
    SIZES.md section 4(b) remains a source-derived figure.  Training on the pilot's 774 / 1,033 augmented rows takes
    80-120 ms of CPU, against 26-53 ms for the validation's 20-40 rows.

20. **The network's fourth-command step is a retrain, not continual learning**: model B is trained from scratch on the
    retained enrolment audio of all four commands (uai32 cannot add an output class to a saved model), so the forgetting
    figure for the network measures interference from retraining, not the behaviour of an updated model.  Continuing
    training of model A is the deferred continual-learning experiment (README.md section 5).
