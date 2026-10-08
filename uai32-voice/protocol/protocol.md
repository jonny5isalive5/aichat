# Voice-command challenge: review of the proposed acceptance conditions and a corrected protocol

Reviewer stance: sceptical statistician / test designer. All intervals are exact (Clopper-Pearson) unless
stated; "upper95" means the one-sided 95% upper confidence bound, which is the quantity a claim of the form
"rate <= x%" actually needs. Arithmetic: `intervals.py` / `intervals_output.txt` in this directory.

## Part 1. What is wrong with the proposal as written

1. **"At most 1% false accepts on 300 recordings" cannot show 1%.** Observed 0/300 gives upper95 = 0.99%
   (two-sided 95% CI 0.00-1.22%); 1/300: upper95 1.57% (CI 0.01-1.84%); 2/300: 2.08% (CI 0.08-2.39%);
   3/300: 2.56% (CI 0.21-2.89%). So the only observation on 300 that "shows <= 1%" is zero false accepts,
   and a rule "pass if <= 3/300" passes a system whose true rate is 1.0% only 65% of the time and a system
   at 2.0% still 15% of the time. To establish "< 1%" with 95% confidence you need 299 trials with 0 false
   accepts, 473 with <= 1, 628 with <= 2, 773 with <= 3, 1,049 with <= 5, 1,693 with <= 10. For 80% power
   you need about 780 trials (pass if <= 3) when the true rate is 0.25%, or about 1,950 (pass if <= 12)
   when the true rate is 0.5%. A test sitting on the boundary (true 1%, target 1%) is a coin flip at any n.
2. **">= 90% per command on 30 fresh recordings" has a wide interval and a multiplicity problem.**
   27/30 = 90.0% has CI 73.5-97.9% (Wilson 74.4-96.5%), lower95 = 76.1%. Even 30/30 only has lower95 =
   90.5%. Worse, the rule is applied per (speaker x command) cell: 9 cells for three commands, 12 after the
   fourth. A system whose true per-utterance accuracy is 95% passes a single cell with probability 0.939,
   all 9 cells with 0.57, all 12 with 0.47; at a true 93% the family-wise pass probability is 0.22 / 0.13.
   The rule as written fails a genuinely good system about half the time and tells you nothing about why.
3. **The negative set is undefined**, and the definition is the whole test. Negatives spoken by other people
   through other microphones (e.g. raw Google Speech Commands clips) are rejected by a speaker-dependent
   system largely on voice and channel mismatch; the hard negatives are the *same speaker, same device*
   saying confusable words. 300 easy negatives at 0% tell you nothing about "similar-sounding words".
4. **"Thresholds fixed before final testing" does not say on which data.** If per-speaker thresholds are
   tuned on extra recordings of the test speakers, the system has in fact been given more than five examples
   per command, and the five-example claim is void.
5. **"Initially untrained" is undefined.** A VAD trained on data, corpus-derived normalisation statistics,
   a PCA basis, or a shipped "garbage" set of negatives are all learned state from data.
6. **Segmentation loophole.** If the host hands the system a one-second window centred on the word (as in
   Speech Commands), the hardest part of the task (finding the word in time, time-normalising it) has been
   done outside the byte budget. Nothing in the proposal forbids this.
