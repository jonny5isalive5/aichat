"""Pretraining loop: FSDP2 + HSDP, WSD schedule, batch ramp, skip-step guard (section 05).

Single process (python3 train_fsdp.py) runs the tiny config on CPU as a smoke test.
Multi-node: srun / torchrun launches one process per GPU; see section 05 "Launch".

Numbers from decision-record.md: global batch 8,388,608 tokens (micro-batch 2 x 4096 per
GPU, grad-accum 2, 512 GPUs), ramp 2M -> 4M -> 8M over the first 100B and 400B tokens,
warmup 8B tokens, AdamW (0.9, 0.95) eps 1e-8, wd 0.1, clip 1.0, peak LR 3e-4, min LR 1 %,
1-sqrt decay over the last 10 % (1.1T of 11.0T tokens), HSDP mesh 64 replicate x 8 shard.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time
from dataclasses import dataclass

import torch
import torch.distributed as dist
from torch.utils.checkpoint import checkpoint

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import ModelConfig, Transformer, flops_per_token  # noqa: E402

H100_PEAK_BF16 = 989e12


@dataclass
class TrainConfig:
    seq_len: int = 4096
    micro_batch: int = 2                 # sequences per GPU per micro-step
    global_batch_tokens: int = 8_388_608
    ramp: tuple[int, int, int] = (2_097_152, 4_194_304, 8_388_608)
    ramp_tokens: tuple[int, int] = (100_000_000_000, 400_000_000_000)  # phase 1, phase 2 lengths
    ramp_plateaus: int = 17              # per phase; keeps torch.compile recompiles bounded
    total_tokens: int = 11_000_000_000_000
    decay_fraction: float = 0.10         # WSD: last 10 % of tokens decay with 1 - sqrt
    warmup_tokens: int = 8_000_000_000
    peak_lr: float = 3e-4
    min_lr_ratio: float = 0.01
    betas: tuple[float, float] = (0.9, 0.95)
    eps: float = 1e-8
    weight_decay: float = 0.1
    grad_clip: float = 1.0
    skip_factor: float = 3.0             # skip the step if grad-norm > 3 x its 100-step EMA
    skip_ema_steps: int = 100
    max_consecutive_skips: int = 3       # then roll back to the last checkpoint and reseed data
    hsdp_shard: int = 8                  # intra-node sharding group
    activation_checkpointing: bool = True
    compile: bool = False
    ckpt_every_steps: int = 657          # 30 min at 2.738 s/step
    log_every: int = 10


# ---- schedules -------------------------------------------------------------
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


def global_batch_at(tokens_seen: int, cfg: TrainConfig) -> int:
    """Two-phase ramp, linear in steps, quantised to ramp_plateaus plateaus per phase."""
    b0, b1, b2 = cfg.ramp
    t1, t2 = cfg.ramp_tokens
    seq = cfg.seq_len
    if tokens_seen >= t1 + t2:
        return b2
    if tokens_seen < t1:
        frac, lo, hi = tokens_seen / t1, b0, b1
    else:
        frac, lo, hi = (tokens_seen - t1) / t2, b1, b2
    plateau = math.floor(frac * cfg.ramp_plateaus) / cfg.ramp_plateaus
    tokens = lo + (hi - lo) * plateau
    return int(round(tokens / seq)) * seq  # whole sequences


# ---- distributed setup ----------------------------------------------------
def setup_distributed() -> tuple[int, int, torch.device]:
    world = int(os.environ.get("WORLD_SIZE", "1"))
    if world == 1:
        return 0, 1, torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dist.init_process_group("nccl")
    local = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local)
    return dist.get_rank(), world, torch.device("cuda", local)


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


def apply_activation_checkpointing(model: Transformer) -> None:
    """Full per-block recompute in the reference; production uses torchtitan's selective
    op-level policy (save matmul / attention outputs, recompute norms, SiLU, RoPE)."""
    for layer in model.layers:
        inner = layer.forward
        layer.forward = (lambda f: (lambda x, cos, sin: checkpoint(f, x, cos, sin, use_reentrant=False)))(inner)


# ---- skip-step guard ---------------------------------------------------------
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

    @property
    def needs_rollback(self) -> bool:
        return self.consecutive >= self.cfg.max_consecutive_skips


# ---- training loop ---------------------------------------------------------
def train(model_cfg: ModelConfig, cfg: TrainConfig, steps: int, batches, save_fn=None) -> list[float]:
    rank, world, device = setup_distributed()
    torch.manual_seed(1234)
    model = Transformer(model_cfg).to(device)
    if cfg.activation_checkpointing:
        apply_activation_checkpointing(model)
    model = shard_model(model, world, cfg)
    if cfg.compile:
        for layer in model.layers:
            layer.compile(fullgraph=True)
    fused = device.type == "cuda"
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.peak_lr, betas=cfg.betas, eps=cfg.eps,
                            weight_decay=cfg.weight_decay, fused=fused)
    guard = GradNormGuard(cfg)
    fpt = flops_per_token(model_cfg, cfg.seq_len)
    tokens_seen, losses, step = 0, [], 0
    t_last = time.time()
    while step < steps:
        gbs = global_batch_at(tokens_seen, cfg)
        accum = max(1, gbs // (world * cfg.micro_batch * cfg.seq_len))
        lr = lr_at(tokens_seen, cfg)
        for g in opt.param_groups:
            g["lr"] = lr
        loss_acc = 0.0
        for micro in range(accum):
            x, y = next(batches)
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            if world > 1:
                model.set_requires_gradient_sync(micro == accum - 1)  # reduce-scatter once per step
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                loss = model(x, y) / accum
            loss.backward()
            loss_acc += loss.item()
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip).item()
        if guard.should_skip(grad_norm):
            opt.zero_grad(set_to_none=True)
            if rank == 0:
                print(f"step {step}: skipped (grad_norm {grad_norm:.3g} vs ema {guard.ema:.3g})")
            if guard.needs_rollback:
                raise RuntimeError("3 consecutive skipped steps: roll back to the last checkpoint and advance the data seed")
            continue
        opt.step()
        opt.zero_grad(set_to_none=True)
        step += 1
        tokens_seen += gbs if world > 1 else accum * cfg.micro_batch * cfg.seq_len
        losses.append(loss_acc)
        if step % cfg.log_every == 0 or step == 1:
            now = time.time()
            tok_s = (accum * cfg.micro_batch * cfg.seq_len * world * cfg.log_every) / max(now - t_last, 1e-9)
            mfu = tok_s * fpt / (H100_PEAK_BF16 * world)
            if rank == 0:
                print(f"step {step} loss {loss_acc:.4f} lr {lr:.2e} gbs {gbs} grad_norm {grad_norm:.3f} "
                      f"tok/s {tok_s:,.0f} mfu(H100) {mfu:.3f}")
            t_last = now
        if save_fn is not None and step % cfg.ckpt_every_steps == 0:
            save_fn(model, opt, step, tokens_seen)
    if world > 1:
        dist.destroy_process_group()
    return losses


def synthetic_batches(cfg: ModelConfig, micro_batch: int, seq_len: int, seed: int = 0):
    g = torch.Generator().manual_seed(seed)
    x = torch.randint(0, cfg.vocab_size, (micro_batch, seq_len + 1), generator=g)
    while True:  # one fixed batch so the loss must fall
        yield x[:, :-1], x[:, 1:]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="tiny", choices=["tiny", "dr10b"])
    ap.add_argument("--steps", type=int, default=6)
    ap.add_argument("--compile", action="store_true")
    args = ap.parse_args()
    t0 = time.time()

    # schedule checks against the DR
    dr = TrainConfig()
    assert abs(lr_at(dr.warmup_tokens, dr) - 3e-4) < 1e-12
    assert lr_at(5_000_000_000_000, dr) == 3e-4                         # stable phase
    assert abs(lr_at(dr.total_tokens, dr) - 3e-6) < 1e-12               # end of decay = 1 %
    assert lr_at(9_900_000_000_000 + 275_000_000_000, dr) < 3e-4 * 0.6  # 1-sqrt falls fast early
    assert global_batch_at(0, dr) == 2_097_152
    assert global_batch_at(100_000_000_000, dr) == 4_194_304
    assert global_batch_at(500_000_000_000, dr) == 8_388_608
    assert dr.global_batch_tokens == 512 * dr.micro_batch * 2 * dr.seq_len
    assert round(1800 / 2.738) == dr.ckpt_every_steps
    guard = GradNormGuard(dr)
    for _ in range(100):
        assert not guard.should_skip(1.0)
    assert guard.should_skip(3.5) and not guard.should_skip(1.1)

    if args.config == "tiny":
        mcfg = ModelConfig.tiny()
        tcfg = TrainConfig(seq_len=mcfg.max_seq_len, micro_batch=2, global_batch_tokens=4 * mcfg.max_seq_len,
                           ramp=(4 * mcfg.max_seq_len,) * 3, warmup_tokens=2 * 4 * mcfg.max_seq_len,
                           total_tokens=10 * 4 * mcfg.max_seq_len, peak_lr=3e-3, compile=args.compile,
                           log_every=2, ckpt_every_steps=10_000)
    else:
        mcfg, tcfg = ModelConfig.dr10b(), TrainConfig(compile=args.compile)
    losses = train(mcfg, tcfg, args.steps, synthetic_batches(mcfg, tcfg.micro_batch, tcfg.seq_len))
    assert losses[-1] < losses[0], losses
    print(f"OK train_fsdp.py smoke test in {time.time() - t0:.1f}s: losses {[round(l, 3) for l in losses]}")
