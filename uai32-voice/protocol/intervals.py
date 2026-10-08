#!/usr/bin/env python3
"""Interval arithmetic for the voice-command challenge protocol review.
Self-contained (no scipy): exact binomial tail sums, Clopper-Pearson by bisection,
Wilson score interval, power of the proposed pass rules, shuffled-label control
expectation by exact enumeration over permutations, and the recording time budget.
"""
import math, random, itertools
from math import comb, log, sqrt

def binom_cdf(k, n, p):
    """P(X <= k) for X ~ Bin(n, p)."""
    if k < 0: return 0.0
    if k >= n: return 1.0
    if p <= 0: return 1.0
    if p >= 1: return 0.0
    # log-space terms to avoid overflow for n up to a few thousand
    lp, lq = log(p), log(1 - p)
    return sum(math.exp(math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq)
               for i in range(0, k + 1))

def binom_sf_ge(k, n, p):
    """P(X >= k)."""
    return 1.0 - binom_cdf(k - 1, n, p)

def bisect(f, lo, hi, it=200):
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0: hi = mid
        else: lo = mid
    return 0.5 * (lo + hi)

def clopper_pearson(k, n, alpha=0.05):
    """Exact two-sided (1-alpha) interval."""
    if k == 0: lo = 0.0
    else: lo = bisect(lambda p: binom_sf_ge(k, n, p) - alpha / 2, 0.0, 1.0)
    if k == n: hi = 1.0
    else: hi = bisect(lambda p: -(binom_cdf(k, n, p) - alpha / 2), 0.0, 1.0)
    return lo, hi

def cp_upper_one_sided(k, n, alpha=0.05):
    """One-sided 95% upper bound (the quantity a 'rate <= x%' claim needs)."""
    if k == n: return 1.0
    return bisect(lambda p: -(binom_cdf(k, n, p) - alpha), 0.0, 1.0)

def cp_lower_one_sided(k, n, alpha=0.05):
    if k == 0: return 0.0
    return bisect(lambda p: binom_sf_ge(k, n, p) - alpha, 0.0, 1.0)

def wilson(k, n, z=1.959964):
    ph = k / n
    den = 1 + z * z / n
    cen = (ph + z * z / (2 * n)) / den
    half = z * sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return cen - half, cen + half

def pct(x): return f"{100*x:.2f}%"

out = []
_pending = ""
def P(*a, end="\n"):
    global _pending
    s = _pending + " ".join(str(x) for x in a)
    if end == "":
        _pending = s; return
    _pending = ""; print(s); out.append(s)

P("=" * 78)
P("A. FALSE-ACCEPT GATE: '<= 1% false accepts on 300 recordings'")
P("=" * 78)
P("Observed k/300 -> two-sided 95% Clopper-Pearson, Wilson, and one-sided 95% upper bound")
for k in range(0, 6):
    lo, hi = clopper_pearson(k, 300); wl, wh = wilson(k, 300)
    P(f"  k={k}: point {pct(k/300):>6}  CP95 [{pct(lo)}, {pct(hi)}]  Wilson [{pct(wl)}, {pct(wh)}]  one-sided upper95 {pct(cp_upper_one_sided(k,300))}")
P("Pooled over 3 speakers, k/900:")
for k in [0, 1, 2, 3, 5, 9, 12, 18]:
    lo, hi = clopper_pearson(k, 900)
    P(f"  k={k:>2}: point {pct(k/900):>6}  CP95 [{pct(lo)}, {pct(hi)}]  one-sided upper95 {pct(cp_upper_one_sided(k,900))}")

P("\nSmallest n such that the one-sided 95% upper bound <= target, given k observed:")
def n_needed(k, target, alpha=0.05):
    n = max(k, 1)
    while cp_upper_one_sided(k, n, alpha) > target: n += 1
    return n
for target in [0.01, 0.02, 0.005]:
    P(f"  target {pct(target)}: " + ", ".join(f"k={k}: n>={n_needed(k, target)}" for k in range(0, 4)))