7. **The example-level shuffled-label control does not behave as intended at n = 15.** Exact enumeration
   (ideal recogniser that predicts each word's majority shuffled label): under a uniformly random permutation
   of the 15 enrolment labels, test accuracy is 0% with probability 0.333, 33% with 0.414, 67% with 0.172
   and **100% with 0.080**. The mean is chance (33.3%) but a single shuffled run is above 2/3 one time in
   four. With 20 permutations there is an 81% chance that at least one of them scores 100%. A single
   permuted run cannot therefore serve as a "must be at chance" gate, and "trained beats all 20
   permutations" would fail a perfect system most of the time.
8. **No rule against re-running after seeing test results**, no fixed seeds, no publication of recordings,
   manifests or decision tables, so neither the one-shot nature of the test nor reproducibility is guaranteed.
9. **Cross-speaker same-word utterances are undefined**: if speaker B says speaker A's command word, is that
   a false accept or a correct accept? It depends on whether the system is meant to be personal.
10. **"Retains its learning after restart"** needs a process-boundary definition and a byte-identity check,
    and the fourth-command step needs a forgetting check on the original commands.
11. **The two gates share one threshold.** Accuracy and false accepts trade off through the rejection
    threshold; both must be met by one frozen operating point, so the dev-set DET curve must be examined
    before freezing, and the gate must not be met by rejecting more positives.

## Part 2. Corrected protocol (numbered, ready to adopt)

### A. Definitions

A1. *System* = the executable file(s) plus the persistent state file. *Host* = audio capture, resampling to
    the declared format, and delivery of raw PCM to the system, nothing else (see F).
A2. *Clip* = 2.5 s of raw little-endian 16-bit PCM, mono, 16,000 Hz = 40,000 samples = 80,000 bytes, with
    the word beginning at whatever moment the speaker said it after the prompt (not aligned, not trimmed).
A3. *Decision* = exactly one of {command 1..C, REJECT} per clip. *Correct* for a positive clip means the
    decision equals the enrolled command (a substitution or a REJECT is an error). *False accept* for a
    negative clip means any decision other than REJECT.
A4. *Cell* = one (speaker, command) pair; 30 fresh test clips per cell.
A5. All rates are reported as k/n with the exact two-sided 95% Clopper-Pearson interval; gates below are
    stated as counts so that no interval arithmetic is needed at decision time.

### B. Byte budget (desktop gate)

B1. Count = sum of on-disk sizes (`wc -c`) of every file the system needs to run that is not provided by
    the OS: executable(s), any script or configuration, and the persistent state file **measured after the
    fourth command is enrolled** (i.e. at the declared capacity C >= 4 commands x 5 examples). The sum must
    be strictly below 32,768.
B2. If the state grows with enrolled examples (templates), the count uses the worst case at declared
    capacity, and the state-file length must be a function of its own header (as uai32 does), so the
    measurement can be checked by formula.
B3. Excluded: kernel, libc/libm, dynamic loader, shell, the host capture program (restricted by F).
    Included: all hyperparameters, thresholds and constants, wherever stored.
B4. The executable may read only its state file and the clip (stdin or one named file). Verified by
    running each test phase inside an empty directory under `strace -f -e trace=openat,open,read,execve`;
    the log is published. No network, no environment variables, no `/proc`, no other files.
B5. Packers are allowed (the decompressor is inside the counted file); an external decompressor is not.
B6. Reproducible build: compiler and version, flags, source SHA-256 and executable SHA-256 are published
    at the freeze (E3). A second build from the same source must give identical bytes.

### C. Board gate (later, separate numbers, declared up front)

C1. Flash: the whole application image (code, constants, drivers/HAL, and the persistent-state region at
    capacity) must be <= the declared flash budget (recommended: the same 32,768 bytes). Only the silicon
    vendor's mask-ROM bootloader is excluded, and it is named.
C2. RAM: peak of .data + .bss + stack high-water mark (stack painting) + heap, during enrolment and during
    recognition, including the audio capture buffer, <= the declared RAM budget (declare it; 16 KiB is a
    reasonable Cortex-M0+-class figure).
C3. Declare whether test audio reaches the board digitally (tests the algorithm) or acoustically through
    its own microphone at a declared distance and level (tests the device); both may be reported, the
    headline says which.
C4. Latency and energy per decision are reported, not gated.

### D. What "initially untrained" means

D1. Permitted shipped state (Tier A, "tabula rasa"): code; closed-form DSP constants derivable from a
    published formula with a handful of parameters (window, mel filterbank, DCT); and at most 16 named
    scalar hyperparameters (frame size, hop, number of coefficients, hidden size, learning rate, epochs,
    rejection threshold(s), augmentation settings), each listed with its value in the disclosure.
D2. Not permitted in Tier A: any array derived from speech or audio data (weights, codebooks, PCA/LDA
    bases, corpus mean/variance statistics, trained VAD, stored templates other than those created at
    enrolment).
D3. Runtime adaptation from the user's own data is permitted (noise floor estimated from the clip, feature
    normalisation estimated from the enrolment clips, leave-one-out thresholds from the 5 enrolment clips).
D4. Per-speaker thresholds may be derived **only** from that speaker's enrolment clips; otherwise thresholds
    are global constants from D1. No other per-speaker tuning.
D5. Shipping generic negative examples (e.g. 32 feature vectors cut from public data) **does** violate
    "initially untrained": it is learned state derived from data. It is allowed only as a declared Tier B
    ("seeded") variant: fully counted in the byte budget, built from a listed set of Google Speech Commands
    v0.02 files (paths + SHA-256) disjoint from every file used in the negative test set, and reported
    side-by-side with Tier A. The headline claim of the challenge is Tier A.
D6. The untrained control (H1) verifies D1-D2 empirically: the shipped executable with no enrolment must
    perform at chance.

