import numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
data = fs.Data(os.path.join(S, 'cache')); cmds = ('yes', 'no', 'stop'); seeds = [901, 902, 903, 904, 905]; k = 3
splits = [fs.split(data, cmds, s) for s in seeds]
for feat, nc, pm in [('mfcc_raw', 12, 'center'), ('mfcc_raw', 12, 'grid'), ('mfcc_c0', 12, 'center'), ('mfcc_raw', 15, 'center'), ('mfcc_raw', 8, 'center')]:
    rows = []
    for sp in splits:
        qidx, sl = fs.query_sets(sp)
        Ve = fs.pooled_vectors(data.LM[sp['enrol_idx']], feat, nc, pm); Vq = fs.pooled_vectors(data.LM[qidx], feat, nc, pm); M = fs.proto_fit(Ve, sp['enrol_lab'], k)
        Mn = M / np.linalg.norm(M, axis=1, keepdims=True); Qn = Vq / np.linalg.norm(Vq, axis=1, keepdims=True); dcls = 1 - Qn @ Mn.T
        for c in ['min', 'ratio']:
            pred, score = fs.f2.calibrate(dcls, None, c); pos_ok = pred[sl['test_pos']] == sp['test_lab']
            st = fs.roc_stats(pos_ok, score[sl['test_pos']], score[sl['test_neg']]); st['acc'] = pos_ok.mean(); st['c'] = c; rows.append(st)
    for c in ['min', 'ratio']:
        rr = [r for r in rows if r['c'] == c]; print('%-10s nc%2d %-6s %-5s dim %3d ' % (feat, nc, pm, c, Vq.shape[1]) + '  '.join('%s %.3f' % (a, np.mean([x[a] for x in rr])) for a in ['acc', 'rec@1%', 'rec@5%', 'rec@10%', 'AUC', 'EER']), flush=True)
