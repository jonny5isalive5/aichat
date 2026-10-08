"""Does uint8 quantisation of DTW templates (CMVN log-mel, step 0.05, clipped to [-6.35, 6.4]) change the DTW results?  seeds 1-10, yes/no/stop."""
import numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs, features as F, dtw_c
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); data = fs.Data(os.path.join(S, 'cache')); cmds = ('yes', 'no', 'stop'); k = 3
q = lambda X: (np.clip(np.round(X / 0.05), -127, 128).astype(np.int16).astype(np.float32)) * 0.05
res = {'float32': [], 'uint8': []}
for seed in range(1, 11):
    sp = fs.split(data, cmds, seed); qidx, sl = fs.query_sets(sp)
    Xe = fs.dtw_frames(data.LM[sp['enrol_idx']]); Xq = fs.dtw_frames(data.LM[qidx])
    for name, Te in [('float32', Xe), ('uint8', q(Xe))]:
        d = dtw_c.dtw_dist(Xq, np.full(len(Xq), F.T), Te, np.full(len(Te), F.T)); dcls = np.stack([d[:, sp['enrol_lab'] == c].min(1) for c in range(k)], 1)
        pred, score = fs.f2.calibrate(dcls, d, 'margin'); ok = pred[sl['test_pos']] == sp['test_lab']; thr = fs.threshold_for_fa(score[sl['dev_neg']])
        res[name].append((ok.mean(), (ok & (score[sl['test_pos']] > thr)).mean(), (score[sl['test_neg']] > thr).mean()))
for name, r in res.items():
    r = np.array(r); print('DTW-margin templates %-8s closed-set %.3f  recall@1%%devFA %.3f  testFA %.4f' % (name, r[:, 0].mean(), r[:, 1].mean(), r[:, 2].mean()))
print('max |quantisation error| in template values: %.3f (CMVN units; value range about -4..+4)' % 0.025)
