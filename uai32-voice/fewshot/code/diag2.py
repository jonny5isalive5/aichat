import numpy as np, sys, os, itertools, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs, features as F, dtw_c, feats2 as f2
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
data = fs.Data(os.path.join(S, 'cache'))
cmds = ('yes', 'no', 'stop'); seeds = [901, 902, 903]; k = 3
from diag import roc_stats
splits = [fs.split(data, cmds, s) for s in seeds]
def summarise(name, rows):
    r = {key: np.mean([x[key] for x in rows]) for key in rows[0]}
    print('%-36s ' % name + '  '.join('%s %.3f' % (a, b) for a, b in r.items()), flush=True)
feats = ['logmel_cmn', 'logmel_cmvn', 'lmclamp_cmn', 'mfcc_cmn', 'mfcc_cmvn', 'mfcc_raw']
for feat in feats:
    res = {('proto', m, c): [] for m in ['cos', 'euc'] for c in ['min', 'margin', 'ratio', 'tnorm']}
    res.update({('dtw', 'euc', c): [] for c in ['min', 'margin', 'ratio', 'tnorm']})
    t0 = time.time()
    for sp in splits:
        qidx, sl = fs.query_sets(sp); LMe = data.LM[sp['enrol_idx']]; LMq = data.LM[qidx]
        Xe = f2.frames(LMe, feat); Xq = f2.frames(LMq, feat)
        Ve = f2.pool_center(Xe, f2.energy(LMe)); Vq = f2.pool_center(Xq, f2.energy(LMq)); M = fs.proto_fit(Ve, sp['enrol_lab'], k)
        for m in ['cos', 'euc']:
            if m == 'cos':
                Mn = M / np.linalg.norm(M, axis=1, keepdims=True); Qn = Vq / np.linalg.norm(Vq, axis=1, keepdims=True)
                dcls = 1 - Qn @ Mn.T; En = Ve / np.linalg.norm(Ve, axis=1, keepdims=True); dall = 1 - Qn @ En.T
            else:
                dcls = np.sqrt(((Vq[:, None] - M[None]) ** 2).sum(-1)); dall = np.sqrt(((Vq[:, None] - Ve[None]) ** 2).sum(-1))
            for c in ['min', 'margin', 'ratio', 'tnorm']:
                pred, score = f2.calibrate(dcls, dall, c)
                thr = fs.threshold_for_fa(score[sl['dev_neg']]); pos_ok = pred[sl['test_pos']] == sp['test_lab']
                st = roc_stats(pos_ok, score[sl['test_pos']], score[sl['test_neg']]); st['acc'] = pos_ok.mean()
                st['rec@dev'] = (pos_ok & (score[sl['test_pos']] > thr)).mean(); st['FAdev'] = (score[sl['test_neg']] > thr).mean()
                res[('proto', m, c)].append(st)
        d = dtw_c.dtw_dist(Xq, np.full(len(Xq), F.T), Xe, np.full(len(Xe), F.T))
        dcls = np.stack([d[:, sp['enrol_lab'] == c].min(1) for c in range(k)], 1)
        for c in ['min', 'margin', 'ratio', 'tnorm']:
            pred, score = f2.calibrate(dcls, d, c)
            thr = fs.threshold_for_fa(score[sl['dev_neg']]); pos_ok = pred[sl['test_pos']] == sp['test_lab']
            st = roc_stats(pos_ok, score[sl['test_pos']], score[sl['test_neg']]); st['acc'] = pos_ok.mean()
            st['rec@dev'] = (pos_ok & (score[sl['test_pos']] > thr)).mean(); st['FAdev'] = (score[sl['test_neg']] > thr).mean()
            res[('dtw', 'euc', c)].append(st)
    print('=== feat', feat, '(%.0fs)' % (time.time() - t0))
    for key, rows in res.items(): summarise(' '.join(key), rows)
