# 10B-parameter LLM: production plan

A step-by-step roadmap for building, training, aligning and serving a 9.8B-parameter dense decoder-only language model on NVIDIA H100s with an all-in budget of USD 5,000,000. Every number in this plan is produced by `dr_calc.py` and recorded in `decision-record.md`; the sections below are the execution plan built on those numbers. All code under `code/` runs on CPU-only PyTorch in under 30 seconds per file and is the executable specification for the production configs.

## Executive summary

We train a 9.80B dense transformer (d_model 4096, 40 layers, GQA 32/8, SwiGLU 14336, 131k vocabulary) on 11.0T tokens of deduplicated public data at 4k context, extend it to 32k and then 128k context, fine-tune it (SFT, DPO, GRPO on verifiable rewards), and serve it in FP8 on vLLM at one replica per H100.

The main run uses 512 H100 SXM GPUs (64 nodes) plus 16 hot spares for 49 days at a planning MFU of 0.38 (6,000 tokens/s/GPU, 3.06M tokens/s), inside an 8-week reserved block. The whole program is 40 weeks: six weeks of data, tokenizer and contracts; eight weeks of pilots on 64 GPUs (scaling ladder, ablations, a 3B rehearsal); the 8-week main-run block; eight weeks of post-training on 48 GPUs; eight weeks of serving hardening and pilot; two weeks of buffer.

Budget: USD 2,049,600 compute (41%), 1,785,833 team (7.7 FTE, 36%), 361,438 data, storage, human data, serving infrastructure and software (7%), 788,129 contingency (16%). GPU hours are bought as one reserved master contract at USD 2.20 per GPU-hour.

Six go/no-go gates (G1 data, G2 throughput and framework, G3 unique data, G4 cluster acceptance, G5 loss-vs-prediction, G6 release) each have a number; failing a gate stops spend, not the plan.

What the reader gets at the end: a base model checkpoint (11T tokens, 128k context) with an exact parameter table and training record; an instruction-tuned, preference-optimised model that passes the G6 table; FP8 and INT4 serving builds with a capacity model; and the runbooks, dashboards and alerting that operated the run.

## Key numbers

| Item | Value |
|---|---|
| Model | d_model 4096, 40 layers, 32 heads / 8 KV heads, head_dim 128, SwiGLU 14336, vocab 131,072, untied embeddings |
| Parameters | 9,798,236,160 total; 8,724,494,336 non-embedding |
| Pretraining tokens | 11.0T at seq 4,096 (9.9T stable + 1.1T anneal, WSD schedule) + 50B at 32k + 20B at 128k |
| Tokens per parameter | 1,123 (56x Chinchilla) |
| Unique data | 8.73T tokens after global dedup; 1.62 epochs average; caps 3 (stable) / 4 (incl. anneal) |
| Global batch | 8,388,608 tokens (512 GPUs x 2 x 4,096 x grad-accum 2); ramp 2M -> 4M -> 8M |
| Optimiser | AdamW (0.9, 0.95), peak LR 3e-4, warmup 8B tokens, 1-sqrt decay over the last 10% to 1%, wd 0.1, clip 1.0 |
| Cluster | 512 H100 SXM 80 GB (64 nodes) + 16 hot spares; 8x 400G NDR IB per node; FSDP2 HSDP shard 8 x replicate 64 |
| Throughput | MFU 0.38 = 6,000 tokens/s/GPU (gate), 3.06M tokens/s, 2.738 s per step |
| Main run | 602,646 GPU-h incl. 1.18 overhead = 49.0 days |
| GPU price | USD 2.20/GPU-h reserved (walk-away 2.40); 2.90 on-demand |
| Compute | USD 2,049,600 for 927,360 GPU-h bought |
| Team | USD 1,785,833 (7.7 FTE loaded) |
| Contingency | USD 788,129 (15.8%) |
| Total | USD 5,000,000 |
| Timeline | 40 weeks (9.2 months); main run W15-W22 |
| Serving | FP8 on vLLM, 1 GPU per replica, USD 0.244 per 1M output tokens at 2,500 tokens/s/GPU |

## System architecture

A. Program data flow:

```text
 public datasets (FineWeb-Edu, DCLM, Nemotron-CC, FinePDFs, Stack v2, FineWeb-2, math, papers, wiki, books)
      |  download + licence manifest (sec 04)
      v
 [filter: URL, language, Gopher/C4/FineWeb rules, quality score, PII]      768-core CPU partition
      |
      v
 [dedup: URL, exact SHA-256, MinHash LSH 5-gram 112 hashes 14x8, decontamination 13-gram]
      |
      v
 [tokenize: 131k byte-level BPE -> uint32 shards + manifests]  (sec 03)      45.1 TB on parallel FS
      |
      v
 [pretrain 9.9T stable @4k] -> [anneal 1.1T on HQ mix] -> [32k 50B, CP=8] -> [128k 20B]   (sec 05, 06, 09)
      |        512 H100, FSDP2/HSDP, 30-min DCP checkpoints, async evals on the spare node
      v
 [SFT 1.2M conv] -> [RM + on-policy pairs] -> [DPO 300k pairs] -> [GRPO verifiable rewards]   (sec 07)
      |        48 H100, Block 3
      v
 [G6 release gate] -> [export HF safetensors] -> [FP8 / INT4 quantise + accuracy gate]        (sec 08)
      |
      v
 [vLLM replicas on Kubernetes, prefix-aware router, gateway, canary rollout, pilot]
```

B. Training cluster (detail in section 05):

```text
            login x2    slurm ctrl (HA)    monitoring (prometheus/grafana/loki)    eval/spare x2 nodes
               |              |                     |                                  |
   ============+==============+=====================+==================================+====  mgmt / storage Ethernet
               |              |                     |                                  |
   +-----------+--------------+---------------------+----------------------------------+-----------+
   |  64 compute nodes: 8x H100 SXM 80 GB, NVSwitch, 2 TB RAM, 8x 3.84 TB NVMe, 8x ConnectX-7 400G   |
   +-----|---------|---------|---------|---------|---------|---------|---------|---------------------+
       rail0     rail1     rail2     rail3     rail4     rail5     rail6     rail7     (one NIC per GPU)
         |         |         |         |         |         |         |         |
   +-----+---------+---------+---------+---------+---------+---------+---------+-----+
   |              NDR InfiniBand, 8 rails, 2-tier non-blocking fat tree, SHARP          |
   +------------------------------------------------------------------------------------+
   parallel FS 120 TB (tokens, rolling checkpoints)      object store (raw data, permanent checkpoints, exports)
```

C. Software stack:

```text
 +----------------------------------------------------------------------------------------+
 | orchestration   Slurm 24.x (reservations, requeue, prolog health checks), enroot/pyxis   |
 +----------------------------------------------------------------------------------------+
 | training        torchtitan (FSDP2 + HSDP mesh, SAC, torch.compile), torch 2.7+, CUDA 12.8 |
 |                 flash-attn 3 varlen custom op, NCCL 2.26+ (SHARP), fused AdamW            |
 +----------------------------------------------------------------------------------------+
 | checkpoint      torch.distributed.checkpoint async -> NVMe -> object store; verify job  |
 +----------------------------------------------------------------------------------------+
 | data            datatrove / NeMo Curator (filters, dedup), HF tokenizers, uint32 shards,|
 |                 resumable packed loader (cu_seqlens)                                    |
 +----------------------------------------------------------------------------------------+
 | post-training   TRL (SFT, DPO), verl (GRPO) with vLLM rollouts, lm-evaluation-harness    |
 +----------------------------------------------------------------------------------------+
 | serving         vLLM (FP8, prefix cache, EAGLE), Kubernetes HPA, gateway + router        |
 +----------------------------------------------------------------------------------------+
 | observability   JSON-lines metrics, W&B, Prometheus + dcgm-exporter, Grafana, Loki,      |
 |                 Alertmanager -> PagerDuty / Slack                                        |
 +----------------------------------------------------------------------------------------+
```

## Roadmap and gates

