#!/usr/bin/env python3
"""
dr_calc.py -- single source of truth for every derived number in DECISION_RECORD.md.

Run:  python3 dr_calc.py            prints every table (markdown) and writes decision_record.json
      python3 dr_calc.py --json     prints the JSON only

Built from the cost_first proposal (judges' winner) with the judges' corrections applied and the
grafted ideas from quality_first / risk_first. Every assertion below is a budget or fit rule the DR
relies on; the script exits non-zero if any of them breaks.
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, asdict

# =====================================================================================
# 0. ASSUMPTIONS (DR section 10). Change here, nowhere else.
# =====================================================================================
A = {
    "h100_peak_bf16_flops": 989e12,     # dense BF16 per H100 SXM (brief)
    "usd_gpu_hr_reserved": 2.20,        # one master contract (RFQ target 2.20, walk-away 2.40), capacity schedule 8 -> 72 -> 536 -> 56 -> 8 GPUs,
                                        # W1-W40 (dev node to W40; the 64/528/48-GPU blocks end W30)
    "usd_gpu_hr_ondemand": 2.90,        # on-demand tail (serving pilot W31-40, overflow)
    "usd_gpu_hr_spot": 1.50,            # ablations / evals overflow only, never the main run
    "mfu_main": 0.38,                   # PLANNING value over 6ND + causal attention FLOPs (0.355 on the 6ND basis), seq 4096,
                                        # HSDP + compile + FA3 varlen, = the acceptance gate on 512 GPUs (G2 gate 0.40 on 64 GPUs
                                        # minus 0.02 for 512-GPU stragglers). The budget is built at this value and is never re-based
                                        # upward: before the W12 freeze mfu_main := G2 measurement - 0.02 and the Block 2 fit is
                                        # regenerated; every MFU point above 0.38 becomes stable tokens through the date-driven anneal
                                        # rule (MFU_TOKENS_PER_POINT_T below), 0.42 is upside (12.5T), not the plan.
                                        # MFU always means tokens/s x FPT_4K / 989e12 (tokens/s is basis-free; see TOKS_* gates).
    "mfu_longctx_32k": 0.35,            # CP=8 inside the node, SAC(op), micro-batch 2 (4,096 local tokens per sequence)
    "mfu_longctx_128k": 0.25,           # CP=8, 128k, FULL per-block activation checkpointing (SAC(op) does not fit: 84.8 GB = MEM_LC2_SAC)
    "mfu_post": 0.30,                   # SFT / RM / DPO
    "mfu_rl_train": 0.25,               # RL trainer side
    "overhead_main": 1.18,              # build-up in OVERHEAD_BREAKDOWN below (sums to 17.8 %)
    "overhead_small": 1.25,             # ladder, ablations, rehearsal, long-context stages
    "overhead_post": 1.30,              # SFT / RM / DPO
    "overhead_rl": 3.00,                # online RL (generation tail, weight sync, idle trainer)
    "interrupts_per_day_per_512": 0.5,  # one hardware interruption every 2 days per 512 GPUs
    "ckpt_interval_min": 30,            # async DCP to local NVMe AND uploaded to object store every interval
    "restart_min": 15,                  # relaunch + compile cache warm + first step
    "usd_tb_month_object": 21.0,
    "usd_tb_month_pfs": 80.0,
    "usd_per_tb_egress": 50.0,
    "usd_cpu_core_hr": 0.045,
    "usd_ram_node_hr": 4.00,
    "bytes_per_token_text": 4.5,
    "weeks_total": 40,                  # kickoff to served model; INCLUDES the W13-14 pre-block float, the 2-week contract start window
                                        # (Block 2 may slip to W17 inside the plan) and the W39-40 buffer
    "block2_start_week": 15,
    "contract_start_window_weeks": 2,
    "nvlink_gbps": 450e9,               # unidirectional per GPU
    "ib_gbps": 50e9,                    # 400 Gb/s NIC per GPU, line rate
    "ib_gbps_realistic": 40e9,          # what a 64-node ring all-reduce sustains in practice (35-42 GB/s)
    "tokenizer_shrink_web": 0.87,       # our 131k BPE vs the ~50k tokenizers the web sources are quoted in (10-15 % fewer tokens)
    "anneal_token_floor": 9.0e12,       # the anneal may not start below this many stable tokens; below it, buy compute (options)
    "serving_tok_s_per_gpu": 2500.0,    # vLLM FP8 W8A8, batch 64, 10B dense (assumption)
    "rl_gen_tok_s_per_gpu": 3000.0,     # vLLM bf16 rollouts for GRPO (assumption)
}
PEAK = A["h100_peak_bf16_flops"]
RES = A["usd_gpu_hr_reserved"]
OD = A["usd_gpu_hr_ondemand"]
HRS_WK = 168
GB = 1024 ** 3


def gpu_hr_flop(mfu: float) -> float:
    """Useful FLOP delivered by one H100 in one hour at the given MFU."""
    return PEAK * mfu * 3600


# =====================================================================================
# 1. MODEL
# =====================================================================================
@dataclass
class Shape:
    name: str
    d_model: int
    n_layers: int
    n_heads: int
    n_kv_heads: int
    ffn_hidden: int
    vocab: int = 131072
    tied: bool = False

    @property
    def head_dim(self) -> int:
        return self.d_model // self.n_heads

    @property
    def kv_dim(self) -> int:
        return self.n_kv_heads * self.head_dim

    def counts(self) -> dict:
        d, L, V = self.d_model, self.n_layers, self.vocab
        attn = d * d + 2 * d * self.kv_dim + d * d           # q, k, v, o
        mlp = 3 * d * self.ffn_hidden                        # SwiGLU gate, up, down
        norms = 2 * d + 2 * self.head_dim                    # attn_norm, mlp_norm, q_norm, k_norm (per head_dim)
        per_layer = attn + mlp + norms
        final_norm = d
        embed = V * d
        lm_head = 0 if self.tied else V * d
        total = L * per_layer + final_norm + embed + lm_head
        nonembed = L * per_layer + final_norm
        return dict(attn=attn, mlp=mlp, norms=norms, per_layer=per_layer, layers_total=L * per_layer,
                    final_norm=final_norm, embed=embed, lm_head=lm_head, total=total, nonembed=nonembed,
                    flop_bearing=nonembed + V * d)

    def attn_flops_per_token(self, seq: int) -> float:
        # QK^T and AV: 4*s*d per token per layer forward, x3 for fwd+bwd = 12*s*d, causal halves it.
        return 6 * self.n_layers * seq * self.d_model

    def flops_per_token(self, seq: int) -> float:
        # 6 * N_total (conservative: includes the input embedding, +5.8 % margin) + causal attention term.
        return 6 * self.counts()["total"] + self.attn_flops_per_token(seq)


MODEL = Shape("10B", d_model=4096, n_layers=40, n_heads=32, n_kv_heads=8, ffn_hidden=14336)
MC = MODEL.counts()
assert MODEL.ffn_hidden % 256 == 0 and MODEL.vocab % 256 == 0
assert 9.5e9 <= MC["total"] <= 11e9, MC["total"]

MIB = 1024 * 1024
LADDER = [  # name, shape, tokens per run, LR points, seeds, MFU, global batch (tokens). Every run: main-run WSD + 10 % 1-sqrt decay,
            # ranked on POST-DECAY loss. Batch grows with N (sqrt batch-LR correction applied when transferring; (LR, batch) swept jointly at 400M).
    ("150M", Shape("150M", 1024, 14, 8, 2, 2816), 6e9, 6, 2, 0.20, MIB // 2),
    ("400M", Shape("400M", 1536, 16, 12, 4, 4096), 12e9, 5, 2, 0.25, MIB),
    ("1B", Shape("1B", 2048, 22, 16, 4, 5632), 30e9, 4, 1, 0.32, 2 * MIB),
    ("3B", Shape("3B", 3072, 30, 24, 8, 8192), 90e9, 3, 1, 0.38, 4 * MIB),   # 3 LRs (fit x 0.67, 1.0, 1.5): a parabola needs three points
]
SHP_1B, SHP_3B = LADDER[2][1], LADDER[3][1]
LADDER_DURATION = [  # duration axis for lr*(N, D): (name, shape, tokens per run, LR points, MFU, batch, note)
    ("1B x 120B", SHP_1B, 120e9, 3, 0.32, 2 * MIB, "3 LRs around the 1B/30B optimum; with 1B/30B gives d lr*/d D at fixed N"),
    ("3B x 300B", SHP_3B, 300e9, 1, 0.38, 4 * MIB, "second LR (fit x 1.5) at 300B; the full-recipe rehearsal at the fitted LR is the first point"),
]


# --- functional forms the gates G2 and G5 are scored against (fitted at G2 on post-decay losses; self-tested below)
def lr_star(N: float, a: float, b: float) -> float:
    """Optimal peak LR as a power law in non-embedding params: lr*(N) = a * N^-b."""
    return a * N ** (-b)


def fit_lr_power_law(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Log-log least squares of lr* = a * N^-b over [(N_nonembed, lr*)]. Returns (a, b, R^2 in log space)."""
    xs = [math.log(n) for n, _ in points]
    ys = [math.log(lr) for _, lr in points]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    return math.exp(intercept), -slope, 1 - ss_res / ss_tot


def chinchilla_form(N: float, D: float, E: float, A_: float, B_: float, alpha: float = 0.34, beta: float = 0.28) -> float:
    """L(N, D) = E + A / N^alpha + B / D^beta (Hoffmann et al. form; exponents fixed, E/A/B fitted)."""
    return E + A_ / N ** alpha + B_ / D ** beta


def fit_chinchilla(points: list[tuple[float, float, float]], alpha: float = 0.34, beta: float = 0.28) -> tuple[float, float, float, float]:
    """Linear least squares for (E, A, B) given the exponents, over [(N, D, post-decay loss)]. Returns (E, A, B, rmse)."""
    rows = [(1.0, n ** (-alpha), d ** (-beta), l) for n, d, l in points]
    # normal equations (3 x 3), solved by Gaussian elimination
    M = [[sum(r[i] * r[j] for r in rows) for j in range(3)] for i in range(3)]
    v = [sum(r[i] * r[3] for r in rows) for i in range(3)]
    for i in range(3):
        piv = max(range(i, 3), key=lambda k: abs(M[k][i]))
        M[i], M[piv], v[i], v[piv] = M[piv], M[i], v[piv], v[i]
        for k in range(i + 1, 3):
            f = M[k][i] / M[i][i]
            for j in range(i, 3):
                M[k][j] -= f * M[i][j]
            v[k] -= f * v[i]
    sol = [0.0, 0.0, 0.0]
    for i in (2, 1, 0):
        sol[i] = (v[i] - sum(M[i][j] * sol[j] for j in range(i + 1, 3))) / M[i][i]
    rmse = math.sqrt(sum((chinchilla_form(n, d, *sol, alpha, beta) - l) ** 2 for n, d, l in points) / len(points))
    return sol[0], sol[1], sol[2], rmse


def predict_loss_anchored(N: float, D: float, fit: tuple[float, float, float], anchor: tuple[float, float, float]) -> float:
    """Post-decay prediction: the fitted L(N, D) shifted by the residual at the anchor run (3B/300B rehearsal: (N, D, post-decay loss))."""
    E, A_, B_ = fit[:3]
    n0, d0, l0 = anchor
    return chinchilla_form(N, D, E, A_, B_) + (l0 - chinchilla_form(n0, d0, E, A_, B_))


DECAY_FRAC = 0.10        # WSD decay fraction on every ladder run and the main run (1.1T of 11.0T)


def stable_minus_postdecay_delta(stable_loss_at_decay_start: float, postdecay_loss: float) -> float:
    """Per ladder run: loss at the end of the stable phase (0.9 D tokens, peak LR) minus the post-decay loss at D tokens.
    Logged for every run; it is roughly size-invariant at a fixed 10 % decay and is the quantity G3b's '>= 2 %' gate measures."""
    return stable_loss_at_decay_start - postdecay_loss


def predict_stable_loss(N: float, D: float, fit: tuple[float, float, float], delta: float) -> float:
    """Stable-phase (peak-LR) loss after D stable tokens: L_stable(N, D) = L_postdecay(N, D / (1 - DECAY_FRAC)) + delta, i.e. the
    post-decay loss of a run whose stable phase is D tokens long, plus the measured stable-minus-postdecay gap."""
    E, A_, B_ = fit[:3]
    return chinchilla_form(N, D / (1 - DECAY_FRAC), E, A_, B_) + delta


def predict_stable_loss_anchored(N: float, D: float, fit: tuple[float, float, float], delta: float, anchor: tuple[float, float, float]) -> float:
    """G5 prediction (main run is at peak LR at 1T / 4T / 8T, so it is compared with STABLE-phase curves, never post-decay ones):
    predict_stable_loss shifted by its residual at the anchor = the 3B/300B rehearsal's stable-phase loss at the decay start
    (N_3B, 270B stable tokens, measured loss on the same 6-domain held-out set)."""
    n0, d0, l0 = anchor
    return predict_stable_loss(N, D, fit, delta) + (l0 - predict_stable_loss(n0, d0, fit, delta))


def log_lr_parabola_optimum(points: list[tuple[float, float]]) -> float:
    """G2 at 3B: the optimum of a parabola through three (LR, post-decay loss) points in log(LR). Returns the LR at the vertex."""
    assert len(points) == 3
    xs = [math.log(lr) for lr, _ in points]
    ys = [l for _, l in points]
    (x0, x1, x2), (y0, y1, y2) = xs, ys
    denom = (x0 - x1) * (x0 - x2) * (x1 - x2)
    a = (x2 * (y1 - y0) + x1 * (y0 - y2) + x0 * (y2 - y1)) / denom
    b = (x2 * x2 * (y0 - y1) + x1 * x1 * (y2 - y0) + x0 * x0 * (y1 - y2)) / denom
    assert a > 0, "the three LRs must bracket the optimum (loss convex in log LR)"
    return math.exp(-b / (2 * a))


G5_BAND_NATS = 0.02           # |stable-phase val loss - anchored stable prediction| at 1T / 4T / 8T must be <= this
G2_3B_BAND_NATS = 0.02        # 3B/90B post-decay loss vs the L(N, D) fit from the three smaller sizes
G2_LR_OPT_RATIO_MAX = 1.5     # the 3-point log-LR parabola optimum at 3B/90B must lie within this factor of the extrapolated lr*(N)
G2_LR_BRACKET_LOSS_PCT = 0.5  # post-decay loss at the two bracketing LRs (fit x 0.67, x 1.5) differs by <= this (flat optimum)
G2_R2_REPORTED = "R^2 of the 3-point lr*(N) fit is reported, not gated (a 2-parameter fit through 3 points cannot fail an R^2 test)"
LR_CLAMP = (3.0e-4, 6.0e-4)   # main-run peak LR = clamp(lr*(N, D) extrapolated to 8.72B x 11.0T, 3e-4, 6e-4); prior 3e-4
# self-test on synthetic data so the forms are exercised on every run
_pts = [(1.2e8, lr_star(1.2e8, 0.9, 0.42)), (3.5e8, lr_star(3.5e8, 0.9, 0.42)), (1.0e9, lr_star(1.0e9, 0.9, 0.42))]
_a, _b, _r2 = fit_lr_power_law(_pts)
assert abs(_a - 0.9) < 1e-9 and abs(_b - 0.42) < 1e-9 and _r2 > 0.9999, (_a, _b, _r2)
_cpts = [(n, d, chinchilla_form(n, d, 1.69, 406.4, 410.7)) for n, d in ((1.2e8, 6e9), (3.5e8, 12e9), (1.0e9, 30e9), (1.0e9, 120e9), (3.0e9, 90e9))]
_E, _A, _B, _rmse = fit_chinchilla(_cpts)
assert abs(_E - 1.69) < 1e-6 and abs(_A - 406.4) < 1e-3 and abs(_B - 410.7) < 1e-3 and _rmse < 1e-9, (_E, _A, _B, _rmse)
_fit = (_E, _A, _B)
_delta = 0.045                                                   # a plausible ladder gap (2.2 % of L ~ 2.0)
_anchor_stable = (2.8e9, 270e9, predict_stable_loss(2.8e9, 270e9, _fit, _delta) + 0.01)   # rehearsal lands 0.01 above the fit
_p = predict_stable_loss_anchored(8.7e9, 1e12, _fit, _delta, _anchor_stable)
assert abs(_p - (predict_stable_loss(8.7e9, 1e12, _fit, _delta) + 0.01)) < 1e-12, _p
assert abs(predict_stable_loss(8.7e9, 0.9e12, _fit, 0.0) - chinchilla_form(8.7e9, 1e12, *_fit)) < 1e-12   # 0.9 D stable = post-decay at D
assert abs(stable_minus_postdecay_delta(2.05, 2.005) - 0.045) < 1e-12
_lr_opt = 3.3e-4
_par = [(lr, 2.0 + 0.8 * (math.log(lr / _lr_opt)) ** 2) for lr in (_lr_opt * 0.67, _lr_opt, _lr_opt * 1.5)]
assert abs(log_lr_parabola_optimum(_par) / _lr_opt - 1) < 1e-9, log_lr_parabola_optimum(_par)

# =====================================================================================
# 2. TOKENS AND DATA
# =====================================================================================
SEQ_PRETRAIN, SEQ_POST, SEQ_LC1, SEQ_LC2 = 4096, 8192, 32768, 131072
# PLAN = what the 8-week block delivers at the planning MFU 0.38; DESIGN POINT = what the data plan is sized for. The date-driven
# anneal rule turns every MFU point above 0.38 into stable tokens (12.0T lands at MFU_FOR_DESIGN, ~0.40 = the gate value; 12.5T at 0.42).
TOK_STABLE, TOK_ANNEAL = 9.9e12, 1.1e12            # 11.0T plan, 10 % decay fraction (DECAY_FRAC)
TOK_PRETRAIN = TOK_STABLE + TOK_ANNEAL
TOK_DESIGN = 12.0e12                                # design point: the mix, caps and extension pool support it
assert abs(TOK_ANNEAL / TOK_PRETRAIN - DECAY_FRAC) < 1e-9
TOK_LC1, TOK_LC2 = 50e9, 20e9
TOK_ANNEAL_SELECT = 4 * 50e9          # 4 candidate anneal mixes x 50B from the ~8T checkpoint
CHINCHILLA_TOK = 20 * MC["total"]
ROPE_THETA = {"pretrain_4k": 500_000, "stage_32k": 4_000_000, "stage_128k": 16_000_000}

