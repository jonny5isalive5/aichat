## 06. Checkpointing, monitoring and logging

Covers: the checkpointing system (`code/checkpoint.py`) and monitoring and logging (`code/monitoring.py`). Numbers from DR sections 4 and 5 (checkpoint sizes, cadence, interruption rate, validation cadence).

### Decisions

- **Checkpoint every 657 steps (30 minutes) with `torch.distributed.checkpoint` (DCP), asynchronously, to local NVMe, then upload to object storage.** Expected loss per interruption is 15 min of work plus 15 min of restart; at 0.5 interruptions/day over 49 days that is 25 x 30 min = 12.7 h = 1.1% of the run, the figure booked in the DR's 1.18 overhead factor.
- **One checkpoint = sharded fp32 params + Adam m and v (117.6 GB) + app state.** DCP deduplicates the 64 HSDP replicas and spreads the write over all 512 ranks: 230 MB per GPU, 0.11 s to NVMe, 65 MB/s average upload per node-group to the object store.
- **Exact resume is a gate, not a hope.** The app state carries step, tokens seen, dataloader cursors, RNG states, config hash, tokenizer hash and git SHA; the rehearsal (section 05) proves a bit-identical loss curve for 100 steps after a forced kill.
- **Retention: last 6 (3 h) on NVMe and parallel FS, one per hour for 24 h on the parallel FS (2.8 TB), one full checkpoint every 91 checkpoints (about 500B tokens, 23 over the run, 2.7 TB) plus a bf16 weights-only export every 100B tokens (110 x 19.6 GB = 2.2 TB) in object storage, replicated to a second region.** Total retained 7.7 TB.
- **Every uploaded checkpoint is verified by a load-and-forward job** on the eval node before it becomes `latest`; a checkpoint that fails verification is never a resume target.
- **Monitoring stack: in-process JSON-lines metrics with spike/NaN/throughput alerts, Weights & Biases for experiment curves, Prometheus + Grafana with dcgm-exporter and node-exporter for hardware, Loki for logs, Alertmanager to PagerDuty and Slack.** One on-call engineer during Block 2 with a 15-minute response target.
- **Evaluation runs off the training job**: in-loop validation loss every 1,000 steps (60M tokens, 0.24% of step time) and per-source validation every 10B tokens; downstream benchmarks via lm-evaluation-harness on the hot-spare node every 100B tokens on the bf16 export.

### Procedure

1. **Wire the checkpointer into the loop (W8).** `Checkpointer.save()` on every 657th step; `TrainState` filled from the loop, the loader's `state_dict()` and the run metadata; `MixedPrecision` master weights are what DCP saves (fp32 DTensors). Smoke test: `python3 code/checkpoint.py`.
2. **Local landing zone.** `/nvme/ckpt/step-NNNNNNNNN/` on each node's RAID-0; the background uploader (`aws s3 sync`, 4 streams per node) copies the directory to `s3://llm10b-ckpt/run-<id>/` and writes `MANIFEST.json` with the sha256 of the shard files only after the upload completes. `latest` is a symlink updated only after `MANIFEST.json` exists.
3. **Verification job (every checkpoint).** The eval node loads the checkpoint with DCP into a fresh model, runs 32 fixed prompts, compares logits to the training-time values logged at that step (atol 1e-5 in fp32 after an fp32 forward), checks step and dataloader cursors are present, and marks the checkpoint `verified` in the run database. Alert if a checkpoint is not verified within 20 minutes of its step.
4. **Resume procedure (automatic on Slurm requeue).** `--resume-from latest` -> DCP load (resharding onto the current mesh is automatic, so a resume on 504 GPUs after a node loss works without conversion) -> loader state restored -> the first 20 steps are compared to the pre-failure log (loss within 1e-4; if the world size changed the batch composition differs and this check is skipped) -> normal operation.
5. **Rollback procedure (loss spike runbook, section 09).** Pick the last verified checkpoint before the spike, resume with the data seed advanced by one (the loader skips the window that triggered the spike), optionally reduce the peak LR by 20% for the rest of the stable phase if a second rollback is needed within 1,000 steps.
6. **Export (every 100B tokens and at the end).** `dcp_to_torch_save` style consolidation on the eval node: gather the fp32 DTensors, cast to bf16, write HF-layout safetensors (section 02) plus `tokenizer.json`; the same artefact serves evaluation and the serving pilot (section 08).
7. **Disaster recovery.** Object store bucket versioning on; cross-region replication of `run-<id>/permanent/` within 1 hour; a quarterly restore drill loads a permanent checkpoint on the dev node and trains 10 steps.
8. **Stand up monitoring (W5-W6, infra/SRE).** dcgm-exporter and node-exporter on every node, Prometheus scrape at 15 s, Grafana dashboards below, Loki + Promtail for the JSON-lines metrics and Slurm logs, Alertmanager routes: `severity=page` -> PagerDuty, `severity=warn` -> Slack `#llm10b-alerts`. The in-process logger's `on_alert` posts to the same Slack channel with the step and a link to the dashboard.
9. **Alert tuning on the rehearsal (W12-W13).** Run the 3B rehearsal with all alerts live; every false page is a threshold change recorded in the alert file; the forced node kill must page within 2 minutes and the requeue must clear the page within 15.

