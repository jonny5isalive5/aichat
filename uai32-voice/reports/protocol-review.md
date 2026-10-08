# Investigation report: protocol-review

Verbatim final report of the investigating agent (2026-10-07). Paths it cites were under the session scratch space; the preserved copies are in this directory tree.

## Summary

I read uai32/README.md and uai32.c (a 229-line one-hidden-layer MLP that consumes pre-extracted numeric feature rows, so the voice challenge adds a front-end, time segmentation and a rejection decision that uai32 itself does not have), then checked every number in the proposed acceptance conditions with a self-contained exact-binomial Python script (no scipy available; Clopper-Pearson by bisection, Wilson, operating characteristics, Monte Carlo for the combined rules, exact enumeration over label permutations). The headline findings: "<= 1% false accepts on 300 recordings" cannot demonstrate 1% (only 0/300 reaches an upper bound of 0.99%; 3/300 has upper bound 2.56%, and the rule passes a system with a true 1% rate 65% of the time and a true 2% rate 15% of the time); showing < 1% needs 299 trials with zero false accepts or ~1,050 with <= 5, and 80% power at a true 0.5% needs ~1,950 trials. The ">= 90% per command on 30" rule (27/30, CI 73.5-97.9%) applied to 9-12 cells fails a genuinely 95%-accurate system 43-53% of the time by multiplicity alone. The proposed example-level shuffled-label control is not a chance-level control at 15 enrolment clips: exact enumeration shows a perfect learner scores 100% on the test set under a random permutation with probability 0.080 and >= 67% with probability 0.253, so a single shuffled run cannot be a gate; I replace it with a constrained permutation (every word's modal label wrong) plus a reported 20-permutation distribution. The negative set must be dominated by same-speaker, same-device confusable words, because other-voice public clips are rejected on channel/voice mismatch alone; I specify 600 negatives per speaker (200 own-voice recorded, 400 public from Speech Commands v0.02 testing_list, background-noise crops and other test speakers' non-shared words), 1,800 pooled, with the gate pooled <= 18/1,800 and own-voice <= 12/600, honestly described as "point estimate <= 1%, demonstrated below 1.5%". Accuracy gate becomes pooled >= 243/270 plus a per-cell floor of 24/30 (pass probability 0.50/0.95/0.99 at true 90/93/95%), with a 12-cell retest and a McNemar forgetting check after the fourth command. Thresholds and all hyperparameters are frozen (published hashes) on a development set from the developer and one non-test speaker before any test-speaker recording, and per-speaker thresholds may derive only from the 5 enrolment clips, otherwise the five-example claim is void. "Initially untrained" is defined as code plus formula-derived DSP constants plus <= 16 named scalar hyperparameters; shipped generic negatives are learned state and are allowed only as a counted, disclosed Tier B variant reported beside Tier A. The host may capture and resample only; the system receives a full 2.5 s raw clip with the word at an uncontrolled position, with an strace log proving no other input, because segmentation is where host-side help would silently do the work. Byte accounting is on-disk size of all solution files plus the state file at 4-command capacity, strictly below 32,768; the board gate separately budgets flash (whole image minus mask-ROM bootloader) and measured peak RAM. Recording takes about 1 h per speaker across 4 sessions on 4 days within 3 weeks, with 4 recruits for 3 needed, blind QA of clips, randomised interleaved prompting and consented public release. The pre-registered interpretation states that DTW passing while the network fails establishes the method-agnostic claim but falsifies "a trainable network is the right tool at five shots", and declares that prior up front.

## Measurements

