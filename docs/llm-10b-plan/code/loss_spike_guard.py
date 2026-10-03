"""Training-loop guard for loss spikes and divergence (section 09 runbook 1, executable).

Policy (DR section 4 skip-step rule plus the rollback ladder):
  1. grad-norm > 3 x its 100-step EMA, or a non-finite loss/grad  -> skip the optimizer step
  2. 3 consecutive skips                                            -> roll back to the last verified
     checkpoint and advance the data seed (the loader skips the offending window)
  3. a second rollback within 1,000 steps                           -> also cut the peak LR by 20 %
  4. a third rollback within 1,000 steps                            -> stop the run, page the tech lead
Loss spikes (loss > 1.25 x EMA) are logged and raise an alert but do not skip by themselves:
the gradient norm is the earlier and more specific signal.

Run:  python3 loss_spike_guard.py   (< 1 s)
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class GuardConfig:
    grad_factor: float = 3.0
    ema_steps: int = 100
    warmup_steps: int = 100          # no skipping before the EMA is meaningful
    max_consecutive_skips: int = 3
    rollback_window_steps: int = 1_000
    lr_cut: float = 0.8
    max_rollbacks_in_window: int = 3
    loss_spike_ratio: float = 1.25


@dataclass
class GuardDecision:
    action: str                      # "step" | "skip" | "rollback" | "rollback_lr_cut" | "stop"
    reason: str
    lr_scale: float = 1.0


@dataclass
class LossSpikeGuard:
    cfg: GuardConfig
    rollback: Callable[[int], int]   # given the current step, restores a checkpoint and returns its step
    grad_ema: float = 0.0
    loss_ema: float = 0.0
    n: int = 0
    consecutive_skips: int = 0
    rollback_steps: list[int] = field(default_factory=list)
    lr_scale: float = 1.0
    events: list[tuple[int, str]] = field(default_factory=list)

    def _update_ema(self, cur: float, new: float) -> float:
        return new if self.n == 0 else cur + (new - cur) / min(self.n + 1, self.cfg.ema_steps)

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


if __name__ == "__main__":
    import random

    t0 = time.time()
    rng = random.Random(0)
    last_ckpt = {"step": 0}
    restored_to: list[int] = []

    def fake_rollback(step: int) -> int:
        restored_to.append(last_ckpt["step"])
        return last_ckpt["step"]

    guard = LossSpikeGuard(GuardConfig(), fake_rollback)
    actions: dict[int, str] = {}
    step = 0
    while step < 3000:
        if step % 657 == 0:
            last_ckpt["step"] = step
        loss, gn = 2.5 + 0.01 * rng.gauss(0, 1), 0.6 + 0.03 * rng.gauss(0, 1)
        if step in (500, 501, 502):           # three bad steps in a row -> rollback
            gn = 4.0
        if step in (900, 901, 902):           # again inside the window -> rollback + LR cut
            gn = 5.0
        if step == 1200:                      # a lone spike -> skip only
            gn, loss = 3.5, 3.5
        if step in (2400, 2401, 2402):        # outside the window -> plain rollback, no cut
            loss, gn = float("nan"), float("nan")
        d = guard.observe(step, loss, gn)
        actions[step] = d.action
        step += 1
    assert actions[500] == "skip" and actions[501] == "skip" and actions[502] == "rollback", [actions[s] for s in (500, 501, 502)]
    assert actions[902] == "rollback_lr_cut" and abs(guard.lr_scale - 0.8) < 1e-9
    assert actions[1200] == "skip" and actions[1201] == "step"
    assert any(s == 1200 and "loss_spike_alert" in e for s, e in guard.events)
    assert actions[2402] == "rollback" and abs(guard.lr_scale - 0.8) < 1e-9   # no second cut
    assert restored_to == [0, 657, 1971], restored_to                         # last 657-step checkpoints
    assert not any(a == "stop" for a in actions.values())
    # a third rollback inside one window stops the run
    g2 = LossSpikeGuard(GuardConfig(), fake_rollback)
    for s in range(200):
        g2.observe(s, 2.5, 0.6)
    outcomes = [g2.observe(200 + i, 2.5, 9.0).action for i in range(9)]
    assert outcomes[2] == "rollback" and outcomes[5] == "rollback_lr_cut" and outcomes[8] == "stop", outcomes
    print(f"OK loss_spike_guard.py in {time.time() - t0:.1f}s: {len(guard.events)} events")