P(f"  (rule of three check: ln(0.05)/ln(0.99) = {log(0.05)/log(0.99):.1f})")

P("\nOperating characteristic of the rule 'pass if k <= 3 of 300' at true FA rate p:")
for p in [0.002, 0.005, 0.01, 0.015, 0.02, 0.03]:
    P(f"  true p={pct(p):>6}: P(pass) = {binom_cdf(3, 300, p):.3f}")
P("Operating characteristic of 'pass if k <= 0 of 300':")
for p in [0.002, 0.005, 0.01, 0.02]:
    P(f"  true p={pct(p):>6}: P(pass) = {binom_cdf(0, 300, p):.3f}")
P("Pooled rule 'pass if k <= 9 of 900' (point estimate <= 1.0%):")
for p in [0.005, 0.0075, 0.01, 0.015, 0.02]:
    P(f"  true p={pct(p):>6}: P(pass) = {binom_cdf(9, 900, p):.3f}")
P("Pooled rule 'pass if k <= 4 of 900' (one-sided upper bound ~1.0%):")
for p in [0.002, 0.003, 0.005, 0.01, 0.02]:
    P(f"  true p={pct(p):>6}: P(pass) = {binom_cdf(4, 900, p):.3f}")

P("\nSample size to REJECT H0: p >= 2% at alpha=0.05 while accepting c false accepts:")
for c in [0, 1, 2, 3, 5]:
    n = c + 1
    while binom_cdf(c, n, 0.02) > 0.05: n += 1
    P(f"  c={c}: n >= {n}   (power at true p=0.5%: {binom_cdf(c, n, 0.005):.3f}; at 1%: {binom_cdf(c, n, 0.01):.3f})")
P("Sample size to REJECT H0: p >= 1% at alpha=0.05 (i.e. 'convincingly below 1%'):")
for c in [0, 1, 2, 3, 5, 10]:
    n = c + 1
    while binom_cdf(c, n, 0.01) > 0.05: n += 1
    P(f"  c={c}: n >= {n}   (power at true p=0.25%: {binom_cdf(c, n, 0.0025):.3f}; at 0.5%: {binom_cdf(c, n, 0.005):.3f})")

P("\n" + "=" * 78)
P("B. ACCURACY GATE: '>= 90% per command on 30 fresh recordings' (27/30)")
P("=" * 78)
for k in [30, 29, 28, 27, 26, 25, 24, 21]:
    lo, hi = clopper_pearson(k, 30); wl, wh = wilson(k, 30)
    P(f"  {k}/30 = {pct(k/30):>7}  CP95 [{pct(lo)}, {pct(hi)}]  Wilson [{pct(wl)}, {pct(wh)}]  one-sided lower95 {pct(cp_lower_one_sided(k,30))}")
P("Pooled per speaker (3 commands x 30 = 90) and over speakers (9 cells x 30 = 270):")
for k, n in [(81, 90), (85, 90), (243, 270), (250, 270), (256, 270), (260, 270), (90, 90), (270, 270)]:
    lo, hi = clopper_pearson(k, n)
    P(f"  {k}/{n} = {pct(k/n):>7}  CP95 [{pct(lo)}, {pct(hi)}]  one-sided lower95 {pct(cp_lower_one_sided(k,n))}")
P("Smallest n with zero errors whose one-sided 95% lower bound is >= 90%: ", end="")
n = 1
while cp_lower_one_sided(n, n) < 0.90: n += 1
P(n)
P("Smallest n with 10% errors (k = 0.9 n) whose lower bound is >= 85%: ", end="")
for n in range(30, 2000, 10):
    k = round(0.9 * n)
    if cp_lower_one_sided(k, n) >= 0.85: P(n, f"({k}/{n})"); break

P("\nPer-cell rule P(cell passes 27/30) and P(all 9 or 12 cells pass) at true per-utterance accuracy p:")
for p in [0.85, 0.90, 0.93, 0.95, 0.97, 0.98, 0.99]:
    q = binom_sf_ge(27, 30, p)
    P(f"  p={pct(p):>6}: P(cell >=27/30) = {q:.3f}   all 9 cells: {q**9:.3f}   all 12 cells: {q**12:.3f}")
