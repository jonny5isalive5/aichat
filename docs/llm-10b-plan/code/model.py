"""Reference implementation of the 10B dense decoder (section 02 of the plan).

Shapes, init and numerics follow docs/llm-10b-plan/decision-record.md:
d_model 4096, 40 layers, 32 heads / 8 KV heads, head_dim 128, SwiGLU 14336,
vocab 131072, untied embeddings, pre-norm RMSNorm, QK-norm before RoPE,
RoPE theta 500k, z-loss 1e-4, no biases, no dropout.

Production attention goes through flash-attn 3 varlen (document-masked packing);
this file uses torch SDPA so it runs anywhere, including CPU for the smoke test.

Run:  python3 model.py   (CPU, < 30 s)
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint


@dataclass
class ModelConfig:
    vocab_size: int = 131072
    d_model: int = 4096
    n_layers: int = 40
    n_heads: int = 32
    n_kv_heads: int = 8
    head_dim: int = 128
    ffn_hidden: int = 14336
    rope_theta: float = 500_000.0
    norm_eps: float = 1e-5
    qk_norm: bool = True
    z_loss: float = 1e-4
    tie_embeddings: bool = False
    init_std: float = 0.02
    max_seq_len: int = 4096
    ce_chunk: int = 2048  # tokens per cross-entropy chunk

    @classmethod
    def dr10b(cls) -> "ModelConfig":
        return cls()

    @classmethod
    def tiny(cls) -> "ModelConfig":
        return cls(vocab_size=512, d_model=64, n_layers=2, n_heads=4, n_kv_heads=2,
                   head_dim=16, ffn_hidden=160, max_seq_len=64, ce_chunk=16)

    @property
    def out_proj_std(self) -> float:  # o_proj and down_proj: std / sqrt(2 * n_layers)
        return self.init_std / math.sqrt(2 * self.n_layers)

    @property
    def lm_head_std(self) -> float:  # d_model ** -0.5
        return self.d_model ** -0.5


def count_params(cfg: ModelConfig) -> dict[str, int]:
    """Parameter table from shapes alone (no allocation). Matches the DR table."""
    d, h, kv, hd, f = cfg.d_model, cfg.n_heads, cfg.n_kv_heads, cfg.head_dim, cfg.ffn_hidden
    attn = d * (h * hd) + 2 * d * (kv * hd) + (h * hd) * d
    mlp = 3 * d * f
    norms = 2 * d + (2 * hd if cfg.qk_norm else 0)
    per_layer = attn + mlp + norms
    embed = cfg.vocab_size * d
    lm_head = 0 if cfg.tie_embeddings else cfg.vocab_size * d
    total = cfg.n_layers * per_layer + d + embed + lm_head
    return {
        "attention_per_layer": attn, "mlp_per_layer": mlp, "norms_per_layer": norms,
        "per_layer": per_layer, "all_layers": cfg.n_layers * per_layer, "final_norm": d,
        "embedding": embed, "lm_head": lm_head, "total": total,
        "non_embedding": total - embed - lm_head,
        "flop_bearing": total - embed,  # lm_head matmuls count, the embedding lookup does not
    }


def flops_per_token(cfg: ModelConfig, seq_len: int) -> int:
    """6N on the total count plus the causal attention term 12 * L * d * s / 2 (fwd+bwd)."""
    n = count_params(cfg)["total"]
    attn = 12 * cfg.n_layers * cfg.d_model * seq_len // 2
    return 6 * n + attn


class RMSNorm(nn.Module):
    """RMSNorm computed in fp32 regardless of the autocast dtype."""

    def __init__(self, dim: int, eps: float) -> None:
        super().__init__()
        self.eps = eps
        self.weight = nn.Parameter(torch.ones(dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        xf = x.float()
        out = xf * torch.rsqrt(xf.pow(2).mean(-1, keepdim=True) + self.eps)
        return (out * self.weight.float()).to(x.dtype)


def rope_cache(head_dim: int, max_seq_len: int, theta: float, device=None) -> tuple[torch.Tensor, torch.Tensor]:
    """cos/sin tables [seq, head_dim] for the rotate-half convention (HF Llama layout)."""
    inv = 1.0 / (theta ** (torch.arange(0, head_dim, 2, device=device).float() / head_dim))
    t = torch.arange(max_seq_len, device=device).float()
    freqs = torch.outer(t, inv)  # [seq, head_dim/2]
    emb = torch.cat([freqs, freqs], dim=-1)
    return emb.cos(), emb.sin()


def apply_rope(x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
    """x: [B, H, S, D]; cos/sin: [S, D]. Pairs dim i with dim i + D/2 (rotate-half)."""
    half = x.shape[-1] // 2
    x1, x2 = x[..., :half], x[..., half:]
    rotated = torch.cat([-x2, x1], dim=-1)
    return (x.float() * cos + rotated.float() * sin).to(x.dtype)


class Attention(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.n_heads, self.n_kv, self.hd = cfg.n_heads, cfg.n_kv_heads, cfg.head_dim
        self.wq = nn.Linear(cfg.d_model, cfg.n_heads * cfg.head_dim, bias=False)
        self.wk = nn.Linear(cfg.d_model, cfg.n_kv_heads * cfg.head_dim, bias=False)
        self.wv = nn.Linear(cfg.d_model, cfg.n_kv_heads * cfg.head_dim, bias=False)
        self.wo = nn.Linear(cfg.n_heads * cfg.head_dim, cfg.d_model, bias=False)
        self.q_norm = RMSNorm(cfg.head_dim, cfg.norm_eps) if cfg.qk_norm else nn.Identity()
        self.k_norm = RMSNorm(cfg.head_dim, cfg.norm_eps) if cfg.qk_norm else nn.Identity()

    def forward(self, x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
        b, s, _ = x.shape
        q = self.wq(x).view(b, s, self.n_heads, self.hd).transpose(1, 2)  # [B, H, S, D]
        k = self.wk(x).view(b, s, self.n_kv, self.hd).transpose(1, 2)
        v = self.wv(x).view(b, s, self.n_kv, self.hd).transpose(1, 2)
        q, k = self.q_norm(q), self.k_norm(k)          # QK-norm BEFORE RoPE
        q, k = apply_rope(q, cos[:s], sin[:s]), apply_rope(k, cos[:s], sin[:s])
        # Production: flash_attn_varlen_func(q, k, v, cu_seqlens, ..., causal=True) wrapped as a custom op.
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True, enable_gqa=True)
        return self.wo(y.transpose(1, 2).reshape(b, s, self.n_heads * self.hd))


class SwiGLU(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.w1 = nn.Linear(cfg.d_model, cfg.ffn_hidden, bias=False)  # gate
        self.w3 = nn.Linear(cfg.d_model, cfg.ffn_hidden, bias=False)  # up
        self.w2 = nn.Linear(cfg.ffn_hidden, cfg.d_model, bias=False)  # down

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.w2(F.silu(self.w1(x)) * self.w3(x))


class Block(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.attn_norm = RMSNorm(cfg.d_model, cfg.norm_eps)
        self.attn = Attention(cfg)
        self.mlp_norm = RMSNorm(cfg.d_model, cfg.norm_eps)
        self.mlp = SwiGLU(cfg)

    def forward(self, x: torch.Tensor, cos: torch.Tensor, sin: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.attn_norm(x), cos, sin)   # residual stream stays in the autocast
        return x + self.mlp(self.mlp_norm(x))             # input dtype (fp32 outside autocast)


class Transformer(nn.Module):
    def __init__(self, cfg: ModelConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.embed = nn.Embedding(cfg.vocab_size, cfg.d_model)
        self.layers = nn.ModuleList(Block(cfg) for _ in range(cfg.n_layers))
        self.norm = RMSNorm(cfg.d_model, cfg.norm_eps)
        self.lm_head = nn.Linear(cfg.d_model, cfg.vocab_size, bias=False)
        if cfg.tie_embeddings:
            self.lm_head.weight = self.embed.weight
        cos, sin = rope_cache(cfg.head_dim, cfg.max_seq_len, cfg.rope_theta)
        self.register_buffer("rope_cos", cos, persistent=False)
        self.register_buffer("rope_sin", sin, persistent=False)
        self.reset_parameters()

    def set_rope_theta(self, theta: float, max_seq_len: int) -> None:
        """Long-context extension: 500k -> 4M at 32k, 16M at 128k. Weights are untouched."""
        self.cfg.rope_theta, self.cfg.max_seq_len = theta, max_seq_len
        cos, sin = rope_cache(self.cfg.head_dim, max_seq_len, theta, device=self.rope_cos.device)
        self.rope_cos, self.rope_sin = cos, sin

    @torch.no_grad()
    def reset_parameters(self) -> None:
        std, out_std = self.cfg.init_std, self.cfg.out_proj_std
        for name, p in self.named_parameters():
            if p.ndim < 2:
                p.fill_(1.0)  # RMSNorm scales (QK-norm included)
            elif name.endswith(("attn.wo.weight", "mlp.w2.weight")):
                nn.init.trunc_normal_(p, std=out_std, a=-3 * out_std, b=3 * out_std)
            elif name == "lm_head.weight" and not self.cfg.tie_embeddings:
                s = self.cfg.lm_head_std
                nn.init.trunc_normal_(p, std=s, a=-3 * s, b=3 * s)
            else:
                nn.init.trunc_normal_(p, std=std, a=-3 * std, b=3 * std)

    def hidden(self, tokens: torch.Tensor) -> torch.Tensor:
        x = self.embed(tokens)
        for layer in self.layers:
            x = layer(x, self.rope_cos, self.rope_sin)
        return self.norm(x)

    def _chunk_loss(self, h: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
        """Sum of CE + z-loss over one chunk. fp32 logits exist only for this chunk."""
        logits = F.linear(h, self.lm_head.weight).float()
        lse = torch.logsumexp(logits, dim=-1)
        ce = lse - logits.gather(-1, t.unsqueeze(-1)).squeeze(-1)
        return (ce + self.cfg.z_loss * lse.pow(2)).sum()

    def forward(self, tokens: torch.Tensor, targets: torch.Tensor | None = None,
                chunked: bool = True) -> torch.Tensor:
        """Returns logits [B, S, V] when targets is None, else the mean (CE + z-loss) per token."""
        h = self.hidden(tokens)
        if targets is None:
            return self.lm_head(h)
        hf, tf = h.reshape(-1, h.shape[-1]), targets.reshape(-1)
        if not chunked:
            return self._chunk_loss(hf, tf) / tf.numel()
        total = hf.new_zeros((), dtype=torch.float32)
        for i in range(0, hf.shape[0], self.cfg.ce_chunk):
            hc, tc = hf[i:i + self.cfg.ce_chunk], tf[i:i + self.cfg.ce_chunk]
            # recompute the chunk's logits in backward instead of keeping them alive
            total = total + checkpoint(self._chunk_loss, hc, tc, use_reentrant=False)
        return total / tf.numel()


def print_param_table(cfg: ModelConfig) -> None:
    for k, v in count_params(cfg).items():
        print(f"{k:22s} {v:>16,d}")


if __name__ == "__main__":
    t0 = time.time()
    torch.manual_seed(0)
    dr = ModelConfig.dr10b()
    table = count_params(dr)
    print_param_table(dr)
    assert table["total"] == 9_798_236_160, table["total"]
    assert table["non_embedding"] == 8_724_494_336
    assert flops_per_token(dr, 4096) == 62_815_948_800, flops_per_token(dr, 4096)
    # The formula must agree with the real module shapes: build the DR model on the meta device.
    with torch.device("meta"):
        meta_total = sum(p.numel() for p in Transformer(dr).parameters())
    assert meta_total == table["total"], (meta_total, table["total"])

    cfg = ModelConfig.tiny()
    model = Transformer(cfg)
    assert sum(p.numel() for p in model.parameters()) == count_params(cfg)["total"]
    opt = torch.optim.AdamW(model.parameters(), lr=3e-3, betas=(0.9, 0.95), weight_decay=0.1)
    x = torch.randint(0, cfg.vocab_size, (4, cfg.max_seq_len))
    y = torch.roll(x, -1, dims=1)
    with torch.no_grad():
        l_chunk, l_full = model(x, y, chunked=True), model(x, y, chunked=False)
    assert abs(l_chunk.item() - l_full.item()) < 1e-4, (l_chunk.item(), l_full.item())
    losses = []
    for step in range(5):
        loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        losses.append(loss.item())
    print("losses:", [round(l, 4) for l in losses])
    assert losses[-1] < losses[0], losses
    model.set_rope_theta(4_000_000.0, 128)
    assert model(x[:, :8]).shape == (4, 8, cfg.vocab_size)
    print(f"OK model.py smoke test in {time.time() - t0:.1f}s")
