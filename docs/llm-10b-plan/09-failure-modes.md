## 09. Failure modes, mitigations and runbooks

Covers: potential failure modes and mitigation strategies, with the executable guard in `code/loss_spike_guard.py`. Risk ranking and reserves from DR sections 1 and 9.

### Decisions

- **Every failure mode below has a detection signal that is already a metric or alert in section 06, a mitigation that is already in the design, and a runbook step.** Nothing here depends on someone noticing something by eye.
- **The training loop defends itself**: skip-step on gradient-norm spikes, automatic rollback after three consecutive skips, an LR cut on a second rollback within 1,000 steps, a hard stop on a third. Humans decide what happens after the stop.
- **Hardware failures are routine, not incidents.** Hot spares, Slurm requeue and verified 30-minute checkpoints turn a node loss into a 15-minute restart; the on-call engineer is paged but the run has usually already resumed.
- **Go/no-go gates are the main protection against the expensive failures** (bad data, wrong recipe, a cluster that cannot reach the planned throughput): G1-G6 are defined in the DR with a number each and are not waived.
- **The contingency (USD 788,129, 15.8%) is pre-allocated to named risks in order** (price, MFU, schedule) and is released only by the program lead against a change request.

### Risk register

Training dynamics:

| Failure mode | Detection | Mitigation (in design) | Response |
|---|---|---|---|
| Loss spike, recovers | loss > 1.25 x EMA alert | QK-norm, z-loss, clip 1.0, batch 8M | Runbook 1 step 1; log; no action if recovered within 200 steps |
| Loss spike, does not recover / divergence | grad-norm > 3 x EMA, loss rising 500+ steps | skip-step rule, rollback ladder | Runbook 1 |
| NaN / Inf in bf16 | NonFiniteLoss page | fp32 norms, softmax, logits, reduce; QK-norm | Runbook 2 |
| Slow plateau, below ladder prediction | ValidationDrift > 0.02 nats at 1T/4T/8T (G5) | ladder-fit L(N, D), per-source val loss | compare per-source losses; check mix drift and data bugs first; if the recipe is wrong, the G5 decision is a DR change, not a hot fix |
| LR too high or too low | grad-norm trend, update/param ratio, ladder comparison | ladder sets LR, clamp [3e-4, 6e-4], 3B rehearsal | not changed mid-run except by the rollback ladder's 20% cut |
| Batch too small for stable phase | gradient noise scale B_simple every 10B tokens | 8M batch, 4M fallback decided at 1B ablation | none mid-run |
| Bad init or numerics bug | activation RMS out of [0.3, 30] in the first 10B tokens | rehearsal at 3B with the same code | stop within the first hour of the run, not at day 10 |
| Anneal started too early/late | token counter vs the DR date-driven rule | anneal start rule and token floor (9.0T) | PM and tech lead review at block day 48 |

Data:

| Failure mode | Detection | Mitigation | Response |
|---|---|---|---|
| Duplicated shards or a source counted twice | MANIFEST sha256 collisions; per-source token totals vs plan; loss steps down suddenly | manifest with sha256 per shard; loader logs realised mix | rebuild the source directory; rollback to before the first duplicated window |
| Benchmark contamination | decontamination log; suspiciously high eval on one task | 13-gram decontamination against every eval set, private held-out suite | drop the affected eval; re-run decontamination; report |
| Tokenizer mismatch (wrong hash) | tokenizer sha256 in shard manifests vs checkpoint meta | hash checked at loader start | stop; retokenize |
| Mis-weighted mix | MixDrift > 1% alert | weights in config, logged every 10B tokens | fix weights; no rollback needed unless > 50B tokens affected |
| Corrupt shard | sha256 check at open; decode of 100 docs per shard at verification | verification step in section 03 | quarantine shard; the loader skips it; rebuild from pass-2 output |
| Licence or takedown event | legal notice | provenance per document; drop lists; counsel manifest | drop list append, source rebuild, note in the model card; a release gate item if after G6 |
| PII leakage in outputs | red team; output classifier | PII scrub, anneal-mix presidio pass, SFT refusals | targeted DPO pass; serving filter rule |
| Unique data short of plan | G3 measurement per source | epoch caps, extension pool, fallback order in the DR | apply the DR fallback order; the date-driven anneal rule caps the exposure |