# Planning unique counts. Public anchors: Nemotron-CC's GLOBAL fuzzy + exact dedup of all English CC 2013-2024 left
# ~4.4T original tokens across every quality bucket; FineWeb's global cross-dump dedup collapsed ~20T to ~4T. FineWeb-Edu
# and its score-2 tier are only per-dump deduped and DCLM-baseline only Bloom-filter / per-global-shard deduped, so the
# plan applies a global MinHash (5-gram, 112 hashes, 14 x 8, Jaccard ~0.8) at the UNION level, keeping the NEWEST copy
# (FineWeb's "global dedup hurt" result kept the oldest), and books the losses below BEFORE any token is counted.
# The planned losses are replaced by the W3 measurement via measured_unique.json (see below). The W3 measurement is a
# DOMAIN-STRATIFIED sample across ALL CC dumps (keep every document whose hash(registered domain) mod 20 == 0, in every dump
# of FineWeb-Edu, score-2, DCLM-baseline and Nemotron-CC HQ real), then the full 5-gram/112/14x8 MinHash on that 5 % slice.
# A per-dump sample (e.g. 4 of ~100 dumps) is structurally blind to cross-dump recrawls (a page in k dumps is caught only if
# >= 2 copies fall in the sample: P = 0.001 at k = 2, 0.049 at k = 10) and would read 5-15 % where the global pass removes
# 30-70 %; the domain-stratified sample keeps recrawls of the same page together, so the measured cross-dump and
# cross-source rates are unbiased (missing only cross-domain syndication, a few points low).
W3_SAMPLE_FRAC = 0.05
TOK_SHRINK = A["tokenizer_shrink_web"]
# (source, raw T in the source's tokenizer, planned dedup loss (global cross-dump + cross-source, keep newest),
#  tokenizer factor (ours vs the source's), licence, stable epochs or None = residual filler, stable epoch cap, note)
# Epochs are set for the 9.9T PLAN; the extension pool (EXTENSION_ROWS) carries stable tokens beyond 9.9T up to the caps.
DATA_STABLE = [
    ("FineWeb-Edu (score>=3)", 1.30, 0.30, TOK_SHRINK, "ODC-By 1.0", 2.50, 3.0, "CC HTML; anchor; global cross-dump dedup, keep newest"),
    ("DCLM-baseline (dedup vs FineWeb-Edu)", 3.80, 0.50, TOK_SHRINK, "CC-BY-4.0 (dataset card)", 2.00, 3.0, "CC HTML; global dedup (per-shard Bloom only upstream) + vs FineWeb-Edu"),
    ("Nemotron-CC HQ, real text (dedup vs pool)", 1.10, 0.50, TOK_SHRINK, "CC-BY-4.0", 2.00, 3.0, "CC HTML; already global-deduped upstream; high overlap with the two above"),
    ("Nemotron-CC HQ, synthetic rephrase/QA", 1.90, 0.47, TOK_SHRINK, "CC-BY-4.0", 1.00, 1.0, "slice whose source doc survived (loss derived from the measured real-text survival); ~9 % of stable"),
    ("FinePDFs (edu-filtered subset)", 1.00, 0.00, TOK_SHRINK, "ODC-By 1.0", 1.00, 2.0, "PDF corpus, not CC HTML; MinHash-deduped upstream"),
    ("FineWeb-Edu score-2 tier (mid web, filler)", 4.10, 0.45, TOK_SHRINK, "ODC-By 1.0", None, 1.0, "residual; first 3T of stable only; global dedup keep newest"),
    ("The Stack v2 (permissive licences, dedup)", 0.60, 0.00, 1.00, "per-file permissive + SWH terms; opt-out applied", 1.50, 3.0, "code"),
    ("FineWeb-2 (12 languages, top quality bin)", 1.50, 0.00, TOK_SHRINK, "ODC-By 1.0", 0.40, 2.0, "de fr es it pt nl pl ru ja zh ko ar"),
    ("FineMath 3+ / InfiWebMath 3+ / OpenWebMath", 0.07, 0.00, 1.00, "ODC-By 1.0", 2.00, 3.0, "math web"),
    ("peS2o v2 + arXiv (CC-BY / CC0 papers)", 0.07, 0.00, 1.00, "ODC-By 1.0 / per-paper CC-BY", 2.00, 3.0, "papers"),
    ("Wikipedia (en + 20 languages, 2026 dump)", 0.015, 0.00, 1.00, "CC-BY-SA 4.0", 2.00, 3.0, "encyclopedic"),
    ("Books, public domain (Gutenberg, Standard Ebooks)", 0.006, 0.00, 1.00, "public domain", 2.00, 3.0, "long-form"),
    ("Cosmopedia v2 (synthetic textbooks)", 0.028, 0.00, 1.00, "Apache-2.0", 1.00, 1.0, "synthetic, kept separate from real text"),
]
EPOCH_CAP_STABLE_WEB = 3.0        # data-constrained scaling (Muennighoff et al. 2023): <= 4 epochs is near-free; 3 is the plan cap
EPOCH_CAP_INCL_ANNEAL = 4.0       # any source or anneal sub-pool, stable + anneal
# Generator model and its OUTPUT terms for every synthetic / instruction source (the dataset licence alone is not enough:
# Llama 3.1 outputs carry a naming clause, OpenAI outputs a no-competing-model clause, Qwen an attribution clause).
# Status: "keep" = cleared by default; "counsel" = counsel's W3 memo must clear it, with the default substitution named.
GENERATOR_TERMS = {
    "Nemotron-CC HQ, synthetic rephrase/QA": ("Mistral-NeMo-12B-Instruct / Mixtral-8x22B-Instruct (Apache-2.0; no output restriction)", "keep"),
    "Cosmopedia v2 (synthetic textbooks)": ("Mixtral-8x7B-Instruct (Apache-2.0; no output restriction)", "keep"),
    "Nemotron-CC synthetic HQ (QA / distill / extract)": ("Mistral-NeMo-12B-Instruct / Mixtral-8x22B-Instruct (Apache-2.0)", "keep"),
    "Code HQ (Stack v2 edu-filtered, python-edu, synthetic with unit tests)": ("synthetic subset: open Apache-2.0/MIT generators only (per-file provenance)", "keep"),
    "Math HQ, anneal-only (Nemotron-CC-Math v1, OpenMathInstruct-2; CC-BY-4.0)": ("OpenMathInstruct-2: Llama-3.1-405B/70B-Instruct (Llama 3.1 Community License: a model trained on its outputs must carry 'Llama' at the start of its name); Nemotron-CC-Math v1: LLM-cleaned real CC text, generator per the dataset card", "counsel: accept a 'Llama-' prefixed release name (recorded in the model card) or drop OpenMathInstruct-2 for Nemotron-CC-Math v1 real text + open-generator math sets (DeepSeek-R1 / Qwen-generated, MIT / Apache-2.0)"),
    "Instruction-style (Nemotron-Pretraining-SFT-v1, SmolTalk, Tulu-3 SFT mix)": ("Nemotron-Pretraining-SFT-v1: open generators per the dataset card (CC-BY-4.0); SmolTalk: Qwen2.5-72B-Instruct (Qwen licence attribution clause); Tulu-3 SFT mix (ODC-By): subsets generated with GPT-4o (OpenAI terms prohibit use to develop competing models)", "counsel: drop the GPT-4o-derived Tulu-3 subsets by default and keep the rest; Qwen attribution recorded in the model card"),
}
# anneal mix: (component, share of the anneal, sub-pool unique T IN OUR TOKENIZER after global dedup, parent stable row index or -1)
DATA_ANNEAL = [
    ("FineWeb-Edu score>=4 (top bin)", 0.12, 0.15, 0),
    ("DCLM-baseline top decile (DCLM fastText probability at W12; 0.5B classifier refinement by W18)", 0.15, 0.165, 1),
    ("Nemotron-CC synthetic HQ (QA / distill / extract)", 0.13, 0.435, 3),
    ("Code HQ (Stack v2 edu-filtered, python-edu, synthetic with unit tests)", 0.16, 0.20, 6),
    ("Math HQ from the stable pool (FineMath 4+, InfiWebMath 4+, OpenWebMath)", 0.03, 0.04, 8),
    ("Math HQ, anneal-only (Nemotron-CC-Math v1, OpenMathInstruct-2; CC-BY-4.0)", 0.10, 0.15, -1),
    ("Instruction-style (Nemotron-Pretraining-SFT-v1, SmolTalk, Tulu-3 SFT mix)", 0.12, 0.08, -1),
    ("Papers + Wikipedia + PD books", 0.06, 0.091, -1),
    ("FinePDFs top bin", 0.05, 0.174, 4),
    ("Multilingual (FineWeb-2 top bin)", 0.08, 0.348, 7),
]
assert abs(sum(s for _, s, _, _ in DATA_ANNEAL) - 1.0) < 1e-9
DATA_LC = [  # share of the 32k stage (50B); the 128k stage (20B) uses the same mix with a 64k length floor
    ("Repo-level concatenated code (Stack v2)", 0.25),
    ("Papers (peS2o / arXiv full text)", 0.25),
    ("Public-domain books", 0.20),
    ("Long web / PDF documents > 8k tokens", 0.10),
    ("Short-context replay (packed anneal mix)", 0.20),
]
assert abs(sum(s for _, s in DATA_LC) - 1.0) < 1e-9


MEASURED_UNIQUE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "measured_unique.json")


def load_measured_unique() -> dict:
    """G3 input: {source name: unique T in OUR tokenizer} measured by the data pipeline. Absent before W3."""
    if os.path.exists(MEASURED_UNIQUE_FILE):
        with open(MEASURED_UNIQUE_FILE) as f:
            return json.load(f)
    return {}


def _anneal_T_per_row(rows: list) -> list[float]:
    """Anneal tokens (T) attributed to each stable row; papers + wiki + books pro rata by unique size."""
    out = [0.0] * len(rows)
    for comp, share, sub, parent in DATA_ANNEAL:
        if parent >= 0:
            out[parent] += share * TOK_ANNEAL / 1e12
    pw = next(s for c, s, _, p in DATA_ANNEAL if c.startswith("Papers")) * TOK_ANNEAL / 1e12
    pw_u = sum(rows[i]["unique_T"] for i in (9, 10, 11))
    for i in (9, 10, 11):
        out[i] += pw * rows[i]["unique_T"] / pw_u
    return out


def build_data_rows(measured: dict | None = None):
    """The plan fixes TOKENS per source (planning unique x planned epochs). A measured unique count changes only the
    epochs, unless it cannot carry the planned tokens under the caps: then the row is clipped to measured x cap
    (G3 fails for that source) and the residual filler absorbs the difference (fallback steps 1-2)."""
    measured = measured or {}
    rows = []
    for name, raw, loss, tf, lic, ep, cap, note in DATA_STABLE:
        uniq_src = raw * (1 - loss)
        uniq_plan = uniq_src * tf
        uniq = measured.get(name, uniq_plan)
        rows.append(dict(source=name, raw_T=raw, dedup_loss=loss, unique_src_T=uniq_src, tok_factor=tf, unique_plan_T=uniq_plan,
                         unique_T=uniq, licence=lic, epochs_plan=ep, cap_stable=cap, note=note, measured=name in measured))
    # planned tokens and the G3 minimum per source come from the PLAN, never from the measurement
    plan_anneal = _anneal_T_per_row(rows)
    fixed_plan = sum(r["unique_plan_T"] * r["epochs_plan"] for r in rows if r["epochs_plan"] is not None)
    for r, an in zip(rows, plan_anneal):
        r["residual"] = r["epochs_plan"] is None
        r["tokens_plan_T"] = (TOK_STABLE / 1e12 - fixed_plan) if r["residual"] else r["unique_plan_T"] * r["epochs_plan"]
        r["g3_min_unique_T"] = max(r["tokens_plan_T"] / r["cap_stable"], (r["tokens_plan_T"] + an) / EPOCH_CAP_INCL_ANNEAL)
        r["g3_fail"] = r["measured"] and r["unique_T"] < r["g3_min_unique_T"] - 1e-12
    # re-solve: fixed rows keep their planned tokens where the measured count supports them, else clip to measured x cap
    for r in rows:
        if not r["residual"]:
            r["tokens_T"] = min(r["tokens_plan_T"], r["unique_T"] * r["cap_stable"]) if r["measured"] else r["tokens_plan_T"]
            r["epochs_stable"] = r["tokens_T"] / r["unique_T"]
    fixed = sum(r["tokens_T"] for r in rows if not r["residual"])
    for r in rows:
        if r["residual"]:
            r["tokens_T"] = TOK_STABLE / 1e12 - fixed
            r["epochs_stable"] = r["tokens_T"] / r["unique_T"]
    tot = sum(r["tokens_T"] for r in rows)
    assert abs(tot - TOK_STABLE / 1e12) < 1e-9, tot
    for r, an in zip(rows, _anneal_T_per_row(rows)):
        r["mix_pct"] = 100 * r["tokens_T"] / tot
        r["anneal_T"] = an
        r["epochs_incl_anneal"] = (r["tokens_T"] + r["anneal_T"]) / r["unique_T"]
    return rows


MEASURED_UNIQUE = load_measured_unique()
DATA_ROWS = build_data_rows(MEASURED_UNIQUE)
G3_FAILED = [r["source"] for r in DATA_ROWS if r["g3_fail"]]
for _r in DATA_ROWS:   # hard caps: if even the re-solved mix breaks one, fallback steps 3-4 need a human (exit 1)
    assert _r["epochs_stable"] <= _r["cap_stable"] + 1e-9, (_r["source"], _r["epochs_stable"], "cap broken even after re-solve: engage fallback 3-4")
    assert _r["epochs_incl_anneal"] <= EPOCH_CAP_INCL_ANNEAL + 1e-9, (_r["source"], _r["epochs_incl_anneal"])
    assert _r["residual"] or _r["cap_stable"] <= EPOCH_CAP_STABLE_WEB
    assert _r["tokens_T"] >= 0, (_r["source"], "fixed rows exceed the stable budget; lower an epoch count")
UNIQUE_AVAILABLE_T = sum(r["unique_T"] for r in DATA_ROWS)
UNIQUE_AVAILABLE_SRC_T = sum(r["unique_src_T"] for r in DATA_ROWS)
UNIQUE_TOUCHED_T = sum(min(r["unique_T"], r["tokens_T"]) for r in DATA_ROWS)
AVG_EPOCHS = (TOK_STABLE / 1e12) / UNIQUE_TOUCHED_T
WEB_ROWS = (0, 1, 2, 3)
HQ_WEB_ROWS = (0, 1, 2)
WEB_USED_T = sum(DATA_ROWS[i]["tokens_T"] for i in WEB_ROWS)
WEB_UNIQUE_T = sum(DATA_ROWS[i]["unique_T"] for i in WEB_ROWS)
CC_UNIQUE_SRC_T = sum(DATA_ROWS[i]["unique_src_T"] for i in (0, 1, 2, 5))   # CC-derived real text incl. the score-2 tier
MAX_EPOCHS_STABLE = max(r["epochs_stable"] for r in DATA_ROWS)
MAX_EPOCHS_INCL_ANNEAL = max(r["epochs_incl_anneal"] for r in DATA_ROWS)
# capacity: stable tokens available if every source ran to its cap (quality-neutral upper bound) and if only the HQ rows
# (web HQ, PDFs, code, math, papers, wiki, books) ran to their caps with synthetic / filler / multilingual held at plan
CAP_ALL_T = sum(r["unique_T"] * r["cap_stable"] for r in DATA_ROWS)
HQ_ROWS = (0, 1, 2, 4, 6, 8, 9, 10, 11)
CAP_HQ_T = sum(r["unique_T"] * r["cap_stable"] if i in HQ_ROWS else r["tokens_T"] for i, r in enumerate(DATA_ROWS))
SHRINK_SENS = 0.25     # G3 sensitivity: every unique count lands this fraction below plan
CAP_HQ_SHRUNK_T = sum(r["unique_T"] * (1 - SHRINK_SENS) * r["cap_stable"] if i in HQ_ROWS else r["tokens_T"] for i, r in enumerate(DATA_ROWS))
SCORE2_FALLBACK_T = DATA_ROWS[5]["unique_T"] * 1.0 - DATA_ROWS[5]["tokens_T"]   # score-2 tier taken to 1.0 epoch
CC_RAW_SRC_T = sum(DATA_ROWS[i]["raw_T"] for i in (0, 1, 2, 5))               # the same four rows counted per dump (raw), source tok
# Extension pool: stable tokens beyond the 9.9T plan (MFU above 0.38, via the date-driven anneal rule) are drawn from the HQ
# web rows in their stable proportions up to their stable caps (synthetic, Cosmopedia, filler and multilingual stay at their
# planned token counts; the dataloader's mixture weights switch at 9.9T). If the G2b epoch-proxy ablation favours unique
# tokens, the pool becomes score-2 to 1.0 epoch + Nemotron-CC medium-high buckets instead.
EXTENSION_ROWS = HQ_WEB_ROWS
EXTENSION_CAPACITY_T = sum(DATA_ROWS[i]["unique_T"] * DATA_ROWS[i]["cap_stable"] - DATA_ROWS[i]["tokens_T"] for i in EXTENSION_ROWS)
# Epoch-proxy decision rule (G2b): if arm B (unique) beats arm A (repeated HQ) by more than the 2-seed noise floor, FineWeb-Edu
# and DCLM are capped at this many epochs INCL. anneal and the score-2 tier rises to 1.0 epoch in the frozen mix.
EPOCH_PROXY_CAP_INCL_ANNEAL = 2.0
ANNEAL_ROWS = []
for comp, share, sub, parent in DATA_ANNEAL:
    tok_B = share * TOK_ANNEAL / 1e9
    stable_ep = DATA_ROWS[parent]["epochs_stable"] if parent >= 0 else 0.0
    ANNEAL_ROWS.append(dict(component=comp, share=share, tokens_B=tok_B, subpool_unique_T=sub,
                            epochs_subpool_incl_stable=stable_ep + tok_B / 1e3 / sub,
                            parent=DATA_ROWS[parent]["source"] if parent >= 0 else "anneal-only"))
MAX_EPOCHS_SUBPOOL = max(r["epochs_subpool_incl_stable"] for r in ANNEAL_ROWS)
assert MAX_EPOCHS_SUBPOOL <= EPOCH_CAP_INCL_ANNEAL, MAX_EPOCHS_SUBPOOL
TOKENIZED_TOKENS = TOK_PRETRAIN + TOK_LC1 + TOK_LC2 + TOK_ANNEAL_SELECT
TOKENIZED_TB = TOKENIZED_TOKENS * 4 / 1e12            # uint32: vocab 131072 > 65535


def chinchilla_loss(N: float, D: float) -> float:   # marginal-value proxy only (Hoffmann et al. constants)
    return 1.69 + 406.4 / (N ** 0.34) + 410.7 / (D ** 0.28)


# =====================================================================================
# 3. RECIPE NUMBERS
# =====================================================================================
N_GPUS, N_NODES, HOT_SPARE_NODES = 512, 64, 2
BLOCK2_GPUS = N_GPUS + 8 * HOT_SPARE_NODES
MICRO_BATCH, GRAD_ACCUM = 2, 2
GLOBAL_BATCH_TOK = N_GPUS * MICRO_BATCH * GRAD_ACCUM * SEQ_PRETRAIN      # 8,388,608 (default; 4,194,304 = grad-accum 1 is the fallback)
BATCH_FALLBACK_TOK = N_GPUS * MICRO_BATCH * 1 * SEQ_PRETRAIN             # 4M: used only if the 1B batch ablation shows > 0.5 % post-decay penalty
# Batch ramp, LINEAR IN STEPS (the trainer convention), in two phases. Phase 1 (grad-accum 1): the per-rank packed varlen
# window grows from 4,096 tokens (= micro-batch 1) to 8,192 (= micro-batch 2) in 256-token increments over the first 100B
# tokens: 2,097,152 -> 4,194,304. Phase 2 (grad-accum 2 from 100B): two micro-steps per step, each window again growing
# 4,096 -> 8,192 over the next 400B tokens: 4,194,304 -> 8,388,608 by 500B. Documents stay cut at 4,096 so max_seqlen for
# FA3 varlen never changes; no rank idles; the smallest GEMM has M = 4,096. cu_seqlens is padded to a fixed 1,024 entries
# and the token dimension is marked dynamic, so only the 17 window sizes recompile (never a new document count).
RAMP_WINDOW_START, RAMP_WINDOW_END, RAMP_WINDOW_STEP = SEQ_PRETRAIN, MICRO_BATCH * SEQ_PRETRAIN, 256
CU_SEQLENS_PAD = 1024
BATCH_RAMP_START = N_GPUS * RAMP_WINDOW_START                                            # 2,097,152
BATCH_RAMP_MID = N_GPUS * RAMP_WINDOW_END                                                # 4,194,304 (end of phase 1)
BATCH_RAMP1_TOKENS, BATCH_RAMP2_TOKENS = 100e9, 400e9
BATCH_RAMP_TOKENS = BATCH_RAMP1_TOKENS + BATCH_RAMP2_TOKENS                              # 8M reached by 500B
RAMP_PLATEAUS = (RAMP_WINDOW_END - RAMP_WINDOW_START) // RAMP_WINDOW_STEP + 1          # 17 window sizes per phase
WARMUP_TOKENS = 8e9                                                                       # linear from 0, inside phase 1
PEAK_LR, MIN_LR_FRAC = 3.0e-4, 0.01
MIN_LR = PEAK_LR * MIN_LR_FRAC
LC_LR = 3.0e-5
STEPS_RAMP1 = BATCH_RAMP1_TOKENS / ((BATCH_RAMP_START + BATCH_RAMP_MID) / 2)            # mean batch over a linear-in-steps ramp
STEPS_RAMP2 = BATCH_RAMP2_TOKENS / ((BATCH_RAMP_MID + GLOBAL_BATCH_TOK) / 2)
STEPS_RAMP = STEPS_RAMP1 + STEPS_RAMP2
STEPS_PER_PLATEAU1, STEPS_PER_PLATEAU2 = STEPS_RAMP1 / RAMP_PLATEAUS, STEPS_RAMP2 / RAMP_PLATEAUS
STEPS_STABLE = STEPS_RAMP + (TOK_STABLE - BATCH_RAMP_TOKENS) / GLOBAL_BATCH_TOK
STEPS_ANNEAL = TOK_ANNEAL / GLOBAL_BATCH_TOK
STEPS_TOTAL = STEPS_STABLE + STEPS_ANNEAL
# warmup happens inside phase 1, same linear-in-steps convention: tokens(s) = b0 s + (b1 - b0) s^2 / (2 R); solve for 8B
_qa, _qb = (BATCH_RAMP_MID - BATCH_RAMP_START) / (2 * STEPS_RAMP1), BATCH_RAMP_START
WARMUP_STEPS = (-_qb + math.sqrt(_qb * _qb + 4 * _qa * WARMUP_TOKENS)) / (2 * _qa)
assert WARMUP_TOKENS < BATCH_RAMP1_TOKENS
# long-context stages: CP=8 inside the node -> 64 CP groups; batch = groups x micro-batch x seq
CP_LC = 8
LC_GROUPS = N_GPUS // CP_LC
MB_LC1, MB_LC2 = 2, 1
BATCH_LC1 = LC_GROUPS * MB_LC1 * SEQ_LC1          # 4,194,304 at 32k
BATCH_LC2 = LC_GROUPS * MB_LC2 * SEQ_LC2          # 8,388,608 at 128k
LC_WARMUP_TOKENS = 1e9
STEPS_LC1 = TOK_LC1 / BATCH_LC1
STEPS_LC2 = TOK_LC2 / BATCH_LC2
FPT_4K = MODEL.flops_per_token(SEQ_PRETRAIN)
TOK_PER_S_CLUSTER = N_GPUS * PEAK * A["mfu_main"] / FPT_4K
TOK_PER_S_GPU = TOK_PER_S_CLUSTER / N_GPUS
STEP_TIME_S = GLOBAL_BATCH_TOK / TOK_PER_S_CLUSTER
CKPT_EVERY_STEPS = A["ckpt_interval_min"] * 60 / STEP_TIME_S


def tok_s_per_gpu(mfu: float, seq: int = SEQ_PRETRAIN) -> float:
    """Basis-free throughput gate: tokens/s per GPU at the given MFU (DR basis: 6ND + causal attention at this seq)."""
    return PEAK * mfu / MODEL.flops_per_token(seq)


