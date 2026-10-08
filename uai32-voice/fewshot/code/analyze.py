"""Compute recall / false-accept metrics from run_main.py outputs.
usage: python3 -I analyze.py TEST.npz [--dev DEV.npz] [--fa 0.01]
Threshold policies:
  per-draw : threshold chosen on that draw's own dev negatives (speaker-disjoint from enrolment, disjoint from test negatives)
  fixed    : one global threshold per method = median of the per-draw dev thresholds of the DEV run (separate seeds), applied unchanged
  oracle   : threshold at exactly <=fa on the test negatives themselves (upper bound, not a legitimate operating point)"""
import numpy as np, sys, os, json, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs
ap = argparse.ArgumentParser(); ap.add_argument('test'); ap.add_argument('--dev'); ap.add_argument('--fa', type=float, default=0.01); ap.add_argument('--json')
a = ap.parse_args()
def load(p):
    z = np.load(p, allow_pickle=True); return json.loads(str(z['meta'])), z['results'][0]
meta, R = load(a.test); cmds = meta['cmds']; k = len(cmds); seeds = meta['seeds']
methods = [m for m in R if not m.startswith('_')]
devR = load(a.dev)[1] if a.dev else None

def slices(sp):
    _, sl = fs.query_sets(sp); return sl

def thr_of(res, sp, fa):
    sl = slices(sp); return fs.threshold_for_fa(res[1][sl['dev_neg']], fa)

summary = {}
print('commands', cmds, '| test seeds', seeds[0], '-', seeds[-1], '| n_enrol', meta['n_enrol'], '| vec dim', meta['vec_dim'], '| FA target %.1f%%' % (100 * a.fa))
print('state bytes:', json.dumps(meta['sizes']))
for m in methods:
    fixed_thr = None
    if devR is not None and m in devR:
        fixed_thr = float(np.median([thr_of(devR[m][s], devR['_split'][s], a.fa) for s in devR[m]]))
    rows = {'per-draw': [], 'fixed': [], 'oracle': []}; closed = []; roc = []; neg_by_word = {}
    for s in seeds:
        pred, score = R[m][s]; sp = R['_split'][s]; sl = slices(sp)
        pos_ok = pred[sl['test_pos']] == sp['test_lab']; closed.append(pos_ok.mean())
        roc.append(fs.roc_stats(pos_ok, score[sl['test_pos']], score[sl['test_neg']]))
        pol = {'per-draw': fs.threshold_for_fa(score[sl['dev_neg']], a.fa), 'oracle': fs.threshold_for_fa(score[sl['test_neg']], a.fa)}
        if fixed_thr is not None: pol['fixed'] = fixed_thr
        for name, thr in pol.items():
            acc_pos = score[sl['test_pos']] > thr; acc_neg = score[sl['test_neg']] > thr
            rec_c = [float((acc_pos & pos_ok)[sp['test_lab'] == c].mean()) for c in range(k)]
            wrong_c = float((acc_pos & ~pos_ok).mean())   # accepted but confused with another command
            rows[name].append(dict(rec=rec_c, fa_k=int(acc_neg.sum()), fa_n=int(len(acc_neg)), pos_k=int((acc_pos & pos_ok).sum()), pos_n=int(len(acc_pos)), wrong=wrong_c, thr=float(thr)))
            if name == 'per-draw':
                for w in np.unique(sp['test_negw']):
                    neg_by_word.setdefault(str(w), []).append(float(acc_neg[sp['test_negw'] == w].mean()))
    out = dict(closed_set_acc=float(np.mean(closed)), closed_sd=float(np.std(closed)), roc={key: float(np.mean([r[key] for r in roc])) for key in roc[0]})
    print('\n== %s   closed-set accuracy %.3f (sd %.3f)   AUC %.3f  EER %.3f   oracle recall @1%%/5%%/10%% FA: %.3f / %.3f / %.3f' % (
        m, out['closed_set_acc'], out['closed_sd'], out['roc']['AUC'], out['roc']['EER'], out['roc']['rec@1%'], out['roc']['rec@5%'], out['roc']['rec@10%']))
    for name, rr in rows.items():
        if not rr: continue
        rec = np.array([r['rec'] for r in rr]); fa_k = sum(r['fa_k'] for r in rr); fa_n = sum(r['fa_n'] for r in rr)
        fa_rates = np.array([r['fa_k'] / r['fa_n'] for r in rr]); w = fs.wilson(fa_k, fa_n); pk = sum(r['pos_k'] for r in rr); pn = sum(r['pos_n'] for r in rr); wr = fs.wilson(pk, pn)
        per_cmd = '  '.join('%s %.3f±%.3f' % (cmds[c], rec[:, c].mean(), rec[:, c].std()) for c in range(k))
        print('   %-9s thr %s | recall per command: %s | mean recall %.3f (min over draws %.3f) pooled %d/%d Wilson [%.3f,%.3f] | test FA %.4f±%.4f pooled %d/%d Wilson [%.4f,%.4f] | accepted-but-wrong %.3f' % (
            name, ('%.4f' % rr[0]['thr']) if name == 'fixed' else 'per-draw', per_cmd, rec.mean(), rec.mean(1).min(), pk, pn, wr[0], wr[1], fa_rates.mean(), fa_rates.std(), fa_k, fa_n, w[0], w[1], np.mean([r['wrong'] for r in rr])))
        out[name] = dict(recall_per_cmd=rec.mean(0).tolist(), recall_sd=rec.std(0).tolist(), recall_mean=float(rec.mean()), pos_k=pk, pos_n=pn, recall_wilson=wr,
                         fa_mean=float(fa_rates.mean()), fa_sd=float(fa_rates.std()), fa_k=fa_k, fa_n=fa_n, fa_wilson=w, thr=(fixed_thr if name == 'fixed' else None))
    print('   per-draw FA by unfamiliar word: ' + '  '.join('%s %.3f' % (w, np.mean(v)) for w, v in sorted(neg_by_word.items())))
    out['fa_by_word'] = {w: float(np.mean(v)) for w, v in neg_by_word.items()}; summary[m] = out
if a.json: json.dump(dict(meta=meta, summary=summary), open(a.json, 'w'), indent=1, default=str)
