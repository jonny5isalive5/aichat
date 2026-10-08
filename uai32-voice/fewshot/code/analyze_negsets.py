"""Recall at the per-draw 1%-FA threshold when the unfamiliar set excludes the similar-sounding words (dev AND test negatives restricted)."""
import numpy as np, sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); R = os.path.join(S, 'results')
def load(p):
    z = np.load(p, allow_pickle=True); return json.loads(str(z['meta'])), z['results'][0]
for tri, similar in [('yes_no_stop', ('go', 'up')), ('up_down_go', ('no', 'stop'))]:
    meta, res = load(os.path.join(R, 'full_%s_test.npz' % tri)); cmds = meta['cmds']; k = len(cmds)
    print('\n%s: recall at per-draw <=1%% FA threshold | negatives = all five other words  vs  excluding %s' % ('/'.join(cmds), '+'.join(similar)))
    for m in [x for x in res if not x.startswith('_')]:
        out = {}
        for label, excl in [('all', ()), ('no-similar', similar)]:
            recs, fas = [], []
            for s in meta['seeds']:
                pred, score = res[m][s]; sp = res['_split'][s]; sl = fs.query_sets(sp)[1]
                kd = ~np.isin(sp['dev_negw'], excl); kt = ~np.isin(sp['test_negw'], excl)
                thr = fs.threshold_for_fa(score[sl['dev_neg']][kd]); ok = pred[sl['test_pos']] == sp['test_lab']
                recs.append((ok & (score[sl['test_pos']] > thr)).mean()); fas.append((score[sl['test_neg']][kt] > thr).mean())
            out[label] = (np.mean(recs), np.std(recs), np.mean(fas))
        print('  %-18s all: recall %.3f±%.3f FA %.4f | excl %s: recall %.3f±%.3f FA %.4f' % (m, *out['all'], '+'.join(similar), *out['no-similar']))
