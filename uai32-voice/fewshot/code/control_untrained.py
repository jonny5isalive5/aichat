"""Untrained control: uai32 model saved after 0 epochs (random He-uniform init), same features, seeds 1-10, yes/no/stop."""
import numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); data = fs.Data(os.path.join(S, 'cache')); cmds = ('yes', 'no', 'stop'); k = 3
accs, recs, fas = [], [], []
for seed in range(1, 11):
    sp = fs.split(data, cmds, seed); qidx, sl = fs.query_sets(sp)
    Ve = fs.pooled_vectors(data.LM[sp['enrol_idx']]); Vq = fs.pooled_vectors(data.LM[qidx])
    pred, probs, size, log = fs.uai32_run(Ve, sp['enrol_lab'], Vq, 16, 0, 0.01, seed, os.path.join(S, 'work', 'control_untrained'))
    p, s = fs.mlp_score(pred, probs, k); ok = p[sl['test_pos']] == sp['test_lab']; thr = fs.threshold_for_fa(s[sl['dev_neg']])
    accs.append(ok.mean()); recs.append((ok & (s[sl['test_pos']] > thr)).mean()); fas.append((s[sl['test_neg']] > thr).mean())
print('UNTRAINED CONTROL (0 epochs, seeds 1-10, yes/no/stop): closed-set acc %.3f±%.3f  recall@per-draw-1%%FA %.3f±%.3f  test FA %.4f  model bytes %d  (%s)' % (np.mean(accs), np.std(accs), np.mean(recs), np.std(recs), np.mean(fas), size, log))