Infrastructure:

| Failure mode | Detection | Mitigation | Response |
|---|---|---|---|
| GPU XID error / uncorrectable ECC | GpuXid, GpuUncorrectableEcc page | hot spares in the reservation, requeue, 30-min checkpoints | Runbook 3 |
| NVLink failure | NvlinkErrors, DCGM diag | prolog check; spare | drain node; Runbook 3 |
| IB link flap | IbLinkFlap page, NCCL warnings, step-time jump | rail-optimised fabric; adaptive routing | vendor ticket; if the step time is > 10% worse, drain the node (Runbook 3) |
| NCCL hang / timeout | NccLTimeout page; step time stalls; heartbeat timeout | TORCH_NCCL_ASYNC_ERROR_HANDLING, flight recorder dump | Runbook 4 |
| Straggler rank | StragglerRank warn (max/min step time > 1.3) | per-rank step time export | Runbook 5 |
| Thermal throttling / power event | GpuThermalThrottle warn; clocks < 1,600 MHz | vendor SLA; acceptance burn-in | drain node; vendor |
| Filesystem throughput collapse | loader stall time; checkpoint write time > 60 s | pre-tokenized shards (12 MB/s read); NVMe landing zone | Runbook 5; move checkpoints to NVMe-only until fixed |
| Object store throttling | UploadLag warn | background uploader with retries; 24 h on PFS | widen the upload window; nothing is lost while PFS holds 24 h |
| Slurm preemption / reservation loss | job state alert | standing reservation, exclusive nodes | vendor escalation (4-hour SLA) |
| Silent data corruption (SDC) | loss divergence with no other signal; periodic determinism check (same batch, two nodes, equal logits) | weekly determinism test on the spare node | isolate the node by bisection; vendor RMA |
| Network partition between racks | NCCL timeout on a subset of ranks | flight recorder; topology map | Runbook 4 |

Checkpointing:

| Failure mode | Detection | Mitigation | Response |
|---|---|---|---|
| Corrupt or partial checkpoint | MANIFEST missing; verification job fails; CheckpointUnverified page | async save finalised only after upload; sha256; load-and-forward job | Runbook 6 |
| Resume mismatch (loss jumps after restart) | first 20 steps vs pre-failure log | bit-identical resume gate in the rehearsal; RNG and loader state saved | stop; compare state dicts; resume from the previous verified checkpoint |
| Resharding bug on a different world size | load error or wrong shapes | DCP resharding tested in the rehearsal (512 -> 504) | resume at the original world size on the spare |
| Lost dataloader state | cursors missing in app state | flat JSON app state (section 06) | reconstruct from tokens_seen; mark the window range as replayed |
| Storage cost blow-up | retained TB vs the 7.7 TB plan | retention policy, pruning job | prune; audit pinned checkpoints |

Evaluation and post-training:

| Failure mode | Detection | Mitigation | Response |
|---|---|---|---|
| Benchmark leakage via post-training data | decontamination log; private suite disagrees with public | 13-gram decontamination; private suite | drop the set; retrain the stage |
| Judge bias (length, style) | length growth; human agreement < 0.75 | position swap, length gate, 20k human pairs | re-filter pairs; switch to length-normalised DPO |
| Reward hacking in GRPO | reward up, private suite flat; response length doubling | verifiable rewards only, KL 0.001, early-stop rule | stop; inspect samples; tighten verifiers |
| Catastrophic forgetting | MMLU/GSM8K regression > 1 point | low LR, 1 epoch DPO, replay of SFT data in RL prompts | roll back a stage; add replay |
| Refusal over-training | benign refusal rate > 3% | benign prompt set in the gate | targeted DPO pass with benign-compliance pairs |

Serving:

