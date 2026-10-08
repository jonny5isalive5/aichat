import numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs, features as F, dtw_c
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
data = fs.Data(os.path.join(S, 'cache'))
cmds = ('yes', 'no', 'stop'); seeds = [901, 902, 903]; k = 3

def roc_stats(pos_ok, pos_s, neg_s):
    # pos_ok: whether the predicted class is right; recall at FA levels on *these* negatives (oracle), AUC, EER
    out = {}
    for fa in [0.01, 0.05, 0.10, 0.20]:
        thr = fs.threshold_for_fa(neg_s, fa); out['rec@%d%%' % int(fa * 100)] = ((pos_s > thr) & pos_ok).mean()
    allsc = np.concatenate([pos_s, neg_s]); lab = np.concatenate([np.ones(len(pos_s)), np.zeros(len(neg_s))])
    order = np.argsort(-allsc); lab = lab[order]; tp = np.cumsum(lab) / lab.sum(); fp = np.cumsum(1 - lab) / (1 - lab).sum()
    out['AUC'] = np.trapezoid(tp, fp); out['EER'] = fp[np.argmin(np.abs(fp - (1 - tp)))]
    return out

def show(name, sp, sl, pred, score):
    pos_ok = pred[sl['test_pos']] == sp['test_lab']; st = roc_stats(pos_ok, score[sl['test_pos']], score[sl['test_neg']])
    thr = fs.threshold_for_fa(score[sl['dev_neg']]); acc_w = (score[sl['test_neg']] > thr)
    perw = {w: round(float(acc_w[sp['test_negw'] == w].mean()), 3) for w in np.unique(sp['test_negw'])}
    print('%-34s acc %.3f  ' % (name, pos_ok.mean()) + '  '.join('%s %.3f' % (a, b) for a, b in st.items()), ' FA by word', perw, flush=True)

for sp in [fs.split(data, cmds, s) for s in seeds]:
    qidx, sl = fs.query_sets(sp); print('--- seed', sp['seed'])
    for norm, pm in [('peak', 'center'), ('cmn', 'center')]:
        Xe = fs.vectors(data.LM[sp['enrol_idx']], norm, pm); Xq = fs.vectors(data.LM[qidx], norm, pm); M = fs.proto_fit(Xe, sp['enrol_lab'], k)
        for metric in ['cos', 'cos_margin']:
            pred, score = fs.proto_score(M, Xq, metric); show('proto %s %s %s' % (norm, pm, metric), sp, sl, pred, score)
        # nearest-neighbour (all 15 enrolment vectors) cosine
        Qn = Xq / np.linalg.norm(Xq, axis=1, keepdims=True); En = Xe / np.linalg.norm(Xe, axis=1, keepdims=True); sim = Qn @ En.T
        cls = np.stack([sim[:, sp['enrol_lab'] == c].max(1) for c in range(k)], 1); show('1-NN cos %s %s' % (norm, pm), sp, sl, cls.argmax(1), cls.max(1))
    Te, lt = fs.trim_sequences(F.normalise(data.LM[sp['enrol_idx']], 'cmn'), 'full'); Q, lq = fs.trim_sequences(F.normalise(data.LM[qidx], 'cmn'), 'full')
    d = dtw_c.dtw_dist(Q, lq, Te, lt); cls = np.stack([d[:, sp['enrol_lab'] == c].min(1) for c in range(k)], 1); srt = np.sort(cls, 1)
    show('dtw cmn full min', sp, sl, cls.argmin(1), -srt[:, 0])
    show('dtw cmn full margin', sp, sl, cls.argmin(1), srt[:, 1] - srt[:, 0])
    show('dtw cmn full ratio', sp, sl, cls.argmin(1), srt[:, 1] / srt[:, 0])
    # class-mean of distances to all 5 templates instead of min
    clsm = np.stack([d[:, sp['enrol_lab'] == c].mean(1) for c in range(k)], 1); srtm = np.sort(clsm, 1)
    show('dtw cmn full mean5', sp, sl, clsm.argmin(1), -srtm[:, 0])
    show('dtw cmn full mean5 ratio', sp, sl, clsm.argmin(1), srtm[:, 1] / srtm[:, 0])
