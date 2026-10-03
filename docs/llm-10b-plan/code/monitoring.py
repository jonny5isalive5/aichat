"""Training metrics logger with spike detection, NaN guard and MFU (section 06).

Writes JSON lines (one object per step) that Loki/Promtail ship to Grafana, and optionally
mirrors to Weights & Biases. Alerts are decided here (fast, in-process) and also by
Prometheus rules on the exported gauges; this file is the in-process half.

Run:  python3 monitoring.py   (CPU, < 2 s)
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

H100_PEAK_BF16 = 989e12
FLOPS_PER_TOKEN_4K = 62_815_948_800  # DR section 2; model.flops_per_token(dr10b, 4096)


@dataclass
class Alert:
    step: int
    kind: str
    message: str


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


@dataclass
class MetricsLogger:
    path: str
    world_size: int
    flops_per_token: int = FLOPS_PER_TOKEN_4K
    wandb_run: Any = None
    on_alert: Callable[[Alert], None] | None = None
    loss_det: SpikeDetector = field(default_factory=SpikeDetector)
    grad_det: SpikeDetector = field(default_factory=lambda: SpikeDetector(ratio=3.0, k_sigma=6.0))
    throughput_window: deque = field(default_factory=lambda: deque(maxlen=50))
    alerts: list[Alert] = field(default_factory=list)
    _f: Any = None

    def __post_init__(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._f = open(self.path, "a", buffering=1)

    def log_step(self, step: int, loss: float, grad_norm: float, lr: float, tokens: int,
                 step_time: float, breakdown: dict[str, float] | None = None,
                 extra: dict[str, float] | None = None) -> dict[str, Any]:
        tok_s = tokens / max(step_time, 1e-9)
        self.throughput_window.append(tok_s)
        mfu = tok_s * self.flops_per_token / (H100_PEAK_BF16 * self.world_size)
        rec: dict[str, Any] = {
            "ts": time.time(), "step": step, "loss": loss, "grad_norm": grad_norm, "lr": lr,
            "tokens": tokens, "step_time_s": step_time, "tok_s": tok_s, "tok_s_per_gpu": tok_s / self.world_size,
            "mfu": mfu, **(breakdown or {}), **(extra or {}),
        }
        if not math.isfinite(loss) or not math.isfinite(grad_norm):
            self._alert(step, "nan", f"non-finite loss={loss} grad_norm={grad_norm}")
        if self.loss_det.update(loss):
            self._alert(step, "loss_spike", f"loss {loss:.4f} vs ema {self.loss_det.ema:.4f}")
        if self.grad_det.update(grad_norm):
            self._alert(step, "grad_spike", f"grad_norm {grad_norm:.3f} vs ema {self.grad_det.ema:.3f}")
        if len(self.throughput_window) == self.throughput_window.maxlen:
            recent = sum(list(self.throughput_window)[-10:]) / 10
            base = sum(self.throughput_window) / len(self.throughput_window)
            if recent < 0.85 * base:
                self._alert(step, "throughput_drop", f"{recent:,.0f} tok/s vs window {base:,.0f}")
        rec["alerts"] = [a.kind for a in self.alerts if a.step == step]
        self._f.write(json.dumps(rec) + "\n")
        if self.wandb_run is not None:
            self.wandb_run.log(rec, step=step)
        return rec

    def _alert(self, step: int, kind: str, message: str) -> None:
        a = Alert(step, kind, message)
        self.alerts.append(a)
        if self.on_alert:
            self.on_alert(a)

    def close(self) -> None:
        self._f.close()


def expected_tok_s_per_gpu(mfu: float, flops_per_token: int = FLOPS_PER_TOKEN_4K) -> float:
    return H100_PEAK_BF16 * mfu / flops_per_token


if __name__ == "__main__":
    import random
    import tempfile

    t0 = time.time()
    rng = random.Random(0)
    with tempfile.TemporaryDirectory() as d:
        fired: list[Alert] = []
        log = MetricsLogger(os.path.join(d, "metrics.jsonl"), world_size=512, on_alert=fired.append)
        tokens, step_time = 8_388_608, 2.738
        for step in range(1, 601):
            loss = 2.4 + 0.01 * rng.gauss(0, 1) - step * 1e-4
            gn = 0.6 + 0.03 * rng.gauss(0, 1)
            if step == 400:
                loss += 1.0           # a real spike
            if step == 450:
                gn = 5.0
            if step == 500:
                loss = float("nan")
            st = step_time * (1.4 if step > 560 else 1.0)  # a straggler slows the cluster by 40 %
            rec = log.log_step(step, loss, gn, 3e-4, tokens, st, breakdown={"t_fwd": 0.9, "t_bwd": 1.6, "t_opt": 0.1})
        kinds = {a.kind for a in fired}
        assert {"loss_spike", "grad_spike", "nan", "throughput_drop"} <= kinds, kinds
        assert any(a.step == 400 and a.kind == "loss_spike" for a in fired)
        assert any(a.step == 450 and a.kind == "grad_spike" for a in fired)
        assert not any(a.kind == "loss_spike" and a.step < 100 for a in fired)  # warmup: no false alarms
        assert abs(rec["tok_s_per_gpu"] * 1.4 - 5984) < 20  # 40 % slower than the 5,983 plan
        assert abs(expected_tok_s_per_gpu(0.38) - 5983) < 1
        lines = open(os.path.join(d, "metrics.jsonl")).read().splitlines()
        assert len(lines) == 600 and json.loads(lines[399])["alerts"] == ["loss_spike"]
        log.close()
    print(f"OK monitoring.py in {time.time() - t0:.1f}s: {len(fired)} alerts {sorted(kinds)}")
