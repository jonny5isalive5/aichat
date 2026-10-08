#!/usr/bin/env python3
"""run_pilot.py -- run the enrolled-speaker pilot on a sealed manifest and its clips, both arms (python3 -I; numpy + stdlib only).

    run_pilot.py dev  MANIFEST OUTDIR [options]     P1 (enrol commands 1-3 -> state A for both arms), score the dev phase,
                                                    write the dev DET curves (CSV) and FREEZE one threshold per arm
    run_pilot.py test MANIFEST OUTDIR [options]     the one-shot test: P2 (state A, twice: restart test), P3 (enrol the 4th
                                                    command -> state B), P4, the H5 controls, the report OUTDIR/RESULTS.md
    run_pilot.py all  MANIFEST OUTDIR [options]     dev then test (what the dry run does)

Arms.  DTW: `dtwapp enrol` one template per enrolment clip, `dtwapp score` per clip (fresh process each time); score =
runner-up minus best distance (--dtw-score margin, the benchmark's calibrated choice) or minus the best distance (min).
Network: `netapp feat` on every clip (the counted executable extracts the 144 features for every row), training set =
the enrolment rows + 30 waveform-augmented copies per enrolment clip (shift +-0.1 s, gain +-6 dB, white/brown noise at
10-30 dB SNR, made in numpy on the host) + a synthetic 'unknown' class built ONLY from the enrolment audio (time-reversed
clips, spliced halves of two different commands, noise-only clips, segment-shuffled rows), `netapp train` 16 hidden,
20 epochs, rate 0.01 (the benchmark's best recipe: reports/fewshot-accuracy.md), `netapp predict`; score = the largest
command probability, 0 when the unknown class wins (--net-score prob) or the logit margin (margin).
Decision = the predicted command when score > threshold, else REJECT.

Freeze rule.  The threshold of each arm is chosen ONLY on the dev phase: accept at most floor(TARGET_FA x n_dev_neg) of
the dev negatives (TARGET_FA 1% -> 1 of 100), i.e. threshold = the (floor(TARGET_FA n)+1)-th largest dev-negative score,
accept when strictly above.  `dev` writes OUTDIR/thresholds.json with the SHA-256 of the executables, the manifest seal,
state A and the dev decisions; `test` refuses to run without it, refuses if anything hashed has changed, and applies the
thresholds exactly once (a second `test` on the same OUTDIR is refused unless --force-rerun, and is then labelled POST-HOC
in the report).  The same thresholds are applied to state B and to every control.

Phases (protocol H).  P1 enrol 1-3; P2 fresh process from state A on all test positives of commands 1-3, all test
negatives and the test clips of command 4 (an extra 'unfamiliar speech' stratum), run twice and compared byte for byte;
P3 fresh process from state A enrols command 4 (DTW: append 5 templates; network: retrain from the retained enrolment
audio with capacity 4 commands + unknown -- the continual-learning variant, continuing training of model A, is a
deferred experiment); P4 from state B on all 120 positives and the 300 negatives; forgetting = errors after minus errors
before on the 90 original clips with the exact McNemar one-sided p.  H5 controls with the frozen thresholds: untrained
(DTW: empty state, every decision is REJECT; network: the same training rows for 0 epochs), constrained example-level
permutations of the 15 enrolment labels (every word's modal label unique and wrong; 5 seeds), unconstrained permutations
(--perms N, reported with the permutation p-value).  Every rate is k/n with the exact two-sided 95% Clopper-Pearson
interval; false accepts additionally get the one-sided 95% upper bound ('bound demonstrated') and the n that bound
would need to reach 1%.  Raw outputs: OUTDIR/decisions.csv (one row per clip x arm x stage), summary.json, the states.
"""
import sys, os, json, time, hashlib, argparse, subprocess, math, shutil, csv, io
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import record
REJECT = -1; NI = 144; NSEG = 12; NC = 12

# ---------------------------------------------------------------- exact binomial statistics (stdlib) ----------------------------------------------------------------
def binom_cdf(k, n, p):
    """P(X <= k), X ~ Bin(n, p), log-space terms."""
    if k < 0: return 0.0
    if k >= n: return 1.0
    if p <= 0: return 1.0
    if p >= 1: return 0.0
    lp, lq = math.log(p), math.log1p(-p); lg = math.lgamma(n + 1)
    return min(1.0, sum(math.exp(lg - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq) for i in range(k + 1)))

def bisect(f, lo, hi, it=60):
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0: hi = mid
        else: lo = mid
    return 0.5 * (lo + hi)

def cp_interval(k, n, alpha=0.05):
    """Exact two-sided Clopper-Pearson (1 - alpha) interval for k/n."""
    if n == 0: return (float('nan'), float('nan'))
    lo = 0.0 if k == 0 else bisect(lambda p: (1 - binom_cdf(k - 1, n, p)) - alpha / 2, 0.0, 1.0)
    hi = 1.0 if k == n else bisect(lambda p: alpha / 2 - binom_cdf(k, n, p), 0.0, 1.0)
    return lo, hi

def cp_upper(k, n, alpha=0.05):
    """One-sided (1 - alpha) upper bound: the quantity a claim 'rate <= x' needs."""
    if n == 0: return float('nan')
    return 1.0 if k >= n else bisect(lambda p: alpha - binom_cdf(k, n, p), 0.0, 1.0)

def n_for_upper(k, target=0.01, alpha=0.05, nmax=1000000):
    """Smallest n at which k accepts would give cp_upper(k, n) <= target (cp_upper decreases with n)."""
    if cp_upper(k, nmax, alpha) > target: return None
    lo, hi = max(k, 1), nmax
    while lo < hi:
        mid = (lo + hi) // 2
        if cp_upper(k, mid, alpha) <= target: hi = mid
        else: lo = mid + 1
    return lo

def n_for_upper_at_rate(k, n, target=0.01, alpha=0.05, nmax=1000000):
    """Smallest n at which the OBSERVED RATE k/n (count scaled with n, rounded up) gives cp_upper <= target; None if the rate itself is >= target."""
    if n == 0 or k / n >= target: return None
    m = max(1, k); ok = lambda m: cp_upper(math.ceil(k / n * m), m, alpha) <= target
    while m <= nmax and not ok(m): m = int(m * 1.05) + 1
    if m > nmax: return None
    while m > 1 and ok(m - 1): m -= 1
    return m

def mcnemar(b, c):
    """b = clips that became wrong, c = clips that became right.  One-sided exact p for 'more became wrong' and the two-sided p."""
    n = b + c
    if n == 0: return 1.0, 1.0
    one = 1 - binom_cdf(b - 1, n, 0.5); two = min(1.0, 2 * binom_cdf(min(b, c), n, 0.5))
    return one, two

def chance_bound(n, p, q=0.999):
    """Smallest count m with P(X >= m) <= 1 - q for X ~ Bin(n, p): the q-quantile ceiling used by the control gates (I5/I6)."""
    for m in range(n + 1):
        if 1 - binom_cdf(m - 1, n, p) <= 1 - q: return m
    return n + 1

def kn(k, n): return '%d/%d' % (k, n)
def pct(x): return 'n/a' if x != x else '%.1f%%' % (100 * x)
def ci(k, n): lo, hi = cp_interval(k, n); return '%s [%s, %s]' % (pct(k / n if n else float('nan')), pct(lo), pct(hi))

# ---------------------------------------------------------------- helpers ----------------------------------------------------------------
def sha(path): return record.sha256_file(path)
def shab(b): return hashlib.sha256(b).hexdigest()
def now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
def to_i16_bytes(y): return np.clip(np.round(np.asarray(y, np.float64) * 32768.0), -32768, 32767).astype('<i2').tobytes()