1. **W1-W2: contracts and staffing.** LOI for the master contract (913,920 reserved GPU-h) by W2; dev node (8 GPUs) live; counsel starts the licence manifest; data downloads start (section 04).
2. **W3-W4: tokenizer and legal.** Tokenizer trained on a 40 GB stratified sample and evaluated against Llama 3 (section 03); counsel's W3 memo; W3 domain-stratified dedup measurement; contract signed by W4.
3. **W5-W6: v0 corpus and image.** Tokenizer frozen W5 d1; v0 corpus >= 1.5T tokens tokenized; container image pinned; monitoring stack up (section 06). **G1 (end W6): v0 >= 1.5T tokens, tokenizer invariants pass, dedup rates published.**
4. **W7-W9: ladder on 64 GPUs (Block 1).** 150M/400M/1B/3B models at 20-40 tokens/param with the main-run schedule; LR fit; 1B x 300B epoch-proxy ablation. **G2 (W9): the 10B config reaches >= 6,300 tokens/s/GPU on 64 GPUs; framework decision (torchtitan or Megatron-Core); planning MFU := measurement - 0.02.**
5. **W10-W11: production data passes.** Pass 1 (filters) due W10 d3, pass 2 (dedup, decontamination) due W11 d7. **G3a (W11 d7): >= 300B tokens of the frozen mix tokenized.**
6. **W12-W13: rehearsal.** **G3 (W12 d1): per-source unique tokens >= plan / caps; licence manifest signed.** 3B x 300B rehearsal on the frozen mix with a forced node kill at hour 20 (sections 05, 06, 09); anneal-mix candidates selected.
7. **W13-W14: float.** Two weeks of pre-block float absorb data or contract slips; FP8 pilot and 3B ablations fill the GPUs otherwise.
8. **W15: Block 2 acceptance (4 days, billed).** Node prolog on 66 nodes, fabric tests, **G4: >= 6,000 tokens/s/GPU for 2 h on 512 GPUs with checkpointing and logging on.**
9. **W15-W22: main run.** Milestones 1T at W16 d2, 4T at W18 d1, 8T at W20 d5. **G5 at 1T/4T/8T: |validation loss - ladder prediction| <= 0.02 nats; a failure at 1T stops the run for a recipe review.** Option 1 (+1 week at 2.20) decision by W18 d1 if MFU < 0.371. Anneal from W22 d2 (block day 50.3); then 200B anneal-mix selection, 32k and 128k stages.
10. **W23-W30: post-training (Block 3, 48 GPUs).** SFT W23, RM W23-W24, on-policy pairs W24, DPO W25, GRPO W26-W29, red team W28-W29. **G6 (W30): release table (section 07) signed.**
11. **W31-W34: serving hardening.** FP8/INT4 builds and accuracy gates, capacity test, gateway/router/replicas, canary pipeline (section 08).
12. **W35-W38: pilot and hand-off.** 8 on-demand GPUs; measured cost per 1M tokens; runbooks and capacity model handed to the owning team.
13. **W39-W40: buffer.**

```text
week   1   3   5   7   9   11  13  15  17  19  21  23  25  27  29  31  33  35  37  39
       |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |   |
data   ####====####..................................................................   contracts, tokenizer, v0 (G1 W6)
B1     ........########xx..........................................................   ladder, G2 W9, passes, G3 W12, float
B2     ................########....................................................   acceptance G4, main run, G5, anneal, long ctx
B3     ........................########............................................   SFT, DPO, GRPO, G6 W30
serve  ................................########....................................   hardening W31-34, pilot W35-38
buffer ........................................##..................................
dev    ########################################################################....   8-GPU dev node all program
```

## Budget and compute

| Line item | USD | % |
|---|---|---|
| GPU compute: 4 reserved blocks + on-demand serving tail (incl. 16 hot spares) | 2,049,600 | 41.0 |
| Team (7.7 FTE loaded, incl. 3-month data-pipeline contractor) | 1,785,833 | 35.7 |
| Data processing: 768-core CPU cluster 8 weeks + 3 RAM nodes | 54,513 | 1.1 |
| Storage: object store 913 TB-months + parallel FS 120 TB x 5 months | 67,181 | 1.3 |
| Egress and DR replication | 4,744 | 0.1 |
| Human data, evaluation, red team, judge API | 220,000 | 4.4 |
| Serving pilot non-GPU infrastructure | 15,000 | 0.3 |
| Software / SaaS (W&B, CI, paging, HF) | 15,000 | 0.3 |
| Contingency (residual) | 788,129 | 15.8 |
| Total | 5,000,000 | 100.0 |

| Block | GPUs | Weeks | GPU-hours | USD/GPU-h | USD |
|---|---|---|---|---|---|
| Dev node, W1-W40 | 8 | 40 | 53,760 | 2.20 | 118,272 |
| Block 1: ladder, ablations, rehearsal, data GPU jobs, W7-W14 | 64 | 8 | 86,016 | 2.20 | 189,235 |
| Block 2: main run (512 compute + 16 spare), W15-W22 | 528 | 8 | 709,632 | 2.20 | 1,561,190 |
| Block 3: SFT, RM, DPO, GRPO, judge, evals, W23-W30 | 48 | 8 | 64,512 | 2.20 | 141,926 |
| Serving pilot on-demand, W31-W40 | 8 | 10 | 13,440 | 2.90 | 38,976 |
| Total bought | | | 927,360 | | 2,049,600 |

Main-run arithmetic: 11.0e12 tokens x 62,815,948,800 FLOP/token = 6.91e23 FLOP; / (989e12 x 0.38) / 3,600 = 510,717 GPU-h ideal; x 1.18 overhead = 602,646 GPU-h; / 512 / 24 = 49.0 days. Attributed utilisation of the bought hours is 89%.