# Every throughput gate is stated in tokens/s/GPU (torchtitan's own MFU counts non-causal attention and reads 6.4 % high on
# the DR basis, 13.7 % high on 6ND; a torchtitan-reported 0.40 is 0.376 here). Gate values are rounded to the nearest 100.
MFU_GATE_64 = 0.40                                                 # G2 / G3b on 64 GPUs
TOKS_GATE_64 = round(tok_s_per_gpu(MFU_GATE_64) / 100) * 100       # 6,300 tok/s/GPU at 4,096 (= 0.400)
TOKS_GATE_512 = round(tok_s_per_gpu(A["mfu_main"]) / 100) * 100    # 6,000 tok/s/GPU at acceptance (G4) and rolling (G5) (= 0.381, the planning value)
TOKS_GATE_32K = round(tok_s_per_gpu(A["mfu_longctx_32k"], SEQ_LC1) / 100) * 100     # 3,800 at 32k (= 0.35)
TOKS_GATE_128K = round(tok_s_per_gpu(A["mfu_longctx_128k"], SEQ_LC2) / 100) * 100   # 1,300 at 128k (= 0.25)
MFU_OF = lambda toks, seq=SEQ_PRETRAIN: toks * MODEL.flops_per_token(seq) / PEAK        # tokens/s/GPU -> MFU on the DR basis
TORCHTITAN_MFU_RATIO = (6 * MC["total"] + 12 * MODEL.n_layers * SEQ_PRETRAIN * MODEL.d_model) / FPT_4K   # non-causal attention count / DR basis
SHAKEDOWN_H = 2.0
SHAKEDOWN_TOKENS = TOK_PER_S_CLUSTER * SHAKEDOWN_H * 3600          # the G4 shakedown: 2 h of the real job at plan throughput
VAL_EVERY_STEPS = 1000
VAL_TOKENS_INLOOP = 6 * 10e6                     # 6 domains x 10M held-out tokens, forward only
VAL_FRAC_INLOOP = (VAL_TOKENS_INLOOP / 3 / GLOBAL_BATCH_TOK) / VAL_EVERY_STEPS
PER_SOURCE_VAL_EVERY_TOK = 10e9
PER_SOURCE_VAL_TOKENS = len(DATA_STABLE) * 10e6
VAL_FRAC_PER_SOURCE = (PER_SOURCE_VAL_TOKENS / 3 / GLOBAL_BATCH_TOK) / (PER_SOURCE_VAL_EVERY_TOK / GLOBAL_BATCH_TOK)
VAL_FRAC_TOTAL = VAL_FRAC_INLOOP + VAL_FRAC_PER_SOURCE

# =====================================================================================
# 4. COMPUTE PLAN
# =====================================================================================
@dataclass
class Work:
    name: str
    tokens: float
    seq: int
    mfu: float
    overhead: float
    gpus: int
    block: str
    shape: Shape | None = None
    flop_mult: float = 1.0
    flops: float = 0.0
    gpu_hr_ideal: float = 0.0
    gpu_hr: float = 0.0
    days: float = 0.0
    note: str = ""

    def compute(self):
        if self.shape is not None and self.tokens:
            self.flops = self.shape.flops_per_token(self.seq) * self.tokens * self.flop_mult
            self.gpu_hr_ideal = self.flops / gpu_hr_flop(self.mfu)
            self.gpu_hr = self.gpu_hr_ideal * self.overhead
        self.days = self.gpu_hr / self.gpus / 24
        return self

    @property
    def usd(self) -> float:
        return self.gpu_hr * (OD if self.block == "OD" else RES)


def wall(name, gpu_hr, gpus, block, note=""):
    w = Work(name, 0, 0, 0.0, 1.0, gpus, block, note=note)
    w.gpu_hr_ideal = w.gpu_hr = gpu_hr
    return w.compute()


W = {}
W["stable"] = Work("Main run: stable phase", TOK_STABLE, SEQ_PRETRAIN, A["mfu_main"], A["overhead_main"], N_GPUS, "B2", MODEL).compute()
W["anneal"] = Work("Main run: anneal/decay phase", TOK_ANNEAL, SEQ_PRETRAIN, A["mfu_main"], A["overhead_main"], N_GPUS, "B2", MODEL).compute()
W["anneal_select"] = Work("Anneal-mix selection: 4 candidates x 50B from the ~8T ckpt (4 parallel 128-GPU jobs)", TOK_ANNEAL_SELECT, SEQ_PRETRAIN, A["mfu_main"], A["overhead_main"], N_GPUS, "B2", MODEL).compute()
W["lc32k"] = Work("Long-context stage 1: 50B at 32k, CP=8, SAC(op), mb 2, theta 4M", TOK_LC1, SEQ_LC1, A["mfu_longctx_32k"], A["overhead_small"], N_GPUS, "B2", MODEL).compute()
W["lc128k"] = Work("Long-context stage 2: 20B at 128k, CP=8, full AC, mb 1, theta 16M", TOK_LC2, SEQ_LC2, A["mfu_longctx_128k"], A["overhead_small"], N_GPUS, "B2", MODEL).compute()
ACCEPT_DAYS = 4.0
W["accept"] = wall(f"Block 2 acceptance + burn-in ({ACCEPT_DAYS:.0f} d x {BLOCK2_GPUS} GPUs)", ACCEPT_DAYS * 24 * BLOCK2_GPUS, BLOCK2_GPUS, "B2")
N_CKPT_EVALS = int(TOK_PRETRAIN / 100e9)
W["evals_inrun"] = wall(f"In-run downstream evals: {N_CKPT_EVALS} ckpts x 3 GPU-h on spare node 1", N_CKPT_EVALS * 3, 8, "B2")

ladder_rows = []
for name, shp, toks, nlr, nseed, mfu, bsz in LADDER:
    c = shp.counts()
    w = Work(f"Ladder {name}: {nlr} LR x {nseed} seed x {toks/1e9:.0f}B at batch {bsz/MIB:.1f}M", toks * nlr * nseed, SEQ_PRETRAIN, mfu, A["overhead_small"], 64, "B1", shp).compute()
    w.note = f"d{shp.d_model} L{shp.n_layers} h{shp.n_heads}/{shp.n_kv_heads} ffn{shp.ffn_hidden}; N_total {c['total']/1e9:.3f}B, N_nonembed {c['nonembed']/1e9:.3f}B, {toks/c['nonembed']:.0f} tok/nonembed-param"
    ladder_rows.append((name, shp, c, toks, nlr, nseed, bsz, w))
    W[f"ladder_{name}"] = w
ladder_dur_rows = []
for name, shp, toks, nlr, mfu, bsz, note in LADDER_DURATION:
    c = shp.counts()
    w = Work(f"Ladder duration axis {name}: {nlr} LR x {toks/1e9:.0f}B at batch {bsz/MIB:.0f}M", toks * nlr, SEQ_PRETRAIN, mfu, A["overhead_small"], 64, "B1", shp).compute()
    w.note = note
    ladder_dur_rows.append((name, shp, c, toks, nlr, bsz, w))
    W[f"ladder_dur_{name.split()[0]}"] = w
LADDER_DUR_GPU_HR = sum(w.gpu_hr for *_, w in ladder_dur_rows)
W["fp8"] = Work("FP8 pilot: 3B x 90B (torchao float8 rowwise vs bf16 twin)", 90e9, SEQ_PRETRAIN, 0.38, A["overhead_small"], 64, "B1", SHP_3B).compute()
W["abl1b"] = Work("Ablations: 20 x 1B @ 30B on v0 (mix, code 8 vs 15 %, math 1.3 vs 4 %, dedup threshold 0.7/0.8/0.9 on the W5-6 10-dump corpora, doc-mask, decay shape, batch 2M vs 4M (= the 4M vs 8M decision at 10B), WD, tokenizer, z-loss)", 20 * 30e9, SEQ_PRETRAIN, 0.32, A["overhead_small"], 64, "B1", SHP_1B).compute()
EPOCH_PROXY_ARMS, EPOCH_PROXY_TOKENS = 2, 300e9
W["abl_epoch"] = Work("Epoch-proxy ablation: 2 x 1B @ 300B on v0 (arm A: 100B unique HQ x 3 epochs; arm B: 300B unique HQ + score-2 / Nemotron-CC medium-high x 1 epoch; same WSD; ranked on post-decay loss + the 8-task aggregate)", EPOCH_PROXY_ARMS * EPOCH_PROXY_TOKENS, SEQ_PRETRAIN, 0.32, A["overhead_small"], 64, "B1", SHP_1B).compute()
W["abl3b"] = Work("Ablation confirmations: 3 x 3B @ 60B on v0", 3 * 60e9, SEQ_PRETRAIN, 0.38, A["overhead_small"], 64, "B1", SHP_3B).compute()
W["rehearsal"] = Work("Full-recipe rehearsal: 3B x 300B on the frozen mix (WSD + 1-sqrt anneal + mini 32k + DCP resume)", 300e9, SEQ_PRETRAIN, 0.38, A["overhead_small"], 64, "B1", SHP_3B).compute()
MEGATRON_COMPARE_H = 4
W["dress"] = wall(f"10B dress rehearsal on 64 GPUs (4 h x 64) + Megatron-Core/TE comparison of the same config ({MEGATRON_COMPARE_H} h x 64, at G2) + node-kill/restore drill", 4 * 64 + MEGATRON_COMPARE_H * 64, 64, "B1")
CLASSIFIER_POOL_T = 5e12                            # anneal candidate pools: DCLM-baseline, FinePDFs, Stack v2, FineWeb-2 top bins (<= 5T); NOT on the freeze path
_cls_flops = 2 * 0.5e9 * CLASSIFIER_POOL_T          # 0.5B classifier inference (trained on the public FineWeb-Edu Llama-3-70B annotations + DCLM OH-2.5/ELI5 positives)
W["data_gpu"] = wall(f"GPU data jobs: 0.5B quality classifier over the anneal candidate pools (<= {CLASSIFIER_POOL_T/1e12:.0f}T; 2ND inference, MFU 0.30, x1.5; W13 d4-W14 on Block 1, dev-node overflow, due W18) + 600 GPU-h NeMo Curator semantic dedup",
                     _cls_flops / gpu_hr_flop(0.30) * 1.5 + 600, 64, "B1")
W["sft"] = Work("SFT: 1.5M ex x 1.5k tok x 3 ep + 5 ablations x 1 ep (TRL, 8k packed)", 1.5e6 * 1500 * 8, SEQ_POST, A["mfu_post"], A["overhead_post"], 32, "B3", MODEL).compute()
W["rm"] = Work("Reward model: 300k pairs x 2 ep (10B init)", 300e3 * 2 * 2 * 1200, SEQ_POST, A["mfu_post"], A["overhead_post"], 32, "B3", MODEL).compute()
W["dpo"] = Work("DPO: 300k pairs x 2 ep x 3 rounds (policy fwd+bwd + ref fwd = 8ND)", 300e3 * 2 * 2 * 1200 * 3, SEQ_POST, A["mfu_post"], A["overhead_post"], 32, "B3", MODEL, flop_mult=8 / 6).compute()
RL_RUNS, RL_STEPS, RL_PROMPTS, RL_SAMPLES, RL_RESP, RL_PROMPT_LEN = 5, 300, 512, 8, 1024, 512
RL_GEN_TOK = RL_RUNS * RL_STEPS * RL_PROMPTS * RL_SAMPLES * RL_RESP
RL_TRAIN_TOK = RL_RUNS * RL_STEPS * RL_PROMPTS * RL_SAMPLES * (RL_RESP + RL_PROMPT_LEN)
RL_GEN_GPU_HR = RL_GEN_TOK / A["rl_gen_tok_s_per_gpu"] / 3600
_rl = Work("rl", RL_TRAIN_TOK, SEQ_POST, A["mfu_rl_train"], 1.0, 48, "B3", MODEL, flop_mult=(8 / 6) + (2 / 6)).compute()
RL_TRAIN_GPU_HR = _rl.gpu_hr_ideal
RL_FLOP_GPU_HR = (RL_TRAIN_GPU_HR + RL_GEN_GPU_HR) * A["overhead_rl"]
RL_WALL_DAYS = 21
W["rl"] = wall(f"Online RL (GRPO, verl): 5 campaigns x 300 steps; wall-clock budget 48 GPUs x {RL_WALL_DAYS} d", 48 * 24 * RL_WALL_DAYS, 48, "B3",
               note=f"FLOP-based need {RL_FLOP_GPU_HR:,.0f} GPU-h (gen {RL_GEN_TOK/1e9:.2f}B tok = {RL_GEN_GPU_HR:,.0f} GPU-h + train {RL_TRAIN_GPU_HR:,.0f} GPU-h ideal, x{A['overhead_rl']:.0f})")
W["judge"] = wall("Local 70B-class open-weight judge: label 280k on-policy preference pairs + eval judging", 2000, 16, "B3")
W["evals_post"] = wall("Post-training + final evals: 50 x 8 GPU-h + 1,500 GPU-h final suite/safety/long-ctx", 50 * 8 + 1500, 16, "B3")
SERVING_GPUS, SERVE_WK_B3, SERVE_WK_OD = 8, 2, 10
W["serve_b3"] = wall(f"Serving pilot in Block 3 (W29-30): {SERVING_GPUS} GPUs x {SERVE_WK_B3} wk", SERVING_GPUS * SERVE_WK_B3 * HRS_WK, SERVING_GPUS, "B3")
W["serve_od"] = wall(f"Serving pilot on-demand (W31-40): {SERVING_GPUS} GPUs x {SERVE_WK_OD} wk", SERVING_GPUS * SERVE_WK_OD * HRS_WK, SERVING_GPUS, "OD")
W["dev"] = wall("Dev/debug node: 8 GPUs x 40 wk standing (smoke tests, repro, CI)", 8 * 40 * HRS_WK, 8, "DEV")

MAIN_RUN_GPU_HR = W["stable"].gpu_hr + W["anneal"].gpu_hr
MAIN_RUN_IDEAL = W["stable"].gpu_hr_ideal + W["anneal"].gpu_hr_ideal
MAIN_RUN_DAYS = MAIN_RUN_GPU_HR / N_GPUS / 24
MAIN_FLOPS = W["stable"].flops + W["anneal"].flops
MAIN_6ND = 6 * MC["total"] * TOK_PRETRAIN
GPU_HR_PER_T = W["stable"].gpu_hr / (TOK_STABLE / 1e12)
USD_PER_T = GPU_HR_PER_T * RES

# --- reserved blocks (cash)
BLOCKS = [  # key, name, gpus, weeks, price, week range
    ("DEV", "Dev node (W1-40): standing 8-GPU allocation", 8, 40, RES, "W1-W40"),
    ("B1", "Block 1 (W7-14): ladder, FP8 pilot, ablations, rehearsal, data GPU jobs", 64, 8, RES, "W7-W14"),
    ("B2", f"Block 2 (W15-22): main run, {N_GPUS} compute + {8*HOT_SPARE_NODES} hot-spare GPUs", BLOCK2_GPUS, 8, RES, "W15-W22"),
    ("B3", "Block 3 (W23-30): SFT, RM, DPO, GRPO, judge, evals, serving pilot start", 48, 8, RES, "W23-W30"),
    ("OD", "Serving pilot on-demand (W31-40)", 8, 10, OD, "W31-W40"),
]
block_rows = []
for key, name, g, wk, price, rng in BLOCKS:
    hrs = g * wk * HRS_WK
    used = sum(w.gpu_hr for w in W.values() if w.block == key)
    block_rows.append(dict(key=key, name=name, gpus=g, weeks=wk, gpu_hr=hrs, price=price, usd=hrs * price, used=used, util=used / hrs, range=rng))
COMPUTE_USD = sum(b["usd"] for b in block_rows)
RESERVED_GPU_HR = sum(b["gpu_hr"] for b in block_rows if b["price"] == RES)
TOTAL_GPU_HR_BOUGHT = sum(b["gpu_hr"] for b in block_rows)
USED_GPU_HR = sum(w.gpu_hr for w in W.values())
UTIL_OVERALL = USED_GPU_HR / TOTAL_GPU_HR_BOUGHT
B2 = next(b for b in block_rows if b["key"] == "B2")
assert B2["util"] <= 1.0, B2["util"]
for b in block_rows:
    assert b["util"] <= 1.0, (b["key"], b["util"])

# --- Block 2 fit and the single anneal-start rule
BLOCK2_DAYS = B2["weeks"] * 7
TAIL_DAYS = W["anneal"].days + W["lc32k"].days + W["lc128k"].days
ANNEAL_START_DAY = BLOCK2_DAYS - TAIL_DAYS                    # date-driven: anneal starts here regardless of tokens
STABLE_WINDOW_DAYS = ANNEAL_START_DAY - ACCEPT_DAYS - W["anneal_select"].days
STABLE_NEED_DAYS = W["stable"].days
BLOCK2_SLACK_DAYS = STABLE_WINDOW_DAYS - STABLE_NEED_DAYS
assert BLOCK2_SLACK_DAYS >= 0, BLOCK2_SLACK_DAYS
TOK_PER_STABLE_DAY = TOK_STABLE / STABLE_NEED_DAYS
SLACK_TOKENS = BLOCK2_SLACK_DAYS * TOK_PER_STABLE_DAY
STABLE_EXPECTED_T = (TOK_STABLE + SLACK_TOKENS) / 1e12
LC_DAYS = W["lc32k"].days + W["lc128k"].days                  # independent of mfu_main (their own MFU assumptions)
TOK_AT_MAIN_MFU = TOK_ANNEAL + TOK_ANNEAL_SELECT               # tokens trained at mfu_main outside the stable phase


def stable_tokens_at(mfu: float, block_days: float = BLOCK2_DAYS) -> float:
    """Stable tokens the date-driven anneal rule delivers at an effective MFU over the whole block (the anneal, the selection
    pause and the stable phase all speed up or slow down together; the long-context stages do not)."""
    rate = TOK_PER_STABLE_DAY * mfu / A["mfu_main"]            # tokens per day at this MFU
    return (block_days - ACCEPT_DAYS - LC_DAYS) * rate - TOK_AT_MAIN_MFU


assert abs(stable_tokens_at(A["mfu_main"]) / 1e12 - STABLE_EXPECTED_T) < 1e-9
MFU_UPSIDE = 0.42                                              # the former planning value, now the upside case
STABLE_T_AT_UPSIDE = stable_tokens_at(MFU_UPSIDE) / 1e12
MFU_TOKENS_PER_POINT_T = (stable_tokens_at(A["mfu_main"] + 0.01) - stable_tokens_at(A["mfu_main"])) / 1e12   # stable T per MFU point
MFU_FOR_DESIGN = A["mfu_main"] * (TOK_DESIGN - TOK_ANNEAL + TOK_AT_MAIN_MFU) / ((BLOCK2_DAYS - ACCEPT_DAYS - LC_DAYS) * TOK_PER_STABLE_DAY)   # MFU at which 12.0T lands
assert abs(stable_tokens_at(MFU_FOR_DESIGN) - (TOK_DESIGN - TOK_ANNEAL)) < 1
MFU_OPTION1_TRIGGER = A["mfu_main"] * (TOK_STABLE + TOK_AT_MAIN_MFU) / ((BLOCK2_DAYS - ACCEPT_DAYS - LC_DAYS) * TOK_PER_STABLE_DAY)   # below it the 9.9T plan is missed
assert abs(stable_tokens_at(MFU_OPTION1_TRIGGER) - TOK_STABLE) < 1
MFU_LOW = 0.36                                                 # the low case shown in the fit table (2 points under plan)
STABLE_T_AT_LOW = stable_tokens_at(MFU_LOW) / 1e12
STABLE_SHORTFALL_DAYS_AT_LOW = (TOK_STABLE / 1e12 - STABLE_T_AT_LOW) * 1e12 / (TOK_PER_STABLE_DAY * MFU_LOW / A["mfu_main"])
OPTION_WEEK_USD = BLOCK2_GPUS * HRS_WK * RES                  # option 1: +1 week at 2.20, exercisable by block day 21 (~3.8T)
OPTION2_PRICE = 2.40
OPTION2_WEEK_USD = BLOCK2_GPUS * HRS_WK * OPTION2_PRICE       # option 2: +1 week at <= 2.40, exercisable by block day 42
OPTION_WEEK_TOKENS_T = 7 * TOK_PER_STABLE_DAY / 1e12          # stable tokens one extra week buys at plan MFU
ANNEAL_FLOOR_T = A["anneal_token_floor"] / 1e12
# the floor binds only if the effective MFU over the block falls below this (or an equivalent number of stable days is lost)
MFU_AT_FLOOR = A["mfu_main"] * (ANNEAL_FLOOR_T * 1e12 + TOK_AT_MAIN_MFU) / ((BLOCK2_DAYS - ACCEPT_DAYS - LC_DAYS) * TOK_PER_STABLE_DAY)
assert abs(stable_tokens_at(MFU_AT_FLOOR) / 1e12 - ANNEAL_FLOOR_T) < 1e-9
DAYS_LOST_AT_FLOOR = (STABLE_EXPECTED_T - ANNEAL_FLOOR_T) * 1e12 / TOK_PER_STABLE_DAY
assert STABLE_T_AT_LOW >= ANNEAL_FLOOR_T, "MFU 0.36 must not breach the anneal token floor without an option"
assert MFU_OPTION1_TRIGGER < A["mfu_main"] < MFU_FOR_DESIGN <= MFU_GATE_64 + 0.01, (MFU_OPTION1_TRIGGER, MFU_FOR_DESIGN)
# the extension pool must carry the upside case within the stable caps
EXTENSION_NEEDED_T = STABLE_T_AT_UPSIDE - TOK_STABLE / 1e12
assert EXTENSION_CAPACITY_T >= EXTENSION_NEEDED_T, (EXTENSION_CAPACITY_T, EXTENSION_NEEDED_T)

def _ext_room(i: int) -> float:
    return DATA_ROWS[i]["unique_T"] * DATA_ROWS[i]["cap_stable"] - DATA_ROWS[i]["tokens_T"]