class Log:
    def __init__(self, path): self.f = open(path, 'a')
    def __call__(self, *a):
        s = ' '.join(str(x) for x in a); print(s, flush=True); self.f.write(s + '\n'); self.f.flush()

def run(cmd, stdin=b'', check=True, cwd=None):
    p = subprocess.run(cmd, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd)
    if check and p.returncode: raise SystemExit('command failed (%d): %s\n%s' % (p.returncode, ' '.join(cmd), p.stderr.decode(errors='replace')))
    return p

# ---------------------------------------------------------------- the benchmark's augmentation, ported (numpy, host side) ----------------------------------------------------------------
def augment_waves(W, rng, k, shift_s=0.1, gain_db=6.0, snr=(10, 30)):
    """W int16 (n, 16000) -> (n*k, 16000) float32 in [-1, 1]: random shift, gain, white/brown noise (fewshot.augment_waves)."""
    x = np.asarray(W, np.float32) / 32768.0; n = len(x); SR = record.SR; out = np.zeros((n * k, SR), np.float32)
    for i in range(n):
        for j in range(k):
            sh = int(rng.integers(-shift_s * SR, shift_s * SR + 1)); g = 10 ** (rng.uniform(-gain_db, gain_db) / 20)
            y = np.zeros(SR, np.float32)
            if sh >= 0: y[sh:] = x[i, :SR - sh]
            else: y[:SR + sh] = x[i, -sh:]
            y *= g
            rms = np.sqrt((y ** 2).mean()) + 1e-6
            nz = rng.standard_normal(SR).astype(np.float32)
            if rng.random() < 0.5: nz = np.cumsum(nz); nz -= nz.mean(); nz /= (np.sqrt((nz ** 2).mean()) + 1e-9)
            y += nz * rms / 10 ** (rng.uniform(*snr) / 20)
            out[i * k + j] = np.clip(y, -1, 1)
    return out

def synth_negative_waves(W, y, rng, n_out):
    """Synthetic 'unknown' audio from the enrolment clips only: reversed clips, spliced halves of two commands, noise (fewshot.synth_negative_waves)."""
    x = np.asarray(W, np.float32) / 32768.0; n = len(x); SR = record.SR; out = np.zeros((n_out, SR), np.float32); y = np.asarray(y)
    for m in range(n_out):
        kind = m % 3
        if kind == 0:
            i = rng.integers(n); out[m] = x[i][::-1]
        elif kind == 1:
            i = rng.integers(n); j = rng.choice(np.where(y != y[i])[0]); cut = int(rng.uniform(0.3, 0.7) * SR)
            out[m] = np.concatenate([x[i][:cut], x[j][cut:]])
        else:
            lvl = 10 ** (rng.uniform(-50, -15) / 20); nz = rng.standard_normal(SR).astype(np.float32)
            if rng.random() < 0.5: nz = np.cumsum(nz); nz -= nz.mean(); nz /= (np.sqrt((nz ** 2).mean()) + 1e-9)
            out[m] = np.clip(nz * lvl, -1, 1)
    return out

def synth_negative_vectors(X, rng, n_out):
    """Feature-level negatives: the 12 segments of an enrolment/augmented row shuffled (fewshot.synth_negative_vectors, nseg 12, nb 12)."""
    out = np.zeros((n_out, X.shape[1]), np.float32)
    for m in range(n_out):
        v = X[rng.integers(len(X))].reshape(NSEG, NC); out[m] = v[rng.permutation(NSEG)].reshape(-1)
    return out

