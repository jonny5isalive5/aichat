"""compare.py REFDIR WORKDIR VALDIR -- compare the applications' outputs with the benchmark reference (reference.py).
Reads  WORKDIR/fe_Os/<name>.txt, fe_O0/<name>.txt   front-end harness output (bin line, then 61 rows of 16, %.9g)
       WORKDIR/feat/<name>.txt                      netapp feat rows (144 values [+ label])
       VALDIR/pilot.state                           dtwapp state after enrolling the 20 enrolment clips
       VALDIR/dtwapp_scores.txt                     'name best best_dist runnerup_dist margin' per query
       VALDIR/netapp_predict{4,5}.txt, WORKDIR/uai32_predict{4,5}.txt   predict output of netapp and of the frozen uai32
Prints the agreement statistics.  Run with python3 -I."""
import sys, os, numpy as np
ref, work, val = sys.argv[1:4]
names = open(os.path.join(ref, 'names.txt')).read().split()
LM = np.load(os.path.join(ref, 'logmel.npy')); V = np.load(os.path.join(ref, 'vectors.npy'))
BINS = [3, 6, 11, 16, 22, 28, 36, 44, 54, 66, 79, 94, 111, 131, 153, 179, 209, 243]
def load_fe(d):
    out = np.zeros_like(LM); ok = 0
    for i, n in enumerate(names):
        t = open(os.path.join(work, d, n + '.txt')).read().split('\n')
        ok += [int(v) for v in t[0].split()] == BINS
        out[i] = np.array([[float(v) for v in r.split()] for r in t[1:62]], np.float32)
    return out, ok
for d in ('fe_Os', 'fe_O0'):
    A, ok = load_fe(d)
    print('%s: filter bins equal to the benchmark on %d/%d clips; log-mel max |diff| vs features.py %.3g (mean %.3g); worst clip %s'
          % (d, ok, len(names), np.abs(A - LM).max(), np.abs(A - LM).mean(), names[int(np.abs(A - LM).reshape(len(names), -1).max(1).argmax())]))
A, _ = load_fe('fe_Os'); B, _ = load_fe('fe_O0'); print('fe_Os vs fe_O0 max |diff| %.3g' % np.abs(A - B).max())
# ---- netapp feat vectors ----
F = np.zeros_like(V); tok_same = tok_all = 0; reftxt = [l.split()[:144] for l in open(os.path.join(ref, 'vectors.txt'))]
for i, n in enumerate(names):
    t = open(os.path.join(work, 'feat', n + '.txt')).read().split()[:144]; F[i] = [float(v) for v in t]
    tok_same += sum(a == b for a, b in zip(t, reftxt[i])); tok_all += 144
d = np.abs(F - V); per = d.max(1)
print('netapp feat: 144 values on %d clips; max |diff| vs the benchmark vectors %.3g, mean %.3g; clips with max |diff| > 0.01: %d; %%.5g tokens identical to the benchmark text rows: %d/%d (%.1f%%)'
      % (len(names), d.max(), d.mean(), (per > 0.01).sum(), tok_same, tok_all, 100.0 * tok_same / tok_all))
if (per > 0.01).any(): print('  clips above 0.01:', ', '.join('%s (%.3g)' % (names[i], per[i]) for i in np.where(per > 0.01)[0]))
# ---- dtwapp state bytes ----
exp = np.frombuffer(open(os.path.join(ref, 'state_expected.bin'), 'rb').read(), np.uint8)
got = np.frombuffer(open(os.path.join(val, 'pilot.state'), 'rb').read(), np.uint8)
print('dtwapp state: %d bytes (expected %d); header %s; label bytes %s' % (len(got), len(exp), 'equal' if (got[:8] == exp[:8]).all() else 'DIFFERENT',
      'equal' if all(got[8 + 977 * j] == exp[8 + 977 * j] for j in range(20)) else 'DIFFERENT'))
E = exp[8:].reshape(20, 977)[:, 1:].astype(int); G = got[8:].reshape(20, 977)[:, 1:].astype(int)
print('  template bytes: %d/%d identical to the numpy quantisation, %d differ by one step, %d by more (max |diff| %d steps of 0.05)'
      % ((E == G).sum(), E.size, (np.abs(E - G) == 1).sum(), (np.abs(E - G) > 1).sum(), np.abs(E - G).max()))