### Checkpoint arithmetic

| Quantity | Value | One-line arithmetic |
|---|---|---|
| Full checkpoint | 117.6 GB | 9,798,236,160 params x 12 B (fp32 param + Adam m + Adam v) |
| bf16 weights export | 19.6 GB | 9,798,236,160 x 2 B |
| Per-GPU write | 230 MB | 117.6 GB / 512 ranks (DCP deduplicates replicas and balances writers) |
| Cadence | 657 steps = 30.0 min | 1,800 s / 2.738 s per step |
| Write stall | 0.11 s per checkpoint | 230 MB at 2 GB/s per GPU to NVMe (staging is a device-to-host copy; the file write is async) |
| Checkpoint overhead | 0.5% | (0.11 s + ~9 s DCP metadata/collectives) / 1,800 s |
| Upload bandwidth | 65 MB/s average | 117.6 GB / 1,800 s |
| Expected interruptions | 25 | 0.5 per day x (49.0 + 4.0 acceptance) days, rounded |
| Expected lost work | 1.1% | 25 x (15 min lost + 15 min restart) / (49 x 24 h) |
| Rolling day on PFS | 2.8 TB | 24 hourly x 117.6 GB |
| Permanent | 4.9 TB | 23 full x 117.6 GB + 110 bf16 x 19.6 GB |

Why 30 minutes and not 10: the lost-work term falls linearly with the interval (0.37% at 10 min) but the upload would need 196 MB/s sustained and the metadata collectives would cost 1.5% of step time; 30 minutes is where the two terms sum to the minimum given the DCP metadata cost measured on the rehearsal. Re-measure on the rehearsal and change the cadence only through the DR.

### Reference implementation

App state and the DCP wrapper (`code/checkpoint.py`):