- False accepts k/300: 0 -> CP95 [0.00%, 1.22%], one-sided upper95 0.99%; 1 -> [0.01%, 1.84%], upper95 1.57%; 2 -> [0.08%, 2.39%], upper95 2.08%; 3 -> [0.21%, 2.89%], upper95 2.56% (exact binomial, bisection, intervals.py section A)
- Rule 'pass if <= 3/300' passes a system with true FA rate 0.5% / 1% / 1.5% / 2% / 3% with probability 0.935 / 0.647 / 0.340 / 0.149 / 0.020 (binomial cdf)
- Smallest n whose upper95 <= 1% given k observed: k=0 n=299, k=1 n=473, k=2 n=628, k=3 n=773, k=5 n=1049, k=10 n=1693; for <= 2%: 149/236/313/386; for <= 0.5%: 598/947/1258/1549
- 80% power to show p < 1% (one-sided alpha 0.05): n = 780 with pass if k <= 3 when true p = 0.25%; n = 1,950 with pass if k <= 12 when true p = 0.5%
- 27/30 = 90.0%: CP95 [73.47%, 97.89%], Wilson [74.38%, 96.54%], one-sided lower95 76.14%; 30/30 lower95 = 90.50%; 24/30 CP95 [61.43%, 92.29%]; 243/270 CP95 [85.78%, 93.31%]; 324/360 CP95 [86.43%, 92.90%]
- Per-cell 27/30 rule: P(cell passes) at true accuracy 90/93/95/97% = 0.647/0.845/0.939/0.988; all 9 cells 0.020/0.220/0.569/0.898; all 12 cells 0.005/0.133/0.471/0.866
- Recommended rule (pooled >= 243/270 AND every cell >= 24/30), Monte Carlo 20,000 reps: pass probability at true 88/90/92/93/95/97% = 0.162/0.502/0.860/0.947/0.994/1.000; with per-session Beta drift sd 0.05: 0.467/-/-/0.868/0.949/0.974
- 12-cell retest rule (pooled >= 324/360 AND every cell >= 24/30): pass probability at true 90/92/93/95% = 0.471/0.861/0.946/0.993
- Recommended FA rule pooled <= 18/1800: point 1.00%, CP95 [0.59%, 1.58%], upper95 1.48%; pass probability at true 0.5/0.75/1.0/1.5/2.0% = 0.998/0.909/0.562/0.043/0.001; per-speaker floor <= 12/600 holds for all three speakers with probability 0.975 at true 1%, 0.191 at true 2%
- Stricter rule <= 4/1800 (upper95 0.51%): pass probability 0.964 / 0.532 / 0.055 at true 0.1% / 0.25% / 0.5%
- Example-level label permutation, 3 words x 5 enrolment clips, exact enumeration with an ideal majority-label learner: P(test acc = 0) 0.333, (= 1/3) 0.414, (= 2/3) 0.172, (= 1) 0.080; P(acc >= 2/3) = 0.253; with 20 permutations P(at least one scores 100%) = 0.813; 4 words x 5: P(acc = 1) 0.012, P(acc >= 3/4) 0.066
- Chance band for an untrained/permuted control: 3 classes on 270 clips, central 95% [75/270 = 27.8%, 105/270 = 38.9%], 99.9th percentile 114/270 = 42.2%; 4 classes on 360 clips 99.9th percentile 116/360 = 32.2%
- Paired DTW-vs-NN comparison: exact McNemar needs 6 one-way discordant clips for p < 0.05 (p = 0.031); with ~22 discordant pairs on 270 clips a 16-vs-6 split (3.7 accuracy points) is the smallest detectable difference
- Recording budget per speaker at 5 s per prompted item: 20 enrolment + 12 sanity + 120 test positives + 200 own-voice negatives = 352 items = 29 min prompting, ~49 min with setup, over 4 sessions on 4 days; ~3.3 h total speaker time for 4 recruits; public negatives cost 0 recording minutes
- uai32 facts used: executable 9,188 B; model file = 8 + 8*NI + 2*(NH*(NI+1) + NO*(NH+1)) bytes; it reads only text feature rows, so segmentation/front-end/rejection are outside the existing program and must be counted in the voice budget

## Recommendation

# Corrected protocol (numbered, ready to adopt). Full text also at protocol.md; arithmetic in intervals.py / intervals_output.txt.

