"""Checkpointing with torch.distributed.checkpoint (DCP) for FSDP2 models (section 06).

What a checkpoint holds:  sharded model + optimizer (DCP, resharded on load if the world
size changes), plus app state: step, tokens_seen, LR-schedule inputs, dataloader state,
RNG states, config hash, tokenizer hash, git SHA. Saved asynchronously to local NVMe,
uploaded to object storage, retained by policy, verified by a load-and-forward job.

Run:  python3 checkpoint.py   (single process, CPU, < 20 s)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any

import torch
import torch.distributed as dist
import torch.distributed.checkpoint as dcp
from torch.distributed.checkpoint.state_dict import (
    StateDictOptions,
    get_model_state_dict,
    get_optimizer_state_dict,
    set_model_state_dict,
    set_optimizer_state_dict,
)
from torch.distributed.checkpoint.stateful import Stateful


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


@dataclass
class RetentionPolicy:
    keep_last: int = 6                   # 30-min checkpoints kept on NVMe/PFS (3 h)
    keep_hourly_for_steps: int = 31_560  # 24 h at 2.738 s/step
    permanent_every_steps: int = 59_787  # 91 x 657-step checkpoints = 501.6B tokens at 8,388,608 tokens/step
    steps_per_hour: int = 1_315          # 3600 / 2.738
    pinned: set[int] = field(default_factory=set)  # eval-best or milestone steps, never pruned

    def to_delete(self, steps_present: list[int], current_step: int) -> list[int]:
        steps = sorted(steps_present)
        keep = set(steps[-self.keep_last:])
        for s in steps:
            if s % self.permanent_every_steps == 0 or s in self.pinned:
                keep.add(s)
            elif current_step - s <= self.keep_hourly_for_steps and s % self.steps_per_hour < 657:
                keep.add(s)  # the first checkpoint of every hour within the rolling day
        return [s for s in steps if s not in keep]


class Checkpointer:
    def __init__(self, local_dir: str, remote_uri: str | None, policy: RetentionPolicy,
                 process_group: dist.ProcessGroup | None = None) -> None:
        self.local_dir, self.remote_uri, self.policy = local_dir, remote_uri, policy
        self.pg = process_group
        self._pending: Any = None
        os.makedirs(local_dir, exist_ok=True)

    def path(self, step: int) -> str:
        return os.path.join(self.local_dir, f"step-{step:09d}")

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

    def wait(self) -> None:
        if self._pending is not None:
            self._pending.result()
            self._pending = None

    def _finalise(self, p: str, step: int) -> None:
        with open(os.path.join(p, "MANIFEST.json"), "w") as f:
            json.dump({"step": step, "sha256": dir_sha256(p), "complete": True}, f)
        if self.remote_uri:
            upload(p, f"{self.remote_uri}/{os.path.basename(p)}")
        self.prune(step)

    def prune(self, current_step: int) -> None:
        present = [int(d.split("-")[1]) for d in os.listdir(self.local_dir) if d.startswith("step-")]
        for s in self.policy.to_delete(present, current_step):
            shutil.rmtree(self.path(s), ignore_errors=True)

    def latest(self) -> str | None:
        done = [d for d in os.listdir(self.local_dir)
                if d.startswith("step-") and os.path.exists(os.path.join(self.local_dir, d, "MANIFEST.json"))]
        return os.path.join(self.local_dir, max(done)) if done else None

    def load(self, wrapper: ModelOptWrapper, state: TrainState, p: str) -> None:
        """Resharding on load is automatic: DCP maps saved shards onto the current mesh."""
        dcp.load({"train": wrapper, "app": state}, checkpoint_id=p)


def dir_sha256(p: str) -> str:
    h = hashlib.sha256()
    for name in sorted(os.listdir(p)):
        if name.endswith(".distcp") or name == ".metadata":
            with open(os.path.join(p, name), "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
    return h.hexdigest()


def upload(local: str, remote: str) -> None:
    """Background upload; the training process never waits on object storage."""
    subprocess.Popen(["bash", "-c", f"command -v aws >/dev/null && aws s3 sync --quiet {local} {remote} || true"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def verify(wrapper: ModelOptWrapper, p: str, probe: torch.Tensor, expected: torch.Tensor) -> bool:
    """Load-and-forward check run by a side job on every uploaded checkpoint."""
    state = TrainState()
    dcp.load({"train": wrapper, "app": state}, checkpoint_id=p)
    with torch.no_grad():
        out = wrapper.model(probe)
    return bool(torch.allclose(out, expected, atol=1e-5)) and state.step > 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from model import ModelConfig, Transformer

    t0 = time.time()
    torch.manual_seed(0)
    cfg = ModelConfig.tiny()
    model = Transformer(cfg)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, betas=(0.9, 0.95), weight_decay=0.1)
    x = torch.randint(0, cfg.vocab_size, (2, cfg.max_seq_len))
    for _ in range(3):  # populate Adam state
        loss = model(x[:, :-1], x[:, 1:])
        opt.zero_grad()
        loss.backward()
        opt.step()
    probe = x[:, :8]
    with torch.no_grad():
        expected = model(probe)
    with tempfile.TemporaryDirectory() as d:
        ck = Checkpointer(d, remote_uri=None, policy=RetentionPolicy(keep_last=2))
        state = TrainState(step=657, tokens_seen=657 * 8_388_608, loader_state={"epoch": 0, "k": 1314, "cursors": {"web": 900}},
                           meta={"git": "abc123", "tokenizer_sha256": "t" * 64, "config": json.dumps(cfg.__dict__)})
        p = ck.save(ModelOptWrapper(model, opt), state, step=657, async_=False)
        assert os.path.exists(os.path.join(p, "MANIFEST.json")) and ck.latest() == p
        # perturb everything, then restore and compare
        fresh = Transformer(cfg)
        fresh_opt = torch.optim.AdamW(fresh.parameters(), lr=1e-3, betas=(0.9, 0.95), weight_decay=0.1)
        fresh_state = TrainState()
        ck.load(ModelOptWrapper(fresh, fresh_opt), fresh_state, p)
        for (n1, p1), (n2, p2) in zip(model.named_parameters(), fresh.named_parameters()):
            assert n1 == n2 and torch.equal(p1, p2), n1
        for k, v in opt.state_dict()["state"][0].items():
            assert torch.equal(v, fresh_opt.state_dict()["state"][0][k]) if torch.is_tensor(v) else v == fresh_opt.state_dict()["state"][0][k]
        assert fresh_state.step == 657 and fresh_state.loader_state["cursors"]["web"] == 900
        assert fresh_state.tokens_seen == 657 * 8_388_608 and fresh_state.meta["git"] == "abc123"
        assert verify(ModelOptWrapper(fresh, fresh_opt), p, probe, expected)
        # one more training step on both must stay bit-identical (optimizer state restored exactly)
        for m, o in ((model, opt), (fresh, fresh_opt)):
            loss = m(x[:, :-1], x[:, 1:])
            o.zero_grad()
            loss.backward()
            o.step()
        assert all(torch.equal(a, b) for a, b in zip(model.parameters(), fresh.parameters()))
        # retention: 657-step cadence, keep the last 2, hourly within 24 h, permanent every 91 checkpoints
        pol = RetentionPolicy(keep_last=2)
        present = [657 * i for i in range(1, 101)]          # 100 checkpoints, 50 h of training
        dele = pol.to_delete(present, current_step=65_700)
        assert 59_787 not in dele                           # permanent (91 x 657)
        assert 65_700 not in dele and 65_043 not in dele    # keep_last
        assert 6_570 in dele                                # older than 24 h, not permanent
        kept_recent = [s_ for s_ in present if 65_700 - s_ <= 31_560 and s_ not in dele]
        assert 20 <= len(kept_recent) <= 30, len(kept_recent)  # about one per hour over the last day
        assert len(dele) > 40
        for s in (1314, 1971, 2628):
            ck.save(ModelOptWrapper(model, opt), state, step=s, async_=False)
        assert len([d_ for d_ in os.listdir(d) if d_.startswith("step-")]) <= 4  # policy applied
    print(f"OK checkpoint.py in {time.time() - t0:.1f}s")