```python
class TrainState(Stateful):
    """Everything DCP needs besides the model and optimizer; lives in app_state."""

    def __init__(self, step: int = 0, tokens_seen: int = 0, loader_state: dict | None = None,
                 meta: dict | None = None) -> None:
        self.step, self.tokens_seen = step, tokens_seen
        self.loader_state = loader_state or {}
        self.meta = meta or {}

    # DCP loads only keys that already exist in the target's state_dict() and flattens nested
    # dicts, so an empty nested dict on the fresh process would silently drop the loaded keys.
    # Structured app state is therefore stored as flat JSON strings (one leaf each).
    def state_dict(self) -> dict[str, Any]:
        return {
            "step": self.step, "tokens_seen": self.tokens_seen,
            "loader_state_json": json.dumps(self.loader_state, sort_keys=True),
            "meta_json": json.dumps(self.meta, sort_keys=True),
            "rng_torch": torch.get_rng_state(),
            "rng_cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [],
        }

    def load_state_dict(self, sd: dict[str, Any]) -> None:
        self.step, self.tokens_seen = int(sd["step"]), int(sd["tokens_seen"])
        self.loader_state, self.meta = json.loads(sd["loader_state_json"]), json.loads(sd["meta_json"])
        torch.set_rng_state(sd["rng_torch"])
        if torch.cuda.is_available() and sd["rng_cuda"]:
            torch.cuda.set_rng_state_all(sd["rng_cuda"])


class ModelOptWrapper(Stateful):
    """DCP-friendly view of (model, optimizer); works for FSDP2 DTensors and plain modules."""

    def __init__(self, model: torch.nn.Module, optim: torch.optim.Optimizer) -> None:
        self.model, self.optim = model, optim

    def state_dict(self) -> dict[str, Any]:
        return {"model": get_model_state_dict(self.model),
                "optim": get_optimizer_state_dict(self.model, self.optim)}

    def load_state_dict(self, sd: dict[str, Any]) -> None:
        set_model_state_dict(self.model, sd["model"], options=StateDictOptions(strict=True))
        set_optimizer_state_dict(self.model, self.optim, sd["optim"])
```

Save, load and retention:

```python
class Checkpointer:
    def save(self, wrapper: ModelOptWrapper, state: TrainState, step: int, async_: bool = True) -> str:
        """Stage the state (fast), return immediately; the write happens in a background thread."""
        self.wait()  # never two saves in flight
        p = self.path(step)
        sd = {"train": wrapper, "app": state}
        if async_ and dist.is_initialized():
            self._pending = dcp.async_save(sd, checkpoint_id=p, process_group=self.pg)
        else:
            dcp.save(sd, checkpoint_id=p)
            self._finalise(p, step)
        return p

    def load(self, wrapper: ModelOptWrapper, state: TrainState, p: str) -> None:
        """Resharding on load is automatic: DCP maps saved shards onto the current mesh."""
        dcp.load({"train": wrapper, "app": state}, checkpoint_id=p)


@dataclass
class RetentionPolicy:
    keep_last: int = 6                   # 30-min checkpoints kept on NVMe/PFS (3 h)
    keep_hourly_for_steps: int = 31_560  # 24 h at 2.738 s/step
    permanent_every_steps: int = 59_787  # 91 x 657-step checkpoints = 501.6B tokens at 8,388,608 tokens/step
    steps_per_hour: int = 1_315          # 3600 / 2.738
    pinned: set[int] = field(default_factory=set)  # eval-best or milestone steps, never pruned
```

The smoke test saves after three optimizer steps, restores into a fresh model and optimizer, asserts every parameter and every Adam tensor is equal, that the app state (step 657, cursors, metadata) round-trips, that one further step is bit-identical on both copies, and that the retention policy keeps the right set.

### Metrics taxonomy

| Group | Metric | Source | Cadence |
|---|---|---|---|
| Training | loss, z-loss share, grad norm (pre-clip), LR, global batch tokens, tokens/s, tokens/s/GPU, MFU, step time and its fwd/bwd/opt/data split, skipped steps, rollbacks | in-process logger | every step |
| Training | per-layer activation RMS, attention logit max, param RMS, update/param ratio | in-process (hooks) | every 100 steps |
| Validation | held-out loss on the 6-domain set; per-source loss | eval callback | 1,000 steps / 10B tokens |
| Downstream | MMLU, HellaSwag, ARC-C, GSM8K, HumanEval, the private 10-task suite | lm-evaluation-harness on the spare node | every 100B tokens |
| Data | realised mix per source, epoch per source, loader stall time | loader | every 10B tokens |
| GPU | utilisation, SM occupancy, HBM used, temperature, power, clocks, ECC (corrected/uncorrected), XID events, NVLink errors, retired pages | dcgm-exporter | 15 s |
| Fabric | IB port counters (link down, symbol errors, congestion), NCCL collective latency (flight recorder on timeout) | node-exporter + NCCL | 15 s |
| Storage | NVMe write throughput and queue, PFS read/write, object upload lag per checkpoint | node-exporter, uploader | 15 s / per checkpoint |
| Cluster | nodes up/drained, job state, requeue count, spare pool occupancy | Slurm exporter | 60 s |

