# Pilot results: speaker SPEAKER, DATE

<!-- This is the shape of the report that run_pilot.py writes to OUTDIR/RESULTS.md.  Fill nothing by hand: every number comes from
     decisions.csv / summary.json.  k/n is always a count over a count; "[lo, hi]" is the exact two-sided 95% Clopper-Pearson interval.
     If the test stage was run more than once on the same OUTDIR the report starts with a POST-HOC RERUN banner and does not count. -->

Manifest seal SHA16; dtwapp SHA16; netapp SHA16; thresholds frozen DATETIME (dev decisions sha256 SHA16).  Recipe: DTW score margin|min;
network H hidden, E epochs, rate LR, AUG augmented copies, seed S, score prob|margin; target dev false-accept rate 1.0%.
Commands: 0=W1, 1=W2, 2=W3, 3=W4; held back until P3: W4.

## 1. Bytes: complete application plus required state (`wc -c`)

| arm | executable | state A (3 commands) | state B (4 commands, declared capacity) | application + state B | spare under 32,768 |
|---|---:|---:|---:|---:|---:|
| DTW | 7416 | 8 + 977 x 15 = 14663 (sha256) | 8 + 977 x 20 = 19548 (sha256) | **26964** | 5804 |
| network | 11500 | 5936 (sha256) | 5970 (sha256) | **17470** | 15298 |

Retained host-side for retraining the network (disclosed, not in the model): the 20 enrolment rows (bytes as text / as float32) and the
raw enrolment audio.  Peak RSS and the source-derived working set: `measure.sh --pilot OUTDIR MANIFEST` -> OUTDIR/measurements/.
Network training sets A and B: rows = enrolment + augmented + synthetic-unknown waveforms + segment-shuffled rows; final train accuracy.

## 2. Development phase (thresholds chosen here, then frozen)

| arm | score | frozen threshold | dev false accepts | dev recall (commands 1-3) | per command | dev closed-set (ignoring the threshold) | held-back command accepted |
|---|---|---:|---|---|---|---|---|
| DTW | margin | T | k/100 % [lo, hi] | k/30 % [lo, hi] | W1 k/10, W2 k/10, W3 k/10 | k/30 | k/10 |
| network | prob | T | k/100 % [lo, hi] | k/30 % [lo, hi] | ... | k/30 | k/10 |

Dev DET curves as CSV (threshold, accepts, n_neg, false_accept_rate, hits, n_pos, recall, frr), one per arm and candidate score:
`dev_det_dtw_margin.csv`, `dev_det_dtw_min.csv`, `dev_det_net_prob.csv`, `dev_det_net_margin.csv`; recall at dev false-accept
rates <= 0 / 1 / 2 / 5 / 10% listed for each.  The frozen score kind and threshold are the ones in thresholds.json; the others
are information for the attribution of errors (classification versus rejection calibration), never for a second attempt.

## 3. Test with state A (commands 1-3), P2: the pre-registered one-shot result

### Recall per command (decision = the enrolled command; a substitution or a REJECT is an error)

| command | DTW correct k/n [95% CI] | DTW closed-set | DTW substituted / rejected | network correct k/n [95% CI] | network closed-set | network substituted / rejected |
|---|---|---|---|---|---|---|
| W1 | k/30 % [lo, hi] | k/30 | s / r | k/30 % [lo, hi] | k/30 | s / r |
| W2 | ... | | | | | |
| W3 | ... | | | | | |
| **pooled** | k/90 % [lo, hi] | k/90 | s / r | k/90 % [lo, hi] | k/90 | s / r |

<!-- correct + substituted + rejected = n.  "closed-set" = label of the best class ignoring the threshold (what the recogniser would
     say if forced); correct <= closed-set.  The gap closed-set minus correct is the price of rejection at the frozen threshold. -->

### False accepts on the own-voice negatives (measured rate and demonstrated bound are different quantities)

