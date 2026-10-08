import numpy as np, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs, features as F
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
data = fs.Data(os.path.join(S, 'cache')); cmds = ('yes', 'no', 'stop'); seeds = [901, 902, 903]; k = 3
work = os.path.join(S, 'work', 'pilot3'); splits = [fs.split(data, cmds, s) for s in seeds]

def stats(sp, sl, p, s):
    pos_ok = p[sl['test_pos']] == sp['test_lab']; st = fs.roc_stats(pos_ok, s[sl['test_pos']], s[sl['test_neg']]); st['acc'] = float(pos_ok.mean())
    thr = fs.threshold_for_fa(s[sl['dev_neg']]); st['rec@dev'] = float((pos_ok & (s[sl['test_pos']] > thr)).mean()); st['FAdev'] = float((s[sl['test_neg']] > thr).mean())
    st['thr'] = float(thr); st['sat'] = float((s[sl['test_neg']] >= 0.9995).mean()); return st
def show(name, rows, extra=''):
    r = {key: np.mean([x[key] for x in rows]) for key in rows[0]}; print('%-26s ' % name + '  '.join('%s %.3f' % (a, b) for a, b in r.items()), extra, flush=True)
prep = []
for sp in splits:
    qidx, sl = fs.query_sets(sp); rng = np.random.default_rng(sp['seed'] + 7)
    Ve = fs.pooled_vectors(data.LM[sp['enrol_idx']]); Vq = fs.pooled_vectors(data.LM[qidx])
    Wa = fs.augment_waves(data.W[sp['enrol_idx']], rng, 30); Va = fs.pooled_vectors(F.logmel(Wa)); ya = np.repeat(sp['enrol_lab'], 30)
    nneg = 31 * 15 // 2; Wn = fs.synth_negative_waves(data.W[sp['enrol_idx']], sp['enrol_lab'], rng, nneg); Vn = fs.pooled_vectors(F.logmel(Wn))
    Vs = fs.synth_negative_vectors(np.concatenate([Ve, Va]), rng, nneg // 3, nseg=12, nb=12); prep.append((sp, sl, Ve, Vq, Va, ya, Vn, Vs))
l2 = lambda X: X / np.linalg.norm(X, axis=1, keepdims=True)
for name, mode, E, lr, norm in [('aug E5 lr.01', 'aug', 5, 0.01, 0), ('aug E10 lr.01', 'aug', 10, 0.01, 0), ('aug E3 lr.05', 'aug', 3, 0.05, 0), ('aug E20 lr.005', 'aug', 20, 0.005, 0),
                                ('aug_neg E20 lr.01 L2', 'augneg', 20, 0.01, 1), ('plain E300 lr.01 L2', 'plain', 300, 0.01, 1), ('aug E10 lr.01 L2', 'aug', 10, 0.01, 1), ('plain E300 lr.01', 'plain', 300, 0.01, 0)]:
    rr = []; t0 = time.time()
    for sp, sl, Ve, Vq, Va, ya, Vn, Vs in prep:
        if mode == 'aug': Xtr = np.concatenate([Ve, Va]); ytr = np.concatenate([sp['enrol_lab'], ya])
        elif mode == 'augneg': Xtr = np.concatenate([Ve, Va, Vn, Vs]); ytr = np.concatenate([sp['enrol_lab'], ya, np.full(len(Vn) + len(Vs), k)])
        else: Xtr, ytr = Ve, sp['enrol_lab']
        Xq = Vq
        if norm: Xtr, Xq = l2(Xtr), l2(Vq)
        pred, probs, size, log = fs.uai32_run(Xtr, ytr, Xq, 16, E, lr, sp['seed'], work); p, s = fs.mlp_score(pred, probs, k); rr.append(stats(sp, sl, p, s))
    show('mlp ' + name, rr, '| rows %d (%.0fs) %s' % (len(Xtr), time.time() - t0, log))