P("Floor rule P(cell >= 24/30) and P(all cells) at true p:")
for p in [0.85, 0.90, 0.93, 0.95, 0.97]:
    q = binom_sf_ge(24, 30, p)
    P(f"  p={pct(p):>6}: P(cell >=24/30) = {q:.3f}   all 9: {q**9:.3f}   all 12: {q**12:.3f}")
P("Pooled rule P(>= 243/270) at true p:")
for p in [0.85, 0.88, 0.90, 0.92, 0.93, 0.95]:
    P(f"  p={pct(p):>6}: P(pooled >= 243/270) = {binom_sf_ge(243, 270, p):.3f}")

P("\nMonte Carlo: combined rule (pooled >= 243/270 AND every cell >= 24/30), iid utterances:")
random.seed(1)
def sim_combined(p, cells=9, n=30, R=20000, pooled_min=243, floor=24):
    ok = 0
    for _ in range(R):
        cs = [sum(random.random() < p for _ in range(n)) for _ in range(cells)]
        if sum(cs) >= pooled_min * cells / 9 and min(cs) >= floor: ok += 1
    return ok / R
for p in [0.88, 0.90, 0.92, 0.93, 0.95, 0.97]:
    P(f"  p={pct(p):>6}: P(pass) = {sim_combined(p):.3f}")

P("\nSame rule but with session clustering (3 sessions x 10 per cell; per-session accuracy drawn")
P("from Beta with mean p and sd 0.05 to mimic day-to-day drift):")
def sim_clustered(p, sd=0.05, cells=9, R=20000, pooled_min=243, floor=24):
    # beta parameters from mean/sd
    v = sd * sd; a = p * (p * (1 - p) / v - 1); b = (1 - p) * (p * (1 - p) / v - 1)
    ok = 0
    for _ in range(R):
        cs = []
        for _c in range(cells):
            c = 0
            for _s in range(3):
                ps = random.betavariate(a, b)
                c += sum(random.random() < ps for _ in range(10))
            cs.append(c)
        if sum(cs) >= pooled_min * cells / 9 and min(cs) >= floor: ok += 1
    return ok / R
for p in [0.90, 0.93, 0.95, 0.97]:
    P(f"  p={pct(p):>6}: P(pass) = {sim_clustered(p):.3f}")

P("\n" + "=" * 78)
P("C. CONTROLS")
P("=" * 78)
P("Chance level for 3 classes on 270 test utterances (no rejection): 95% range of k/270 at p=1/3:")
lo = 0
while binom_cdf(lo, 270, 1/3) < 0.025: lo += 1
hi = 0
while binom_cdf(hi, 270, 1/3) < 0.975: hi += 1
P(f"  central 95%: [{lo}/270 = {pct(lo/270)}, {hi}/270 = {pct(hi/270)}]; 99.9th percentile: ", end="")
q = 0
while binom_cdf(q, 270, 1/3) < 0.999: q += 1
P(f"{q}/270 = {pct(q/270)}")
P("Chance level with 4 classes on 360 utterances (p=1/4): ", end="")
q = 0
while binom_cdf(q, 360, 1/4) < 0.999: q += 1
P(f"99.9th percentile {q}/360 = {pct(q/360)}")

