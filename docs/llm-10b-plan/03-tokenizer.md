## 03. Tokenization strategy

Covers: tokenization strategy, the tokenizer training and evaluation code (`code/train_tokenizer.py`) and the corpus-to-shard writer (`code/tokenize_shards.py`). Numbers from DR sections 2, 3 and 7.

### Decisions

- **Train our own byte-level BPE with a 131,072 vocabulary (2^17).** Reusing the Llama 3 tokenizer would tie the model to the Llama licence; tiktoken's o200k_base has no training-time control over digit handling or special tokens. Training takes one RAM node for a day and costs under USD 200.
- **Vocabulary budget: 256 byte tokens + 64 reserved special tokens + 130,752 merges.** 131,072 is a multiple of 256 (FP8 and tensor-core friendly) and shards evenly over 8, 16 and 64 ranks; it gives 10-15% fewer tokens per byte on code and multilingual text than a 64k vocabulary.
- **Llama-3-style pre-tokenization regex with digits grouped in runs of at most three** (`\p{N}{1,3}`), NFC normalisation, no lowercasing, no byte fallback token (byte-level BPE covers every byte).
- **Special tokens are inserted by id, never by text.** The encoder runs with `encode_special_tokens = True`, so the literal string `<|end_of_text|>` in a crawled page is ordinary text and cannot end a document or inject a chat turn.
- **Tokenizer frozen at W5 d1** (trained W3-4). After the freeze, every change is a new tokenizer version with a new hash, and the shards carry that hash in their manifest.
- **Shard format: raw uint32 token ids with EOS after every document, a uint64 document-offset index, and a JSON manifest with sha256.** 11.27T tokens become 45.1 TB; 268M-token shards (1.07 GB) give about 42,000 files per corpus version.

### Procedure

1. **Build the training sample (W3 d1-d2, contractor).** 40 GB of text (about 10B tokens) drawn from the v0 corpus sources, upweighting the domains where tokenization quality matters most: English web 50% (FineWeb-Edu, DCLM), code 20% (The Stack v2, all 30 languages with Python, JS/TS, C/C++, Java, Go, Rust at their corpus shares), multilingual 15% (FineWeb-2, the 12 languages equally), math and papers 12% (FineMath, peS2o, FinePDFs), Wikipedia and books 3%. Deduplicate the sample exactly (section 04) so boilerplate does not earn merges.
2. **Train (W3 d3, one RAM node, 1 TB RAM).** `python3 code/train_tokenizer.py --corpus sample.jsonl --vocab 131072 --out tokenizer-v1.json`. `max_token_length=64` and `min_frequency=2` stop 100-byte boilerplate tokens.
3. **Evaluate against the Llama 3 tokenizer on a held-out 2 GB per domain (W3 d4).** Pass criteria: fertility (tokens per whitespace word) on English web within +2% of Llama 3, on code and on the 12 languages at or below Llama 3; bytes per token >= 4.2 on English web and >= 3.6 on code; round-trip exact on 1M documents (100%); every number up to 999 is one token and `1234567` becomes `123|456|7`; no token longer than 64 bytes; no token that is a complete URL, email or PII pattern (grep the vocab).
4. **Measure the shrink factor (W3 d4).** Count tokens of the same 2 GB web sample under the sources' tokenizers (FineWeb-Edu and DCLM report GPT-2/Llama-3 counts) and ours. The DR plans with web rows x 0.87; the measured ratio replaces 0.87 in `dr_calc.py` at the G1 gate.
5. **Freeze (W5 d1).** Tag `tokenizer-v1.json`, record its sha256 in the DR, and publish the 64 special-token ids to the post-training and serving owners (sections 07 and 08).
6. **Tokenize the v0 corpus (W5-W6) and the frozen mix (W10-W11).** `python3 code/tokenize_shards.py --inputs ... --tokenizer tokenizer-v1.json --out /pfs/data/v1/<source>/<source> --source <source> --shard-tokens 268435456 --workers 192` per source on the 768-core partition. Rate assumption 200k tokens/s/core (HF tokenizers, regex pre-tokenizer): 11.27e12 / 2e5 / 3600 = 15,650 core-hours = 20.4 h on 768 cores = USD 704 at 0.045/core-hour. The v0 corpus (1.5T) is 2,083 core-hours.
7. **Verify shards (same day).** For each shard: sha256 matches the manifest, `idx[-1] == n_tokens`, the token before every offset is EOS, 100 random documents decode to their source text, per-source token totals within 1% of the plan in DR section 3. Write the per-source totals into `measured_unique.json` for the G3 gate.

### Design detail

Pre-tokenization pattern (one alternative per line):

```text
(?i:'s|'t|'re|'ve|'m|'ll|'d)        contractions stay attached
[^\r\n\p{L}\p{N}]?\p{L}+            a word with one optional leading symbol or space
\p{N}{1,3}                          digits in runs of at most three
 ?[^\s\p{L}\p{N}]+[\r\n]*           punctuation runs, optional leading space, trailing newlines
\s*[\r\n]+                          newline runs (code structure survives)
\s+(?!\S)                           whitespace runs except the last space before a word
\s+                                 remaining whitespace (indentation becomes its own tokens)
```

Special tokens (ids 0-63, inside the 131,072 budget):

