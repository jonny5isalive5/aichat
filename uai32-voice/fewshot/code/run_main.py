"""Main experiment: for each seed, enrol 5 recordings per command, score dev/test positives and negatives with every
method, and save raw (pred, score) arrays so analysis can apply any threshold policy afterwards.
usage: python3 -I run_main.py CMDS SEEDS OUT.npz [--n_enrol 5] [--mlp all|none]
  CMDS  comma list, e.g. yes,no,stop ; SEEDS like 1-20 or 101-110"""
import numpy as np, sys, os, time, argparse, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs, features as F, dtw_c
S = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ap = argparse.ArgumentParser(); ap.add_argument('cmds'); ap.add_argument('seeds'); ap.add_argument('out')
ap.add_argument('--n_enrol', type=int, default=5); ap.add_argument('--mlp', default='all'); ap.add_argument('--aug', type=int, default=30)
ap.add_argument('--H', type=int, default=16); ap.add_argument('--E_plain', type=int, default=300); ap.add_argument('--E_aug', type=int, default=5)
ap.add_argument('--lr', type=float, default=0.01); ap.add_argument('--E_augneg', type=int, default=20)
ap.add_argument('--shuffle_labels', action='store_true', help='control: permute the enrolment labels at example level before every method')
a = ap.parse_args()
cmds = tuple(a.cmds.split(',')); k = len(cmds); lo, hi = map(int, a.seeds.split('-')); seeds = list(range(lo, hi + 1))
data = fs.Data(os.path.join(S, 'cache')); work = os.path.join(S, 'work', 'main_' + '_'.join(cmds) + '_%d' % lo)
results = {}; sizes = {}; logs = {}

def store(seed, name, pred, score):
    results.setdefault(name, {})[seed] = (pred.astype(np.int16), score.astype(np.float32))

t_all = time.time()
for seed in seeds:
    t0 = time.time(); sp = fs.split(data, cmds, seed, n_enrol=a.n_enrol); qidx, sl = fs.query_sets(sp)
    if a.shuffle_labels: sp['enrol_lab'] = np.random.default_rng(seed + 999).permutation(sp['enrol_lab'])
    results.setdefault('_split', {})[seed] = sp
    LMe, LMq = data.LM[sp['enrol_idx']], data.LM[qidx]
    # ---- A: prototypes on pooled MFCC vectors (144 values) ----
    Ve, Vq = fs.pooled_vectors(LMe), fs.pooled_vectors(LMq); M = fs.proto_fit(Ve, sp['enrol_lab'], k)
    Mn = M / np.linalg.norm(M, axis=1, keepdims=True); Qn = Vq / np.linalg.norm(Vq, axis=1, keepdims=True); dcls = 1 - Qn @ Mn.T
    for c in ['min', 'ratio']:
        pred, score = fs.f2.calibrate(dcls, None, c); store(seed, 'A_proto_cos_' + c, pred, score)
    # 1-NN on the 15 enrolment vectors (uses all enrolment vectors as state)
    En = Ve / np.linalg.norm(Ve, axis=1, keepdims=True); dnn = 1 - Qn @ En.T
    dcls_nn = np.stack([dnn[:, sp['enrol_lab'] == c].min(1) for c in range(k)], 1)
    pred, score = fs.f2.calibrate(dcls_nn, None, 'min'); store(seed, 'A_1nn_cos_min', pred, score)
    sizes['A_proto'] = int(k * Vq.shape[1] * 4); sizes['A_1nn'] = int(len(Ve) * Vq.shape[1] * 4)
    # ---- B: DTW on normalised log-mel frame sequences (61 x 16) ----
    Xe, Xq = fs.dtw_frames(LMe), fs.dtw_frames(LMq)
    d = dtw_c.dtw_dist(Xq, np.full(len(Xq), F.T), Xe, np.full(len(Xe), F.T))
    dcls = np.stack([d[:, sp['enrol_lab'] == c].min(1) for c in range(k)], 1)
    for c in ['min', 'margin']:
        pred, score = fs.f2.calibrate(dcls, d, c); store(seed, 'B_dtw_' + c, pred, score)
    sizes['B_dtw_float32'] = int(len(Xe) * F.T * F.NB * 4); sizes['B_dtw_uint8'] = int(len(Xe) * F.T * F.NB)
    # ---- C: uai32 on the same pooled vectors ----
    if a.mlp != 'none':
        rng = np.random.default_rng(seed + 7)
        Wa = fs.augment_waves(data.W[sp['enrol_idx']], rng, a.aug); Va = fs.pooled_vectors(F.logmel(Wa)); ya = np.repeat(sp['enrol_lab'], a.aug)
        nneg = (a.aug + 1) * len(Ve) // 2
        Wn = fs.synth_negative_waves(data.W[sp['enrol_idx']], sp['enrol_lab'], rng, nneg); Vn = fs.pooled_vectors(F.logmel(Wn))
        Vs = fs.synth_negative_vectors(np.concatenate([Ve, Va]), rng, nneg // 3, nseg=12, nb=12)
        Vneg = np.concatenate([Vn, Vs]); yneg = np.full(len(Vneg), k)
        nneg_plain = len(Ve)   # for the no-augmentation + negatives variant keep the class balance similar
        configs = {'C0_mlp_plain': (Ve, sp['enrol_lab'], a.E_plain),
                   'C1_mlp_aug': (np.concatenate([Ve, Va]), np.concatenate([sp['enrol_lab'], ya]), a.E_aug),
                   'C2_mlp_neg': (np.concatenate([Ve, Vneg[:nneg_plain]]), np.concatenate([sp['enrol_lab'], yneg[:nneg_plain]]), a.E_plain),
                   'C3_mlp_aug_neg': (np.concatenate([Ve, Va, Vneg]), np.concatenate([sp['enrol_lab'], ya, yneg]), a.E_augneg)}
        for name, (Xtr, ytr, E) in configs.items():
            pred, probs, size, log = fs.uai32_run(Xtr, ytr, Vq, a.H, E, a.lr, seed, work, tag=name)
            p, s = fs.mlp_score(pred, probs, k); store(seed, name, p, s); sizes[name] = size; logs.setdefault(name, []).append(log)
    print('seed %d done in %.0fs' % (seed, time.time() - t0), flush=True)

meta = dict(cmds=cmds, seeds=seeds, n_enrol=a.n_enrol, aug=a.aug, H=a.H, E_plain=a.E_plain, E_aug=a.E_aug, E_augneg=a.E_augneg, lr=a.lr, shuffle_labels=a.shuffle_labels, sizes=sizes,
            vec_dim=int(Vq.shape[1]), argv=sys.argv, logs={n: l[:3] for n, l in logs.items()})
np.savez_compressed(a.out, meta=json.dumps(meta, default=str), results=np.array([results], dtype=object), allow_pickle=True)
print('saved', a.out, 'total %.0fs' % (time.time() - t_all), json.dumps(sizes))
