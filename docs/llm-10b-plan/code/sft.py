"""Supervised fine-tuning: chat template, packing with loss masking, cosine schedule (section 07).

The chat template is rendered from special-token IDS (never from text, see section 03):
  <|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system}<|eot_id|>
  <|start_header_id|>user<|end_header_id|>\n\n{user}<|eot_id|>
  <|start_header_id|>assistant<|end_header_id|>\n\n{assistant}<|eot_id|>
Loss is taken on assistant content tokens and their <|eot_id|> only.

Run:  python3 sft.py   (CPU, tiny model, < 20 s)
"""
from __future__ import annotations

import math
import os
import sys
import time
from dataclasses import dataclass
from typing import Callable

import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import ModelConfig, Transformer  # noqa: E402

# ids 0-63 are the reserved specials (section 03); byte tokens follow at 64..319 in the BPE vocab
SPECIAL = {"bos": 0, "eos": 1, "pad": 2, "start_header": 4, "end_header": 5, "eot": 6, "eom": 7,
           "tool_call": 8, "tool_call_end": 9, "tool_result": 10, "tool_result_end": 11}
IGNORE = -100


@dataclass
class Turn:
    role: str      # system | user | assistant | tool
    content: str


def render_chat(turns: list[Turn], encode: Callable[[str], list[int]],
                add_generation_prompt: bool = False) -> tuple[list[int], list[int]]:
    """Returns (token ids, loss mask). Mask is 1 on assistant content + its <|eot_id|>."""
    ids, mask = [SPECIAL["bos"]], [0]
    for t in turns:
        header = [SPECIAL["start_header"], *encode(t.role), SPECIAL["end_header"], *encode("\n\n")]
        body = encode(t.content)
        ids += header
        mask += [0] * len(header)
        train = t.role == "assistant"
        ids += body + [SPECIAL["eot"]]
        mask += [int(train)] * (len(body) + 1)
    if add_generation_prompt:
        ids += [SPECIAL["start_header"], *encode("assistant"), SPECIAL["end_header"], *encode("\n\n")]
        mask += [0] * (len(ids) - len(mask))
    return ids, mask


def pack(examples: list[tuple[list[int], list[int]]], seq_len: int) -> list[dict[str, torch.Tensor]]:
    """Greedy packing into seq_len + 1 windows; a conversation never crosses a window boundary
    (longer ones are truncated); cu_seqlens stops attention across conversations."""
    windows: list[dict[str, torch.Tensor]] = []
    buf_ids: list[int] = []
    buf_mask: list[int] = []
    bounds: list[int] = [0]

    def flush() -> None:
        if not buf_ids:
            return
        n = seq_len + 1 - len(buf_ids)
        ids = buf_ids + [SPECIAL["pad"]] * n
        msk = buf_mask + [0] * n
        x, y = torch.tensor(ids[:-1]), torch.tensor(ids[1:])
        m = torch.tensor(msk[1:], dtype=torch.bool)       # mask aligned to targets
        y = torch.where(m, y, torch.full_like(y, IGNORE))
        cu = torch.tensor(bounds + ([seq_len] if bounds[-1] != seq_len else []), dtype=torch.int32)
        windows.append({"input": x, "target": y, "cu_seqlens": cu})

    for ids, mask in examples:
        ids, mask = ids[: seq_len + 1], mask[: seq_len + 1]
        if len(buf_ids) + len(ids) > seq_len + 1:
            flush()
            buf_ids, buf_mask, bounds = [], [], [0]
        buf_ids += ids
        buf_mask += mask
        bounds.append(min(len(buf_ids), seq_len))
    flush()
    return windows


def masked_loss(model: Transformer, x: torch.Tensor, y: torch.Tensor, chunk: int = 2048) -> torch.Tensor:
    """Mean CE over unmasked targets; logits computed per chunk in fp32 like model._chunk_loss."""
    h = model.hidden(x).reshape(-1, model.cfg.d_model)
    t = y.reshape(-1)
    total, count = h.new_zeros((), dtype=torch.float32), (t != IGNORE).sum()
    for i in range(0, h.shape[0], chunk):
        logits = F.linear(h[i:i + chunk], model.lm_head.weight).float()
        total = total + F.cross_entropy(logits, t[i:i + chunk], ignore_index=IGNORE, reduction="sum")
    return total / count.clamp(min=1)


