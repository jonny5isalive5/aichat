import numpy as np, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs, features as F
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
data = fs.Data(os.path.join(S, 'cache')); cmds = ('yes', 'no', 'stop'); seeds = [901, 902, 903]; k = 3
work = os.path.join(S, 'work', 'pilot'); splits = [fs.split(data, cmds, s) for s in seeds]
configs = [('noaug', 0, 0, 16, 300, 0.05, None), ('noaug_lowlr', 0, 0, 16, 300, 0.01, None),
           ('aug30', 30, 0, 16, 60, 0.05, None), ('aug30_H32', 30, 0, 32, 60, 0.05, None), ('aug30_E30', 30, 0, 16, 30, 0.05, None),
           ('aug30_neg', 30, 1, 16, 60, 0.05, None), ('neg_only', 0, 1, 16, 300, 0.05, None)]
for name, aug, neg, H, E, lr, extra in configs:
    rows = []; t0 = time.time()
    for sp in splits:
        qidx, sl = fs.query_sets(sp); rng = np.random.default_rng(sp['seed'] + 7)
        Xe = fs.pooled_vectors(data.LM[sp['enrol_idx']]); ye = sp['enrol_lab']; Xq = fs.pooled_vectors(data.LM[qidx])
        if aug:
            Wa = fs.augment_waves(data.W[sp['enrol_idx']], rng, aug); Xe = np.concatenate([Xe, fs.pooled_vectors(F.logmel(Wa))]); ye = np.concatenate([ye, np.repeat(sp['enrol_lab'], aug)])
        if neg:
            nneg = max(len(Xe) // 2, 45)
            Wn = fs.synth_negative_waves(data.W[sp['enrol_idx']], sp['enrol_lab'], rng, nneg); Xn = fs.pooled_vectors(F.logmel(Wn))
            Xs = fs.synth_negative_vectors(Xe, rng, nneg // 3, nseg=12, nb=12)
            Xe = np.concatenate([Xe, Xn, Xs]); ye = np.concatenate([ye, np.full(len(Xn) + len(Xs), k)])
        pred, probs, size, log = fs.uai32_run(Xe, ye, Xq, H, E, lr, sp['seed'], work, extra=extra)
        p, s = fs.mlp_score(pred, probs, k)
        pos_ok = p[sl['test_pos']] == sp['test_lab']; st = fs.roc_stats(pos_ok, s[sl['test_pos']], s[sl['test_neg']]); st['acc'] = float(pos_ok.mean())
        thr = fs.threshold_for_fa(s[sl['dev_neg']]); st['rec@dev'] = float((pos_ok & (s[sl['test_pos']] > thr)).mean()); st['FAdev'] = float((s[sl['test_neg']] > thr).mean())
        st['thr'] = float(thr); st['neg>=0.999'] = float((s[sl['test_neg']] >= 0.999).mean()); rows.append(st)
    r = {key: np.mean([x[key] for x in rows]) for key in rows[0]}
    print('%-14s rows %4d bytes %5d (%.0fs) ' % (name, len(Xe), size, time.time() - t0) + '  '.join('%s %.3f' % (a, b) for a, b in r.items()), '| last log:', log, flush=True)
