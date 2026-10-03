## 07. Fine-tuning and preference optimisation

Covers: the fine-tuning pipeline (`code/sft.py`) and RLHF / preference optimisation (`code/dpo.py`, GRPO via verl). Numbers from DR section 5 (Block 3 workloads) and section 1 (human data line).

### Decisions

- **Three stages in Block 3 (W23-W30, 48 reserved GPUs): SFT -> DPO -> GRPO on verifiable rewards.** SFT and DPO are cheap and predictable (1,933 GPU-h together); online RL is the only stage with open-ended cost and is boxed at 48 GPUs x 21 days (24,192 GPU-h, USD 53,222).
- **Full-parameter fine-tuning for every stage.** A 9.8B model fits 32 GPUs with FSDP2 at seq 8,192; LoRA is reserved for ablations and for customer adapters after release.
- **DPO before any online RL, on on-policy pairs.** 280,000 pairs are sampled from the SFT model and labelled by an Apache-2.0 open-weight judge served locally; 20,000 human pairs (USD 100,000) train the reward model and validate the judge. Off-policy pairs from other models are not used for DPO.
- **GRPO only where a reward can be checked by a program**: math with reference answers, code with unit tests, instruction constraints with verifiers (IFEval-style). No learned reward model in the RL loop; the reward model is used for pair filtering and for evaluation only.
- **Chat template rendered from special-token ids** (section 03): user text can never open or close a turn.
- **Release gate G6 is a fixed evaluation table, decided before Block 3 starts**, with a private held-out suite that no training set has touched.

### Procedure

1. **Freeze the evaluation suite (W18, post-training engineer).** Public: IFEval, MMLU, GSM8K, MATH-500, HumanEval+, MBPP+, Arena-Hard-Auto, MT-Bench, BBH, GPQA-Diamond, a multilingual subset (MGSM); private: the 10-task held-out suite from section 04 (>= 500 items each, hashed). Decontaminate every post-training set against all of them (13-gram, section 04). Record the Llama-3.1-8B-Instruct and Qwen2.5-7B-Instruct scores under the same harness as the comparison bands.
2. **Assemble the SFT corpus (W19-W22).** Target 1.2M conversations (about 3B tokens per epoch; the DR budgets 1,126 ideal GPU-h, enough for 10B tokens per epoch at MFU 0.30, so synthetic expansion has room):

   | Set | Licence | Use | Approx. size |
   |---|---|---|---|
   | Tulu 3 SFT mixture | ODC-By; subsets carry generator terms (counsel memo) | general, math, code, safety | 900k |
   | SmolTalk | Apache-2.0 | general chat, rewriting, summarisation | 500k (sampled) |
   | OpenMathInstruct-2 | CC-BY-4.0 (Llama-generated: naming clause) | math CoT | 300k (sampled) |
   | Nemotron post-training sets (chat, code, math, tool use) | CC-BY-4.0 | tool calling, code | 300k (sampled) |
   | OpenCodeInstruct | CC-BY-4.0 | code | 200k (sampled) |
   | Expert-written (vendor, USD 25 each) | ours | long-form, multi-turn, refusals with reasons | 2,000 |
   | Self-generated with the W22 model + verifier filtering | ours | tool use, agentic multi-turn, 12 languages | 150k |

   Pipeline: exact + MinHash dedup (section 04 code), decontamination, language ID, length and format checks, a judge pass that drops responses rated < 3/5, and a manual 500-sample audit per source. Sample to the target mix: 45% general chat and writing, 20% math, 20% code, 10% tool use and agentic, 5% safety and refusals.