# extension tokens are drawn in proportion to each row's remaining room below its stable cap (so no row crosses its cap)
EXT_TOKENS_AT_UPSIDE = {DATA_ROWS[i]["source"]: EXTENSION_NEEDED_T * _ext_room(i) / EXTENSION_CAPACITY_T for i in EXTENSION_ROWS}
EXT_EPOCHS_AT_UPSIDE = {}
for i in EXTENSION_ROWS:
    r = DATA_ROWS[i]
    ext = EXT_TOKENS_AT_UPSIDE[r["source"]]
    ep_stable = (r["tokens_T"] + ext) / r["unique_T"]
    ep_incl = (r["tokens_T"] + ext + r["anneal_T"]) / r["unique_T"]
    assert ep_stable <= r["cap_stable"] + 1e-9 and ep_incl <= EPOCH_CAP_INCL_ANNEAL, (r["source"], ep_stable, ep_incl)
    EXT_EPOCHS_AT_UPSIDE[r["source"]] = (round(ep_stable, 2), round(ep_incl, 2))
BLOCK2_IDLE_DAY_USD = BLOCK2_GPUS * 24 * RES
BLOCK2_NEED_DAYS = ACCEPT_DAYS + STABLE_NEED_DAYS + W["anneal_select"].days + TAIL_DAYS
TOK_AT_DAY = {t: ACCEPT_DAYS + t / TOK_PER_STABLE_DAY for t in (1e12, 4e12, 8e12)}   # block day at which stable reaches t (before the select pause)
TOK_AT_DAY[8e12 + 1] = TOK_AT_DAY[8e12] + W["anneal_select"].days                       # resume after anneal select
OPTION1_DEADLINE_DAY = 21
TOK_AT_OPTION1_DEADLINE_T = (OPTION1_DEADLINE_DAY - ACCEPT_DAYS) * TOK_PER_STABLE_DAY / 1e12   # stable tokens reached when option 1 expires
assert TOK_AT_DAY[4e12] <= OPTION1_DEADLINE_DAY + 1.0, "the 4T gate (G5b) must fall on the same calendar day as the option-1 deadline or earlier"


def week_day(block_day: float) -> str:
    d = int(math.floor(block_day))
    return f"W{A['block2_start_week'] + d // 7} d{d % 7 + 1}"


# --- overhead build-up (fractions of ideal main-run time)
INTERRUPTS = A["interrupts_per_day_per_512"] * (BLOCK2_NEED_DAYS - ACCEPT_DAYS)
LOST_PER_INTERRUPT_MIN = A["ckpt_interval_min"] / 2 + A["restart_min"]
INTERRUPT_FRAC = INTERRUPTS * LOST_PER_INTERRUPT_MIN / 60 / (MAIN_RUN_DAYS * 24)
OVERHEAD_BREAKDOWN = [
    (f"hardware interruptions: {INTERRUPTS:.1f} events x ({A['ckpt_interval_min']/2:.0f} min lost + {A['restart_min']} min restart)", INTERRUPT_FRAC),
    ("async checkpoint stalls (0.11 s NVMe write + DCP metadata, every 30 min)", 0.005),
    (f"in-loop validation ({VAL_FRAC_INLOOP:.2%} every {VAL_EVERY_STEPS} steps + per-source {VAL_FRAC_PER_SOURCE:.2%} every 10B tokens)", 0.010),
    ("dataloader, logging, optimizer step", 0.010),
    ("stragglers, slow nodes, IB congestion", 0.030),
    ("loss-spike rollbacks (2 x 6 h budgeted)", 0.010),
    ("torch.compile warmup after each restart (~5 min x ~25)", 0.002),
    ("unplanned debugging, MFU dips, config iterations", 0.100),
]
OVERHEAD_SUM = sum(f for _, f in OVERHEAD_BREAKDOWN)
assert abs(round(1 + OVERHEAD_SUM, 2) - A["overhead_main"]) < 1e-9, OVERHEAD_SUM
assert VAL_FRAC_TOTAL <= 0.010 + 1e-9, VAL_FRAC_TOTAL

# =====================================================================================
# 5. MEMORY, COMMUNICATION, CHECKPOINTS
# =====================================================================================
SHARD = 8
REPLICATE = N_GPUS // SHARD
P = MC["total"]
s, d, kv, H, F = SEQ_PRETRAIN, MODEL.d_model, MODEL.kv_dim, MODEL.n_heads, MODEL.ffn_hidden
ACT_LAYER_B = (s * d * 2 + s * d * 2 + 2 * s * kv * 2 + s * d * 2 + s * H * 4 + s * d * 2 + 2 * s * F * 2)  # x, q, k+v, sdpa-out, lse, resid2, gate+up
ACT_LAYER_NO_SAC_B = ACT_LAYER_B + 2 * s * d * 2 + s * F * 2    # + 2 norm outputs + silu*up product
CE_CHUNK = 2048
MEM = [
    ("fp32 sharded params (FSDP2 master DTensor; bf16 copies live only in all-gather buffers)", P * 4 / SHARD / GB),
    ("fp32 Adam m + v (sharded)", P * 8 / SHARD / GB),
    ("fp32 sharded grads (reduce_dtype = fp32)", P * 4 / SHARD / GB),
    ("bf16 all-gather buffers: 2 blocks in flight + embedding + lm_head", (2 * MC["per_layer"] * 2 + 2 * MC["lm_head"] * 2) / GB),
    (f"activations, SAC(op): {ACT_LAYER_B/1024**2:.0f} MB/layer/seq x {MODEL.n_layers} layers x micro-batch {MICRO_BATCH}", ACT_LAYER_B * MODEL.n_layers * MICRO_BATCH / GB),
    (f"logits, chunked fused linear+CE (chunk {CE_CHUNK}, fp32 logits + grad)", 2 * CE_CHUNK * MODEL.vocab * 4 / GB),
    ("CUDA context, NCCL buffers, cuBLAS workspace, allocator fragmentation", 4.0),
]
MEM_TOTAL = sum(v for _, v in MEM)
MEM_HEADROOM = 80 - MEM_TOTAL
MEM_MB4 = MEM_TOTAL + ACT_LAYER_B * MODEL.n_layers * 2 / GB
MEM_NO_SAC = MEM_TOTAL - ACT_LAYER_B * MODEL.n_layers * MICRO_BATCH / GB + ACT_LAYER_NO_SAC_B * MODEL.n_layers * MICRO_BATCH / GB
assert MEM_TOTAL < 70, MEM_TOTAL
MEM_STATES = sum(v for _, v in MEM[:4])                  # fp32 params + m + v + grads + all-gather buffers (sequence-independent)
MEM_FIXED_TAIL = sum(v for _, v in MEM[5:])              # chunked logits + CUDA allowance
# long-context stages (CP=8 ring attention inside the node): local tokens per sequence = seq / CP
LOCAL_TOK_LC1, LOCAL_TOK_LC2 = SEQ_LC1 // CP_LC, SEQ_LC2 // CP_LC            # 4,096 and 16,384
KV_RING_BUF_GB = 2 * (2 * LOCAL_TOK_LC2 * kv * 2) / GB                       # double-buffered K and V chunks received from the ring
MEM_LC1 = MEM_STATES + ACT_LAYER_B * (LOCAL_TOK_LC1 / s) * MODEL.n_layers * MB_LC1 / GB + MEM_FIXED_TAIL + KV_RING_BUF_GB
MEM_LC2_SAC = MEM_STATES + ACT_LAYER_B * (LOCAL_TOK_LC2 / s) * MODEL.n_layers * MB_LC2 / GB + MEM_FIXED_TAIL + KV_RING_BUF_GB   # does not fit
LC2_SAVED_INPUTS_GB = LOCAL_TOK_LC2 * d * 2 * MODEL.n_layers * MB_LC2 / GB    # full AC: one bf16 block input per layer
LC2_LIVE_LAYER_GB = ACT_LAYER_NO_SAC_B * (LOCAL_TOK_LC2 / s) * MB_LC2 / GB    # the one block being recomputed, no SAC inside it
MEM_LC2 = [
    ("fp32 params + Adam m + v + grads, 8-way sharded (unchanged)", sum(v for _, v in MEM[:3])),
    ("bf16 all-gather buffers (unchanged)", MEM[3][1]),
    (f"full AC: saved bf16 block inputs, {LOCAL_TOK_LC2:,} local tokens x 4,096 x 2 B x {MODEL.n_layers} layers", LC2_SAVED_INPUTS_GB),
    (f"one live block during recompute (no SAC inside it), {LOCAL_TOK_LC2:,} local tokens", LC2_LIVE_LAYER_GB),
    ("ring-attention K/V receive buffers (double-buffered)", KV_RING_BUF_GB),
    (f"logits, chunked fused linear+CE (chunk {CE_CHUNK})", MEM[5][1]),
    ("CUDA context, NCCL buffers, cuBLAS workspace, allocator fragmentation", MEM[6][1]),
]
MEM_LC2_TOTAL = sum(v for _, v in MEM_LC2)
assert MEM_LC1 < 70 and MEM_LC2_TOTAL < 70, (MEM_LC1, MEM_LC2_TOTAL)
assert MEM_LC2_SAC > 80, MEM_LC2_SAC   # documents why SAC(op) is not used at 128k

AG_GB = P * 2 * (SHARD - 1) / SHARD / 1e9               # bf16 all-gather receive volume per GPU, once
RS_GB = P * 4 * (SHARD - 1) / SHARD / 1e9               # fp32 reduce-scatter per GPU
AR_GB = 2 * (P / SHARD) * 4 * (REPLICATE - 1) / REPLICATE / 1e9   # ring all-reduce of the fp32 shard across replicas
T_AG_MICRO = 2 * AG_GB * 1e9 / A["nvlink_gbps"]         # forward + backward all-gather, once per micro-step (reshard_after_forward)
T_RS_MICRO = RS_GB * 1e9 / A["nvlink_gbps"]              # reduce-scatter once per micro-step (accumulates into the fp32 sharded grad)
T_AG = T_AG_MICRO * GRAD_ACCUM                           # per optimizer step
T_RS = T_RS_MICRO * GRAD_ACCUM
T_AR = AR_GB * 1e9 / A["ib_gbps"]                        # cross-replica all-reduce ONCE per step (set_requires_all_reduce(False) on micro-step 1)
T_AR_REAL = AR_GB * 1e9 / A["ib_gbps_realistic"]
AR_TAIL_GB = 2 * ((2 * MC["per_layer"] + MC["embed"]) / SHARD) * 4 * (REPLICATE - 1) / REPLICATE / 1e9   # last 2 blocks + embedding: cannot overlap
T_AR_TAIL = AR_TAIL_GB * 1e9 / A["ib_gbps_realistic"]
BACKWARD_S = STEP_TIME_S * 2 / 3
COMM_TOTAL_S = T_AG + T_RS + T_AR
AR_SHARE_OF_STEP = T_AR_REAL / STEP_TIME_S               # the fixed all-reduce as a fraction of the step (halved by the 8M batch)
AR_SHARE_OF_STEP_4M = T_AR_REAL / (BATCH_FALLBACK_TOK / TOK_PER_S_CLUSTER)
TOK_PER_GPU_STEP = GLOBAL_BATCH_TOK / N_GPUS

CKPT_FULL_GB = P * 12 / 1e9          # fp32 params + Adam m + v
CKPT_BF16_GB = P * 2 / 1e9
CKPT_PER_GPU_MB = CKPT_FULL_GB * 1000 / N_GPUS
CKPT_NVME_WRITE_S = CKPT_PER_GPU_MB / 1000 / 2.0      # 2 GB/s per-GPU share of local NVMe
CKPT_UPLOAD_MBPS = CKPT_FULL_GB * 1000 / (A["ckpt_interval_min"] * 60)   # aggregate to object store, every interval
CKPTS_PER_DAY = 24 * 60 / A["ckpt_interval_min"]
N_PERM_FULL = int(TOK_PRETRAIN / 500e9) + 1            # 24 multiples of 500B (12.0T = end of anneal is one) + end of stable at 10.8T
CKPT_PERM_TB = (N_PERM_FULL * CKPT_FULL_GB + N_CKPT_EVALS * CKPT_BF16_GB) / 1000       # permanent tier
CKPT_ROLLING_TB = 24 * CKPT_FULL_GB / 1000                                            # rolling 24-hour hourly tier (not permanent)
CKPT_RETAINED_TB = CKPT_PERM_TB + CKPT_ROLLING_TB                                     # what object storage holds at peak

# =====================================================================================
# 6. STORAGE, CPU, EGRESS, DATA, SOFTWARE
# =====================================================================================
RAW_TB, INTERMEDIATE_TB, LOGS_TB = 70.0, 60.0, 2.0
OBJECT_TB_MONTHS = RAW_TB * 3 + INTERMEDIATE_TB * 4 + TOKENIZED_TB * 9 + CKPT_PERM_TB * 7 + CKPT_ROLLING_TB * 2 + LOGS_TB * 9
PFS_TB, PFS_MONTHS = 120.0, 5
STORAGE_USD = OBJECT_TB_MONTHS * A["usd_tb_month_object"] + PFS_TB * PFS_MONTHS * A["usd_tb_month_pfs"]
CPU_CORES, CPU_WEEKS = 768, 8
CPU_CORE_HRS = CPU_CORES * CPU_WEEKS * HRS_WK
TEXT_GB = sum(r["raw_T"] for r in DATA_ROWS) * 1e12 * A["bytes_per_token_text"] / 1e9
CORE_HR_PER_GB = 2.5       # quality 0.4 + MinHash/LSH 1.5 + exact-hash 0.1 + PII/opt-out 0.2 + tokenize/pack/shuffle 0.3
CORE_HR_PER_GB_MINHASH, CORE_HR_PER_GB_TOKENIZE = 1.5, 0.3
CC_TEXT_GB = CC_RAW_SRC_T * 1e12 * A["bytes_per_token_text"] / 1e9
# pre-production CPU work (W3-W6), booked explicitly: the W3 domain-stratified dedup measurement (5 % of the CC text, full
# pipeline), the dedup-threshold ablation corpora (a fixed 10-dump subset ~10 % of the CC text, MinHash at Jaccard 0.7 / 0.8 /
# 0.9 = 3 corpora) and the v0 corpus tokenization (>= 1.5T tokens from the as-released, per-dump-deduped shards).
W3_MEASURE_CORE_HRS = CC_TEXT_GB * W3_SAMPLE_FRAC * CORE_HR_PER_GB
DEDUP_THRESHOLDS = (0.7, 0.8, 0.9)
DEDUP_ABL_SUBSET_FRAC = 0.10
DEDUP_ABL_CORE_HRS = CC_TEXT_GB * DEDUP_ABL_SUBSET_FRAC * CORE_HR_PER_GB_MINHASH * len(DEDUP_THRESHOLDS)
V0_TOKENS = 1.5e12
V0_CORE_HRS = V0_TOKENS * A["bytes_per_token_text"] / 1e9 * CORE_HR_PER_GB_TOKENIZE
PRE_PROD_CORE_HRS = W3_MEASURE_CORE_HRS + DEDUP_ABL_CORE_HRS + V0_CORE_HRS
CPU_NEED_CORE_HRS = TEXT_GB * CORE_HR_PER_GB * 2 + PRE_PROD_CORE_HRS   # x2 for re-runs (two production passes) + pre-production work
PIPELINE_GB_PER_H = CPU_CORES / CORE_HR_PER_GB      # sustained throughput the partition implies (G1 gate, >= 300 GB/h)
PIPELINE_DAYS_PER_PASS = TEXT_GB / PIPELINE_GB_PER_H / 24
G1_GB_PER_H = 300.0
assert PIPELINE_GB_PER_H >= G1_GB_PER_H, PIPELINE_GB_PER_H
assert 2 * TEXT_GB / G1_GB_PER_H / 24 <= CPU_WEEKS * 7, "two passes must fit the CPU booking at the G1 rate"
W3_MEASURE_DAYS = W3_MEASURE_CORE_HRS / CPU_CORES / 24
DEDUP_ABL_DAYS = DEDUP_ABL_CORE_HRS / CPU_CORES / 24
V0_DAYS = V0_CORE_HRS / CPU_CORES / 24
assert W3_MEASURE_DAYS <= 1.0 and DEDUP_ABL_DAYS <= 3.0 and V0_DAYS <= 1.0, (W3_MEASURE_DAYS, DEDUP_ABL_DAYS, V0_DAYS)
# production schedule: pass 1 from W7 d1 must finish by W10 d3 (G1 rate + margin), pass 2 by W11 d7; tokenization of the frozen
# mix is incremental from W10 d4 and must reach >= G3A_TOKENS by W11 d7 (gate G3a) so the 3B/300B rehearsal has data on W12 d1.
G3A_TOKENS = 300e9
G3A_TOKENIZE_CORE_HRS = G3A_TOKENS * A["bytes_per_token_text"] / 1e9 * CORE_HR_PER_GB_TOKENIZE
assert G3A_TOKENIZE_CORE_HRS / CPU_CORES / 24 < 1.0
assert PIPELINE_DAYS_PER_PASS <= 3 * 7 + 3 - 1, "pass 1 at the partition rate must fit W7 d1 - W10 d3"
RAM_NODES, RAM_WEEKS = 3, 4
CPU_USD = CPU_CORE_HRS * A["usd_cpu_core_hr"] + RAM_NODES * RAM_WEEKS * HRS_WK * A["usd_ram_node_hr"]
assert CPU_NEED_CORE_HRS <= CPU_CORE_HRS
EGRESS_TB = 20 + TOKENIZED_TB + 500 * CKPT_BF16_GB / 1000 + 20
EGRESS_USD = EGRESS_TB * A["usd_per_tb_egress"]
HUMAN_PAIRS, HUMAN_PAIR_USD = 20_000, 5.00
EXPERT_SFT, EXPERT_SFT_USD = 2_000, 25.00
HUMAN_EVALS, HUMAN_EVAL_USD = 2_000, 10.00
RED_TEAM_USD, JUDGE_API_USD = 25_000, 25_000
ONPOLICY_PAIRS = 300_000 - HUMAN_PAIRS
EVAL_DATA_USD = HUMAN_PAIRS * HUMAN_PAIR_USD + EXPERT_SFT * EXPERT_SFT_USD + HUMAN_EVALS * HUMAN_EVAL_USD + RED_TEAM_USD + JUDGE_API_USD
SERVING_INFRA_USD = 15_000
SOFTWARE_USD = 6_000 + 3_000 + 3_000 + 3_000     # W&B, CI, paging, HF

# =====================================================================================
# 7. TEAM
# =====================================================================================
TEAM = [  # role, HC, loaded USD/yr, months, start week (W-2 = two weeks before kickoff)
    ("Program tech lead (pretraining, architecture, recipe; backs up the systems engineer)", 1.0, 450_000, 10, "W-2"),
    ("Distributed-training engineer (torchtitan/FSDP2, perf, checkpointing)", 1.0, 390_000, 9, "W1"),
    ("Data engineer (datatrove / NeMo Curator pipeline: global dedup + quality only)", 1.0, 340_000, 8, "W1"),
    ("Data-pipeline contractor (downloads, 131k tokenizer + v0 corpus, PII / opt-out, provenance manifest; planned, not conditional)", 1.0, 340_000, 3, "W1"),
    ("Research engineer (ladder, ablations, anneal selection, held-out suite, long-context; later RL)", 1.0, 340_000, 8, "W5"),
    ("Post-training and evaluation engineer (SFT/DPO/GRPO, harness, safety)", 1.0, 360_000, 6, "W13"),
    ("Infra/SRE (cluster, Slurm, storage, observability, vLLM; backs up the data engineer)", 1.0, 330_000, 10, "W-2"),
    ("Program manager / ops (vendor contracts, annotation vendors)", 0.5, 200_000, 10, "W-2"),
    ("Legal / data-licence counsel, fractional (signs the licence manifest at G3)", 0.2, 250_000, 10, "W1"),
]
team_rows = [(r, hc, ld, m, hc * ld * m / 12, start) for r, hc, ld, m, start in TEAM]
TEAM_USD = sum(t[4] for t in team_rows)
TEAM_FTE = sum(hc for _, hc, _, _, _ in TEAM)
TEAM_CORE_USD_PER_WEEK = sum(hc * ld for r, hc, ld, _, _ in TEAM if "contractor" not in r) / 52   # run rate at full strength (the contractor ends W13)
TEAM_USD_PER_WEEK = TEAM_CORE_USD_PER_WEEK
TEAM_USD_PER_DAY = TEAM_USD_PER_WEEK / 7
DATA_CONTRACTOR_MONTHS = TEAM[3][3]
DATA_CONTRACTOR_USD = TEAM[3][1] * TEAM[3][2] * DATA_CONTRACTOR_MONTHS / 12   # the planned W1-W13 line (covers the W12 freeze and the G3 manifest)
DATA_CONTRACTOR_EXT_USD = TEAM[3][2] * 1 / 12                                   # pre-authorised +1 month if G3 slips
DEV_NODE_USD_PER_WEEK = 8 * HRS_WK * RES
DATA_SLIP_2WK_USD = 2 * (TEAM_USD_PER_WEEK + DEV_NODE_USD_PER_WEEK)             # a 2-week data slip consumes the W13-14 float at the run rate
DATA_SLIP_4WK_USD = 4 * (TEAM_USD_PER_WEEK + DEV_NODE_USD_PER_WEEK)             # 4 weeks: float + contract window (Block 2 starts W17)