| Failure mode | Detection | Mitigation | Response |
|---|---|---|---|
| OOM from long prompts | replica restarts; KV usage > 90% | max-model-len per tier; chunked prefill; `--max-num-seqs` from the capacity model | route long requests to the 128k tier; lower max-num-seqs |
| KV fragmentation / low batch | tokens/s per GPU < 60% of plan | paged attention; prefix caching | tune block size; check router hashing |
| Tail latency | p99 TTFT > 1.5 s or TPOT > 60 ms | HPA on queue depth; chunked prefill | scale out; cap prefill chunk |
| Quantisation regression | G6 table delta > 0.5 points | accuracy gate per build | ship bf16 or INT8 for that tier |
| Bad build reaches production | canary error rate / quality signal | canary 5% for 24 h, automatic rollback | rollback; post-mortem |

Program:

| Failure mode | Detection | Mitigation | Response |
|---|---|---|---|
| Cost overrun | monthly cost vs DR budget table | reserved contract, named contingency items, change requests | program lead decision; the DR sensitivity table lists what is pre-authorised |
| Schedule slip before Block 2 | G1/G3/G3a dates | 2-week float (W13-14), contract start window, v0 corpus decouples Block 1 from the production passes | spend float; exercise option 1 (+1 week at 2.20) by block day 21 |
| MFU below plan | G2 (64 GPUs) and G4 (512 GPUs) gates | planning MFU = G2 - 0.02; option 1 | fewer stable tokens via the date-driven rule; the 9.0T floor triggers option 2 |
| Vendor loses capacity | contract terms | master contract with named escalation and penalties; on-demand fallback priced | on-demand fallback (2.90) for Block 1; Block 2 cannot be replaced at short notice: this is the top vendor risk and the reason for the W6 start-date fix |
| Key-person loss | staffing | backups named per role (tech lead <-> systems; infra <-> data); contractor line | 3-month contractor reserve (97,500) in the sensitivity table |
| Data-pipeline slip | G3 at W12 | contractor + data engineer; v0 corpus | +1 month contractor (28,333); rehearsal starts on v0 |

### Rollback and stop policy (main run)

1. Skip the step when the gradient norm exceeds 3x its 100-step EMA or is non-finite (no rollback, no page; logged).
2. Three consecutive skips: roll back to the last verified checkpoint (at most 30 minutes old), advance the data seed so the loader skips the window that triggered it, resume; page `warn`.
3. A second rollback within 1,000 steps: also cut the peak LR by 20% for the remainder of the stable phase; page `page`.
4. A third rollback within 1,000 steps: stop the run; the tech lead decides (candidates: data inspection of the skipped windows, LR cut 50%, batch to 4M for 10B tokens, or resume from a checkpoint 1,000+ steps earlier).
5. Any rollback older than 2 hours of training (4 checkpoints) requires the tech lead's sign-off and a change-request note, because it costs USD 4,600 per lost hour at 512 GPUs (27,878 per day).

Go/no-go gates that stop the main run from starting or continuing: G4 (6,000 tokens/s/GPU for 2 h on 512 GPUs before launch), the activation-RMS check in the first 10B tokens, G5 at 1T/4T/8T (|validation loss - ladder prediction| <= 0.02 nats; a failure at 1T stops the run for a recipe review rather than spending 40 more days).

### Runbooks

Runbook 1: loss spike or divergence

1. Alert `LossSpike` or `GradNormExplosion` fires with the step. Open the Stability dashboard: grad norm, skipped steps, activation RMS by layer, attention logit max.
2. If the guard has already skipped or rolled back (events in the metrics log), confirm the resume: loss within 0.05 of the pre-spike EMA within 200 steps. Done; note the step in the run log.
3. If the loss is still above 1.25x EMA after 500 steps with no skips (a slow divergence): roll back manually to the last checkpoint before the rise began, advance the data seed, resume.
4. Inspect the data windows at the spike step (the loader logs shard and window ids): look for binary junk, giant repeated spans, or a mis-tokenized shard; quarantine any offending shard.
5. If two manual rollbacks were needed within 1,000 steps: cut the peak LR by 20% (guard does this automatically for automatic rollbacks). Record a change request.
6. Post-mortem within 24 h: step, cause, tokens lost, cost (hours x 512 x 2.20).