## Part 1. Defects in the proposal as written
1. "<= 1% false accepts on 300" cannot show 1%: 0/300 -> upper95 0.99% (CI 0-1.22%); 1/300 -> 1.57% (CI 0.01-1.84%); 2/300 -> 2.08% (CI 0.08-2.39%); 3/300 -> 2.56% (CI 0.21-2.89%). "Pass if <= 3/300" passes a true-1% system 65% of the time and a true-2% system 15% of the time. Showing < 1% at 95% confidence needs 299 trials with 0 FA, 473 with <= 1, 628 with <= 2, 773 with <= 3, 1,049 with <= 5, 1,693 with <= 10; 80% power needs ~780 (<= 3) at a true 0.25% or ~1,950 (<= 12) at a true 0.5%. A test on the boundary is a coin flip at any n.
2. ">= 90% per command on 30" (27/30: CI 73.5-97.9%, Wilson 74.4-96.5%, lower95 76.1%; even 30/30 has lower95 90.5%) is applied per cell: 9 cells, then 12. A true-95% system passes one cell with 0.939, all 9 with 0.57, all 12 with 0.47; a true-93% system 0.22/0.13. The rule fails good systems about half the time and does not say why.
3. The negative set is undefined and is the whole test: other-voice/other-mic clips are rejected on voice and channel mismatch; the hard negatives are the same speaker on the same device saying confusable words.
4. "Thresholds fixed before final testing" does not say on what data; per-speaker thresholds tuned on extra recordings of the test speakers void the five-example claim.
5. "Initially untrained" is undefined (trained VAD, corpus normalisation statistics, PCA bases, shipped garbage examples are all learned state).
6. Segmentation loophole: a host that hands over a one-second window centred on the word has done the hardest part outside the budget.
7. The example-level shuffled-label control is not a chance-level control at n = 15: under a random permutation an ideal learner scores 0% w.p. 0.333, 33% w.p. 0.414, 67% w.p. 0.172, 100% w.p. 0.080; with 20 permutations, P(at least one scores 100%) = 0.81. A single shuffled run cannot be a gate, and "trained beats all 20 permutations" fails a perfect system.
8. No one-shot rule, no seeds, no publication of recordings/manifests/decision tables.
9. Cross-speaker same-word utterances are undefined (false accept or hit?).
10. "Retains learning after restart" needs a process-boundary definition, byte-identity, and a forgetting check after the fourth command.
11. Accuracy and FA share one threshold: both gates must be met at one frozen operating point; a system must not meet the FA gate by rejecting more positives.