P("\nExample-level shuffled-label control, exact enumeration: 3 words x 5 enrolment examples,")
P("labels permuted uniformly at random; assume a PERFECT word recogniser that predicts the")
P("majority shuffled label of each word (ties -> uniformly random among tied labels).")
P("Expected test accuracy under the permuted labels (what a 'good' learner can still score):")
def shuffled_expectation(n_words=3, per=5):
    labels = [w for w in range(n_words) for _ in range(per)]
    # enumerate multiset permutations by assigning labels to positions: count via itertools.permutations is 15! too big;
    # instead enumerate compositions: for each word, how many of each label it received (contingency tables
    # with margins (per,...,per)), weight by multinomial counts.
    from functools import lru_cache
    total_weight = 0
    acc_weight = 0.0
    def tables(remaining_cols, rows_left):
        # yield list of rows (each a tuple of counts summing to per) with column sums == remaining_cols
        if rows_left == 1:
            yield [tuple(remaining_cols)]
            return
        # enumerate a row: counts of each label for this word, sum per, each <= remaining col
        def rows(i, left, cur):
            if i == n_words - 1:
                if left <= remaining_cols[i]:
                    yield cur + [left]
                return
            for c in range(0, min(left, remaining_cols[i]) + 1):
                yield from rows(i + 1, left - c, cur + [c])
        for r in rows(0, per, []):
            rem = [remaining_cols[i] - r[i] for i in range(n_words)]
            for rest in tables(rem, rows_left - 1):
                yield [tuple(r)] + rest
    for t in tables([per] * n_words, n_words):
        # weight = prod over words of multinomial(per; row) ; sum over tables = (n_words*per)!/(per!)^n_words
        w = 1
        for r in t:
            m = math.factorial(per)
            for c in r: m //= math.factorial(c)
            w *= m
        total_weight += w
        # accuracy: for word i, majority label among its row; correct if == i
        a = 0.0
        for i, r in enumerate(t):
            mx = max(r); ties = [j for j, c in enumerate(r) if c == mx]
            a += (1.0 / len(ties)) if i in ties else 0.0
        acc_weight += w * a / n_words
    return acc_weight / total_weight
e3 = shuffled_expectation(3, 5)
P(f"  3 words x 5: expected accuracy = {pct(e3)}  (chance 33.3%)")
e4 = shuffled_expectation(4, 5)
P(f"  4 words x 5: expected accuracy = {pct(e4)}  (chance 25.0%)")
P("  -> the MEAN over permutations is chance, but a single permuted run is NOT expected to sit at chance; use >= 20 permutations and a")
P("     permutation p-value, or report the max over permutations.")

# distribution of the per-permutation 'ideal' accuracy for 3x5 via sampling
random.seed(2)
vals = []
for _ in range(20000):
    lab = [w for w in range(3) for _ in range(5)]
    random.shuffle(lab)
    a = 0.0
    for w in range(3):
        row = [lab[w*5:(w+1)*5].count(j) for j in range(3)]
        mx = max(row); ties = [j for j, c in enumerate(row) if c == mx]
        a += (1 / len(ties)) if w in ties else 0
    vals.append(a / 3)
vals.sort()
P(f"  3x5 ideal-recogniser accuracy under permutation: median {pct(vals[len(vals)//2])}, 95th pct {pct(vals[int(0.95*len(vals))])}, max {pct(vals[-1])}, P(acc >= 2/3) = {sum(v >= 2/3 - 1e-9 for v in vals)/len(vals):.3f}")

P("\n" + "=" * 78)
P("D. DTW vs NN paired comparison on the same 270 (or 360) utterances")
P("=" * 78)
P("McNemar exact test: discordant pairs b (NN right, DTW wrong) vs c (NN wrong, DTW right).")
P("Two-sided p = 2*min tail of Bin(b+c, 1/2). Smallest (b, c=0) that reaches p < 0.05: ", end="")
m = 1
while 2 * binom_cdf(0, m, 0.5) >= 0.05: m += 1
P(f"{m} discordant all one way (p = {2*binom_cdf(0, m, 0.5):.4f})")
P("If both systems are ~93% and discordance is 8% of 270 (~22 pairs), detectable split (one-sided p<0.05): ", end="")
for b in range(11, 23):
    if binom_sf_ge(b, 22, 0.5) < 0.05: P(f"{b} vs {22-b}  -> a difference of ~{pct((2*b-22)/270)} in accuracy"); break

