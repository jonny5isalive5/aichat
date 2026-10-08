/* DTW nearest-template distance: steps (1,0),(0,1),(1,1), Euclidean local cost, normalised by (lq+lt).
   Q: nq x T x NB, Tm: nt x T x NB (zero padded), lengths lq/lt.  out: nq x nt. */
#include <math.h>
#include <stdlib.h>
#include <string.h>
void dtw_many(const float *Q, const int *lq, int nq, const float *Tm, const int *lt, int nt, int T, int NB, float *out) {
    float *D = malloc(sizeof(float) * (T + 1) * (T + 1));
    for (int q = 0; q < nq; q++) for (int t = 0; t < nt; t++) {
        int n = lq[q], m = lt[t]; const float *a = Q + (size_t)q * T * NB, *b = Tm + (size_t)t * T * NB;
        for (int i = 0; i <= n; i++) for (int j = 0; j <= m; j++) D[i * (T + 1) + j] = INFINITY;
        D[0] = 0;
        for (int i = 1; i <= n; i++) for (int j = 1; j <= m; j++) {
            float c = 0; for (int k = 0; k < NB; k++) { float d = a[(i - 1) * NB + k] - b[(j - 1) * NB + k]; c += d * d; }
            float u = D[(i - 1) * (T + 1) + j], l = D[i * (T + 1) + j - 1], dg = D[(i - 1) * (T + 1) + j - 1];
            float best = u < l ? u : l; if (dg < best) best = dg;
            D[i * (T + 1) + j] = sqrtf(c) + best;
        }
        out[q * nt + t] = D[n * (T + 1) + m] / (n + m);
    }
    free(D);
}