## Part 2. Protocol
### A. Definitions
A1. System = executable file(s) + persistent state file. Host = capture, resampling to the declared format, delivery of raw PCM, nothing else.
A2. Clip = 2.5 s raw LE16 PCM mono 16,000 Hz = 40,000 samples = 80,000 bytes; the word starts wherever the speaker said it (no alignment, no trimming).
A3. Decision = exactly one of {command 1..C, REJECT}. A positive clip is correct only if the decision equals its command (substitution or REJECT = error). A negative clip is a false accept if the decision is anything but REJECT.
A4. Cell = (speaker, command); 30 fresh test clips per cell.
A5. Every rate reported as k/n with exact two-sided 95% Clopper-Pearson CI; gates are stated as counts.
### B. Byte budget (desktop gate)
B1. Count = sum of on-disk sizes (wc -c) of every non-OS file the system needs (executables, scripts, config) plus the state file measured after the fourth command is enrolled (declared capacity C >= 4 commands x 5 examples). Strictly < 32,768.
B2. If state grows with examples, count the worst case at declared capacity; the state-file length must be a function of its own header (as uai32) so it can be checked by formula.
B3. Excluded: kernel, libc/libm, dynamic loader, shell, the host capture program (restricted by F). Included: all hyperparameters, thresholds, constants, wherever stored.
B4. The executable may read only its state file and the clip (stdin or one named file). Each test phase runs in an empty directory under strace -f -e trace=openat,open,read,execve; log published. No network, env vars, /proc, other files.
B5. Packers allowed (decompressor inside the counted file); external decompressors not.
B6. Reproducible build: compiler+version, flags, source SHA-256, executable SHA-256 published at the freeze; a rebuild must be byte-identical.
### C. Board gate (later; separate declared numbers)
C1. Flash: whole application image (code, constants, drivers/HAL, persistent-state region at capacity) <= declared flash budget (recommend 32,768). Only the silicon vendor's mask-ROM bootloader is excluded, by name.
C2. RAM: peak of .data + .bss + stack high-water (stack painting) + heap during enrolment and recognition, including the capture buffer, <= declared RAM budget (declare; 16 KiB is a reasonable Cortex-M0+ figure).
C3. Declare whether test audio reaches the board digitally (tests the algorithm) or acoustically at declared distance/level (tests the device); the headline says which.
C4. Latency and energy per decision reported, not gated.
### D. "Initially untrained"
D1. Tier A permitted: code; closed-form DSP constants from published formulas (window, mel filterbank, DCT); at most 16 named scalar hyperparameters (frame size, hop, coefficient count, hidden size, learning rate, epochs, threshold(s), augmentation settings), each listed with its value.
D2. Not permitted in Tier A: any array derived from speech/audio data (weights, codebooks, PCA/LDA bases, corpus mean/variance, trained VAD, templates other than those created at enrolment).
D3. Runtime adaptation from the user's own data is permitted (noise floor from the clip, normalisation from enrolment clips, leave-one-out thresholds from the 5 enrolment clips).
D4. Per-speaker thresholds may derive only from that speaker's enrolment clips; otherwise thresholds are global constants (D1). No other per-speaker tuning.
D5. Shipping generic negatives (e.g. 32 feature vectors from public data) violates "initially untrained". Allowed only as a declared Tier B variant: counted in the budget, built from listed Speech Commands v0.02 files (paths + SHA-256) disjoint from all negative test files, reported beside Tier A. The headline claim is Tier A.
D6. The untrained control (H5) checks D1-D2 empirically.
### E. People, development set, freeze
E1. 1 developer; 1 development speaker (not a test speaker); 4 test candidates (3 needed + 1 spare); 1 QA listener who is not the developer; 1 person who runs the frozen test (may be the QA listener). Test speakers never contribute to tuning.
E2. Development set: developer's voice + development speaker, each 10 fresh clips per command for 3 (+1) commands, 200 own-voice negatives (recipe G), public negatives from Speech Commands validation_list.txt only (testing_list.txt reserved for the test draw). All feature/architecture/training/threshold choices happen here. Plot the dev DET curve and pick the operating point before freezing.
E3. Freeze: commit source; publish SHA-256 of executable, hyperparameter list, negative-set manifest and seeds, prompt lists, and this protocol with its pass rules, before the first test-speaker session; record commit + public timestamp.
E4. One shot: each pre-registered configuration (Tier A, optional Tier B, DTW baseline) runs on the test set exactly once; any change afterwards needs fresh S2-S4 sessions or is labelled post-hoc and does not count.
E5. Seeds for enrolment training, permutations and negative draws are fixed in the manifest.
### F. Recording procedure and host-side rules
F1. One fixed device per speaker (model named), same device/room/distance in all sessions. Capture 16 kHz 16-bit mono, or 48 kHz resampled by a named library+version. OS/driver AGC, noise suppression, echo cancellation OFF, fixed gain, all disclosed. Distance 30-50 cm. Ambient < 45 dBA (phone SPL meter, value reported).
F2. Host may: open device, capture, resample, write raw PCM. Host may not: normalise gain, trim, VAD/endpoint, filter, denoise, compute features. The system gets the full 2.5 s clip with the word wherever it fell; disclosure states this and B4's strace log shows it.
F3. Rationale: segmentation is the hidden hard part. Public corpora hand you a one-second window with the word roughly centred; in use the word starts anywhere and lasts 0.3-0.8 s, the system must find it (energy endpointing is fragile for fricative/plosive onsets and under noise) and time-normalise it; these errors dominate. Descriptive requirement: on 60 dev clips with hand-marked onsets, report the distribution of detected-onset error.
F4. Sessions: 4 per test speaker on 4 different calendar days, each >= 24 h apart, all within 21 days. Seeded prompter (seed = speaker id x 10 + session) shows one prompt at a time in randomised interleaved order of positives and negatives, beeps, captures 2.5 s starting 0.5 s after the prompt. Files have opaque ids; the label manifest is sealed; the system never sees a label.
  S1 (day 1): enrolment 5 clips x 4 commands (commands 1-3 and the future 4th, recorded now, command 4 not fed until P3); 12 pipeline-sanity clips; 50 own-voice negatives.
  S2, S3, S4 (earliest days 2, 4, 7): per session 11 clips per command x 4 commands (first 10 valid per command are test clips, the 11th a spare) + 50 own-voice negatives.
  About 100 items x 5 s = 8-9 min prompting + 5 min setup = ~15 min per session; ~1 h per speaker over four days; ~4 h speaker time for four candidates; the real cost is >= 3 weeks of calendar and four visits per person.
