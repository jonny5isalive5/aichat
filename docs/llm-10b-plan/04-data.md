## 04. Dataset acquisition pipeline and deduplication

Covers: dataset acquisition pipeline and data deduplication methods, with `code/dedup_minhash.py` and `code/quality_filters.py`. Numbers from DR section 3 (data plan), section 1 (CPU and storage lines) and section 7 (data readiness).

### Decisions

- **No new web crawl. Build the corpus from already-processed public datasets** (FineWeb-Edu, DCLM-baseline, Nemotron-CC, FinePDFs, The Stack v2, FineWeb-2, FineMath, peS2o, Wikipedia, public-domain books, Cosmopedia). Processing raw Common Crawl would cost 3+ months of a data team before the first token; the public sets already carry extraction, language ID and quality scores.
- **Global deduplication across all four Common Crawl-derived sources before any token is counted.** FineWeb-Edu, DCLM and Nemotron-CC are deduplicated per crawl dump, not against each other; the same page recrawled in ten dumps appears ten times. The DR books 30-50% loss per web source and plans with 8.73T unique tokens in our tokenizer against an 11.0T token budget (average 1.62 epochs; cap 3 epochs stable, 4 including anneal).
- **MinHash LSH near-dedup at 5-word shingles, 112 hashes, 14 bands x 8 rows (Jaccard threshold 0.72, detection 0.92 at 0.8), keep the newest copy; exact dedup by SHA-256 of normalised text; 13-gram decontamination against every evaluation set.**
- **Two production passes on a 768-core CPU partition** (300 GB/h per pass, 9.5 days per pass), due W10 d3 and W11 d7; GPU dedup with NeMo Curator (7,622 GPU-h booked in Block 1) is the fast path for the MinHash stage.
- **Mix is enforced at the shard level by source directories and loader weights**, so changing the mix never rewrites data.
- **Licence manifest signed by counsel at G3**; every document carries provenance (source, dump, URL hash, licence) so a takedown or opt-out can be executed per document.

### Procedure

1. **Legal review (W1-W3, counsel + PM).** Record the terms of every source in the manifest; counsel's W3 memo states the positions on CC-BY-SA (Wikipedia) for model weights, on The Stack v2 attribution and SWH terms, and on the generator-model output clauses for synthetic sets (Nemotron-CC synthetic and Cosmopedia come from Apache-2.0 generators and are kept; OpenMathInstruct-2 is Llama-3.1-licensed and is used in the anneal only under the naming clause). Apply the Hugging Face / Spawning opt-out list and The Stack's opt-out list before any processing. Sources with an unresolved position are excluded, not deferred.
2. **Acquire (W1-W4, contractor).** `huggingface-cli download --repo-type dataset <name> --local-dir /obj/raw/<name>` with `HF_HUB_ENABLE_HF_TRANSFER=1` straight onto a storage node attached to the object store; verify each parquet file's sha256 against the dataset card or a second download; store a `SOURCES.json` with dataset revision hashes. The Stack v2 content comes from Software Heritage with the SWH contents API (keep the permissive-licence subset as marked in the dataset); Wikipedia from the 2026 dumps with `wikiextractor`; Gutenberg and Standard Ebooks via their mirrors. Raw text total 69.7 TB.
3. **Build the v0 corpus (W4-W6, G1: >= 1.5T tokens).** Take the as-released per-dump-deduped FineWeb-Edu (score >= 3), DCLM-baseline, Nemotron-CC HQ and the score-2 tier, apply only the filters in step 5 and tokenisation (section 03). Every ladder run and ablation in Block 1 trains on v0, so Block 1 is never blocked on the production passes.
4. **W3 dedup measurement (0.31 CPU-days).** Domain-stratified 5% sample across ALL dumps of the four CC-derived sources: keep every document whose `hash(registered_domain) mod 20 == 0`, run the full MinHash pipeline on the sample, and publish the measured cross-source and cross-dump duplicate rate per source. A per-dump sample is blind to recrawls (a page recrawled in k of ~100 dumps lands twice in a 4-dump sample with probability well under 1%); the domain-stratified sample sees them. These rates replace the 30/50/50/47/45% planning losses in `dr_calc.py`.
5. **Filter (production pass 1, W7-W10 d3).** datatrove pipeline per source, 768 cores, 300 GB/h:
   - URL filter: adult/malware blocklists (UT1 and the FineWeb list), known boilerplate hosts, the opt-out list.
   - Language ID: fastText `lid.176.bin`, keep if the top language is in the 13-language set with probability >= 0.65 (English) or >= 0.80 (other 12).
   - Gopher quality rules, Gopher repetition rules, the C4 document rules and the three FineWeb rules with the exact thresholds in `code/quality_filters.py`.
   - Quality score: keep the shipped FineWeb-Edu score (>= 3 stable, >= 4 anneal top bin) and the DCLM fastText probability (top decile for the anneal); the 0.5B classifier (W13-W18) refines the anneal pools only and is not on the freeze path.
   - PII: regex scrub of emails, phone numbers, IPv4/IPv6 and IBAN-like strings to fixed placeholders; presidio name/address scrub only on the anneal mix (10x smaller, where the precision matters).