| Ids | Tokens | Use |
|---|---|---|
| 0-3 | `<\|begin_of_text\|>`, `<\|end_of_text\|>`, `<\|pad\|>`, `<\|unk\|>` | BOS, EOS (document boundary in shards), padding (never in pretraining), unused |
| 4-7 | `<\|start_header_id\|>`, `<\|end_header_id\|>`, `<\|eot_id\|>`, `<\|eom_id\|>` | chat template: role header, end of turn, end of message with a pending tool call |
| 8-12 | `<\|tool_call\|>`, `<\|/tool_call\|>`, `<\|tool_result\|>`, `<\|/tool_result\|>`, `<\|python_tag\|>` | tool calling |
| 13-18 | `<\|fim_prefix\|>`, `<\|fim_middle\|>`, `<\|fim_suffix\|>`, `<\|fim_pad\|>`, `<\|repo_name\|>`, `<\|file_sep\|>` | fill-in-the-middle and repo-level code packing |
| 19-63 | `<\|reserved_0\|>` .. `<\|reserved_44\|>` | future use; never emitted by the model |

Shard format (read by `code/data_loader.py`, written by `code/tokenize_shards.py`):

```text
web-00017.bin   uint32 LE  [t t t ... EOS t t ... EOS ...]      268,435,456 tokens = 1.07 GB
web-00017.idx   uint64 LE  [0, len(doc0)+1, len(doc0)+len(doc1)+2, ..., n_tokens]
web-00017.json  {"n_tokens", "n_docs", "source", "sha256_bin", "tokenizer_sha256",
                 "inputs", "format": "uint32-eos-v1"}
```

Documents are packed, never padded. BOS is not written into pretraining shards: the document boundary is EOS, and the loader derives `cu_seqlens` from EOS positions so attention never crosses documents. BOS is used by the chat template only.

Layout on the parallel filesystem: `/pfs/data/v1/<source>/<source>-NNNNN.{bin,idx,json}`; one directory per source so the loader's mix weights (section 04) are applied per source; a top-level `MANIFEST.json` lists every shard with its sha256, token count and the tokenizer hash. A new tokenizer or a new filter is a new version directory, never an in-place rewrite.

### Reference implementation

Tokenizer construction and training (`code/train_tokenizer.py`):

```python
PRETOKENIZE_PATTERN = (
    r"(?i:'s|'t|'re|'ve|'m|'ll|'d)"
    r"|[^\r\n\p{L}\p{N}]?\p{L}+"
    r"|\p{N}{1,3}"
    r"| ?[^\s\p{L}\p{N}]+[\r\n]*"
    r"|\s*[\r\n]+"
    r"|\s+(?!\S)"
    r"|\s+"
)


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
```

Shard writer core (`code/tokenize_shards.py`):

```python
class ShardWriter:
    def add(self, doc: list[int]) -> None:
        self.tokens.append(np.asarray(doc, dtype="<u4"))
        self.count += len(doc)
        self.offsets.append(self.count)
        if self.count >= self.limit:
            self.flush()

    def flush(self) -> None:
        if not self.tokens:
            return
        path = f"{self.prefix}-{self.n:05d}"
        arr = np.concatenate(self.tokens)
        arr.tofile(path + ".bin")
        np.asarray(self.offsets, dtype="<u8").tofile(path + ".idx")
        man = {"n_tokens": int(arr.size), "n_docs": len(self.offsets) - 1, "source": self.source,
               "sha256_bin": hashlib.sha256(arr.tobytes()).hexdigest(), "tokenizer_sha256": self.tok_sha,
               "inputs": self.inputs, "format": "uint32-eos-v1"}
        json.dump(man, open(path + ".json", "w"), indent=1)
        self.manifests.append(man)
        self.tokens, self.offsets, self.count, self.n = [], [0], 0, self.n + 1


def tokenize(inputs: list[str], tokenizer_path: str, out_prefix: str, source: str,
             shard_tokens: int, workers: int, batch_docs: int = 256) -> list[dict]:
    tok_sha = hashlib.sha256(open(tokenizer_path, "rb").read()).hexdigest()
    writer = ShardWriter(out_prefix, source, shard_tokens, tok_sha, inputs)
    with Pool(workers, initializer=_init, initargs=(tokenizer_path,)) as pool:
        for docs in pool.imap(_encode_batch, _batches(inputs, batch_docs), chunksize=1):
            for d in docs:
                writer.add(d)
    writer.flush()
    return writer.manifests
```

Smoke tests (CPU): the tokenizer test trains a small vocabulary on synthetic text and asserts round-trip exactness on unicode, tabs, newlines, 300-character runs and literal special-token text, digit grouping, and the special-token ids; the shard test trains, writes four shards, verifies offsets and EOS placement, re-runs for byte-identical output, and opens the shards with the training loader.

```text
OK train_tokenizer.py in 0.1s (vocab 1524, fertility 1.41, bytes/token 3.89)
OK tokenize_shards.py in 1.0s (4 shards, 6392 tokens)
```

### Checklist

- [ ] 40 GB stratified, exact-deduplicated training sample built and its composition recorded.
- [ ] `tokenizer-v1.json` trained; vocabulary 131,072; 64 specials at ids 0-63; no token > 64 bytes; no URL/email/PII tokens.
- [ ] Evaluation vs Llama 3 passes the fertility and bytes/token thresholds on all five domains; 1M-document round trip is exact.
- [ ] Shrink factor measured and written into `dr_calc.py` (replaces 0.87).
- [ ] Tokenizer sha256 recorded in the DR and in every shard manifest; special-token ids published to post-training and serving.
- [ ] v0 corpus (>= 1.5T tokens) tokenized by end of W6; shard verification passes; `measured_unique.json` written.