Logging format: one JSON object per step per rank 0 (and per-rank step time at 1/100 sampling), fields as in `MetricsLogger.log_step`; Slurm stdout/stderr per node; NCCL at `WARN`; everything shipped by Promtail to Loki with labels `run_id`, `node`, `rank`.

### Alert rules

Prometheus rules (hardware and cluster); the in-process logger handles the loss/grad/NaN/throughput alerts at step granularity with the same thresholds.

```yaml
groups:
- name: llm10b-training
  rules:
  - alert: LossSpike
    expr: train_loss > 1.25 * train_loss_ema200 or train_loss > train_loss_ema200 + 4 * train_loss_emastd200
    for: 0m
    labels: {severity: page}
  - alert: NonFiniteLoss
    expr: train_loss_is_nan == 1 or train_grad_norm_is_nan == 1
    labels: {severity: page}
  - alert: GradNormExplosion
    expr: train_grad_norm > 3 * train_grad_norm_ema100
    labels: {severity: page}
  - alert: ThroughputDrop
    expr: avg_over_time(train_tok_s[5m]) < 0.85 * avg_over_time(train_tok_s[1h])
    for: 5m
    labels: {severity: page}
  - alert: BelowPlanThroughput
    expr: avg_over_time(train_tok_s_per_gpu[30m]) < 6000
    for: 30m
    labels: {severity: warn}
  - alert: StragglerRank
    expr: max(train_step_time_rank) > 1.3 * min(train_step_time_rank)
    for: 10m
    labels: {severity: warn}
  - alert: CheckpointLate
    expr: time() - train_last_checkpoint_ts > 2700
    labels: {severity: page}
  - alert: CheckpointUnverified
    expr: time() - train_last_verified_checkpoint_ts > 3600
    labels: {severity: page}
  - alert: ValidationDrift
    expr: val_loss_per_source - val_loss_per_source_pred > 0.02
    for: 0m
    labels: {severity: warn}
  - alert: MixDrift
    expr: abs(loader_realised_share - loader_target_share) > 0.01
    labels: {severity: warn}
- name: llm10b-hardware
  rules:
  - alert: GpuXid
    expr: increase(DCGM_FI_DEV_XID_ERRORS[5m]) > 0
    labels: {severity: page}
  - alert: GpuUncorrectableEcc
    expr: increase(DCGM_FI_DEV_ECC_DBE_VOL_TOTAL[10m]) > 0
    labels: {severity: page}
  - alert: GpuThermalThrottle
    expr: DCGM_FI_DEV_GPU_TEMP > 85 or DCGM_FI_DEV_SM_CLOCK < 1600
    for: 5m
    labels: {severity: warn}
  - alert: NvlinkErrors
    expr: increase(DCGM_FI_DEV_NVLINK_CRC_FLIT_ERROR_COUNT_TOTAL[10m]) > 0
    labels: {severity: warn}
  - alert: IbLinkFlap
    expr: increase(node_infiniband_link_downed_total[10m]) > 0
    labels: {severity: page}
  - alert: NccLTimeout
    expr: increase(nccl_timeouts_total[5m]) > 0
    labels: {severity: page}
  - alert: NvmeFull
    expr: node_filesystem_avail_bytes{mountpoint="/nvme"} / node_filesystem_size_bytes{mountpoint="/nvme"} < 0.2
    labels: {severity: page}
  - alert: UploadLag
    expr: ckpt_upload_lag_seconds > 1800
    labels: {severity: warn}
  - alert: NodeDown
    expr: up{job="node"} == 0
    for: 2m
    labels: {severity: page}
```