# =====================================================================================
# 8. BUDGET (sums to exactly 5,000,000; contingency is the residual and must be >= 15 %)
# =====================================================================================
TOTAL_BUDGET = 5_000_000
budget = [
    ("GPU compute: 4 reserved blocks + on-demand serving tail (incl. 16 hot-spare GPUs)", round(COMPUTE_USD)),
    (f"Team ({TEAM_FTE:.1f} FTE, loaded)", round(TEAM_USD)),
    ("Data processing: CPU cluster + RAM nodes", round(CPU_USD)),
    ("Storage: object store + parallel FS", round(STORAGE_USD)),
    ("Egress and DR replication", round(EGRESS_USD)),
    ("Human data, evaluation, red team, judge API", round(EVAL_DATA_USD)),
    ("Serving pilot non-GPU infra (gateway, LB, logging, 2 CPU nodes)", SERVING_INFRA_USD),
    ("Software / SaaS (W&B, CI, paging, HF)", SOFTWARE_USD),
]
NON_CONT = sum(v for _, v in budget)
CONTINGENCY = TOTAL_BUDGET - NON_CONT
budget.append(("Contingency (residual)", CONTINGENCY))
assert sum(v for _, v in budget) == TOTAL_BUDGET
CONT_PCT = CONTINGENCY / TOTAL_BUDGET
assert CONT_PCT >= 0.15, CONT_PCT

# --- sensitivities the contingency must cover
SLIP_WEEKS = 4
SENS = {
    "price +0.10 on reserved hours": RESERVED_GPU_HR * 0.10,
    "price 2.60 instead of 2.20": RESERVED_GPU_HR * (2.60 - RES),
    f"MFU below {MFU_OPTION1_TRIGGER:.3f} (the 9.9T plan is missed): +1-week option 1 on Block 2 at 2.20 (exercisable by block day {OPTION1_DEADLINE_DAY})": OPTION_WEEK_USD,
    "late restart / token floor: +1-week option 2 on Block 2 at <= 2.40 (exercisable by block day 42)": OPTION2_WEEK_USD,
    "two-week block-start slip beyond the contract window (idle Block 2)": 14 * BLOCK2_IDLE_DAY_USD,
    "one-week block-start slip": 7 * BLOCK2_IDLE_DAY_USD,
    f"{SLIP_WEEKS}-week program slip (team run rate + dev node)": SLIP_WEEKS * (TEAM_USD_PER_WEEK + DEV_NODE_USD_PER_WEEK),
    "Block 1 first 2 weeks on on-demand if contract signing slips (64 x 336 h x (2.90 - 2.20))": 64 * 2 * HRS_WK * (OD - RES),
    "human preference data doubled (40k pairs)": HUMAN_PAIRS * HUMAN_PAIR_USD,
    "human preference pairs at USD 15 instead of 5 (vendor quote risk, 20k pairs)": HUMAN_PAIRS * (15.0 - HUMAN_PAIR_USD),
    "data-pipeline contractor +1 month (G3 slips past W12)": DATA_CONTRACTOR_EXT_USD,
    "framework switch to Megatron-Core at G2: 2 engineer-weeks of checkpoint / serving export conversion (distributed-training engineer, W9-10)": 2 * 390_000 / 52,
    "3-month contractor (key-person loss)": 390_000 / 4,
}
_k_opt1 = f"MFU below {MFU_OPTION1_TRIGGER:.3f} (the 9.9T plan is missed): +1-week option 1 on Block 2 at 2.20 (exercisable by block day {OPTION1_DEADLINE_DAY})"
_k_opt2 = "late restart / token floor: +1-week option 2 on Block 2 at <= 2.40 (exercisable by block day 42)"
_k_slip = f"{SLIP_WEEKS}-week program slip (team run rate + dev node)"
COVERED = SENS["price 2.60 instead of 2.20"] + SENS[_k_opt1] + SENS["one-week block-start slip"]
COVERED_SLIP = SENS["price 2.60 instead of 2.20"] + SENS[_k_opt1] + SENS[_k_slip]
NOT_COVERED = SENS["price 2.60 instead of 2.20"] + SENS[_k_opt1] + SENS[_k_opt2] + SENS[_k_slip]   # 2.60 + both options + slip
COVERED_AT_240 = RESERVED_GPU_HR * (2.40 - RES) + SENS[_k_opt1] + SENS[_k_opt2] + SENS[_k_slip]    # same at the walk-away price
assert COVERED <= CONTINGENCY, (COVERED, CONTINGENCY)
assert COVERED_SLIP <= CONTINGENCY, (COVERED_SLIP, CONTINGENCY)
assert NOT_COVERED > CONTINGENCY          # documents why the 2.40 walk-away is load-bearing
assert COVERED_AT_240 <= CONTINGENCY, (COVERED_AT_240, CONTINGENCY)

# --- compute-only counterfactual
CO_CONT = 0.15
CO_GPU_USD = TOTAL_BUDGET * (1 - CO_CONT)
CO_GPU_HRS = CO_GPU_USD / RES
CO_SUPPORT_HRS = (USED_GPU_HR - MAIN_RUN_GPU_HR) * 1.3
CO_MAIN_HRS = CO_GPU_HRS - CO_SUPPORT_HRS
CO_TOKENS_UNCAPPED = CO_MAIN_HRS / A["overhead_main"] * gpu_hr_flop(A["mfu_main"]) / FPT_4K
# data cap on a useful run: HQ capacity at the 3-epoch caps (CAP_HQ_T) + the 1.2T anneal, to the nearest T (16T at plan);
# beyond it the marginal token is a 4th epoch or score-2 filler. Moves with measured_unique.json.
CO_TOKENS_CAPPED = round(CAP_HQ_T + TOK_ANNEAL / 1e12) * 1e12
CO_CAPPED_HRS = CO_TOKENS_CAPPED * FPT_4K / gpu_hr_flop(A["mfu_main"]) * A["overhead_main"]
CO_CAPPED_DAYS = CO_CAPPED_HRS / N_GPUS / 24
CO_LEFT_USD = CO_GPU_USD - CO_CAPPED_HRS * RES - CO_SUPPORT_HRS * RES

# --- marginal value of tokens (Chinchilla fit as a proxy only)
L_8T, L_11T, L_12T, L_15T = (chinchilla_loss(MC["total"], t) for t in (8e12, 11e12, 12e12, 15e12))
USD_8_TO_11 = 3 * USD_PER_T
USD_12_TO_15 = 3 * USD_PER_T
SERVING_USD_PER_M_TOK = RES / (A["serving_tok_s_per_gpu"] * 3600 / 1e6)
SERVING_USD_PER_M_TOK_OD = OD / (A["serving_tok_s_per_gpu"] * 3600 / 1e6)


# =====================================================================================
# 9. OUTPUT
# =====================================================================================
def usd(x: float) -> str:
    return f"{x:,.0f}"


