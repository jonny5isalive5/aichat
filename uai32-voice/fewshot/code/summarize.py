"""Collect every run into results/summary.txt and results/summary.json (tables for the write-up)."""
import numpy as np, sys, os, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'); R = os.path.join(S, 'results')
def load(p):
    z = np.load(p, allow_pickle=True); return json.loads(str(z['meta'])), z['results'][0]
def metrics(meta, res, devres=None, fa=0.01):
    cmds = meta['cmds']; k = len(cmds); out = {}
    for m in [x for x in res if not x.startswith('_')]:
        fixed = float(np.median([fs.threshold_for_fa(devres[m][s][1][fs.query_sets(devres['_split'][s])[1]['dev_neg']], fa) for s in devres[m]])) if devres and m in devres else None
        pol = {'per-draw': [], 'fixed': [], 'oracle': []}; closed = []; roc = []
        for s in meta['seeds']:
            pred, score = res[m][s]; sp = res['_split'][s]; sl = fs.query_sets(sp)[1]
            ok = pred[sl['test_pos']] == sp['test_lab']; closed.append(ok.mean()); roc.append(fs.roc_stats(ok, score[sl['test_pos']], score[sl['test_neg']]))
            thrs = {'per-draw': fs.threshold_for_fa(score[sl['dev_neg']], fa), 'oracle': fs.threshold_for_fa(score[sl['test_neg']], fa)}
            if fixed is not None: thrs['fixed'] = fixed
            for name, thr in thrs.items():
                ap = score[sl['test_pos']] > thr; an = score[sl['test_neg']] > thr
                pol[name].append(dict(rec=[float((ap & ok)[sp['test_lab'] == c].mean()) for c in range(k)], fa_k=int(an.sum()), fa_n=len(an), pk=int((ap & ok).sum()), pn=len(ap)))
        o = dict(closed=float(np.mean(closed)), closed_sd=float(np.std(closed)), AUC=float(np.mean([r['AUC'] for r in roc])), EER=float(np.mean([r['EER'] for r in roc])),
                 oracle5=float(np.mean([r['rec@5%'] for r in roc])), oracle10=float(np.mean([r['rec@10%'] for r in roc])))
        for name, rr in pol.items():
            if not rr: continue
            rec = np.array([r['rec'] for r in rr]); fk = sum(r['fa_k'] for r in rr); fn = sum(r['fa_n'] for r in rr); pk = sum(r['pk'] for r in rr); pn = sum(r['pn'] for r in rr)
            o[name] = dict(rec_cmd=rec.mean(0).tolist(), rec_cmd_sd=rec.std(0).tolist(), rec=float(rec.mean()), rec_sd=float(rec.mean(1).std()), rec_min_cmd=float(rec.mean(0).min()),
                           pk=pk, pn=pn, rec_w=fs.wilson(pk, pn), fa=fk / fn, fa_sd=float(np.std([r['fa_k'] / r['fa_n'] for r in rr])), fk=fk, fn=fn, fa_w=fs.wilson(fk, fn), thr=fixed if name == 'fixed' else None)
        out[m] = o
    return out
lines = []; J = {}
def P(s=''): lines.append(s); print(s)
def table(title, meta, M):
    cmds = meta['cmds']; P('\n### %s   (commands %s; test seeds %d-%d, %d draws; %d enrolment recordings per command)' % (title, '/'.join(cmds), meta['seeds'][0], meta['seeds'][-1], len(meta['seeds']), meta['n_enrol']))
    P('%-16s %8s %6s %6s | %-34s %7s %7s | %-28s %-14s | %-26s' % ('method', 'closed', 'AUC', 'EER', 'per-draw-thr recall per cmd', 'mean', 'minCmd', 'per-draw test FA [Wilson95]', 'fixed-thr rec', 'fixed-thr FA [Wilson95]'))
    for m, o in M.items():
        pd = o['per-draw']; fx = o.get('fixed'); rc = ' '.join('%s %.2f±%.2f' % (c[:4], r, sd) for c, r, sd in zip(cmds, pd['rec_cmd'], pd['rec_cmd_sd']))
        P('%-16s %5.1f%%   %.3f  %.3f | %-34s %5.1f%%  %5.1f%% | %5.2f%%±%.2f [%.2f,%.2f] %d/%d | %-14s | %s' % (
            m, 100 * o['closed'], o['AUC'], o['EER'], rc, 100 * pd['rec'], 100 * pd['rec_min_cmd'], 100 * pd['fa'], 100 * pd['fa_sd'], 100 * pd['fa_w'][0], 100 * pd['fa_w'][1], pd['fk'], pd['fn'],
            ('%5.1f%% (min %4.1f%%)' % (100 * fx['rec'], 100 * fx['rec_min_cmd'])) if fx else 'n/a', ('%5.2f%% [%.2f,%.2f] thr=%.4g' % (100 * fx['fa'], 100 * fx['fa_w'][0], 100 * fx['fa_w'][1], fx['thr'])) if fx else 'n/a'))
