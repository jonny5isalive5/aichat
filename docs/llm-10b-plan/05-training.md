## 05. Training cluster, parallelism and the training loop

Covers: training cluster specifications, multi-GPU and multi-node parallelism, and the PyTorch training-loop example (`code/train_fsdp.py`, `code/data_loader.py`). Numbers from DR sections 4, 5 and 6.

### Decisions

- **512 compute GPUs (64 nodes of 8x H100 SXM 80 GB) plus 16 hot spares (2 nodes) reserved for the 8-week main-run block.** 49.0 days of main run at MFU 0.38 fits the block with 1.3 days of slack; the spares absorb the ~25 expected hardware interruptions without a queue wait.
- **FSDP2 (`fully_shard`) with an HSDP mesh: shard 8 (inside the node, over NVSwitch) x replicate 64 (across nodes).** A 9.8B model needs no tensor or pipeline parallelism: sharded fp32 params + Adam + grads are 18.3 GB per GPU, and the only cross-node traffic is one fp32 gradient all-reduce per step (0.19-0.24 s of a 2.74 s step, fully overlapped).
- **Micro-batch 2 x 4096 per GPU, gradient accumulation 2, global batch 8,388,608 tokens** (512 x 2 x 2 x 4096). Ramp 2M -> 4M -> 8M over the first 100B and 400B tokens.
- **bf16 autocast, fp32 master weights, fp32 gradient reduce. FP8 is not in the main run.** The Block 1 pilot on the 3B ladder model decides whether FP8 (Transformer Engine) is adopted for a future run; it is never switched on mid-run.
- **Selective op-level activation checkpointing** (save matmul and attention outputs, recompute norms, SiLU and RoPE): 28.8 GB of activations per GPU instead of 80+ GB, at ~10% recompute cost. Full per-block checkpointing only in the 128k stage.
- **torchtitan as the training framework; Megatron-Core only if the week-9 gate (G2) shows torchtitan under 6,300 tokens/s/GPU on 64 GPUs.** The reference loop below is the executable specification of what torchtitan is configured to do.
- **Slurm with a standing reservation, automatic requeue and a prolog health check.** Kubernetes is the alternative only if the vendor cannot provide Slurm.

### Procedure

