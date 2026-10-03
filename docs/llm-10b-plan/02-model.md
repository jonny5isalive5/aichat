## 02. Transformer block and model design

Covers: transformer block design, and the first PyTorch implementation example (`code/model.py`).
All numbers come from `decision-record.md` (DR) section 2.

### Decisions

- **9.80B dense decoder, d_model 4096 x 40 layers.** The low end of the 9.5-11B window: training and serving cost scale with N, and quality at this size is set by data and tokens (11.0T, 1,123 tokens per parameter). Aspect ratio 102 is in the well-trodden Llama range.
- **GQA 32 query heads / 8 KV heads, head_dim 128.** KV cache is 4x smaller than MHA at serving (section 08); H100-shaped GEMMs (multiples of 128).
- **SwiGLU, ffn 14336 (= 56 x 256), pre-norm RMSNorm, RoPE, no biases, no dropout.** Every component has production precedent (Llama 3, Qwen 2.5, OLMo 2). Nothing experimental goes into a 49-day run.
- **QK-norm before RoPE and z-loss 1e-4.** Both cost under 1% throughput; each divergence they prevent saves a multi-day rollback (section 09).
- **Untied embeddings, vocab 131,072 (2^17).** Separate input and output matrices add 0.54B params but let the lm_head take its own init (std 0.0156) and shard evenly on 8/16/64 ranks.
- **bf16 autocast with fp32 master weights; RMSNorm, softmax, logsumexp and the residual stream in fp32.** FP8 is piloted on the 3B ladder model only (DR section 4), never switched on in the main run without that pilot.
- **Production attention = flash-attn 3 varlen with document-masked packing; reference code = torch SDPA.** The reference file runs on CPU and is the oracle for the production kernel path.

### Procedure

1. Implement `code/model.py` exactly as below. Run `python3 code/model.py`. It must print the parameter table ending in `total 9,798,236,160` and `OK`.
2. Add the three unit checks the smoke test already performs to CI: (a) formula count == meta-device count == DR table, (b) chunked loss == unchunked loss within 1e-4, (c) 5 optimizer steps on the tiny config reduce the loss.
3. Register the production attention op (week 7, Block 1):
   - `pip install flash-attn==3.*` built for Hopper (sm90), pinned by commit hash in the container image.
   - Wrap `flash_attn_varlen_func` with `torch.library.custom_op("plan::fa3_varlen", mutates_args=())` and a `register_fake` that returns `torch.empty_like(q)`, so each block compiles with `torch.compile(fullgraph=True)`.
   - Equivalence test: for 64 random packed batches at seq 4096 with 1-40 documents, the custom op output must match the SDPA path with an explicit block-diagonal causal mask within 2e-3 (bf16) per element.
   - Fallback path: FlexAttention with a `block_mask` built from `cu_seqlens` (document-causal). Keep it compiled and benchmarked; it is 10-20% slower in backward on H100 and is used only if FA3 breaks on a torch upgrade.
4. Numerics checks on the 1B ladder model (week 8): activation RMS per layer must stay within [0.3, 30] over the first 10B tokens; attention logit max must stay under 50 with QK-norm on; z-loss term must stay under 0.5% of the total loss after warmup. These three are the alarms wired in section 06.
5. Long-context extension (end of Block 2): call `set_rope_theta(4_000_000, 32_768)` before the 32k stage and `set_rope_theta(16_000_000, 131_072)` before the 128k stage. Weights are untouched; only the RoPE tables change. Verify with a needle-in-a-haystack pass at 32k before starting the 128k stage.
6. Export: `torch.distributed.checkpoint` state (section 06) converts to a Hugging Face `LlamaForCausalLM`-compatible safetensors layout (q/k/v/o, gate/up/down, RMSNorm names) plus `qk_norm` weights, so vLLM loads it without a custom model class (section 08). The export script asserts logits equality on 32 prompts within 1e-2 in bf16.

### Architecture

One block (pre-norm, two residual adds). Shapes are per token.

