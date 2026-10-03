"""Exact and near-duplicate detection for pretraining text (section 04 of the plan).

Near-dedup: word 5-gram shingles -> MinHash with 112 hash functions -> LSH with
14 bands x 8 rows (detection probability 0.92 at Jaccard 0.8, 0.21 at 0.6) ->
union-find clusters -> keep the NEWEST copy of each cluster.
This is the reference for the parameters used in datatrove / NeMo Curator at scale;
it runs on a few thousand documents here, not on 10T tokens.

Run:  python3 dedup_minhash.py   (CPU, < 5 s)
"""
from __future__ import annotations

import hashlib
import random
import re
import time
from collections import defaultdict
from dataclasses import dataclass

import numpy as np

N_HASHES, BANDS, ROWS = 112, 14, 8
assert BANDS * ROWS == N_HASHES
MERSENNE_31 = (1 << 31) - 1          # a < 2^31 keeps a*x < 2^63 in uint64
PRIME_32 = 4_294_967_291             # largest prime < 2^32
_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    return _WS.sub(" ", text.lower()).strip()


def exact_key(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def shingles(text: str, k: int = 5) -> np.ndarray:
    """uint32 hashes of word k-grams (k=5 words, the DR setting)."""
    words = normalise(text).split()
    if len(words) < k:
        words = words + ["<pad>"] * (k - len(words))
    grams = {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}
    out = np.fromiter((int.from_bytes(hashlib.blake2b(g.encode(), digest_size=4).digest(), "little")
                       for g in grams), dtype=np.uint64, count=len(grams))
    return out


class MinHasher:
    def __init__(self, n_hashes: int = N_HASHES, seed: int = 42) -> None:
        rng = np.random.default_rng(seed)
        self.a = rng.integers(1, MERSENNE_31, size=n_hashes, dtype=np.uint64)
        self.b = rng.integers(0, MERSENNE_31, size=n_hashes, dtype=np.uint64)

    def signature(self, sh: np.ndarray) -> np.ndarray:
        # (a * x + b) mod p for every (hash function, shingle); min over shingles -> [n_hashes]
        h = (self.a[:, None] * sh[None, :] + self.b[:, None]) % PRIME_32
        return h.min(axis=1).astype(np.uint32)


@dataclass
class Doc:
    doc_id: int
    text: str
    timestamp: int  # crawl date as an int (YYYYMMDD); newest copy is kept


class UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def near_dedup(docs: list[Doc], hasher: MinHasher | None = None) -> tuple[set[int], list[list[int]]]:
    """Returns (ids to drop, clusters). Within each cluster the newest document survives."""
    hasher = hasher or MinHasher()
    sigs = [hasher.signature(shingles(d.text)) for d in docs]
    buckets: dict[tuple[int, bytes], list[int]] = defaultdict(list)
    for i, sig in enumerate(sigs):
        for band in range(BANDS):
            key = (band, sig[band * ROWS:(band + 1) * ROWS].tobytes())
            buckets[key].append(i)
    uf = UnionFind(len(docs))
    for members in buckets.values():
        for j in members[1:]:
            uf.union(members[0], j)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(docs)):
        groups[uf.find(i)].append(i)
    clusters = [g for g in groups.values() if len(g) > 1]
    drop: set[int] = set()
    for g in clusters:
        keep = max(g, key=lambda i: (docs[i].timestamp, -docs[i].doc_id))
        drop.update(i for i in g if i != keep)
    return drop, clusters


def exact_dedup(docs: list[Doc]) -> set[int]:
    """Drop later exact copies (after normalisation). At scale: a Bloom filter (Dolma bff)."""
    seen: dict[str, int] = {}
    drop: set[int] = set()
    for i, d in enumerate(sorted(docs, key=lambda d: (-d.timestamp, d.doc_id))):
        k = exact_key(d.text)
        if k in seen:
            drop.add(docs.index(d))
        else:
            seen[k] = i
    return drop


def detection_probability(jaccard: float, bands: int = BANDS, rows: int = ROWS) -> float:
    return 1 - (1 - jaccard ** rows) ** bands


def print_s_curve() -> None:
    print("Jaccard  P(detected) with 14 bands x 8 rows")
    for s in (0.5, 0.6, 0.7, 0.72, 0.8, 0.9, 0.95):
        print(f"  {s:4.2f}     {detection_probability(s):.3f}")
    print(f"  threshold (P=0.5) ~ (1/b)^(1/r) = {(1 / BANDS) ** (1 / ROWS):.3f}")


if __name__ == "__main__":
    t0 = time.time()
    rng = random.Random(0)
    vocab = [f"w{i}" for i in range(5000)]
    base = [" ".join(rng.choice(vocab) for _ in range(80)) for _ in range(60)]
    docs: list[Doc] = []
    expected_pairs: set[tuple[int, int]] = set()
    for i, text in enumerate(base):
        docs.append(Doc(len(docs), text, 20240101 + i))
        if i < 20:  # a near duplicate: 1 of 80 words changed -> 5 of 76 shingles differ, Jaccard 0.88
            words = text.split()
            words[rng.randrange(80)] = rng.choice(vocab)
            docs.append(Doc(len(docs), " ".join(words), 20250101 + i))
            expected_pairs.add((len(docs) - 2, len(docs) - 1))
        if i < 5:  # an exact copy with an older date
            docs.append(Doc(len(docs), text.upper(), 20230101))
    drop, clusters = near_dedup(docs)
    found = {tuple(sorted(c[:2])) for c in clusters if len(c) == 2}
    for a, b in expected_pairs:
        assert any(a in c and b in c for c in clusters), (a, b)
    # the newest copy is kept
    for a, b in expected_pairs:
        assert a in drop and b not in drop
    # unrelated documents are never clustered
    unrelated = [d.doc_id for d in docs if d.doc_id >= 45]
    assert all(len([i for i in c if i in unrelated]) <= 1 for c in clusters), clusters
    ex = exact_dedup(docs)
    assert len(ex) == 5 and all(docs[i].timestamp == 20230101 for i in ex)
    print_s_curve()
    assert abs(detection_probability(0.8) - 0.924) < 0.005
    # below the threshold detection is probabilistic: 3 of 80 words changed -> Jaccard ~0.67, P ~ 0.4
    weak: list[Doc] = []
    for i, text in enumerate(base[:40]):
        words = text.split()
        for pos in rng.sample(range(80), 3):
            words[pos] = rng.choice(vocab)
        weak += [Doc(2 * i, text, 1), Doc(2 * i + 1, " ".join(words), 2)]
    _, weak_clusters = near_dedup(weak)
    rate = len(weak_clusters) / 40
    print(f"  measured detection rate at Jaccard ~0.67: {rate:.2f} (expected ~0.4)")
    assert 0.15 < rate < 0.7, rate
    print(f"OK dedup_minhash.py in {time.time() - t0:.1f}s: {len(docs)} docs, "
          f"{len(clusters)} near-dup clusters, {len(drop)} dropped, {len(ex)} exact dups")