Contingency is pre-allocated in order to: GPU price up to 2.60 (365,568), MFU below 0.371 (option 1, +1 week of Block 2, 195,149), a late restart (option 2, 212,890), a 4-week program slip (193,366); see `decision-record.md` section 1 for the full sensitivity table.

## Team and ownership

| Role | FTE | Months | USD | Owns |
|---|---|---|---|---|
| Program tech lead (pretraining, architecture, recipe) | 1.0 | 10 | 375,000 | DR, gates G2/G5, sections 02 and 05 recipe, rollback decisions |
| Distributed-training engineer (torchtitan/FSDP2, perf, checkpointing) | 1.0 | 9 | 292,500 | sections 05 and 06 code, G2/G4 throughput, FA3 op |
| Data engineer (datatrove / NeMo Curator: dedup + quality) | 1.0 | 8 | 226,667 | section 04, G3 |
| Data-pipeline contractor (downloads, tokenizer, v0, PII, provenance) | 1.0 | 3 | 85,000 | section 03, acquisition, G1 |
| Research engineer (ladder, ablations, anneal mix, held-out suite, long context; later RL) | 1.0 | 8 | 226,667 | ladder fits, G5 prediction, anneal selection, GRPO |
| Post-training and evaluation engineer (SFT/DPO/GRPO, harness, safety) | 1.0 | 6 | 180,000 | section 07, G6 |
| Infra/SRE (cluster, Slurm, storage, observability, vLLM) | 1.0 | 10 | 275,000 | cluster acceptance, section 06 stack, section 08 serving, on-call lead |
| Program manager / ops (vendor contracts, annotation vendors) | 0.5 | 10 | 83,333 | contract, budget tracking, vendors, change requests |
| Legal / data-licence counsel (fractional) | 0.2 | 10 | 41,667 | licence manifest, W3 memo, takedowns |
| Total | 7.7 | | 1,785,833 | |

Backups: tech lead <-> distributed-training engineer; infra/SRE <-> data engineer. On-call during Block 2 rotates between the distributed-training engineer, the infra/SRE and the tech lead.

## How to read this document

| File | Covers | Code |
|---|---|---|
| `decision-record.md`, `dr_calc.py`, `decision_record.json` | every number: model, tokens, data, recipe, compute, memory, budget, timeline, team, risks, assumptions | `python3 dr_calc.py` regenerates all tables |
| `02-model.md` | transformer block design, numerics, parameter table, FLOPs | `code/model.py` |
| `03-tokenizer.md` | tokenizer training and evaluation, special tokens, shard format | `code/train_tokenizer.py`, `code/tokenize_shards.py` |
| `04-data.md` | sources and licences, acquisition, filters, deduplication, mixing, QA | `code/dedup_minhash.py`, `code/quality_filters.py` |
| `05-training.md` | cluster spec, acceptance tests, FSDP2/HSDP parallelism, memory and communication, training loop, Slurm launch | `code/train_fsdp.py`, `code/data_loader.py` |
| `06-checkpointing-monitoring.md` | DCP checkpoints, retention, verification, resume; metrics, alerts, dashboards, async evals | `code/checkpoint.py`, `code/monitoring.py` |
| `07-post-training.md` | SFT data and recipe, chat template, reward model, DPO, GRPO, release gate | `code/sft.py`, `code/dpo.py` |
| `08-serving-cost.md` | vLLM serving architecture, quantisation, capacity model, SLOs, cost-optimisation table | `code/serving_capacity.py` |
| `09-failure-modes.md` | risk register, rollback policy, six runbooks | `code/loss_spike_guard.py` |

Run every example: `cd code && for f in *.py; do python3 $f || break; done` (CPU, about one minute in total).

## Program checklist

- [ ] Master contract signed by W4 at <= USD 2.40/GPU-h with the Block 2 start fixed by W6.
- [ ] G1 passed end of W6; G2 at W9 with the framework decision recorded; G3a at W11 d7; G3 at W12 d1 with the licence manifest signed.
- [ ] Rehearsal complete with a verified bit-identical resume and all runbooks exercised.
- [ ] G4 passed on day 4 of Block 2; main run launched from the sbatch script.
- [ ] G5 within 0.02 nats at 1T, 4T and 8T; anneal, 32k and 128k stages complete; final checkpoint exported and replicated.
- [ ] G6 release table signed; FP8 build passes its accuracy gate; pilot reports cost per 1M tokens against the 0.244 plan.
- [ ] Spend tracked monthly against the budget table; contingency released only by change request.