```text
                     x [4096] (residual stream, fp32 outside autocast)
                       |
          +------------+-------------------------------------------+
          |                                                        |
      RMSNorm (fp32)                                               |
          |                                                        |
   +------+------+------+                                          |
   |             |      |                                          |
  Wq           Wk     Wv          Wq: 4096 -> 32x128 = 4096        |
 [4096]      [1024] [1024]        Wk, Wv: 4096 -> 8x128 = 1024     |
   |             |      |                                          |
 q_norm        k_norm   |         RMSNorm over head_dim, BEFORE RoPE|
   |             |      |                                          |
  RoPE          RoPE    |         theta 500k (4k) / 4M (32k) / 16M (128k)
   |             |      |                                          |
   +------+------+------+                                          |
          |                                                        |
   causal attention, GQA 4:1      FA3 varlen (prod) / SDPA (ref)   |
          |                                                        |
         Wo   4096 -> 4096        init std 0.02/sqrt(80) = 0.00224 |
          |                                                        |
          +-------------------------------------------(+)----------+
                                                       |
          +--------------------------------------------+-----------+
          |                                                        |
      RMSNorm (fp32)                                               |
          |                                                        |
   +------+------+                                                 |
   |             |                                                 |
  W1 (gate)    W3 (up)      4096 -> 14336 each                     |
   |             |                                                 |
  SiLU           |                                                 |
   +------x------+                                                 |
          |                                                        |
         W2 (down)          14336 -> 4096, init std 0.00224        |
          |                                                        |
          +-------------------------------------------(+)----------+
                                                       |
                                                 x' [4096]
```

Full model:

```text
 tokens [B, S] --> Embedding 131072 x 4096 (std 0.02)
                       |
                 Block x 40  (each: 218,112,256 params)
                       |
                 RMSNorm (final)
                       |
                 LM head 4096 -> 131072 (untied, std 0.0156)
                       |
            chunked fp32 cross-entropy + z-loss (2048-token chunks)
```

### Decision table

| Component | Chosen | Alternative considered | Why |
|---|---|---|---|
| Width / depth | 4096 x 40 | 5120 x 32 (same N) | 40 layers keeps per-layer GEMMs at Llama-3-8B shapes that torchtitan and FA3 are tuned for; depth helps reasoning benchmarks at equal N |
| Attention | GQA 32/8 | MHA 32/32, MQA 32/1 | 4x smaller KV cache than MHA with no measurable loss at this scale; MQA loses quality on long context |
| head_dim | 128 | 64, 256 | FA3 fastest path on Hopper; 256 halves the head count and hurts GQA ratio |
| FFN | SwiGLU 14336 | GeLU 16384 | SwiGLU at 3.5x d_model is the Llama/Qwen operating point; 14336 is a multiple of 256 for tensor-core tiling |
| Norm | pre-norm RMSNorm, eps 1e-5, fp32 | post-norm, LayerNorm | pre-norm trains stably without warmup tricks; RMSNorm is 10-15% cheaper than LayerNorm |
| Position | RoPE theta 500k | ALiBi, learned | RoPE extends to 128k with theta scaling and no weight change; ALiBi hurts retrieval over long context |
| QK-norm | yes, before RoPE | none | removes the attention-logit growth that causes most bf16 loss spikes; after RoPE it breaks relative position |
| z-loss | 1e-4 | none | keeps logsumexp near 0 so the lm_head stays well conditioned; negligible cost |
| Embeddings | untied | tied | tied saves 0.54B params but forces one init and one LR for two different roles |
| Vocab | 131,072 | 65,536; 262,144 | 10-15% fewer tokens per byte on code and multilingual text than 64k; 256k inflates the lm_head cost per token |
| Biases / dropout | none | | nothing at this scale benefits; removing them simplifies FSDP sharding |

### Numerics

| Tensor | dtype | Where |
|---|---|---|
| Master weights, Adam m and v | fp32 | FSDP2 sharded DTensor (section 05) |
| Weights for matmul, activations | bf16 | `MixedPrecisionPolicy(param_dtype=bf16)` |
| RMSNorm (all), QK-norm | fp32 compute, bf16 output | `RMSNorm.forward` upcasts |
| Attention softmax | fp32 inside the kernel | FA3 and SDPA both accumulate in fp32 |
| Residual stream | fp32 | FSDP2 keeps the block input dtype; the add is outside autocast |
| Logits, logsumexp, CE, z-loss | fp32 | `_chunk_loss` casts the chunk's logits |
| Gradient reduce | fp32 | `MixedPrecisionPolicy(reduce_dtype=fp32)` |