P('# Few-shot spoken-command recognition on mini_speech_commands (speaker-independent): summary')
P('Enrolment = 5 recordings per command from random speakers; all dev/test recordings come from OTHER speakers (harder than the challenge\'s enrolled-speaker setting).')
P('Per draw: 100 fresh test recordings per command, 1000 dev + 1000 test unfamiliar recordings (200 per other word).  Threshold policy: accept if score > thr;')
P('per-draw thr = the value that admits <=1% of that draw\'s dev negatives; fixed thr = median per-draw dev threshold over SEPARATE dev seeds (101-110), frozen before testing.')
P('Recall = accepted AND correct command.  Wilson 95% intervals are on counts pooled over draws (draws share recordings, so they are optimistic; the ±sd across draws is also given).')
for tri in ['yes_no_stop', 'up_down_go', 'yes_no_stop_go']:
    tp = os.path.join(R, 'full_%s_test.npz' % tri); dp = os.path.join(R, 'full_%s_dev.npz' % tri)
    if not os.path.exists(tp): continue
    meta, res = load(tp); dev = load(dp)[1] if os.path.exists(dp) else None; M = metrics(meta, res, dev); J['full_' + tri] = dict(meta=meta, metrics=M); table('MAIN RESULT', meta, M)
    P('   MLP settings: H=%d hidden, lr=%g, epochs plain %d / aug %d / aug+neg %d, %d augmented copies per example; state bytes %s' % (meta['H'], meta['lr'], meta['E_plain'], meta['E_aug'], meta['E_augneg'], meta['aug'], json.dumps(meta['sizes'])))
cp = os.path.join(R, 'control_shuffled_yes_no_stop.npz')
if os.path.exists(cp):
    meta, res = load(cp); M = metrics(meta, res); J['control_shuffled'] = dict(meta=meta, metrics=M); table('CONTROL: example-level shuffled enrolment labels (chance closed-set = 33%)', meta, M)
for n in [10, 20, 50]:
    p = os.path.join(R, 'enrol%d_yes_no_stop_test.npz' % n)
    if os.path.exists(p): meta, res = load(p); M = metrics(meta, res); J['enrol%d' % n] = dict(meta=meta, metrics=M); table('ENROLMENT-SIZE SWEEP: %d recordings per command (templates only)' % n, meta, M)
p = os.path.join(R, 'enrol20mlp_yes_no_stop_test.npz')
if os.path.exists(p): meta, res = load(p); M = metrics(meta, res); J['enrol20mlp'] = dict(meta=meta, metrics=M); table('ENROLMENT-SIZE SWEEP: 20 recordings per command, all methods (MLP aug x8)', meta, M)
# ---- byte accounting ----
P('\n### STATE / CODE BYTES (feature vector 144 float32 = 12 segments x 12 MFCC; DTW template 61 frames x 16 bands)')
P('%-44s %10s %10s   %s' % ('item', '3 cmds', '4 cmds', 'note'))
def mlp_bytes(NI, NH, NO): return 8 + 8 * NI + 2 * (NH * (NI + 1) + NO * (NH + 1))
rows = [('uai32 executable (as shipped)', 9188, 9188, 'trainer + inference, dynamic ELF'),
        ('C front end: log-mel+MFCC+pooling (.text)', 2006, 2006, 'frontend.c built with the uai32 flags; standalone ELF 4,680 B'),
        ('C DTW (.text)', 546, 546, 'dtw.c, same flags'),
        ('A prototypes, float32 (k x 144 x 4)', 3 * 144 * 4, 4 * 144 * 4, '+ 1 threshold'),
        ('A prototypes, bfloat16', 3 * 144 * 2, 4 * 144 * 2, ''),
        ('A 1-NN: all enrolment vectors float32 (5k x 144 x 4)', 15 * 144 * 4, 20 * 144 * 4, 'also what re-training the MLP for a 4th command needs if raw audio is not kept'),
        ('B DTW templates float32 (5k x 61 x 16 x 4)', 15 * 61 * 16 * 4, 20 * 61 * 16 * 4, 'OVER the 32,768 B budget even alone'),
        ('B DTW templates uint8 (5k x 61 x 16)', 15 * 61 * 16, 20 * 61 * 16, 'e.g. 0.05 steps of the CMVN value, clipped to +-6'),
        ('B DTW templates uint8, 48-frame crop', 15 * 48 * 16, 20 * 48 * 16, 'templates cropped like the pooled vector'),
        ('C uai32 model, 144-16-k (k cmds, no unknown)', mlp_bytes(144, 16, 3), mlp_bytes(144, 16, 4), '8 + 8*144 + 2*(16*145 + k*17)'),
        ('C uai32 model, 144-16-(k+1) (with unknown class)', mlp_bytes(144, 16, 4), mlp_bytes(144, 16, 5), 'the only variant whose rejection score was calibrated'),
        ('C uai32 model, 144-32-(k+1)', mlp_bytes(144, 32, 4), mlp_bytes(144, 32, 5), ''),
        ('TOTAL C: uai32 + front end ELF + model 144-16-(k+1)', 9188 + 4680 + mlp_bytes(144, 16, 4), 9188 + 4680 + mlp_bytes(144, 16, 5), 'front end as a separate ELF; merged into uai32.c it would add ~2-2.5 KB instead of 4,680'),
        ('TOTAL B: front end+DTW ELF + uint8 templates', 4680 + 800 + 15 * 61 * 16, 4680 + 800 + 20 * 61 * 16, 'no trainer needed; 4th command = 5 more templates'),
        ('TOTAL A: front end ELF + float32 prototypes', 4680 + 3 * 144 * 4, 4680 + 4 * 144 * 4, 'smallest; 4th command = one more mean')]
for name, b3, b4, note in rows: P('%-44s %10s %10s   %s' % (name, format(b3, ','), format(b4, ','), note))
J['bytes'] = rows
open(os.path.join(R, 'summary.txt'), 'w').write('\n'.join(lines) + '\n'); json.dump(J, open(os.path.join(R, 'summary.json'), 'w'), indent=1, default=str)
print('\nwrote', os.path.join(R, 'summary.txt'))
