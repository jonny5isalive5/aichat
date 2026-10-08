"""Few-shot spoken-command experiment library: splits, prototype / DTW / uai32 methods, augmentation."""
import numpy as np, json, os, subprocess, shutil
import features as F

ROOT = os.path.dirname(os.path.abspath(__file__))
UAI32 = os.path.join(ROOT, '..', 'bin', 'uai32')
ALL_WORDS = ['down', 'go', 'left', 'no', 'right', 'stop', 'up', 'yes']

class Data:
    def __init__(self, cache):
        meta = json.load(open(os.path.join(cache, 'meta.json')))
        self.words = np.array(meta['words']); self.spk = np.array(meta['speakers']); self.files = meta['files']
        self.LM = np.load(os.path.join(cache, 'logmel.npy'))
        self.W = np.load(os.path.join(cache, 'waves.npy'), mmap_mode='r')

def split(data, cmds, seed, n_enrol=5, n_pos=100, n_dev_pos=100, n_neg_per_word=200):
    """Enrolment: n_enrol recordings per command.  Dev/test positives and negatives come from speakers
    that contributed no enrolment recording (speaker-independent).  Dev and test sets are disjoint."""
    rng = np.random.default_rng(seed)
    enrol_idx, enrol_lab = [], []
    for c, w in enumerate(cmds):
        idx = np.where(data.words == w)[0]
        pick = rng.choice(idx, n_enrol, replace=False)
        enrol_idx += list(pick); enrol_lab += [c] * n_enrol
    enrol_idx = np.array(enrol_idx); enrol_lab = np.array(enrol_lab)
    enrol_spk = set(data.spk[enrol_idx])
    ok = np.array([s not in enrol_spk for s in data.spk])
    dev_pos, dev_lab, test_pos, test_lab = [], [], [], []
    for c, w in enumerate(cmds):
        idx = np.where((data.words == w) & ok)[0]; rng.shuffle(idx)
        test_pos += list(idx[:n_pos]); test_lab += [c] * n_pos
        dev_pos += list(idx[n_pos:n_pos + n_dev_pos]); dev_lab += [c] * n_dev_pos
    dev_neg, test_neg, dev_negw, test_negw = [], [], [], []
    for w in ALL_WORDS:
        if w in cmds: continue
        idx = np.where((data.words == w) & ok)[0]; rng.shuffle(idx)
        dev_neg += list(idx[:n_neg_per_word]); dev_negw += [w] * n_neg_per_word
        test_neg += list(idx[n_neg_per_word:2 * n_neg_per_word]); test_negw += [w] * n_neg_per_word
    return dict(cmds=cmds, seed=seed, enrol_idx=enrol_idx, enrol_lab=enrol_lab,
                dev_pos=np.array(dev_pos), dev_lab=np.array(dev_lab), test_pos=np.array(test_pos), test_lab=np.array(test_lab),
                dev_neg=np.array(dev_neg), dev_negw=np.array(dev_negw), test_neg=np.array(test_neg), test_negw=np.array(test_negw))

def query_sets(sp):
    """All non-enrolment utterances of a split, concatenated, with slice names."""
    names = ['dev_pos', 'test_pos', 'dev_neg', 'test_neg']
    idx = np.concatenate([sp[n] for n in names]); off = np.cumsum([0] + [len(sp[n]) for n in names])
    return idx, {n: slice(off[i], off[i + 1]) for i, n in enumerate(names)}

# ---------------- features ----------------
def vectors(LM, norm, poolmode):
    return F.pool(F.normalise(LM, norm), poolmode)

# ---------------- A: prototypes ----------------
def proto_fit(Xe, ye, k):
    return np.stack([Xe[ye == c].mean(axis=0) for c in range(k)])

def proto_score(M, Xq, metric):
    """returns pred (nq,), score (nq,) higher = more confident."""
    if metric == 'cos':
        Mn = M / np.linalg.norm(M, axis=1, keepdims=True); Qn = Xq / np.linalg.norm(Xq, axis=1, keepdims=True)
        sim = Qn @ Mn.T; return sim.argmax(1), sim.max(1)
    if metric == 'euc':
        d = np.sqrt(((Xq[:, None, :] - M[None]) ** 2).sum(-1)); return d.argmin(1), -d.min(1)
    if metric == 'cos_margin':   # best minus second best cosine
        Mn = M / np.linalg.norm(M, axis=1, keepdims=True); Qn = Xq / np.linalg.norm(Xq, axis=1, keepdims=True)
        sim = np.sort(Qn @ Mn.T, axis=1); pred = (Qn @ Mn.T).argmax(1)
        return pred, sim[:, -1] - sim[:, -2] + 0.0 * sim[:, -1]
    raise ValueError(metric)

