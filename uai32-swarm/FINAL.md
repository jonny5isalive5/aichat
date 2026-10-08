# Final determination

*Numbers below are from `results/REPORT.md` (seed 1, gcc 13.3 / glibc 2.39 x86-64, released uai32 v1.0.0).
The Stage 6 table is from the rerun with the chunked router; see FAILURES.md items 10 and 11.*

## What was proven

| success criterion | evidence | verdict |
|---|---|---|
| 1. Two identical brains diverge through different experiences | Stage 1: one SHA-256 at start; different after training on different domains; a third clone given the same experience stays byte-identical; each clone scores 84 to 87% on its own domain and 18 to 27% on the other's; the two answer differently on 80% of inputs | proven |
| 2. Learning persists | Stage 1: fresh processes reproduce every output from the files; hashes unchanged by use; Stage 8: hashes change only when a specialist is trained | proven |
| 3. Specialists coexist independently | Stage 8: training one specialist leaves the other nine files byte-identical; a corrupted file is caught by its hash and excluded; removal deletes one file | proven (isolation is structural: one file per brain) |
| 4. A lightweight router selects useful specialists | Stages 2 and 6: routing accuracy 97.8 to 100% from 2 to 1,000 specialists using only per-specialist centroid, spread and radius; about 1 KB of routing data per specialist; no model file opened to route | proven |
| 5. Multiple specialists contribute to one task | Stage 3: weighted vote of three same-domain experts raises accuracy from 82.0% to 86.9% (normal inputs); Stage 4: two specialists composed through a table reach 76.4% on a task no single specialist can read | proven |
| 6. Disagreement is exposed or arbitrated | Stage 3: 3.3% (normal) and 8.2% (edge) of inputs flagged as disagreements with both sides and their supporters recorded; accuracy on flagged inputs is 46 to 47%, so the flag is informative | proven |
| 7. The system says when no suitable expert exists | Stage 2: 100% of inputs from three never-seen domains and 100% of uniform noise marked unsupported; Stage 6: 94 to 100% of out-of-distribution inputs unsupported at every N, 1 to 2% of in-domain inputs wrongly refused | proven |
| 8. Add, replace, retrain, clone, remove independently | Stage 8: all six operations performed and verified by hash and accuracy; branching one expert into two gives three distinct hashes and condition-specific behaviour | proven |
| 9. Scales materially beyond a handful | Stage 6: 1,000 specialists, 2.6 MB of storage, task accuracy 84.3%, routing 98.7%, 3,054 uai32 processes, no failed invocation; run-to-run reproducible | proven, with one flaw found and fixed (router memory) |
| 10. Total resource cost keeps the Mini Sentinel advantage | per specialist 576 B model + ~1 KB metadata; a specialist runs in a 2.2 MB process (1.4 MB of which is glibc floor) with an 816-byte working set; 1,000 specialists cost 10,224 multiply-adds per query including routing | proven for the specialists; the Python orchestrator is the expensive part (see boundary) |

## What remains unproven or failed

- **Choosing among experts for the same domain by condition.** Input statistics detect a distribution shift
  (254 of 300 shifted inputs routed to the shifted expert) but cannot separate normal, noisy, edge and adversarial
  inputs; the swarm reaches oracle accuracy only through k = 3 arbitration, and under edge conditions every
  expert and the swarm are below 50% (Stage 7).
- **Forgetting inside a specialist is total** (89% → 33% after learning a second domain). The swarm has no
  mechanism against it other than isolation and retraining from the canonical brain (Stage 8).
- **Spawning works but clusters crudely**: two unseen domains arriving together produced three specialists,
  one of them mixed; the niche ended at 60% and 88% accuracy (stretch).
- **The equal-storage comparison at N = 1,000 is capped.** The fair monolith would need about 19,000 hidden
  units; the trained one has 2,048 (62 KB, the storage of about 107 specialists) and reaches 31.3%. At N = 100,
  where the fair monolith (1,917 units, 57.6 KB) was trained, it reaches 56.7% against the swarm's 85.1%.
- **Real workloads were not tested.** All domains are synthetic random teachers chosen to partition cleanly.

## The final question

*Can a large population of tiny, separately trained specialists provide useful broad capability through
routing and composition at substantially lower resource cost than a monolithic model for the same constrained
workload?*

**Yes, for workloads that partition into recognisable domains, and the boundary is the coordination layer,
not the specialists.**

Quantified, on this workload (N domains, each a different nonlinear 4-class rule on 6 condition features):

| N | swarm accuracy | same-size monolith (576 B) | equal-storage monolith | swarm storage | swarm MACs/query | monolith MACs/query |
|---|---|---|---|---|---|---|
| 2 | 84.0% | 81.0% | 81.0% (1.1 KB) | 5.2 KB | 244 | 490 |
| 10 | 83.2% | 65.8% | 79.2% (5.8 KB) | 26 KB | 324 | 2,646 |
| 100 | 85.1% | 31.8% | 56.7% (57.6 KB) | 262 KB | 1,224 | 26,838 |
| 1,000 | 84.3% | 25.9% | 31.3% (61.5 KB, capped) | 2.6 MB | 10,224 | 28,672 |

- The swarm's accuracy is flat in N; both monoliths fall with N. At 100 domains the swarm beats a monolith of
  the same total storage by 28 points while using 22 times fewer multiply-adds per query, and beats the
  same-size monolith by 53 points.
- Composition adds capability no single brain has: 76% versus at most 45% for brains trained directly on the
  compound task with the same data.
- The cost that does not stay small is coordination: the Python orchestrator uses 38 MB at N = 2 and 487 MB
  at N = 1,000 (after the router was chunked; it needed 7.9 GB before), routing costs 2 µs per row at N = 10
  and 301 µs at N = 1,000, and per-row orchestration overhead (0.12 ms at N = 1,000) is twice the specialist
  invocation itself (0.05 ms, amortised in batches). The specialists keep the Mini Sentinel advantage; the
  orchestrator must be engineered with the same discipline, which this Python implementation does not.
- Below about 10 domains the advantage is small (84.0% vs 81.0% at N = 2); the architecture earns its keep
  when the workload is wide.

Where it fails: when the domain cannot be recognised from the input (populations under noise, edge or
adversarial conditions), the router has no signal and the swarm degrades to voting; and when a specialist
must learn a second task, it forgets the first. Both are properties of this routing signal and this brain,
not of the swarm structure, and both were measured rather than argued away.
