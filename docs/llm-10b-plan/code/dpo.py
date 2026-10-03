"""Direct Preference Optimization from scratch, with a frozen reference model (section 07).

loss = -log sigmoid(beta * [(log pi(yw|x) - log ref(yw|x)) - (log pi(yl|x) - log ref(yl|x))])
Sequence log-probs sum over response tokens only (prompt tokens masked). The implicit reward
of a response is beta * (log pi - log ref); the margin chosen - rejected must rise during training.

Run:  python3 dpo.py   (CPU, tiny model, < 20 s)
"""
from __future__ import annotations

import copy
import os
import sys
import time

import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import ModelConfig, Transformer  # noqa: E402
from sft import IGNORE, SPECIAL, ToyTokenizer, Turn, render_chat  # noqa: E402


def sequence_logprobs(model: Transformer, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Sum of log p(y_t | x_<t) over positions where y != IGNORE. Returns [batch]."""
    logits = model(x).float()                                   # [B, S, V]
    mask = y != IGNORE
    y_safe = torch.where(mask, y, torch.zeros_like(y))
    logp = torch.log_softmax(logits, dim=-1).gather(-1, y_safe.unsqueeze(-1)).squeeze(-1)
    return (logp * mask).sum(-1)


def dpo_loss(policy: Transformer, ref: Transformer, batch: dict[str, torch.Tensor], beta: float,
             length_normalise: bool = False) -> tuple[torch.Tensor, dict[str, float]]:
    pi_w = sequence_logprobs(policy, batch["x_w"], batch["y_w"])
    pi_l = sequence_logprobs(policy, batch["x_l"], batch["y_l"])
    with torch.no_grad():
        ref_w = sequence_logprobs(ref, batch["x_w"], batch["y_w"])
        ref_l = sequence_logprobs(ref, batch["x_l"], batch["y_l"])
    if length_normalise:  # SimPO-style; use when chosen responses are systematically longer
        n_w, n_l = (batch["y_w"] != IGNORE).sum(-1), (batch["y_l"] != IGNORE).sum(-1)
        pi_w, pi_l, ref_w, ref_l = pi_w / n_w, pi_l / n_l, ref_w / n_w, ref_l / n_l
    r_w, r_l = beta * (pi_w - ref_w), beta * (pi_l - ref_l)   # implicit rewards
    loss = -F.logsigmoid(r_w - r_l).mean()
    stats = {"reward_chosen": r_w.mean().item(), "reward_rejected": r_l.mean().item(),
             "margin": (r_w - r_l).mean().item(), "accuracy": (r_w > r_l).float().mean().item()}
    return loss, stats


def build_pair(prompt: list[Turn], chosen: str, rejected: str, encode, seq_len: int) -> dict[str, torch.Tensor]:
    def one(resp: str) -> tuple[torch.Tensor, torch.Tensor]:
        ids, mask = render_chat(prompt + [Turn("assistant", resp)], encode)
        ids, mask = ids[: seq_len + 1], mask[: seq_len + 1]
        pad = seq_len + 1 - len(ids)
        ids, mask = ids + [SPECIAL["pad"]] * pad, mask + [0] * pad
        x, y = torch.tensor(ids[:-1]), torch.tensor(ids[1:])
        y = torch.where(torch.tensor(mask[1:], dtype=torch.bool), y, torch.full_like(y, IGNORE))
        return x, y

    xw, yw = one(chosen)
    xl, yl = one(rejected)
    return {"x_w": xw, "y_w": yw, "x_l": xl, "y_l": yl}


def collate(pairs: list[dict[str, torch.Tensor]]) -> dict[str, torch.Tensor]:
    return {k: torch.stack([p[k] for p in pairs]) for k in pairs[0]}


def train_dpo(policy: Transformer, pairs: list[dict[str, torch.Tensor]], steps: int, lr: float, beta: float,
              batch: int) -> list[dict[str, float]]:
    ref = copy.deepcopy(policy).eval()
    for p in ref.parameters():
        p.requires_grad_(False)
    opt = torch.optim.AdamW(policy.parameters(), lr=lr, betas=(0.9, 0.95), weight_decay=0.0)
    history = []
    g = torch.Generator().manual_seed(0)
    for step in range(steps):
        idx = torch.randperm(len(pairs), generator=g)[:batch].tolist()
        loss, stats = dpo_loss(policy, ref, collate([pairs[i] for i in idx]), beta)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
        opt.step()
        history.append({"loss": loss.item(), **stats})
    return history


if __name__ == "__main__":
    t0 = time.time()
    torch.manual_seed(0)
    tok = ToyTokenizer()
    cfg = ModelConfig.tiny()
    cfg.vocab_size, cfg.max_seq_len = 512, 96
    policy = Transformer(cfg)
    pairs = [build_pair([Turn("user", f"Question {i}?")], chosen=f"Answer {i}.", rejected=f"I refuse {i}!!",
                        encode=tok.encode, seq_len=cfg.max_seq_len) for i in range(16)]
    # prompt tokens are masked, response tokens are not
    assert int((pairs[0]["y_w"] != IGNORE).sum()) == len(tok.encode("Answer 0.")) + 1
    hist = train_dpo(policy, pairs, steps=40, lr=3e-4, beta=0.1, batch=8)
    first, last = hist[0], hist[-1]
    assert abs(first["margin"]) < 1e-4, first                   # policy == reference at step 0
    assert last["margin"] > 0.5 and last["accuracy"] == 1.0, last
    assert last["loss"] < first["loss"]
    assert last["reward_chosen"] > 0 > last["reward_rejected"]  # chosen up, rejected down vs reference
    print(f"OK dpo.py in {time.time() - t0:.1f}s: loss {first['loss']:.3f} -> {last['loss']:.3f}, "
          f"margin {last['margin']:.2f}, accuracy {last['accuracy']:.2f}")
