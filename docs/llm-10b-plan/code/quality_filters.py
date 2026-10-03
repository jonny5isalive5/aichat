"""Document quality filters and eval-set decontamination (section 04 of the plan).

Pure functions with the exact thresholds the pipeline uses: Gopher quality and
repetition rules, the C4 rules we keep, the FineWeb additions, and a 13-gram
decontamination check. Each returns (keep, reasons).

Run:  python3 quality_filters.py   (CPU, < 2 s)
"""
from __future__ import annotations

import hashlib
import re
import time
from collections import Counter

STOP_WORDS = ("the", "be", "to", "of", "and", "that", "have", "with")
TERMINAL = (".", "!", "?", '"', "'", ")")
_WORD = re.compile(r"\w+", re.UNICODE)


def _words(text: str) -> list[str]:
    return text.split()


def gopher_quality(text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    words = _words(text)
    n = len(words)
    if not 50 <= n <= 100_000:
        reasons.append(f"word_count={n} not in [50, 100000]")
    if n:
        mean_len = sum(len(w) for w in words) / n
        if not 3 <= mean_len <= 10:
            reasons.append(f"mean_word_length={mean_len:.1f} not in [3, 10]")
        symbols = sum(w.count("#") + w.count("...") + w.count("…") for w in words)
        if symbols / n > 0.1:
            reasons.append("symbol_to_word_ratio>0.1")
        alpha = sum(1 for w in words if any(c.isalpha() for c in w))
        if alpha / n < 0.8:
            reasons.append(f"alpha_word_fraction={alpha / n:.2f}<0.8")
        lower = {w.lower().strip(".,;:!?") for w in words}
        if sum(1 for s in STOP_WORDS if s in lower) < 2:
            reasons.append("stop_words<2")
    lines = [l for l in text.split("\n") if l.strip()]
    if lines:
        bullets = sum(1 for l in lines if l.lstrip().startswith(("-", "*", "•")))
        if bullets / len(lines) > 0.9:
            reasons.append("bullet_lines>0.9")
        ellipsis = sum(1 for l in lines if l.rstrip().endswith(("...", "…")))
        if ellipsis / len(lines) > 0.3:
            reasons.append("ellipsis_lines>0.3")
    return not reasons, reasons


def _ngram_char_fraction(words: list[str], n: int, top_only: bool) -> float:
    grams = [" ".join(words[i:i + n]) for i in range(len(words) - n + 1)]
    if not grams:
        return 0.0
    counts = Counter(grams)
    total_chars = sum(len(g) for g in grams)
    if top_only:
        g, c = counts.most_common(1)[0]
        return len(g) * c / total_chars
    dup_chars = sum(len(g) * c for g, c in counts.items() if c > 1)
    return dup_chars / total_chars


def gopher_repetition(text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    words = _words(text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for name, items, frac_limit, char_limit in (("line", lines, 0.30, 0.20), ("paragraph", paras, 0.30, 0.20)):
        if len(items) > 1:
            c = Counter(items)
            dup = sum(v for v in c.values() if v > 1)
            if dup / len(items) > frac_limit:
                reasons.append(f"duplicate_{name}_fraction>{frac_limit}")
            dup_chars = sum(len(k) * v for k, v in c.items() if v > 1)
            if dup_chars / sum(len(i) for i in items) > char_limit:
                reasons.append(f"duplicate_{name}_char_fraction>{char_limit}")
    for n, limit in ((2, 0.20), (3, 0.18), (4, 0.16)):
        if _ngram_char_fraction(words, n, top_only=True) > limit:
            reasons.append(f"top_{n}gram_char_fraction>{limit}")
    for n, limit in ((5, 0.15), (6, 0.14), (7, 0.13), (8, 0.12), (9, 0.11), (10, 0.10)):
        if _ngram_char_fraction(words, n, top_only=False) > limit:
            reasons.append(f"duplicate_{n}gram_char_fraction>{limit}")
    return not reasons, reasons


def c4_rules(text: str) -> tuple[bool, list[str]]:
    """The C4 document-level rules we keep (the line-level terminal-punctuation drop is not used)."""
    reasons: list[str] = []
    low = text.lower()
    if "lorem ipsum" in low:
        reasons.append("lorem_ipsum")
    if "{" in text and "}" in text and "javascript" in low:
        reasons.append("javascript_with_braces")
    if "javascript" in low and low.count("javascript") > 2:
        reasons.append("javascript_boilerplate")
    if any(k in low for k in ("terms of use", "privacy policy", "cookie policy", "uses cookies")) and len(_words(text)) < 200:
        reasons.append("policy_boilerplate_short_doc")
    return not reasons, reasons


def fineweb_rules(text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if lines:
        ending = sum(1 for l in lines if l.endswith(TERMINAL))
        if ending / len(lines) < 0.12:
            reasons.append("lines_ending_with_punctuation<0.12")
        short = sum(1 for l in lines if len(l) < 30)
        if short / len(lines) > 0.67:
            reasons.append("short_lines>0.67")
        c = Counter(lines)
        dup_chars = sum(len(k) * v for k, v in c.items() if v > 1)
        if dup_chars / sum(len(l) for l in lines) > 0.10:
            reasons.append("duplicate_line_char_fraction>0.10")
    return not reasons, reasons


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

    def _hashes(self, text: str) -> set[bytes]:
        w = _WORD.findall(text.lower())
        return {hashlib.blake2b(" ".join(w[i:i + self.n]).encode(), digest_size=8).digest()
                for i in range(len(w) - self.n + 1)}

    def contaminated(self, text: str) -> bool:
        return not self.grams.isdisjoint(self._hashes(text))


if __name__ == "__main__":
    t0 = time.time()
    good = ("The committee published its findings on Tuesday after a review of the evidence. "
            "Members said that the data have been checked twice, and that the report will be revised "
            "with new figures next month. The chair thanked the staff for their work.\n"
            "Local officials welcomed the decision but asked for more detail on the timeline. "
            "A spokesperson said the first phase would start in the spring, with funding to be "
            "confirmed by the council in its next budget.\n"
            "Residents who attended the meeting raised questions about traffic and noise. "
            "The planners promised a second consultation before any construction begins, and "
            "published the full report on the town website the same evening.\n")
    assert keep_document(good)[0], keep_document(good)
    bullets = "\n".join(f"- item {i}" for i in range(60))
    ok, r = keep_document(bullets)
    assert not ok and any("bullet" in x for x in r), r
    repeated = ("Buy now and save big. " * 40) + "\n\n" + ("Buy now and save big. " * 40)
    ok, r = keep_document(repeated)
    assert not ok and any("gram" in x or "duplicate" in x for x in r), r
    lorem = good + " Lorem ipsum dolor sit amet."
    ok, r = keep_document(lorem)
    assert not ok and "lorem_ipsum" in r, r
    shorties = "\n".join(["ok", "yes", "no", "fine", "sure", "the end of it"] * 20)
    ok, r = keep_document(shorties)
    assert not ok and any("short_lines" in x for x in r), r
    numbers = " ".join(str(i) for i in range(400))
    ok, r = keep_document(numbers)
    assert not ok and any("alpha_word_fraction" in x for x in r), r
    dec = Decontaminator(["What is the capital city of the country that borders both France and Germany to the east?"])
    assert dec.contaminated("Quiz: what is the capital city of the country that borders both France and Germany to the east? Answer below.")
    assert not dec.contaminated(good)
    print(f"OK quality_filters.py in {time.time() - t0:.1f}s")