In-process detector (`code/monitoring.py`):

```python
@dataclass
class SpikeDetector:
    """Loss spike: value > EMA + k * EMA-std, or > ratio * EMA. Grad-norm uses the same rule."""

    halflife_steps: int = 200
    k_sigma: float = 4.0
    ratio: float = 1.25
    warmup: int = 100
    ema: float = 0.0
    var: float = 0.0
    n: int = 0

    def update(self, value: float) -> bool:
        if not math.isfinite(value):
            return True
        alpha = 1 - 0.5 ** (1 / self.halflife_steps)
        spike = False
        if self.n >= self.warmup:
            std = math.sqrt(max(self.var, 1e-12))
            spike = value > self.ema + self.k_sigma * std or value > self.ratio * self.ema
        if self.n == 0:
            self.ema, self.var = value, 0.0
        elif not spike:  # a spike must not pull the baseline up
            d = value - self.ema
            self.ema += alpha * d
            self.var = (1 - alpha) * (self.var + alpha * d * d)
        self.n += 1
        return spike
```

MFU is computed from the DR FLOPs per token: `tok_s * 62,815,948,800 / (989e12 * world_size)`; at the plan's 5,983 tokens/s/GPU this prints 0.380. The smoke test injects a loss spike, a gradient spike, a NaN and a 40% straggler slowdown into 600 synthetic steps and asserts each alert fires (and that none fire during the 100-step warmup).

### Dashboards

1. **Run overview:** loss (raw and EMA) with the ladder prediction band from the DR's G5 rule, tokens seen vs plan line (1T at W16 d2, 4T at W18 d1, 8T at W20 d5), tokens/s/GPU vs the 6,000 gate, MFU, LR, global batch.
2. **Stability:** grad norm, skipped steps, z-loss share, per-layer activation RMS heatmap, attention logit max, update/param ratio.
3. **Validation:** 6-domain held-out loss, per-source loss vs the 10B-token baseline, downstream benchmark table per 100B-token export.
4. **Hardware:** per-node GPU utilisation, HBM, temperature, power, ECC/XID counters, NVLink and IB errors, straggler rank table.
5. **Checkpoints and storage:** last save, last verified, upload lag, NVMe and PFS usage, retention counts.
6. **Data:** realised vs target mix, epoch per source, loader stall time.

### Async evaluation loop

The spare node (8 GPUs, 330 GPU-h booked over Block 2) runs `lm_eval --model vllm --model_args pretrained=<export>,dtype=bfloat16 --tasks mmlu,hellaswag,arc_challenge,gsm8k,humaneval,<private-suite> --batch_size auto` on every 100B-token bf16 export, writes results to the run database and the Validation dashboard, and posts a one-line Slack summary. Perplexity validation is in-loop (every 1,000 steps on 60M tokens) and per-source (every 10B tokens); both are exported to Prometheus for the `ValidationDrift` rule. The eval job yields the spare node to the main job on a second hardware failure (Slurm preemption, section 05).

### Checklist

- [ ] `python3 code/checkpoint.py` and `python3 code/monitoring.py` pass in the container image.
- [ ] First checkpoint of the G4 acceptance run uploaded, verified and visible as `latest` within 45 minutes.
- [ ] Rehearsal: forced node kill -> page within 2 min -> requeue -> resume bit-identical for 100 steps; alert thresholds tuned, false pages recorded.
- [ ] Retention policy observed on NVMe, PFS and object store after 48 h of the rehearsal; cross-region replication lag < 1 h.
- [ ] All six dashboards populated; on-call rota and PagerDuty routes tested with a synthetic XID alert.
- [ ] Every 100B-token export evaluated within 6 hours of the export; results in the run database.
