import numpy as np, sys, time
sys.path.insert(0, '.')
import fewshot as fs
def naive(a, b):
    n, m = len(a), len(b); D = np.full((n + 1, m + 1), np.inf); D[0, 0] = 0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            D[i, j] = np.linalg.norm(a[i - 1] - b[j - 1]) + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    return D[n, m] / (n + m)
rng = np.random.default_rng(0); T, NB = 61, 16
Q = rng.standard_normal((5, T, NB)).astype(np.float32); Tm = rng.standard_normal((4, T, NB)).astype(np.float32)
lq = np.array([61, 40, 25, 61, 10]); lt = np.array([61, 30, 61, 50])
for b in range(5):
    for t in range(4):
        Q[b, lq[b]:] = 0; Tm[t, lt[t]:] = 0
d = fs.dtw_dist(Q, lq, Tm, lt)
ref = np.array([[naive(Q[b, :lq[b]], Tm[t, :lt[t]]) for t in range(4)] for b in range(5)])
print('max abs err vs naive', np.abs(d - ref).max())
t0 = time.time(); fs.dtw_dist(rng.standard_normal((512, T, NB)).astype(np.float32), np.full(512, 61), Tm[:4].repeat(4, 0)[:15], np.full(15, 61)); print('512x15 DTW s', round(time.time() - t0, 2))