def md() -> str:
    o = []
    p = o.append
    p("## Computed tables (generated by dr_calc.py)\n")
    p("### Key numbers")
    p("| Item | Value |")
    p("|---|---|")
    p(f"| Model shape | d_model {MODEL.d_model}, {MODEL.n_layers} layers, {MODEL.n_heads} heads / {MODEL.n_kv_heads} KV heads, head_dim {MODEL.head_dim}, SwiGLU {MODEL.ffn_hidden}, vocab {MODEL.vocab:,}, untied |")
    p(f"| Params total / non-embedding | {MC['total']:,} ({MC['total']/1e9:.3f}B) / {MC['nonembed']:,} ({MC['nonembed']/1e9:.3f}B) |")
    p(f"| Tokens | {TOK_PRETRAIN/1e12:.1f}T planned pretrain ({TOK_STABLE/1e12:.1f}T stable + {TOK_ANNEAL/1e12:.1f}T anneal, {DECAY_FRAC:.0%} decay) at 4,096 and MFU {A['mfu_main']:.2f}; {TOK_DESIGN/1e12:.1f}T design point lands at MFU {MFU_FOR_DESIGN:.3f}, {STABLE_T_AT_UPSIDE+TOK_ANNEAL/1e12:.1f}T at {MFU_UPSIDE:.2f} (date-driven anneal rule, {MFU_TOKENS_PER_POINT_T:.2f}T per MFU point); + {TOK_LC1/1e9:.0f}B at 32k + {TOK_LC2/1e9:.0f}B at 128k; + {TOK_ANNEAL_SELECT/1e9:.0f}B anneal selection |")
    p(f"| GPUs | {N_GPUS} H100 SXM compute ({N_NODES} nodes) + {8*HOT_SPARE_NODES} hot spare = {BLOCK2_GPUS} reserved for the main block |")
    p(f"| MFU (over 6ND + attention) | {A['mfu_main']:.2f} planning value for the main run (= {A['mfu_main']*6*MC['total']/FPT_4K:.3f} on the 6ND basis) = {TOKS_GATE_512:,} tok/s/GPU; G2 gate {TOKS_GATE_64:,} tok/s/GPU (0.40) on 64 GPUs, planning := G2 - 0.02 at W12, never re-based upward; {MFU_UPSIDE:.2f} is upside |")
    p(f"| Data | {UNIQUE_AVAILABLE_T:.2f}T unique in our tokenizer ({UNIQUE_AVAILABLE_SRC_T:.2f}T after global dedup in the sources' tokenizers; web rows x {TOK_SHRINK}, code/math/papers/wiki/books/Cosmopedia x 1.0); avg {AVG_EPOCHS:.2f} epochs; caps {EPOCH_CAP_STABLE_WEB:.0f} stable / {EPOCH_CAP_INCL_ANNEAL:.0f} incl. anneal; max {MAX_EPOCHS_INCL_ANNEAL:.2f}; extension pool {EXTENSION_CAPACITY_T:.2f}T for the upside |")
    p(f"| USD per GPU-hour | {RES:.2f} reserved (all four blocks, one master contract); {OD:.2f} on-demand; {A['usd_gpu_hr_spot']:.2f} spot |")
    p(f"| Main run | {MAIN_RUN_GPU_HR:,.0f} GPU-h with overhead {A['overhead_main']:.2f} = {MAIN_RUN_DAYS:.1f} days on {N_GPUS} GPUs (stable {W['stable'].days:.1f} + anneal {W['anneal'].days:.1f}) |")
    p(f"| Compute USD | {usd(COMPUTE_USD)} ({100*COMPUTE_USD/TOTAL_BUDGET:.1f} %) |")
    p(f"| Team USD | {usd(TEAM_USD)} ({TEAM_FTE:.1f} FTE incl. the 3-month data contractor, {100*TEAM_USD/TOTAL_BUDGET:.1f} %) |")
    p(f"| Contingency USD | {usd(CONTINGENCY)} ({100*CONT_PCT:.1f} %) |")
    p(f"| Total | {TOTAL_BUDGET:,} |")
    p(f"| Timeline | {A['weeks_total']} weeks = {A['weeks_total']/52*12:.1f} months (includes the W13-14 pre-block float, the {A['contract_start_window_weeks']}-week contract start window and the W39-40 buffer); Block 2 W{A['block2_start_week']}-{A['block2_start_week']+7} |")
    p("")

    p("### Parameter count")
    p("| Component | Formula | Params |")
    p("|---|---|---|")
    p(f"| Attention per layer (q, k, v, o) | {d}*{d} + 2*{d}*{kv} + {d}*{d} | {MC['attn']:,} |")
    p(f"| MLP per layer (SwiGLU gate/up/down) | 3*{d}*{F} | {MC['mlp']:,} |")
    p(f"| Norms per layer (attn_norm, mlp_norm, q_norm, k_norm) | 2*{d} + 2*{MODEL.head_dim} | {MC['norms']:,} |")
    p(f"| Per layer | sum | {MC['per_layer']:,} |")
    p(f"| All {MODEL.n_layers} layers | {MODEL.n_layers}*{MC['per_layer']:,} | {MC['layers_total']:,} |")
    p(f"| Final RMSNorm | {d} | {MC['final_norm']:,} |")
    p(f"| Input embedding | {MODEL.vocab}*{d} | {MC['embed']:,} |")
    p(f"| LM head (untied) | {MODEL.vocab}*{d} | {MC['lm_head']:,} |")
    p(f"| **Total** | | **{MC['total']:,}** ({MC['total']/1e9:.3f}B) |")
    p(f"| Non-embedding | | {MC['nonembed']:,} ({MC['nonembed']/1e9:.3f}B) |")
    p(f"| FLOP-bearing (non-embedding + lm_head) | | {MC['flop_bearing']:,} ({MC['flop_bearing']/1e9:.3f}B) |")
    p(f"\n6N over-states matmul FLOPs by {100*(MC['total']/MC['flop_bearing']-1):.1f} % (deliberate margin). Chinchilla-optimal tokens 20N = {CHINCHILLA_TOK/1e9:.0f}B; we train {TOK_PRETRAIN/CHINCHILLA_TOK:.0f}x that ({TOK_PRETRAIN/MC['total']:,.0f} tokens per parameter).")
    p(f"Chinchilla-fit proxy: L(8T) {L_8T:.4f}, L(11T) {L_11T:.4f}, L(12T) {L_12T:.4f}, L(15T) {L_15T:.4f}; 8T->11T buys {L_8T-L_11T:.4f} nats for USD {usd(USD_8_TO_11)} of stable compute at MFU {A['mfu_main']:.2f}; 11T->12T buys {L_11T-L_12T:.4f} nats and costs nothing above MFU {MFU_FOR_DESIGN:.3f} (date rule) or USD {usd(USD_PER_T)} per T otherwise; 12T->15T buys {L_12T-L_15T:.4f} nats for USD {usd(USD_12_TO_15)}.\n")

    p("### Ladder shapes (every run: main-run WSD + 10 % 1-sqrt decay; LR ranked on post-decay loss)")
    p("| Size | d_model | layers | heads/kv | ffn | N_total | N_nonembed | tokens/run | tok per nonembed-param | batch | steps | LR points x seeds | MFU | GPU-h |")
    p("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, shp, c, toks, nlr, nseed, bsz, w in ladder_rows:
        p(f"| {name} | {shp.d_model} | {shp.n_layers} | {shp.n_heads}/{shp.n_kv_heads} | {shp.ffn_hidden} | {c['total']/1e9:.3f}B | {c['nonembed']/1e9:.3f}B | {toks/1e9:.0f}B | {toks/c['nonembed']:.0f} | {bsz/MIB:.1f}M | {toks/bsz:,.0f} | {nlr} x {nseed} | {w.mfu:.0%} | {w.gpu_hr:,.0f} |")
    for name, shp, c, toks, nlr, bsz, w in ladder_dur_rows:
        p(f"| {name} (duration axis) | {shp.d_model} | {shp.n_layers} | {shp.n_heads}/{shp.n_kv_heads} | {shp.ffn_hidden} | {c['total']/1e9:.3f}B | {c['nonembed']/1e9:.3f}B | {toks/1e9:.0f}B | {toks/c['nonembed']:.0f} | {bsz/MIB:.0f}M | {toks/bsz:,.0f} | {nlr} x 1 | {w.mfu:.0%} | {w.gpu_hr:,.0f} |")
    p(f"\nDuration axis adds {LADDER_DUR_GPU_HR:,.0f} GPU-h = USD {usd(LADDER_DUR_GPU_HR*RES)} inside Block 1; the third 3B/90B LR (fit x 1.0) adds {W['ladder_3B'].gpu_hr/3:,.0f} GPU-h = USD {usd(W['ladder_3B'].gpu_hr/3*RES)}. Every ladder run and every 1B/3B ablation trains on the v0 corpus (>= {V0_TOKENS/1e12:.1f}T tokens, as-released per-dump-deduped shards in the frozen 131k tokenizer, ready at G1), so the G2 fits are v0 fits; the 3B/300B rehearsal trains on the frozen mix. Fits at G2: lr*(N) = a x N^-b (log-log least squares over the 150M/400M/1B post-decay optima; {G2_R2_REPORTED}); L(N, D) = E + A/N^0.34 + B/D^0.28 (E, A, B by least squares on every ladder post-decay loss); 3B/90B within {G2_3B_BAND_NATS} nats of L(N, D). G2 LR gate at 3B/90B: the 3-point log-LR parabola optimum (fit x 0.67, 1.0, 1.5) lies within {G2_LR_OPT_RATIO_MAX}x of the extrapolated lr*(N) AND post-decay loss at the two bracketing LRs differs by <= {G2_LR_BRACKET_LOSS_PCT} %. Main-run peak LR = clamp(lr*(N, D) extrapolated to {MC['nonembed']/1e9:.2f}B x {TOK_PRETRAIN/1e12:.1f}T, {LR_CLAMP[0]:.0e}, {LR_CLAMP[1]:.0e}); the {TOK_PRETRAIN/MC['nonembed']:,.0f} tokens/non-embedding-param regime is covered only by the stable/decay form, not by the LR fit (ladder: {90e9/SHP_3B.counts()['nonembed']:.0f}-{300e9/SHP_3B.counts()['nonembed']:.0f} tokens/param at 3B); the 3B/300B rehearsal ({300e9/SHP_3B.counts()['nonembed']:.0f} tokens/param) is the last LR confirmation. G5 (main run at peak LR at 1T / 4T / 8T): |stable-phase val loss - L_stable(N, D)| <= {G5_BAND_NATS} nats, where L_stable(N, D) = L_postdecay(N, D / (1 - {DECAY_FRAC})) + delta, delta = the stable-minus-postdecay gap logged on every ladder run, anchored by the residual at the 3B/300B rehearsal's stable-phase loss at its decay start (270B); never compared with post-decay curves (the G3b gate itself requires the anneal to lower loss >= 2 %, twice the G5 band). All forms live in this script (fit_lr_power_law, log_lr_parabola_optimum, fit_chinchilla, predict_loss_anchored, predict_stable_loss_anchored) and are self-tested on every run.\n")

    p(f"### Stable-phase mix ({TOK_STABLE/1e12:.1f}T; unique counts are planning values until measured_unique.json exists)")
    p("| Source | Raw (T, source tokenizer) | Planned dedup loss | Unique, source tok (T) | Unique, our tok (T) | Licence | Stable epochs (cap) | Tokens (T) | Mix % | Anneal (T) | Epochs incl. anneal | G3 min unique (T) | Note |")
    p("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in DATA_ROWS:
        p(f"| {r['source']} | {r['raw_T']:.3g} | {r['dedup_loss']:.0%} | {r['unique_src_T']:.3g} | {r['unique_T']:.3g}{' (measured)' if r['measured'] else ''} | {r['licence']} | {r['epochs_stable']:.2f} ({r['cap_stable']:.0f}) | {r['tokens_T']:.3f} | {r['mix_pct']:.1f} | {r['anneal_T']:.3f} | {r['epochs_incl_anneal']:.2f} | {r['g3_min_unique_T']:.3f} | {r['note']} |")
    p(f"| **Total** | {sum(r['raw_T'] for r in DATA_ROWS):.2f} | | {UNIQUE_AVAILABLE_SRC_T:.2f} | {UNIQUE_AVAILABLE_T:.2f} | | avg {AVG_EPOCHS:.2f} | **{TOK_STABLE/1e12:.2f}** | 100.0 | {sum(r['anneal_T'] for r in DATA_ROWS):.3f} | max {MAX_EPOCHS_INCL_ANNEAL:.2f} | {sum(r['g3_min_unique_T'] for r in DATA_ROWS):.2f} | unique touched {UNIQUE_TOUCHED_T:.2f}T; web {WEB_USED_T:.2f}T used / {WEB_UNIQUE_T:.2f}T unique = {WEB_USED_T/WEB_UNIQUE_T:.2f} ep; CC-derived real text {CC_UNIQUE_SRC_T:.3f}T unique (source tok) |")
    if MEASURED_UNIQUE:
        p(f"\nG3 gate on measured_unique.json ({len(MEASURED_UNIQUE)} sources measured): {'FAILED for ' + ', '.join(G3_FAILED) if G3_FAILED else 'PASSED'}. "
          + (f"Re-solved mix above: failing rows clipped to measured x cap, residual absorbed by the score-2 filler at {DATA_ROWS[5]['epochs_stable']:.2f} epochs (fallback step {'2' if DATA_ROWS[5]['epochs_stable'] > DATA_ROWS[5]['tokens_plan_T']/DATA_ROWS[5]['unique_T'] + 1e-9 else '1'}); needs sign-off before the W12 freeze." if G3_FAILED else "Planned tokens stand; epochs recomputed from the measured counts."))
    p(f"\nCC-derived real text (FineWeb-Edu, DCLM, Nemotron-CC real, score-2): {CC_UNIQUE_SRC_T:.3f}T unique in the sources' tokenizers against a per-dump (raw) count of {CC_RAW_SRC_T:.2f}T for the same four rows. Capacity at the per-source caps: {CAP_ALL_T:.1f}T stable tokens (every row at its cap); HQ rows at cap with synthetic / filler / multilingual at plan: {CAP_HQ_T:.1f}T; the same with every unique count {SHRINK_SENS:.0%} below plan: {CAP_HQ_SHRUNK_T:.1f}T (>= {TOK_STABLE/1e12:.1f}T stable, so the plan stays feasible). Ordered fallback: re-solve the mix at the caps; score-2 tier to 1.0 epoch (+{SCORE2_FALLBACK_T:.2f}T); Nemotron synthetic to 12 % of stable; date-driven WSD cut, never below the {ANNEAL_FLOOR_T:.1f}T anneal floor.")
    p(f"\nExtension pool (stable tokens beyond {TOK_STABLE/1e12:.1f}T when MFU exceeds {A['mfu_main']:.2f}): the HQ web rows (FineWeb-Edu, DCLM, Nemotron-CC real) in proportion to their room below the {EPOCH_CAP_STABLE_WEB:.0f}-epoch stable cap, capacity {EXTENSION_CAPACITY_T:.2f}T; the upside case ({MFU_UPSIDE:.2f}, {STABLE_T_AT_UPSIDE:.2f}T stable) needs {EXTENSION_NEEDED_T:.2f}T and lands at " + "; ".join(f"{k.split(' (')[0]} {v[0]:.2f} stable / {v[1]:.2f} incl. anneal" for k, v in EXT_EPOCHS_AT_UPSIDE.items()) + f" epochs. If the G2b epoch-proxy ablation (arm B unique beats arm A repeated by more than the 2-seed noise floor) decides for unique tokens, FineWeb-Edu and DCLM are capped at {EPOCH_PROXY_CAP_INCL_ANNEAL:.1f} epochs incl. anneal, the score-2 tier rises to 1.0 epoch (+{SCORE2_FALLBACK_T:.2f}T) and Nemotron-CC medium-high buckets become the extension pool.")
    p(f"\nW3 dedup measurement: keep every document whose hash(registered domain) mod {round(1/W3_SAMPLE_FRAC)} == 0 in EVERY CC dump of FineWeb-Edu, score-2, DCLM-baseline and Nemotron-CC HQ real ({W3_SAMPLE_FRAC:.0%} of {CC_TEXT_GB:,.0f} GB), run the full 5-gram/112/14x8 MinHash on the slice ({W3_MEASURE_CORE_HRS:,.0f} core-h = {W3_MEASURE_DAYS:.2f} days on {CPU_CORES} cores), publish measured removal rates for all four CC sources (the synthetic slice is derived from the real-text survival) into measured_unique.json. A per-dump sample cannot see cross-dump recrawls (P(caught) = 0.001 at k = 2 copies, 0.049 at k = 10 with 4 of ~100 dumps) and would read 5-15 % where the global pass removes 30-70 %.\n")
    p("### Generator model and output terms (synthetic / instruction sources; the dataset licence alone is not enough)")
    p("| Source | Generator and its output terms | Status / default substitution |")
    p("|---|---|---|")
    for k, (gen, status) in GENERATOR_TERMS.items():
        p(f"| {k} | {gen} | {status} |")
    p("\nCounsel's W3 memo states positions on (a) the Llama-output naming clause, (b) OpenAI-output training clauses, (c) Qwen attribution, and (d) CC-BY-SA 4.0 for weights; the G3 manifest signature certifies the generator column, not only the dataset licences.\n")
    p(f"### Anneal mix ({TOK_ANNEAL/1e12:.1f}T; candidate 1 of 4, selected at the ~8T checkpoint)")
    p("| Component | Share | Tokens (B) | Sub-pool unique (T) | Sub-pool epochs incl. stable | Parent stable row |")
    p("|---|---|---|---|---|---|")
    for r in ANNEAL_ROWS:
        p(f"| {r['component']} | {r['share']:.0%} | {r['tokens_B']:.0f} | {r['subpool_unique_T']:.3g} | {r['epochs_subpool_incl_stable']:.2f} | {r['parent']} |")
    p("")
    p(f"### Long-context mix ({TOK_LC1/1e9:.0f}B at 32k; the {TOK_LC2/1e9:.0f}B 128k stage uses the same mix with a 64k length floor)")
    p("| Component | Share | Tokens (B) at 32k | Tokens (B) at 128k |")
    p("|---|---|---|---|")
    for name, share in DATA_LC:
        p(f"| {name} | {share:.0%} | {share*TOK_LC1/1e9:.1f} | {share*TOK_LC2/1e9:.1f} |")
    p(f"\nTokenized corpus: {TOKENIZED_TOKENS/1e12:.2f}T tokens x 4 B (uint32) = {TOKENIZED_TB:.1f} TB.\n")

    p("### Recipe numbers")
    p("| Item | Value | Arithmetic |")
    p("|---|---|---|")
    p(f"| Global batch | {GLOBAL_BATCH_TOK:,} tokens (default) | {N_GPUS} GPUs x micro-batch {MICRO_BATCH} x {SEQ_PRETRAIN} x grad-accum {GRAD_ACCUM}; fallback {BATCH_FALLBACK_TOK:,} (grad-accum 1) only if the 1B batch ablation shows > 0.5 % post-decay penalty at the 8M-equivalent; the 4T decision from the B_simple trend is 'step down to 4M', never up |")
    p(f"| Batch ramp | {BATCH_RAMP_START:,} -> {BATCH_RAMP_MID:,} over the first {BATCH_RAMP1_TOKENS/1e9:.0f}B tokens (grad-accum 1), then -> {GLOBAL_BATCH_TOK:,} by {BATCH_RAMP_TOKENS/1e9:.0f}B (grad-accum 2), linear in steps | phase 1: {STEPS_RAMP1:,.0f} steps = {BATCH_RAMP1_TOKENS/1e9:.0f}B / mean batch {(BATCH_RAMP_START+BATCH_RAMP_MID)//2:,}, per-rank packed window {RAMP_WINDOW_START:,} -> {RAMP_WINDOW_END:,} in {RAMP_WINDOW_STEP}-token steps = {RAMP_PLATEAUS} plateaus of {STEPS_PER_PLATEAU1:,.0f} steps; phase 2: {STEPS_RAMP2:,.0f} steps = {BATCH_RAMP2_TOKENS/1e9:.0f}B / mean batch {(BATCH_RAMP_MID+GLOBAL_BATCH_TOK)//2:,}, two micro-steps each with the window again {RAMP_WINDOW_START:,} -> {RAMP_WINDOW_END:,} = {RAMP_PLATEAUS} plateaus of {STEPS_PER_PLATEAU2:,.0f} steps; max_seqlen stays {SEQ_PRETRAIN:,}; cu_seqlens padded to {CU_SEQLENS_PAD:,} int32 entries + token dim marked dynamic = {2*RAMP_PLATEAUS} window recompiles in total, zero per document count |")
    p(f"| Warmup | {WARMUP_STEPS:,.0f} steps ({WARMUP_TOKENS/1e9:.0f}B tokens) linear from 0 | inside ramp phase 1: {BATCH_RAMP_START:,} s + {BATCH_RAMP_MID-BATCH_RAMP_START:,} s^2 / (2 x {STEPS_RAMP1:,.0f}) = {WARMUP_TOKENS:.0e}; stated in steps because the ramp makes tokens ambiguous; the 3B/300B rehearsal checks for early grad-norm spikes |")
    p(f"| Steps: stable / anneal / total | {STEPS_STABLE:,.0f} / {STEPS_ANNEAL:,.0f} / {STEPS_TOTAL:,.0f} | ramp {STEPS_RAMP:,.0f} + ({TOK_STABLE/1e12:.1f}T - {BATCH_RAMP_TOKENS/1e12:.1f}T) / {GLOBAL_BATCH_TOK:,}; {TOK_ANNEAL/1e12:.1f}T / {GLOBAL_BATCH_TOK:,} |")
    p(f"| Peak LR / min LR | {PEAK_LR:.1e} prior; final = clamp(lr*(N, D), {LR_CLAMP[0]:.0e}, {LR_CLAMP[1]:.0e}) / {MIN_LR:.1e} | min = {MIN_LR_FRAC:.0%} of peak; 1-sqrt decay; LR unchanged by the 8M batch (the sqrt rule would allow x1.41; 3e-4 stays the safe prior) |")
    p(f"| Long-context LR | constant {LC_LR:.1e} after a {LC_WARMUP_TOKENS/1e9:.0f}B-token warmup | 10 % of peak |")
    p(f"| Long-context batch | 32k: {BATCH_LC1:,} = {LC_GROUPS} CP groups x mb {MB_LC1} x {SEQ_LC1:,} ({STEPS_LC1:,.0f} steps); 128k: {BATCH_LC2:,} = {LC_GROUPS} x mb {MB_LC2} x {SEQ_LC2:,} ({STEPS_LC2:,.0f} steps) | CP={CP_LC} inside the node; 128k uses full per-block AC |")
    p(f"| FLOP per token (4k / 32k / 128k) | {FPT_4K:.4e} / {MODEL.flops_per_token(SEQ_LC1):.4e} / {MODEL.flops_per_token(SEQ_LC2):.4e} | 6N = {6*MC['total']:.4e}; attention = 6*L*s*d = {MODEL.attn_flops_per_token(SEQ_PRETRAIN):.4e} at 4k ({100*MODEL.attn_flops_per_token(SEQ_PRETRAIN)/(6*MC['total']):.2f} % of 6N) |")
    p(f"| Throughput at plan MFU | {TOK_PER_S_CLUSTER:,.0f} tok/s cluster, {TOK_PER_S_GPU:,.0f} tok/s/GPU, {STEP_TIME_S:.2f} s/step | {N_GPUS} x 989e12 x {A['mfu_main']} / {FPT_4K:.4e} |")
    p(f"| Checkpoint cadence | every {A['ckpt_interval_min']} min = {CKPT_EVERY_STEPS:,.0f} steps; {CKPTS_PER_DAY:.0f}/day | |")
    p(f"| Validation | 6 x 10M tokens every {VAL_EVERY_STEPS} steps ({VAL_FRAC_INLOOP:.2%}) + {len(DATA_STABLE)} x 10M per-source every 10B tokens ({VAL_FRAC_PER_SOURCE:.2%}) | total {VAL_FRAC_TOTAL:.2%} of step time, booked as 1.0 % |")
    p("")
    p("### Throughput gates (tokens/s per GPU; basis-free)")
    p("| Gate | tok/s/GPU | Equals (DR basis) | Where |")
    p("|---|---|---|---|")
    p(f"| G2, G3b: 10B config on 64 GPUs at seq {SEQ_PRETRAIN:,} | >= {TOKS_GATE_64:,} | MFU {MFU_OF(TOKS_GATE_64):.3f} | W8, W13 |")
    p(f"| G4 acceptance (2 h rolling, 512 GPUs), G5 rolling | >= {TOKS_GATE_512:,} | MFU {MFU_OF(TOKS_GATE_512):.3f} = the planning value | Block 2 |")
    p(f"| G3b: 32k stage path (CP=8, one node) | >= {TOKS_GATE_32K:,} | MFU {MFU_OF(TOKS_GATE_32K, SEQ_LC1):.3f} at 32k | W13 |")
    p(f"| G3b: 128k stage path (CP=8, one node, full AC) | >= {TOKS_GATE_128K:,} | MFU {MFU_OF(TOKS_GATE_128K, SEQ_LC2):.3f} at 128k | W13 |")
    p(f"\nMFU always means tokens/s x {FPT_4K:.4e} / 989e12 at seq 4,096 (6ND + causal attention). torchtitan's built-in MFU counts attention non-causally (12*L*h*hd*s) and reads x{TORCHTITAN_MFU_RATIO:.3f} on this basis: a torchtitan-reported 0.40 is {0.40/TORCHTITAN_MFU_RATIO:.3f} here and {0.40*6*MC['total']/FPT_4K/TORCHTITAN_MFU_RATIO:.3f} on 6ND; the metrics hook logs tokens/s/GPU and the DR-basis MFU next to torchtitan's number. The G4 shakedown is {SHAKEDOWN_H:.0f} h of the real job = {SHAKEDOWN_TOKENS/1e9:.0f}B tokens at plan throughput.\n")

    p("### Overhead build-up (main run)")
    p("| Component | Fraction of ideal time |")
    p("|---|---|")
    for name, f in OVERHEAD_BREAKDOWN:
        p(f"| {name} | {100*f:.1f} % |")
    p(f"| **Sum** | **{100*OVERHEAD_SUM:.1f} % -> factor {A['overhead_main']:.2f}** |")
    p(f"\nInterruption model: {INTERRUPTS:.1f} events x {LOST_PER_INTERRUPT_MIN:.0f} min / ({MAIN_RUN_DAYS:.1f} d x 24 h) = {100*INTERRUPT_FRAC:.2f} %; valid only because every 30-min checkpoint is uploaded ({CKPT_UPLOAD_MBPS:.0f} MB/s aggregate), so a node loss never rolls back further than one interval.\n")

    p("### Compute plan (GPU-hours; USD at the block's price)")
    p("| Workload | Block | Tokens | Seq | MFU | FLOPs | GPU-h ideal | Overhead | GPU-h | GPUs | Days | USD |")
    p("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for w in W.values():
        t = f"{w.tokens/1e12:.2f}T" if w.tokens >= 1e12 else (f"{w.tokens/1e9:.1f}B" if w.tokens else "-")
        fl = f"{w.flops:.2e}" if w.flops else "-"
        mfu = f"{w.mfu:.0%}" if w.mfu else "-"
        p(f"| {w.name} | {w.block} | {t} | {w.seq or '-'} | {mfu} | {fl} | {w.gpu_hr_ideal:,.0f} | {w.overhead:.2f} | {w.gpu_hr:,.0f} | {w.gpus} | {w.days:.1f} | {usd(w.usd)} |")
    p(f"| **Sum of workloads** | | | | | | | | **{USED_GPU_HR:,.0f}** | | | |")
    p("\nRows rounded independently; totals from unrounded values.")
    p(f"\nMain run: 6ND = {MAIN_6ND:.4e}; with attention {MAIN_FLOPS:.4e} FLOP; / ({PEAK:.3e} x {A['mfu_main']} x 3600 = {gpu_hr_flop(A['mfu_main']):.4e} FLOP per GPU-h) = {MAIN_RUN_IDEAL:,.0f} GPU-h ideal; x {A['overhead_main']:.2f} = {MAIN_RUN_GPU_HR:,.0f} GPU-h; / {N_GPUS} / 24 = {MAIN_RUN_DAYS:.1f} days. Per 1T stable tokens: {GPU_HR_PER_T:,.0f} GPU-h = USD {usd(USD_PER_T)}.")
    p(f"RL note: {W['rl'].note}; wall-clock budget gives {W['rl'].gpu_hr/RL_FLOP_GPU_HR:.1f}x headroom.\n")

    p("### Reserved blocks (cash)")
    p("| Block | GPUs | Weeks | GPU-h | USD/GPU-h | USD | Attributed GPU-h | Utilisation |")
    p("|---|---|---|---|---|---|---|---|")
    for b in block_rows:
        p(f"| {b['name']} | {b['gpus']} | {b['weeks']} | {b['gpu_hr']:,} | {b['price']:.2f} | {usd(b['usd'])} | {b['used']:,.0f} | {100*b['util']:.0f} % |")
    p(f"| **Total** | | | **{TOTAL_GPU_HR_BOUGHT:,}** | | **{usd(COMPUTE_USD)}** | **{USED_GPU_HR:,.0f}** | {100*UTIL_OVERALL:.0f} % |")
    p(f"\nRows rounded independently; totals from unrounded values. Reserved hours {RESERVED_GPU_HR:,} under one master contract over W1-W40 (dev node to W40; the 64/528/48-GPU blocks end W30); +0.10/GPU-h = USD {usd(SENS['price +0.10 on reserved hours'])}. Idle Block 2 day = {BLOCK2_GPUS} x 24 x {RES:.2f} = USD {usd(BLOCK2_IDLE_DAY_USD)}. Option 1 (+1 week at {RES:.2f}, by block day {OPTION1_DEADLINE_DAY} = {TOK_AT_OPTION1_DEADLINE_T:.1f}T stable tokens, {week_day(OPTION1_DEADLINE_DAY)}) = USD {usd(OPTION_WEEK_USD)}, exercised only if the effective MFU projects below {MFU_OPTION1_TRIGGER:.3f} (the {TOK_STABLE/1e12:.1f}T plan missed); option 2 (+1 week at <= {OPTION2_PRICE:.2f}, by block day 42) = USD {usd(OPTION2_WEEK_USD)}; each buys {OPTION_WEEK_TOKENS_T:.2f}T stable tokens at plan MFU. Neither option is in the base plan. Acceptance days are billed (4 x {BLOCK2_GPUS} GPUs, USD {usd(W['accept'].usd)}); the acceptance clause credits days lost to vendor-caused failures.\n")

    p("### Block 2 fit and the anneal-start rule")
    p("| Item | Days | Note |")
    p("|---|---|---|")
    p(f"| Block length | {BLOCK2_DAYS:.0f} | 8 weeks |")
    p(f"| Acceptance + burn-in | {ACCEPT_DAYS:.1f} | block days 0-4, billed |")
    p(f"| Stable phase needed at MFU {A['mfu_main']:.2f} | {STABLE_NEED_DAYS:.1f} | {W['stable'].gpu_hr:,.0f} GPU-h / {N_GPUS} / 24 |")
    p(f"| Anneal-mix selection pause (~8T) | {W['anneal_select'].days:.1f} | 4 x 50B as 4 parallel 128-GPU jobs |")
    p(f"| Anneal | {W['anneal'].days:.1f} | starts at block day {ANNEAL_START_DAY:.1f} ({week_day(ANNEAL_START_DAY)}) if >= {ANNEAL_FLOOR_T:.1f}T stable tokens are reached; below the floor an option is exercised instead |")
    p(f"| 32k stage + 128k stage | {W['lc32k'].days:.1f} + {W['lc128k'].days:.1f} | |")
    p(f"| Total needed | {BLOCK2_NEED_DAYS:.1f} | slack {BLOCK2_SLACK_DAYS:.1f} d = {SLACK_TOKENS/1e12:.2f}T extra stable tokens ({TOK_PER_STABLE_DAY/1e12:.3f}T per stable day) |")
    p(f"| Stable window (day {ACCEPT_DAYS:.0f} to {ANNEAL_START_DAY:.1f} minus the select pause) | {STABLE_WINDOW_DAYS:.1f} | expected stable tokens {STABLE_EXPECTED_T:.2f}T at MFU {A['mfu_main']:.2f} ({STABLE_EXPECTED_T+TOK_ANNEAL/1e12:.2f}T total); {TOK_DESIGN/1e12:.1f}T total at MFU {MFU_FOR_DESIGN:.3f}; {STABLE_T_AT_UPSIDE:.2f}T stable ({STABLE_T_AT_UPSIDE+TOK_ANNEAL/1e12:.1f}T total) at {MFU_UPSIDE:.2f}; {STABLE_T_AT_LOW:.2f}T at MFU {MFU_LOW:.2f} (shortfall {STABLE_SHORTFALL_DAYS_AT_LOW:.1f} d) unless option 1 is exercised; {MFU_TOKENS_PER_POINT_T:.2f}T stable per MFU point |")
    p(f"\nRows rounded independently; totals from unrounded values. The anneal, the selection pause and the stable phase all scale with the effective MFU; the long-context stages do not. Option 1 trigger: effective MFU below {MFU_OPTION1_TRIGGER:.3f} (the {TOK_STABLE/1e12:.1f}T plan is missed by more than the {BLOCK2_SLACK_DAYS:.1f}-day slack). Anneal token floor {ANNEAL_FLOOR_T:.1f}T: binds only if the effective MFU falls below {MFU_AT_FLOOR:.3f} or {DAYS_LOST_AT_FLOOR:.1f} stable days are lost (restart from an old checkpoint, bad hot-swap, non-determinism found via the data-order hash); option 1 by day {OPTION1_DEADLINE_DAY} or option 2 by day 42 then adds {OPTION_WEEK_TOKENS_T:.2f}T per week.")
    p(f"\nToken milestones (block day; stable starts day {ACCEPT_DAYS:.0f}): 1T at day {TOK_AT_DAY[1e12]:.1f} ({week_day(TOK_AT_DAY[1e12])}), 4T at day {TOK_AT_DAY[4e12]:.1f} ({week_day(TOK_AT_DAY[4e12])}), 8T at day {TOK_AT_DAY[8e12]:.1f} ({week_day(TOK_AT_DAY[8e12])}), resume after selection at day {TOK_AT_DAY[8e12+1]:.1f}.\n")

    p(f"### Memory per GPU (HSDP shard={SHARD} in-node, replicate={REPLICATE}; micro-batch {MICRO_BATCH} x {SEQ_PRETRAIN}; SAC op-level)")
    p("| Item | GB |")
    p("|---|---|")
    for k, v in MEM:
        p(f"| {k} | {v:.2f} |")
    p(f"| **Total** | **{MEM_TOTAL:.2f}** |")
    p(f"| Headroom to 80 GB | {MEM_HEADROOM:.2f} |")
    p(f"\nMicro-batch 4 would need {MEM_MB4:.1f} GB (does not fit); no activation checkpointing at micro-batch 2 would need {MEM_NO_SAC:.1f} GB (too tight). SAC(op) recomputes only RMSNorm, RoPE, SiLU and the gate*up product (~2 % of step time).")
    p(f"\n### Memory per GPU, long-context stages (CP={CP_LC} inside the node, dp_shard={SHARD}, dp_replicate={N_GPUS//CP_LC//SHARD})")
    p(f"32k stage: {LOCAL_TOK_LC1:,} local tokens per sequence x micro-batch {MB_LC1}, SAC(op): {MEM_LC1:.2f} GB (the 4k table + {KV_RING_BUF_GB:.2f} GB ring K/V buffers). 128k stage with SAC(op) at micro-batch 1 would need {MEM_LC2_SAC:.1f} GB (does not fit), so it uses full per-block activation checkpointing:")
    p("| Item (128k, micro-batch 1, full AC) | GB |")
    p("|---|---|")
    for k, v in MEM_LC2:
        p(f"| {k} | {v:.2f} |")
    p(f"| **Total** | **{MEM_LC2_TOTAL:.2f}** (headroom {80-MEM_LC2_TOTAL:.2f}) |")
    p(f"\nCommunication per optimizer step (grad-accum {GRAD_ACCUM}): bf16 all-gather {AG_GB:.1f} GB x 2 (fwd + bwd) at {A['nvlink_gbps']/1e9:.0f} GB/s NVLink = {T_AG_MICRO:.3f} s per micro-step, {T_AG:.3f} s per step; fp32 reduce-scatter {RS_GB:.1f} GB = {T_RS_MICRO:.3f} s per micro-step (accumulating into the fp32 sharded grad), {T_RS:.3f} s per step; fp32 all-reduce of the {P/SHARD/1e9:.2f}B-param shard across {REPLICATE} replicas ONCE per step (set_requires_all_reduce(False) on micro-step 1) = {AR_GB:.1f} GB at {A['ib_gbps']/1e9:.0f} GB/s IB line rate = {T_AR:.3f} s ({T_AR_REAL:.3f} s at the {A['ib_gbps_realistic']/1e9:.0f} GB/s a 64-node ring sustains); comm total {COMM_TOTAL_S:.3f} s of the {STEP_TIME_S:.2f} s step (backward ~{BACKWARD_S:.2f} s) with {TOK_PER_GPU_STEP:,.0f} tokens per GPU per step; the fixed all-reduce is {100*AR_SHARE_OF_STEP:.1f} % of the step ({100*AR_SHARE_OF_STEP_4M:.1f} % at the 4M fallback); the all-reduce of the last two blocks + embedding ({AR_TAIL_GB:.2f} GB, {T_AR_TAIL*1000:.0f} ms, {100*T_AR_TAIL/STEP_TIME_S:.1f} % of the step) cannot overlap.")
    p(f"Checkpoints: full state {CKPT_FULL_GB:.1f} GB (12 B/param), bf16 export {CKPT_BF16_GB:.1f} GB, {CKPT_PER_GPU_MB:.0f} MB per GPU written in {CKPT_NVME_WRITE_S:.2f} s at 2 GB/s; uploaded every interval at {CKPT_UPLOAD_MBPS:.0f} MB/s aggregate; permanent tier {N_PERM_FULL} full x {CKPT_FULL_GB:.1f} GB + {N_CKPT_EVALS} bf16 x {CKPT_BF16_GB:.1f} GB = {CKPT_PERM_TB:.1f} TB; rolling 24-hour hourly tier 24 x {CKPT_FULL_GB:.1f} GB = {CKPT_ROLLING_TB:.1f} TB; retained at peak {CKPT_RETAINED_TB:.1f} TB.\n")

    p("### Budget (sums to exactly 5,000,000)")
    p("| Line item | USD | % of 5.0M |")
    p("|---|---|---|")
    for name, v in budget:
        p(f"| {name} | {v:,} | {100*v/TOTAL_BUDGET:.1f} |")
    p(f"| **Total** | **{TOTAL_BUDGET:,}** | **100.0** |")
    p(f"\nRows rounded independently; totals from unrounded values. Line arithmetic: data CPU = {CPU_CORES} cores x {CPU_WEEKS} wk x 168 h x {A['usd_cpu_core_hr']} + {RAM_NODES} RAM nodes x {RAM_WEEKS} wk x 168 h x {A['usd_ram_node_hr']:.2f} = {usd(CPU_USD)} (need {CPU_NEED_CORE_HRS:,.0f} of {CPU_CORE_HRS:,} core-h: {TEXT_GB:,.0f} GB text x {CORE_HR_PER_GB} core-h/GB x 2 production passes + {PRE_PROD_CORE_HRS:,.0f} core-h pre-production; the partition implies {PIPELINE_GB_PER_H:.0f} GB/h = {PIPELINE_DAYS_PER_PASS:.1f} days per pass, so G1 requires >= {G1_GB_PER_H:.0f} GB/h sustained); storage = {OBJECT_TB_MONTHS:,.0f} TB-months x {A['usd_tb_month_object']:.0f} + {PFS_TB:.0f} TB x {PFS_MONTHS} mo x {A['usd_tb_month_pfs']:.0f} = {usd(STORAGE_USD)}; egress = {EGRESS_TB:.1f} TB x {A['usd_per_tb_egress']:.0f} = {usd(EGRESS_USD)}; human data = {HUMAN_PAIRS:,} pairs x {HUMAN_PAIR_USD:.2f} + {EXPERT_SFT:,} expert SFT x {EXPERT_SFT_USD:.0f} + {HUMAN_EVALS:,} human evals x {HUMAN_EVAL_USD:.0f} + red team {usd(RED_TEAM_USD)} + judge/synthetic API {usd(JUDGE_API_USD)} = {usd(EVAL_DATA_USD)}; the other {ONPOLICY_PAIRS:,} preference pairs are on-policy and labelled by the local judge (Block 3 GPU-h). The {HUMAN_PAIRS:,} human pairs compare outputs of the W23 d4 SFT checkpoint (ordered W23 d5, delivered 10k/week on W24 d5 and W25 d5, used for the reward model); the W13-22 vendor work is the {EXPERT_SFT:,} expert SFT examples only.")
    p(f"\nPre-production CPU work (W3-W6, inside the booking): W3 domain-stratified dedup measurement {W3_MEASURE_CORE_HRS:,.0f} core-h ({W3_MEASURE_DAYS:.2f} d on {CPU_CORES} cores); dedup-threshold ablation corpora (10-dump subset, {DEDUP_ABL_SUBSET_FRAC:.0%} of the CC text, MinHash at Jaccard {' / '.join(str(t) for t in DEDUP_THRESHOLDS)}) {DEDUP_ABL_CORE_HRS:,.0f} core-h ({DEDUP_ABL_DAYS:.1f} d, W5-6); v0 corpus tokenization ({V0_TOKENS/1e12:.1f}T tokens) {V0_CORE_HRS:,.0f} core-h ({V0_DAYS:.2f} d, W5-6). Production: pass 1 W7 d1 -> W10 d3 at the latest ({PIPELINE_DAYS_PER_PASS:.1f} d at the partition rate + margin), pass 2 (re-run after fixes) -> W11 d7; tokenization of the frozen mix incremental from W10 d4, >= {G3A_TOKENS/1e9:.0f}B tokens by W11 d7 (gate G3a, {G3A_TOKENIZE_CORE_HRS:,.0f} core-h) so the 3B/300B rehearsal has data on W12 d1; if G3a slips the rehearsal starts on v0 and the G5 anchor is re-based at the main run's 1T checkpoint.\n")

    p("### Sensitivities covered by contingency")
    p("| Scenario | USD |")
    p("|---|---|")
    for k, v in SENS.items():
        p(f"| {k} | {usd(v)} |")
    p(f"| Price 2.60 + option 1 + one-week idle slip together (pre-authorised) | {usd(COVERED)} (contingency {usd(CONTINGENCY)}, remainder {usd(CONTINGENCY-COVERED)}) |")
    p(f"| Price 2.60 + option 1 + {SLIP_WEEKS}-week program slip | {usd(COVERED_SLIP)} (remainder {usd(CONTINGENCY-COVERED_SLIP)}) |")
    p(f"| Price 2.60 + both options + {SLIP_WEEKS}-week slip | {usd(NOT_COVERED)} (exceeds contingency by {usd(NOT_COVERED-CONTINGENCY)}: the 2.40 walk-away is load-bearing) |")
    p(f"| Price 2.40 (walk-away) + both options + {SLIP_WEEKS}-week slip | {usd(COVERED_AT_240)} (remainder {usd(CONTINGENCY-COVERED_AT_240)}) |")
    p("")

    p("### Team")
    p("| Role | HC | Loaded USD/yr | Months | Start | USD |")
    p("|---|---|---|---|---|---|")
    for role, hc, ld, m, u, start in team_rows:
        p(f"| {role} | {hc} | {ld:,} | {m} | {start} | {u:,.0f} |")
    p(f"| **Total** | **{TEAM_FTE:.1f}** | | | | **{TEAM_USD:,.0f}** |")
    p(f"\nRows rounded independently; totals from unrounded values. Run rate at full strength (without the contractor): USD {usd(TEAM_USD_PER_WEEK)} per week, USD {usd(TEAM_USD_PER_DAY)} per day. The {DATA_CONTRACTOR_MONTHS}-month data-pipeline contractor (USD {usd(DATA_CONTRACTOR_USD)}, W1-W13) is a planned line; pre-authorised +1 month (USD {usd(DATA_CONTRACTOR_EXT_USD)}) if G3 slips. A data slip past W12 costs USD {usd(DATA_SLIP_2WK_USD)} per 2 weeks (float consumed at the run rate + dev node), USD {usd(DATA_SLIP_4WK_USD)} at 4 weeks (float + contract window, Block 2 starts W17), then USD {usd(BLOCK2_IDLE_DAY_USD)} per idle Block 2 day.\n")

    p("### Compute-only counterfactual")
    p(f"USD {usd(CO_GPU_USD)} (after 15 % reserve) / {RES:.2f} = {CO_GPU_HRS:,.0f} GPU-h; minus support work {CO_SUPPORT_HRS:,.0f} GPU-h = {CO_MAIN_HRS:,.0f} for the main run = {CO_TOKENS_UNCAPPED/1e12:.1f}T tokens uncapped at MFU {A['mfu_main']:.2f}. Data caps the useful run at {CO_TOKENS_CAPPED/1e12:.0f}T (HQ rows at their 3-epoch caps = {CAP_HQ_T:.1f}T + the {TOK_ANNEAL/1e12:.1f}T anneal; beyond it the marginal token is a 4th epoch or score-2 filler): {CO_CAPPED_HRS:,.0f} GPU-h, {CO_CAPPED_DAYS:.1f} days on {N_GPUS} GPUs, USD {usd(CO_CAPPED_HRS*RES)}; USD {usd(CO_LEFT_USD)} would be returned or re-open the model-size decision.\n")
    p(f"Serving: {A['serving_tok_s_per_gpu']:.0f} output tok/s per H100 (FP8, batch 64) = USD {SERVING_USD_PER_M_TOK:.3f} per 1M output tokens at the reserved rate, {SERVING_USD_PER_M_TOK_OD:.3f} on-demand.")
    return "\n".join(o)


def summary() -> dict:
    return {
        "generated_by": "dr_calc.py",
        "assumptions": A,
        "model": {
            "d_model": MODEL.d_model, "n_layers": MODEL.n_layers, "n_heads": MODEL.n_heads, "n_kv_heads": MODEL.n_kv_heads,
            "head_dim": MODEL.head_dim, "ffn_hidden": MODEL.ffn_hidden, "vocab_size": MODEL.vocab, "tied_embeddings": False,
            "norm": "RMSNorm pre-norm eps 1e-5", "qk_norm": "RMSNorm over head_dim on q and k, before RoPE, learnable scale",
            "z_loss": 1e-4, "rope_theta": ROPE_THETA, "biases": False, "activation": "SwiGLU",
            "seq_len": {"pretrain": SEQ_PRETRAIN, "post_training": SEQ_POST, "long_context_1": SEQ_LC1, "long_context_2": SEQ_LC2},
            "params": {k: int(v) for k, v in MC.items()},
            "params_total_B": round(MC["total"] / 1e9, 3), "params_nonembed_B": round(MC["nonembed"] / 1e9, 3),
            "init": {"std": 0.02, "out_proj_std": round(0.02 / math.sqrt(2 * MODEL.n_layers), 5), "lm_head_std": round(MODEL.d_model ** -0.5, 4)},
        },
        "training": {
            "tokens_stable": TOK_STABLE, "tokens_anneal": TOK_ANNEAL, "tokens_pretrain": TOK_PRETRAIN, "decay_fraction": DECAY_FRAC,
            "tokens_design_point": TOK_DESIGN, "mfu_for_design_point": round(MFU_FOR_DESIGN, 3),
            "stable_tokens_vs_mfu": {"rule": "date-driven anneal start; stable tokens = (block days - acceptance - long-context days) x rate(MFU) - (anneal + selection tokens)",
                                     "at_plan_0.38_T": round(STABLE_EXPECTED_T, 2), "at_0.42_T": round(STABLE_T_AT_UPSIDE, 2), "at_0.36_T": round(STABLE_T_AT_LOW, 2),
                                     "T_per_mfu_point": round(MFU_TOKENS_PER_POINT_T, 2), "option1_trigger_mfu": round(MFU_OPTION1_TRIGGER, 3), "floor_mfu": round(MFU_AT_FLOOR, 3)},
            "tokens_longctx_32k": TOK_LC1, "tokens_longctx_128k": TOK_LC2, "tokens_anneal_select": TOK_ANNEAL_SELECT,
            "tokens_per_param": round(TOK_PRETRAIN / MC["total"]), "chinchilla_multiple": round(TOK_PRETRAIN / CHINCHILLA_TOK, 1),
            "global_batch_tokens": GLOBAL_BATCH_TOK, "micro_batch": MICRO_BATCH, "grad_accum": GRAD_ACCUM,
            "global_batch_fallback_tokens": BATCH_FALLBACK_TOK,
            "batch_rule": "8M default (grad-accum 2, set_requires_all_reduce(False) on micro-step 1); 4M fallback only if the 1B batch ablation shows > 0.5 % post-decay penalty at the 8M-equivalent; the 4T decision from B_simple is 'step down to 4M', never up; LR unchanged",
            "batch_ramp": {"start": BATCH_RAMP_START, "mid": BATCH_RAMP_MID, "end": GLOBAL_BATCH_TOK, "phase1_over_tokens": BATCH_RAMP1_TOKENS, "phase2_over_tokens": BATCH_RAMP2_TOKENS,
                           "convention": "linear in steps", "steps_phase1": round(STEPS_RAMP1), "steps_phase2": round(STEPS_RAMP2), "steps": round(STEPS_RAMP),
                           "implementation": f"phase 1 (grad-accum 1): per-rank packed varlen window {RAMP_WINDOW_START} -> {RAMP_WINDOW_END} in {RAMP_WINDOW_STEP}-token increments; phase 2 (grad-accum 2): each of the two micro-step windows again {RAMP_WINDOW_START} -> {RAMP_WINDOW_END}",
                           "plateaus_per_phase": RAMP_PLATEAUS, "steps_per_plateau": [round(STEPS_PER_PLATEAU1), round(STEPS_PER_PLATEAU2)], "max_seqlen": SEQ_PRETRAIN,
                           "compile": f"cu_seqlens padded to {CU_SEQLENS_PAD} int32 entries, token dim marked dynamic (torch._dynamo.mark_dynamic): {2*RAMP_PLATEAUS} window recompiles total, zero per document count; G1 asserts zero extra recompiles over 3 document counts x 2 window sizes"},
            "warmup_tokens": WARMUP_TOKENS, "warmup_steps": round(WARMUP_STEPS),
            "steps_stable": round(STEPS_STABLE), "steps_anneal": round(STEPS_ANNEAL), "steps_total": round(STEPS_TOTAL),
            "optimizer": "AdamW betas (0.9, 0.95) eps 1e-8 fused", "peak_lr": PEAK_LR, "peak_lr_rule": f"clamp(lr*(N, D) extrapolated to {MC['nonembed']/1e9:.2f}B x {TOK_PRETRAIN/1e12:.1f}T, {LR_CLAMP[0]:.0e}, {LR_CLAMP[1]:.0e}); prior 3e-4",
            "peak_lr_clamp": list(LR_CLAMP), "min_lr": MIN_LR, "longctx_lr": LC_LR,
            "schedule": "WSD: linear warmup, constant stable, 1-sqrt decay to 1 % of peak over the anneal",
            "weight_decay": 0.1, "grad_clip": 1.0, "skip_step_rule": "skip update if grad-norm > 3x its 100-step EMA; 3 consecutive skips -> rollback + advance data seed",
            "precision": "bf16 autocast, fp32 master weights, fp32 gradient reduce; FP8 piloted at 3B only",
            "attention": {"primary": "flash-attn 3 (hopper) flash_attn_varlen_func registered as an opaque torch custom op, pinned by commit",
                          "fallback": "FlexAttention with a block-causal document mask (compile-native, ~10-20 % slower backward)",
                          "packing": "cu_seqlens int32 per micro-batch, max_seqlen 4096, document-masked (no cross-document attention) in every phase"},
            "ladder": {"batches_tokens": {name: bsz for name, _, _, _, _, _, bsz in LADDER}, "lr_points": {name: nlr for name, _, _, nlr, _, _, _ in LADDER},
                       "duration_axis": {name: {"tokens": toks, "lr_points": nlr, "batch": bsz} for name, _, toks, nlr, _, bsz, _ in LADDER_DURATION},
                       "corpus": f"v0 corpus (>= {V0_TOKENS/1e12:.1f}T tokens, as-released per-dump-deduped FineWeb-Edu / score-2 / DCLM-baseline / Nemotron-CC medium-high / Stack v2 / FineMath shards in the frozen 131k tokenizer, ready at G1) for every ladder run and 1B/3B ablation; G2 fits are v0 fits; the 3B/300B rehearsal trains on the frozen mix",
                       "schedule": "main-run WSD + 10 % 1-sqrt decay on every run; LR ranked on post-decay loss; sqrt batch-LR correction; (LR, batch) swept jointly at 400M",
                       "lr_fit": "lr*(N) = a * N^-b, log-log least squares over 150M/400M/1B post-decay optima", "lr_fit_r2": G2_R2_REPORTED,
                       "lr_gate_3b": f"3-point log-LR parabola optimum at 3B/90B (fit x 0.67, 1.0, 1.5) within {G2_LR_OPT_RATIO_MAX}x of the extrapolated lr*(N); post-decay loss at the two bracketing LRs differs by <= {G2_LR_BRACKET_LOSS_PCT} %",
                       "lr_regime_note": f"the main run's {TOK_PRETRAIN/MC['nonembed']:,.0f} tokens/non-embedding-param is covered only by the stable/decay form (ladder spans {90e9/SHP_3B.counts()['nonembed']:.0f}-{300e9/SHP_3B.counts()['nonembed']:.0f} at 3B); the 3B/300B rehearsal is the last LR confirmation",
                       "loss_fit": "L(N, D) = E + A/N^0.34 + B/D^0.28, least squares on every ladder post-decay loss", "g2_3b_band_nats": G2_3B_BAND_NATS,
                       "g5_rule": f"|stable-phase val loss at D - L_stable(N, D)| <= {G5_BAND_NATS} nats at D = 1T / 4T / 8T on the 6-domain held-out set; L_stable(N, D) = L_postdecay(N, D / (1 - {DECAY_FRAC})) + delta, delta = stable-minus-postdecay gap logged per ladder run; anchored by the residual at the 3B/300B rehearsal's stable-phase loss at its decay start (270B); plus the per-source non-increase rule; with the data hot-swap the 1T gate uses the FineWeb-Edu + DCLM held-out subset only and the full-mix comparison moves to 2T",
                       "g5_band_nats": G5_BAND_NATS, "g5_anchor": "3B/300B rehearsal, stable-phase loss at 270B", "gradient_noise_scale": "B_simple every 10B tokens from the start of Block 2"},
            "epoch_proxy_ablation": {"arms": EPOCH_PROXY_ARMS, "tokens_per_arm": EPOCH_PROXY_TOKENS, "gpu_hours": round(W["abl_epoch"].gpu_hr), "usd": round(W["abl_epoch"].usd),
                                     "design": "1B x 300B on v0: arm A = 100B unique HQ (FineWeb-Edu + DCLM at plan proportions) x 3 epochs; arm B = 300B unique HQ + score-2 / Nemotron-CC medium-high x 1 epoch; same WSD; ranked on post-decay loss and the 8-task aggregate",
                                     "decision_rule_g2b": f"if B beats A by more than the 2-seed noise floor: cap FineWeb-Edu and DCLM at {EPOCH_PROXY_CAP_INCL_ANNEAL:.1f} epochs incl. anneal, raise score-2 to 1.0 epoch (+{SCORE2_FALLBACK_T:.2f}T), extension pool = Nemotron-CC medium-high"},
            "long_context": {"cp": CP_LC, "cp_groups": LC_GROUPS,
                             "kernel_path": "primary: torchtitan SDPA-based context parallelism (torch.distributed.tensor.experimental context_parallel, flash backend) with EOS-separated causal packing (no document mask) at 32k and 128k, compile-supported and in-tree; upside: ring-flash-attention zigzag varlen (FA3 hopper backend, document mask on), pinned by commit, tested on the dev node by W10; document masking is dropped for these two stages only",
                             "stage_32k": {"tokens": TOK_LC1, "seq": SEQ_LC1, "micro_batch": MB_LC1, "global_batch_tokens": BATCH_LC1, "steps": round(STEPS_LC1), "activation_checkpointing": "selective op-level", "mfu": A["mfu_longctx_32k"], "memory_GB": round(MEM_LC1, 2), "g3b_tok_s_per_gpu_min": TOKS_GATE_32K},
                             "stage_128k": {"tokens": TOK_LC2, "seq": SEQ_LC2, "micro_batch": MB_LC2, "global_batch_tokens": BATCH_LC2, "steps": round(STEPS_LC2), "activation_checkpointing": "full per-block", "mfu": A["mfu_longctx_128k"], "memory_GB": round(MEM_LC2_TOTAL, 2), "memory_GB_if_sac_op": round(MEM_LC2_SAC, 1), "g3b_tok_s_per_gpu_min": TOKS_GATE_128K},
                             "warmup_tokens": LC_WARMUP_TOKENS, "lr": LC_LR},
            "flops_per_token_4k": FPT_4K, "flops_per_token_32k": MODEL.flops_per_token(SEQ_LC1), "flops_per_token_128k": MODEL.flops_per_token(SEQ_LC2),
            "tok_per_s_cluster": round(TOK_PER_S_CLUSTER), "tok_per_s_per_gpu": round(TOK_PER_S_GPU), "step_time_s": round(STEP_TIME_S, 3),
            "throughput_gates_tok_s_per_gpu": {"g2_g3b_64_gpus_4k": TOKS_GATE_64, "g4_acceptance_2h_512_gpus": TOKS_GATE_512, "g5_rolling_512_gpus": TOKS_GATE_512, "g3b_32k": TOKS_GATE_32K, "g3b_128k": TOKS_GATE_128K,
                                               "mfu_definition": f"MFU = tokens/s x {FPT_4K:.4e} / 989e12 at seq 4096 (6ND + causal attention)", "torchtitan_mfu_ratio": round(TORCHTITAN_MFU_RATIO, 3),
                                               "shakedown": {"hours": SHAKEDOWN_H, "tokens_B": round(SHAKEDOWN_TOKENS / 1e9, 1)}},
            "checkpoint_interval_min": A["ckpt_interval_min"], "checkpoint_every_steps": round(CKPT_EVERY_STEPS),
            "checkpoint_full_GB": round(CKPT_FULL_GB, 1), "checkpoint_bf16_GB": round(CKPT_BF16_GB, 1), "checkpoint_per_gpu_MB": round(CKPT_PER_GPU_MB),
            "checkpoint_upload_MBps_aggregate": round(CKPT_UPLOAD_MBPS),
            "permanent_checkpoint_TB": round(CKPT_PERM_TB, 1), "permanent_checkpoints": {"full": N_PERM_FULL, "bf16": N_CKPT_EVALS},
            "rolling_24h_checkpoint_TB": round(CKPT_ROLLING_TB, 1), "retained_checkpoint_TB": round(CKPT_RETAINED_TB, 1),
            "validation": {"inloop_every_steps": VAL_EVERY_STEPS, "inloop_tokens": VAL_TOKENS_INLOOP, "per_source_every_tokens": PER_SOURCE_VAL_EVERY_TOK, "fraction_of_step_time": round(VAL_FRAC_TOTAL, 4)},
            "anneal_start_rule": f"anneal starts at Block 2 day {ANNEAL_START_DAY:.1f} if >= {ANNEAL_FLOOR_T:.1f}T stable tokens are reached; stable tokens = whatever is reached by then (extension pool above {TOK_STABLE/1e12:.1f}T); below the floor exercise option 1 (by day {OPTION1_DEADLINE_DAY}) or option 2 (by day 42) instead",
            "anneal_token_floor": A["anneal_token_floor"], "mfu_at_floor": round(MFU_AT_FLOOR, 3), "stable_days_lost_at_floor": round(DAYS_LOST_AT_FLOOR, 1),
        },
        "compute": {
            "n_gpus": N_GPUS, "n_nodes": N_NODES, "hot_spare_nodes": HOT_SPARE_NODES, "block2_gpus": BLOCK2_GPUS,
            "mfu_main": A["mfu_main"], "mfu_main_6nd_basis": round(A["mfu_main"] * 6 * MC["total"] / FPT_4K, 3), "mfu_upside": MFU_UPSIDE, "mfu_gate_64_gpus": MFU_GATE_64,
            "framework_gate_g2": "run the 10B config on the same 64 GPUs in Megatron-Core/NeMo (bf16, TE kernels, TP=1) for one afternoon; if it beats torchtitan by >= 3 MFU points (>= 470 tok/s/GPU) the framework is decided at G2 and two engineer-weeks of checkpoint / serving export conversion are booked (sensitivity table)",
            "overhead_main": A["overhead_main"],
            "overhead_breakdown": {k: round(v, 4) for k, v in OVERHEAD_BREAKDOWN},
            "main_run_flops": MAIN_FLOPS, "main_run_6nd_flops": MAIN_6ND, "main_run_gpu_hours_ideal": round(MAIN_RUN_IDEAL),
            "main_run_gpu_hours": round(MAIN_RUN_GPU_HR), "main_run_days": round(MAIN_RUN_DAYS, 1),
            "stable_days": round(W["stable"].days, 1), "anneal_days": round(W["anneal"].days, 1),
            "anneal_select_days": round(W["anneal_select"].days, 2), "lc32k_days": round(W["lc32k"].days, 2), "lc128k_days": round(W["lc128k"].days, 2),
            "gpu_hours_per_T_stable": round(GPU_HR_PER_T), "usd_per_T_stable": round(USD_PER_T),
            "block2": {"days": BLOCK2_DAYS, "acceptance_days": ACCEPT_DAYS, "need_days": round(BLOCK2_NEED_DAYS, 1), "slack_days": round(BLOCK2_SLACK_DAYS, 1),
                       "slack_tokens_T": round(SLACK_TOKENS / 1e12, 2), "anneal_start_day": round(ANNEAL_START_DAY, 1),
                       "stable_expected_T": round(STABLE_EXPECTED_T, 2), "stable_T_at_mfu_42": round(STABLE_T_AT_UPSIDE, 2), "stable_T_at_mfu_36": round(STABLE_T_AT_LOW, 2),
                       "mfu_for_design_point_12T": round(MFU_FOR_DESIGN, 3), "option1_trigger_mfu": round(MFU_OPTION1_TRIGGER, 3), "option1_deadline_block_day": OPTION1_DEADLINE_DAY,
                       "stable_T_at_option1_deadline": round(TOK_AT_OPTION1_DEADLINE_T, 2),
                       "idle_day_usd": round(BLOCK2_IDLE_DAY_USD), "option_week_usd": round(OPTION_WEEK_USD),
                       "option2_week_usd": round(OPTION2_WEEK_USD), "option2_price": OPTION2_PRICE, "option_week_tokens_T": round(OPTION_WEEK_TOKENS_T, 2),
                       "options_in_base_plan": False, "acceptance_billed": True,
                       "token_milestones_block_day": {"1T": round(TOK_AT_DAY[1e12], 1), "4T": round(TOK_AT_DAY[4e12], 1), "8T": round(TOK_AT_DAY[8e12], 1)}},
            "workloads": {k: {"block": w.block, "gpu_hours_ideal": round(w.gpu_hr_ideal), "gpu_hours": round(w.gpu_hr), "gpus": w.gpus, "days": round(w.days, 2), "usd": round(w.usd)} for k, w in W.items()},
            "blocks": [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in b.items()} for b in block_rows],
            "reserved_gpu_hours": RESERVED_GPU_HR, "total_gpu_hours_bought": TOTAL_GPU_HR_BOUGHT, "attributed_gpu_hours": round(USED_GPU_HR), "utilisation": round(UTIL_OVERALL, 3),
            "rounding_note": "rows rounded independently; totals from unrounded values",
            "memory_per_gpu_GB": {k: round(v, 2) for k, v in MEM}, "memory_total_GB": round(MEM_TOTAL, 2), "memory_headroom_GB": round(MEM_HEADROOM, 2),
            "memory_per_gpu_GB_128k": {k: round(v, 2) for k, v in MEM_LC2}, "memory_total_GB_128k": round(MEM_LC2_TOTAL, 2), "memory_total_GB_32k": round(MEM_LC1, 2),
            "parallelism": {"fsdp2_hsdp": {"shard": SHARD, "replicate": REPLICATE}, "tp": 1, "pp": 1, "cp_longctx": CP_LC,
                            "longctx_mesh": {"cp": CP_LC, "dp_shard": SHARD, "dp_replicate": N_GPUS // CP_LC // SHARD},
                            "activation_checkpointing": "selective op-level (4k, 32k); full per-block (128k)", "compile": "per TransformerBlock, fullgraph"},
            "mfu_replacement_rule": "mfu_main = G2 64-GPU measurement - 0.02, set before the W12 freeze and the Block 2 fit regenerated; the budget is built at 0.38 and never re-based upward (extra MFU becomes stable tokens through the date rule); G2 variants: bf16 reduce with fp32 accumulate, dp_shard 16, grad-accum 1 (4M) vs 2 (8M), inductor max-autotune-no-cudagraphs",
            "comm_per_step_s": {"all_gather_bf16_per_micro_step": round(T_AG_MICRO, 3), "all_gather_bf16": round(T_AG, 3), "reduce_scatter_fp32_per_micro_step": round(T_RS_MICRO, 3), "reduce_scatter_fp32": round(T_RS, 3),
                                "all_reduce_fp32_ib": round(T_AR, 3), "all_reduce_fp32_ib_realistic": round(T_AR_REAL, 3), "total_at_line_rate": round(COMM_TOTAL_S, 3),
                                "all_reduce_share_of_step": round(AR_SHARE_OF_STEP, 3), "all_reduce_share_of_step_at_4M": round(AR_SHARE_OF_STEP_4M, 3),
                                "non_overlappable_tail": round(T_AR_TAIL, 3), "tokens_per_gpu_per_step": TOK_PER_GPU_STEP},
            "interruptions_expected": round(INTERRUPTS, 1), "lost_min_per_interruption": LOST_PER_INTERRUPT_MIN,
            "hot_spare_policy": "Slurm reservation with preemption: the main job takes spare 1 automatically on a second failure; eval jobs requeue to the dev node",
        },
        "cost": {
            "total_budget_usd": TOTAL_BUDGET, "budget_lines": {k: v for k, v in budget},
            "compute_total_usd": round(COMPUTE_USD), "team_total_usd": round(TEAM_USD), "contingency_usd": CONTINGENCY, "contingency_pct": round(100 * CONT_PCT, 1),
            "team_fte": TEAM_FTE, "team_usd_per_week": round(TEAM_USD_PER_WEEK), "team": [{"role": r, "hc": hc, "loaded_usd_yr": ld, "months": m, "start_week": start, "usd": round(u)} for r, hc, ld, m, u, start in team_rows],
            "team_rounding_note": "rows rounded independently; total from unrounded values",
            "data_contractor": {"usd": round(DATA_CONTRACTOR_USD), "months": DATA_CONTRACTOR_MONTHS, "weeks": "W1-W13", "planned": True, "scope": "downloads, 131k tokenizer + v0 corpus, PII / opt-out, provenance manifest (the data engineer owns dedup + quality only)",
                                "extension_1_month_usd": round(DATA_CONTRACTOR_EXT_USD)},
            "data_slip_usd": {"2_weeks_float_consumed": round(DATA_SLIP_2WK_USD), "4_weeks_float_plus_contract_window": round(DATA_SLIP_4WK_USD), "per_idle_block2_day": round(BLOCK2_IDLE_DAY_USD)},
            "sensitivities_usd": {k: round(v) for k, v in SENS.items()},
            "contingency_coverage_usd": {"price_2.60_plus_option1_plus_one_idle_week": round(COVERED), "price_2.60_plus_option1_plus_4wk_slip": round(COVERED_SLIP),
                                         "price_2.60_plus_both_options_plus_4wk_slip": round(NOT_COVERED), "price_2.40_plus_both_options_plus_4wk_slip": round(COVERED_AT_240)},
            "procurement": {"loi_by": "W2", "signed_by": "W4", "block2_start_fixed_by": "W6", "walk_away_price": 2.40, "target_price": RES, "master_contract": "913,920 reserved GPU-h over W1-W40 (dev node to W40; the 64/528/48-GPU blocks end W30)"},
            "serving_usd_per_M_output_tokens": {"reserved": round(SERVING_USD_PER_M_TOK, 3), "on_demand": round(SERVING_USD_PER_M_TOK_OD, 3)},
            "compute_only_counterfactual": {"tokens_uncapped_T": round(CO_TOKENS_UNCAPPED / 1e12, 1), "tokens_capped_T": CO_TOKENS_CAPPED / 1e12, "capped_days": round(CO_CAPPED_DAYS, 1), "left_usd": round(CO_LEFT_USD)},
        },
        "timeline": {
            "weeks_total": A["weeks_total"], "months": round(A["weeks_total"] / 52 * 12, 1), "weeks_total_note": "includes the W13-14 pre-block float, the 2-week contract start window and the W39-40 buffer",
            "block1_weeks": "W7-W14", "pre_block_float": "W13-W14",
            "block2_start_week": A["block2_start_week"], "block2_weeks": "W15-W22", "contract_start_window_weeks": A["contract_start_window_weeks"],
            "block3_weeks": "W23-W30", "serving_hardening": "W31-W34", "pilot_handoff": "W35-W38", "end_buffer": "W39-W40",
            "anneal_start": week_day(ANNEAL_START_DAY), "milestones": {"1T": week_day(TOK_AT_DAY[1e12]), "4T": week_day(TOK_AT_DAY[4e12]), "8T": week_day(TOK_AT_DAY[8e12])},
            "option1_deadline": week_day(OPTION1_DEADLINE_DAY),
            "data_readiness": {"tokenizer_frozen": "W5 d1 (trained W3-4; digit / whitespace tests at G1 still apply)",
                               "v0_corpus": f">= {V0_TOKENS/1e12:.1f}T tokens tokenized by end of W6 (G1); every ladder run and 1B/3B ablation trains on v0",
                               "dedup_threshold_ablation_corpora": f"W5-6 on the CPU partition: 10-dump subset at Jaccard {' / '.join(str(t) for t in DEDUP_THRESHOLDS)} ({DEDUP_ABL_DAYS:.1f} days)",
                               "w3_measurement": f"domain-stratified {W3_SAMPLE_FRAC:.0%} sample across all dumps of the four CC sources ({W3_MEASURE_DAYS:.2f} days)",
                               "production_pass_1_due": "W10 d3", "production_pass_2_due": "W11 d7",
                               "g3a": f"tokenization of the frozen mix >= {G3A_TOKENS/1e9:.0f}B tokens by W11 d7 (globally shuffled) so the 3B/300B rehearsal starts W12 d1; if G3a slips the rehearsal starts on v0 and the G5 anchor is re-based at the 1T checkpoint",
                               "quality_classifier": "0.5B classifier (labels: public FineWeb-Edu Llama-3-70B annotations 450k + DCLM OH-2.5 / ELI5 positives) is NOT on the freeze path; W12 uses the shipped FineWeb-Edu score and DCLM fastText probability; the classifier runs W13 d4-W14 on Block 1 (dev-node overflow) for the anneal pools only, due W18",
                               "held_out_suite": "research engineer builds a private 10-task held-out suite (>= 500 items each, never used in ablations, hashed and decontaminated) due W18; decides the anneal mix at G5c",
                               "human_preference_pairs": f"{HUMAN_PAIRS:,} pairs compare outputs of the W23 d4 SFT checkpoint; ordered W23 d5, delivered 10k/week (W24 d5, W25 d5), used for the reward model; W13-22 vendor work = {EXPERT_SFT:,} expert SFT examples only"},
        },
        "data": {
            "unique_available_T": round(UNIQUE_AVAILABLE_T, 3), "unique_available_source_tokenizer_T": round(UNIQUE_AVAILABLE_SRC_T, 3),
            "cc_derived_unique_source_tokenizer_T": round(CC_UNIQUE_SRC_T, 3), "cc_derived_raw_per_dump_source_tokenizer_T": round(CC_RAW_SRC_T, 2), "tokenizer_shrink_web": TOK_SHRINK,
            "unique_touched_T": round(UNIQUE_TOUCHED_T, 3), "avg_epochs": round(AVG_EPOCHS, 2),
            "max_epochs_stable": round(MAX_EPOCHS_STABLE, 2), "max_epochs_incl_anneal": round(MAX_EPOCHS_INCL_ANNEAL, 2), "max_epochs_subpool_incl_stable": round(MAX_EPOCHS_SUBPOOL, 2),
            "epoch_caps": {"stable_web": EPOCH_CAP_STABLE_WEB, "incl_anneal_any_source_or_subpool": EPOCH_CAP_INCL_ANNEAL},
            "web_used_T": round(WEB_USED_T, 3), "web_unique_T": round(WEB_UNIQUE_T, 3),
            "capacity_T": {"all_rows_at_cap": round(CAP_ALL_T, 2), "hq_rows_at_cap": round(CAP_HQ_T, 2), "hq_rows_at_cap_uniques_25pct_low": round(CAP_HQ_SHRUNK_T, 2), "score2_to_1_epoch_adds": round(SCORE2_FALLBACK_T, 2)},
            "extension_pool": {"rows": [DATA_ROWS[i]["source"] for i in EXTENSION_ROWS], "rule": "stable tokens beyond the 9.9T plan are drawn from the HQ web rows in proportion to their room below the 3-epoch stable cap; synthetic, Cosmopedia, filler and multilingual stay at their planned counts; the dataloader's mixture weights switch at 9.9T; replaced by score-2 + Nemotron-CC medium-high if the G2b epoch-proxy ablation decides for unique tokens",
                               "capacity_T": round(EXTENSION_CAPACITY_T, 3), "needed_at_mfu_42_T": round(EXTENSION_NEEDED_T, 3), "tokens_at_mfu_42_T": {k: round(v, 3) for k, v in EXT_TOKENS_AT_UPSIDE.items()},
                               "epochs_at_mfu_42_stable_incl_anneal": EXT_EPOCHS_AT_UPSIDE},
            "g3_gate": {"rule": "for every source: measured unique tokens in our tokenizer >= max(planned stable tokens / cap_stable, (stable + anneal) / 4); planned tokens stand and epochs are recomputed when it holds; a failing row is clipped to measured x cap and the score-2 filler absorbs the difference (dr_calc.py prints the re-solved mix, writes decision_record.g3_resolved.json and exits 2 for sign-off; exit 1 if even the re-solved mix breaks a cap)",
                        "measured_unique_file": "measured_unique.json (absent = planning values)", "measured_sources": sorted(MEASURED_UNIQUE), "failed_sources": G3_FAILED,
                        "near_dup_check": "1M sampled docs queried against the full-corpus LSH index; <= 1 % with a neighbour at Jaccard >= 0.8",
                        "w3_measurement": f"domain-stratified sample across ALL CC dumps: keep every document whose hash(registered domain) mod {round(1/W3_SAMPLE_FRAC)} == 0 in every dump of FineWeb-Edu, score-2, DCLM-baseline and Nemotron-CC HQ real ({W3_SAMPLE_FRAC:.0%} of {CC_TEXT_GB:,.0f} GB), then the full MinHash 5-gram/112/14x8 on the slice ({W3_MEASURE_CORE_HRS:,.0f} core-h, {W3_MEASURE_DAYS:.2f} days on the 768-core partition); measured removal rates for all four CC sources written to measured_unique.json; the synthetic slice is derived from the real-text survival; recrawls stay together so cross-dump and cross-source rates are unbiased (cross-domain syndication biases a few points low)",
                        "w3_measurement_g1_requirement": "measured rates published for all four CC sources (not 'per-source removal rates')",
                        "why_not_per_dump": "a 4-of-~100-dump sample catches a page recrawled in k dumps only if >= 2 copies fall in the sample: P = 0.001 (k=2), 0.012 (k=5), 0.049 (k=10), 0.18 (k=20); it reads 5-15 % where the global pass removes 30-70 %",
                        "fallback_order": ["re-solve the mix at the caps", "score-2 tier to 1.0 epoch", "Nemotron synthetic to 12 % of stable", "date-driven WSD cut, never below the 9.0T anneal floor"]},
            "tokenized_tokens": TOKENIZED_TOKENS, "tokenized_TB_uint32": round(TOKENIZED_TB, 1),
            "pipeline": {"g1_gb_per_h": G1_GB_PER_H, "partition_gb_per_h": round(PIPELINE_GB_PER_H), "days_per_pass": round(PIPELINE_DAYS_PER_PASS, 1), "raw_text_GB": round(TEXT_GB), "cc_text_GB": round(CC_TEXT_GB),
                         "pre_production_core_hours": {"w3_measurement": round(W3_MEASURE_CORE_HRS), "dedup_threshold_corpora": round(DEDUP_ABL_CORE_HRS), "v0_tokenization": round(V0_CORE_HRS)},
                         "cpu_need_core_hours": round(CPU_NEED_CORE_HRS), "cpu_booked_core_hours": CPU_CORE_HRS, "g3a_tokens": G3A_TOKENS},
            "generator_terms": {k: {"generator_and_output_terms": g, "status": s} for k, (g, s) in GENERATOR_TERMS.items()},
            "counsel_w3_memo": "positions on (a) the Llama-output naming clause, (b) OpenAI-output training clauses, (c) Qwen attribution, (d) CC-BY-SA 4.0 for weights; the G3 manifest signature certifies the generator column",
            "stable_mix": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in DATA_ROWS],
            "anneal_mix": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()} for r in ANNEAL_ROWS],
            "longctx_mix": [{"component": n, "share": s, "tokens_B_32k": round(s * TOK_LC1 / 1e9, 1), "tokens_B_128k": round(s * TOK_LC2 / 1e9, 1)} for n, s in DATA_LC],
            "human_data": {"human_pairs": HUMAN_PAIRS, "usd_per_pair": HUMAN_PAIR_USD, "vendor_quotes_by": "W3", "onpolicy_judge_pairs": ONPOLICY_PAIRS, "expert_sft_examples": EXPERT_SFT, "usd_per_expert_example": EXPERT_SFT_USD},
            "dedup": {"minhash": "5-gram, 112 hashes, 14 bands x 8 rows, Jaccard ~0.8", "scope": "global, union level, across CC dumps and sources; keep the NEWEST copy",
                      "cross_source_order": "FineWeb-Edu <- DCLM <- Nemotron-CC", "decontamination": "13-gram against every eval set"},
            "opt_out": "robots.txt at crawl time (inherited from the FineWeb/DCLM/Nemotron-CC crawls) plus the HF/Spawning opt-out list, refreshed weekly; SWH opt-out list for The Stack v2 with per-file attribution",
            "licence_positions": "counsel's W3 memo states the position on CC-BY-SA 4.0 (Wikipedia) for model weights; The Stack v2 attribution kept in the provenance manifest",
        },
    }


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    # a failed G3 gate writes the re-solved plan beside the canonical JSON, never over it, and exits 2 for sign-off
    out_json = os.path.join(here, "decision_record.g3_resolved.json" if G3_FAILED else "decision_record.json")
    s_ = summary()
    if "--json" in sys.argv:
        print(json.dumps(s_, indent=1))
    else:
        print(md())
        with open(out_json, "w") as f:
            json.dump(s_, f, indent=1)
        print(f"\nWrote {out_json}")
    if G3_FAILED:
        print(f"G3 GATE FAILED: {', '.join(G3_FAILED)} below the G3 minimum; re-solved mix written to {out_json} (exit 2)", file=sys.stderr)
        sys.exit(2)
    sys.exit(0)
