"""Pilot on seeds 901-905 (never used for final numbers): choose feature normalisation/pooling, DTW trimming,
and uai32 hyper-parameters.  Prints closed-set accuracy, recall at the per-draw dev threshold (<=1% dev FA), test FA."""
import numpy as np, sys, time, os, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs, features as F, dtw_c
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
data = fs.Data(os.path.join(S, 'cache'))
cmds = ('yes', 'no', 'stop'); seeds = [901, 902, 903, 904, 905]; k = 3

def evaluate(sp, sl, pred, score):
    thr = fs.threshold_for_fa(score[sl['dev_neg']])
    acc = (pred[sl['test_pos']] == sp['test_lab']).mean()
    rec = ((pred[sl['test_pos']] == sp['test_lab']) & (score[sl['test_pos']] > thr)).mean()
    fa = (score[sl['test_neg']] > thr).mean()
    return acc, rec, fa

def report(name, rows):
    r = np.array(rows); print('%-40s closed-set acc %.3f   recall@1%%devFA %.3f (sd %.3f)   testFA %.4f' % (name, r[:, 0].mean(), r[:, 1].mean(), r[:, 1].std(), r[:, 2].mean()), flush=True)

splits = [fs.split(data, cmds, s) for s in seeds]
if 'proto' in sys.argv[1:] or len(sys.argv) == 1:
    for norm, pm, metric in itertools.product(['cmn', 'peak'], ['grid', 'center', 'vad'], ['cos', 'euc']):
        rows = []
        for sp in splits:
            qidx, sl = fs.query_sets(sp)
            Xe = fs.vectors(data.LM[sp['enrol_idx']], norm, pm); Xq = fs.vectors(data.LM[qidx], norm, pm)
            M = fs.proto_fit(Xe, sp['enrol_lab'], k); pred, score = fs.proto_score(M, Xq, metric)
            rows.append(evaluate(sp, sl, pred, score))
        report('proto %s %s %s' % (norm, pm, metric), rows)
if 'dtw' in sys.argv[1:] or len(sys.argv) == 1:
    for norm, trim, drop in [('cmn', 'full', 0), ('peak', 'full', 0), ('cmn', 'vad', 3.0), ('cmn', 'vad', 2.0), ('peak', 'vad', 3.0), ('peak', 'vad', 2.0)]:
        rows = []; t0 = time.time()
        for sp in splits:
            qidx, sl = fs.query_sets(sp)
            Te, lt = fs.trim_sequences(F.normalise(data.LM[sp['enrol_idx']], norm), trim, drop)
            Q, lq = fs.trim_sequences(F.normalise(data.LM[qidx], norm), trim, drop)
            d = dtw_c.dtw_dist(Q, lq, Te, lt); pred, score = fs.dtw_score(d, sp['enrol_lab'], k)
            rows.append(evaluate(sp, sl, pred, score))
        report('dtw %s %s drop%.1f (%.0fs)' % (norm, trim, drop, time.time() - t0), rows)
if 'mlp' in sys.argv[1:] or len(sys.argv) == 1:
    norm, pm = sys.argv[sys.argv.index('mlp') + 1].split(',') if 'mlp' in sys.argv[1:] else ('cmn', 'center')
    work = os.path.join(S, 'work', 'pilot')
    for aug, H, E, lr, extra in [(0, 16, 300, 0.05, None), (0, 16, 600, 0.02, None), (30, 16, 60, 0.05, None), (30, 16, 60, 0.05, [(20, 0.01)]), (30, 32, 60, 0.05, None)]:
        rows = []; t0 = time.time(); logs = []
        for sp in splits:
            qidx, sl = fs.query_sets(sp); rng = np.random.default_rng(sp['seed'] + 7)
            Xe = fs.vectors(data.LM[sp['enrol_idx']], norm, pm); ye = sp['enrol_lab']; Xq = fs.vectors(data.LM[qidx], norm, pm)
            if aug:
                Wa = fs.augment_waves(data.W[sp['enrol_idx']], rng, aug); Xa = fs.vectors(F.logmel(Wa), norm, pm)
                Xe = np.concatenate([Xe, Xa]); ye = np.concatenate([ye, np.repeat(sp['enrol_lab'], aug)])
            pred, probs, size, log = fs.uai32_run(Xe, ye, Xq, H, E, lr, sp['seed'], work, extra=extra)
            p, s = fs.mlp_score(pred, probs, k); rows.append(evaluate(sp, sl, p, s)); logs.append(log)
        report('mlp aug%d H%d E%d lr%g extra%s bytes%d (%.0fs)' % (aug, H, E, lr, extra, size, time.time() - t0), rows); print('   last log:', logs[0])