# ---- dtwapp decisions ----
R = {}
for l in open(os.path.join(ref, 'ref_dtw.txt')):
    if l.startswith('#'): continue
    p = l.split(' | '); h = p[0].split(); R[h[0]] = (int(h[1]), [float(v) for v in p[1].split()], [float(v) for v in p[2].split()])
S = {}
for l in open(os.path.join(val, 'dtwapp_scores.txt')):
    t = l.split(); S[t[0]] = [float(v) for v in t[1:]]
q = list(S); tl = np.array([R[n][0] for n in q]); a = np.array([R[n][1] for n in q]); b = np.array([R[n][2] for n in q]); s = np.array([S[n] for n in q])
pos = tl >= 0
print('dtwapp score on %d queries (%d in-vocabulary, %d unfamiliar):' % (len(q), pos.sum(), (~pos).sum()))
print('  decision agrees with the benchmark DTW on uint8 templates: %d/%d; on float32 templates: %d/%d; float32 vs uint8 (benchmark alone): %d/%d'
      % ((s[:, 0] == b[:, 0]).sum(), len(q), (s[:, 0] == a[:, 0]).sum(), len(q), (a[:, 0] == b[:, 0]).sum(), len(q)))
print('  vs uint8 reference: max |best_dist diff| %.6f, |runnerup diff| %.6f, |margin diff| %.6f' % tuple(np.abs(s[:, i] - b[:, i]).max() for i in (1, 2, 3)))
print('  vs float32 reference: max |best_dist diff| %.6f, |runnerup diff| %.6f, |margin diff| %.6f' % tuple(np.abs(s[:, i] - a[:, i]).max() for i in (1, 2, 3)))
print('  closed-set accuracy on in-vocabulary queries: dtwapp %d/%d, benchmark uint8 %d/%d, benchmark float32 %d/%d'
      % ((s[pos, 0] == tl[pos]).sum(), pos.sum(), (b[pos, 0] == tl[pos]).sum(), pos.sum(), (a[pos, 0] == tl[pos]).sum(), pos.sum()))
print('  margin (runnerup - best): in-vocabulary correct mean %.3f, in-vocabulary wrong mean %.3f, unfamiliar mean %.3f (information only: 60 speaker-independent clips)'
      % (s[pos & (s[:, 0] == tl), 3].mean(), s[pos & (s[:, 0] != tl), 3].mean() if (pos & (s[:, 0] != tl)).any() else float('nan'), s[~pos, 3].mean()))
# ---- netapp predict vs the frozen uai32 ----
for k in (4, 5):
    N = [l.split() for l in open(os.path.join(val, 'netapp_predict%d.txt' % k))]; U = [l.split() for l in open(os.path.join(work, 'uai32_predict%d.txt' % k))]
    cls = sum(n[0] == u[0] for n, u in zip(N, U)); pd = max(abs(float(x) - float(y)) for n, u in zip(N, U) for x, y in zip(n[1:1 + k], u[1:1 + k]))
    cons = []
    for n in N:
        p = np.array([float(v) for v in n[1:1 + k]]); srt = np.sort(p)
        if srt[-2] > 1e-5: cons.append(abs(float(n[1 + k]) - np.log(srt[-1] / srt[-2])))
    sat = sum(max(float(v) for v in u[1:1 + k]) >= 0.9995 for u in U); sat6 = sum(max(float(v) for v in n[1:1 + k]) >= 0.9999995 for n in N)
    print('netapp predict (NO=%d): class equal to the frozen uai32 on %d/%d rows; max |p(6 dp) - p(3 dp)| %.4f (<= 0.0005 + rounding);'
          ' |margin - ln(p_best/p_second)| max %.2e on %d rows; rows printing max prob 1.000 under uai32: %d, printing 1.000000 under netapp: %d'
          % (k, cls, len(N), pd, max(cons) if cons else 0, len(cons), sat, sat6))