6. **Deduplicate (production pass 2, W10-W11 d7)** in this order; each stage writes a drop list, never a rewritten corpus:
   - URL dedup: normalised URL (scheme, www, trailing slash, utm parameters removed), keep newest.
   - Exact dedup: SHA-256 of normalised text through a Bloom filter sized for 5e9 documents at 1e-6 false positives (Dolma `bff`), keep newest.
   - Near dedup: MinHash LSH as below, union-find clusters, keep newest; cross-source order FineWeb-Edu <- DCLM <- Nemotron-CC (a DCLM document is dropped if it collides with FineWeb-Edu; Nemotron-CC against both).
   - Substring dedup (anneal mix only): suffix-array pass (`deduplicate-text-datasets`) removing spans of >= 50 tokens repeated across documents.
   - Decontamination: 13-gram word overlap against every evaluation set used anywhere in the program (the public suite and the private held-out suite); any hit drops the document and is logged with the eval set name.
7. **G3 data gate (W12 d1).** For every source: measured unique tokens in our tokenizer >= planned stable tokens / 3 (and >= (stable + anneal) / 4); 1M sampled documents queried against the full LSH index show <= 1% with a neighbour at Jaccard >= 0.8; decontamination log reviewed. Fallbacks in order: re-solve the mix at the caps, raise the score-2 tier to 1.0 epoch, raise Nemotron synthetic to 12% of stable, exercise the DR's date-driven anneal rule. Counsel signs the licence manifest.
8. **Tokenise and freeze (W11-W12, G3a: >= 300B frozen tokens by W11 d7)** per section 03; `/pfs/data/v1/<source>/` directories plus `MANIFEST.json`; the frozen mix's token totals go into `measured_unique.json`.
9. **QA (continuous).** 200 random documents per source read by two engineers each week with a 4-point rubric (boilerplate, truncation, language, usefulness); per-source token counts vs plan; duplicate rate before and after each stage; a 1B model trained on v0 vs on the frozen mix (300B tokens each, 2 seeds) must improve held-out loss on every domain set by more than the seed noise.
10. **Mixing at train time.** Loader weights are the DR stable-mix percentages below; the anneal mix is a second weight table switched on at the anneal start step; long-context stages use a third table. The loader logs the realised mix every 10B tokens; a drift > 1% from the table is an alert (section 06).

### Sources and mix

Stable phase (DR section 3; unique tokens are after global dedup, in our tokenizer):

| Source | Licence | Raw (T) | Dedup loss | Unique (T) | Tokens used (T) | Epochs | Stable mix |
|---|---|---|---|---|---|---|---|
| FineWeb-Edu (score >= 3) | ODC-By 1.0 | 1.30 | 30% | 0.79 | 1.98 | 2.5 | 20.0% |
| DCLM-baseline (dedup vs FineWeb-Edu) | CC-BY-4.0 (dataset card) | 3.80 | 50% | 1.65 | 3.31 | 2.0 | 33.4% |
| Nemotron-CC HQ, real text | CC-BY-4.0 | 1.10 | 50% | 0.48 | 0.96 | 2.0 | 9.7% |
| Nemotron-CC HQ, synthetic rephrase/QA | CC-BY-4.0 | 1.90 | 47% | 0.88 | 0.88 | 1.0 | 8.8% |
| FinePDFs (edu-filtered subset) | ODC-By 1.0 | 1.00 | 0% | 0.87 | 0.87 | 1.0 | 8.8% |
| FineWeb-Edu score-2 tier (filler) | ODC-By 1.0 | 4.10 | 45% | 1.96 | 0.14 | 0.07 | 1.4% |
| The Stack v2 (permissive, dedup) | per-file permissive + SWH terms | 0.60 | 0% | 0.60 | 0.90 | 1.5 | 9.1% |
| FineWeb-2 (12 languages, top bin) | ODC-By 1.0 | 1.50 | 0% | 1.31 | 0.52 | 0.4 | 5.3% |
| FineMath 3+ / InfiWebMath 3+ / OpenWebMath | ODC-By 1.0 | 0.07 | 0% | 0.07 | 0.14 | 2.0 | 1.4% |
| peS2o v2 + arXiv (CC-BY / CC0) | ODC-By 1.0 / per paper | 0.07 | 0% | 0.07 | 0.14 | 2.0 | 1.4% |
| Wikipedia (en + 20 languages) | CC-BY-SA 4.0 | 0.015 | 0% | 0.015 | 0.03 | 2.0 | 0.3% |
| Books, public domain | public domain | 0.006 | 0% | 0.006 | 0.012 | 2.0 | 0.1% |
| Cosmopedia v2 | Apache-2.0 | 0.028 | 0% | 0.028 | 0.028 | 1.0 | 0.3% |
| Total | | | | 8.73 | 9.90 | 1.62 avg | 100% |