# ---------------- B: DTW ----------------
def dtw_dist(Q, lq, Tm, lt, chunk=256):
    """Q (nq,T,NB) lengths lq; Tm (nt,T,NB) lengths lt.  Full DTW (steps (1,0),(0,1),(1,1)), Euclidean local cost,
    distance normalised by (lq+lt).  Anti-diagonal vectorised.  Returns (nq, nt)."""
    nq, T, NB = Q.shape; nt = Tm.shape[0]; out = np.zeros((nq, nt), np.float32)
    for q0 in range(0, nq, chunk):
        Qc = Q[q0:q0 + chunk]; B = len(Qc)
        # cost (B, nt, T, T)
        C = np.sqrt(np.maximum((Qc ** 2).sum(-1)[:, None, :, None] + (Tm ** 2).sum(-1)[None, :, None, :]
                               - 2 * np.einsum('bik,tjk->btij', Qc, Tm), 0)).reshape(B * nt, T, T)
        D = np.full((B * nt, T + 1, T + 1), np.inf, np.float32); D[:, 0, 0] = 0
        # anti-diagonals in the (T+1)x(T+1) padded grid: cell (i,j) with i,j>=1
        for d in range(2, 2 * T + 1):
            i = np.arange(max(1, d - T), min(T, d - 1) + 1); j = d - i
            best = np.minimum(np.minimum(D[:, i - 1, j], D[:, i, j - 1]), D[:, i - 1, j - 1])
            D[:, i, j] = C[:, i - 1, j - 1] + best
        D = D.reshape(B, nt, T + 1, T + 1)
        ii = lq[q0:q0 + chunk][:, None]; jj = lt[None, :]
        out[q0:q0 + chunk] = np.take_along_axis(np.take_along_axis(D, ii[:, :, None, None].repeat(nt, 1), 2)[:, :, 0, :],
                                                jj[:, :, None].repeat(B, 0), 2)[:, :, 0] / (ii + jj)
    return out

def trim_sequences(LM_norm, mode, drop=3.0):
    """Returns padded sequences (B,T,NB) and lengths.  mode 'full' keeps 61 frames; 'vad' keeps the active region."""
    B = LM_norm.shape[0]
    if mode == 'full': return LM_norm, np.full(B, F.T)
    s, t = F.active_region(LM_norm, drop); out = np.zeros_like(LM_norm); L = np.zeros(B, int)
    for b in range(B):
        a, z = s[b], t[b]; z = max(z, a + 4); z = min(z, F.T)
        out[b, :z - a] = LM_norm[b, a:z]; L[b] = z - a
    return out, L

def dtw_score(dist, ye, k):
    """nearest template -> class; score = -min distance; also returns -class-min for per-class."""
    cls_min = np.stack([dist[:, ye == c].min(1) for c in range(k)], 1)
    return cls_min.argmin(1), -cls_min.min(1)

# ---------------- C: uai32 ----------------
def write_rows(path, X, y=None):
    with open(path, 'w') as f:
        for i in range(len(X)):
            row = ' '.join('%.5g' % v for v in X[i])
            f.write(row + (' %d' % y[i] if y is not None else ' 0') + '\n')

def uai32_run(Xtr, ytr, Xq, hidden, epochs, lr, seed, work, tag='m', extra=None):
    """Train a fresh uai32 model on (Xtr,ytr); predict Xq.  Returns pred, probs (nq,NO), model bytes, train log tail.
    extra: optional list of (epochs, lr) continuation stages (lower-rate fine tuning)."""
    os.makedirs(work, exist_ok=True)
    tr = os.path.join(work, tag + '_train.txt'); model = os.path.join(work, tag + '.model'); q = os.path.join(work, tag + '_q.txt')
    if os.path.exists(model): os.remove(model)
    write_rows(tr, Xtr, ytr); write_rows(q, Xq)
    log = subprocess.run([UAI32, 'train', tr, model, str(hidden), str(epochs), repr(float(lr)), str(seed)],
                         capture_output=True, text=True, check=True).stdout
    for (e2, lr2) in (extra or []):
        log += subprocess.run([UAI32, 'train', tr, model, '0', str(e2), repr(float(lr2)), str(seed)],
                              capture_output=True, text=True, check=True).stdout
    with open(q) as qf:
        outp = subprocess.run([UAI32, 'predict', model], stdin=qf, capture_output=True, text=True, check=True).stdout
    rows = [l.split() for l in outp.strip().split('\n')]
    pred = np.array([int(r[0]) for r in rows]); probs = np.array([[float(v) for v in r[1:]] for r in rows], np.float32)
    size = os.path.getsize(model)
    return pred, probs, size, log.strip().split('\n')[-1]

def mlp_score(pred, probs, k):
    """Commands are classes 0..k-1; any further class is 'unknown'.  score = max command probability,
    0 if the argmax is unknown."""
    pc = probs[:, :k]; p = pc.argmax(1); s = pc.max(1)
    s = np.where(pred >= k, 0.0, s)
    return p, s

