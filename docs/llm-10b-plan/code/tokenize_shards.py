"""Tokenize JSONL documents into the shard format read by code/data_loader.py (section 03).

  <name>.bin  raw little-endian uint32 token ids; every document ends with EOS
  <name>.idx  raw little-endian uint64 document start offsets, length n_docs + 1
  <name>.json manifest: n_tokens, n_docs, sha256 of the .bin, source, tokenizer sha256, inputs

Ordering is deterministic (ordered imap over input files), so re-running on the same inputs
with the same tokenizer gives byte-identical shards (checked by the manifest sha256).

Run:  python3 tokenize_shards.py                      (smoke test, < 10 s)
      python3 tokenize_shards.py --inputs a.jsonl b.jsonl --tokenizer tokenizer.json \
              --out /pfs/data/v1/web --source web --shard-tokens 268435456 --workers 64
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from multiprocessing import Pool

import numpy as np
from tokenizers import Tokenizer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_TOK: Tokenizer | None = None
_EOS = 1


def _init(tokenizer_path: str) -> None:
    global _TOK
    _TOK = Tokenizer.from_file(tokenizer_path)
    _TOK.encode_special_tokens = True  # literal "<|...|>" text in documents stays ordinary text


def _encode_batch(lines: list[str]) -> list[list[int]]:
    assert _TOK is not None
    texts = [json.loads(l)["text"] for l in lines]
    return [e.ids + [_EOS] for e in _TOK.encode_batch(texts, add_special_tokens=False)]


def _batches(paths: list[str], size: int):
    buf: list[str] = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    buf.append(line)
                if len(buf) == size:
                    yield buf
                    buf = []
    if buf:
        yield buf


class ShardWriter:
    def __init__(self, out_prefix: str, source: str, shard_tokens: int, tokenizer_sha: str, inputs: list[str]) -> None:
        self.prefix, self.source, self.limit = out_prefix, source, shard_tokens
        self.tok_sha, self.inputs, self.n = tokenizer_sha, inputs, 0
        self.tokens: list[np.ndarray] = []
        self.offsets: list[int] = [0]
        self.count = 0
        self.manifests: list[dict] = []

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
    os.makedirs(os.path.dirname(out_prefix) or ".", exist_ok=True)
    tok_sha = hashlib.sha256(open(tokenizer_path, "rb").read()).hexdigest()
    writer = ShardWriter(out_prefix, source, shard_tokens, tok_sha, inputs)
    with Pool(workers, initializer=_init, initargs=(tokenizer_path,)) as pool:
        for docs in pool.imap(_encode_batch, _batches(inputs, batch_docs), chunksize=1):
            for d in docs:
                writer.add(d)
    writer.flush()
    return writer.manifests


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="*")
    ap.add_argument("--tokenizer")
    ap.add_argument("--out", help="output prefix, e.g. /pfs/data/v1/web/web")
    ap.add_argument("--source", default="web")
    ap.add_argument("--shard-tokens", type=int, default=2 ** 28)  # 268M tokens = 1.07 GB per shard
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 4)
    args = ap.parse_args()
    t0 = time.time()

    if args.inputs:
        mans = tokenize(args.inputs, args.tokenizer, args.out, args.source, args.shard_tokens, args.workers)
        print(json.dumps({"shards": len(mans), "tokens": sum(m["n_tokens"] for m in mans)}))
        sys.exit(0)

    # smoke test: train a tiny tokenizer, write shards, read them back through the data loader
    from data_loader import PackedDataset, SourceSpec
    from train_tokenizer import EOS, synthetic_corpus, train

    with tempfile.TemporaryDirectory() as d:
        docs = synthetic_corpus(120)
        tok = train(docs, 1024)
        assert tok.token_to_id(EOS) == _EOS
        tok.save(os.path.join(d, "tok.json"))
        with open(os.path.join(d, "in.jsonl"), "w") as f:
            for t in docs:
                f.write(json.dumps({"text": t}) + "\n")
        mans = tokenize([os.path.join(d, "in.jsonl")], os.path.join(d, "tok.json"),
                        os.path.join(d, "out", "web"), "web", shard_tokens=2000, workers=2)
        assert len(mans) >= 2 and sum(m["n_docs"] for m in mans) == 120
        # read back shard 0 and check document boundaries
        idx = np.fromfile(os.path.join(d, "out", "web-00000.idx"), dtype="<u8")
        bin0 = np.fromfile(os.path.join(d, "out", "web-00000.bin"), dtype="<u4")
        assert idx[0] == 0 and idx[-1] == bin0.size == mans[0]["n_tokens"]
        assert all(bin0[int(e) - 1] == _EOS for e in idx[1:])
        assert tok.decode(bin0[: int(idx[1]) - 1].tolist()) == docs[0]
        # determinism: a second run gives identical shards
        mans2 = tokenize([os.path.join(d, "in.jsonl")], os.path.join(d, "tok.json"),
                         os.path.join(d, "out2", "web"), "web", shard_tokens=2000, workers=2)
        assert [m["sha256_bin"] for m in mans] == [m["sha256_bin"] for m in mans2]
        # the training loader opens them
        prefixes = [os.path.join(d, "out", f"web-{i:05d}") for i in range(len(mans))]
        ds = PackedDataset([SourceSpec("web", prefixes, 1.0)], seq_len=64, eos_id=_EOS, seed=0)
        x, y, cu = next(ds)
        assert x.shape == (64,) and cu[-1] == 64
    print(f"OK tokenize_shards.py in {time.time() - t0:.1f}s ({len(mans)} shards, "
          f"{sum(m['n_tokens'] for m in mans)} tokens)")