### E. Speakers, development data, freeze

E1. People: 1 developer; 1 development speaker (not a test speaker); 4 recruited test candidates (3 needed,
    1 spare); 1 QA listener who is not the developer; 1 person who runs the frozen test (may be the QA
    listener). Test speakers must never have contributed to tuning.
E2. Development set: developer's voice and the development speaker, each: 10 fresh clips per command for
    3 (+1) commands, 200 own-voice negatives (same recipe as G), and public negatives drawn from Speech
    Commands `validation_list.txt` (never from `testing_list.txt`, which is reserved for the test draw).
    All feature, architecture, training and threshold choices are made here and nowhere else. Plot the
    dev DET curve (false-accept rate vs false-reject rate) and choose the operating point before freezing.
E3. Freeze: commit source; publish SHA-256 of the executable, the hyperparameter list (D1), the
    negative-set manifest and seeds (G), the prompt lists, and this protocol with the pass rules (I),
    before the first test-speaker recording session. Record the commit and a public timestamp.
E4. One shot: each pre-registered configuration (Tier A, optionally Tier B, the DTW baseline) is run on the
    test set exactly once. Any change after that requires fresh test sessions (S2-S4 below) or the result
    is labelled post-hoc and does not count.
E5. Seeds for enrolment training, permutations and negative-set draws are fixed in the manifest.

### F. Recording procedure and host-side rules

F1. Device: one fixed device per speaker (model named), same device, same room, same distance for all
    sessions. Capture 16 kHz 16-bit mono if the device allows, else 48 kHz resampled by a named library
    and version. OS/driver AGC, noise suppression and echo cancellation **off**, fixed gain, all settings
    disclosed. Distance 30-50 cm. Ambient noise < 45 dBA (phone SPL meter, value reported).
F2. The host may: open the device, capture, resample to the declared format, write/deliver raw PCM. The
    host may not: normalise gain, trim, run VAD or endpointing, filter, denoise, or compute features. The
    system receives the full 2.5 s clip with the word wherever it fell. The disclosure states this
    explicitly, and B4's strace log shows the executable received the raw clip.
F3. Why: segmentation is the hidden hard part. Public keyword corpora hand you a one-second window with the
    word roughly centred; a fixed-size feature map then works. In use, the word starts anywhere in the
    window and lasts 0.3-0.8 s; the system must find it (energy endpointing is fragile for words that
    start with fricatives or plosives, and under noise) and time-normalise it, and those errors dominate.
    A host that aligns or trims has done this work outside the byte budget. Descriptive requirement: on
    60 dev clips with hand-marked onsets, report the distribution of the system's detected onset error.
F4. Sessions: 4 per test speaker on 4 different calendar days, each >= 24 h apart, all within 21 days.
    A seeded prompter (seed = speaker id x 10 + session) shows one prompt at a time in a randomised,
    interleaved order of positives and negatives, beeps, and captures 2.5 s starting 0.5 s after the
    prompt. Files are named by opaque ids; the label manifest is sealed; the system never sees a label.
    - S1 (day 1): enrolment, 5 clips x 4 commands (commands 1-3 and the future 4th, all recorded now
      but command 4 is not fed to the system until phase P3); 12 pipeline-sanity clips; 50 own-voice
      negatives.
    - S2, S3, S4 (days 2+, 4+, 7+ at the earliest): per session 11 clips per command x 4 commands (the
      first 10 valid per command per session are the test clips, the 11th is a spare) and 50 own-voice
      negatives.
    Per session about 100 items x 5 s = 8-9 min of prompting plus 5 min setup: about 15 min; about 1 h per
    speaker over four days; about 4 h of speaker time for four candidates; the real cost is the calendar
    (>= 3 weeks elapsed) and scheduling four visits per person.
F5. Commands: each speaker chooses 4 distinct words or short phrases of 1-3 syllables; at least 2 of the 4
    must be Speech Commands v0.02 vocabulary words (yes, no, up, down, left, right, on, off, stop, go,
    zero-nine, bed, bird, cat, dog, happy, house, marvin, sheila, tree, wow, backward, forward, follow,
    learn, visual) so that public confusables exist. Before S1 the experimenter pre-registers, per command,
    3 own-voice confusables (minimal pairs or rhymes where possible: e.g. stop -> top, shop, stock;
    go -> no, so, goat; left -> lift, let, laughed) and the 5 nearest Speech Commands words (e.g.
    on/off, go/no, tree/three, four/forward/follow, bed/bird, up/off).