# ---------------------------------------------------------------- the pilot ----------------------------------------------------------------
class Pilot:
    def __init__(self, a):
        self.a = a; self.out = os.path.abspath(a.outdir); os.makedirs(self.out, exist_ok=True)
        self.log = Log(os.path.join(self.out, 'log.txt')); self.log('# run_pilot.py %s %s  argv: %s' % (a.stage, now(), ' '.join(sys.argv[1:])))
        self.pilot = os.path.abspath(a.pilot_dir); self.dtwapp = os.path.join(self.pilot, 'dtwapp'); self.netapp = os.path.join(self.pilot, 'netapp')
        self.exe = {'dtwapp': sha(self.dtwapp), 'netapp': sha(self.netapp)}
        self.check_frozen_executables()
        self.man = record.load_manifest(a.manifest); self.mdir = os.path.dirname(os.path.abspath(a.manifest))
        self.seal = open(os.path.join(self.mdir, 'SEALED.sha256')).read().split()[0]
        self.rec = record.load_recordings(a.manifest); self.cmds = self.man['commands']; self.held = self.man['held_back_command']
        self.items = {it['id']: it for it in self.man['items']}
        self.verify_clips()
        self.fdir = os.path.join(self.out, 'features'); os.makedirs(self.fdir, exist_ok=True)
        self.decisions = []; self.summary = {}
        self.log('executables: dtwapp %s (%d bytes), netapp %s (%d bytes); manifest seal %s; speaker %s; commands %s (held back: %s)' % (
            self.exe['dtwapp'][:16], os.path.getsize(self.dtwapp), self.exe['netapp'][:16], os.path.getsize(self.netapp), self.seal[:16], self.man['speaker'], self.cmds, self.cmds[self.held]))

    def check_frozen_executables(self):
        sums = os.path.join(self.pilot, 'SHA256SUMS')
        if self.a.no_hash_check or not os.path.exists(sums): self.log('WARNING: executables not checked against SHA256SUMS'); return
        want = {l.split()[1]: l.split()[0] for l in open(sums) if l.strip()}
        for p in ('dtwapp', 'netapp'):
            if want.get(p) != self.exe[p]: raise SystemExit('%s hash %s differs from SHA256SUMS (%s): not the frozen build (run build.sh, or --no-hash-check to proceed and say so)' % (p, self.exe[p][:16], str(want.get(p))[:16]))

    def verify_clips(self):
        missing = [i for i in self.items if i not in self.rec or not os.path.exists(os.path.join(self.mdir, self.items[i]['file']))]
        if missing: raise SystemExit('%d items have no recorded clip (record.py status); first: %s' % (len(missing), missing[:5]))
        bad = []
        for i, it in self.items.items():
            f = os.path.join(self.mdir, it['file'])
            if os.path.getsize(f) != 2 * record.CLIP_N or sha(f) != self.rec[i]['sha256']: bad.append(i)
        if bad: raise SystemExit('%d clips differ from recordings.json (size or sha256): %s' % (len(bad), bad[:5]))
        self.log('clips: %d verified against recordings.json (32,000 bytes each, sha256 equal)' % len(self.items))

    # ---- selections ----
    def sel(self, phase, kind=None, labels=None):
        """ids of a phase in prompt order; kind 'command'/'negative'; labels = allowed command labels."""
        its = [it for it in self.man['items'] if it['phase'] == phase and (kind is None or it['kind'] == kind) and (labels is None or it['label'] in labels)]
        return [it['id'] for it in sorted(its, key=lambda it: it['order'])]
    def clip(self, i): return open(os.path.join(self.mdir, self.items[i]['file']), 'rb').read()
    def wave(self, i): return np.frombuffer(self.clip(i), '<i2')

    # ---- DTW arm ----
    def dtw_enrol(self, state, ids):
        for i in ids: run([self.dtwapp, 'enrol', state, str(self.items[i]['label'])], self.clip(i))
    def dtw_decide(self, state, ids, thr, k):
        out = []
        for i in ids:
            p = run([self.dtwapp, 'score', state], self.clip(i), check=False)
            if p.returncode: out.append(dict(id=i, raw='EXIT %d %s' % (p.returncode, p.stderr.decode().strip()), pred=REJECT, score=float('-inf'), margin=float('nan'), best=float('nan'))); continue
            t = p.stdout.decode().split(); lab, best, runner, margin = int(t[0]), float(t[1]), float(t[2]), float(t[3])
            out.append(dict(id=i, raw=p.stdout.decode().strip(), pred=lab, best=best, margin=margin, score=margin if self.a.dtw_score == 'margin' else -best))
        return self.apply(out, thr)

    # ---- network arm ----
    def feat(self, i, cache=None):
        """netapp feat of a recorded clip, cached as text (the row the executable printed); cache = a different directory re-extracts."""
        f = os.path.join(cache or self.fdir, i + '.txt')
        if not os.path.exists(f):
            p = run([self.netapp, 'feat'], self.clip(i)); open(f, 'w').write(p.stdout.decode())
        return open(f).read().strip()
    def feat_bytes(self, b): return run([self.netapp, 'feat'], b).stdout.decode().strip()

    def training_set(self, enrol_ids, k, tag, seed):
        """Rows of the network's training set for the enrolled clips: dict(rows, src (index into enrol_ids or -1 = synthetic), n_*).
        Cached in OUTDIR/trainsets/<tag>.json; labels are applied afterwards so the permutation controls reuse the same rows."""
        d = os.path.join(self.out, 'trainsets'); os.makedirs(d, exist_ok=True); f = os.path.join(d, tag + '.json')
        if os.path.exists(f):
            ts = json.load(open(f))
            if ts['enrol_ids'] == list(enrol_ids) and ts['netapp'] == self.exe['netapp'] and ts['aug'] == self.a.aug and ts['seed'] == seed: return ts
        t0 = time.time(); rng = np.random.default_rng([int(seed), 7, k]); y = np.array([self.items[i]['label'] for i in enrol_ids])
        W = np.stack([self.wave(i) for i in enrol_ids]); n = len(enrol_ids)
        rows = [self.feat(i) for i in enrol_ids]; src = list(range(n))
        Wa = augment_waves(W, rng, self.a.aug)
        for j in range(len(Wa)): rows.append(self.feat_bytes(to_i16_bytes(Wa[j]))); src.append(j // self.a.aug)
        nneg = (self.a.aug + 1) * n // 2
        Wn = synth_negative_waves(W, y, rng, nneg)
        for j in range(nneg): rows.append(self.feat_bytes(to_i16_bytes(Wn[j]))); src.append(-1)
        X = np.array([[float(v) for v in r.split()] for r in rows[:n + len(Wa)]], np.float32)
        for v in synth_negative_vectors(X, rng, nneg // 3): rows.append(' '.join('%.5g' % x for x in v)); src.append(-1)
        ts = dict(tag=tag, enrol_ids=list(enrol_ids), netapp=self.exe['netapp'], aug=self.a.aug, seed=seed, k=k, rows=rows, src=src,
                  n_enrol=n, n_aug=len(Wa), n_synth_wave=nneg, n_synth_vec=nneg // 3, seconds=round(time.time() - t0, 1))
        json.dump(ts, open(f, 'w')); self.log('training set %s: %d enrol + %d augmented + %d synthetic waveforms + %d segment-shuffled rows = %d rows (%.1f s)' % (
            tag, n, len(Wa), nneg, nneg // 3, len(rows), ts['seconds']))
        return ts

    def net_train(self, ts, labels, k, model, epochs, seed, tag):
        """labels: per enrolment clip (len n_enrol); augmented rows inherit their source's label; synthetic rows get k (unknown)."""
        rows = os.path.join(self.out, 'trainsets', tag + '_rows.txt')
        with open(rows, 'w') as f:
            for r, s in zip(ts['rows'], ts['src']): f.write('%s %d\n' % (r, labels[s] if s >= 0 else k))
        if os.path.exists(model): os.remove(model)
        p = run([self.netapp, 'train', rows, model, str(self.a.hidden), str(epochs), repr(self.a.lr), str(seed)])
        lines = p.stdout.decode().strip().split('\n'); open(model + '.log', 'w').write(p.stdout.decode())
        return rows, lines[0] + ('; ' + lines[-1] if len(lines) > 1 else '')

    def net_decide(self, model, ids, thr, k, cache=None):
        if cache: os.makedirs(cache, exist_ok=True)
        feats = [self.feat(i, cache) for i in ids]; rows = '\n'.join(feats) + '\n'
        p = run([self.netapp, 'predict', model], rows.encode()); lines = p.stdout.decode().strip().split('\n'); out = []
        for i, l, fr in zip(ids, lines, feats):
            t = l.split(); cls = int(t[0]); probs = [float(v) for v in t[1:-1]]; lm = float(t[-1]); pc = probs[:k]
            pred = int(np.argmax(pc)); unknown = cls >= k
            score = (0.0 if unknown else max(pc)) if self.a.net_score == 'prob' else (-lm if unknown else lm)
            out.append(dict(id=i, raw=l.strip(), feat_sha=shab(fr.encode())[:16], pred=pred, score=score, pmax=max(pc), margin=lm, cls=cls))
        return self.apply(out, thr)

    def apply(self, out, thr):
        for d in out:
            it = self.items[d['id']]; d['true'] = it['label']; d['word'] = it['word']; d['kind'] = it['kind']; d['stratum'] = it['stratum']; d['phase'] = it['phase']
            d['threshold'] = thr; d['accepted'] = (thr is not None) and d['pred'] != REJECT and d['score'] > thr
            d['decision'] = d['pred'] if d['accepted'] else REJECT; d['correct'] = d['kind'] == 'command' and d['decision'] == d['true']
        return out

    def record_decisions(self, stage, arm, out):
        for d in out: self.decisions.append(dict(stage=stage, arm=arm, **d))
        return out

    def write_decisions(self):
        cols = ['stage', 'arm', 'id', 'phase', 'kind', 'stratum', 'word', 'true', 'pred', 'score', 'threshold', 'accepted', 'decision', 'correct', 'raw', 'feat_sha']
        with open(os.path.join(self.out, 'decisions.csv'), 'w' if self.first_write else 'a', newline='') as f:
            w = csv.writer(f)
            if self.first_write: w.writerow(cols)
            for d in self.decisions: w.writerow([d.get(c, '') for c in cols])
        self.first_write = False; self.decisions = []

    # ---- threshold and DET ----
    @staticmethod
    def threshold_for_fa(neg_scores, fa):
        s = np.sort(np.asarray(neg_scores, float))[::-1]; kk = int(math.floor(fa * len(s)))
        return float(s[min(kk, len(s) - 1)])

    @staticmethod
    def det(pos, neg, path):
        """pos/neg decision dicts with 'score' (and 'pred'/'true' for pos).  Writes the DET: every unique score as a threshold."""
        ps = np.array([d['score'] for d in pos]); ok = np.array([d['pred'] == d['true'] for d in pos]); ns = np.array([d['score'] for d in neg])
        thrs = sorted(set(np.concatenate([ps, ns]).tolist()) | {float('-inf')}, reverse=True); rows = []
        for t in thrs:
            fa = int((ns > t).sum()); hit = int(((ps > t) & ok).sum())
            rows.append(dict(threshold=t, accepts=fa, n_neg=len(ns), false_accept_rate=fa / len(ns) if len(ns) else float('nan'), hits=hit, n_pos=len(ps), recall=hit / len(ps), frr=1 - hit / len(ps)))
        with open(path, 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        return rows

    @staticmethod
    def recall_at(rows, fa_levels):
        out = {}
        for fa in fa_levels:
            cand = [r for r in rows if r['false_accept_rate'] <= fa + 1e-12]
            out[fa] = max(cand, key=lambda r: r['recall']) if cand else None
        return out

    # ================================================================ stage: dev ================================================================
    def stage_dev(self):
        a = self.a; o = self.out; self.first_write = True
        if os.path.exists(os.path.join(o, 'TEST_RUNS.json')): raise SystemExit('the test stage already ran on %s: re-freezing after a test is not allowed; use a new output directory and new test recordings' % o)
        enrol3 = self.sel('enrol', 'command', labels=set(range(len(self.cmds))) - {self.held}); k = len(self.cmds) - 1
        self.log('\n== P1: enrol commands 1-%d from %d clips (%s) ==' % (k, len(enrol3), ', '.join(self.cmds[:self.held] + self.cmds[self.held + 1:])))
        stateA = os.path.join(o, 'stateA.dtw'); modelA = os.path.join(o, 'modelA.bin')
        if os.path.exists(stateA): os.remove(stateA)
        t0 = time.time(); self.dtw_enrol(stateA, enrol3); self.log('dtwapp: state A %d bytes, sha256 %s (%.2f s); info: %s' % (
            os.path.getsize(stateA), sha(stateA)[:16], time.time() - t0, run([self.dtwapp, 'info', stateA]).stdout.decode().split('\n')[0]))
        tsA = self.training_set(enrol3, k, 'A', a.seed); labels = [self.items[i]['label'] for i in enrol3]
        t0 = time.time(); rowsA, tl = self.net_train(tsA, labels, k, modelA, a.epochs, a.seed, 'A')
        self.log('netapp: model A %d bytes, sha256 %s (%.2f s): %s' % (os.path.getsize(modelA), sha(modelA)[:16], time.time() - t0, tl))
        enrol_rows = os.path.join(o, 'enrol_rows_A.txt'); open(enrol_rows, 'w').write(''.join('%s %d\n' % (self.feat(i), self.items[i]['label']) for i in enrol3))
        # ---- dev scoring with state A ----
        pos = self.sel('dev', 'command', labels=set(range(len(self.cmds))) - {self.held}); neg = self.sel('dev', 'negative'); c4 = self.sel('dev', 'command', labels={self.held})
        self.log('\n== dev phase: %d positives (commands 1-%d), %d own-voice negatives, %d clips of the held-back command (%s) ==' % (len(pos), k, len(neg), len(c4), self.cmds[self.held]))
        thresholds = dict(frozen=now(), target_fa=a.target_fa, manifest_seal=self.seal, speaker=self.man['speaker'], executables=self.exe, k=k, held_back=self.held,
                          stateA=dict(bytes=os.path.getsize(stateA), sha256=sha(stateA)), modelA=dict(bytes=os.path.getsize(modelA), sha256=sha(modelA)),
                          recipe=dict(hidden=a.hidden, epochs=a.epochs, lr=a.lr, aug=a.aug, seed=a.seed, dtw_score=a.dtw_score, net_score=a.net_score), arms={},
                          train_A=dict(rows=len(tsA['rows']), n_enrol=tsA['n_enrol'], n_aug=tsA['n_aug'], n_synth_wave=tsA['n_synth_wave'], n_synth_vec=tsA['n_synth_vec'], log=tl))
        for arm in ('dtw', 'net'):
            dec = (self.dtw_decide(stateA, pos + neg + c4, None, k) if arm == 'dtw' else self.net_decide(modelA, pos + neg + c4, None, k))
            P = [d for d in dec if d['id'] in set(pos)]; N = [d for d in dec if d['id'] in set(neg)]; C = [d for d in dec if d['id'] in set(c4)]
            kinds = ('margin', 'min') if arm == 'dtw' else ('prob', 'margin')
            for kind in kinds:                           # DET for both candidate scores; the configured one is frozen
                def sc(d):
                    if arm == 'dtw': return d['margin'] if kind == 'margin' else -d['best']
                    return (0.0 if d['cls'] >= k else d['pmax']) if kind == 'prob' else (-d['margin'] if d['cls'] >= k else d['margin'])
                Pk = [dict(d, score=sc(d)) for d in P]; Nk = [dict(d, score=sc(d)) for d in N]
                rows = self.det(Pk, Nk, os.path.join(o, 'dev_det_%s_%s.csv' % (arm, kind))); ra = self.recall_at(rows, [0.0, 0.01, 0.02, 0.05, 0.10])
                self.log('%s/%s DET on dev: recall at FA <=0%%: %s, <=1%%: %s, <=2%%: %s, <=5%%: %s, <=10%%: %s  (dev_det_%s_%s.csv)' % (
                    arm, kind, *['%s' % (kn(r['hits'], r['n_pos']) if r else 'n/a') for r in ra.values()], arm, kind))
            thr = self.threshold_for_fa([d['score'] for d in N], a.target_fa)
            for d in dec: d['threshold'] = thr; d['accepted'] = d['pred'] != REJECT and d['score'] > thr; d['decision'] = d['pred'] if d['accepted'] else REJECT; d['correct'] = d['kind'] == 'command' and d['decision'] == d['true']
            fa = sum(d['accepted'] for d in N); hit = sum(d['correct'] for d in P); c4a = sum(d['accepted'] for d in C)
            per = {self.cmds[c]: kn(sum(d['correct'] for d in P if d['true'] == c), sum(d['true'] == c for d in P)) for c in range(len(self.cmds)) if c != self.held}
            self.log('%s: FROZEN threshold %.6f on score %s -> dev false accepts %s, dev recall %s (%s), held-back command accepted %s' % (
                arm, thr, a.dtw_score if arm == 'dtw' else a.net_score, kn(fa, len(N)), kn(hit, len(P)), ', '.join('%s %s' % kv for kv in per.items()), kn(c4a, len(C))))
            thresholds['arms'][arm] = dict(score=a.dtw_score if arm == 'dtw' else a.net_score, threshold=thr, dev_false_accepts=[fa, len(N)], dev_recall=[hit, len(P)], dev_per_command=per,
                                           dev_closed_set=[sum(d['pred'] == d['true'] for d in P), len(P)], dev_held_back_accepted=[c4a, len(C)])
            self.record_decisions('dev', arm, dec)
        self.write_decisions(); thresholds['dev_decisions_sha256'] = sha(os.path.join(o, 'decisions.csv'))
        json.dump(thresholds, open(os.path.join(o, 'thresholds.json'), 'w'), indent=1)
        self.log('thresholds frozen in %s (sha256 %s)' % (os.path.join(o, 'thresholds.json'), sha(os.path.join(o, 'thresholds.json'))[:16]))

    # ================================================================ stage: test ================================================================
    def stage_test(self):
        a = self.a; o = self.out; self.first_write = not os.path.exists(os.path.join(o, 'decisions.csv'))
        tj = os.path.join(o, 'thresholds.json')
        if not os.path.exists(tj): raise SystemExit('no thresholds.json in %s: run the dev stage first (freeze rule)' % o)
        T = json.load(open(tj)); stateA = os.path.join(o, 'stateA.dtw'); modelA = os.path.join(o, 'modelA.bin')
        for name, want in (('manifest seal', (T['manifest_seal'], self.seal)), ('dtwapp', (T['executables']['dtwapp'], self.exe['dtwapp'])), ('netapp', (T['executables']['netapp'], self.exe['netapp'])),
                           ('state A', (T['stateA']['sha256'], sha(stateA))), ('model A', (T['modelA']['sha256'], sha(modelA)))):
            if want[0] != want[1]: raise SystemExit('%s changed since the freeze (%s != %s): the test is void' % (name, want[0][:16], want[1][:16]))
        for key, val in (('dtw_score', a.dtw_score), ('net_score', a.net_score), ('hidden', a.hidden), ('epochs', a.epochs), ('lr', a.lr), ('aug', a.aug), ('seed', a.seed)):
            if T['recipe'][key] != val: raise SystemExit('%s=%r differs from the frozen recipe %r' % (key, val, T['recipe'][key]))
        runs = os.path.join(o, 'TEST_RUNS.json'); prev = json.load(open(runs)) if os.path.exists(runs) else []
        if prev and not a.force_rerun: raise SystemExit('the test stage already ran on %s at %s: the one-shot rule forbids a second run (--force-rerun labels it POST-HOC)' % (o, prev[-1]['started']))
        self.posthoc = len(prev); prev.append(dict(started=now(), argv=sys.argv[1:])); json.dump(prev, open(runs, 'w'), indent=1)
        thr = {arm: T['arms'][arm]['threshold'] for arm in ('dtw', 'net')}; k = T['k']; S = self.summary; S['thresholds'] = T; S['posthoc'] = self.posthoc
        self.log('\n== TEST (one shot%s): thresholds dtw %.6f (%s), net %.6f (%s) frozen %s ==' % (', POST-HOC RERUN %d' % self.posthoc if self.posthoc else '', thr['dtw'], T['arms']['dtw']['score'], thr['net'], T['arms']['net']['score'], T['frozen']))
        pos3 = self.sel('test', 'command', labels=set(range(len(self.cmds))) - {self.held}); neg = self.sel('test', 'negative'); c4 = self.sel('test', 'command', labels={self.held})
        all_ids = pos3 + neg + c4
        # ---- P2: state A, twice, fresh processes, byte-identical ----
        self.log('\n== P2: state A on %d positives (commands 1-%d), %d negatives, %d clips of the held-back %r; run twice ==' % (len(pos3), k, len(neg), len(c4), self.cmds[self.held]))
        shaA0 = (sha(stateA), sha(modelA)); P2 = {}
        for arm in ('dtw', 'net'):
            outs = []
            for rep in (1, 2):
                t0 = time.time(); dec = self.dtw_decide(stateA, all_ids, thr['dtw'], k) if arm == 'dtw' else self.net_decide(modelA, all_ids, thr['net'], k, cache=os.path.join(o, 'features_rerun') if rep == 2 else None)
                outs.append('\n'.join(d['raw'] + ' ' + d.get('feat_sha', '') for d in dec)); self.record_decisions('P2' if rep == 1 else 'P2_rerun', arm, dec)
                self.log('%s P2 run %d: %d decisions in %.1f s (%s), raw output sha256 %s' % (arm, rep, len(dec), time.time() - t0, 'one fresh process per clip' if arm == 'dtw' else 'feat in one fresh process per clip%s, predict in one' % (', re-extracted' if rep == 2 else ''), shab(outs[-1].encode())[:16]))
            P2[arm] = dec; S['restart_%s' % arm] = dict(identical=outs[0] == outs[1], sha256=shab(outs[0].encode()), state_unchanged=(sha(stateA), sha(modelA)) == shaA0)
            self.log('%s restart test: outputs %s, state %s' % (arm, 'byte-identical' if outs[0] == outs[1] else 'DIFFER', 'unchanged' if S['restart_%s' % arm]['state_unchanged'] else 'MODIFIED'))
        self.write_decisions()
        # ---- P3: enrol the 4th command -> state B ----
        enrol4 = self.sel('enrol', 'command', labels={self.held}); enrol_all = self.sel('enrol', 'command'); k4 = len(self.cmds)
        stateB = os.path.join(o, 'stateB.dtw'); modelB = os.path.join(o, 'modelB.bin'); shutil.copyfile(stateA, stateB)
        self.log('\n== P3: enrol the 4th command %r from %d clips (fresh process from state A) ==' % (self.cmds[self.held], len(enrol4)))
        self.dtw_enrol(stateB, enrol4); self.log('dtwapp: state B %d bytes, sha256 %s; %s' % (os.path.getsize(stateB), sha(stateB)[:16], run([self.dtwapp, 'info', stateB]).stdout.decode().split('\n')[0]))
        tsB = self.training_set(enrol_all, k4, 'B', a.seed); labels4 = [self.items[i]['label'] for i in enrol_all]
        rowsB, tl = self.net_train(tsB, labels4, k4, modelB, a.epochs, a.seed, 'B'); S['train_B'] = dict(rows=len(tsB['rows']), n_enrol=tsB['n_enrol'], n_aug=tsB['n_aug'], n_synth_wave=tsB['n_synth_wave'], n_synth_vec=tsB['n_synth_vec'], log=tl); self.log('netapp: model B %d bytes, sha256 %s (retrained from the retained enrolment audio, capacity %d commands + unknown): %s' % (os.path.getsize(modelB), sha(modelB)[:16], k4, tl))
        enrol_rows = os.path.join(o, 'enrol_rows_B.txt'); open(enrol_rows, 'w').write(''.join('%s %d\n' % (self.feat(i), self.items[i]['label']) for i in enrol_all))
        # ---- P4: state B on all positives and the negatives ----
        pos4 = self.sel('test', 'command'); self.log('\n== P4: state B on %d positives (4 commands) and %d negatives ==' % (len(pos4), len(neg)))
        P4 = {}
        for arm in ('dtw', 'net'):
            t0 = time.time(); dec = self.dtw_decide(stateB, pos4 + neg, thr['dtw'], k4) if arm == 'dtw' else self.net_decide(modelB, pos4 + neg, thr['net'], k4)
            P4[arm] = dec; self.record_decisions('P4', arm, dec); self.log('%s P4: %d decisions in %.1f s' % (arm, len(dec), time.time() - t0))
        self.write_decisions()
        # ---- controls (H5), frozen thresholds ----
        self.log('\n== controls (H5) ==')
        enrol3 = self.sel('enrol', 'command', labels=set(range(len(self.cmds))) - {self.held}); tsA = self.training_set(enrol3, k, 'A', a.seed); labels3 = [self.items[i]['label'] for i in enrol3]
        ctrl = S['controls'] = {}
        empty = os.path.join(o, 'ctrl_untrained.dtw')
        if os.path.exists(empty): os.remove(empty)
        open(empty, 'wb').write(bytes([0xD7, 0xA1, 61, 0, 16, 0, 0, 0]))   # header only: 0 templates = no state
        modelU = os.path.join(o, 'ctrl_untrained.bin'); rowsU, tl = self.net_train(tsA, labels3, k, modelU, 0, a.seed, 'untrained')
        self.log('untrained network: 0 epochs on the P1 rows (%s), %d bytes' % (tl, os.path.getsize(modelU)))
        for arm in ('dtw', 'net'):
            dec = self.dtw_decide(empty, pos3 + neg, thr['dtw'], k) if arm == 'dtw' else self.net_decide(modelU, pos3 + neg, thr['net'], k)
            self.record_decisions('untrained', arm, dec); P = [d for d in dec if d['kind'] == 'command']; N = [d for d in dec if d['kind'] == 'negative']
            ctrl['untrained_' + arm] = dict(acc=[sum(d['correct'] for d in P), len(P)], closed=[sum(d['pred'] == d['true'] for d in P), len(P)], fa=[sum(d['accepted'] for d in N), len(N)],
                                            note='every decision REJECT (dtwapp refuses to score with no templates)' if arm == 'dtw' else '0-epoch model: data normalisation plus He-uniform random weights')
            self.log('untrained %s: accuracy %s, closed-set (label of the best, ignoring the threshold) %s, false accepts %s' % (arm, kn(*ctrl['untrained_' + arm]['acc']), kn(*ctrl['untrained_' + arm]['closed']), kn(*ctrl['untrained_' + arm]['fa'])))
        self.write_decisions()
        y3 = np.array(labels3); words = sorted(set(y3))
        def constrained_ok(perm):
            for w in words:
                cnt = np.bincount(perm[y3 == w], minlength=k); top = np.argsort(cnt)[::-1]
                if cnt[top[0]] == cnt[top[1]] or top[0] == w: return False
            return True
        def perm_control(name, nseeds, constrained):
            res = []
            for s in range(nseeds):
                rng = np.random.default_rng([a.seed, 0xC0, 1 if constrained else 0, s]); tries = 0
                while True:
                    perm = rng.permutation(y3); tries += 1
                    if not constrained or constrained_ok(perm): break
                st = os.path.join(o, 'ctrl_%s_%d.dtw' % (name, s))
                if os.path.exists(st): os.remove(st)
                for i, lab in zip(enrol3, perm): run([self.dtwapp, 'enrol', st, str(int(lab))], self.clip(i))
                md = os.path.join(o, 'ctrl_%s_%d.bin' % (name, s)); self.net_train(tsA, [int(v) for v in perm], k, md, a.epochs, a.seed, '%s_%d' % (name, s))
                r = dict(seed=s, perm=[int(v) for v in perm], tries=tries)
                for arm in ('dtw', 'net'):
                    dec = self.dtw_decide(st, pos3 + neg, thr['dtw'], k) if arm == 'dtw' else self.net_decide(md, pos3 + neg, thr['net'], k)
                    self.record_decisions('%s_%d' % (name, s), arm, dec); P = [d for d in dec if d['kind'] == 'command']; N = [d for d in dec if d['kind'] == 'negative']
                    r[arm] = dict(acc=[sum(d['correct'] for d in P), len(P)], closed=[sum(d['pred'] == d['true'] for d in P), len(P)], fa=[sum(d['accepted'] for d in N), len(N)], acc_pos=[sum(d['accepted'] for d in P), len(P)])
                self.log('%s permutation %d (%s, %d draws): dtw accuracy %s closed %s FA %s; net accuracy %s closed %s FA %s' % (
                    name, s, ''.join(str(v) for v in perm), tries, kn(*r['dtw']['acc']), kn(*r['dtw']['closed']), kn(*r['dtw']['fa']), kn(*r['net']['acc']), kn(*r['net']['closed']), kn(*r['net']['fa'])))
                res.append(r); self.write_decisions()
            return res
        ctrl['constrained'] = perm_control('constrained', a.constrained, True)
        ctrl['unconstrained'] = perm_control('unconstrained', a.perms, False) if a.perms else []
        # ---- strace (B4), optional, one decision per arm in an empty directory ----
        if shutil.which('strace') and not a.no_strace:
            cwd = os.path.join(o, 'strace_cwd'); shutil.rmtree(cwd, ignore_errors=True); os.makedirs(cwd); S['strace'] = {}
            for arm, cmd in (('dtw', [self.dtwapp, 'score', stateB]), ('net', [self.netapp, 'predict', modelB])):
                logp = os.path.join(o, 'strace_%s.log' % arm); stdin = self.clip(pos3[0]) if arm == 'dtw' else (self.feat(pos3[0]) + '\n').encode()
                run(['strace', '-f', '-e', 'trace=openat,open,read,execve', '-o', logp] + cmd, stdin, cwd=cwd)
                opened = sorted({l.split('"')[1] for l in open(logp) if l.split('(', 1)[0].split()[-1] in ('openat', 'open', 'execve') and '"' in l and 'ENOENT' not in l})
                S['strace'][arm] = opened; self.log('strace %s: files opened: %s' % (arm, ', '.join(os.path.basename(p) if p.startswith(o) or p.startswith(self.pilot) else p for p in opened)))
        else: S['strace'] = None; self.log('strace: not run (%s)' % ('--no-strace' if a.no_strace else 'strace not installed'))
        # ---- sizes ----
        sz = S['sizes'] = dict(dtwapp=os.path.getsize(self.dtwapp), netapp=os.path.getsize(self.netapp), stateA=os.path.getsize(stateA), stateB=os.path.getsize(stateB),
                               modelA=os.path.getsize(modelA), modelB=os.path.getsize(modelB), enrol_rows_B_text=os.path.getsize(enrol_rows), enrol_rows_B_float32=len(enrol_all) * NI * 4,
                               enrol_audio_B=len(enrol_all) * 2 * record.CLIP_N, sha=dict(stateA=sha(stateA), stateB=sha(stateB), modelA=sha(modelA), modelB=sha(modelB)))
        S['P2'] = self.tally(P2, pos3, neg, c4, k); S['P4'] = self.tally(P4, pos4, neg, [], k4)
        S['forgetting'] = {arm: self.forgetting(P2[arm], P4[arm], pos3) for arm in ('dtw', 'net')}
        S['paired'] = {st: self.paired(D['dtw'], D['net'], ids) for st, D, ids in (('P2', P2, pos3), ('P4', P4, pos4))}
        S['chance_bound'] = dict(P2=chance_bound(len(pos3), 1.0 / k), n=len(pos3), k=k)
        json.dump(S, open(os.path.join(o, 'summary.json'), 'w'), indent=1, default=str)
        self.report(T, S); self.log('report: %s' % os.path.join(o, 'RESULTS.md'))

    # ---- tallies ----
    def tally(self, D, pos, neg, c4, k):
        t = {}
        for arm, dec in D.items():
            by = {d['id']: d for d in dec}; r = t[arm] = dict(per_command={}, strata={}, c4=None)
            for c in sorted({self.items[i]['label'] for i in pos}):
                P = [by[i] for i in pos if self.items[i]['label'] == c]
                r['per_command'][self.cmds[c]] = self.counts(P)
            P = [by[i] for i in pos]; r['pooled'] = self.counts(P)
            for s in sorted({self.items[i]['stratum'] for i in neg}):
                N = [by[i] for i in neg if self.items[i]['stratum'] == s]; r['strata'][s] = dict(accepts=sum(d['accepted'] for d in N), n=len(N))
            N = [by[i] for i in neg]; r['strata']['all own-voice negatives'] = dict(accepts=sum(d['accepted'] for d in N), n=len(N))
            if c4: C = [by[i] for i in c4]; r['c4'] = dict(accepts=sum(d['accepted'] for d in C), n=len(C))
        return t

    @staticmethod
    def counts(P):
        return dict(correct=sum(d['correct'] for d in P), closed=sum(d['pred'] == d['true'] for d in P), substituted=sum(d['accepted'] and not d['correct'] for d in P), rejected=sum(not d['accepted'] for d in P), n=len(P))

    def forgetting(self, before, after, ids):
        b0 = {d['id']: d['correct'] for d in before}; b1 = {d['id']: d['correct'] for d in after}
        e0 = sum(not b0[i] for i in ids); e1 = sum(not b1[i] for i in ids); worse = sum(b0[i] and not b1[i] for i in ids); better = sum((not b0[i]) and b1[i] for i in ids)
        p1, p2 = mcnemar(worse, better)
        return dict(n=len(ids), errors_before=e0, errors_after=e1, became_wrong=worse, became_right=better, net=e1 - e0, p_one_sided=p1, p_two_sided=p2)

    def paired(self, dtw, net, ids):
        d0 = {d['id']: d['correct'] for d in dtw}; d1 = {d['id']: d['correct'] for d in net}
        b = sum(d0[i] and not d1[i] for i in ids); c = sum((not d0[i]) and d1[i] for i in ids); p1, p2 = mcnemar(b, c)
        return dict(n=len(ids), dtw_correct=sum(d0[i] for i in ids), net_correct=sum(d1[i] for i in ids), dtw_only=b, net_only=c, p_two_sided=p2)

    # ---- report ----
    def report(self, T, S):
        a = self.a; o = self.out; L = []; w = L.append; k = T['k']; sz = S['sizes']; ARMS = (('dtw', 'DTW (`dtwapp`)'), ('net', 'network (`netapp`)'))
        w('# Pilot results: speaker %s, %s' % (self.man['speaker'], now()))
        if self.posthoc: w('\n**POST-HOC RERUN %d of the test stage on this output directory: the one-shot rule was broken; these numbers do not count as the pilot result.**' % self.posthoc)
        w('\nManifest seal %s; dtwapp %s; netapp %s; thresholds frozen %s (dev decisions sha256 %s).  Recipe: DTW score %s; network %d hidden, %d epochs, rate %g, %d augmented copies, seed %d, score %s; target dev false-accept rate %.1f%%.'
          % (self.seal[:16], self.exe['dtwapp'][:16], self.exe['netapp'][:16], T['frozen'], T['dev_decisions_sha256'][:16], T['recipe']['dtw_score'], T['recipe']['hidden'], T['recipe']['epochs'], T['recipe']['lr'], T['recipe']['aug'], T['recipe']['seed'], T['recipe']['net_score'], 100 * T['target_fa']))
        w('Commands: %s; held back until P3: %s.  Every rate is k/n with the exact two-sided 95%% Clopper-Pearson interval.' % (', '.join('%d=%s' % (i, c) for i, c in enumerate(self.cmds)), self.cmds[self.held]))
        w('\n## 1. Bytes: complete application plus required state (`wc -c`)\n')
        w('| arm | executable | state A (3 commands) | state B (4 commands, declared capacity) | application + state B | spare under 32,768 |'); w('|---|---:|---:|---:|---:|---:|')
        w('| DTW | %d | %d (sha256 %s) | %d (%s) | **%d** | %d |' % (sz['dtwapp'], sz['stateA'], sz['sha']['stateA'][:12], sz['stateB'], sz['sha']['stateB'][:12], sz['dtwapp'] + sz['stateB'], 32768 - sz['dtwapp'] - sz['stateB']))
        w('| network | %d | %d (%s) | %d (%s) | **%d** | %d |' % (sz['netapp'], sz['modelA'], sz['sha']['modelA'][:12], sz['modelB'], sz['sha']['modelB'][:12], sz['netapp'] + sz['modelB'], 32768 - sz['netapp'] - sz['modelB']))
        w('\nThe network was retrained for the 4th command from retained enrolment data (disclosed): the 20 enrolment rows are %d bytes as `netapp feat` text (%d as float32), the 20 raw clips %d bytes; neither is inside the model file.  Peak RSS: `measure.sh --pilot OUTDIR` (see SIZES.md section 4 for why RSS is glibc-dominated).'
          % (sz['enrol_rows_B_text'], sz['enrol_rows_B_float32'], sz['enrol_audio_B']))
        for tag, tr in (('A', T['train_A']), ('B', S['train_B'])):
            w('\nNetwork training set %s: %d rows = %d enrolment + %d augmented + %d synthetic-unknown waveforms + %d segment-shuffled rows; %s.' % (tag, tr['rows'], tr['n_enrol'], tr['n_aug'], tr['n_synth_wave'], tr['n_synth_vec'], tr['log']))
        w('\n## 2. Development phase (thresholds chosen here, then frozen)\n')
        w('| arm | score | frozen threshold | dev false accepts | dev recall (commands 1-%d) | per command | dev closed-set (ignoring the threshold) | held-back command accepted |' % k); w('|---|---|---:|---|---|---|---|---|')
        for arm, name in ARMS:
            t = T['arms'][arm]; w('| %s | %s | %.6f | %s | %s | %s | %s | %s |' % (name, t['score'], t['threshold'], ci(*t['dev_false_accepts']), ci(*t['dev_recall']), ', '.join('%s %s' % kv for kv in t['dev_per_command'].items()), kn(*t['dev_closed_set']), kn(*t['dev_held_back_accepted'])))
        w('\nDev DET curves (every unique score as a threshold; false-accept rate on the dev negatives, recall on the dev positives): `dev_det_dtw_margin.csv`, `dev_det_dtw_min.csv`, `dev_det_net_prob.csv`, `dev_det_net_margin.csv`.  Recall at dev false-accept rates <= 0 / 1 / 2 / 5 / 10%:\n')
        for arm, kinds in (('dtw', ('margin', 'min')), ('net', ('prob', 'margin'))):
            for kind in kinds:
                rows = list(csv.DictReader(open(os.path.join(o, 'dev_det_%s_%s.csv' % (arm, kind)))))
                for r in rows: r['false_accept_rate'] = float(r['false_accept_rate']); r['recall'] = float(r['recall']); r['hits'] = int(r['hits']); r['n_pos'] = int(r['n_pos'])
                ra = self.recall_at(rows, [0.0, 0.01, 0.02, 0.05, 0.10])
                w('- %s / %s%s: %s' % (arm, kind, ' (frozen)' if kind == T['arms'][arm]['score'] else '', ' / '.join(kn(r['hits'], r['n_pos']) if r else 'n/a' for r in ra.values())))
        for stage, title, kk in (('P2', '3. Test with state A (commands 1-%d), P2: the pre-registered one-shot result' % k, k), ('P4', '4. Test with state B (all 4 commands), P4', len(self.cmds))):
            w('\n## %s\n' % title); t = S[stage]
            w('### Recall per command (decision = the enrolled command; a substitution or a REJECT is an error)\n')
            w('| command | DTW correct k/n [95% CI] | DTW closed-set | DTW substituted / rejected | network correct k/n [95% CI] | network closed-set | network substituted / rejected |'); w('|---|---|---|---|---|---|---|')
            for c in list(t['dtw']['per_command']) + ['pooled']:
                cells = []
                for arm in ('dtw', 'net'):
                    r = t[arm]['pooled'] if c == 'pooled' else t[arm]['per_command'][c]; cells += ['%s %s' % (kn(r['correct'], r['n']), ci(r['correct'], r['n'])), kn(r['closed'], r['n']), '%d / %d' % (r['substituted'], r['rejected'])]
                w('| %s | %s |' % ('**pooled**' if c == 'pooled' else c, ' | '.join(cells)))
            w('\n### False accepts on the own-voice negatives (measured rate and demonstrated bound are different quantities)\n')
            w('| arm | stratum | accepts k/n | measured false-accept rate: point estimate [95% CI] | bound demonstrated: one-sided 95% upper limit | n needed for the bound to reach 1%: at this count / at this rate |')
            w('|---|---|---|---|---|---|')
            for arm, name in ARMS:
                for s, r in t[arm]['strata'].items():
                    kk_, n = r['accepts'], r['n']; n1 = n_for_upper(kk_); n2 = n_for_upper_at_rate(kk_, n)
                    w('| %s | %s | %s | %s | %s | %s / %s |' % (name, s, kn(kk_, n), ci(kk_, n), pct(cp_upper(kk_, n)), ('%d' % n1) if n1 else 'never', ('%d' % n2) if n2 else 'never (rate >= 1%)'))
            if stage == 'P2':
                w('\nThe held-back command %r as unfamiliar speech at P2 (extra stratum, not pooled above): DTW accepted %s, network accepted %s.' % (self.cmds[self.held], kn(t['dtw']['c4']['accepts'], t['dtw']['c4']['n']), kn(t['net']['c4']['accepts'], t['net']['c4']['n'])))
                w('\n### Restart test (P2 run twice: fresh processes loading only the saved state)\n')
                for arm, name in ARMS:
                    r = S['restart_' + arm]; w('- %s: raw outputs of the two runs (%s) %s (sha256 %s); state file %s by scoring.' % (name, 'score line per clip' if arm == 'dtw' else 'predict line plus the sha256 of the feat row per clip, features re-extracted in run 2', '**byte-identical**' if r['identical'] else '**DIFFER**', r['sha256'][:16], 'unchanged' if r['state_unchanged'] else '**MODIFIED**'))
            else:
                w('\n### Forgetting on the %d original test clips of commands 1-%d (P2 -> P4)\n' % (S['forgetting']['dtw']['n'], k))
                w('| arm | errors before | errors after | became wrong | became right | net change | exact McNemar one-sided p (more became wrong) |'); w('|---|---:|---:|---:|---:|---:|---:|')
                for arm, name in ARMS:
                    f = S['forgetting'][arm]; w('| %s | %d | %d | %d | %d | %+d | %.3f |' % (name, f['errors_before'], f['errors_after'], f['became_wrong'], f['became_right'], f['net'], f['p_one_sided']))
        w('\n## 5. Controls (same clips, same frozen thresholds)\n'); C = S['controls']; cb = S['chance_bound']
        w('Chance for %d positives at 1/%d is %.1f%%; the 99.9th percentile of chance is %d/%d (a learner that ignores labels should stay at or below it).\n' % (cb['n'], cb['k'], 100 / cb['k'], cb['P2'], cb['n']))
        w('| control | DTW accuracy | DTW closed-set | DTW false accepts | network accuracy | network closed-set | network false accepts |'); w('|---|---|---|---|---|---|---|')
        w('| untrained (no state / 0 epochs) | %s | %s | %s | %s | %s | %s |' % tuple(kn(*C['untrained_' + arm][f]) for arm in ('dtw', 'net') for f in ('acc', 'closed', 'fa')))
        for r in C['constrained']: w('| constrained permutation seed %d (labels %s) | %s | %s | %s | %s | %s | %s |' % ((r['seed'], ''.join(str(v) for v in r['perm'])) + tuple(kn(*r[arm][f]) for arm in ('dtw', 'net') for f in ('acc', 'closed', 'fa'))))
        for r in C['constrained']:
            for arm in ('dtw', 'net'):
                if r[arm]['acc'][0] > cb['P2']: w('\n**Constrained permutation seed %d, %s: accuracy %s exceeds the chance bound %d/%d (I6 analogue): check for a label leak.**' % (r['seed'], arm, kn(*r[arm]['acc']), cb['P2'], cb['n']))
        if C['unconstrained']:
            obs = {arm: S['P2'][arm]['pooled']['correct'] for arm in ('dtw', 'net')}; n = C['unconstrained'][0]['dtw']['acc'][1]
            w('\n%d unconstrained example-level permutations of the 15 enrolment labels (reported, not gated; permutation p = (1 + #{permuted accuracy >= observed}) / %d):\n' % (len(C['unconstrained']), len(C['unconstrained']) + 1))
            w('| arm | accuracy under permutation, min / median / max of %d | closed-set, min / median / max | false accepts, min / median / max of %d | observed P2 accuracy | permutation p |' % (n, C['unconstrained'][0]['dtw']['fa'][1])); w('|---|---|---|---|---|---:|')
            for arm, name in ARMS:
                accs = [r[arm]['acc'][0] for r in C['unconstrained']]; cl = [r[arm]['closed'][0] for r in C['unconstrained']]; fa = [r[arm]['fa'][0] for r in C['unconstrained']]
                p = (1 + sum(x >= obs[arm] for x in accs)) / (len(accs) + 1)
                w('| %s | %d / %.0f / %d | %d / %.0f / %d | %d / %.0f / %d | %d | %.3f |' % (name, min(accs), float(np.median(accs)), max(accs), min(cl), float(np.median(cl)), max(cl), min(fa), float(np.median(fa)), max(fa), obs[arm], p))
        w('\n"Closed-set" = the label of the best class ignoring the threshold; "accuracy" applies the frozen threshold.  The untrained DTW rejects everything by construction (no templates), which is why the recall and false-accept gates are both needed.')
        w('\n## 6. DTW versus network, paired on identical clips (exact McNemar)\n')
        for st in ('P2', 'P4'):
            p = S['paired'][st]; w('- %s: DTW %s correct, network %s correct; DTW-only correct %d, network-only correct %d, two-sided p = %.3f.' % (st, kn(p['dtw_correct'], p['n']), kn(p['net_correct'], p['n']), p['dtw_only'], p['net_only'], p['p_two_sided']))
        w('\n## 7. Disclosures\n')
        w('- Host-side segmentation: the recorder centres each 1.0 s clip on the energy centre of the 1.5 s capture (record.py, logged per clip in recordings.json).  Isolated utterances only; segmentation of a longer stream is a deferred experiment.')
        w('- The network arm\'s augmentation and synthetic unknown class are computed in numpy on the host from the enrolment audio only, then fed through `netapp feat`; the model is retrained from scratch for the 4th command (continual learning deferred).')
        w('- The DTW arm never sees a label other than at `enrol`; the network sees labels only in its training rows.  Thresholds were frozen before the test clips were scored (thresholds.json).')
        if S.get('strace') is not None:
            for arm in ('dtw', 'net'): w('- strace (one %s decision in an empty directory) opened: %s.' % (arm, ', '.join(S['strace'][arm])))
        w('- Raw decision table: `decisions.csv` (stage x arm x clip); states and models: `stateA.dtw`, `stateB.dtw`, `modelA.bin`, `modelB.bin`; machine-readable numbers: `summary.json`; the run log: `log.txt`.')
        open(os.path.join(o, 'RESULTS.md'), 'w').write('\n'.join(L) + '\n')

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['dev', 'test', 'all']); ap.add_argument('manifest'); ap.add_argument('outdir')
    ap.add_argument('--pilot-dir', default=HERE); ap.add_argument('--seed', type=int, default=1, help='uai32 training seed and the numpy augmentation seed')
    ap.add_argument('--target-fa', type=float, default=0.01); ap.add_argument('--dtw-score', choices=['margin', 'min'], default='margin'); ap.add_argument('--net-score', choices=['prob', 'margin'], default='prob')
    ap.add_argument('--hidden', type=int, default=16); ap.add_argument('--epochs', type=int, default=20); ap.add_argument('--lr', type=float, default=0.01); ap.add_argument('--aug', type=int, default=30)
    ap.add_argument('--constrained', type=int, default=5, help='constrained permutation seeds'); ap.add_argument('--perms', type=int, default=20, help='unconstrained permutation seeds (0 = skip)')
    ap.add_argument('--force-rerun', action='store_true'); ap.add_argument('--no-hash-check', action='store_true'); ap.add_argument('--no-strace', action='store_true')
    a = ap.parse_args(); stage = a.stage
    if stage in ('dev', 'all'): a.stage = 'dev'; Pilot(a).stage_dev()
    if stage in ('test', 'all'): a.stage = 'test'; Pilot(a).stage_test()

if __name__ == '__main__': main()