3. **SFT (W23 d1-d3, 32 GPUs).** Hyperparameters for a 9.8B model: peak LR 1e-5, cosine to 1e-6, warmup 3%, 2 epochs, batch 1,048,576 tokens (128 x 8,192), seq 8,192, AdamW (0.9, 0.95), weight decay 0.0, grad clip 1.0, bf16 with fp32 master, loss on assistant tokens only, packing with document masking (`pack()` below; FA3 varlen in production). Compute: 1,464 GPU-h with the 1.3 overhead factor = 1.91 days on 32 GPUs = USD 3,222. Checkpoint every epoch; pick the checkpoint by the private suite, not by loss.
4. **Reward model (W23 d4-d5, 32 GPUs, 117 GPU-h).** Initialise from the SFT model with a scalar head; Bradley-Terry loss on the 20,000 human pairs (ordered W23 d5, delivered 10k/week, so the RM trains on the first 10k and is refreshed at W25 d5) plus 50k judge pairs; held-out agreement with humans must be >= 0.75 before the RM filters anything.
5. **On-policy preference data (W24, 16 GPUs for the judge, 2,000 GPU-h).** 70,000 prompts (held-out from SFT; same mix) x 4 samples at temperature 0.8 from the SFT model via vLLM; the judge ranks the 4 (pairwise, position-swapped); keep pairs with a judge margin >= 2 on a 10-point scale and RM agreement; drop pairs where the chosen response is > 1.5x longer than the rejected one unless the judge cites completeness. Yield about 280,000 pairs.
6. **DPO (W25, 32 GPUs, 469 GPU-h).** beta 0.1, LR 5e-7, 1 epoch over 300,000 pairs (280k judge + 20k human), batch 64 pairs, warmup 10%, reference = the SFT checkpoint, length-normalised variant only if the length gate in step 5 removed > 30% of pairs. Monitor: implicit reward margin (should rise and plateau), chosen-response length (must not grow > 15%), refusal rate on the 500-prompt benign set (must not rise > 2 points), MMLU/GSM8K regression (<= 1 point).
7. **GRPO (W26-W29, 48 GPUs = 32 training + 16 vLLM rollout, 24,192 GPU-h).** verl with the config below: 1,024 prompts per step x 8 samples, max response 4,096 tokens, LR 1e-6, KL coefficient 0.001 against the DPO checkpoint, clip 0.2, 300 steps, reward = 1 for a verified answer or passing tests else 0, with a -0.1 format penalty for missing the answer tag. Prompt pools: 60k math problems with reference answers (NuminaMath-style sets under their licences, GSM8K/MATH train only), 40k code tasks with unit tests, 20k constraint-following prompts with programmatic checkers. Stop early if the private-suite score has not improved for 50 steps or if mean response length doubles.
8. **Safety and red team (W28-W29).** 2,000 human evaluations (USD 20,000) on a stratified prompt set; red-team contract (USD 25,000) covering jailbreaks, tool misuse and PII extraction; findings become SFT/DPO examples for a final short DPO pass (W29 d5).
9. **Release gate G6 (W30).** Table below; the post-training engineer and the tech lead sign; the serving pilot (section 08) takes the signed checkpoint only.

### Chat template

Rendered by `render_chat()` from ids (shown as text for readability):

```text
<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system}<|eot_id|>
<|start_header_id|>user<|end_header_id|>\n\n{user}<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>\n\n{assistant}<|eot_id|>
```

Tool calling: the assistant emits `<|tool_call|>{"name": ..., "arguments": {...}}<|/tool_call|><|eom_id|>`; the runtime appends `<|start_header_id|>tool<|end_header_id|>\n\n<|tool_result|>{json}<|/tool_result|><|eot_id|>` and the assistant continues. `<|eom_id|>` (end of message, more to come) versus `<|eot_id|>` (end of turn) lets the server know whether to return to the user. Loss is on assistant content tokens and their `<|eot_id|>`/`<|eom_id|>`; tool results and headers are masked.

### Compute and cost (DR section 5, Block 3)

| Stage | GPUs | GPU-hours | Days | USD |
|---|---|---|---|---|
| SFT | 32 | 1,464 | 1.91 | 3,222 |
| Reward model | 32 | 117 | 0.15 | 258 |
| DPO | 32 | 469 | 0.61 | 1,031 |
| GRPO (training + rollouts) | 48 | 24,192 | 21.0 | 53,222 |
| Judge serving (vLLM) | 16 | 2,000 | 5.2 | 4,400 |
| Post-training evals | 16 | 1,900 | 5.0 | 4,180 |
| Serving pilot start (W29-W30) | 8 | 2,688 | 14.0 | 5,914 |

Human data and evaluation (USD 220,000): 20,000 preference pairs x 5 = 100,000; 2,000 expert SFT examples x 25 = 50,000; 2,000 human evaluations x 10 = 20,000; red team 25,000; judge and synthetic-data API reserve 25,000. Two vendor quotes by W3; the preference-pair price (USD 5 vs 15) is the DR's named sensitivity.

### Release gate G6

| Metric | Band A (ship) | Band B (ship with a note) | Fail |
|---|---|---|---|
| Private 10-task suite, mean | >= SFT model + 5 points and >= Llama-3.1-8B-Instruct | >= SFT model + 2 | otherwise |
| IFEval (prompt-level strict) | >= 0.78 | >= 0.72 | otherwise |
| GSM8K (strict, 8-shot) | >= 0.85 | >= 0.80 | otherwise |
| HumanEval+ | >= 0.70 | >= 0.62 | otherwise |
| MMLU (5-shot) | >= base model - 1.0 | >= base model - 2.0 | otherwise |
| Arena-Hard-Auto vs Llama-3.1-8B-Instruct | >= 50% | >= 40% | otherwise |
| Benign refusal rate (500 prompts) | <= 3% | <= 5% | otherwise |
| Red-team critical findings open | 0 | 0 | any |
| Mean response length vs SFT model | <= +15% | <= +30% | otherwise |

Thresholds are the W18 proposal; they are confirmed against the base-model numbers at G5 and frozen before Block 3 starts.

### Reference implementation

Template rendering and packing with loss masks (`code/sft.py`):