F6. QA: the QA listener audits every clip for truncation or mis-speak **before** any system output exists
    and blind to it; invalid clips are replaced from the spares; invalid counts are reported (expect < 3%).
F7. Consent: speakers are asked to consent to CC BY 4.0 release of their clips so the test is
    reproducible; those who decline are still usable, and the report says which speakers' audio is public.
F8. A speaker who misses a session is replaced by the spare; speakers with fewer than 4 sessions are
    excluded and the exclusion is reported.

### G. Negative set (per speaker model: 600 clips; pooled: 1,800)

G1. N1 own-voice confusables: 120 = 3 confusables x 4 commands x 10 repeats, spread over S1-S4.
G2. N2 own-voice unrelated words/short phrases: 60, from a fixed list of 20 items x 3 repeats.
G3. N3 own-voice non-speech: 20 (cough, laugh, "hmm", throat clear, typing, silence with room noise, all
    captured through the same pipeline).
G4. N4 Speech Commands v0.02 word clips: 300, drawn by seeded script from `testing_list.txt`:
    150 from the pre-registered nearest-word lists, 150 uniformly from the other words; distinct files per
    speaker model (900 distinct files overall). Each 1 s clip is placed at a seeded random offset inside a
    2.5 s clip whose remainder is a seeded crop of `_background_noise_` scaled to 30 dB below the speech.
    Clips of a word that the speaker has enrolled are excluded from N4 and reported under G7.
G5. N5 `_background_noise_` crops: 50 x 2.5 s, seeded, 25 at the recorded level and 25 at +10 dB.
G6. N6 other test speakers' clips of their own commands and confusables, restricted to words this speaker
    did not enrol: 50, seeded.
G7. Cross-speaker same-word clips (other people saying this speaker's enrolled words, from N4 and from the
    other test speakers) are **not** counted as false accepts and not as hits; they are reported as a
    separate descriptive "cross-speaker acceptance" rate, because the challenge does not say whether the
    system is personal. Pre-register the intended behaviour (recommended: personal, i.e. these should be
    rejected, but it is not gated).
G8. The tar.gz of Speech Commands v0.02 is pinned by SHA-256 in the manifest, together with the drawn
    file lists.

### H. Test procedure (per speaker model; a restart is a separate OS process, a power cycle on the board)

H1. P1: start from no state file; enrol commands 1-3 from the 15 S1 clips; save state A (size, SHA-256).
H2. P2: fresh process loading only state A; decide all 90 fresh positives of commands 1-3 (S2-S4), all
    600 negatives, and the 30 command-4 test clips (which at this point are unfamiliar speech and are
    reported as an extra negative stratum). Run P2 twice: outputs must be byte-identical.
H3. P3: fresh process loading state A; enrol command 4 from its 5 S1 clips, no recompilation, same
    executable and hyperparameters; save state B (size, SHA-256). B1 is measured on state B.