P("\n" + "=" * 78)
P("E. RECORDING TIME BUDGET PER SPEAKER (prompted, 2.5 s clip + 2.5 s gap = 5 s per item)")
P("=" * 78)
items = {
    "enrolment (4 commands x 5)": 20,
    "developer/pipeline sanity clips, session 1 only (4 x 3)": 12,
    "fresh test utterances (4 commands x 30)": 120,
    "own-voice negatives: confusable words (3 x 4 commands x 10)": 120,
    "own-voice negatives: unrelated words/short phrases": 60,
    "own-voice negatives: non-speech (cough, laugh, hum, silence w/ room noise)": 20,
}
tot = sum(items.values())
for k_, v in items.items(): P(f"  {v:>4}  {k_}")
P(f"  {tot:>4}  total prompted items -> {tot*5/60:.0f} min of prompting, spread over 4 sessions on 4 days")
P(f"  plus ~5 min setup/consent per session: ~{tot*5/60 + 20:.0f} min per speaker, ~{(tot*5/60+20)*4/60:.1f} h for 4 recruited speakers (1 spare)")
P("  public negatives (GSC v0.02 + background noise crops): 0 recording minutes, selected by seeded script")

with open("/tmp/claude-0/-home-user-aichat/809e473e-6ead-51f0-b725-4e01dff2b821/scratchpad/voice-protocol-review/intervals_output.txt", "w") as f:
    f.write("\n".join(out) + "\n")


P("\n" + "=" * 78)
P("F. EXTRA: rules actually recommended in the protocol")
P("=" * 78)
P("Exact distribution of ideal-recogniser accuracy under example-level label permutation (3 words x 5):")
from fractions import Fraction
def perm_dist(n_words=3, per=5):
    dist = {}
    def tables(remaining_cols, rows_left):
        if rows_left == 1:
            yield [tuple(remaining_cols)]; return
        def rows(i, left, cur):
            if i == n_words - 1:
                if left <= remaining_cols[i]: yield cur + [left]
                return
            for c in range(0, min(left, remaining_cols[i]) + 1):
                yield from rows(i + 1, left - c, cur + [c])
        for r in rows(0, per, []):
            rem = [remaining_cols[i] - r[i] for i in range(n_words)]
            for rest in tables(rem, rows_left - 1):
                yield [tuple(r)] + rest
    total = 0
    for t in tables([per] * n_words, n_words):
        w = 1
        for r in t:
            m = math.factorial(per)
            for c in r: m //= math.factorial(c)
            w *= m
        total += w
        # accuracy distribution: ties broken uniformly -> contributes fractional probability mass to several outcomes
        # enumerate tie-break outcomes
        choices = []
        for i, r in enumerate(t):
            mx = max(r); ties = [j for j, c in enumerate(r) if c == mx]
            choices.append([(1 if j == i else 0, Fraction(1, len(ties))) for j in ties])
        for combo in itertools.product(*choices):
            acc = Fraction(sum(c[0] for c in combo), n_words)
            pr = Fraction(w)
            for c in combo: pr *= c[1]
            dist[acc] = dist.get(acc, Fraction(0)) + pr
    return {k: v / total for k, v in dist.items()}
d = perm_dist(3, 5)
for k in sorted(d):
    P(f"  acc = {float(k):.3f}: P = {float(d[k]):.4f}")
tail = lambda x: float(sum(v for k, v in d.items() if k >= x))
P(f"  P(acc >= 2/3) = {tail(Fraction(2,3)):.4f}; P(acc = 1) = {tail(Fraction(1)):.4f}")
p1 = tail(Fraction(1))
P(f"  With R=20 permutations: P(at least one permuted run scores 100%) = {1-(1-p1)**20:.3f}")
P(f"  P(at most 1 of 20 permuted runs >= 90%) = {(1-p1)**20 + 20*p1*(1-p1)**19:.3f}  (so 'trained beats >=19 of 20' is NOT a safe rule at n=15)")
d4 = perm_dist(4, 5)
P(f"  4 words x 5: P(acc >= 1/2) = {float(sum(v for k, v in d4.items() if k >= Fraction(1,2))):.4f}; P(acc = 1) = {float(d4.get(Fraction(1), 0)):.4f}; P(acc >= 3/4) = {float(sum(v for k, v in d4.items() if k >= Fraction(3,4))):.4f}")