Anneal mix (1.1T tokens, upweighted high-quality subsets; DR section 3):

| Component | Share | Tokens (B) |
|---|---|---|
| FineWeb-Edu score >= 4 (top bin) | 12% | 132 |
| DCLM-baseline top decile | 15% | 165 |
| Nemotron-CC synthetic HQ (QA / distill / extract) | 13% | 143 |
| Code HQ (Stack v2 edu-filtered, python-edu, synthetic with unit tests) | 16% | 176 |
| Math HQ from the stable pool (FineMath 4+, InfiWebMath 4+, OpenWebMath) | 3% | 33 |
| Math HQ, anneal-only (Nemotron-CC-Math v1, OpenMathInstruct-2) | 10% | 110 |
| Instruction-style (Nemotron-Pretraining-SFT-v1, SmolTalk, Tulu-3 SFT mix) | 12% | 132 |
| Papers + Wikipedia + public-domain books | 6% | 66 |
| FinePDFs top bin | 5% | 55 |
| Multilingual (FineWeb-2 top bin) | 8% | 88 |

Long-context stages (50B at 32k, 20B at 128k): repo-level concatenated code 25%, papers 25%, public-domain books 20%, long web/PDF documents 10%, short-context replay of the anneal mix 20%.

### Pipeline

```text
 object store (raw parquet, 69.7 TB)
      |
      v
 [reader] -> [URL filter + opt-out] -> [language ID fastText >= 0.65/0.80]
      |
      v
 [Gopher quality] -> [Gopher repetition] -> [C4 doc rules] -> [FineWeb rules]
      |
      v
 [quality score: FineWeb-Edu >= 3 | DCLM fastText]  -> [PII scrub]
      |                                                       pass 1 output: parquet + provenance
      v
 [URL dedup] -> [exact SHA-256 / Bloom] -> [MinHash LSH 5-gram, 112 hashes, 14 x 8, keep newest]
      |                                      (NeMo Curator on GPUs, or datatrove on 768 cores)
      v
 [substring dedup, anneal mix only] -> [13-gram decontamination vs every eval set]
      |                                                       pass 2 output: drop lists + stats
      v
 [tokenize_shards.py per source] -> /pfs/data/v1/<source>/*.bin|.idx|.json + MANIFEST.json
      |
      v
 [data_loader.py: source weights = stable / anneal / long-context tables]
```

### Deduplication detail

MinHash LSH parameters and what they mean: with b = 14 bands of r = 8 rows, a pair with Jaccard s collides in at least one band with probability 1 - (1 - s^8)^14: 0.05 at s = 0.5, 0.21 at 0.6, 0.57 at 0.7, 0.92 at 0.8, 1.00 at 0.9; the 50% point is (1/14)^(1/8) = 0.72. This is the FineWeb/DCLM operating point: near-identical boilerplate variants are caught, paraphrases are not. The W5-W6 threshold ablation trains 1B models on 10-dump subsets deduplicated at 0.7 / 0.8 / 0.9 and keeps the setting with the best held-out loss (1.1 CPU-days to build the three corpora).

Compute for the near-dedup stage at scale: 5-gram shingling plus 112 hashes over 46.4 TB of CC-derived text is 377,179 core-hours of the total CPU need (two passes, all stages) against 1,032,192 booked (768 cores x 8 weeks x 168 h), so the partition has 2.7x headroom for re-runs. On GPUs, NeMo Curator's fuzzy dedup runs the same signature + LSH + connected-components in about 60 GPU-hours per TB of text; the 7,622 GPU-h booked in Block 1 cover the four CC sources with margin.

Why keep the newest copy: recrawls fix broken extractions and remove expired boilerplate; newest also keeps the provenance date monotone for the takedown process.

Exact dedup at scale: Bloom filter with 5e9 entries at a 1e-6 false-positive rate needs 5e9 x 28.8 bits = 18 GB of RAM on one of the three RAM nodes; false positives drop one real document in a million, which is acceptable.

Storage layout:

```text
/obj/raw/<dataset>/<revision>/...parquet          immutable downloads + SOURCES.json
/obj/processed/v1/<source>/pass1/*.parquet         filtered text + provenance columns
/obj/processed/v1/<source>/pass2/drop_*.parquet    per-stage drop lists (doc_id, reason)
/pfs/data/v1/<source>/<source>-NNNNN.{bin,idx,json} tokenized shards (section 03)
/pfs/data/v1/MANIFEST.json                         every shard, sha256, tokens, tokenizer hash
/pfs/data/v1/measured_unique.json                  per-source unique tokens for the G3 gate
```

Provenance columns on every document: `source`, `dump`, `url_sha256`, `licence`, `crawl_date`, `pass1_reasons`, `quality_score`. A takedown is a query on `url_sha256`, a drop-list append, and a shard rebuild for the affected source.

### Reference implementation

MinHash signature and LSH (`code/dedup_minhash.py`):

```python
class MinHasher:
    def __init__(self, n_hashes: int = N_HASHES, seed: int = 42) -> None:
        rng = np.random.default_rng(seed)
        self.a = rng.integers(1, MERSENNE_31, size=n_hashes, dtype=np.uint64)
        self.b = rng.integers(0, MERSENNE_31, size=n_hashes, dtype=np.uint64)

    def signature(self, sh: np.ndarray) -> np.ndarray:
        # (a * x + b) mod p for every (hash function, shingle); min over shingles -> [n_hashes]
        h = (self.a[:, None] * sh[None, :] + self.b[:, None]) % PRIME_32
        return h.min(axis=1).astype(np.uint32)


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
```

Filter composition and decontamination (`code/quality_filters.py`):

```python
def keep_document(text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    for f in (gopher_quality, gopher_repetition, c4_rules, fineweb_rules):
        ok, r = f(text)
        reasons += r
    return not reasons, reasons


class Decontaminator:
    """13-gram overlap against every evaluation set (word-level, lowercased)."""

    def __init__(self, eval_texts: list[str], n: int = 13) -> None:
        self.n = n
        self.grams: set[bytes] = set()
        for t in eval_texts:
            self.grams.update(self._hashes(t))

    def contaminated(self, text: str) -> bool:
        return not self.grams.isdisjoint(self._hashes(text))
```

Illustrative datatrove stage list for pass 1 (requires `datatrove[all]`; not executed here):

```python
from datatrove.executor import SlurmPipelineExecutor
from datatrove.pipeline.readers import ParquetReader
from datatrove.pipeline.filters import URLFilter, LanguageFilter, GopherQualityFilter, GopherRepetitionFilter, C4QualityFilter, FineWebQualityFilter
from datatrove.pipeline.writers import ParquetWriter

SlurmPipelineExecutor(
    job_name="pass1-dclm", tasks=3072, time="48:00:00", partition="cpu768", cpus_per_task=1,
    pipeline=[
        ParquetReader("/obj/raw/dclm-baseline", text_key="text"),
        URLFilter(), LanguageFilter(languages=LANGS, language_threshold=0.65),
        GopherQualityFilter(), GopherRepetitionFilter(), C4QualityFilter(filter_no_terminal_punct=False),
        FineWebQualityFilter(),
        ParquetWriter("/obj/processed/v1/dclm/pass1"),
    ],
).run()
```

Smoke test output:

```text
Jaccard  P(detected) with 14 bands x 8 rows
  0.60     0.211
  0.70     0.565
  0.80     0.924
  threshold (P=0.5) ~ (1/b)^(1/r) = 0.719
  measured detection rate at Jaccard ~0.67: 0.40 (expected ~0.4)
OK dedup_minhash.py in 0.0s: 85 docs, 20 near-dup clusters, 25 dropped, 5 exact dups
OK quality_filters.py in 0.0s
```

### Checklist

- [ ] Licence manifest complete; counsel's W3 memo filed; opt-out lists applied; excluded sources listed with reasons.
- [ ] All raw downloads verified by sha256 against a second copy; `SOURCES.json` with revisions committed.
- [ ] v0 corpus >= 1.5T tokens tokenized by end of W6 (G1).
- [ ] W3 domain-stratified dedup measurement published for all four CC sources; planning losses in `dr_calc.py` replaced.
- [ ] Pass 1 complete by W10 d3 with per-stage drop counts; pass 2 by W11 d7.
- [ ] G3 passed: per-source unique tokens >= plan / 3; <= 1% near-dup neighbours at Jaccard >= 0.8 in a 1M sample; decontamination log reviewed.
- [ ] Frozen mix tokenized; `MANIFEST.json` and `measured_unique.json` written; loader realised mix within 1% of the tables.