```python
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


def masked_loss(model: Transformer, x: torch.Tensor, y: torch.Tensor, chunk: int = 2048) -> torch.Tensor:
    """Mean CE over unmasked targets; logits computed per chunk in fp32 like model._chunk_loss."""
    h = model.hidden(x).reshape(-1, model.cfg.d_model)
    t = y.reshape(-1)
    total, count = h.new_zeros((), dtype=torch.float32), (t != IGNORE).sum()
    for i in range(0, h.shape[0], chunk):
        logits = F.linear(h[i:i + chunk], model.lm_head.weight).float()
        total = total + F.cross_entropy(logits, t[i:i + chunk], ignore_index=IGNORE, reduction="sum")
    return total / count.clamp(min=1)
```

DPO loss with a frozen reference (`code/dpo.py`):

```python
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
```

Smoke tests: SFT asserts the mask covers exactly the assistant bodies plus `<|eot_id|>`, that packing preserves the masked-token count, and that six epochs on 25 synthetic conversations halve the loss; DPO asserts a zero margin at step 0 (policy equals reference), then margin > 0.5, accuracy 1.0, chosen reward > 0 > rejected reward after 40 steps.

```text
OK sft.py in 1.4s: 19 packed windows, loss 6.648 -> 1.449
OK dpo.py in 2.4s: loss 0.693 -> 0.000, margin 10.09, accuracy 1.00
```

Production configs. TRL for SFT and DPO (the from-scratch code above is the reference the configs must match on a 1,000-example check):

```yaml
# trl sft, 32 GPUs, accelerate + FSDP2 config
model_name_or_path: /pfs/exports/base-11T-bf16
dataset_name: /pfs/post/sft-v1            # jsonl with "messages"
chat_template_path: /pfs/post/tokenizer   # tokenizer.json + chat_template.jinja (ids as above)
assistant_only_loss: true
packing: true
packing_strategy: bfd                     # packs without crossing examples; position_ids reset
max_length: 8192
per_device_train_batch_size: 2
gradient_accumulation_steps: 2            # 32 x 2 x 2 x 8192 = 1,048,576 tokens
learning_rate: 1.0e-5
lr_scheduler_type: cosine
warmup_ratio: 0.03
num_train_epochs: 2
weight_decay: 0.0
bf16: true
gradient_checkpointing: true
attn_implementation: flash_attention_3
save_strategy: epoch
eval_strategy: steps
eval_steps: 200
```

```yaml
# trl dpo
beta: 0.1
learning_rate: 5.0e-7
num_train_epochs: 1
per_device_train_batch_size: 1
gradient_accumulation_steps: 2            # 64 pairs per step on 32 GPUs
max_length: 8192
max_prompt_length: 4096
precompute_ref_log_probs: true            # the reference forward is done once, then freed
loss_type: sigmoid                        # switch to ipo or simpo only via the length gate
```

verl GRPO (48 GPUs: 32 actor/FSDP2, 16 vLLM rollout):

```yaml
algorithm:
  adv_estimator: grpo
  kl_ctrl: {type: fixed, kl_coef: 0.001}
data:
  train_files: [/pfs/post/rl/math.parquet, /pfs/post/rl/code.parquet, /pfs/post/rl/ifeval.parquet]
  train_batch_size: 1024
  max_prompt_length: 2048
  max_response_length: 4096
actor_rollout_ref:
  model: {path: /pfs/exports/dpo-v1, use_remove_padding: true, enable_gradient_checkpointing: true}
  actor:
    strategy: fsdp2
    optim: {lr: 1.0e-6, weight_decay: 0.0}
    ppo_mini_batch_size: 256
    ppo_micro_batch_size_per_gpu: 4
    clip_ratio: 0.2
    use_kl_loss: true
    kl_loss_coef: 0.001
    entropy_coeff: 0.0
  rollout:
    name: vllm
    n: 8                                   # group size
    temperature: 1.0
    gpu_memory_utilization: 0.85
    tensor_model_parallel_size: 1
reward_model:
  enable: false                            # verifiable rewards only
custom_reward_function: {path: /pfs/post/rl/rewards.py, name: compute_score}
trainer:
  total_training_steps: 300
  save_freq: 25
  test_freq: 25
  val_before_train: true
```

`compute_score` returns 1.0 for a correct boxed answer (math, symbolic match via `math-verify`), the fraction of unit tests passed (code, sandboxed with a 10 s limit), or the checker result (instruction constraints); minus 0.1 when the answer tag is missing.

### Checklist

- [ ] Evaluation suite frozen at W18; private suite hashed; baselines recorded under the same harness.
- [ ] SFT corpus 1.2M examples, deduplicated and decontaminated, mix audit filed; counsel's position on each set's generator terms recorded.
- [ ] `python3 code/sft.py` and `python3 code/dpo.py` pass; TRL configs reproduce the reference losses on 1,000 examples within 2%.
- [ ] SFT checkpoint chosen by the private suite; RM agreement with humans >= 0.75.
- [ ] DPO: margin rises and plateaus; length growth <= 15%; refusal rate within 2 points; no benchmark regression > 1 point.
- [ ] GRPO: verifiable-reward curves and private-suite score logged every 25 steps; early-stop rule applied.
- [ ] Red-team findings closed; 2,000 human evaluations scored; G6 table signed by the tech lead.