H4. P4: fresh process loading only state B; decide all 120 positives and the same 600 negatives.
H5. Controls (same clips, same frozen hyperparameters, same thresholds):
    - Untrained: the executable with no state (or a 0-epoch state); decide the 270 positives and the 600
      negatives.
    - Constrained example-level permutation: 5 seeds; each permutes the 15 enrolment labels uniformly
      among permutations in which, for every word, the modal label is unique and differs from the true
      label; train, decide the 270 positives.
    - Unconstrained example-level permutations: 20 seeds, uniformly random permutations; the full
      distribution of accuracy and accept rate is reported with the permutation p-value
      p = (1 + #{perm acc >= observed}) / 21. This is reported, not gated (see Part 1, item 7).
H6. DTW baseline: a compact-template method (MFCC + DTW nearest template, same front-end budget rules,
    same clips, same phases P1-P4, same byte accounting, its own frozen threshold from the same dev set).

### I. Pass rules (pre-registered; all must hold)

I1. Accuracy, three commands (P2): pooled >= 243/270 (90.0%, CI 85.8-93.3%) **and** every one of the 9
    cells >= 24/30 (80%). Operating characteristic at true accuracy 90 / 92 / 93 / 95 / 97%: pass
    probability 0.50 / 0.86 / 0.95 / 0.99 / 1.00 (iid); with day-to-day drift of sd 5 points per session:
    0.47 / - / 0.87 / 0.95 / 0.97. The proposal's per-cell 27/30 rule at a true 95% passes with 0.57.
I2. False accepts (P2, state A): pooled <= 18/1,800 (1.00%, CI 0.59-1.58%, upper95 1.48%) **and** each
    speaker <= 12/600 (2.0%) **and** the own-voice strata N1+N2+N3 pooled over speakers <= 12/600.
    Operating characteristic of the pooled rule at true rate 0.5 / 0.75 / 1.0 / 1.5 / 2.0%: 1.00 / 0.91 /
    0.56 / 0.04 / 0.00. State the claim honestly: "point estimate <= 1.0%, demonstrated below 1.5% at 95%
    confidence". If the collaborator insists on *demonstrating* < 1%, the pooled count must be <= 4/1,800
    (upper95 0.51%), which a system at a true 0.5% passes only 5.5% of the time (at a true 0.25%: 53%),
    or the set must grow to about 1,950 negatives with <= 12 accepts (free for public strata, 4 more
    own-voice sessions otherwise).
I3. Fourth command (P4, state B): all 12 cells pooled >= 324/360 **and** every cell >= 24/30 **and** the
    4th command alone >= 81/90 **and** I2 re-evaluated on the same 1,800 negatives with state B **and**
    no material forgetting: on the original 270 clips, (errors after) - (errors before) <= 5 (the exact
    McNemar one-way boundary is 6 net discordant clips, p < 0.05).
I4. Budget: B1 holds on state B; B4 strace log clean; B6 rebuild identical.
I5. Untrained control: accuracy on the 270 positives <= 114/270 (42.2%, the 99.9th percentile of chance
    at 1/3); accept rate on negatives reported. (A system that rejects everything scores 0% here and 0%
    false accepts; that is why I1 and I2 are both gates.)
I6. Constrained-permutation control: accuracy <= 114/270 on every one of the 5 seeds (a learner that uses
    the labels scores near 0% here; a leak, e.g. labels in filenames or test clips in training, scores near
    the trained figure).
I7. Disclosure (F1, F2, B4, B6, D1 list, G manifest, QA counts, exclusions) complete and published with
    the raw decision table (one row per clip x system x phase x control) and the recordings where consented.

### J. Analysis and reporting

J1. Every rate as k/n with exact 95% CI, pooled and broken down by speaker, command, session and stratum.
J2. Independence caveat stated: the 30 clips per cell come from 3 sessions; per-session results shown; the
    drift simulation in I1 shows how much this costs.
J3. DTW vs network: paired on identical clips; exact McNemar on discordant pairs (6 one-way discordant
    clips is the smallest significant split); difference in accuracy with a seeded 2,000-resample
    bootstrap CI over clips. On 270 clips at ~93% with ~22 discordant pairs, a 16-vs-6 split (3.7 points)
    is the smallest detectable difference, so "no significant difference" is not evidence of equality.
J4. The dev DET curves of both methods are published so readers can see whether a joint operating point
    for I1 and I2 existed before the freeze.

### K. Interpretation rules (pre-registered)

K1. Network passes I1-I7: the challenge claim holds for the trainable network.
K2. DTW passes, network fails: the method-agnostic claim ("an initially untrained system learns three
    commands from five examples, rejects unfamiliar speech, persists, within 32 KiB") is established,
    since storing exemplars and updating weights are both learning from examples and the untrained and
    permutation controls apply equally to DTW; but the specific claim "a trainable network is the right
    tool at this size and at five shots" is falsified for this task, and the report must say so rather
    than promote the network on a secondary metric. The failure is then attributed from the dev set
    (endpointing vs classification vs rejection calibration), not by re-running the test.
K3. Neither passes: report, with the component attribution from the dev set.
K4. Network passes, DTW fails: report.
K5. Prior stated now so the outcome cannot be re-narrated: at 5 examples per class, MFCC + DTW nearest
    template is the textbook solution and the prior favours K2 or "both pass". The network's weak point is
    rejection: the softmax of an MLP fitted to 15 points is not a calibrated probability, so a frozen global
    threshold is unlikely to satisfy I1 and I2 simultaneously without an auxiliary score (distance to the
    enrolment examples, leave-one-out calibration from the 5 clips, or the Tier B seeded garbage class).

### L. Feasibility summary

L1. Speaker time: about 1 h each over four days for 4 candidates; dev speaker about 1.5 h; QA about 2 h;
    test run about 1 day. Calendar: >= 3 weeks after the freeze. Recruiting 4 people for four short visits
    is realistic in a workplace or household; the dropout risk is handled by the spare and rule F8.
L2. Public negatives cost no recording time, which is why the negative set can be 1,800 rather than 900.
L3. The time-critical path is the freeze: nothing from the test speakers may be used before it.
