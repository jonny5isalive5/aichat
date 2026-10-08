import numpy as np, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs, features as F, dtw_c
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
data = fs.Data(os.path.join(S, 'cache')); cmds = ('yes', 'no', 'stop'); seeds = [901, 902, 903]; k = 3
work = os.path.join(S, 'work', 'pilot2'); splits = [fs.split(data, cmds, s) for s in seeds]
def stats(sp, sl, p, s):
    pos_ok = p[sl['test_pos']] == sp['test_lab']; st = fs.roc_stats(pos_ok, s[sl['test_pos']], s[sl['test_neg']]); st['acc'] = float(pos_ok.mean())
    thr = fs.threshold_for_fa(s[sl['dev_neg']]); st['rec@dev'] = float((pos_ok & (s[sl['test_pos']] > thr)).mean()); st['FAdev'] = float((s[sl['test_neg']] > thr).mean())
    st['thr'] = float(thr); st['sat'] = float((s[sl['test_neg']] >= np.max(s[sl['test_neg']])).mean()); return st
def show(name, rows, extra=''):
    r = {key: np.mean([x[key] for x in rows]) for key in rows[0]}; print('%-26s ' % name + '  '.join('%s %.3f' % (a, b) for a, b in r.items()), extra, flush=True)
prep = []
for sp in splits:
    qidx, sl = fs.query_sets(sp); rng = np.random.default_rng(sp['seed'] + 7)
    Ve = fs.pooled_vectors(data.LM[sp['enrol_idx']]); Vq = fs.pooled_vectors(data.LM[qidx])
    Wa = fs.augment_waves(data.W[sp['enrol_idx']], rng, 30); Va = fs.pooled_vectors(F.logmel(Wa)); ya = np.repeat(sp['enrol_lab'], 30)
    nneg = 31 * 15 // 2; Wn = fs.synth_negative_waves(data.W[sp['enrol_idx']], sp['enrol_lab'], rng, nneg); LMn = F.logmel(Wn); Vn = fs.pooled_vectors(LMn)
    Vs = fs.synth_negative_vectors(np.concatenate([Ve, Va]), rng, nneg // 3, nseg=12, nb=12)
    prep.append((sp, sl, qidx, Ve, Vq, Va, ya, Vn, Vs, Wn, LMn))
# --- prototypes / DTW with synthetic negatives ---
rows = {n: [] for n in ['proto negmargin', 'proto negratio', 'proto 4class-ratio', 'dtw negmargin', 'dtw negratio', 'dtw min(ref)', 'dtw margin(ref)', 'proto min(ref)']}
for sp, sl, qidx, Ve, Vq, Va, ya, Vn, Vs, Wn, LMn in prep:
    M = fs.proto_fit(Ve, sp['enrol_lab'], k); Mn = M / np.linalg.norm(M, axis=1, keepdims=True); Qn = Vq / np.linalg.norm(Vq, axis=1, keepdims=True); dcls = 1 - Qn @ Mn.T
    kinds = np.arange(len(Vn)) % 3; Nproto = np.stack([Vn[kinds == j].mean(0) for j in range(3)] + [Vs.mean(0)]); Nn = Nproto / np.linalg.norm(Nproto, axis=1, keepdims=True)
    dneg = (1 - Qn @ Nn.T).min(1); pred = dcls.argmin(1); d1 = dcls.min(1)
    rows['proto negmargin'].append(stats(sp, sl, pred, dneg - d1)); rows['proto negratio'].append(stats(sp, sl, pred, dneg / (d1 + 1e-9)))
    rows['proto 4class-ratio'].append(stats(sp, sl, pred, np.minimum(np.sort(dcls, 1)[:, 1], dneg) / (d1 + 1e-9)))
    rows['proto min(ref)'].append(stats(sp, sl, pred, -d1))
    Xe = fs.dtw_frames(data.LM[sp['enrol_idx']]); Xq = fs.dtw_frames(data.LM[qidx]); Xn = fs.dtw_frames(LMn[:45])   # 45 negative templates
    d = dtw_c.dtw_dist(Xq, np.full(len(Xq), F.T), np.concatenate([Xe, Xn]), np.full(len(Xe) + len(Xn), F.T))
    dc = np.stack([d[:, :15][:, sp['enrol_lab'] == c].min(1) for c in range(k)], 1); dn = d[:, 15:].min(1); pred = dc.argmin(1); d1 = dc.min(1); srt = np.sort(dc, 1)
    rows['dtw negmargin'].append(stats(sp, sl, pred, dn - d1)); rows['dtw negratio'].append(stats(sp, sl, pred, dn / d1))
    rows['dtw min(ref)'].append(stats(sp, sl, pred, -d1)); rows['dtw margin(ref)'].append(stats(sp, sl, pred, srt[:, 1] - srt[:, 0]))
for n, r in rows.items(): show(n, r)
# --- MLP with negatives: epochs / rate grid against saturation ---
for name, aug, E, lr in [('aug_neg E5', 1, 5, 0.05), ('aug_neg E10', 1, 10, 0.05), ('aug_neg E20', 1, 20, 0.05), ('aug_neg E20 lr.01', 1, 20, 0.01), ('aug_neg E60 lr.01', 1, 60, 0.01),
                         ('neg E100', 0, 100, 0.05), ('neg E300 lr.01', 0, 300, 0.01), ('aug E10', -1, 10, 0.05), ('aug E5', -1, 5, 0.05)]:
    rr = []; t0 = time.time()
    for sp, sl, qidx, Ve, Vq, Va, ya, Vn, Vs, Wn, LMn in prep:
        if aug == 1: Xtr = np.concatenate([Ve, Va, Vn, Vs]); ytr = np.concatenate([sp['enrol_lab'], ya, np.full(len(Vn) + len(Vs), k)])
        elif aug == 0: Xtr = np.concatenate([Ve, Vn[:15]]); ytr = np.concatenate([sp['enrol_lab'], np.full(15, k)])
        else: Xtr = np.concatenate([Ve, Va]); ytr = np.concatenate([sp['enrol_lab'], ya])
        pred, probs, size, log = fs.uai32_run(Xtr, ytr, Vq, 16, E, lr, sp['seed'], work); p, s = fs.mlp_score(pred, probs, k); rr.append(stats(sp, sl, p, s))
    show('mlp ' + name, rr, '| rows %d (%.0fs) %s' % (len(Xtr), time.time() - t0, log))
