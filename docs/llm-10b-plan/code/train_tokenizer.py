"""Train and evaluate the 131,072-token byte-level BPE tokenizer (section 03 of the plan).

Pre-tokenization: GPT-4 / Llama-3 style regex with digits split into runs of at most 3,
byte-level BPE (every byte is a token, so there is no unknown token), NFC normalisation,
no lowercasing. 64 special tokens are reserved inside the 131,072 budget.

Run:  python3 train_tokenizer.py            (trains a 2,048-vocab tokenizer on synthetic text, < 10 s)
      python3 train_tokenizer.py --corpus sample.jsonl --vocab 131072 --out tokenizer.json
"""
from __future__ import annotations

import argparse
import json
import random
import tempfile
import time
from collections.abc import Iterable

from tokenizers import Regex, Tokenizer, decoders, models, normalizers, pre_tokenizers, trainers

# Llama-3 / GPT-4 pattern with \p{N}{1,3}: numbers are split into groups of up to three digits.
PRETOKENIZE_PATTERN = (
    r"(?i:'s|'t|'re|'ve|'m|'ll|'d)"
    r"|[^\r\n\p{L}\p{N}]?\p{L}+"
    r"|\p{N}{1,3}"
    r"| ?[^\s\p{L}\p{N}]+[\r\n]*"
    r"|\s*[\r\n]+"
    r"|\s+(?!\S)"
    r"|\s+"
)

CONTROL = ["<|begin_of_text|>", "<|end_of_text|>", "<|pad|>", "<|unk|>"]
CHAT = ["<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>", "<|eom_id|>"]  # eom: end of message, tool call pending
TOOLS = ["<|tool_call|>", "<|/tool_call|>", "<|tool_result|>", "<|/tool_result|>", "<|python_tag|>"]
FIM = ["<|fim_prefix|>", "<|fim_middle|>", "<|fim_suffix|>", "<|fim_pad|>", "<|repo_name|>", "<|file_sep|>"]
N_SPECIAL = 64
SPECIAL_TOKENS = CONTROL + CHAT + TOOLS + FIM
SPECIAL_TOKENS += [f"<|reserved_{i}|>" for i in range(N_SPECIAL - len(SPECIAL_TOKENS))]
assert len(SPECIAL_TOKENS) == N_SPECIAL
EOS = "<|end_of_text|>"
BOS = "<|begin_of_text|>"


def build_tokenizer() -> Tokenizer:
    tok = Tokenizer(models.BPE(unk_token=None, byte_fallback=False, fuse_unk=False))
    tok.normalizer = normalizers.NFC()
    tok.pre_tokenizer = pre_tokenizers.Sequence([
        pre_tokenizers.Split(Regex(PRETOKENIZE_PATTERN), behavior="isolated"),
        pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False),
    ])
    tok.decoder = decoders.ByteLevel()
    return tok


def train(texts: Iterable[str], vocab_size: int) -> Tokenizer:
    tok = build_tokenizer()
    trainer = trainers.BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=2,
        special_tokens=SPECIAL_TOKENS,
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
        show_progress=False,
        max_token_length=64,  # no 100-byte junk merges from boilerplate
    )
    tok.train_from_iterator(texts, trainer=trainer)
    assert tok.get_vocab_size() <= vocab_size
    # Pretraining text must never be able to inject a control token: with this flag the literal
    # string "<|end_of_text|>" inside a document is split into ordinary byte-level tokens.
    # Chat/SFT rendering (section 07) inserts special tokens by id, never by text.
    tok.encode_special_tokens = True
    return tok


def iter_jsonl(path: str, limit: int | None = None) -> Iterable[str]:
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
            yield json.loads(line)["text"]


def evaluate(tok: Tokenizer, texts: list[str]) -> dict[str, float]:
    """Fertility (tokens per whitespace word), bytes per token, round-trip exactness."""
    n_tok = n_words = n_bytes = exact = 0
    for t in texts:
        enc = tok.encode(t, add_special_tokens=False)
        n_tok += len(enc.ids)
        n_words += max(1, len(t.split()))
        n_bytes += len(t.encode("utf-8"))
        exact += int(tok.decode(enc.ids, skip_special_tokens=False) == t)
    return {"fertility": n_tok / n_words, "bytes_per_token": n_bytes / max(n_tok, 1),
            "round_trip_exact": exact / max(len(texts), 1), "docs": len(texts)}


def synthetic_corpus(n: int, seed: int = 0) -> list[str]:
    rng = random.Random(seed)
    words = ("the model trains on tokens and the loss falls while the learning rate decays "
             "code def return import numpy torch for while if else data cluster gpu").split()
    out = []
    for i in range(n):
        sent = " ".join(rng.choice(words) for _ in range(rng.randint(8, 40)))
        num = str(rng.randint(0, 10 ** rng.randint(1, 9)))
        code = f"def f{i % 7}(x):\n    return x * {rng.randint(2, 99)}  # comment\n"
        out.append(f"{sent.capitalize()}. Value {num} and {num}.5 units.\n{code}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", help="JSONL with a 'text' field; omit for the synthetic smoke test")
    ap.add_argument("--vocab", type=int, default=131072)
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    t0 = time.time()

    if args.corpus:
        tok = train(iter_jsonl(args.corpus, args.limit), args.vocab)
        held = list(iter_jsonl(args.corpus, 2000))
    else:
        corpus = synthetic_corpus(3000)
        tok = train(corpus, 2048)
        held = synthetic_corpus(200, seed=1)
    stats = evaluate(tok, held)
    print(json.dumps(stats, indent=1))

    # invariants every tokenizer version must satisfy before it is frozen
    for s in ["Hello world", "  leading spaces", "tabs\tand\nnewlines\r\n", "naive café résumé 日本語 🙂",
              "x = 1234567; y = 0.00042", "<|end_of_text|> is literal text here", "a" * 300]:
        ids = tok.encode(s, add_special_tokens=False).ids
        assert tok.decode(ids, skip_special_tokens=False) == s, (s, tok.decode(ids, skip_special_tokens=False))
        assert tok.token_to_id(EOS) not in ids  # no injection from literal text
    ids = tok.encode("1234567", add_special_tokens=False).ids
    pieces = [tok.decode([i]) for i in ids]
    assert all(len(p.strip()) <= 3 for p in pieces), pieces
    assert tok.token_to_id(EOS) == 1 and tok.token_to_id(BOS) == 0
    assert tok.token_to_id(SPECIAL_TOKENS[-1]) == N_SPECIAL - 1
    assert stats["round_trip_exact"] == 1.0
    if args.out:
        tok.save(args.out)
        print("saved", args.out)
    print(f"OK train_tokenizer.py in {time.time() - t0:.1f}s (vocab {tok.get_vocab_size()}, "
          f"fertility {stats['fertility']:.2f}, bytes/token {stats['bytes_per_token']:.2f})")
