## 08. Inference serving architecture and cost optimisation

Covers: inference serving architecture (`code/serving_capacity.py`) and cost optimisation techniques across the whole program. Numbers from DR sections 1 and 5 (serving assumptions 2,500 tokens/s/GPU, USD 2.20 reserved / 2.90 on-demand) and the calculator output below.

### Decisions

- **vLLM is the serving engine, one model replica per H100, FP8 weights and FP8 KV cache.** A 9.8B model in FP8 is 9.8 GB; the remaining 63 GB of KV budget holds 188 concurrent 4k-context sequences. One replica per GPU (no tensor parallelism) keeps failure domains small and scaling linear. SGLang is the drop-in alternative if its prefix-cache hit rate wins on our traffic; TensorRT-LLM only if a latency SLO cannot be met otherwise.
- **Quantise with llm-compressor (FP8 W8A8, dynamic per-token activations), gate on accuracy.** Any benchmark in the G6 table that drops more than 0.5 points versus bf16 blocks the FP8 build; INT4 (AWQ) is a separate cheaper tier with its own gate (1.5 points).
- **Planning throughput is 2,500 output tokens/s/GPU at the SLO, not the 8,200 the memory-bound decode model allows.** The gap pays for prefill interference, p99 latency headroom and uneven traffic; it is re-measured on the pilot and the DR's serving line is updated.
- **Kubernetes with one Deployment per model tier, HPA on queue depth, a prefix-aware router in front.** Autoscaling to zero for batch-only tiers; spot replicas for offline batch inference.
- **Cost optimisation is a program-wide table, not a serving afterthought**: the two largest levers are the reserved contract (USD 650k vs on-demand) and MFU (every 0.01 of MFU on the main run is 15,900 GPU-h, USD 35k).

### Procedure

1. **Export and quantise (W30-W31).** From the G6-signed checkpoint: bf16 HF-layout safetensors (section 02) -> `llm-compressor` FP8 recipe (`QuantizationModifier(targets="Linear", scheme="FP8_DYNAMIC", ignore=["lm_head"])`) -> `vllm serve --quantization fp8 --kv-cache-dtype fp8`. Run the G6 table on bf16, FP8 and INT4 builds under the same harness; file the deltas.
2. **Capacity test (W31, 8 on-demand GPUs).** `vllm bench serve` (or `genai-perf`) with the pilot traffic profile (prompt 1.2k median / 6k p95 tokens, output 350 median / 1.5k p95) at rising concurrency until p99 TTFT > 1.5 s or p99 inter-token latency > 60 ms; the throughput at that point is the per-replica capacity written into the autoscaler. Expect 2,000-3,500 output tokens/s per GPU depending on prefix-cache hit rate.
3. **Build the serving stack (W31-W34).** Diagram below. Gateway (auth, per-key rate limits, request logging, PII redaction toggle), router (consistent hashing on the conversation id so multi-turn requests hit the replica that holds the prefix cache; falls back to least-loaded), vLLM replicas, Prometheus scraping vLLM's `/metrics`, Grafana, Loki, Alertmanager (same stack as section 06).
4. **Rollout policy.** Every new build goes canary (5% of traffic, 24 h) with automatic rollback on error rate > 0.5%, p99 TTFT regression > 20%, or a drop in the online quality signal (thumbs-down rate, judge-sampled 1% of traffic). Shadow mode for post-training candidates before canary.
5. **Pilot (W35-W38, 8 on-demand GPUs, 13,440 GPU-h, USD 38,976).** Internal users plus one design partner; measure cache hit rate, real tokens/s per GPU, cost per 1M tokens; hand over runbooks and the capacity model to the owning team at W38.
6. **Long-context tier (optional, W37).** A second Deployment with `--max-model-len 131072`, chunked prefill, 5 concurrent sequences per GPU, strict per-key quotas; priced separately.

### Architecture

```text
 clients (SDK / HTTP)                       offline batch (files -> results)
       |                                              |
       v                                              v
 +-------------+   +-------------------+   +----------------------------+
 | API gateway |-->| prefix-aware      |   | batch runner (vLLM offline |
 | auth, rate  |   | router (conv-id   |   | engine on spot replicas)   |
 | limits, log |   | hashing, least-   |   +----------------------------+
 +-------------+   | loaded fallback)  |
                   +---------+---------+
                             |
        +--------------------+---------------------+
        v                    v                     v
 +--------------+    +--------------+       +--------------+
 | vLLM replica |    | vLLM replica |  ...  | vLLM replica |   1 x H100 each, FP8 W8A8,
 | 9.8B FP8     |    | 9.8B FP8     |       | 128k tier    |   FP8 KV, prefix cache,
 | 4k/8k tier   |    | 4k/8k tier   |       | 5 seqs/GPU   |   spec-decode optional
 +------+-------+    +------+-------+       +------+-------+
        |                   |                      |
        +--------- /metrics -> Prometheus -> Grafana / Alertmanager
        |
 +--------------+   +---------------------+   +------------------+
 | model registry|  | safety filters      |   | request store    |
 | (versioned   |   | (input/output       |   | (sampled 1 % for |
 | safetensors) |   | classifiers, PII)   |   | judge + eval)    |
 +--------------+   +---------------------+   +------------------+
```