F5. Commands: each speaker chooses 4 distinct words/short phrases of 1-3 syllables; at least 2 of 4 must be Speech Commands v0.02 vocabulary (yes, no, up, down, left, right, on, off, stop, go, zero-nine, bed, bird, cat, dog, happy, house, marvin, sheila, tree, wow, backward, forward, follow, learn, visual) so public confusables exist. Before S1 the experimenter pre-registers per command 3 own-voice confusables (minimal pairs/rhymes: stop -> top, shop, stock; go -> no, so, goat; left -> lift, let, laughed) and the 5 nearest Speech Commands words (on/off, go/no, tree/three, four/forward/follow, bed/bird, up/off).
F6. QA: the QA listener audits every clip for truncation/mis-speak before any system output exists and blind to it; invalid clips replaced from spares; counts reported (expect < 3%).
F7. Consent for CC BY 4.0 release of clips requested; decliners still usable; report says whose audio is public.
F8. A speaker who misses a session is replaced by the spare; speakers with < 4 sessions are excluded and the exclusion reported.
### G. Negative set (600 per speaker model; 1,800 pooled)
G1. N1 own-voice confusables: 120 = 3 confusables x 4 commands x 10 repeats over S1-S4.
G2. N2 own-voice unrelated words/short phrases: 60 (fixed list of 20 x 3).
G3. N3 own-voice non-speech: 20 (cough, laugh, "hmm", throat clear, typing, silence with room noise, same pipeline).
G4. N4 Speech Commands v0.02 word clips: 300 drawn by seeded script from testing_list.txt: 150 from the pre-registered nearest-word lists, 150 uniform from other words; distinct files per speaker model (900 overall). Each 1 s clip is placed at a seeded random offset in a 2.5 s clip whose remainder is a seeded _background_noise_ crop at 30 dB below the speech. Clips of a word the speaker enrolled are excluded here and reported under G7.
G5. N5 _background_noise_ crops: 50 x 2.5 s, seeded, 25 at recorded level and 25 at +10 dB.
G6. N6 other test speakers' clips of their own commands/confusables, restricted to words this speaker did not enrol: 50, seeded.
G7. Cross-speaker same-word clips are neither false accepts nor hits; reported as a separate descriptive "cross-speaker acceptance" rate; pre-register the intended behaviour (recommended: personal system, should reject; not gated).
G8. The v0.02 tar.gz is pinned by SHA-256 in the manifest with the drawn file lists.
### H. Test procedure per speaker model (restart = separate OS process; power cycle on the board)
H1. P1: no state file; enrol commands 1-3 from the 15 S1 clips; save state A (size, SHA-256).
H2. P2: fresh process loading only A; decide the 90 fresh positives of commands 1-3, the 600 negatives, and the 30 command-4 test clips (reported as an extra negative stratum at this stage). Run P2 twice: byte-identical output required.
H3. P3: fresh process loading A; enrol command 4 from its 5 S1 clips with the same executable and hyperparameters, no recompilation; save state B (size, SHA-256); B1 is measured on B.
H4. P4: fresh process loading only B; decide all 120 positives and the same 600 negatives.
H5. Controls (same clips, frozen hyperparameters and thresholds): (a) untrained: executable with no state (or 0-epoch state) on the 270 positives and 600 negatives; (b) constrained example-level permutation, 5 seeds: labels permuted uniformly among permutations in which every word's modal label is unique and differs from the true label; train; decide the 270 positives; (c) unconstrained example-level permutations, 20 seeds: distribution of accuracy and accept rate with permutation p = (1 + #{perm acc >= observed})/21, reported not gated (Part 1 item 7).
H6. DTW baseline: MFCC + DTW nearest template, same front-end rules, same clips, same P1-P4, same byte accounting, its own frozen threshold from the same dev set.
### I. Pass rules (pre-registered; all must hold)
I1. Accuracy, 3 commands (P2): pooled >= 243/270 (90.0%, CI 85.8-93.3%) AND every one of 9 cells >= 24/30. Pass probability at true 90/92/93/95/97% = 0.50/0.86/0.95/0.99/1.00 (iid); with session drift sd 5 points: 0.47/-/0.87/0.95/0.97. (Proposal's per-cell 27/30 at true 95%: 0.57.)
I2. False accepts (P2, state A): pooled <= 18/1,800 (1.00%, CI 0.59-1.58%, upper95 1.48%) AND each speaker <= 12/600 AND own-voice strata N1+N2+N3 pooled <= 12/600. Pass probability at true 0.5/0.75/1.0/1.5/2.0% = 1.00/0.91/0.56/0.04/0.00. Claim wording: "point estimate <= 1.0%, demonstrated below 1.5% at 95% confidence". To demonstrate < 1% instead: pooled <= 4/1,800 (upper95 0.51%; a true-0.5% system passes only 5.5% of the time, a true-0.25% system 53%), or ~1,950 negatives with <= 12 accepts.
I3. Fourth command (P4, state B): 12 cells pooled >= 324/360 AND every cell >= 24/30 AND command 4 alone >= 81/90 AND I2 re-evaluated on the same 1,800 negatives with state B AND no material forgetting: on the original 270 clips (errors after) - (errors before) <= 5 (exact McNemar one-way boundary is 6, p < 0.05).
I4. Budget: B1 on state B; B4 strace log clean; B6 rebuild identical.
I5. Untrained control: accuracy on 270 positives <= 114/270 (42.2%, 99.9th percentile of chance 1/3); negative accept rate reported. (Reject-everything scores 0% here and 0% FA; hence both I1 and I2.)
I6. Constrained-permutation control: accuracy <= 114/270 on each of 5 seeds (a label-using learner scores near 0%; a leak scores near the trained figure).
I7. Disclosure complete (F1, F2, B4, B6, D1 list, G manifest, QA counts, exclusions) and published with the raw decision table (one row per clip x system x phase x control) and the consented recordings.
### J. Analysis and reporting
J1. Every rate as k/n with exact 95% CI, pooled and by speaker, command, session, stratum.
J2. Independence caveat: 30 clips per cell come from 3 sessions; show per-session results; the drift simulation in I1 quantifies the cost.
J3. DTW vs network paired on identical clips: exact McNemar on discordant pairs (6 one-way discordant clips is the smallest significant split); accuracy difference with a seeded 2,000-resample bootstrap CI over clips. On 270 clips near 93% with ~22 discordant pairs, a 16-vs-6 split (3.7 points) is the smallest detectable difference; "no significant difference" is not equality.
J4. Publish both methods' dev DET curves so readers can see whether a joint operating point for I1 and I2 existed before the freeze.
### K. Interpretation (pre-registered)
K1. Network passes I1-I7: the claim holds for the trainable network.
K2. DTW passes, network fails: the method-agnostic claim ("an initially untrained system learns three commands from five examples, rejects unfamiliar speech, persists, within 32 KiB") is established, since storing exemplars and updating weights are both learning from examples and the controls apply equally to DTW; but "a trainable network is the right tool at this size and five shots" is falsified for this task and the report must say so, not promote the network on a secondary metric. Attribute the failure from the dev set (endpointing vs classification vs rejection calibration), never by re-running the test.
K3. Neither passes: report with component attribution from the dev set. K4. Network passes, DTW fails: report.
K5. Prior stated now: at 5 examples per class MFCC + DTW nearest template is the textbook method; the prior favours K2 or both passing. The network's weak point is rejection: the softmax of an MLP fitted to 15 points is not calibrated, so one frozen global threshold is unlikely to satisfy I1 and I2 jointly without an auxiliary score (distance to enrolment examples in feature/hidden space, leave-one-out calibration from the 5 clips, or the Tier B seeded garbage class).
### L. Feasibility
L1. Speaker time ~1 h each over four days for 4 candidates; dev speaker ~1.5 h; QA ~2 h; test run ~1 day; calendar >= 3 weeks after the freeze. Four people for four short visits is realistic in a workplace/household; dropout handled by the spare and F8.
L2. Public negatives cost no recording time, which is why the set is 1,800 rather than 900.
L3. The critical path is the freeze: nothing from the test speakers may be used before it.

## Risks

- Any count-based gate sitting on its own target (true FA 1% vs target 1%; true accuracy 90% vs target 90%) is a coin flip regardless of n; the protocol therefore reports pass probabilities and states the claim as 'point <= 1%, demonstrated < 1.5%'; if the collaborator insists on 'demonstrated < 1%' the negative set must grow to ~1,950 or the count must be <= 4/1,800, which a system at a true 0.5% fails 94% of the time.
- The 30 clips per cell come from only 3 sessions of one speaker, so they are not independent; my drift simulation (sd 5 points per session) lowers the pass probability of the recommended accuracy rule from 0.95 to 0.87 at a true 93%; real day-to-day drift could be larger (colds, mood, position).
- Three speakers cannot support any speaker-population claim; results are three case studies, and a fourth-speaker generalisation of a global threshold tuned on the developer and one dev speaker is the biggest unmodelled risk.
- The shuffled-label control is intrinsically weak at 15 examples; the constrained permutation detects leaks but cannot measure 'learning strength' the way a large-n permutation test does, so the real evidence of learning is the untrained-vs-trained gap and the DTW comparison.
- Prior expectation (stated in K5) is that DTW/template matching beats a 15-example MLP on rejection calibration; the challenge should be ready to conclude that the method-agnostic claim holds while the 'trainable network' framing fails, and must not quietly move to secondary metrics.
- Segmentation is the dominant practical error source; even with F2 enforced, speakers who start talking before the beep or trail off produce clipped positives, which the blind QA step must catch (expected < 3%, but if the capture window is mis-timed it could be far higher and silently bias toward easy clips).
- Public Speech Commands negatives are channel-mismatched and therefore easy for a speaker-dependent system; the own-voice strata (600 pooled, gate <= 12) carry the real information, and 600 can only bound that stratum at ~3.2% (upper95 for 12/600).
- Recruiting: four visits on four separate days within three weeks per person is the realistic failure point; if a speaker completes only 3 sessions the protocol excludes them, which may drop the study to 2 speakers unless the spare is actually recorded in parallel.
- Speech Commands v0.02 details (35 words, 1 s 16 kHz clips, _background_noise_ folder with six files, validation_list.txt/testing_list.txt) are quoted from memory; the manifest must pin the archive hash and the exact file lists at freeze time rather than rely on this document.
- Tier B (shipped generic negatives) is a slippery slope toward pretraining; if used, the report must show Tier A results alongside, or the 'initially untrained' claim is compromised.

## Artifacts (original scratch paths)

- `/tmp/claude-0/-home-user-aichat/809e473e-6ead-51f0-b725-4e01dff2b821/scratchpad/voice-protocol-review/protocol.md`
- `/tmp/claude-0/-home-user-aichat/809e473e-6ead-51f0-b725-4e01dff2b821/scratchpad/voice-protocol-review/intervals.py`
- `/tmp/claude-0/-home-user-aichat/809e473e-6ead-51f0-b725-4e01dff2b821/scratchpad/voice-protocol-review/intervals_output.txt`