Chunked loss: 2048 tokens x 131,072 vocab x 4 B = 1.07 GB of fp32 logits per chunk, so a 8,192-token micro-batch never materialises the 4.3 GB full logit tensor. `torch.utils.checkpoint` around each chunk recomputes the chunk's logits in backward, which is the same trick the Liger fused linear-cross-entropy kernel applies; the DR memory table books 2.0 GB for this.

### Parameter and FLOP accounting

| Component | Formula | Params |
|---|---|---|
| Attention per layer (q, k, v, o) | 4096*4096 + 2*4096*1024 + 4096*4096 | 41,943,040 |
| MLP per layer (gate, up, down) | 3*4096*14336 | 176,160,768 |
| Norms per layer (2 x d_model + q_norm + k_norm) | 2*4096 + 2*128 | 8,448 |
| Per layer | | 218,112,256 |
| 40 layers | 40 * 218,112,256 | 8,724,490,240 |
| Final RMSNorm | 4096 | 4,096 |
| Input embedding | 131072*4096 | 536,870,912 |
| LM head (untied) | 131072*4096 | 536,870,912 |
| Total | | 9,798,236,160 |
| Non-embedding | | 8,724,494,336 |

FLOPs per token at seq 4096: 6 * 9,798,236,160 = 58,789,416,960 (6ND), plus the causal attention term 12 * 40 * 4096 * 4096 / 2 = 4,026,531,840, total 62,815,948,800. This is the number the MFU gates in sections 05 and 06 use: 989e12 * 0.38 / 62.816e9 = 5,983 tokens/s/GPU.

### Reference implementation

Core classes from `code/model.py` (the file also holds the config, the parameter formula, init and the smoke test).

```python
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
```

Init and the chunked loss (from `Transformer`):

```python
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

    def _chunk_loss(self, h: torch.Tensor, t: torch.Tensor) -> torch.Tensor:
        """Sum of CE + z-loss over one chunk. fp32 logits exist only for this chunk."""
        logits = F.linear(h, self.lm_head.weight).float()
        lse = torch.logsumexp(logits, dim=-1)
        ce = lse - logits.gather(-1, t.unsqueeze(-1)).squeeze(-1)
        return (ce + self.cfg.z_loss * lse.pow(2)).sum()

    def forward(self, tokens: torch.Tensor, targets: torch.Tensor | None = None,
                chunked: bool = True) -> torch.Tensor:
        h = self.hidden(tokens)
        if targets is None:
            return self.lm_head(h)
        hf, tf = h.reshape(-1, h.shape[-1]), targets.reshape(-1)
        if not chunked:
            return self._chunk_loss(hf, tf) / tf.numel()
        total = hf.new_zeros((), dtype=torch.float32)
        for i in range(0, hf.shape[0], self.cfg.ce_chunk):
            hc, tc = hf[i:i + self.cfg.ce_chunk], tf[i:i + self.cfg.ce_chunk]
            total = total + checkpoint(self._chunk_loss, hc, tc, use_reentrant=False)
        return total / tf.numel()
```

Smoke test output on CPU (13 s):

```text
total                     9,798,236,160
non_embedding             8,724,494,336
losses: [6.7906, 4.9235, 3.5524, 2.4959, 1.7242]
OK model.py smoke test in 13.3s
```

### Checklist

- [ ] `python3 code/model.py` passes: formula count == meta-device count == 9,798,236,160; FLOPs/token at 4k == 62,815,948,800.
- [ ] FA3 varlen custom op registered, `register_fake` present, equivalence test vs masked SDPA within 2e-3 on 64 packed batches.
- [ ] FlexAttention fallback compiled and benchmarked; slowdown recorded.
- [ ] Numerics alarms (activation RMS, attention logit max, z-loss share) wired into the metrics logger (section 06).
- [ ] `set_rope_theta` verified at 32k with a needle test before the 128k stage.
- [ ] HF-layout export script asserts logits equality within 1e-2 on 32 prompts; vLLM loads the export (section 08).
