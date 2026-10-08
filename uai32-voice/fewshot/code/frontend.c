/* frontend.c -- C re-implementation of the pilot feature recipe, to measure code size and check the numpy version.
 *   frontend vec  < raw_int16_16k_mono   -> one text row of 144 pooled MFCC values (uai32 input format, label 0)
 *   frontend seq  < raw_int16_16k_mono   -> 61 rows x 16 CMVN log-mel values (DTW frame features)
 * Recipe: 1 s zero-padded, pre-emphasis 0.97, 512-pt periodic Hann frames hop 256 (61 frames), power spectrum,
 * 16 triangular HTK-mel filters 100..7600 Hz, ln(E+1e-3); DCT-II c1..c12; energy-centred 48-frame crop; 12 segment means. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#define SR 16000
#define N 512
#define HOP 256
#define T 61
#define NB 16
#define NC 12
#define L 48
#define NSEG 12
static float lm[T][NB], e[T];
static void fft(float *re, float *im, int n) {               /* iterative radix-2 complex FFT */
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1; for (; j & bit; bit >>= 1) j ^= bit; j ^= bit;
        if (i < j) { float t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    for (int len = 2; len <= n; len <<= 1) {
        float ang = -2 * (float)M_PI / len, wr = cosf(ang), wi = sinf(ang);
        for (int i = 0; i < n; i += len) {
            float cr = 1, ci = 0;
            for (int j = 0; j < len / 2; j++) {
                int a = i + j, b = a + len / 2; float xr = re[b] * cr - im[b] * ci, xi = re[b] * ci + im[b] * cr;
                re[b] = re[a] - xr; im[b] = im[a] - xi; re[a] += xr; im[a] += xi;
                float t = cr * wr - ci * wi; ci = cr * wi + ci * wr; cr = t;
            }
        }
    }
}
static float melf(float f) { return 2595.0f * log10f(1 + f / 700.0f); }
static void logmel(const float *x) {
    static float fb[NB][N / 2 + 1]; static int init;
    if (!init) {                                                 /* triangular filters, unit peak */
        int bins[NB + 2]; float m0 = melf(100), m1 = melf(7600);
        for (int b = 0; b < NB + 2; b++) bins[b] = (int)floorf((N + 1) * (700.0f * (powf(10, (m0 + (m1 - m0) * b / (NB + 1)) / 2595.0f) - 1)) / SR);
        for (int b = 0; b < NB; b++) {
            for (int k = bins[b]; k < bins[b + 1]; k++) fb[b][k] = (float)(k - bins[b]) / (bins[b + 1] - bins[b] > 0 ? bins[b + 1] - bins[b] : 1);
            for (int k = bins[b + 1]; k < bins[b + 2]; k++) fb[b][k] = (float)(bins[b + 2] - k) / (bins[b + 2] - bins[b + 1] > 0 ? bins[b + 2] - bins[b + 1] : 1);
        }
        init = 1;
    }
    float re[N], im[N];
    for (int t = 0; t < T; t++) {
        for (int n = 0; n < N; n++) {
            int i = t * HOP + n; float y = x[i] - (i ? 0.97f * x[i - 1] : 0);
            re[n] = y * (0.5f - 0.5f * cosf(2 * (float)M_PI * n / N)); im[n] = 0;
        }
        fft(re, im, N);
        for (int b = 0; b < NB; b++) {
            float s = 0; for (int k = 0; k <= N / 2; k++) if (fb[b][k] > 0) s += fb[b][k] * (re[k] * re[k] + im[k] * im[k]);
            lm[t][b] = logf(s + 1e-3f);
        }
    }
    for (int t = 0; t < T; t++) {                                 /* 5-frame box-smoothed mean log energy, 'same' padding */
        float s = 0; for (int b = 0; b < NB; b++) s += lm[t][b]; e[t] = s / NB;
    }
    float es[T]; for (int t = 0; t < T; t++) { float s = 0; for (int d = -2; d <= 2; d++) if (t + d >= 0 && t + d < T) s += e[t + d]; es[t] = s / 5; }
    memcpy(e, es, sizeof e);
}
int main(int argc, char **argv) {
    static short pcm[SR]; static float x[SR];
    int n = fread(pcm, 2, SR, stdin); if (n < 0) n = 0;
    for (int i = 0; i < n; i++) x[i] = pcm[i] / 32768.0f;
    logmel(x);
    if (argc > 1 && !strcmp(argv[1], "seq")) {                   /* per-band mean/variance normalised frames for DTW */
        for (int b = 0; b < NB; b++) {
            float m = 0, v = 0; for (int t = 0; t < T; t++) m += lm[t][b]; m /= T;
            for (int t = 0; t < T; t++) v += (lm[t][b] - m) * (lm[t][b] - m); v = sqrtf(v / T) + 1e-3f;
            for (int t = 0; t < T; t++) lm[t][b] = (lm[t][b] - m) / v;
        }
        for (int t = 0; t < T; t++) { for (int b = 0; b < NB; b++) printf("%.5g ", lm[t][b]); printf("\n"); }
        return 0;
    }
    float emin = 1e30f; for (int t = 0; t < T; t++) if (e[t] < emin) emin = e[t];
    int best = 0; float bs = -1e30f;                              /* 48-frame window with the most energy */
    for (int c = 0; c + L <= T; c++) { float s = 0; for (int t = c; t < c + L; t++) s += e[t] - emin; if (s > bs) { bs = s; best = c; } }
    for (int s = 0; s < NSEG; s++) for (int c = 1; c <= NC; c++) {  /* DCT-II c1..c12 of each frame, averaged over 4 frames */
        float acc = 0;
        for (int t = best + s * (L / NSEG); t < best + (s + 1) * (L / NSEG); t++)
            for (int b = 0; b < NB; b++) acc += lm[t][b] * cosf((float)M_PI * c * (b + 0.5f) / NB) * sqrtf(2.0f / NB);
        printf("%.5g ", acc / (L / NSEG));
    }
    printf("0\n");
    return 0;
}