Kubernetes: one `Deployment` per tier (`llm10b-chat-fp8`, `llm10b-long-fp8`, `llm10b-batch`), `nvidia.com/gpu: 1` per pod, readiness probe on `/health` plus a warm-up request, `HorizontalPodAutoscaler` on `vllm:num_requests_waiting` (target 8 per replica) with a 5-minute scale-down window, `PodDisruptionBudget` 80%. Model weights come from the registry bucket into a node-local cache (9.8 GB, 20 s on a 400G NIC) so a cold pod is serving within 90 s.

### vLLM launch

```bash
vllm serve /models/llm10b-dpo-v1-fp8 \
  --served-model-name llm10b \
  --dtype bfloat16 --quantization fp8 --kv-cache-dtype fp8 \
  --max-model-len 8192 --max-num-seqs 192 --max-num-batched-tokens 8192 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching --enable-chunked-prefill \
  --tool-call-parser llm10b --enable-auto-tool-choice \
  --speculative-config '{"method": "eagle", "model": "/models/llm10b-eagle-v1", "num_speculative_tokens": 3}' \
  --disable-log-requests --port 8000
```

Flag rationale: `--max-num-seqs 192` matches the 188-sequence KV budget at 4k with FP8 KV; `--max-num-batched-tokens 8192` bounds prefill chunks so decode steps are not starved (TPOT stays under 60 ms); prefix caching gives 40-70% prompt-token savings on multi-turn and system-prompt-heavy traffic; EAGLE speculative decoding (a small draft head trained on 200M tokens of the model's own outputs, 2 GPU-days) gives 1.6-2.2x decode speed at batch <= 32 and is disabled automatically by vLLM at high batch where it stops paying; `--tool-call-parser` maps the `<|tool_call|>` tokens from section 07 to the OpenAI tool-call schema.

### Capacity model

From `python3 code/serving_capacity.py` (H100 80 GB, 90% memory utilisation, 4 GB workspace, 60% of HBM bandwidth achieved in decode, 50% of peak FLOPs in prefill):

| Metric | FP8 weights + FP8 KV | BF16 weights + BF16 KV |
|---|---|---|
| Weights | 9.8 GB | 19.6 GB |
| KV cache per token (2 x 40 layers x 8 KV heads x 128) | 80 KB | 160 KB |
| KV budget | 63.2 GB | 53.4 GB |
| Concurrent sequences at 4k / 8k / 32k / 128k | 188 / 94 / 23 / 5 | 79 / 39 / 9 / 2 |
| Decode, batch 128 at 2k context (memory-bound bound) | 8,227 tok/s | 4,113 tok/s |
| Decode, batch 32 at 8k context | 2,057 tok/s | 1,028 tok/s |
| Prefill | 50,494 tok/s | 25,234 tok/s |
| TTFT for a 2k prompt (prefill only) | 41 ms | 81 ms |
| Cost per 1M output tokens at the 2,500 tok/s plan | USD 0.244 reserved / 0.322 on-demand | same plan number |
| Cost per 1M input tokens (prefill-bound) | USD 0.012 | USD 0.024 |

One-line arithmetic: KV per token = 2 x 40 x 8 x 128 x 1 B = 81,920 B; concurrency at 4k = 63.2e9 / (81,920 x 4,096) = 188; decode step at batch 128 and 2k context reads 9.8 GB + 128 x 2,048 x 80 KB = 31.3 GB per step at 2.01 TB/s = 15.6 ms, 128 / 0.0156 = 8,227 tok/s; USD per 1M output tokens = 2.20 / (2,500 x 3,600) x 1e6 = 0.244.

SLOs for the chat tier: p50 TTFT <= 300 ms, p99 TTFT <= 1.5 s, p99 inter-token latency <= 60 ms, availability 99.9% monthly, error rate < 0.1%. Alerts mirror section 06: queue depth, TTFT and TPOT percentiles, KV-cache usage > 90%, GPU errors, replica restarts.

Safety and privacy: input and output classifiers on the gateway (prompt-injection and abuse classes, PII in outputs), per-key content policy, request logging with 30-day retention and the 1% judge sample stripped of PII before storage.

### Cost optimisation

Baseline for the savings column: a "naive" execution of the same scope (on-demand GPUs, no pilot ladder, cosine schedule with one full re-run risk, MFU 0.30, bf16 serving, no prefix caching). Program numbers from the DR.

| Technique | Where | Saving (USD, program) | Effort | Risk |
|---|---|---|---|---|
| One reserved master contract at 2.20 instead of on-demand 2.90 (913,920 GPU-h) | compute | 640,000 | contract negotiation, LOI by W2 | idle hours if the schedule slips (hot spares and float cover 1.3 days) |
| MFU 0.38 instead of 0.30 on the main run (6ND + attention basis) | training | 350,000 (159,000 GPU-h) | torchtitan tuning, FA3 custom op, chunked CE, compile | the G2 gate makes it measurable before the block starts |
| WSD schedule with a date-driven anneal instead of a fixed cosine | training | avoids a re-run (up to 1,330,000) | none | anneal start rule must be followed |
| Pilot ladder (150M-3B) sets LR and batch, muP-style transfer | training | avoids 2-3 trial runs at 10B (each 1-day trial = 27,878) | 8 weeks of Block 1 | ladder must use the real data mix |
| Selective activation checkpointing instead of full | training | 10% of main-run step time (about 60,000 GPU-h, 132,000) | torchtitan config | memory headroom 24 GB confirms the fit |
| Checkpoint every 30 min async instead of 10 min sync | training | 1.5% of step time (9,000 GPU-h, 20,000) | DCP async | 15 min more lost work per interruption (booked) |
| In-run evals on the spare node, not inside the job | training | 0.5-1% of step time (15,000) | eval harness on exports | none |
| Reuse processed public corpora instead of a raw crawl | data | 3 months of a data team (about 250,000) | licence review | dependency on upstream filters (audited) |
| GPU dedup (NeMo Curator) for the MinHash stage | data | 2 weeks of the CPU partition (23,000) | 7,622 GPU-h in Block 1 | none |
| Epoch caps and an extension pool instead of buying more unique data | data | 0 cash, protects quality | DR gate G3 | the 3-epoch cap is a quality guard, not a saving |
| DPO before online RL; RL only with verifiable rewards | post-training | 48 GPUs x 21 days bounded (53,222) instead of open-ended | verl config | RL may be cut short by the early-stop rule |
| Local Apache-2.0 judge instead of API judges for 280k pairs | post-training | 60,000-120,000 of API spend | 16 GPUs for 5 days | judge bias (validated on 20k human pairs) |
| FP8 W8A8 + FP8 KV serving | serving | 2x replicas per unit of traffic (half of all serving GPU cost) | llm-compressor, accuracy gate | 0.5-point accuracy gate |
| Prefix caching | serving | 40-70% of prompt tokens on multi-turn traffic | one flag plus the conv-id router | none |
| Speculative decoding (EAGLE) | serving | 1.6-2.2x decode at low batch (latency tier) | 2 GPU-days to train the draft head | disabled by vLLM at high batch |
| Autoscale to zero, spot for batch | serving | 30-50% of the serving bill outside peak hours | Kubernetes HPA | cold start 90 s (warm pool of 1) |
| Right-sized context tiers (8k default, 128k separate) | serving | 2-4x concurrency per GPU on the default tier | routing by requested max length | none |

Sum of the cash savings that are realised in the base plan (contract, MFU, SAC, checkpoints, evals, data reuse, GPU dedup, local judge): about USD 1.5M against the same scope executed naively; the WSD and ladder lines are avoided risk rather than booked savings. The DR's 15.8% contingency (USD 788,129) exists because the three largest risks (price, MFU, schedule) are the same three levers.

### Reference implementation

```python
def kv_bytes_per_token(cfg: ServingConfig) -> int:
    return 2 * N_LAYERS * N_KV_HEADS * HEAD_DIM * cfg.kv_bytes


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
```

The smoke test asserts the KV bytes per token (163,840 bf16 / 81,920 FP8), the weight sizes, the DR's USD 0.244 and 0.322 per million output tokens, and that FP8 more than doubles concurrency.

### Checklist

- [ ] FP8 and INT4 builds pass their accuracy gates against bf16 on the G6 table; deltas filed.
- [ ] Capacity test done with the pilot traffic profile; per-replica capacity and SLO headroom written into the HPA.
- [ ] Gateway, router, replicas, metrics, alerts and canary rollout deployed; rollback tested with an injected bad build.
- [ ] Pilot: measured tokens/s per GPU, cache hit rate and USD per 1M tokens reported against the 2,500 / 0.244 plan; DR serving line updated.
- [ ] Cost table reviewed monthly by the PM; realised savings vs plan recorded.