| arm | stratum | accepts k/n | measured false-accept rate: point estimate [95% CI] | bound demonstrated: one-sided 95% upper limit | n needed for the bound to reach 1%: at this count / at this rate |
|---|---|---|---|---|---|
| DTW | confusable | k/180 | % [lo, hi] | % | N1 / N2 |
| DTW | unrelated | k/120 | % [lo, hi] | % | N1 / N2 |
| DTW | all own-voice negatives | k/300 | % [lo, hi] | % | N1 / N2 |
| network | confusable | ... | | | |
| network | unrelated | ... | | | |
| network | all own-voice negatives | ... | | | |

<!-- Never merge the two middle columns.  "measured false-accept rate" is what happened: k of n negatives were accepted, with the
     interval of the rate consistent with that count.  "bound demonstrated" is the one-sided 95% upper limit: the largest true rate
     that is still consistent with observing <= k in n at the 5% level; a claim "false accepts <= 1%" is DEMONSTRATED only when this
     column is <= 1%.  With 300 negatives that needs 0 accepts (upper 0.99%); 1/300 gives 1.57%, 3/300 2.56%.  The last column says
     what n would have been needed: at this count = keeping k fixed; at this rate = keeping k/n fixed ("never" when k/n >= 1%, since
     the bound can then never fall below the rate). -->

The held-back command W4 as unfamiliar speech at P2 (extra stratum, not pooled above): DTW accepted k/30, network accepted k/30.

### Restart test (P2 run twice: fresh processes loading only the saved state)

- DTW: raw outputs of the two runs byte-identical / DIFFER (sha256); state file unchanged / MODIFIED by scoring.
- network: raw outputs (predict line plus the sha256 of the re-extracted feat row per clip) byte-identical / DIFFER; state file unchanged / MODIFIED.

## 4. Test with state B (all 4 commands), P4

Recall per command (4 rows + pooled over 120) and false accepts on the same 300 negatives, same columns as section 3.

### Forgetting on the 90 original test clips of commands 1-3 (P2 -> P4)

| arm | errors before | errors after | became wrong | became right | net change | exact McNemar one-sided p (more became wrong) |
|---|---:|---:|---:|---:|---:|---:|
| DTW | e0 | e1 | b | c | e1 - e0 | p |
| network | e0 | e1 | b | c | e1 - e0 | p |

<!-- protocol I3: "no material forgetting" = net change <= 5 (the exact one-way McNemar boundary is 6 net discordant clips, p < 0.05). -->

## 5. Controls (same clips, same frozen thresholds)

Chance for 90 positives at 1/3 is 33.3%; the 99.9th percentile of chance is 45/90.

| control | DTW accuracy | DTW closed-set | DTW false accepts | network accuracy | network closed-set | network false accepts |
|---|---|---|---|---|---|---|
| untrained (no state / 0 epochs) | 0/90 (rejects everything) | 0/90 | 0/300 | k/90 | k/90 | k/300 |
| constrained permutation seed 0..4 (labels ...) | k/90 | k/90 | k/300 | k/90 | k/90 | k/300 |

A constrained permutation whose accuracy exceeds the chance bound is flagged: it means the labels leaked (file names, test clips in
training).  Then the unconstrained permutations (reported, not gated): accuracy min / median / max, closed-set, false accepts,
the observed P2 accuracy and the permutation p-value (1 + #{permuted >= observed}) / (N + 1).

## 6. DTW versus network, paired on identical clips (exact McNemar)

- P2: DTW k/90 correct, network k/90 correct; DTW-only correct b, network-only correct c, two-sided p.
- P4: the same over 120.

## 7. Disclosures

Host-side centring of the utterance (record.py), host-side numpy augmentation and synthetic unknown class for the network from the
enrolment audio only, retraining (not continual learning) for the 4th command, labels seen only at enrol/train, thresholds frozen
before the test clips were scored, the strace file list of one decision per arm, and where the raw decision table, states and log are.