Runbook 2: NaN or Inf

1. `NonFiniteLoss` page. The guard has skipped the step; if three in a row, it has rolled back.
2. Check the per-rank step log for which rank first reported non-finite values. One rank only: hardware (go to Runbook 3, drain the node). All ranks: numerics or data.
3. All ranks: inspect the batch (as in Runbook 1 step 4). If the data is clean, run the same batch on the spare node with `torch.autograd.set_detect_anomaly(True)` in fp32 on the checkpoint to locate the op.
4. Resume from the rolled-back checkpoint with the seed advanced. If it recurs within 1,000 steps, cut the LR 20% and escalate to the tech lead.

Runbook 3: node failure mid-run (XID, ECC, NVLink, thermal)

1. Page fires (`GpuXid`, `GpuUncorrectableEcc`, `NodeDown`). Slurm's `--kill-on-bad-exit` ends the job; `--requeue` restarts it on the reservation, which already includes the spare nodes. Expected: training resumes within 15 minutes from the latest verified checkpoint without human action.
2. Confirm on the Run overview: `train_step` advancing, loss continuous with the pre-failure log (first 20 steps within 1e-4), tokens/s/GPU back above 6,000 within 10 minutes of the restart.
3. Drain the failed node (`scontrol update NodeName=<n> State=DRAIN Reason="XID 79"`), open the vendor ticket with the DCGM diag output, and request a replacement under the 4-hour SLA.
4. If the spare pool is now empty (second failure before a replacement arrives): the eval job on the remaining spare is preempted by Slurm so the main job keeps 512 GPUs; if no spare at all is left, the job restarts on 504 GPUs (63 nodes): DCP reshards on load, and the global batch is kept at 8M by raising grad-accum (loader per-rank slicing handles the new world size). Throughput drops 1.6%; record it.
5. When the replacement passes the prolog, return it to the reservation; the eval job returns to the spare.

Runbook 4: NCCL hang or timeout

