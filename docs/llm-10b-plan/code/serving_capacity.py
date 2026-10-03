"""Serving capacity and cost calculator for the 9.8B model on H100 80 GB (section 08).

Formulas:
  weights_bytes      = params * bytes_per_weight
  kv_bytes_per_token = 2 (K and V) * n_layers * n_kv_heads * head_dim * bytes_per_kv
  kv_budget          = hbm * gpu_memory_utilization - weights - workspace
  concurrency(ctx)   = kv_budget / (kv_bytes_per_token * ctx)
  decode tok/s       = batch / ((weights + batch * avg_ctx * kv_bytes) / (hbm_bw * efficiency))
  prefill tok/s      = peak_flops * efficiency / (2 * params)
  usd per 1M tokens  = usd_per_gpu_hour / (tok_s * 3600) * 1e6

Run:  python3 serving_capacity.py   (< 1 s)
"""
from __future__ import annotations

from dataclasses import dataclass

PARAMS = 9_798_236_160
N_LAYERS, N_KV_HEADS, HEAD_DIM = 40, 8, 128
HBM_BYTES = 80 * 1024 ** 3
HBM_BW = 3.35e12                      # H100 SXM HBM3
PEAK_BF16, PEAK_FP8 = 989e12, 1979e12
USD_RESERVED, USD_ONDEMAND = 2.20, 2.90  # DR assumptions
PLAN_TOK_S_PER_GPU = 2500             # DR serving assumption (SLO-bound, mixed prefill/decode)


@dataclass
class ServingConfig:
    weight_bytes: int = 1             # 1 = FP8 (W8A8), 2 = BF16
    kv_bytes: int = 1                 # 1 = FP8 KV cache, 2 = BF16 KV cache
    gpu_memory_utilization: float = 0.90
    workspace_gb: float = 4.0         # CUDA graphs, activations, sampler
    hbm_efficiency: float = 0.60      # achieved fraction of HBM bandwidth during decode
    flops_efficiency: float = 0.50    # achieved fraction of peak during prefill

    @property
    def name(self) -> str:
        return f"W{'8' if self.weight_bytes == 1 else '16'}-KV{'8' if self.kv_bytes == 1 else '16'}"


def weights_bytes(cfg: ServingConfig) -> float:
    return PARAMS * cfg.weight_bytes


def kv_bytes_per_token(cfg: ServingConfig) -> int:
    return 2 * N_LAYERS * N_KV_HEADS * HEAD_DIM * cfg.kv_bytes


def kv_budget_bytes(cfg: ServingConfig) -> float:
    return HBM_BYTES * cfg.gpu_memory_utilization - weights_bytes(cfg) - cfg.workspace_gb * 1024 ** 3


def concurrency(cfg: ServingConfig, ctx: int) -> int:
    return int(kv_budget_bytes(cfg) // (kv_bytes_per_token(cfg) * ctx))


def decode_tok_s(cfg: ServingConfig, batch: int, avg_ctx: int) -> float:
    bytes_per_step = weights_bytes(cfg) + batch * avg_ctx * kv_bytes_per_token(cfg)
    return batch / (bytes_per_step / (HBM_BW * cfg.hbm_efficiency))


def prefill_tok_s(cfg: ServingConfig) -> float:
    peak = PEAK_FP8 if cfg.weight_bytes == 1 else PEAK_BF16
    return peak * cfg.flops_efficiency / (2 * PARAMS)


def usd_per_million(tok_s: float, usd_per_gpu_hour: float) -> float:
    return usd_per_gpu_hour / (tok_s * 3600) * 1e6


def table(cfg: ServingConfig) -> dict[str, float]:
    return {
        "weights_GB": weights_bytes(cfg) / 1e9,
        "kv_KB_per_token": kv_bytes_per_token(cfg) / 1024,
        "kv_budget_GB": kv_budget_bytes(cfg) / 1e9,
        "concurrent_4k": concurrency(cfg, 4096),
        "concurrent_8k": concurrency(cfg, 8192),
        "concurrent_32k": concurrency(cfg, 32768),
        "concurrent_128k": concurrency(cfg, 131072),
        "decode_tok_s_b128_ctx2k": decode_tok_s(cfg, 128, 2048),
        "decode_tok_s_b32_ctx8k": decode_tok_s(cfg, 32, 8192),
        "prefill_tok_s": prefill_tok_s(cfg),
        "ttft_ms_2k_prompt": 2048 / prefill_tok_s(cfg) * 1000,
        "usd_per_M_output_plan_reserved": usd_per_million(PLAN_TOK_S_PER_GPU, USD_RESERVED),
        "usd_per_M_output_plan_ondemand": usd_per_million(PLAN_TOK_S_PER_GPU, USD_ONDEMAND),
        "usd_per_M_input_reserved": usd_per_million(prefill_tok_s(cfg), USD_RESERVED),
    }


if __name__ == "__main__":
    rows = {c.name: table(c) for c in (ServingConfig(1, 1), ServingConfig(2, 2))}
    keys = list(next(iter(rows.values())).keys())
    print(f"{'metric':34s}" + "".join(f"{n:>14s}" for n in rows))
    for k in keys:
        print(f"{k:34s}" + "".join(f"{rows[n][k]:14,.3f}" if isinstance(rows[n][k], float) else f"{rows[n][k]:14,d}" for n in rows))
    fp8, bf16 = rows["W8-KV8"], rows["W16-KV16"]
    assert kv_bytes_per_token(ServingConfig(2, 2)) == 163_840 and kv_bytes_per_token(ServingConfig(1, 1)) == 81_920
    assert abs(bf16["weights_GB"] - 19.596) < 0.001 and abs(fp8["weights_GB"] - 9.798) < 0.001
    assert abs(fp8["usd_per_M_output_plan_reserved"] - 0.2444) < 0.001   # DR: 0.244
    assert abs(fp8["usd_per_M_output_plan_ondemand"] - 0.3222) < 0.001   # DR: 0.322
    assert fp8["concurrent_4k"] > 2 * bf16["concurrent_4k"]
    assert fp8["decode_tok_s_b128_ctx2k"] > PLAN_TOK_S_PER_GPU * 2  # plan number is conservative by design
    print("OK serving_capacity.py")
