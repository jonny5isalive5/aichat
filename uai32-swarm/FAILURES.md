# Preserved failure evidence and corrections

Things that did not work, were wrong on the first attempt, or are weaker than hoped. Kept on purpose.

1. **Peak-RSS measurement was wrong twice.** Measuring the uai32 child's RSS through Python's `subprocess`
   or `os.posix_spawn` reported about 50 MB for every command, including `/bin/true`, because the kernel
   charges a vfork-style child with its parent's pages at exec time. Fixed by spawning through
   `tools/maxrss.c`, a tiny C launcher: specialist process 2,244 KB against a 1,376 KB floor for `/bin/true`.
   The earlier numbers were discarded, not reported.
2. **The first router always chose the "noisy" expert.** Ranking candidates by distance-over-radius favours any
   specialist whose training inputs were widely spread, because its radius is large. In Stage 7 the noisy expert
   was selected for 294 to 299 of 300 inputs under every condition. Fixed by ranking with a diagonal-Gaussian
   score that charges for training spread (`0.5·mean(z²) + mean(log spread)`). The first Stage 6 run, made with
   the old ranking, was stopped at N = 1,000 and its partial output is kept as
   `results/stage6_superseded_old_router.json` / `.log` (routing accuracy there was 100% / 97.8% / 99.0% at
   N = 2 / 10 / 100; the support decision was unchanged by the fix).
3. **Input statistics cannot tell most conditions apart (Stage 7).** After the fix, the swarm detects the
   *shifted* condition (254 of 300 inputs to the shifted expert) but spreads normal, noisy, edge and adversarial
   inputs almost uniformly over the five experts, because those conditions leave the input distribution nearly
   unchanged. k = 3 arbitration recovers oracle-level accuracy in four of five conditions; under the *edge*
   condition every expert is below 50% and so is the swarm. The swarm cannot identify the best expert for noisy,
   edge or adversarial inputs from the inputs alone; this is a real limit, not a bug.
4. **Catastrophic forgetting is total.** A specialist continued-trained on a second domain for 40 epochs drops
   from 89% to 33% on its original domain (chance is about 25 to 35%). uai32 has no replay or regularisation;
   the swarm's protection against forgetting is isolation between files, not anything inside a brain.
5. **Composition baseline was first under-trained.** The single-brain baselines for the compound task were
   first trained on 3,000 rows for 40 epochs; they were given 5,000 rows (the same number the ten specialists
   saw in total) and 100 epochs before the reported run. They stayed at 40 to 45% against the swarm's 76%.
6. **Spawning clusters crudely.** The stretch goal commissions a new specialist from the buffered unsupported
   inputs by taking the points within 0.1 of the buffer's mean identifying coordinates, falling back to the
   neighbourhood of the first buffered point. With two unseen domains arriving together it spawned three
   specialists, one of them trained on a mixed cluster (domain 10 ends at 60%, domain 11 at 88%). A proper
   clustering step is a later improvement.
7. **Specialist accuracy is 83 to 85%, not 95%+.** The random teachers are harder than a 10-16-4 network
   trained with 500 rows and 60 epochs can fit exactly. This is the same brain everywhere, so comparisons are
   fair, but absolute numbers should be read with that in mind. A first version with 400 rows / 40 epochs
   reached 81 to 83%; the defaults were raised once, before any comparison was run.
8. **The orchestrator is not small.** Python + numpy sit at about 50 MB RSS and the per-query cost is
   dominated by starting a uai32 process (about 1.4 ms). The specialists themselves are 576 bytes and run in
   2.2 MB of process memory with an 816-byte working set. The honest total-RAM figure for this implementation
   is the Python figure; a C orchestrator is a later improvement, not an assumption used in any claim.
9. **Equal-storage monolith capped.** At N = 1,000 the equal-storage monolith would need about 19,000 hidden
   units (580 KB); training it with per-sample SGD on 400,000 rows was not feasible in the time available, so
   the comparison uses a 2,048-unit monolith (about 62 KB, roughly the storage of 107 specialists). The cap is
   reported in the table.
10. **The router did not scale in memory (found at N = 1,000, Stage 6).** The vectorised familiarity computation
    formed a rows × specialists × features tensor for the whole 50,000-row evaluation set: 50,000 × 1,000 × 10
    doubles, several times over, and the orchestrator's peak RSS reached 7,896,960 KB (7.9 GB) while accuracy
    was unaffected (84.3%, routing 98.7%). At N = 100 the same code needed 124 MB and at N = 10 42 MB, so the
    flaw was invisible below 1,000. Fixed by routing in chunks of 256 rows (peak temporary memory
    256 × N × 10 doubles). The unchunked run is preserved as `results/stage6_superseded_unchunked_router.json`
    / `.log`; the reported Stage 6 numbers come from the rerun with the chunked router.
11. **Orchestration overhead grows with N even after the fix.** Per-row Python work in `decide()` (building
    provenance records, grouping rows per specialist) was 0.002 ms/row at N = 2 and 0.84 ms/row at N = 1,000
    before the memory fix, more than ten times the specialist invocation itself (about 0.06 ms/row amortised in
    batches). This is the coordination layer, not the specialists, and it is the first thing to rewrite in C.
12. **Baseline models were not reproducible between runs.** `uai32 train` continues training when the model
    file already exists, and `Sentinel.create()` did not delete a stale file first, so monolith and compound
    baselines trained in an earlier run (sometimes by an earlier version of the code) were trained further in the
    next one: the equal-storage monolith at N = 2 scored 81.0%, 83.0% and 79.0% in three consecutive runs while
    every swarm number was identical. Found by comparing `results/stage6_superseded_*.json`. Fixed by deleting
    the file in `create()` and by starting `run_all.sh` from an empty `work/`; all stages were rerun from scratch
    for the reported numbers.