1. `NccLTimeout` page or step time stalled for > 2 minutes with no alert. With `TORCH_NCCL_ASYNC_ERROR_HANDLING=1` the job will abort within the 10-minute timeout and requeue; do not kill it by hand before the flight-recorder dump is written (`TORCH_NCCL_DUMP_ON_TIMEOUT=1`, in the job's log directory).
2. Read the dump: the collective and the ranks that did not arrive identify the node or the rail. Check that node's IB counters (`IbLinkFlap`) and `dmesg`.
3. Drain the identified node (Runbook 3 step 3). If no node is identified (true network partition), run `all_reduce_perf` on the reservation at 64 nodes; a node pair > 15% below the median points at a cable or switch port; open the vendor ticket with the pair.
4. Resume (automatic). If a second hang happens within 6 hours with no identified node, switch `NCCL_ALGO=Ring` (disabling SHARP) as a diagnostic and re-run the fabric test.

Runbook 5: throughput regression

1. `ThroughputDrop` (5-minute average < 85% of the hourly) or `BelowPlanThroughput` (30-minute average < 6,000 tokens/s/GPU).
2. Check the per-rank step-time table. One slow rank: `StragglerRank`; look at that node's GPU clocks, temperature, ECC-correctable rate and IB counters; drain if any is abnormal (Runbook 3).
3. All ranks slower: check the loader stall time (filesystem) and the checkpoint uploader (NVMe full, `NvmeFull`); check for a torch.compile recompilation storm in the logs (the batch ramp recompiles at most 34 times, never per step).
4. Fabric: compare the current NCCL collective times (flight recorder sampling) with the acceptance-day values; a > 20% rise in the cross-node all-reduce time means a fabric problem (Runbook 4 step 3).
5. If no cause is found within 1 hour and throughput is > 10% below plan, restart the job (a clean process often recovers fragmented allocators); if that fails, page the tech lead; the DR's option 1 (+1 week) is the budgeted backstop.

Runbook 6: corrupt checkpoint

1. `CheckpointUnverified` page (no verified checkpoint for 60 minutes) or a verification job failure.
2. Do not touch `latest`; it points at the previous verified checkpoint by construction. Training continues.
3. Read the verification log: sha256 mismatch (upload problem; re-upload from NVMe, which keeps the last 6), missing shard files (a rank's async save failed; the next checkpoint will be complete, delete this one), logits mismatch (a real problem: compare the DCP metadata of the two latest checkpoints; if the shapes differ, a mesh change happened silently; stop and investigate).
4. If two consecutive checkpoints fail verification, pause the run at the next checkpoint boundary and verify a synchronous save on the spare node before continuing. The cost of a pause is 27,878 per day; the cost of training for a day on an unrecoverable state is the same plus the day.
5. After the fix, run the restore drill: load the latest verified checkpoint on the spare node and train 10 steps.

### Reference implementation

The guard in `code/loss_spike_guard.py` encodes steps 1-4 of the rollback policy; the training loop calls `observe()` after `clip_grad_norm_` and acts on the decision (step, skip, rollback, rollback with LR cut, stop).

```python
    def observe(self, step: int, loss: float, grad_norm: float) -> GuardDecision:
        finite = math.isfinite(loss) and math.isfinite(grad_norm)
        armed = self.n >= self.cfg.warmup_steps
        grad_spike = armed and grad_norm > self.cfg.grad_factor * self.grad_ema
        loss_spike = armed and loss > self.cfg.loss_spike_ratio * self.loss_ema
        if loss_spike:
            self.events.append((step, "loss_spike_alert"))
        if finite and not grad_spike:
            self.grad_ema = self._update_ema(self.grad_ema, grad_norm)
            self.loss_ema = self._update_ema(self.loss_ema, loss)
            self.n += 1
            self.consecutive_skips = 0
            return GuardDecision("step", "ok", self.lr_scale)
        self.consecutive_skips += 1
        reason = "non-finite" if not finite else f"grad_norm {grad_norm:.3g} > {self.cfg.grad_factor} x ema {self.grad_ema:.3g}"
        self.events.append((step, f"skip: {reason}"))
        if self.consecutive_skips < self.cfg.max_consecutive_skips:
            return GuardDecision("skip", reason, self.lr_scale)
        # rollback ladder
        self.consecutive_skips = 0
        self.rollback_steps = [s for s in self.rollback_steps if step - s <= self.cfg.rollback_window_steps]
        self.rollback_steps.append(step)
        restored = self.rollback(step)
        self.events.append((step, f"rollback -> step {restored}, data seed advanced"))
        if len(self.rollback_steps) >= self.cfg.max_rollbacks_in_window:
            self.events.append((step, "stop: third rollback inside the window"))
            return GuardDecision("stop", "third rollback within 1,000 steps", self.lr_scale)
        if len(self.rollback_steps) >= 2:
            self.lr_scale *= self.cfg.lr_cut
            self.events.append((step, f"lr_scale -> {self.lr_scale:.3f}"))
            return GuardDecision("rollback_lr_cut", "second rollback within 1,000 steps", self.lr_scale)
        return GuardDecision("rollback", reason, self.lr_scale)
```

The smoke test drives 3,000 synthetic steps with three bad steps at 500 (rollback to checkpoint 0), three at 900 (rollback to 657 plus the 20% LR cut), a lone spike at 1,200 (skip only, with the loss-spike alert), NaNs at 2,400 (plain rollback to 1,971, no second cut because the window has passed), and a separate run that reaches the stop after a third rollback.

### Checklist

- [ ] Every alert in section 06 maps to a row here; every row names a runbook step.
- [ ] Guard integrated in the training loop; `python3 code/loss_spike_guard.py` passes; rollback callback wired to the checkpointer and the loader seed.
- [ ] Runbooks 1-6 rehearsed on the 3B run (forced spike via a corrupted window, forced node kill, forced NCCL timeout, forced checkpoint corruption).
- [ ] On-call rota for Block 2 published; vendor escalation contact and SLA confirmed in writing.
- [ ] Weekly determinism test scheduled on the spare node.
- [ ] Contingency items and their pre-authorisations (DR section 1) signed by the program lead before Block 2.