def cosine_lr(step: int, total: int, peak: float, warmup: int, floor_ratio: float = 0.1) -> float:
    if step < warmup:
        return peak * step / max(warmup, 1)
    p = (step - warmup) / max(total - warmup, 1)
    return peak * (floor_ratio + (1 - floor_ratio) * 0.5 * (1 + math.cos(math.pi * p)))


def train_sft(model: Transformer, windows: list[dict[str, torch.Tensor]], epochs: int, peak_lr: float,
              batch: int, warmup_ratio: float = 0.03, weight_decay: float = 0.0) -> list[float]:
    opt = torch.optim.AdamW(model.parameters(), lr=peak_lr, betas=(0.9, 0.95), weight_decay=weight_decay)
    steps_per_epoch = math.ceil(len(windows) / batch)
    total = epochs * steps_per_epoch
    losses, step = [], 0
    for epoch in range(epochs):
        order = torch.randperm(len(windows), generator=torch.Generator().manual_seed(epoch))
        for b in range(0, len(windows), batch):
            ws = [windows[i] for i in order[b:b + batch].tolist()]
            x = torch.stack([w["input"] for w in ws])
            y = torch.stack([w["target"] for w in ws])
            for g in opt.param_groups:
                g["lr"] = cosine_lr(step, total, peak_lr, int(warmup_ratio * total))
            loss = masked_loss(model, x, y)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            losses.append(loss.item())
            step += 1
    return losses


class ToyTokenizer:
    """Byte-level stand-in with the production id layout (specials 0-63, bytes from 64)."""

    def encode(self, text: str) -> list[int]:
        return [64 + b for b in text.encode("utf-8")]

    def decode(self, ids: list[int]) -> str:
        return bytes(i - 64 for i in ids if i >= 64).decode("utf-8", errors="replace")


if __name__ == "__main__":
    t0 = time.time()
    torch.manual_seed(0)
    tok = ToyTokenizer()
    convs = [
        [Turn("system", "You are terse."), Turn("user", f"Add {i} and {i + 1}."), Turn("assistant", f"{2 * i + 1}")]
        for i in range(24)
    ] + [[Turn("user", "Say hi."), Turn("assistant", "hi"), Turn("user", "Again."), Turn("assistant", "hi")]]
    rendered = [render_chat(c, tok.encode) for c in convs]
    ids, mask = rendered[-1]
    # the mask covers exactly the assistant bodies plus their <|eot_id|>: "hi" (2 bytes) + eot, twice
    assert sum(mask) == 2 * (2 + 1), sum(mask)
    assert ids[0] == SPECIAL["bos"] and ids.count(SPECIAL["eot"]) == 4
    gen_ids, _ = render_chat(convs[0][:2], tok.encode, add_generation_prompt=True)
    assert tok.decode(gen_ids[-13:]) == "assistant\n\n" and gen_ids[-3] == SPECIAL["end_header"]
    cfg = ModelConfig.tiny()
    cfg.vocab_size, cfg.max_seq_len = 512, 128
    windows = pack(rendered, seq_len=cfg.max_seq_len)
    assert all(w["input"].shape == (128,) and w["cu_seqlens"][-1] == 128 for w in windows)
    assert sum(int((w["target"] != IGNORE).sum()) for w in windows) == sum(sum(m[1:]) for _, m in rendered)
    model = Transformer(cfg)
    losses = train_sft(model, windows, epochs=6, peak_lr=3e-3, batch=4)
    assert losses[-1] < 0.5 * losses[0], (losses[0], losses[-1])
    print(f"OK sft.py in {time.time() - t0:.1f}s: {len(windows)} packed windows, loss {losses[0]:.3f} -> {losses[-1]:.3f}")