P("\nRecommended negative-set gate: 600 per speaker, 1,800 pooled; pass if pooled k <= 18 (1.0%)")
for k, n in [(18, 1800), (9, 1800), (4, 1800), (0, 1800), (12, 600), (6, 600), (3, 600), (0, 600), (6, 200), (4, 200), (2, 200), (0, 200), (3, 120), (6, 120), (0, 120)]:
    lo, hi = clopper_pearson(k, n)
    P(f"  {k:>2}/{n}: point {pct(k/n):>6}  CP95 [{pct(lo)}, {pct(hi)}]  one-sided upper95 {pct(cp_upper_one_sided(k,n))}")
P("Operating characteristic of 'pooled k <= 18 of 1800':")
for p in [0.003, 0.005, 0.0075, 0.01, 0.015, 0.02]:
    P(f"  true p={pct(p):>6}: P(pass) = {binom_cdf(18, 1800, p):.3f}")
P("Operating characteristic of per-speaker floor 'k <= 12 of 600' (all three speakers must satisfy it):")
for p in [0.005, 0.01, 0.015, 0.02, 0.03]:
    q = binom_cdf(12, 600, p)
    P(f"  true p={pct(p):>6}: P(one speaker ok) = {q:.3f}; all three = {q**3:.3f}")

P("\nn for 80% power to show p < 1% (alpha 0.05, one-sided) when the true rate is 0.5% / 0.25%:")
for ptrue in [0.005, 0.0025]:
    found = None
    for n in range(100, 6000, 10):
        # largest c with P(X<=c | 0.01) <= 0.05
        c = -1
        while binom_cdf(c + 1, n, 0.01) <= 0.05: c += 1
        if c >= 0 and binom_cdf(c, n, ptrue) >= 0.80:
            found = (n, c); break
    P(f"  true p={pct(ptrue)}: n = {found[0]}, pass if k <= {found[1]}")

P("\n12-cell retest after the 4th command (360 utterances): pooled >= 324/360 AND every cell >= 24/30")
def sim12(p, R=20000):
    ok = 0
    for _ in range(R):
        cs = [sum(random.random() < p for _ in range(30)) for _ in range(12)]
        if sum(cs) >= 324 and min(cs) >= 24: ok += 1
    return ok / R
random.seed(3)
for p in [0.90, 0.92, 0.93, 0.95, 0.97]:
    P(f"  p={pct(p):>6}: P(pass) = {sim12(p):.3f}")
lo, hi = clopper_pearson(324, 360)
P(f"  324/360 = 90.0%: CP95 [{pct(lo)}, {pct(hi)}], one-sided lower95 {pct(cp_lower_one_sided(324,360))}")
lo, hi = clopper_pearson(81, 90)
P(f"  4th command alone, 81/90 = 90.0%: CP95 [{pct(lo)}, {pct(hi)}]")

P("\nForgetting check: original 9 cells before vs after adding command 4 (paired, same 270 clips):")
P("  McNemar; a drop is 'material' if >= 6 more errors than fixes among discordant clips (p<0.05 one-way), i.e. ~2.2 points of accuracy.")

P("\nDev-set size for choosing the threshold (developer + 1 dev speaker): 2 x (10/command x 3 + 200 own-voice negatives + 400 public)")
P("  = 60 positives, 1,200 negatives: at a dev FA of 1% the expected count is 12 (CP95 [0.52%, 1.74%]) - adequate to place a threshold to within ~+-0.5 points.")

with open("/tmp/claude-0/-home-user-aichat/809e473e-6ead-51f0-b725-4e01dff2b821/scratchpad/voice-protocol-review/intervals_output.txt", "w") as f:
    f.write("\n".join(out) + "\n")