# ---------------- augmentation (waveform level) ----------------
def augment_waves(W, rng, k, shift_s=0.1, gain_db=6.0, snr=(10, 30)):
    """W (n,16000) int16 -> (n*k, 16000) float32 in [-1,1]: random circular-free shift, gain, white/brown noise."""
    x = np.asarray(W, np.float32) / 32768.0; n = len(x); out = np.zeros((n * k, F.SR), np.float32)
    for i in range(n):
        for j in range(k):
            sh = int(rng.integers(-shift_s * F.SR, shift_s * F.SR + 1)); g = 10 ** (rng.uniform(-gain_db, gain_db) / 20)
            y = np.zeros(F.SR, np.float32)
            if sh >= 0: y[sh:] = x[i, :F.SR - sh]
            else: y[:F.SR + sh] = x[i, -sh:]
            y *= g
            rms = np.sqrt((y ** 2).mean()) + 1e-6
            nz = rng.standard_normal(F.SR).astype(np.float32)
            if rng.random() < 0.5: nz = np.cumsum(nz); nz -= nz.mean(); nz /= (np.sqrt((nz ** 2).mean()) + 1e-9)   # brown-ish
            y += nz * rms / 10 ** (rng.uniform(*snr) / 20)
            out[i * k + j] = np.clip(y, -1, 1)
    return out

def synth_negative_waves(W, y, rng, n_out):
    """Synthetic 'unknown' audio from the enrolment clips only: time-reversed clips, spliced halves of two
    different commands, and noise-only clips.  Returns (n_out,16000) float32."""
    x = np.asarray(W, np.float32) / 32768.0; n = len(x); out = np.zeros((n_out, F.SR), np.float32)
    for m in range(n_out):
        kind = m % 3
        if kind == 0:
            i = rng.integers(n); out[m] = x[i][::-1]
        elif kind == 1:
            i = rng.integers(n); j = rng.choice(np.where(y != y[i])[0]); cut = int(rng.uniform(0.3, 0.7) * F.SR)
            z = np.concatenate([x[i][:cut], x[j][cut:]]); out[m] = z
        else:
            lvl = 10 ** (rng.uniform(-50, -15) / 20); nz = rng.standard_normal(F.SR).astype(np.float32)
            if rng.random() < 0.5: nz = np.cumsum(nz); nz -= nz.mean(); nz /= (np.sqrt((nz ** 2).mean()) + 1e-9)
            out[m] = np.clip(nz * lvl, -1, 1)
    return out

def synth_negative_vectors(X, rng, n_out, nseg=F.NSEG, nb=F.NB):
    """Feature-level negatives: segment-shuffled copies of enrolment vectors."""
    out = np.zeros((n_out, X.shape[1]), np.float32)
    for m in range(n_out):
        v = X[rng.integers(len(X))].reshape(nseg, nb); out[m] = v[rng.permutation(nseg)].reshape(-1)
    return out

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - h) / d, (c + h) / d)

def threshold_for_fa(neg_scores, fa=0.01):
    """Largest-FA-compatible threshold: accept if score > thr; at most floor(fa*n) dev negatives accepted."""
    s = np.sort(neg_scores)[::-1]; k = int(np.floor(fa * len(s)))
    return s[k]

# ---------------- fixed recipe chosen in the pilot (seeds 901-905, never reused) ----------------
import feats2 as f2
def pooled_vectors(LM, feat='mfcc_raw', ncoef=12, pm='center'):
    """(B,61,16) log-mel -> (B, 12*ncoef) : DCT -> c1..c_ncoef (no CMN), energy-centred 48-frame crop, 12 segment means."""
    X = (LM @ f2.DCT.T)[:, :, 1:ncoef + 1] if feat == 'mfcc_raw' else f2.frames(LM, feat)
    if feat == 'mfcc_c0': X = (LM @ f2.DCT.T)[:, :, :ncoef + 1]
    return f2.pool_center(X.astype(np.float32), f2.energy(LM)) if pm == 'center' else f2.pool_grid(X.astype(np.float32))

def dtw_frames(LM, feat='logmel_cmvn'):
    return f2.frames(LM, feat)

def roc_stats(pos_ok, pos_s, neg_s):
    """Oracle recall at FA levels on these negatives, AUC and EER of pos vs neg scores."""
    out = {}
    for fa in [0.01, 0.05, 0.10, 0.20]:
        thr = threshold_for_fa(neg_s, fa); out['rec@%d%%' % int(fa * 100)] = float(((pos_s > thr) & pos_ok).mean())
    allsc = np.concatenate([pos_s, neg_s]); lab = np.concatenate([np.ones(len(pos_s)), np.zeros(len(neg_s))])
    order = np.argsort(-allsc, kind='stable'); lab = lab[order]; tp = np.cumsum(lab) / lab.sum(); fp = np.cumsum(1 - lab) / (1 - lab).sum()
    out['AUC'] = float(np.trapezoid(tp, fp)); out['EER'] = float(fp[np.argmin(np.abs(fp - (1 - tp)))])
    return out
