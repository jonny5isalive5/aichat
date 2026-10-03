# Decision Record: 10B dense LLM program (canonical, binding for every section)

Date: 2026-10-03 (assumptions are "as of mid-2026"). Every number below is produced by `dr_calc.py` in this
directory (`python3 dr_calc.py` prints the tables and writes `decision_record.json`). One-line arithmetic follows
each derived number. Section writers derive from these numbers and never invent competing ones. Tables round rows
independently; totals come from unrounded values, so a displayed sum may differ from the displayed total by 1-2 units.

Provenance: built from the cost_first proposal (judges' winner, 2 of 3) with the judges' corrections applied
(QK-norm before RoPE; one date-driven anneal-start rule; every 30-min checkpoint uploaded; validation 1.0 %;
human data re-priced; in-run evals pinned to one spare node; reserved price raised to 2.20 under one master
contract; 4-day acceptance; 2-week start window; pre-block float) and the grafts the judges ranked highest
(3B/300B rehearsal, anneal-mix selection at ~8T, 128k stage with staged RoPE, doc-masked varlen packing,
per-source validation loss, skip-step rule, bit-identical resume gates, data hot-swap, standing dev node,
fractional counsel, local open-weight judge for on-policy pairs). Revision 2 applies the verifiers' findings:
global dedup booked before counting tokens with a per-source G3 gate and 3-epoch caps; linear-in-steps batch ramp
from 2,097,152; ladder batches, duration axis and post-decay ranking; FA3 varlen custom op named as the attention
path; 128k stage on full activation checkpointing with its own memory table; anneal token floor and a second
+1-week option; MFU replaced by the G2 measurement before the W12 freeze; named, measurable gates. Revision 3 applies the
second round of verifier findings: the plan is re-based at MFU 0.38 (the acceptance gate value, 6ND basis 0.355) with 11.0T
planned tokens inside the 8-week block and 12.0T as the design point the date-driven anneal rule reaches at the 0.40 gate
(neither option is in the base plan; contingency 15.8 %); the W3 dedup measurement is a domain-stratified sample across every
CC dump of all four CC sources (a per-dump sample is blind to cross-dump recrawls); G5 is scored against stable-phase curves
(L_stable = L_postdecay + the measured ladder gap), never post-decay ones; a v0 corpus (>= 1.5T tokens at G1) feeds every
ladder run and ablation, the dedup-threshold corpora move to W5-6 on CPU, the 0.5B classifier leaves the freeze path, and gate
G3a (>= 300B frozen tokens by W11 d7) protects the W12 rehearsal start; every throughput gate is stated in tokens/s/GPU; the
global batch is 8M by default (grad-accum 2, two-phase ramp, warmup 8B tokens); a third 3B LR and a parabola gate replace the
R^2 gate, with the main-run LR clamped to [3e-4, 6e-4]; the long-context kernel path is decided (SDPA-based CP, EOS packing)
with ring-flash-attention as upside; a generator-terms column covers Llama / OpenAI / Qwen output clauses; an epoch-proxy
ablation (1B x 300B, repeated HQ vs unique) with a G2b decision rule; the data contractor is a planned 3-month line and the
data slip is risk #3; G6 has two target bands; cu_seqlens is padded so the batch ramp recompiles 34 times, never per document
count; the held-out suite, classifier labels and the human-pair ordering are dated and owned.

## Key numbers

| Item | Value |
|---|---|
| Model shape | d_model 4096, 40 layers, 32 heads / 8 KV heads, head_dim 128, SwiGLU 14336, vocab 131,072, untied |
| Params | 9,798,236,160 total (9.798B); 8,724,494,336 non-embedding (8.724B) |
| Tokens | 11.0T planned pretrain (9.9T stable + 1.1T anneal, 10 % decay) at seq 4,096 and MFU 0.38; 12.0T design point lands at MFU 0.404, 12.5T at 0.42 (date-driven anneal rule, 0.30T stable per MFU point, extension pool within the epoch caps); + 50B at 32k + 20B at 128k; + 200B anneal-mix selection |
| Data | 8.73T unique tokens in our tokenizer (9.91T after global dedup in the sources' tokenizers; web rows x 0.87 shrink, code/math/papers/wiki/books/Cosmopedia at 1.0); avg 1.62 epochs; caps 3 epochs stable / 4 incl. anneal; max 2.73; extension pool 2.53T for the upside |
| GPUs | 512 H100 SXM 80 GB compute (64 nodes) + 16 hot spare (2 nodes) = 528 reserved for Block 2 |
| MFU | 0.38 planning value over 6ND + causal attention (= 0.356 on the 6ND basis) = 6,000 tok/s/GPU, the acceptance gate on 512 GPUs; G2 gate 6,300 tok/s/GPU (0.40) on 64 GPUs; planning := G2 measurement minus 0.02 before the W12 freeze, never re-based upward; 0.42 is upside (12.5T), not the plan |
| USD per GPU-hour | 2.20 reserved (one master contract, all blocks, W1-W40); 2.90 on-demand; 1.50 spot (never the main run) |
| Main run | 602,646 GPU-h (overhead 1.18) = 49.0 days on 512 GPUs (stable 44.1 + anneal 4.9) |
| Compute USD | 2,049,600 (41.0 %) for 927,360 GPU-h bought, 829,413 attributed (89 %) |
| Team USD | 1,785,833 (7.7 FTE loaded incl. the 3-month data contractor, 35.7 %) |
| Contingency USD | 788,129 (15.8 %) |
| Total | 5,000,000 |
| Timeline | 40 weeks = 9.2 months (includes the W13-14 pre-block float, the 2-week contract start window and the W39-40 buffer); Block 2 W15-22 |

## 1. Budget interpretation

Decisions:
- USD 5,000,000 is all-in: GPUs, CPU data cluster, storage, egress, team, human data, evaluation, serving pilot,
  software, contingency. Nothing is outside the budget.
- Compute is budgeted as reserved blocks paid whether used or not (cash view) and separately attributed per
  workload (utilisation view), so idle reserved hours are visible. Block 2 acceptance days are billed.
- Contingency is the residual and must stay >= 15 % in the base plan, which is built at the planning MFU 0.38 with
  neither Block 2 option exercised. It lands at 15.8 % and is released only by the program lead against a written
  change request; the pre-authorised first calls are listed in the sensitivity table.
- The 2.40 walk-away price is load-bearing: at 2.60 the contingency no longer covers both +1-week options plus a
  4-week program slip (966,972 > 788,129); at 2.40 it does (784,188, remainder 3,941).

| Line item | USD | % of 5.0M | One-line arithmetic |
|---|---|---|---|
| GPU compute: 4 reserved blocks + on-demand serving tail (incl. 16 hot-spare GPUs) | 2,049,600 | 41.0 | 118,272 + 189,235 + 1,561,190 + 141,926 + 38,976 (block table, section 5; rows rounded) |
| Team (7.7 FTE, loaded; incl. the 3-month data-pipeline contractor) | 1,785,833 | 35.7 | sum of HC x loaded/yr x months/12 (section 8) |
| Data processing: CPU cluster + RAM nodes | 54,513 | 1.1 | 768 cores x 8 wk x 168 h x 0.045 = 46,449; + 3 RAM nodes x 4 wk x 168 h x 4.00 = 8,064 |
| Storage: object store + parallel FS | 67,181 | 1.3 | 913 TB-months x 21 = 19,181; + 120 TB x 5 months x 80 = 48,000 |
| Egress and DR replication | 4,744 | 0.1 | 94.9 TB x 50 (DR copies of 45.1 TB tokens + 20 TB ckpts, 500 x 19.6 GB model downloads, 20 TB misc) |
| Human data, evaluation, red team, judge API | 220,000 | 4.4 | 20,000 human pairs x 5.00 + 2,000 expert SFT x 25 + 2,000 human evals x 10 + red team 25,000 + judge/synthetic API 25,000; two vendor quotes by W3 |
| Serving pilot non-GPU infra (gateway, LB, logging, 2 CPU nodes) | 15,000 | 0.3 | 20 weeks x 750 |
| Software / SaaS (W&B 6k, CI 3k, paging 3k, HF 3k) | 15,000 | 0.3 | counsel moved to the team table |
| Contingency (residual) | 788,129 | 15.8 | 5,000,000 - 4,211,871 |
| **Total** | **5,000,000** | **100.0** | |

Sensitivities the contingency must cover (pre-authorised, in this order): price 2.60 instead of 2.20 on the
913,920 reserved hours = USD 365,568 (+0.10 = 91,392); effective MFU below 0.371 (the 9.9T plan missed by more than
the 1.3-day slack) -> exercise option 1 (+1 week of Block 2 at 2.20, by block day 21) = USD 195,149; one week of idle
Block 2 (27,878 per day) = 195,149; all three together = 755,866, leaving 32,263. Also pre-authorised: option 2 (+1
week at <= 2.40, exercisable by block day 42, USD 212,890) when the anneal token floor would otherwise bind; +1 month
of the data-pipeline contractor (USD 28,333) if G3 slips past W12; Block 1's first two weeks on on-demand (USD 15,053)
if contract signing slips past W4; two engineer-weeks of checkpoint / serving export conversion (USD 15,000) if G2
decides for Megatron-Core. Needing a change request: a two-week slip beyond the contract window (390,298), a 4-week
program slip (193,366 = 4 x 45,385 team + 4 x 2,957 dev node), doubling human pairs (100,000), preference pairs at
USD 15 instead of 5 (200,000). Price 2.60 + option 1 + a 4-week slip = 754,082 still fits; 2.60 + both options + a
4-week slip = 966,972 does not (short by 178,843), which is why 2.40 is the walk-away price. Option 1 is never used to
buy the 12.0T design point at the planning MFU: at 0.38 that would take contingency to 592,980 (11.9 %), below the
floor; the design point is reached by MFU above plan, not by cash.

Compute-only counterfactual: USD 4,250,000 (after a 15 % reserve) / 2.20 = 1,931,818 GPU-h; after the same support
work (294,797 GPU-h incl. 30 % idle) the main run would get 29.9T tokens at MFU 0.38. Unique public data caps the
useful run at 15T (HQ sources at their 3-epoch caps = 14.4T + the 1.1T anneal; beyond it the marginal token is a 4th
epoch or score-2 filler): 821,790 GPU-h, 66.9 days on 512 GPUs, USD 1,807,938; USD 1,793,509 would be returned or
would re-open the model-size decision, which is outside this DR's ~10B scope.

## 2. Model specification

Decisions:
- 9.798B total, 8.724B non-embedding: the low end of the 9.5-11B window, because training and serving cost scale
  with N while quality at this size is set by data and tokens. Every component has production precedent.
- d_model 4096 x 40 layers (aspect ratio 102), head_dim 128, GQA 8 KV heads: H100-shaped GEMMs, KV cache 4x smaller
  than MHA at serving.
- Vocab 131,072 (2^17): multiple of 256, shards evenly across 8/16/64 ranks, FP8-friendly, 10-15 % fewer tokens per
  byte than a 64k vocab on code and multilingual text.
- QK-norm before RoPE and z-loss 1e-4: both nearly free; each avoided divergence saves a multi-day rollback.
- Attention runs through flash-attn 3's `flash_attn_varlen_func` wrapped as an opaque torch custom op (torch SDPA has
  no FA3 backend and no cu_seqlens argument); FlexAttention with a block-causal document mask is the fallback.

| Field | Value |
|---|---|
| d_model / n_layers | 4096 / 40 |
| n_heads / n_kv_heads / head_dim | 32 / 8 (GQA 4:1) / 128 |
| ffn_hidden (SwiGLU) | 14336 (= 56 x 256) |
| vocab_size | 131,072 byte-level BPE (256 byte tokens + 64 reserved specials inside the count) |
| Embeddings | untied (input embedding and lm_head are separate 131072 x 4096 matrices) |
| Norm | pre-norm RMSNorm, eps 1e-5, fp32 compute; no biases anywhere |
| QK-norm | RMSNorm over head_dim on q and k, learnable scale, applied BEFORE RoPE (a learned scale after rotation breaks the relative-position property) |
| RoPE theta | 500,000 for 4k pretraining; 4,000,000 for the 32k stage; 16,000,000 for the 128k stage |
| z-loss | 1e-4 x log(Z)^2 |
| Seq len | 4,096 stable and anneal; 8,192 post-training; 32,768 then 131,072 long-context stages |
| Attention | primary: flash-attn 3 (hopper) `flash_attn_varlen_func`, registered as an opaque custom op so each TransformerBlock compiles with fullgraph=True, pinned by commit; fallback: FlexAttention block-causal document mask (compile-native, ~10-20 % slower backward on H100); document-masked packing in every phase (no cross-document attention); the dataloader emits cu_seqlens as int32 per micro-batch with max_seqlen 4,096 |
| Init | trunc-normal std 0.02 (+-3 sigma) for linears and embedding; o_proj and down_proj std 0.02 / sqrt(2 x 40) = 0.00224; lm_head std 4096^-0.5 = 0.0156; RMSNorm weights 1.0 |
| Dropout | none |

| Component | Formula | Params |
|---|---|---|
| Attention per layer (q, k, v, o) | 4096*4096 + 2*4096*1024 + 4096*4096 | 41,943,040 |
| MLP per layer (SwiGLU gate/up/down) | 3*4096*14336 | 176,160,768 |
| Norms per layer (attn_norm, mlp_norm, q_norm, k_norm) | 2*4096 + 2*128 | 8,448 |
| Per layer | sum | 218,112,256 |
| All 40 layers | 40*218,112,256 | 8,724,490,240 |
| Final RMSNorm | 4096 | 4,096 |
| Input embedding | 131072*4096 | 536,870,912 |
| LM head (untied) | 131072*4096 | 536,870,912 |
| **Total** | | **9,798,236,160 (9.798B)** |
| Non-embedding | | 8,724,494,336 (8.724B) |
| FLOP-bearing (non-embedding + lm_head) | | 9,261,365,248 (9.261B) |

FLOP convention: N = 9.798B (total) in 6ND. This over-states matmul FLOPs by 5.8 % (6 x 9.261B is exact); the margin
absorbs the FlashAttention backward recompute and makes every GPU-hour number conservative.

## 3. Token budget and data plan

Decisions:
- 11.0T planned pretraining tokens = 9.9T stable + 1.1T anneal (10 % decay fraction) at the planning MFU 0.38 inside
  the 8-week block, plus 50B at 32k and 20B at 128k. 12.0T is the design point the data plan is sized for: the
  date-driven anneal rule turns every MFU point above 0.38 into 0.30T of stable tokens, so 12.0T lands at MFU 0.404
  (the 0.40 gate value within rounding) and 12.5T at 0.42, drawn from the extension pool inside the epoch caps.
  Chinchilla-optimal is 20N = 196B; we train 56x that (1,123 tokens per parameter) because a served model is
  inference-dominated and inference cost scales with N, not D.
- The Chinchilla loss fit (E 1.69, A 406.4, B 410.7, alpha 0.34, beta 0.28) is used only as a marginal-value proxy:
  L(8T) 1.9531, L(11T) 1.9445, L(12T) 1.9423, L(15T) 1.9369. 8T -> 11T buys 0.0085 nats for USD 361,588 of stable
  compute; 11T -> 12T buys 0.0022 nats and costs nothing above MFU 0.404 (USD 120,529 per T otherwise); 12T -> 15T
  buys 0.0054 nats for USD 361,588 and pushes HQ web to its epoch caps. 11-12T is the knee for this data at this
  compute.
- Overlap honesty, booked before any token is counted: FineWeb-Edu and its score-2 tier are only per-dump deduped
  and DCLM-baseline only Bloom-filter / per-global-shard deduped, while Nemotron-CC was globally deduped upstream
  (its global fuzzy + exact dedup of all English CC 2013-2024 left ~4.4T original tokens across every quality
  bucket; FineWeb's global cross-dump dedup collapsed ~20T to ~4T). The plan therefore runs one global MinHash
  (5-gram, 112 hashes, 14 bands x 8 rows, Jaccard ~0.8) at the union level, across CC dumps and across sources
  (order FineWeb-Edu <- DCLM <- Nemotron-CC), keeping the NEWEST copy (FineWeb's "global dedup hurt" finding came
  from keeping the oldest), and plans with these losses: FineWeb-Edu 30 %, DCLM 50 %, Nemotron-CC real 50 %,
  score-2 tier 45 %. CC-derived real text then holds 5.615T unique tokens in the sources' tokenizers against a
  per-dump (raw) count of 10.30T for the same four rows. Nemotron synthetic rephrases are not MinHash duplicates
  but carry the same information: only the slice whose source document survived is used (its loss is derived from
  the measured real-text survival), 8.8 % of stable.
- Tokenizer honesty: web sources are quoted in ~50k tokenizers; our 131k BPE yields 10-15 % fewer tokens, so every
  web count is multiplied by 0.87 before planning (code, math, papers, wiki, books, Cosmopedia at 1.0). Planning
  unique = 9.91T in the sources' tokenizers = 8.73T in ours.
- Epoch rule (data-constrained scaling, Muennighoff et al. 2023: <= 4 epochs is near-free, measured at <= 100B-token
  scales): <= 3 epochs in the stable phase on any web, code, math or paper source; <= 1 on synthetic and on the
  score-2 filler; <= 2 on PDFs and multilingual; <= 4 epochs on any source or anneal sub-pool including the anneal.
  The plan runs FineWeb-Edu at 2.5 and DCLM at 2.0 epochs before any score-2 filler; max 2.73 per source incl. anneal,
  3.38 per anneal sub-pool. Average 1.62 epochs over 6.12T unique tokens touched; web 7.12T used over 3.80T unique =
  1.87 epochs.
- Extension pool: stable tokens beyond 9.9T (MFU above 0.38) are drawn from the HQ web rows (FineWeb-Edu, DCLM,
  Nemotron-CC real) in proportion to their room below the 3-epoch stable cap (capacity 2.53T); synthetic, Cosmopedia,
  filler and multilingual stay at their planned counts and the dataloader's mixture weights switch at 9.9T. The 0.42
  upside (11.39T stable) needs 1.49T and lands at FineWeb-Edu 2.80 / 2.96, DCLM 2.59 / 2.69, Nemotron-CC real 2.59 /
  2.59 epochs (stable / incl. anneal), inside every cap.
- Repetition is measured, not assumed: the 20 x 1B @ 30B ablations cannot see repetition (30B << any source's unique
  pool) and Nemotron-CC's 15T-horizon comparison found more unique mid/high-quality tokens beating repeated HQ filters,
  so Block 1 runs one epoch-scaled proxy: 1B x 300B, arm A = 100B unique HQ (FineWeb-Edu + DCLM at plan proportions)
  x 3 epochs, arm B = 300B unique HQ + score-2 / Nemotron-CC medium-high x 1 epoch, same WSD, ranked on post-decay
  loss and the 8-task aggregate (6,768 GPU-h, 4.4 days on 64 GPUs, USD 14,889 inside Block 1). Decision rule at G2b:
  if B beats A by more than the 2-seed noise floor, FineWeb-Edu and DCLM are capped at 2.0 epochs incl. anneal, the
  score-2 tier rises to 1.0 epoch (+1.82T) and Nemotron-CC medium-high buckets become the extension pool.
- Planning counts are replaced by measurement, not argued about. W3 runs a DOMAIN-STRATIFIED sample across ALL CC
  dumps: keep every document whose hash(registered domain) mod 20 == 0 in every dump of FineWeb-Edu, score-2,
  DCLM-baseline and Nemotron-CC HQ real (5 % of 46,350 GB), then the full MinHash above on that slice (5,794 core-h =
  0.31 days on the 768-core partition). Recrawls of the same page stay together, so the measured cross-dump and
  cross-source removal rates are unbiased (missing only cross-domain syndication, which biases them a few points low).
  A per-dump sample (4 of ~100 dumps) is structurally blind to recrawls: a page in k dumps is caught only if >= 2
  copies fall in the sample, P = 0.001 at k = 2, 0.012 at k = 5, 0.049 at k = 10, 0.18 at k = 20, so it would read
  5-15 % where the global pass removes 30-70 % and the real count would arrive at the W12 freeze. The measured rates
  for all four CC sources go into `measured_unique.json` (per-source unique tokens in our tokenizer; the synthetic
  slice derived from the real-text survival) and dr_calc.py is re-run. The plan fixes tokens per source, so a measured
  count only changes that source's epochs while it is at or above its G3 minimum; below it the script clips the row to
  measured x cap, lets the score-2 filler absorb the difference, prints the re-solved mix, writes
  `decision_record.g3_resolved.json` beside the canonical file and exits 2 for sign-off (exit 1 if even the re-solved
  mix breaks a cap, which is when fallback steps 3-4 apply).

### Stable-phase mix (9.9T; unique counts are planning values until measured)

| Source | Raw (T, source tok) | Planned dedup loss | Unique, source tok (T) | Unique, our tok (T) | Licence | Stable epochs (cap) | Tokens (T) | Mix % | Anneal (T) | Epochs incl. anneal | G3 min unique (T) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FineWeb-Edu (score>=3; global cross-dump dedup, keep newest) | 1.3 | 30 % | 0.91 | 0.792 | ODC-By 1.0 | 2.50 (3) | 1.979 | 20.0 | 0.132 | 2.67 | 0.660 |
| DCLM-baseline (global dedup + vs FineWeb-Edu) | 3.8 | 50 % | 1.9 | 1.65 | CC-BY-4.0 (dataset card) | 2.00 (3) | 3.306 | 33.4 | 0.165 | 2.10 | 1.102 |
| Nemotron-CC HQ, real text (already global upstream; dedup vs pool) | 1.1 | 50 % | 0.55 | 0.479 | CC-BY-4.0 | 2.00 (3) | 0.957 | 9.7 | 0 | 2.00 | 0.319 |
| Nemotron-CC HQ, synthetic rephrase/QA (surviving-source slice) | 1.9 | 47 % | 1.01 | 0.876 | CC-BY-4.0 | 1.00 (1) | 0.876 | 8.8 | 0.143 | 1.16 | 0.876 |
| FinePDFs (edu-filtered subset) | 1.0 | 0 % | 1.0 | 0.87 | ODC-By 1.0 | 1.00 (2) | 0.870 | 8.8 | 0.055 | 1.06 | 0.435 |
| FineWeb-Edu score-2 tier (mid web, filler; first 3T of stable only) | 4.1 | 45 % | 2.25 | 1.96 | ODC-By 1.0 | 0.07 (1) | 0.140 | 1.4 | 0 | 0.07 | 0.140 |
| The Stack v2 (permissive licences, dedup; SWH opt-out applied) | 0.6 | 0 % | 0.6 | 0.6 | per-file permissive + SWH terms | 1.50 (3) | 0.900 | 9.1 | 0.176 | 1.79 | 0.300 |
| FineWeb-2 (12 languages, top quality bin) | 1.5 | 0 % | 1.5 | 1.3 | ODC-By 1.0 | 0.40 (2) | 0.522 | 5.3 | 0.088 | 0.47 | 0.261 |
| FineMath 3+ / InfiWebMath 3+ / OpenWebMath | 0.07 | 0 % | 0.07 | 0.07 | ODC-By 1.0 | 2.00 (3) | 0.140 | 1.4 | 0.033 | 2.47 | 0.047 |
| peS2o v2 + arXiv (CC-BY / CC0 papers only) | 0.07 | 0 % | 0.07 | 0.07 | ODC-By 1.0 / per-paper CC-BY | 2.00 (3) | 0.140 | 1.4 | 0.051 | 2.73 | 0.048 |
| Wikipedia (en + 20 languages, 2026 dump) | 0.015 | 0 % | 0.015 | 0.015 | CC-BY-SA 4.0 | 2.00 (3) | 0.030 | 0.3 | 0.011 | 2.73 | 0.010 |
| Books, public domain (Gutenberg, Standard Ebooks) | 0.006 | 0 % | 0.006 | 0.006 | public domain | 2.00 (3) | 0.012 | 0.1 | 0.004 | 2.73 | 0.004 |
| Cosmopedia v2 (synthetic textbooks, kept separate from real text) | 0.028 | 0 % | 0.028 | 0.028 | Apache-2.0 | 1.00 (1) | 0.028 | 0.3 | 0 | 1.00 | 0.028 |
| **Total** | 15.49 | | 9.91 | 8.73 | | avg 1.62 | **9.90** | 100.0 | 0.858 | max 2.73 | 4.23 |

Capacity at the per-source caps: 18.3T stable tokens with every row at its cap; 14.4T with only the HQ rows (web HQ,
PDFs, code, math, papers, wiki, books) at cap and synthetic, filler and multilingual at plan; 11.2T if every unique
count lands 25 % below plan (still >= 9.9T, so the plan stays feasible without lowering quality, and >= 10.9T, so
even the 12.0T design point survives; 12.5T would then need the score-2 fallback). G3 min unique = the larger of
planned stable tokens / cap and (stable + anneal) / 4 per source.

Multilingual: de fr es it pt nl pl ru ja zh ko ar. Opt-out and PII: robots.txt at crawl time as inherited from the
FineWeb/DCLM/Nemotron-CC crawls plus the HF/Spawning opt-out list, refreshed weekly ("ai.txt" is not an adopted
standard and is not relied on); the Software Heritage opt-out list applied to The Stack v2 with per-file attribution
kept in the provenance manifest; scrub emails / phone numbers / IP addresses / government IDs with the datatrove PII
formatter (drop documents with > 5 hits); 13-gram decontamination against every evaluation set before tokenization;
every source kept as its own shard set with a per-document provenance manifest (source, licence, generator model and
its output terms, hash) so any one source can be dropped by a remix. Counsel's W3 memo states positions on (a) the
Llama 3.1 output naming clause, (b) OpenAI output training clauses, (c) Qwen attribution and (d) CC-BY-SA 4.0
(Wikipedia) for model weights (the working position: weights are not a derivative database; the memo confirms or
drops the source); counsel signs the licence manifest at G3, and the signature certifies the generator column, not
only the dataset licences.

### Generator model and output terms (synthetic / instruction sources; the dataset licence alone is not enough)

| Source | Generator and its output terms | Status / default substitution until counsel clears it |
|---|---|---|
| Nemotron-CC HQ synthetic (stable row; anneal QA / distill / extract) | Mistral-NeMo-12B-Instruct / Mixtral-8x22B-Instruct (Apache-2.0; no output restriction) | keep |
| Cosmopedia v2 | Mixtral-8x7B-Instruct (Apache-2.0; no output restriction) | keep |
| Code HQ synthetic subset (unit-tested) | open Apache-2.0 / MIT generators only, per-file provenance | keep |
| Math HQ, anneal-only: OpenMathInstruct-2 | Llama-3.1-405B/70B-Instruct; the Llama 3.1 Community License requires a model trained on its outputs to carry "Llama" at the start of its name | counsel: accept a "Llama-" prefixed release name (recorded in the model card) or drop it for Nemotron-CC-Math v1 real text plus open-generator math sets (DeepSeek-R1 / Qwen-generated, MIT / Apache-2.0) |
| Math HQ, anneal-only: Nemotron-CC-Math v1 | LLM-cleaned real CC text; generator per the dataset card | keep, counsel confirms the generator |
| Instruction-style: Nemotron-Pretraining-SFT-v1 | open generators per the dataset card (CC-BY-4.0) | keep, counsel confirms the generator |
| Instruction-style: SmolTalk | Qwen2.5-72B-Instruct (Qwen licence attribution clause) | keep; Qwen attribution recorded in the model card |
| Instruction-style: Tulu-3 SFT mix (ODC-By) | subsets generated with GPT-4o; OpenAI terms prohibit use to develop competing models | drop the GPT-4o-derived subsets by default, keep the rest |

### Anneal mix (1.1T; candidate 1 of 4, final choice made at the ~8T checkpoint)

| Component | Share | Tokens (B) | Sub-pool unique, our tok (T) | Sub-pool epochs incl. stable |
|---|---|---|---|---|
| FineWeb-Edu score>=4 (top bin) | 12 % | 132 | 0.15 | 3.38 |
| DCLM-baseline top decile (DCLM fastText probability at W12; 0.5B classifier refinement by W18) | 15 % | 165 | 0.165 | 3.00 |
| Nemotron-CC synthetic HQ (QA / distill / extract) | 13 % | 143 | 0.435 | 1.33 |
| Code HQ (Stack v2 edu-filtered, python-edu, synthetic with unit tests) | 16 % | 176 | 0.2 | 2.38 |
| Math HQ from the stable pool (FineMath 4+, InfiWebMath 4+, OpenWebMath) | 3 % | 33 | 0.04 | 2.83 |
| Math HQ, anneal-only (Nemotron-CC-Math v1, OpenMathInstruct-2; CC-BY-4.0; generator terms above) | 10 % | 110 | 0.15 | 0.73 |
| Instruction-style (Nemotron-Pretraining-SFT-v1 CC-BY-4.0, SmolTalk Apache-2.0, Tulu-3 SFT mix ODC-By minus GPT-4o subsets) | 12 % | 132 | 0.08 | 1.65 |
| Papers + Wikipedia + PD books | 6 % | 66 | 0.091 | 0.73 |
| FinePDFs top bin | 5 % | 55 | 0.174 | 1.32 |
| Multilingual (FineWeb-2 top bin) | 8 % | 88 | 0.348 | 0.65 |

Candidates 2-4 vary the HQ-web / code+math / instruction split (50/20/8, 35/35/12, 42/25/15 with no synthetic).
Selection: anneal 50B tokens per candidate from the ~8T checkpoint as 4 parallel 128-GPU jobs (0.9 block days,
10,957 GPU-h), pick by held-out per-source loss plus the private held-out suite (10 tasks, >= 500 items each, never
used in any ablation, hashed and decontaminated; built by the research engineer, due W18); candidate 1 stands unless
beaten on >= 60 % of held-out tasks. The anneal pools are assembled by W18: FineWeb-Edu score >= 4 and the DCLM
fastText top decile are shipped scores; the 0.5B quality classifier (trained on the public FineWeb-Edu Llama-3-70B
annotations, 450k, plus DCLM's OH-2.5 + ELI5 positives) refines the DCLM, FinePDFs, Stack v2 and FineWeb-2 top bins
only and is not on the W12 freeze path.

### Long-context mixes (50B at 32k, 20B at 128k)

| Component | Share | Tokens (B) at 32k | Tokens (B) at 128k |
|---|---|---|---|
| Repo-level concatenated code (Stack v2) | 25 % | 12.5 | 5.0 |
| Papers (peS2o / arXiv full text) | 25 % | 12.5 | 5.0 |
| Public-domain books | 20 % | 10.0 | 4.0 |
| Long web / PDF documents > 8k tokens | 10 % | 5.0 | 2.0 |
| Short-context replay (packed anneal mix) | 20 % | 10.0 | 4.0 |

The 128k stage applies a 64k length floor to the long-document rows. Tokenized corpus: 11.27T tokens x 4 B
(uint32; vocab 131,072 > 65,535) = 45.1 TB (the extension pool is tokenized with the frozen mix; its 2.53T is part of
the shard set, not an extra tokenization).

Data readiness, dated (the pipeline must not gate the ladder): the 131k BPE is trained W3-4 and frozen W5 d1 (the
digit / whitespace tests at G1 still apply); the v0 corpus (>= 1.5T tokens from the as-released, per-dump-deduped
FineWeb-Edu, score-2, DCLM-baseline, Nemotron-CC medium-high, Stack v2 and FineMath shards in the frozen tokenizer;
2,025 core-h) is ready by the end of W6 (G1) and every ladder run and every 1B/3B ablation trains on it, so the G2
fits are v0 fits; the dedup-threshold ablation corpora (one fixed 10-dump subset, 10 % of the CC text, MinHash at
Jaccard 0.7 / 0.8 / 0.9; 20,857 core-h = 1.1 days) are built W5-6 on the CPU partition before the production pass;
production pass 1 runs W7 d1 -> W10 d3 at the latest (9.5 days at the partition rate plus margin), pass 2 (re-run
after fixes) -> W11 d7; tokenization of the frozen mix is incremental from W10 d4 and must reach >= 300B globally
shuffled tokens by W11 d7 (gate G3a) so the 3B/300B rehearsal starts on W12 d1. If G3a slips, the rehearsal starts on
v0 and the G5 anchor is re-based at the main run's 1T checkpoint (the 1T gate becomes a v0-vs-frozen-mix consistency
check and 4T is the first anchored gate).

Gate G3 (per source, measured in our tokenizer): unique tokens >= the G3 min column for every source, else the mix is
re-solved by dr_calc.py from `measured_unique.json` (exit 2, sign-off required) and the ordered fallback applies:
(1) the failing source runs at its cap and the other HQ sources may be raised to theirs; (2) score-2 tier up to 1.0
epoch (+1.82T); (3) Nemotron-CC synthetic to 12 % of stable; (4) let the date-driven WSD rule shorten the stable
phase, never below the 9.0T anneal floor (section 4). Near-dup check: 1M
sampled documents queried against the full-corpus LSH index, <= 1 % with a neighbour at Jaccard >= 0.8. Data hot-swap:
Block 2 may start on FineWeb-Edu + DCLM shards alone and swap in the full mix at 1T tokens, so a late pipeline costs
float, not idle GPUs; when the hot-swap is used, the 1T gate (G5) is scored on the FineWeb-Edu + DCLM held-out subset
only and the full-mix comparison moves to 2T.

## 4. Training recipe

Decisions:
- Standard parameterisation with the peak LR transferred from a ladder fit lr*(N, D) (not muP), because torchtitan,
  checkpoints and serving stay stock and the 3B confirmation is cheap. The ladder fixes its batch per size (150M:
  0.5M; 400M: 1M; 1B: 2M; 3B: 4M tokens), sweeps (LR, batch) jointly at 400M and applies the sqrt batch-LR
  correction elsewhere; every ladder run uses the main-run WSD with a 10 % 1-sqrt decay and LRs are ranked on
  post-decay loss, never stable-phase loss. A duration axis (1B at 30B and 120B tokens, 3B at 90B and 300B) fits
  the D dependence, because optimal LR falls with training length. The ladder guards against a bad LR; it does not
  set it: lr*(N) is fitted through 3 sizes (0.82 decades) and extrapolated 0.94 decades, the duration axis spans
  30-121 tokens per non-embedding parameter while the main run sits at 1,261, so that regime is covered only by the
  stable/decay form, the main-run LR is clamp(fit, 3e-4, 6e-4) and the 3B/300B rehearsal (99 tokens/param) is the
  last LR confirmation. The 3B/90B point has three LRs (fit x 0.67, 1.0, 1.5) so a parabola can locate the optimum.
- 8M-token global batch (8,388,608) by default, reached by a two-phase ramp (2M -> 4M over the first 100B tokens,
  4M -> 8M by 500B), LR unchanged: at 4M the fixed 0.24 s cross-replica all-reduce is 17.6 % of a 1.37 s step; at
  8M it is 8.8 % of a 2.74 s step, with half the exposed tail and half the validation and checkpoint step counts per
  token (OLMo 2 13B used 8M; Llama 3 ramped 4M -> 8M -> 16M). 4M (grad-accum 1) is the fallback, taken only if the 1B
  batch ablation shows > 0.5 % post-decay loss penalty at the 8M-equivalent (batch 4M at 1B); B_simple is measured
  every 10B tokens from the start of Block 2 and the 4T decision is "step down to 4M", never up.
- WSD with a 1-sqrt decay to 1 % of peak and a date-driven anneal start with a 9.0T token floor, so the stable phase
  absorbs schedule variance in both directions: MFU above the 0.38 plan adds stable tokens from the extension pool
  (0.30T per point, 12.0T total at 0.404), an MFU miss shortens the stable phase instead of forcing a re-run or an
  overrun, and a catastrophic loss of days buys compute (options) instead of silently annealing a short run.
- bf16 autocast with fp32 master weights and fp32 gradient reduction. FP8 is piloted at 3B and adopted for the main
  run only if gate G2 passes; it is upside, not baseline.

| Item | Value | Arithmetic / rationale |
|---|---|---|
| Global batch | 8,388,608 tokens (2,048 x 4,096), default | 512 GPUs x micro-batch 2 x 4,096 x grad-accum 2; `set_requires_all_reduce(False)` on micro-step 1 so the cross-node all-reduce runs once per step; memory per GPU unchanged (micro-batch 2 x 4,096 per micro-step) |
| Batch fallback | 4,194,304 (grad-accum 1) | only if the 1B batch ablation (2M vs 4M at 1B = the 4M vs 8M decision at 10B) shows > 0.5 % post-decay penalty; the 4T decision from the B_simple trend is "step down to 4M", never up; LR unchanged either way |
| Batch ramp | phase 1: 2,097,152 -> 4,194,304 over the first 100B tokens (grad-accum 1); phase 2: 4,194,304 -> 8,388,608 by 500B (grad-accum 2); linear in steps | phase 1: 31,789 steps = 100B / mean batch 3,145,728, implemented as the per-rank packed varlen window growing from 4,096 to 8,192 tokens in 256-token increments (17 plateaus of 1,870 steps); phase 2: 63,578 steps = 400B / mean batch 6,291,456, two micro-steps per step each with the window again growing 4,096 -> 8,192 (17 plateaus of 3,740 steps); documents stay cut at 4,096 so max_seqlen never changes; no rank idles and the smallest GEMM has M = 4,096; cu_seqlens padded to 1,024 int32 entries and the token dimension marked dynamic (`torch._dynamo.mark_dynamic`) so the ramp recompiles 34 times in total (one per window size) and never per document count |
| Optimizer | AdamW, betas (0.9, 0.95), eps 1e-8, fused, fp32 state sharded | |
| Peak LR / min LR | 3.0e-4 prior; final = clamp(lr*(N, D) extrapolated to 8.72B non-embedding and 11.0T, 3e-4, 6e-4), confirmed at 3B/90B at fit x {0.67, 1.0, 1.5} and at 3B/300B at fit x {1.0, 1.5} / 1 % of peak | 3e-4 at 4M is the safe prior (OLMo 2 7B 3e-4 at 4M; OLMo 2 13B 9e-4 at 8M; DCLM-7B 2e-3 at 4M with QK-norm + z-loss); kept at 3e-4 for the 8M batch (the sqrt rule would allow x1.41); the risk is loss left on the table, not instability |
| Warmup | 3,610 steps (8B tokens), linear from 0 | inside ramp phase 1 (linear-in-steps: 2,097,152 s + 2,097,152 s^2 / (2 x 31,789) = 8e9); stated in steps because the ramp makes tokens ambiguous; the short end of peer practice is 2,000 steps at 4M (OLMo 2 7B), DCLM-7B 5,000, Llama 3 8,000; the 3B/300B rehearsal checks for early-step grad-norm spikes |
| Stable phase | 9.9T tokens at peak LR = 1,215,935 steps | 95,367 ramp + (9.9T - 0.5T) / 8,388,608 |
| Decay phase | 1.1T tokens = 131,130 steps; lr(tau) = min + (peak - min) x (1 - sqrt(tau)) | 10 % decay fraction; total 1,347,065 steps |
| Anneal-start rule | the anneal starts at Block 2 day 50.3 (= 56 - 4.9 anneal - 0.4 - 0.4 long-context) if >= 9.0T stable tokens have been reached; stable tokens = whatever is reached by then, drawn from the extension pool above 9.9T | expected 10.18T at MFU 0.38 (9.9T + 0.28T slack); 11.39T at 0.42 (12.5T total); 10.90T at 0.404 (12.0T total); 9.58T at 0.36 unless option 1 is exercised by block day 21 |
| Option 1 trigger | effective MFU projected below 0.371 at block day 21 (3.8T stable tokens reached) | the 9.9T plan is then missed by more than the 1.3-day slack; +1 week at 2.20 (USD 195,149) adds 1.57T at plan MFU; never used to buy the 12.0T design point at the planning MFU (section 1) |
| Anneal token floor | 9.0T; below it the program exercises option 1 (by block day 21, USD 195,149) or option 2 (by block day 42, USD 212,890) instead of annealing | the floor binds only if the effective MFU falls below 0.341 or 5.3 stable days are lost (restart from an old checkpoint, bad hot-swap, non-determinism found via the data-order hash); each option week adds 1.57T at plan MFU |
| Long-context LR and batch | constant 3.0e-5 after a 1B-token warmup, both stages; batch 4,194,304 at 32k (64 CP groups x mb 2 x 32,768; 11,921 steps) and 8,388,608 at 128k (64 x mb 1 x 131,072; 2,384 steps) | 10 % of peak; CP=8 inside the node |
| Weight decay | 0.1, decoupled, 2-D weights only (not norms, not embeddings) | |
| Grad clip | 1.0 global norm | |
| Skip-step rule | skip the update if grad-norm > 3x its 100-step EMA; 3 consecutive skips -> roll back to the last checkpoint and advance the data seed | first line of spike defence |
| Spike rollback | loss > EMA + 0.1 for 50 steps or grad-norm > 10x EMA: roll back, skip 200 steps of data, re-seed | 2 rollbacks budgeted in the 1.18 |
| Precision | bf16 autocast, fp32 master, fp32 reduce, fp32 RMSNorm and softmax; FP8 (torchao float8 rowwise or TE) only if G2 passes | bf16 reduce with fp32 accumulation is measured at G2 and kept only if it buys >= 1 MFU point (>= 160 tok/s/GPU) |
| Loss | fused chunked linear + cross-entropy (2,048-token chunks) + z-loss 1e-4 | logits never materialise at full width |
| Packing | document-masked varlen through the FA3 custom op at 4k and 8k (cu_seqlens int32 per micro-batch, padded to 1,024 entries, max_seqlen 4,096); EOS-separated causal packing ablated at 1B as the fallback and used at 32k and 128k (section 6) | FlexAttention block-causal mask is the kernel fallback at 4k |
| Validation | 6 held-out domains x 10M tokens every 1,000 steps (0.24 %) + 13 per-source x 10M every 10B tokens (0.43 %) | 0.67 % of step time, booked as 1.0 % |
| Downstream evals | lm-eval-harness suite on the bf16 export every 100B tokens (110 checkpoints) on spare node 1, never stalling the job | 330 GPU-h |
| Data order | fixed global shuffle seed; per-step dataloader position and RNG in every checkpoint; per-step data-order hash logged to W&B | bit-identical 100-step resume is a gate at G1, G3b and G4 |

Throughput at plan MFU: 512 x 989e12 x 0.38 / 6.2816e10 = 3,063,232 tokens/s cluster-wide, 5,983 tokens/s per
GPU, 2.74 s per 8M-token step; a 30-min checkpoint interval is 657 steps.

Throughput gates are stated in tokens/s per GPU, which is basis-free, and "MFU" always means tokens/s x 6.2816e10 /
989e12 at seq 4,096 (6ND + causal attention): G2 and G3b >= 6,300 tok/s/GPU on 64 GPUs (= 0.400); G4 acceptance
>= 6,000 on 512 GPUs rolling over 2 h and G5 rolling >= 6,000 (= 0.381, the planning value); G3b 32k path >= 3,800
(= 0.35 at 32k) and 128k path >= 1,300 (= 0.25 at 128k). torchtitan's built-in MFU counts attention non-causally
(12*L*h*hd*s) and reads x1.064 on this basis (x1.137 on 6ND): a torchtitan-reported 0.40 is 0.376 here and 0.352 on
6ND, below the option-1 trigger while appearing to pass; the metrics hook logs tokens/s/GPU and the DR-basis MFU next
to torchtitan's number.

Functional forms the gates score against (all implemented and self-tested in dr_calc.py): lr*(N) = a x N^-b by
log-log least squares over the 150M/400M/1B post-decay optima (R^2 is reported, not gated: a 2-parameter fit through
3 points cannot fail an R^2 test); G2 LR gate at 3B/90B: the 3-point log-LR parabola optimum (fit x 0.67, 1.0, 1.5)
lies within 1.5x of the extrapolated lr*(N) and the post-decay loss at the two bracketing LRs differs by <= 0.5 %;
L(N, D) = E + A / N^0.34 + B / D^0.28 with E, A, B by least squares on every ladder post-decay loss, 3B/90B within
0.02 nats (G2). G5 compares the main run, which is at peak LR at 1T / 4T / 8T, with STABLE-phase curves, never
post-decay ones (the G3b gate itself requires the anneal to lower loss >= 2 %, i.e. >= 0.04 nats at L ~ 2.0, twice
the G5 band): every ladder run logs delta = loss at the end of its stable phase (0.9 D) minus its post-decay loss
(roughly size-invariant at a fixed 10 % decay); L_stable(N, D) = L_postdecay(N, D / 0.9) + delta; the G5 prediction is
L_stable shifted by its residual at the 3B/300B rehearsal's stable-phase loss at the decay start (270B tokens), on the
same 6-domain held-out set; gate |L_10B,stable(D) - L_stable(9.8B, D)| <= 0.02 nats at D = 1T / 4T / 8T plus the
per-source non-increase rule.

## 5. Compute plan

Decisions:
- 512 compute GPUs + 16 hot spares for the main run. 512 is the smallest count that finishes the main run inside
  two months; 1,024 halves wall-clock but doubles the interruption rate and saves only ~24 team-days (USD 156k).
- MFU 0.38 over total FLOPs (6ND + attention) at seq 4,096 is the planning value (6ND basis: 0.356; the brief's band
  is 38-45 %, public torchtitan FSDP2 + compile + SAC numbers for 8B-class sit at ~33-40 % on 6ND, and the fp32
  cross-replica all-reduce is a known HSDP exposure). It equals the acceptance gate on 512 GPUs (6,000 tok/s/GPU) and
  the G2 gate on 64 GPUs minus 2 points for 512-GPU stragglers. Before the W12 freeze mfu_main := G2 measurement
  minus 0.02 and the Block 2 fit table is regenerated; the budget is built at 0.38 and is never re-based upward: MFU
  above plan becomes stable tokens through the date rule (0.42, the former planning value, is upside = 12.5T). The
  headline is always reported on both bases and in tokens/s/GPU.
- Framework gate at G2: the 10B config also runs on the same 64 GPUs in Megatron-Core/NeMo (bf16, Transformer Engine
  kernels, TP=1) for one afternoon; if it beats torchtitan by >= 3 MFU points (>= 470 tok/s/GPU) the framework is
  decided at G2 and two engineer-weeks of checkpoint / serving export conversion are booked (sensitivity table).
- Overhead 1.18 for the main run from the build-up below, 1.25 for short runs and long-context stages, 1.30 for
  SFT/RM/DPO, 3.0 for online RL on the FLOP basis (RL is then budgeted as wall-clock with 4.6x headroom).
- Four reserved blocks under one master contract at USD 2.20, plus an on-demand serving tail. Neither Block 2 option
  is in the base plan.

FLOPs: 6N = 6 x 9,798,236,160 = 5.8789e10 per token; causal attention 6 x L x s x d = 6 x 40 x 4,096 x 4,096 =
4.0265e9 (6.85 % of 6N); total 6.2816e10 per token at 4k (9.1002e10 at 32k, 1.8764e11 at 128k). Main run:
11.0e12 x 6.2816e10 = 6.9098e23 FLOP (6ND alone 6.4668e23) / (989e12 x 0.38 x 3,600 = 1.3530e18 per GPU-h) =
510,717 GPU-h ideal; x 1.18 = 602,646 GPU-h; / 512 / 24 = 49.0 days. Per 1T stable tokens: 54,786 GPU-h =
USD 120,529.

### Overhead build-up (main run)

| Component | Fraction of ideal time |
|---|---|
| Hardware interruptions: 0.5/day x 50.7 training days = 25.4 events x (15 min lost + 15 min restart) / (49.0 d x 24 h) | 1.1 % |
| Async checkpoint stalls (0.11 s NVMe write + DCP metadata, every 30 min) | 0.5 % |
| In-loop validation (0.24 % every 1,000 steps + 0.43 % per-source every 10B tokens) | 1.0 % |
| Dataloader, logging, optimizer step | 1.0 % |
| Stragglers, slow nodes, IB congestion | 3.0 % |
| Loss-spike rollbacks (2 x 6 h budgeted) | 1.0 % |
| torch.compile warmup after each restart (~5 min x 25) | 0.2 % |
| Unplanned debugging, MFU dips, config iterations | 10.0 % |
| **Sum** | **17.8 % -> factor 1.18** |

The 15-min loss per interruption holds only because every 30-min checkpoint is uploaded to object storage (117.6 GB /
1,800 s = 65 MB/s aggregate); a node loss destroys that node's local DCP shards, so the restart reads the last upload.

### Compute table (GPU-hours; USD at the block's price; rows rounded independently)

| Workload | Block | Tokens | Seq | MFU | FLOPs | GPU-h ideal | Ovh | GPU-h | GPUs | Days | USD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Main run: stable phase | B2 | 9.90T | 4096 | 38 % | 6.22e23 | 459,645 | 1.18 | 542,381 | 512 | 44.1 | 1,193,239 |
| Main run: anneal/decay phase | B2 | 1.10T | 4096 | 38 % | 6.91e22 | 51,072 | 1.18 | 60,265 | 512 | 4.9 | 132,582 |
| Anneal-mix selection: 4 x 50B from the ~8T ckpt (4 parallel 128-GPU jobs) | B2 | 200B | 4096 | 38 % | 1.26e22 | 9,286 | 1.18 | 10,957 | 512 | 0.9 | 24,106 |
| Long-context stage 1: 50B at 32k, CP=8, SAC(op), mb 2, theta 4M | B2 | 50B | 32768 | 35 % | 4.55e21 | 3,651 | 1.25 | 4,564 | 512 | 0.4 | 10,041 |
| Long-context stage 2: 20B at 128k, CP=8, full AC, mb 1, theta 16M | B2 | 20B | 131072 | 25 % | 3.75e21 | 4,216 | 1.25 | 5,270 | 512 | 0.4 | 11,594 |
| Block 2 acceptance + burn-in (4 d x 528 GPUs, billed) | B2 | - | - | - | - | 50,688 | 1.00 | 50,688 | 528 | 4.0 | 111,514 |
| In-run downstream evals: 110 ckpts x 3 GPU-h on spare node 1 | B2 | - | - | - | - | 330 | 1.00 | 330 | 8 | 1.7 | 726 |
| Ladder 150M (d1024 L14): 6 LR x 2 seeds x 6B at batch 0.5M (11,444 steps), on v0 | B1 | 72B | 4096 | 20 % | 2.10e20 | 294 | 1.25 | 368 | 64 | 0.2 | 809 |
| Ladder 400M (d1536 L16): 5 LR x 2 seeds x 12B at batch 1M (11,444 steps; (LR, batch) swept jointly), on v0 | B1 | 120B | 4096 | 25 % | 6.52e20 | 733 | 1.25 | 916 | 64 | 0.6 | 2,015 |
| Ladder 1B (d2048 L22): 4 LR x 30B at batch 2M (14,305 steps), on v0 | B1 | 120B | 4096 | 32 % | 1.23e21 | 1,083 | 1.25 | 1,354 | 64 | 0.9 | 2,978 |
| Ladder 3B (d3072 L30): 3 LR (fit x 0.67, 1.0, 1.5) x 90B at batch 4M (21,458 steps), on v0 | B1 | 270B | 4096 | 38 % | 6.81e21 | 5,032 | 1.25 | 6,291 | 64 | 4.1 | 13,839 |
| Ladder duration axis: 1B x 120B, 3 LR at batch 2M (57,220 steps), on v0 | B1 | 360B | 4096 | 32 % | 3.70e21 | 3,248 | 1.25 | 4,061 | 64 | 2.6 | 8,933 |
| Ladder duration axis: 3B x 300B, second LR (fit x 1.5) at batch 4M (71,526 steps; the rehearsal is the first point) | B1 | 300B | 4096 | 38 % | 7.57e21 | 5,592 | 1.25 | 6,990 | 64 | 4.6 | 15,377 |
| FP8 pilot: 3B x 90B (torchao float8 rowwise vs bf16 twin) | B1 | 90B | 4096 | 38 % | 2.27e21 | 1,677 | 1.25 | 2,097 | 64 | 1.4 | 4,613 |
| Ablations: 20 x 1B @ 30B on v0 (mix, code 8 vs 15 %, math 1.3 vs 4 %, dedup threshold 0.7/0.8/0.9 on the W5-6 10-dump corpora, doc-mask, decay shape, batch 2M vs 4M, WD, tokenizer, z-loss/QK-norm) | B1 | 600B | 4096 | 32 % | 6.17e21 | 5,414 | 1.25 | 6,768 | 64 | 4.4 | 14,889 |
| Epoch-proxy ablation: 2 x 1B @ 300B on v0 (arm A 100B unique HQ x 3 epochs; arm B 300B unique x 1 epoch; same WSD) | B1 | 600B | 4096 | 32 % | 6.17e21 | 5,414 | 1.25 | 6,768 | 64 | 4.4 | 14,889 |
| Ablation confirmations: 3 x 3B @ 60B on v0 | B1 | 180B | 4096 | 38 % | 4.54e21 | 3,355 | 1.25 | 4,194 | 64 | 2.7 | 9,226 |
| Full-recipe rehearsal: 3B x 300B at the fitted LR on the frozen mix (WSD + 1-sqrt anneal + mini 32k + DCP resume) | B1 | 300B | 4096 | 38 % | 7.57e21 | 5,592 | 1.25 | 6,990 | 64 | 4.6 | 15,377 |
| 10B dress rehearsal on 64 GPUs (4 h) + Megatron-Core/TE comparison of the same config (4 h, at G2) + node-kill/restore drill | B1 | - | - | - | - | 512 | 1.00 | 512 | 64 | 0.3 | 1,126 |
| GPU data jobs: 0.5B quality classifier over the anneal candidate pools (<= 5T; 2ND, MFU 0.30, x1.5; W13 d4-W14 on Block 1, dev-node overflow, due W18; not on the freeze path) + 600 GPU-h NeMo Curator semantic dedup | B1 | - | - | - | - | 7,622 | 1.00 | 7,622 | 64 | 5.0 | 16,768 |
| SFT: 1.5M ex x 1.5k tok x 3 ep + 5 ablations x 1 ep (TRL, 8k packed) | B3 | 18.0B | 8192 | 30 % | 1.20e21 | 1,126 | 1.30 | 1,464 | 32 | 1.9 | 3,222 |
| Reward model: 300k pairs x 2 ep (10B init) | B3 | 1.4B | 8192 | 30 % | 9.63e19 | 90 | 1.30 | 117 | 32 | 0.2 | 258 |
| DPO: 300k pairs x 2 ep x 3 rounds (policy fwd+bwd + ref fwd = 8ND) | B3 | 4.3B | 8192 | 30 % | 3.85e20 | 360 | 1.30 | 469 | 32 | 0.6 | 1,031 |
| Online RL (GRPO, verl): 5 campaigns x 300 steps x 512 prompts x 8 samples; wall-clock budget 48 GPUs x 21 d (FLOP need 5,291 GPU-h: gen 6.29B tok = 583 GPU-h + train 1,181 GPU-h, x3) | B3 | - | - | - | - | 24,192 | 1.00 | 24,192 | 48 | 21.0 | 53,222 |
| Local 70B-class open-weight judge: label 280k on-policy pairs + eval judging | B3 | - | - | - | - | 2,000 | 1.00 | 2,000 | 16 | 5.2 | 4,400 |
| Post-training + final evals: 50 x 8 GPU-h + 1,500 GPU-h final suite/safety/long-ctx | B3 | - | - | - | - | 1,900 | 1.00 | 1,900 | 16 | 4.9 | 4,180 |
| Serving pilot inside Block 3 (W29-30): 8 GPUs x 2 wk | B3 | - | - | - | - | 2,688 | 1.00 | 2,688 | 8 | 14.0 | 5,914 |
| Serving pilot on-demand (W31-40): 8 GPUs x 10 wk | OD | - | - | - | - | 13,440 | 1.00 | 13,440 | 8 | 70.0 | 38,976 |
| Dev/debug node: 8 GPUs x 40 wk standing (smoke tests, repro, CI) | DEV | - | - | - | - | 53,760 | 1.00 | 53,760 | 8 | 280.0 | 118,272 |
| **Sum of workloads** | | | | | | | | **829,413** | | | |

The ladder duration axis adds 11,050 GPU-h = USD 24,310, the third 3B/90B LR 2,097 GPU-h = USD 4,613 and the
epoch-proxy ablation 6,768 GPU-h = USD 14,889, all inside Block 1's reserved hours (no cash change). The 128k dress
rehearsal (one node, CP=8, one 131,072-token sequence, 20 steps, ~5 min) runs on the dev node at G3b. Block 1 load
by window: W7-8 ladder + FP8 pilot 15,085 GPU-h of 21,504 (70 %); W9-11 ablations + epoch proxy + confirmations
17,729 of 32,256 (55 %); W12-13 d3 the two 3B/300B runs on 32 + 32 GPUs; W13 d4-W14 the classifier (7,622 GPU-h, 5
days on 64 GPUs) and any extra seeds.

### Reserved blocks (what we pay; rows rounded independently)

| Block | GPUs | Weeks | GPU-h | USD/GPU-h | USD | Attributed GPU-h | Utilisation |
|---|---|---|---|---|---|---|---|
| Dev node (W1-40): standing 8-GPU allocation | 8 | 40 | 53,760 | 2.20 | 118,272 | 53,760 | 100 % |
| Block 1 (W7-14): ladder, FP8 pilot, ablations, rehearsal, data GPU jobs | 64 | 8 | 86,016 | 2.20 | 189,235 | 54,927 | 64 % |
| Block 2 (W15-22): main run, 512 compute + 16 hot-spare GPUs | 528 | 8 | 709,632 | 2.20 | 1,561,190 | 674,455 | 95 % |
| Block 3 (W23-30): SFT, RM, DPO, GRPO, judge, evals, serving pilot start | 48 | 8 | 64,512 | 2.20 | 141,926 | 32,830 | 51 % |
| Serving pilot on-demand (W31-40) | 8 | 10 | 13,440 | 2.90 | 38,976 | 13,440 | 100 % |
| **Total** | | | **927,360** | | **2,049,600** | **829,413** | 89 % |

Block 1 is over-provisioned on purpose: 20 ablations run 8-wide in 3 rounds of ~42 h, which is what makes the W12
data freeze reachable; the two 3B/300B runs (rehearsal and second LR) run in parallel on 32 GPUs each from W12 d1
(9.1 days wall-clock each, done W13 d3). Overflow policy: ablations and evals may spill to spot (USD 1.50, checkpoint
every 10 min); the main run never does. One idle Block 2 day = 528 x 24 x 2.20 = USD 27,878. Acceptance days are
billed (4 x 528 GPUs = 50,688 GPU-h, USD 111,514); the acceptance clause credits days lost to vendor-caused failures.
Option 1: +1 week at 2.20, exercisable by block day 21 (W18 d1, 3.8T stable tokens reached; USD 195,149), exercised
only if the effective MFU projects below 0.371. Option 2: +1 week at <= 2.40, exercisable by block day 42 (USD
212,890; costs nothing unless used). Each option week buys 1.57T stable tokens at plan MFU. Neither option is in the
base plan; the 913,920 reserved hours sit under one master contract over W1-W40 (dev node to W40; the 64/528/48-GPU
blocks end W30).

### Block 2 fit (56 days; rows rounded independently)

| Item | Days | Note |
|---|---|---|
| Acceptance + burn-in | 4.0 | block days 0-4, billed |
| Stable phase needed at MFU 0.38 | 44.1 | 542,381 / 512 / 24 |
| Anneal-mix selection pause at ~8T | 0.9 | 4 x 50B as 4 parallel 128-GPU jobs |
| Anneal | 4.9 | starts at block day 50.3 (W22 d2) if >= 9.0T stable tokens are reached |
| 32k stage + 128k stage | 0.4 + 0.4 | |
| **Total needed** | **54.7** | slack 1.3 d = 0.28T extra stable tokens (0.224T per stable day) |

Stable window = day 4 to day 50.3 minus the 0.9-day pause = 45.4 days: 10.18T stable tokens expected at MFU 0.38
(11.28T total); the anneal, the selection pause and the stable phase all scale with the effective MFU, the
long-context stages do not, so stable tokens = 51.2 d x rate(MFU) - 1.3T: 10.90T at 0.404 (the 12.0T design point),
11.39T at 0.42 (12.5T total), 9.58T at 0.36 (shortfall 1.5 d); 0.30T per MFU point. Option 1 is exercised only below
0.371 (the 9.9T plan missed by more than the 1.3-day slack). The 9.0T anneal floor binds only if the effective MFU
falls below 0.341 or 5.3 stable days are lost; option 2 (by block day 42) is the remedy after option 1 has expired.
Milestones (block day): 1T at 8.5 (W16 d2), 4T at 21.8 (W18 d1, the same calendar day as the option-1 deadline), 8T
at 39.7 (W20 d5), resume after selection at 40.6.

### Per-GPU memory (HSDP shard=8 inside the node, replicate=64; micro-batch 2 x 4,096 per micro-step; SAC op-level)

| Item | GB | Arithmetic |
|---|---|---|
| fp32 sharded params (FSDP2 master DTensor; bf16 copies exist only inside all-gather buffers) | 4.56 | 9.798e9 x 4 B / 8 / 2^30 |
| fp32 Adam m + v (sharded) | 9.13 | 9.798e9 x 8 B / 8 / 2^30 |
| fp32 sharded grads (reduce_dtype = fp32) | 4.56 | 9.798e9 x 4 B / 8 / 2^30 |
| bf16 all-gather buffers: 2 blocks in flight + embedding + lm_head | 2.81 | (2 x 218.1M + 2 x 536.9M) x 2 B / 2^30 |
| Activations, SAC(op): 368 MB/layer/seq x 40 layers x micro-batch 2 | 28.79 | per seq: x 32 MB + q 32 + kv 16 + FA3 out 32 + lse 0.5 + resid 32 + gate 112 + up 112 |
| Logits, chunked fused linear+CE (chunk 2,048, fp32 logits + grad) | 2.00 | 2 x 2,048 x 131,072 x 4 B / 2^30 |
| CUDA context, NCCL buffers, cuBLAS workspace, allocator fragmentation | 4.00 | measured allowance |
| **Total** | **55.85** | headroom 24.15 GB |

Micro-batch 4 would need 84.6 GB (does not fit); no activation checkpointing at micro-batch 2 would need 69.6 GB
(too tight for fragmentation). SAC(op) saves every matmul and FA3 output (out, lse) and recomputes only RMSNorm, RoPE,
SiLU and the gate*up product (~2 % of step time; never recompute the gate/up matmuls, which would cost 21 % of FLOPs).

### Per-GPU memory, long-context stages (CP=8 inside the node, dp_shard=8, dp_replicate=8 on 512 GPUs)

32k stage: 32,768 / 8 = 4,096 local tokens per sequence x micro-batch 2 with SAC(op) is the 4k table plus 0.12 GB of
ring K/V receive buffers = 55.98 GB. 128k stage: 131,072 / 8 = 16,384 local tokens; SAC(op) at micro-batch 1 would
need 368 MB x 4 x 40 = 57.6 GB of activations and 84.8 GB in total (does not fit in 80 GB), so the 128k stage uses
full per-block activation checkpointing at MFU 0.25:

| Item (128k, micro-batch 1, full AC) | GB | Arithmetic |
|---|---|---|
| fp32 params + Adam m + v + grads, 8-way sharded (unchanged) | 18.25 | 4.56 + 9.13 + 4.56 |
| bf16 all-gather buffers (unchanged) | 2.81 | |
| Full AC: saved bf16 block inputs | 5.00 | 16,384 x 4,096 x 2 B x 40 layers / 2^30 |
| One live block during recompute (no SAC inside it) | 2.13 | 544.5 MB per 4,096 tokens x 4 |
| Ring-attention K/V receive buffers (double-buffered) | 0.12 | 2 x 2 x 16,384 x 1,024 x 2 B / 2^30 |
| Logits, chunked fused linear+CE (chunk 2,048) | 2.00 | |
| CUDA context, NCCL buffers, cuBLAS workspace, allocator fragmentation | 4.00 | |
| **Total** | **34.32** | headroom 45.68 GB |

Communication per optimizer step (grad-accum 2): bf16 all-gather 17.1 GB x 2 (fwd + bwd) at 450 GB/s NVLink =
0.076 s per micro-step, 0.152 s per step; fp32 reduce-scatter 34.3 GB at 450 GB/s = 0.076 s per micro-step
(accumulating into the fp32 sharded grad), 0.152 s per step; fp32 ring all-reduce of the 1.22B-param shard across 64
replicas ONCE per step (`set_requires_all_reduce(False)` on micro-step 1) = 9.6 GB at 50 GB/s (one 400 Gb/s NIC at
line rate) = 0.193 s, 0.241 s at the 40 GB/s a 64-node ring sustains in practice; comm total 0.498 s of the 2.74 s
step (backward ~1.83 s) with 16,384 tokens per GPU per step. The fixed all-reduce is 8.8 % of the step (17.6 % at the
4M fallback, which is why 8M is the default). All but the all-reduce of the last two blocks + embedding (0.96 GB,
24 ms, 0.9 % of the step) overlap. The cross-replica all-reduce is still the single biggest MFU risk and is the first
thing profiled at acceptance; G2 measures the four levers (bf16 reduce with fp32 accumulation, dp_shard=16,
grad-accum 1 vs 2, inductor mode).

Checkpoints: full state 9.798e9 x 12 B = 117.6 GB (fp32 params + Adam m + v), bf16 export 19.6 GB; 230 MB per GPU
written to local NVMe in 0.11 s at 2 GB/s, every 30 min (48/day), each one uploaded to object storage within the
interval (65 MB/s aggregate). Retention: last 6 on NVMe; a rolling 24-hour hourly tier on object storage (24 x 117.6
GB = 2.8 TB); permanently, every 100B tokens as bf16 (110 x 19.6 GB) and every 500B tokens plus the end of the stable
phase at 9.9T as full state (23 x 117.6 GB): 4.9 TB permanent, 7.7 TB retained at peak.

## 6. Cluster and parallelism

Cluster: 66 nodes x 8 H100 SXM 80 GB (64 compute + 2 hot spare; spare 1 runs in-run evals, spare 2 stays idle for
failover), NVLink/NVSwitch intra-node, 8 x 400 Gb/s NDR InfiniBand per node (one NIC per GPU) on a rail-optimised
two-level fat tree, 2 TB host RAM, 8 x 7.68 TB NVMe per node. Storage: 120 TB parallel filesystem (Weka or Lustre;
VAST acceptable) for the 45.1 TB uint32 token stream and rolling checkpoints, plus an S3-compatible object store
(~913 TB-months over the program) for raw data, intermediates, every 30-min checkpoint upload, permanent checkpoints
and logs. Scheduler: Slurm 24.x with Pyxis/Enroot containers, gres=gpu:8, exclusive nodes, `--requeue` with automatic
restart from the latest checkpoint, a prolog that runs DCGM health checks and nccl-tests on every allocation;
NCCL 2.26+, CUDA 12.8+, torch >= 2.7 (mid-2026 stable), torchtitan (mid-2026 release), flash-attn 3 (hopper) and
Liger-kernel pinned by commit. Kubernetes is the alternative if the vendor only offers it; nothing above changes.

Hot-spare policy: the main job runs inside a Slurm reservation with preemption enabled on spare 1, so after one swap
under the 4-h SLA a second failure lets the main job take spare 1 automatically inside the 15-min restart budget;
the eval jobs on spare 1 requeue to the dev node until the swapped node is back.

Acceptance (4 days, billed): DCGM diagnostics level 3 and GPU burn on all 66 nodes; nccl-tests all_reduce >= 80 %
of line rate (>= 40 GB/s per GPU inter-node on 64 nodes), NVLink all-gather >= 350 GB/s intra-node; per-node
straggler scan (step time within 3 % of the median); checkpoint write <= 60 s wall and async stall <= 2 s;
forced-restart drill resumes in <= 15 min; 24 h stress with zero Xid/uncorrected ECC; a 2-hour shakedown of the
real job (~22B tokens at plan throughput) at >= 6,000 tok/s/GPU rolling (= MFU 0.381, the planning value). Failing
nodes are swapped under the contract (4-hour node-swap SLA); days lost to vendor-caused failures are credited under
the acceptance clause.

Parallelism: FSDP2 `fully_shard` with HSDP on a 2-D device mesh (dp_shard=8 inside the node, dp_replicate=64 across
nodes), MixedPrecisionPolicy(param_dtype=bf16, reduce_dtype=fp32), per-TransformerBlock sharding plus embedding and
lm_head, reshard_after_forward=True, forward and backward prefetch of 2 blocks. Micro-batch 2 x 4,096 per GPU per
micro-step, grad-accum 2 (8M batch) with `set_requires_all_reduce(False)` on the first micro-step so the reduce-scatter
accumulates into the fp32 sharded grad each micro-step and the cross-node all-reduce runs once per step; the 4M
fallback is grad-accum 1. Activation checkpointing: torchtitan selective "op" mode at 4k and 32k, full per-block at
128k. Attention at 4k/8k: the FA3 varlen custom op (section 2) inside each compiled block, cu_seqlens padded to 1,024
entries and the token dimension marked dynamic so only window-size changes recompile; torch.compile per block
(fullgraph=True), inductor default mode; max-autotune-no-cudagraphs is tested at G2 and acceptance and kept only if
it adds >= 1 MFU point (>= 160 tok/s/GPU). Fused chunked cross-entropy with z-loss. No tensor or pipeline
parallelism. The 32k and 128k stages use context parallelism of 8 on a 3-D mesh cp=8 x dp_shard=8 x dp_replicate=8
over 512 GPUs (64 CP groups; CP nested in the shard dimension so the K/V exchange stays on NVLink); micro-batch 2 at
32k, 1 at 128k (section 5 memory tables). Kernel path for these two stages, decided now because the FA3 custom op is
not context-parallel-aware: primary = torchtitan's SDPA-based context parallelism
(`torch.distributed.tensor.experimental.context_parallel`, flash backend) with EOS-separated causal packing and no
document mask, which is compile-supported and in-tree; document masking is dropped for the 70B long-context tokens
only (long documents dominate the mix, so cross-document attention is a small cost). Upside path =
ring-flash-attention zigzag varlen (FA3 hopper backend, document mask on), pinned by commit and tested on the dev
node by W10; it replaces the primary only if it passes the same G3b gates. G3b runs 32k and 128k steps on one node
with the chosen path at >= 3,800 and >= 1,300 tok/s/GPU (= the planned 0.35 / 0.25 MFU).

## 7. Timeline (40 weeks, 9.2 months, kickoff to served model)

Decisions: Block 2 starts at a contract date (W15) with a 2-week start window; the data freeze (W12) and the
rehearsal gate (W13) sit two weeks before it, so W13-14 is named float that protects the USD 27,878/day block.
Procurement runs LOI by W2, signature by W4 and a fixed Block 2 start date by W6, because vendors need 4-8 weeks to
commit a 528-GPU block; if signing slips past W4, Block 1's first two weeks run on on-demand (USD 15,053) so G2 does
not move. The data pipeline never gates GPU work: the tokenizer is frozen W5 d1, a v0 corpus (>= 1.5T tokens) is
ready at G1 for every ladder run and ablation, the dedup-threshold corpora are built W5-6 on CPU, the 0.5B classifier
is off the freeze path, and gate G3a (>= 300B frozen tokens by W11 d7) protects the W12 d1 rehearsal start. The
contractor track (downloads, tokenizer, v0, PII / opt-out, manifest) runs W1-W13 beside the data engineer's dedup +
quality track. Post-training data preparation runs in parallel with the main run so Block 3 starts the day Block 2
ends. Float is spent only by gate failures, in the order data (G3a, G3) -> recipe (G3b) -> main run (G5) ->
post-training (G8-G10). Every throughput gate below is in tokens/s per GPU (section 4 gives the MFU equivalents).

| Weeks | Phase | GPUs | Gate | Go metric |
|---|---|---|---|---|
| W1-2 | Kickoff; RFQ to >= 3 vendors; LOI on one master contract (913,920 reserved GPU-h over W1-W40, capacity schedule 8 -> 72 -> 536 -> 56 -> 8 GPUs; W15 start, 2-week window; option 1 +1 week at 2.20 by block day 21; option 2 +1 week at <= 2.40 by block day 42; 4-h node-swap SLA; acceptance clause); Slurm, object store, W&B/Prometheus/Grafana/DCGM; fork torchtitan (metrics hook logs tokens/s/GPU and DR-basis MFU); contractor starts the downloads | 8 dev | G0 | LOI signed by end of W2 at <= 2.40 (RFQ target 2.20, walk-away 2.40); contract signed by W4; Block 2 start date fixed by W6; dev node runs the 10B config 100 steps; >= 20 % of raw data downloaded |
| W3-6 | datatrove pipeline (download, language ID, fastText quality, global MinHash 5-gram/112/14x8 keep-newest, exact dedup, PII, opt-out); W3: domain-stratified dedup measurement across ALL CC dumps of all four CC sources (hash(domain) mod 20 == 0, 5 % slice, 5,794 core-h = 0.31 d on 768 cores), measured rates written to measured_unique.json and dr_calc.py re-run; counsel's W3 memo (Llama naming, OpenAI output clauses, Qwen attribution, CC-BY-SA); two vendor quotes for preference pairs; 131k BPE trained W3-4 on a 50 GB stratified sample and frozen W5 d1; W5-6: v0 corpus tokenized (>= 1.5T tokens, 2,025 core-h) and the three dedup-threshold corpora built (10-dump subset at Jaccard 0.7/0.8/0.9, 20,857 core-h = 1.1 d); FA3 custom op + FlexAttention fallback built with padded cu_seqlens and dynamic token dim; checkpoint/resume drills on the dev node | 8 dev + 768 CPU cores | G1 | tokenizer bytes/token within 2 % of Llama-3 on held-out en/code/multi, digit and whitespace tests pass; v0 corpus >= 1.5T tokens on the PFS with checksums; pipeline >= 300 GB/h sustained on a 1 TB sample (two passes over 69.7 TB = 19 days of the 8-week booking); measured dedup rates published for all four CC sources; a TransformerBlock with the FA3 custom op compiles with fullgraph=True on the dev node, 8-GPU block throughput within 5 % between the FA3 and FlexAttention paths, and three document counts x two window sizes run with zero additional recompiles (assert on torch._dynamo.utils.counters); bit-identical 100-step resume; data-order hash logged |
| W7-8 | Ladder 150M/400M/1B/3B on v0 (29 runs incl. 2 seeds at 150M/400M for the noise floor; batches 0.5M/1M/2M/4M; (LR, batch) jointly at 400M; 3 LRs at 3B/90B; WSD + 10 % decay on every run, stable-minus-postdecay delta logged per run) + duration axis 1B x 120B x 3 LR + FP8 pilot at 3B; 10B throughput test on 8 nodes in four variants: (i) bf16 reduce with fp32 accumulation, (ii) dp_shard=16 across 2 nodes, (iii) grad-accum 1 (4M) vs 2 (8M), (iv) inductor default vs max-autotune-no-cudagraphs; the same 10B config in Megatron-Core/NeMo (bf16, TE kernels, TP=1) for one afternoon; production dedup pass 1 starts W7 d1 (due W10 d3) | 64 (Block 1) + CPU | G2 | lr*(N) = a x N^-b log-log fit on post-decay optima (R^2 reported); 3B/90B: the 3-point log-LR parabola optimum within 1.5x of the extrapolated fit and the bracketing LRs' post-decay losses within 0.5 %; 3B/90B post-decay loss within 0.02 nats of the L(N, D) fit from 150M/400M/1B; >= 36 % MFU at 3B; 10B config >= 6,300 tok/s/GPU on 64 GPUs (0.40); measured tok/s/GPU x 6.2816e10 / 989e12 minus 0.02 written into dr_calc.py as mfu_main before W12 (both bases reported; never above the measurement, the budget stays at 0.38); framework decided if Megatron-Core beats torchtitan by >= 3 MFU points (>= 470 tok/s/GPU); FP8 adopted only if loss gap <= 0.3 % and speedup >= 1.25x |
| W9-11 | 20 ablations at 1B/30B on v0 (incl. code 8 vs 15 %, math 1.3 vs 4 %, dedup threshold on the W5-6 corpora, batch 2M vs 4M) + the epoch-proxy ablation (2 x 1B @ 300B) + 3 confirmations at 3B/60B (code/math winner carried); GPU semantic dedup (600 GPU-h); dedup pass 1 done by W10 d3, pass 2 by W11 d7; tokenization of the frozen mix incremental from W10 d4 | 64 + CPU | G2b, G3a | G2b: recipe frozen; winner >= 0.5 % over baseline on the 8-task aggregate (HellaSwag, ARC-E, ARC-C, PIQA, OpenBookQA, CommonsenseQA, SciQ, LAMBADA; MMLU added only at 3B), above the 2-seed noise floor, confirmed at 3B; linear vs 1-sqrt decay, doc-mask on/off and 8M vs 4M batch decided; epoch rule decided (unique beats repeated by > the noise floor -> FineWeb-Edu and DCLM capped at 2.0 epochs incl. anneal, score-2 to 1.0 epoch). G3a (W11 d7): >= 300B globally shuffled tokens of the frozen mix on the PFS with checksums; else the rehearsal starts on v0 and the G5 anchor is re-based at the 1T checkpoint |
| W12 | Data freeze; tokenize and shuffle 11.27T tokens (incl. the extension pool) into uint32 shards with checksums; contamination scan; counsel signs the licence manifest incl. the generator column | CPU | G3 | per-source: measured unique tokens in our tokenizer >= the G3 min column of the stable-mix table for every source, mix re-solved by dr_calc.py (else the ordered fallback in section 3); near-dup rate <= 1 % for 1M sampled docs queried against the full-corpus LSH index at Jaccard >= 0.8; 13-gram eval overlap < 0.1 % of docs; manifest signed |
| W12-13 | 3B/300B full-recipe rehearsal at the fitted LR on the frozen mix + 3B/300B second-LR run (fit x 1.5), in parallel on 32 GPUs each (9.1 d, done W13 d3); lr*(N, D) frozen from the duration axis and the stable-phase delta fitted; 10B dress rehearsal on 64 GPUs (4 h) + node-kill/restore drill; 32k and 128k dress rehearsals on one node (CP=8, SDPA-based CP + EOS packing; 128k: one 131,072-token sequence, 20 steps); every runbook (restart, rollback, node swap, data hot-swap, spare preemption) rehearsed by the backup owner | 64 + dev | G3b | rehearsal post-decay loss within 0.02 nats of L(N, D); anneal lowers loss >= 2 % vs the stable checkpoint (this gap is the G5 delta anchor); mini-32k NIAH passes; 10B >= 6,300 tok/s/GPU on 64 GPUs; 32k path >= 3,800 and 128k path >= 1,300 tok/s/GPU; 128k step fits in memory (<= 60 GB) and completes 20 steps; restore <= 15 min; bit-identical resume |
| W13-14 | Named pre-block float; 0.5B quality classifier over the anneal candidate pools (W13 d4-W14, 5 d on 64 GPUs; dev-node overflow; due W18); if float is unused, Block 1 runs extra seeds and anneal-candidate ablations | 64 | | contract start window lets Block 2 slip to W17 at no cost |
| W15 d1-4 | Acceptance protocol (section 6) + 2-hour shakedown of the real job (~22B tokens) | 528 (Block 2) | G4 | all checks pass; >= 6,000 tok/s/GPU rolling over 2 h (= 0.381, the planning value); failing nodes swapped under the SLA |
| W15-22 | Stable phase from block day 4 (44.1 d at MFU 0.38 for 9.9T; the date rule runs it to whatever MFU delivers, from the extension pool above 9.9T); batch ramp 2M -> 4M (100B) -> 8M (500B); B_simple every 10B tokens; checkpoints every 30 min; per-source val every 10B; downstream suite every 100B on spare node 1 | 528 | G5 at 1T (W16 d2); G5b at 4T (W18 d1); G5c at 8T (W20 d5) | G5: stable-phase val loss within 0.02 nats of the 3B/300B-anchored L_stable(N, D) prediction on the 6-domain held-out set (FineWeb-Edu + DCLM subset only at 1T if the hot-swap was used, full mix at 2T) AND all 13 per-source val losses non-increasing over the last 100B; no un-recovered spike > 0.1 nats; rolling >= 6,000 tok/s/GPU; interruptions <= 1 per 2 d. G5b (block day 21.8, the option-1 deadline day): same, plus the option-1 decision (exercise only if the projected effective MFU < 0.371, i.e. the stable phase would end below 9.9T) and the batch decision from the B_simple trend (step down to 4M only). G5c: anneal-mix selection (0.9 d), candidate chosen by held-out per-source loss + the private held-out suite (due W18) |
| W22 | Anneal starts block day 50.3 (W22 d2) if >= 9.0T stable tokens (else option 2 by day 42 was exercised); 1.1T in 4.9 d; then 32k stage (0.4 d) and 128k stage (0.4 d, full AC); release base checkpoint | 528 | G6, G7 | G6 base targets (5-shot unless noted; two bands, targets not results): "ship" at MMLU >= 68, GSM8K 8-shot >= 65, HumanEval >= 45, ARC-C >= 65, HellaSwag >= 81 (Gemma-2-9B class, what 11-12T on a 2026 mix with ~23 % code+math should reach); "investigate before release" between that and the floor MMLU >= 63, GSM8K >= 55, HumanEval >= 40, ARC-C >= 60, HellaSwag >= 80 (OLMo-2-7B / DCLM-7B class at 2.6-4T, which a run that wasted two thirds of its compute could still hit); below the floor the run is not released. G7: NIAH >= 95 % at 32k and 128k; RULER-128k >= 70; short-context regression <= 1 point; else ship the 32k checkpoint |
| W13-22 (parallel) | Post-training data: 1.5M SFT examples (open sets + 2,000 expert seed examples, the only vendor work in this window), eval harness, serving design (post-training engineer starts W13); research engineer builds the private held-out suite (10 tasks x >= 500 items, hashed, decontaminated, never used in ablations) due W18 | CPU, API | | SFT set ready by W23; held-out suite frozen W18 |
| W23-24 | SFT (TRL, 8k packed, 3 epochs) + 5 ablations; first SFT checkpoint W23 d4; 20k human preference pairs ordered W23 d5 on prompts answered by that checkpoint (on-policy for the reward model; 10k/week) | 48 (Block 3) | G8 | IFEval >= 75; MT-Bench-class judge >= 7.5; GSM8K 0-shot >= 75; base suite regression <= 1 point |
| W25-26 d2 | Local judge labels 280k on-policy pairs; human pairs delivered W24 d5 and W25 d5; reward model trained W25 d6-7 on all 300k; DPO 3 rounds (round 1 on judge pairs W25 d3-4, rounds 2-3 after the RM) | 48 | G9 | length-controlled win rate vs SFT >= 60 % on 1,000 held-out prompts; harmful-request refusal >= 95 %; XSTest over-refusal <= 10 % |
| W26 d3-W29 d2 | Online RL: GRPO with verifiable rewards (verl), 5 gated campaigns (math, code tests, IFEval-style checkers, RM general, safety), 300 steps each; 21-day wall-clock budget | 48 | G10 | MATH-500 >= 50; HumanEval+ >= 65; no judge-win regression; else ship the DPO checkpoint |
| W29-30 | Safety eval, external red team, release candidate; serving pilot starts on 8 GPUs | 48 | | sev-1 red-team findings = 0, sev-2 <= 3 with mitigations; model card and licence audit signed |
| W31-34 | Serving hardening: vLLM FP8 W8A8 + FP8 KV cache, prefix caching, speculative decoding trial, 2 replicas behind a router, autoscaling, canary | 8 on-demand | G11 | FP8 parity within 0.5 points of bf16; p50 TTFT <= 300 ms, p99 <= 1 s at 64 concurrent x 1k-token prompts; >= 2,500 output tok/s per H100 (USD 0.244 per 1M output tokens at 2.20) |
| W35-38 | Pilot users, model card, dataset provenance report, runbooks, hand-off | 8 on-demand | | SLO met for 4 weeks |
| W39-40 | Buffer; wrap-up | 8 on-demand | | |

## 8. Team

Decisions: 7.7 FTE sized for zero schedule slip, because one week of slip costs USD 45,385 in team time plus up to
USD 195,149 of idle Block 2 (a 4-week program slip is USD 193,366 incl. the dev node and sits in the sensitivity
table). Pair ownership: the tech lead backs up the distributed-training engineer on the training loop; the SRE backs
up the data engineer on storage and shards; the backup, not the owner, rehearses every runbook at G3b. The 12-week
data freeze is the schedule item most likely to consume the W13-14 float and the contract window (FineWeb, DCLM and
Dolma were multi-person, multi-month efforts), so a 3-month data-pipeline contractor (USD 85,000, W1-W13) is a
planned line, not a conditional contingency call (a contractor hired at W7 is productive around W11-13, after the
freeze): the contractor owns downloads, the 131k tokenizer and the v0 corpus, PII / opt-out and the provenance
manifest; the data engineer owns global dedup and quality only. One further month (USD 28,333) is pre-authorised if
G3 slips. The post-training engineer starts W13 so the 1.5M SFT set is built in parallel with Block 2; the research
engineer owns the private held-out suite (due W18). Human SFT/preference data is bought from a vendor, not produced
in-house.

| Role | HC | Loaded USD/yr | Months | Start | USD |
|---|---|---|---|---|---|
| Program tech lead (pretraining, architecture, recipe; backs up the systems engineer) | 1.0 | 450,000 | 10 | W-2 | 375,000 |
| Distributed-training engineer (torchtitan/FSDP2, perf, checkpointing) | 1.0 | 390,000 | 9 | W1 | 292,500 |
| Data engineer (datatrove / NeMo Curator pipeline: global dedup + quality only) | 1.0 | 340,000 | 8 | W1 | 226,667 |
| Data-pipeline contractor (downloads, 131k tokenizer + v0 corpus, PII / opt-out, provenance manifest; planned) | 1.0 | 340,000 | 3 | W1 | 85,000 |
| Research engineer (ladder, ablations, anneal selection, held-out suite, long-context; later RL) | 1.0 | 340,000 | 8 | W5 | 226,667 |
| Post-training and evaluation engineer (SFT/DPO/GRPO, harness, safety) | 1.0 | 360,000 | 6 | W13 | 180,000 |
| Infra/SRE (cluster, Slurm, storage, observability, vLLM; backs up the data engineer) | 1.0 | 330,000 | 10 | W-2 | 275,000 |
| Program manager / ops (vendor contracts, annotation vendors) | 0.5 | 200,000 | 10 | W-2 | 83,333 |
| Legal / data-licence counsel, fractional (signs the licence manifest at G3) | 0.2 | 250,000 | 10 | W1 | 41,667 |
| **Total** | **7.7** | | | | **1,785,833** |

Row arithmetic: HC x loaded/yr x months / 12 (e.g. 1 x 450,000 x 10 / 12 = 375,000); rows rounded independently,
the total from unrounded values. Run rate at full strength (without the contractor, who ends W13) USD 45,385 per
week, USD 6,484 per day. "W-2" = two weeks before kickoff (contract RFQ and cluster bring-up start before W1). A data
slip past W12 costs USD 96,683 per 2 weeks (float consumed at the run rate + dev node), USD 193,366 at 4 weeks (float
+ contract window, Block 2 starts W17), then USD 27,878 per idle Block 2 day.

## 9. Top 10 risks (ranked by expected cost)

| # | Risk | Expected cost if unmitigated | Mitigation |
|---|---|---|---|
| 1 | MFU lands below the 0.38 plan (cross-replica all-reduce not overlapped at 40 GB/s, compile breaks, torchtitan under-delivers vs Megatron-Core) | at 0.36 the stable phase stops at 9.58T instead of 9.9T (10.68T total); below 0.371 USD 195,149 for option 1; every point below plan is 0.30T | Plan at 0.38 = the gate value, with 0.42 as upside, so the budget does not depend on the optimistic edge; G2 measures the 10B config on 64 GPUs in four variants in tokens/s/GPU and the planning value is replaced by the measurement minus 0.02 before W12 (never raised above it); Megatron-Core/TE comparison at G2 with a >= 3-point switch rule; 8M batch halves the all-reduce share (8.8 % of the step); profile at acceptance before committing tokens; 1.3 d slack; date-driven anneal rule with the 9.0T floor caps cost; option 1 by block day 21, option 2 by day 42; fallbacks: per-block compile off, FlexAttention or FA2, SAC off; FP8 is upside only |
| 2 | Reserved price not achieved (2.60 instead of 2.20) or vendor cannot ramp | +USD 365,568 on 913,920 reserved hours; at 2.60 both options plus a 4-week slip exceed the contingency by 178,843 | RFQ to >= 3 vendors in W1, LOI by W2, signed by W4; walk-away 2.40 (load-bearing: 2.40 + both options + a 4-week slip leaves 3,941); contingency covers 2.60 with option 1 and one idle week (755,866 of 788,129); Block 2 quoted separately at 2.40 costs +141,926; Block 1 on on-demand for two weeks (15,053) if signing slips |
| 3 | Data pipeline slips past the W12 freeze (13 sources, two global MinHash passes over 70 TB, tokenizer, PII / opt-out, decontamination, manifest on one critical path) and Block 2 starts before readiness | USD 96,683 per 2 weeks of slip (W13-14 float consumed at the run rate + dev node); 193,366 at 4 weeks (float + contract window, Block 2 starts W17); then USD 27,878 per idle Block 2 day (195,149 per week) | Contractor track W1-W13 (planned, USD 85,000) splits the path in two; tokenizer frozen W5 d1 and v0 corpus at G1 so no GPU work waits on the pipeline; dedup-threshold corpora W5-6 on CPU; classifier off the freeze path; pass 1 due W10 d3, pass 2 W11 d7, G3a (>= 300B frozen tokens) W11 d7; W13-14 named float; 2-week contract start window; data hot-swap (start on FineWeb-Edu + DCLM, swap at 1T, 1T gate on the FineWeb-Edu + DCLM subset); +1 contractor month (28,333) pre-authorised; one-week idle is a pre-authorised contingency call |
| 4 | Unique tokens come in below plan (three Common-Crawl views, per-dump-only upstream dedup, tokenizer shrink) | fewer unique tokens, quality loss at fixed cost; a late discovery forces filler into the mix | Global union-level MinHash keep-newest booked before counting (30/50/50/45 % planned losses, 0.87 shrink); W3 domain-stratified measurement across all dumps of all four CC sources (unbiased for cross-dump recrawls, where a 4-dump sample reads 5-15 % for a 30-70 % loss) replaces planning values via measured_unique.json; per-source G3 gate with 3-epoch caps (9.9T feasible at 25 % below plan); ordered fallback (score-2 to 1.0 ep = +1.82T, synthetic to 12 %, WSD cut above the 9.0T floor); epoch-proxy ablation decides repeated-HQ vs unique at G2b |
| 5 | Loss spikes or divergence late in the run | 6 h to 3 days per event | QK-norm before RoPE, z-loss 1e-4, clip 1.0, ladder-fit LR clamped to [3e-4, 6e-4] with 3e-4 as the prior, 8B-token warmup, skip-step rule, automatic rollback + 200-step skip + re-seed; 2 events in the 1.18 |
| 6 | Hardware interruptions above 1 per 2 days, stragglers, slow node replacement | ~30 min of 512 GPUs (USD 563) per extra event | 4-day acceptance with straggler scan; 2 hot-spare nodes (one kept idle, one preemptible by the main job); 30-min DCP uploaded every interval; Slurm requeue; NCCL timeout 10 min; 4-h node-swap SLA |
| 7 | Checkpoint or dataloader resume bug (silent non-determinism, repeated or skipped data) found after block day 21 | undetected quality loss over weeks; a restart from an old checkpoint after option 1 expired | Bit-identical 100-step resume at G1, G3b, G4; per-step data-order hash in W&B; dataloader + RNG state in DCP; checksums on every shard and checkpoint; option 2 (by day 42) and the 9.0T anneal floor give the restart a compute remedy |
| 8 | Evaluation contamination, a mis-specified quality gate or anneal over-tuning misleads a decision | wrong mix locked at W12 or at 8T; a G5 gate that fails by construction at block day 8 (USD 27,878/day) | 13-gram decontamination; private held-out suite (10 tasks x >= 500 items, research engineer, due W18) kept out of every ablation; G5 scored against stable-phase curves with the ladder delta, never post-decay ones; instruction-style capped at 12 % of the anneal; 4 candidates scored, not 1; G6 in two bands so a run that wasted compute cannot pass as a success |
| 9 | Licence / generator-terms / opt-out / PII failure found late | re-training a slice, a forced "Llama-" model name, or legal exposure | Permissive sources only, with a generator-model column in the manifest (Llama 3.1 naming clause, OpenAI output clauses, Qwen attribution); defaults until counsel clears: keep Nemotron-CC synthetic and Cosmopedia (Apache-2.0 generators), drop the GPT-4o-derived Tulu-3 subsets, accept a "Llama-" prefix or swap OpenMathInstruct-2; robots.txt at crawl time + HF/Spawning opt-out list refreshed weekly; SWH opt-out list and attribution for The Stack v2; counsel's W3 memo; PII scrub; per-source shard sets droppable by remix; counsel signs the manifest incl. the generator column at G3 |
| 10 | Post-training misses bars (RL reward hacking, safety) or long-context regresses | 1-2 weeks of Block 3; re-run 0.8 d of long-context | Verifiable rewards first, KL penalty, 5 gated campaigns with the DPO checkpoint as fallback; 20 % short-context replay; 128k memory fit and the CP kernel path (SDPA-based CP + EOS packing, ring-flash-attention as upside) proven at G3b in tok/s/GPU; G7 regression gate; ship 32k if 128k fails |

Also tracked: key-person loss (pair ownership, runbooks; contingency funds a 3-month contractor, USD 97,500),
attention kernel paths (FA3 custom op vs FlexAttention at 4k decided at G1; SDPA-based CP vs ring-flash-attention at
32k/128k decided at G3b; all pinned by commit), framework switch at G2 (two engineer-weeks, USD 15,000),
preference-data price (vendor quotes by W3; USD 15 per pair would add 200,000), tokenizer defect after the freeze
(digit/whitespace tests at G1), vLLM FP8 quality drop (parity gate at G11).

## 10. Assumptions

| Assumption | Value | Note |
|---|---|---|
| H100 SXM dense bf16 peak | 989 TFLOP/s | brief |
| USD per GPU-hour, reserved | 2.20 | one master contract covering 913,920 GPU-h over W1-W40 (dev node to W40; the 64/528/48-GPU blocks end W30; a capacity ramp 8 -> 72 -> 536 -> 56 -> 8); RFQ target 2.20, walk-away 2.40 (load-bearing); LOI W2, signed W4, Block 2 date fixed W6 |
| USD per GPU-hour, on-demand / spot | 2.90 / 1.50 | serving tail; spot for ablations and evals only |
| MFU, main run (bf16, seq 4,096, HSDP, FA3 varlen, 8M batch) | 0.38 over 6ND + attention (0.356 on 6ND) = 6,000 tok/s/GPU, planning value and acceptance gate | G2 gate 6,300 tok/s/GPU (0.40) on 64 GPUs; planning := G2 - 0.02 before W12, never raised; 0.42 upside = 12.5T; MFU = tokens/s x 6.2816e10 / 989e12 (torchtitan's number reads x1.064) |
| MFU, 32k stage / 128k stage (CP=8) | 0.35 (SAC op, mb 2) = 3,800 tok/s/GPU / 0.25 (full per-block AC, mb 1) = 1,300 tok/s/GPU | 128k with SAC(op) would need 84.8 GB |
| MFU, ladder 150M / 400M / 1B / 3B | 0.20 / 0.25 / 0.32 / 0.38 | small matmuls; batches 0.5M / 1M / 2M / 4M |
| MFU, SFT/RM/DPO; RL trainer | 0.30; 0.25 | |
| Global batch / warmup | 8,388,608 tokens (grad-accum 2) after a two-phase ramp 2M -> 4M (100B) -> 8M (500B); warmup 3,610 steps = 8B tokens | 4M (grad-accum 1) fallback only on a > 0.5 % 1B ablation penalty; LR 3e-4 prior, clamp [3e-4, 6e-4] |
| Overhead factor: main / short runs and long-context / post-training / online RL | 1.18 / 1.25 / 1.30 / 3.0 | build-up in section 5 |
| Interruption rate | 0.5 per day per 512 GPUs | 25.4 events over the run; 15 min lost + 15 min restart each |
| Checkpoint cadence | 30 min async DCP to NVMe, each uploaded to object storage within the interval | 65 MB/s aggregate; 657 steps at 8M |
| Inter-node bandwidth | 50 GB/s per GPU line rate; 40 GB/s sustained by a 64-node ring all-reduce | 0.193 / 0.241 s per step (8.8 % of the 2.74 s step) |
| Storage: object store / parallel FS | USD 21 / 80 per TB-month | 120 TB PFS for 5 months; 913 TB-months object |
| Egress | USD 50 per TB | inbound and HF downloads free |
| CPU core-hour / RAM node (1.5 TB) hour | USD 0.045 / 4.00 | 768-core partition 8 weeks; 3 RAM nodes 4 weeks |
| Text size and processing | 4.5 bytes/token; 2.5 core-h per GB; 2 production passes = 348,502 core-h + 28,676 core-h pre-production (W3 measurement 5,794; dedup-threshold corpora 20,857; v0 tokenization 2,025) = 377,179 core-h | 37 % of the partition; the partition implies 307 GB/h = 9.5 days per pass, G1 >= 300 GB/h; pass 1 due W10 d3, pass 2 W11 d7, G3a >= 300B frozen tokens by W11 d7 |
| Dedup planning losses | FineWeb-Edu 30 %, DCLM 50 %, Nemotron-CC real 50 %, score-2 45 %; keep newest | replaced by the W3 domain-stratified measurement across all dumps of all four CC sources (measured_unique.json) |
| Tokenizer shrink on web sources | 0.87 (our 131k BPE vs ~50k source tokenizers) | code, math, papers, wiki, books, Cosmopedia at 1.0 |
| Epoch caps | 3 stable on web/code/math/papers; 1 synthetic and filler; 2 PDFs and multilingual; 4 incl. anneal on any source or sub-pool | data-constrained scaling (<= 4 epochs near-free at <= 100B scales); the epoch-proxy ablation (1B x 300B) tests it at G2b |
| Anneal token floor | 9.0T stable tokens | binds below MFU 0.341 or 5.3 lost days; option 1 trigger 0.371; remedy = option 1 (2.20, by day 21) or option 2 (<= 2.40, by day 42) |
| Human data unit prices | USD 5.00 per reviewed preference pair (two vendor quotes by W3; 15.00 would add 200,000); 25 per expert SFT example; 10 per human eval | 20k pairs on W23 d4 SFT outputs, ordered W23 d5, delivered 10k/week; 280k further pairs are on-policy, judge-labelled |
| vLLM rates | 3,000 tok/s/GPU bf16 rollouts (RL); 2,500 output tok/s/GPU FP8 (serving) | USD 0.244 per 1M output tokens at 2.20 |
| Team loaded cost | 200k-450k per role per year; 3-month data contractor at 340k/yr | section 8 |
| Timeline | 40 weeks = 9.2 months | includes the W13-14 pre-block float, the 2-week contract start window (Block 2 may slip to W17 inside the plan) and the W39-40 buffer |

Structured summary (also in `decision_record.json`): d_model 4096, n_layers 40, n_heads 32, n_kv_heads 8, ffn_hidden
14336, vocab 131,072, params_total 9.798B, params_nonembed 8.724B, tokens_pretrain 11.0T planned at MFU 0.38 (9.9T
stable + 1.1T anneal; 12.0T design point at MFU 0.404, 12.5T at 0.42; +50B at 32k, +20B at 128k), unique data 8.73T in
our tokenizer (avg 1.62 epochs, max 2.73; extension pool 2.53T), global batch 8,388,608, n_gpus 512 (+16 spare), MFU
0.38 planning = 6,000 tok/s/GPU (G2 gate 6,300 on 64 GPUs; planning := G2 - 0.02 at W12), USD 2.20/GPU-h reserved,
main run 602,646 GPU-h over 49.0 days, compute USD 2,049,600 (829,413 GPU-h attributed of 927,360 bought), team USD
1,785,833 (7.7 FTE), contingency USD 788,129 (15.8 %), total USD 5,000,000, 40 weeks.