1. **Procure (W1-W6).** One master contract for 913,920 reserved GPU-hours at USD 2.20/GPU-h (walk-away 2.40): dev node 8 GPUs W1-40, Block 1 64 GPUs W7-14, Block 2 528 GPUs W15-22, Block 3 48 GPUs W23-30. LOI by W2, signed by W4, Block 2 start date fixed by W6. Require: InfiniBand NDR 8 rails, NVSwitch nodes, parallel filesystem, S3-compatible object store, Slurm, root in containers (enroot/pyxis), DCGM access, a named vendor escalation contact with a 4-hour SLA for node swaps.
2. **Build the container image (W5-W6)** and pin everything by digest: CUDA 12.8+, cuDNN 9, torch 2.7+ (this plan's code was tested on 2.14), torchtitan at a pinned commit, flash-attn 3 (sm90 build) at a pinned commit, NCCL 2.26+, nvidia-dcgm, HF tokenizers, numpy, wandb, `code/` from this repo. One image for ladder, main run and post-training. Rebuilding the image during Block 2 requires the tech lead's sign-off.
3. **Acceptance tests on every node before it joins any job** (prolog, 6 minutes):
   - `dcgmi diag -r 2` passes; `nvidia-smi -q` shows 8 GPUs, no retired pages pending, no XID in `dmesg` since boot.
   - NVLink: `nvidia-smi nvlink -s` all 18 links up per GPU; `nccl-tests all_reduce_perf -b 1G -e 1G -g 8` busbw >= 370 GB/s.
   - IB: `ibstat` 8 ports Active at 400 Gb/s; `ib_write_bw` to a reference node >= 45 GB/s per NIC.
   - NVMe: `fio` 4 MB sequential write >= 6 GB/s on the local RAID; parallel FS mount present.
   - Clock and thermal: GPU SM clock >= 1,980 MHz under a 60 s burn, HBM temperature < 85 C.
   A node failing any check is drained and reported to the vendor; the hot spare replaces it.
4. **Fabric acceptance (first day of each block):** `all_reduce_perf -b 8 -e 4G -f 2` across 8, 64 and all nodes. Targets: >= 180 GB/s busbw at 8 nodes and >= 170 GB/s at 64 nodes on 1 GB+ messages, no node-pair more than 15% below the median (a slow pair means a bad cable or a mis-cabled rail).
5. **Data bring-up (W6):** the v0 corpus (>= 1.5T tokens, section 04) in the shard format of `code/data_loader.py` on the parallel FS; `python3 code/data_loader.py` style checks against real shards: exact resume, no window shared across ranks, source mix within 1% of the weights over 100k draws.
6. **G2 throughput gate (W9, 64 GPUs):** the DR 10B config on 64 GPUs for 2 hours with torchtitan; pass at >= 6,300 tokens/s/GPU (MFU 0.40 on the 6ND + attention basis). Fail: profile with the torch profiler and Nsight Systems, fix the top three stalls (usually dataloader, chunked CE, compile graph breaks), rerun; if still under, run the same config in Megatron-Core/NeMo (bf16, TE kernels, TP=1) for one afternoon and switch if it clears the gate. The planning MFU for the budget is set to (G2 measurement - 0.02), never re-based upward.
7. **Rehearsal (W12-W13, 64 GPUs):** 3B model, 300B tokens on the frozen mix, with checkpointing, async eval, alerting and a forced node kill at hour 20 to prove auto-requeue and bit-identical resume (same loss to 1e-6 for 100 steps after resume).
8. **Block 2 acceptance (W15, 4 days, billed):** node prolog on all 66 nodes, fabric acceptance, then the G4 gate: the 10B config on 512 GPUs for 2 hours at >= 6,000 tokens/s/GPU with the full logging and checkpoint path on. Only then start the main run.
9. **Main run (W15-W22):** launch with the sbatch script below. Operate by the runbooks in section 09; checkpoint every 657 steps (30 min); in-loop validation every 1,000 steps; per-source validation every 10B tokens; anneal starts at block day 50.3 (W22 d2) or when 9.9T stable tokens are reached, whichever the DR's date-driven rule gives; then the 200B anneal-mix selection runs, the 32k stage (50B tokens, CP=8) and the 128k stage (20B tokens).
10. **Hand-off (W22 d7):** final checkpoint verified (load + forward on 32 prompts vs the training-time logits), consolidated bf16 export to HF layout, two object-store copies in different regions, Block 2 released.

### Cluster specification

Node bill of materials (66 nodes: 64 compute + 2 hot spare; vendor-supplied, DGX H100 or HGX H100 equivalent):

| Part | Spec | Why |
|---|---|---|
| GPU | 8x H100 SXM5 80 GB HBM3, NVSwitch (900 GB/s bidirectional NVLink per GPU) | 989 TFLOP/s dense bf16 each; NVSwitch makes the shard-8 group a flat 450 GB/s-per-direction domain |
| CPU | 2x 56-core Xeon or 2x 96-core EPYC | 10+ dataloader workers per GPU, tokenizer-free loading (shards are pre-tokenized) |
| RAM | 2 TB DDR5 | page cache for shards; room for CPU offload of optimizer state in a DR scenario |
| Local NVMe | 8x 3.84 TB, RAID-0, >= 6 GB/s write | async checkpoint landing zone (117.6 GB every 30 min = 65 MB/s average, 6 GB/s burst) |
| Compute NICs | 8x ConnectX-7 400 Gb/s NDR, one per GPU (rail-optimised) | 50 GB/s per NIC; GPUDirect RDMA |
| Storage/mgmt NICs | 2x 100/200 GbE | parallel FS and object store traffic off the compute fabric |

Fabric and storage:

| Item | Spec |
|---|---|
| Compute fabric | 8 rails x NDR 400G, two-tier non-blocking fat tree over 528 GPU ports, SHARP enabled for all-reduce, adaptive routing on |
| Parallel filesystem | 120 TB usable (Lustre, Weka or VAST), >= 20 GB/s aggregate read; holds the 45.1 TB tokenized corpus, the rolling 24 h of checkpoints (2.8 TB) and eval sets |
| Object store | S3-compatible, 913 TB-months booked over the program; permanent checkpoints (4.9 TB), raw and processed data, exports; cross-region replica of checkpoints |
| Control plane | 2 login nodes, 1 Slurm controller (HA pair), 1 monitoring node (Prometheus, Grafana, Loki), 1 eval node pool from the hot spares when idle |
| Scheduler | Slurm 24.x, `enroot` + `pyxis` containers, reservation `mainrun` over 64 nodes + reservation `spare` over 2, `--requeue` on, prolog health check, `MaxTime` unlimited for the main job |

Data path sizing: the main run consumes 3.06M tokens/s x 4 B = 12 MB/s of shard reads, which is noise against the filesystem; the checkpoint path (section 06) is the only storage load that needs engineering.

### Topology

```text
   +------------------ 64 compute nodes + 2 hot spares (66 x 8 GPUs) ------------------+
   |                                                                                   |
   |  node 0                node 1                        node 65                      |
   |  +------------------+  +------------------+          +------------------+         |
   |  | GPU0 .. GPU7     |  | GPU0 .. GPU7     |   ...    | GPU0 .. GPU7     |         |
   |  |  NVSwitch (900)  |  |  NVSwitch        |          |  NVSwitch        |         |
   |  | NIC0 .. NIC7     |  | NIC0 .. NIC7     |          | NIC0 .. NIC7     |         |
   |  +--|----------|----+  +--|----------|----+          +--|----------|----+         |
   +-----|----------|---------|----------|------------------|----------|--------------+
         |          |         |          |                  |          |
      rail 0     rail 7    rail 0     rail 7             rail 0     rail 7
         |          |         |          |                  |          |
   +-----v----+ +---v------+ +-----------------------------------------------+
   | leaf r0  | | leaf r7  |  ... 8 rails, each GPU index i on rail i ...   |
   +-----|----+ +----|-----+                                                 |
         +-----+-----+------------- spine (NDR, non-blocking) ---------------+
                                                                             
   FSDP2 traffic: all-gather / reduce-scatter inside a node (NVSwitch)
                  fp32 gradient all-reduce across the 64 replicas (IB, SHARP)
```

### Parallelism and memory

Device mesh and what moves where (per GPU, per step; DR section 5):

| Collective | Group | Bytes per GPU | Time | Over |
|---|---|---|---|---|
| All-gather bf16 params (2 micro-steps) | dp_shard = 8 | 19.6 GB x 7/8 per micro-step | 0.152 s | NVSwitch |
| Reduce-scatter fp32 grads (once per step) | dp_shard = 8 | 39.2 GB x 7/8 | 0.152 s | NVSwitch |
| All-reduce fp32 sharded grads | dp_replicate = 64 | 2 x 63/64 x 4.9 GB | 0.193 s (0.241 s at 40 GB/s realistic) | IB |
| Total at line rate | | | 0.498 s of 2.738 s | overlapped; 0.024 s non-overlappable tail |

The cross-node all-reduce is 8.8% of the step at the 8M batch (it would be 17.6% at 4M, which is one reason the batch is 8M). With `set_requires_gradient_sync(False)` on the first micro-step, reduce-scatter and all-reduce run once per optimizer step.

Per-GPU memory at seq 4096, micro-batch 2 (DR section 5):

| Item | GB |
|---|---|
| fp32 sharded params (FSDP2 master DTensor) | 4.56 |
| fp32 Adam m + v (sharded) | 9.13 |
| fp32 sharded grads (reduce_dtype fp32) | 4.56 |
| bf16 all-gather buffers (2 blocks in flight + embedding + lm_head) | 2.81 |
| Activations, selective op-level checkpointing (368 MB/layer/seq x 40 x 2) | 28.79 |
| Logits, chunked fused linear + CE (2048-token chunks, fp32) | 2.00 |
| CUDA context, NCCL buffers, cuBLAS workspace, fragmentation | 4.00 |
| Total | 55.85 |
| Headroom | 24.15 |

One-line checks: 9,798,236,160 x 4 B / 8 shards = 4.90e9 B = 4.56 GiB; Adam = 2x that; the 24 GB headroom is what lets micro-batch 2 stay fixed through the whole run and absorbs allocator fragmentation after restarts.

Why no TP or PP: TP would add an all-reduce per layer on the critical path for a model whose sharded state already fits with 24 GB spare; PP would add bubbles at a global batch that already gives 2 micro-steps per GPU. Both add failure modes without buying throughput at this size.

Context parallelism (32k and 128k stages only): CP = 8 inside the node (torchtitan `context_parallel` over SDPA, ring-attention pattern), mesh (cp 8, dp_shard 8, dp_replicate 8) on 512 GPUs, micro-batch 2 at 32k and 1 at 128k, full per-block activation checkpointing at 128k (memory 34.3 GB per GPU), LR 3e-5, 1B warmup tokens per stage. Expected throughput 3,800 tokens/s/GPU at 32k and 1,300 at 128k (attention FLOPs grow with sequence length; both are gates in the DR).

Throughput targets: 989e12 x 0.38 / 62,815,948,800 = 5,983 tokens/s/GPU; x 512 = 3.06M tokens/s; 8,388,608 / 3.06M = 2.738 s per step; 11.0T / 8,388,608 = 1,311,302 full-batch steps (1,347,065 with the ramp); 1,347,065 x 2.738 s / 86,400 = 42.7 days of pure training, 49.0 days with the 1.18 overhead factor (interruptions 1.1%, checkpoint stalls 0.5%, validation 1.0%, dataloader/optimizer/logging 1.0%, stragglers 3.0%, rollbacks 1.0%, compile warmup 0.2%, debugging and config iterations 10%).

### NCCL and runtime settings

```bash
# set in the sbatch script; identical on every node
export NCCL_IB_HCA=mlx5_0:1,mlx5_1:1,mlx5_2:1,mlx5_3:1,mlx5_4:1,mlx5_5:1,mlx5_6:1,mlx5_7:1
export NCCL_IB_GID_INDEX=3               # RoCE only; harmless on IB
export NCCL_NET_GDR_LEVEL=PIX             # GPUDirect RDMA when NIC and GPU share a PCIe switch
export NCCL_IB_QPS_PER_CONNECTION=4
export NCCL_CROSS_NIC=0                   # keep traffic on its rail
export NCCL_COLLNET_ENABLE=1              # SHARP for the cross-node all-reduce
export NCCL_DEBUG=WARN
export NCCL_SOCKET_IFNAME=bond0           # bootstrap over the management network
export TORCH_NCCL_ASYNC_ERROR_HANDLING=1  # a hung collective raises instead of hanging forever
export TORCH_NCCL_HEARTBEAT_TIMEOUT_SEC=600
export TORCH_NCCL_DUMP_ON_TIMEOUT=1       # flight recorder dump for section 09 "NCCL hang"
export TORCH_NCCL_TRACE_BUFFER_SIZE=20000
export OMP_NUM_THREADS=8
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
```

`init_process_group("nccl", timeout=timedelta(minutes=10))`: long enough for the 657-step checkpoint barrier on a slow rank, short enough that a dead node surfaces within the 15-minute restart budget.

### Training loop

The loop in `code/train_fsdp.py` is the executable specification; torchtitan is configured to match it (same mesh, policy, schedule and guard). Core parts:

```python
def lr_at(tokens_seen: int, cfg: TrainConfig) -> float:
    """Warmup-Stable-Decay. Linear warmup, flat stable, 1-sqrt decay to min_lr."""
    peak, floor = cfg.peak_lr, cfg.peak_lr * cfg.min_lr_ratio
    if tokens_seen < cfg.warmup_tokens:
        return peak * tokens_seen / cfg.warmup_tokens
    decay_start = int(cfg.total_tokens * (1 - cfg.decay_fraction))
    if tokens_seen < decay_start:
        return peak
    frac = min(1.0, (tokens_seen - decay_start) / (cfg.total_tokens - decay_start))
    return floor + (peak - floor) * (1 - math.sqrt(frac))


def shard_model(model: Transformer, world: int, cfg: TrainConfig) -> Transformer:
    """FSDP2 with an HSDP mesh: shard inside the node, replicate across nodes."""
    if world == 1:
        return model
    from torch.distributed.device_mesh import init_device_mesh
    from torch.distributed.fsdp import MixedPrecisionPolicy, fully_shard

    shard = min(cfg.hsdp_shard, world)
    mesh = init_device_mesh("cuda", (world // shard, shard), mesh_dim_names=("dp_replicate", "dp_shard"))
    mp = MixedPrecisionPolicy(param_dtype=torch.bfloat16, reduce_dtype=torch.float32)
    for layer in model.layers:
        fully_shard(layer, mesh=mesh, mp_policy=mp, reshard_after_forward=True)
    fully_shard(model, mesh=mesh, mp_policy=mp, reshard_after_forward=False)
    return model


class GradNormGuard:
    def __init__(self, cfg: TrainConfig) -> None:
        self.cfg, self.ema, self.n, self.consecutive = cfg, 0.0, 0, 0

    def should_skip(self, grad_norm: float) -> bool:
        if not math.isfinite(grad_norm):
            self.consecutive += 1
            return True
        if self.n >= self.cfg.skip_ema_steps and grad_norm > self.cfg.skip_factor * self.ema:
            self.consecutive += 1
            return True
        self.ema = grad_norm if self.n == 0 else self.ema + (grad_norm - self.ema) / min(self.n + 1, self.cfg.skip_ema_steps)
        self.n += 1
        self.consecutive = 0
        return False
```

The step (abridged from `train()`):

```python
    while step < steps:
        gbs = global_batch_at(tokens_seen, cfg)                       # batch ramp
        accum = max(1, gbs // (world * cfg.micro_batch * cfg.seq_len))
        for g in opt.param_groups:
            g["lr"] = lr_at(tokens_seen, cfg)
        for micro in range(accum):
            x, y = next(batches)
            if world > 1:
                model.set_requires_gradient_sync(micro == accum - 1)  # reduce-scatter once per step
            with torch.autocast(device.type, dtype=torch.bfloat16):
                loss = model(x, y) / accum                            # chunked CE + z-loss inside
            loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip).item()
        if guard.should_skip(grad_norm):
            opt.zero_grad(set_to_none=True)
            if guard.needs_rollback:
                raise RuntimeError("3 consecutive skipped steps: roll back and advance the data seed")
            continue
        opt.step(); opt.zero_grad(set_to_none=True)
        step += 1; tokens_seen += gbs
```

Dataloader contract (`code/data_loader.py`): packed windows of 4,097 tokens per sample, `cu_seqlens` from EOS positions for the FA3 varlen op, per-rank disjoint windows, source mix by weight, and a `state_dict` of three integers per source that reproduces the stream exactly after a restart. The production loader adds 8 prefetch workers per GPU and pins memory; the sampling logic is unchanged.

Smoke test output (CPU, tiny config):

```text
step 6 loss 1.7093 lr 3.00e-03 gbs 256 grad_norm 2.898 tok/s 6,898 mfu(H100) 0.000
OK train_fsdp.py smoke test in 1.9s: losses [6.77, 6.77, 5.474, 3.783, 2.567, 1.709]
OK data_loader.py smoke test in 0.4s (web share 0.759)
```

### Launch

```bash
#!/bin/bash
#SBATCH --job-name=llm10b-main
#SBATCH --reservation=mainrun
#SBATCH --nodes=64
#SBATCH --ntasks-per-node=8
#SBATCH --gpus-per-node=8
#SBATCH --cpus-per-task=14
#SBATCH --exclusive
#SBATCH --requeue
#SBATCH --time=60-00:00:00
#SBATCH --output=/pfs/logs/%x-%j-%N.out
#SBATCH --container-image=/pfs/images/llm10b-2026w14.sqsh
#SBATCH --container-mounts=/pfs:/pfs,/nvme:/nvme

export MASTER_ADDR=$(scontrol show hostnames "$SLURM_JOB_NODELIST" | head -n 1)
export MASTER_PORT=29500
source /pfs/env/nccl.env                # the NCCL block above
srun --kill-on-bad-exit=1 bash -c '
  export RANK=$SLURM_PROCID WORLD_SIZE=$SLURM_NTASKS LOCAL_RANK=$SLURM_LOCALID
  python3 /pfs/code/train_fsdp.py --config dr10b --compile \
      --resume-from /nvme/ckpt/latest --shards /pfs/data/v1 --run-id ${SLURM_JOB_ID}'
```

Equivalent `torchrun` form for the dev node and Block 1: `torchrun --nnodes 8 --nproc_per_node 8 --rdzv_backend c10d --rdzv_endpoint $MASTER_ADDR:29500 train_fsdp.py --config dr10b`.

On requeue (node failure, section 09), Slurm restarts the job on the reservation; the spare node is already in the reservation, so the job starts within the 15-minute restart budget; `--resume-from latest` loads the newest verified checkpoint and the dataloader state.

### Checklist

- [ ] Master contract signed by W4 at <= USD 2.40/GPU-h; Block 2 start date fixed by W6.
- [ ] Container image pinned by digest; `python3 code/model.py`, `code/train_fsdp.py`, `code/data_loader.py` pass inside it.
- [ ] Node prolog passes on all 66 nodes; fabric busbw >= 170 GB/s at 64 nodes; no node pair > 15% below median.
- [ ] G2: >= 6,300 tokens/s/GPU on 64 GPUs for 2 h; framework decision recorded.
- [ ] Rehearsal: node kill at hour 20 -> auto-requeue -> bit-identical resume for 100 steps.
- [ ] G4: >= 6,000 tokens/s/GPU on 512 GPUs for 2 h with checkpointing and logging on.
- [ ] Main run launched from the sbatch script; first checkpoint uploaded and verified within 45 min.
