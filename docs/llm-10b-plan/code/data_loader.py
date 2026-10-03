"""Resumable packed-sequence loader over tokenized shards (section 05 of the plan).

Shard format (written by code/tokenize_shards.py):
  <name>.bin  raw little-endian uint32 token ids; every document ends with EOS
  <name>.idx  raw little-endian uint64 document start offsets, length n_docs + 1,
              last entry == n_tokens (so idx[i]..idx[i+1] is document i)
  <name>.json manifest: {"n_tokens", "n_docs", "sha256_bin", "source", "tokenizer_sha256"}

Sampling model:
  * each shard is a token stream cut into fixed windows of seq_len + 1 tokens
    (input = window[:-1], target = window[1:]); the +1 is the shift;
  * per source, windows from all its shards are permuted with
    numpy.random.default_rng(seed * 1000 + epoch) and split across ranks
    (rank r takes permutation positions r, r + world, r + 2 * world, ...);
  * each global sample index g = rank + k * world picks its SOURCE with a
    generator seeded by (seed, epoch, g) and the mix weights, then takes that
    source's next window for this rank;
  * state = (epoch, k, per-source cursor). Restoring it reproduces the stream
    exactly, independent of how many samples were drawn before the save.
Documents are packed, never padded; cu_seqlens marks document boundaries
(positions after each EOS) so attention never crosses documents.

Run:  python3 data_loader.py   (CPU, < 5 s)
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import dataclass, field

import numpy as np
import torch


@dataclass
class SourceSpec:
    name: str
    shard_paths: list[str]          # paths without extension
    weight: float                   # mix share, normalised over sources


@dataclass
class LoaderState:
    epoch: int = 0
    k: int = 0                                   # samples drawn by this rank in this epoch
    cursors: dict[str, int] = field(default_factory=dict)  # windows taken per source by this rank


class _Source:
    def __init__(self, spec: SourceSpec, seq_len: int) -> None:
        self.spec, self.window = spec, seq_len + 1
        self.bins: list[np.memmap] = []
        self.n_windows_per_shard: list[int] = []
        for p in spec.shard_paths:
            n_tokens = json.load(open(p + ".json"))["n_tokens"]
            mm = np.memmap(p + ".bin", dtype="<u4", mode="r", shape=(n_tokens,))
            self.bins.append(mm)
            self.n_windows_per_shard.append(n_tokens // self.window)
        self.n_windows = sum(self.n_windows_per_shard)
        self.offsets = np.cumsum([0] + self.n_windows_per_shard)
        self.perm: np.ndarray | None = None
        self.perm_epoch = -1

    def permutation(self, seed: int, epoch: int) -> np.ndarray:
        if self.perm_epoch != epoch:
            self.perm = np.random.default_rng(seed * 1000 + epoch).permutation(self.n_windows)
            self.perm_epoch = epoch
        assert self.perm is not None
        return self.perm

    def window_at(self, flat_index: int) -> np.ndarray:
        shard = int(np.searchsorted(self.offsets, flat_index, side="right") - 1)
        local = flat_index - self.offsets[shard]
        start = local * self.window
        return np.asarray(self.bins[shard][start:start + self.window], dtype=np.int64)


class PackedDataset:
    """Infinite, resumable iterator of (input, target, cu_seqlens) for one rank."""

    def __init__(self, sources: list[SourceSpec], seq_len: int, eos_id: int, seed: int,
                 rank: int = 0, world_size: int = 1) -> None:
        self.seq_len, self.eos_id, self.seed = seq_len, eos_id, seed
        self.rank, self.world = rank, world_size
        self.sources = [_Source(s, seq_len) for s in sources]
        w = np.array([s.weight for s in sources], dtype=np.float64)
        self.weights = w / w.sum()
        self.state = LoaderState(cursors={s.name: 0 for s in sources})

    # ---- exact resume -------------------------------------------------
    def state_dict(self) -> dict:
        return {"epoch": self.state.epoch, "k": self.state.k, "cursors": dict(self.state.cursors)}

    def load_state_dict(self, sd: dict) -> None:
        self.state = LoaderState(epoch=sd["epoch"], k=sd["k"], cursors=dict(sd["cursors"]))

    # ---- sampling -----------------------------------------------------
    def _pick_source(self, g: int) -> int:
        rng = np.random.default_rng([self.seed, self.state.epoch, g])
        return int(rng.choice(len(self.sources), p=self.weights))

    def _next_window(self, src: _Source) -> np.ndarray | None:
        perm = src.permutation(self.seed, self.state.epoch)
        pos = self.state.cursors[src.spec.name] * self.world + self.rank
        if pos >= src.n_windows:
            return None
        self.state.cursors[src.spec.name] += 1
        return src.window_at(int(perm[pos]))

    def __iter__(self):
        return self

    def __next__(self) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        while True:
            g = self.rank + self.state.k * self.world
            src = self.sources[self._pick_source(g)]
            win = self._next_window(src)
            self.state.k += 1
            if win is not None:
                break
            # this source is exhausted for this epoch: advance the epoch, reshuffle
            self.state.epoch += 1
            self.state.k = 0
            for name in self.state.cursors:
                self.state.cursors[name] = 0
        x, y = torch.from_numpy(win[:-1]), torch.from_numpy(win[1:])
        return x, y, self.cu_seqlens(x)

    def cu_seqlens(self, x: torch.Tensor) -> torch.Tensor:
        """Document boundaries inside one packed sequence: [0, ..., seq_len] as int32."""
        ends = (x == self.eos_id).nonzero(as_tuple=True)[0] + 1
        ends = ends[ends < self.seq_len]
        return torch.cat([torch.zeros(1, dtype=torch.int32), ends.to(torch.int32),
                          torch.tensor([self.seq_len], dtype=torch.int32)])


def collate(samples: list[tuple[torch.Tensor, torch.Tensor, torch.Tensor]]) -> dict[str, torch.Tensor]:
    """Stack a micro-batch and offset cu_seqlens so FA3 varlen sees one flat token stream."""
    x = torch.stack([s[0] for s in samples])
    y = torch.stack([s[1] for s in samples])
    seq_len = x.shape[1]
    parts, base = [torch.zeros(1, dtype=torch.int32)], 0
    for s in samples:
        parts.append(s[2][1:] + base)
        base += seq_len
    return {"input": x, "target": y, "cu_seqlens": torch.cat(parts), "max_seqlen": torch.tensor(seq_len)}


# ---- helpers for tests and tooling --------------------------------------
def write_shard(path: str, docs: list[list[int]], eos_id: int, source: str = "test") -> None:
    """Minimal writer of the shard format (the production writer lives in tokenize_shards.py)."""
    import hashlib
    tokens, offsets = [], [0]
    for d in docs:
        tokens.extend(d + [eos_id])
        offsets.append(len(tokens))
    arr = np.asarray(tokens, dtype="<u4")
    arr.tofile(path + ".bin")
    np.asarray(offsets, dtype="<u8").tofile(path + ".idx")
    json.dump({"n_tokens": int(arr.size), "n_docs": len(docs), "source": source,
               "sha256_bin": hashlib.sha256(arr.tobytes()).hexdigest(), "tokenizer_sha256": "test"},
              open(path + ".json", "w"))


if __name__ == "__main__":
    t0 = time.time()
    EOS, SEQ = 7, 16
    with tempfile.TemporaryDirectory() as d:
        rng = np.random.default_rng(0)
        for name, n_docs in (("web", 40), ("code", 20)):
            docs = [rng.integers(8, 500, size=int(rng.integers(3, 30))).tolist() for _ in range(n_docs)]
            write_shard(os.path.join(d, name), docs, EOS, source=name)
        specs = [SourceSpec("web", [os.path.join(d, "web")], 0.75),
                 SourceSpec("code", [os.path.join(d, "code")], 0.25)]

        def stream(n: int, world: int = 2):
            out = []
            for r in range(world):
                ds = PackedDataset(specs, SEQ, EOS, seed=1, rank=r, world_size=world)
                out.append([next(ds) for _ in range(n)])
            return out

        full = stream(12)
        # resume: draw 5, save, build a fresh loader, load, draw 7 more -> identical to the uninterrupted run
        ds = PackedDataset(specs, SEQ, EOS, seed=1, rank=0, world_size=2)
        head = [next(ds) for _ in range(5)]
        sd = json.loads(json.dumps(ds.state_dict()))
        ds2 = PackedDataset(specs, SEQ, EOS, seed=1, rank=0, world_size=2)
        ds2.load_state_dict(sd)
        tail = [next(ds2) for _ in range(7)]
        for (a, b, c), (x, y, cu) in zip(head + tail, full[0]):
            assert torch.equal(a, x) and torch.equal(b, y) and torch.equal(c, cu)
        # ranks never see the same window within an epoch
        seen = {tuple(s[0].tolist()) for s in full[0]}
        assert not any(tuple(s[0].tolist()) in seen for s in full[1][:6])
        # shift and boundaries
        x, y, cu = full[0][0]
        assert torch.equal(x[1:], y[:-1]) and cu[0] == 0 and cu[-1] == SEQ and bool((cu[1:] > cu[:-1]).all())
        batch = collate(full[0][:2])
        assert batch["input"].shape == (2, SEQ) and batch["cu_seqlens"][-1] == 2 * SEQ
        # mix share is honoured over many draws
        ds3 = PackedDataset(specs, SEQ, EOS, seed=3)
        picks = [ds3._pick_source(g) for g in range(4000)]
        share = 1 - sum(picks) / len(picks)
        assert 0.70 < share < 0.80, share
    print(f"OK data_loader.py smoke test in {time.time() - t0:.1f}s (web share {share:.3f})")
