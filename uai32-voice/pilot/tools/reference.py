"""reference.py CLIPDIR BENCHCODE LIBDTW OUTDIR -- the few-shot benchmark's own pipeline (features.py, feats2.py and the
C DTW of dtw.c compiled as LIBDTW) run on the pilot clips, as the reference the two apps are compared with.
CLIPDIR holds clips.txt and raw/ from select_clips.py.  Writes into OUTDIR:
  names.txt            clip names in manifest order (role_word_file)
  logmel.npy           (n, 61, 16) float32 log-mel as features.logmel computes it
  vectors.npy/.txt     (n, 144) float32 MLP vectors (fewshot.pooled_vectors defaults: DCT c1..c12, energy-centred 48-frame
                       crop, 12 segment means), and the same rows printed with %.5g as the benchmark wrote them
  crop_start.txt       the start frame of the energy-centred crop per clip
  frames_cmvn.npy      (n, 61, 16) float32 DTW frames (feats2.frames(LM, 'logmel_cmvn'))
  state_expected.bin   the dtwapp STATE file computed in numpy from the enrolment clips (header + 977-byte records)
  ref_dtw.txt          per query: decisions and distances with float32 templates and with uint8-quantised templates
Run with python3 -I."""
import sys, os, ctypes, struct, numpy as np
clipdir, bench, libdtw, out = sys.argv[1:5]
sys.path.insert(0, bench); import features as F, feats2 as f2
os.makedirs(out, exist_ok=True)
rows = [l.split() for l in open(os.path.join(clipdir, 'clips.txt')) if not l.startswith('#')]
names = ['%s_%s_%s' % (r[0], r[1], os.path.basename(r[3])[:-4]) for r in rows]
roles = np.array([r[0] for r in rows]); labels = np.array([int(r[2]) for r in rows])
W = np.zeros((len(rows), F.SR), np.int16)
for i, n in enumerate(names):
    x = np.fromfile(os.path.join(clipdir, 'raw', n + '.raw'), '<i2'); m = min(len(x), F.SR); W[i, :m] = x[:m]
LM = F.logmel(W)                                                   # (n, 61, 16) float32
X = (LM @ f2.DCT.T)[:, :, 1:13].astype(np.float32); e = f2.energy(LM); V = f2.pool_center(X, e)
crop = [int(np.convolve(e[b] - e[b].min(), np.ones(48), mode='valid').argmax()) for b in range(len(rows))]
FR = f2.frames(LM, 'logmel_cmvn')
open(os.path.join(out, 'names.txt'), 'w').write('\n'.join(names) + '\n')
np.save(os.path.join(out, 'logmel.npy'), LM); np.save(os.path.join(out, 'vectors.npy'), V); np.save(os.path.join(out, 'frames_cmvn.npy'), FR)
open(os.path.join(out, 'crop_start.txt'), 'w').write('\n'.join('%s %d' % (n, c) for n, c in zip(names, crop)) + '\n')
with open(os.path.join(out, 'vectors.txt'), 'w') as f:
    for i in range(len(rows)): f.write(' '.join('%.5g' % v for v in V[i]) + ' %d\n' % max(labels[i], 0))
# ---- dtwapp state file as numpy computes it (benchmark quantisation: clip(round(X/0.05), -127, 128), half-to-even) ----
en = np.where(roles == 'enrol')[0]; Te = FR[en]; ye = labels[en]
qi = np.clip(np.round(Te / 0.05), -127, 128).astype(np.int16); Tq = qi.astype(np.float32) * 0.05
u8 = (qi + 127).astype(np.uint8)
with open(os.path.join(out, 'state_expected.bin'), 'wb') as f:
    f.write(struct.pack('<HHHH', 0xA1D7, 61, 16, len(en)))
    for j in range(len(en)): f.write(bytes([int(ye[j])]) + u8[j].tobytes())
# ---- the benchmark's C DTW (dtw.c) on float32 and on quantised templates ----
lib = ctypes.CDLL(libdtw); P = np.ctypeslib.ndpointer
lib.dtw_many.argtypes = [P(np.float32, flags='C'), P(np.int32, flags='C'), ctypes.c_int, P(np.float32, flags='C'), P(np.int32, flags='C'),
                         ctypes.c_int, ctypes.c_int, ctypes.c_int, P(np.float32, flags='C')]
qs = np.where(roles != 'enrol')[0]; Q = np.ascontiguousarray(FR[qs]); k = ye.max() + 1
def run(Tm):
    o = np.zeros((len(qs), len(en)), np.float32)
    lib.dtw_many(Q, np.full(len(qs), 61, np.int32), len(qs), np.ascontiguousarray(Tm), np.full(len(en), 61, np.int32), len(en), 61, 16, o)
    dcls = np.stack([o[:, ye == c].min(1) for c in range(k)], 1); pred, margin = f2.calibrate(dcls, o, 'margin'); srt = np.sort(dcls, 1)
    return pred, srt[:, 0], srt[:, 1], margin, dcls
A, B = run(Te), run(Tq)
with open(os.path.join(out, 'ref_dtw.txt'), 'w') as f:
    f.write('# name true_label | float32 templates: pred best runnerup margin | uint8 templates: pred best runnerup margin | class mins float32 | class mins uint8\n')
    for j, i in enumerate(qs):
        f.write('%s %d | %d %.6f %.6f %.6f | %d %.6f %.6f %.6f | %s | %s\n' % (names[i], labels[i], A[0][j], A[1][j], A[2][j], A[3][j],
                B[0][j], B[1][j], B[2][j], B[3][j], ' '.join('%.6f' % v for v in A[4][j]), ' '.join('%.6f' % v for v in B[4][j])))
pos = labels[qs] >= 0
print('reference: %d clips, %d templates, %d queries (%d in-vocabulary, %d unfamiliar)' % (len(rows), len(en), len(qs), pos.sum(), (~pos).sum()))
print('closed-set accuracy on the in-vocabulary queries: float32 templates %d/%d, uint8 templates %d/%d; decisions agree on %d/%d queries, max |distance diff| %.6f'
      % ((A[0][pos] == labels[qs][pos]).sum(), pos.sum(), (B[0][pos] == labels[qs][pos]).sum(), pos.sum(), (A[0] == B[0]).sum(), len(qs), np.abs(A[4] - B[4]).max()))
