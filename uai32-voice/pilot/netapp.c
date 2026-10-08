/* netapp.c -- Sentovara uAI-32 voice pilot, arm 2: uai32.c with the shared voice front-end merged in.
 * Differences from the frozen uai32.c (everything else, including the model format, is unchanged):
 *   netapp feat [LABEL] < clip      one second of raw 16 kHz signed 16-bit little-endian mono PCM -> one data row of
 *                                   144 values (the few-shot benchmark's MLP vector, see FRONTEND.md), then LABEL if given
 *   netapp predict MODEL < rows     prints the class, the probabilities with 6 decimals (uai32: 3) and then the logit
 *                                   margin = best logit - runner-up logit, so a rejection threshold is not limited by
 *                                   the saturation of 3-decimal probabilities (margin is inf for a one-class model)
 * The original uai32.c header follows.
 *
 * uai32.c -- Sentovara uAI-32: the smallest genuinely trainable neural network we could make.
 *
 * A one-hidden-layer multilayer perceptron (MLP) classifier, trained by plain stochastic
 * gradient descent with backpropagation (softmax output, cross-entropy loss).  Everything
 * the program learns lives in ONE array of floats (P) which is saved to and loaded from a
 * small file.  There are no rules, lookup tables or dataset-specific code anywhere.
 *
 *   uai32 train DATA MODEL [HIDDEN] [EPOCHS] [RATE] [SEED]   learn from DATA, save to MODEL
 *   uai32 test  DATA MODEL                                   accuracy + loss of MODEL on DATA
 *   uai32 predict MODEL  < rows                              print class + probabilities per row
 *
 * If MODEL already exists, `train` loads it and keeps training it (HIDDEN is then ignored,
 * pass anything; SEED still seeds the shuffle).  Delete the file to start from scratch.
 *
 * DATA format: one example per line, whitespace-separated numbers: the features, then the
 * integer class label (0,1,2,...).  The number of features is taken from the first line.
 * Blank lines and lines that do not start with a number are skipped.  `predict` reads rows
 * from stdin and ignores extra numeric columns after the features, so a labelled file can be piped in.
 *
 * MODEL format (all little-endian):  u16 magic 0xA132, u16 NI, u16 NH, u16 NO, then the
 * parameters in the order mean[NI], scale[NI], W1[NH][NI+1], W2[NO][NH+1] (last column = bias).
 * mean and scale are stored as exact float32; every weight as bfloat16 (the top 16 bits of
 * an IEEE-754 float, rounded to nearest even), which halves the file at no accuracy cost.
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <errno.h>
#include <float.h>
#include <limits.h>

/* ==== FRONT-END BEGIN: this block is textually identical in dtwapp.c and netapp.c (build.sh checks) ====
 * One second of raw 16 kHz signed 16-bit little-endian mono PCM on stdin -> lm[T * NB], the 61 x 16 log-mel matrix
 * of the few-shot benchmark recipe (features.py): pre-emphasis x[n] - 0.97 x[n-1], 512-sample periodic Hann frames
 * every 256 samples (61 frames), |FFT|^2, 16 triangular HTK-mel filters 100..7600 Hz with unit peak, ln(E + 1e-3).
 * Short input is zero-padded; a longer one is not read past the last frame.  Only one frame of samples is held at a
 * time, so the working set is the log-mel matrix, one FFT frame and 513 samples, not the whole second. */
#define SR  16000                   /* sample rate                                            */
#define FN  512                     /* frame length, 32 ms                                    */
#define HOP 256                     /* frame hop, 16 ms                                       */
#define T   61                      /* frames per clip: 1 + (SR - FN) / HOP                   */
#define NB  16                      /* mel bands                                              */
#define PI  3.14159265f
static void die(const char *m);
static short *buf;                  /* buf[0] = the sample before the frame (pre-emphasis), buf[1..FN] = the frame */
static float *re, *im, *lm;         /* FFT real and imaginary parts; lm[t * NB + b]           */
static int *bin, nread, eof;        /* NB + 2 filter edges as FFT bin numbers; samples read; stdin exhausted */

static void alloc_fe(void) {        /* one calloc, as uai32: FN + 1 shorts, 2 FN floats, T * NB floats, NB + 2 ints */
    float *m = calloc((FN + 2) / 2 + 2 * FN + T * NB + NB + 2, sizeof *m);
    if (!m) die("out of memory");
    buf = (short *)m; re = m + (FN + 2) / 2; im = re + FN; lm = im + FN; bin = (int *)(lm + T * NB);
}

static int sample(void) {           /* next sample from stdin; 0 once the input is exhausted  */
    int lo, hi;
    if (eof) return 0;
    if ((lo = getc(stdin)) < 0) { eof = 1; return 0; }
    if ((hi = getc(stdin)) < 0) die("odd number of bytes: not 16-bit PCM");
    nread++; lo |= hi << 8;
    return lo - ((lo & 0x8000) << 1);
}

static void fft(void) {             /* in-place radix-2 decimation-in-time complex FFT of length FN */
    int i, j, k, len;
    for (i = 1, j = 0; i < FN; i++) {                              /* bit-reversal permutation */
        for (k = FN >> 1; j & k; k >>= 1) j ^= k;
        j ^= k;
        if (i < j) { float t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    for (len = 2; len <= FN; len <<= 1) {
        float wr = cosf(2 * PI / len), wi = -sinf(2 * PI / len);   /* twiddle step e^(-2 pi i / len) */
        for (i = 0; i < FN; i += len) {
            float cr = 1, ci = 0;
            for (j = i; j < i + len / 2; j++) {
                int b = j + len / 2;
                float xr = re[b] * cr - im[b] * ci, xi = re[b] * ci + im[b] * cr, t = cr * wr - ci * wi;
                re[b] = re[j] - xr; im[b] = im[j] - xi; re[j] += xr; im[j] += xi;
                ci = cr * wi + ci * wr; cr = t;
            }
        }
    }
}

static void frame(int t) {          /* frame t of the input -> re (pre-emphasised, Hann-windowed), im = 0 */
    int n;
    if (t) memmove(buf, buf + HOP, (FN - HOP + 1) * sizeof *buf);  /* keep the last 257 samples    */
    for (n = t ? FN - HOP + 1 : 1; n <= FN; n++) buf[n] = sample();
    if (!t) {
        if (!nread) die("empty clip");
        if (buf[1] == 0x4952 && buf[2] == 0x4646) die("WAV input: give raw PCM");   /* "RIFF" */
    }
    for (n = 0; n < FN; n++) {
        re[n] = (buf[n + 1] - 0.97f * buf[n]) * (0.5f - 0.5f * cosf(2 * PI * n / FN)) * (1.0f / 32768); im[n] = 0;
    }
}

static void logmel(void) {          /* stdin -> lm; the mel scale is C ln(1 + f/700): the constant cancels in linspace */
    int t, b, k; float m0 = logf(1 + 100 / 700.f), m1 = logf(1 + 7600 / 700.f);
    for (b = 0; b < NB + 2; b++) bin[b] = (FN + 1) * 700 * (expf(m0 + (m1 - m0) * b / (NB + 1)) - 1) / SR;
    for (t = 0; t < T; t++) {
        frame(t); fft();
        for (b = 0; b < NB; b++) {                                     /* triangle rising on bin[b]..bin[b+1], falling to bin[b+2] */
            float s = 0;
            for (k = bin[b]; k < bin[b + 2]; k++) {
                float w = k < bin[b + 1] ? (float)(k - bin[b]) / (bin[b + 1] - bin[b]) : (float)(bin[b + 2] - k) / (bin[b + 2] - bin[b + 1]);
                s += w * (re[k] * re[k] + im[k] * im[k]);
            }
            lm[t * NB + b] = logf(s + 1e-3f);
        }
    }
}
/* ==== FRONT-END END ==== */

static int NI, NH, NO;                 /* inputs, hidden units, outputs (classes)       */
static float *P, *mean, *scale, *W1, *W2;  /* all learned parameters live in P           */
static float *xn, *hid, *z, *out, *dh, lse;  /* normalised input, hidden, logits, softmax, hidden grad, log-sum-exp */
static unsigned rng = 1;               /* xorshift32 state; SEED sets it                */

static void die(const char *m) { fprintf(stderr, "netapp: %s\n", m); exit(1); }

static unsigned integer(const char *s, unsigned max) {
    char *e; unsigned long v; errno = 0; v = strtoul(s, &e, 10);
    if (*s < '0' || *s > '9' || *e || errno || v > max) die("invalid integer argument");
    return (unsigned)v;
}

static float rate(const char *s) {
    char *e; float v; errno = 0; v = strtof(s, &e);
    if (e == s || *e || errno || !isfinite(v) || v <= 0 || v > 1e6f) die("invalid RATE");
    return v;
}

static float frand(void) {             /* uniform in [-1, 1) */
    rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
    return (int)rng * (1.0f / 2147483648.0f);
}

static int nparams(void) { return 2 * NI + NH * (NI + 1) + NO * (NH + 1); }

static void valid_params(void) {
    int i;
    for (i = 0; i < nparams(); i++)
        if (!isfinite(P[i]) || (i >= NI && i < 2 * NI && P[i] < 0)) die("invalid model parameter");
}

static void alloc(void) {
    if (NI < 1 || NH < 1 || NO < 1 || (double)NH * (NI + 1) + (double)NO * (NH + 1) + 2.0 * NI > 1e8) die("bad size");
    P = calloc(nparams(), sizeof *P);
    xn = calloc(NI + 2 * NH + 2 * NO, sizeof *xn);
    if (!P || !xn) die("out of memory");
    mean = P; scale = mean + NI; W1 = scale + NI; W2 = W1 + NH * (NI + 1);
    hid = xn + NI; dh = hid + NH; z = dh + NH; out = z + NO;
}

/* Forward pass: fills xn, hid (ReLU), z (logits), lse, out (softmax probabilities); returns the argmax class. */
static int forward(const float *x) {
    int i, j, k, best = 0; float m = -1e30f, s = 0;
    for (i = 0; i < NI; i++) { xn[i] = (x[i] - mean[i]) * scale[i]; if (!isfinite(xn[i])) die("numeric overflow"); }
    for (j = 0; j < NH; j++) {
        float *w = W1 + j * (NI + 1), a = w[NI];
        for (i = 0; i < NI; i++) a += w[i] * xn[i];
        if (!isfinite(a)) die("numeric overflow");
        hid[j] = a > 0 ? a : 0;
    }
    for (k = 0; k < NO; k++) {
        float *w = W2 + k * (NH + 1), a = w[NH];
        for (j = 0; j < NH; j++) a += w[j] * hid[j];
        if (!isfinite(a)) die("numeric overflow");
        z[k] = a; if (a > m) { m = a; best = k; }
    }
    for (k = 0; k < NO; k++) s += expf(z[k] - m);
    lse = m + logf(s);                                         /* log of the softmax denominator, computed stably */
    if (!isfinite(lse)) die("numeric overflow");
    for (k = 0; k < NO; k++) out[k] = expf(z[k] - lse);
    return best;
}

/* One SGD step on example (x, y): backpropagate the cross-entropy gradient, update P in place. */
static void learn(const float *x, int y, float lr) {
    int i, j, k;
    forward(x);
    for (j = 0; j < NH; j++) dh[j] = 0;
    for (k = 0; k < NO; k++) {
        float g = out[k] - (k == y), *w = W2 + k * (NH + 1);   /* dLoss/dlogit_k */
        for (j = 0; j < NH; j++) { dh[j] += g * w[j]; w[j] -= lr * g * hid[j]; }
        w[NH] -= lr * g;
    }
    for (j = 0; j < NH; j++) if (hid[j] > 0) {                 /* ReLU gate */
        float g = dh[j], *w = W1 + j * (NI + 1);
        for (i = 0; i < NI; i++) w[i] -= lr * g * xn[i];
        w[NI] -= lr * g;
    }
}

/* ---- model file ---- */
static void put16(unsigned v, FILE *f) { putc(v & 255, f); putc(v >> 8 & 255, f); }
static int  get16(FILE *f) { int lo = getc(f), hi = getc(f); if (hi < 0) die("truncated model file"); return lo | hi << 8; }
static unsigned bits(float v) { unsigned b; memcpy(&b, &v, 4); return b; }
static float   value(unsigned b) { float v; memcpy(&v, &b, 4); return v; }

static void save(const char *path) {
    valid_params();
    for (int i = 2 * NI; i < nparams(); i++)
        if (!isfinite(value((bits(P[i]) + 0x7FFF + (bits(P[i]) >> 16 & 1)) & 0xFFFF0000u))) die("model rounding overflow");
    FILE *f = fopen(path, "wb"); int i, n = nparams();
    if (!f) die("cannot write model file");
    put16(0xA132, f); put16(NI, f); put16(NH, f); put16(NO, f);
    for (i = 0; i < 2 * NI; i++) { put16(bits(P[i]) & 0xFFFF, f); put16(bits(P[i]) >> 16, f); }   /* mean, scale: float32 */
    for (; i < n; i++) put16((bits(P[i]) + 0x7FFF + (bits(P[i]) >> 16 & 1)) >> 16, f);         /* weights: bfloat16, round to nearest even */
    if (fclose(f)) die("cannot write model file");
}

static int load(const char *path) {                           /* returns 0 if the file does not exist */
    FILE *f = fopen(path, "rb"); int i, n;
    if (!f) { if (errno == ENOENT) return 0; die("cannot open model file"); }
    if (get16(f) != 0xA132) die("not a uai32 model file");
    NI = get16(f); NH = get16(f); NO = get16(f); alloc();
    if (fseek(f, 0, SEEK_END) || ftell(f) != 8L + 8L * NI + 2L * (nparams() - 2 * NI) || fseek(f, 8, SEEK_SET)) die("wrong model size");
    for (i = 0, n = nparams(); i < 2 * NI; i++) { unsigned lo = get16(f); P[i] = value(lo | (unsigned)get16(f) << 16); }
    for (; i < n; i++) P[i] = value((unsigned)get16(f) << 16);
    fclose(f); valid_params(); return 1;
}

/* ---- data ---- */
static int parse(char *s, float *v, int max, double *label) { /* numbers in s -> v; label kept as double before integer validation */
    int n = 0; char *e;
    for (;;) {
        while (*s == ' ' || *s == '\t' || *s == '\r' || *s == '\n') s++;
        if (!*s) break;
        errno = 0; double x = strtod(s, &e);
        if (e == s) { if (n) die("invalid data token"); break; }
        if (errno || !isfinite(x) || x > FLT_MAX || x < -FLT_MAX || (*e && *e != ' ' && *e != '\t' && *e != '\r' && *e != '\n')) die("invalid data number");
        if (n < max) v[n] = (float)x;
        if (label && n == max - 1) *label = x;
        if (n == INT_MAX) die("too many columns");
        n++; s = e;
    }
    return n;
}

static float *X; static int *Y, N;                            /* the loaded dataset */
static void read_data(const char *path, int need_labels) {    /* fixes NI if it is still 0 */
    FILE *f = path ? fopen(path, "r") : stdin; char *line = 0; size_t cap = 0; float *row = 0; int room = 0, n;
    if (!f) die("cannot open data file");
    while (getline(&line, &cap, f) > 0) {
        if (!(n = parse(line, 0, 0, 0))) continue;           /* skip blank / non-numeric lines */
        if (!NI) { if (n < 2) die("need at least one feature and a label"); NI = n - 1; }
        if (need_labels ? n != NI + 1 : n < NI) die("wrong number of columns");   /* predict ignores extra columns */
        if (!row && !(row = calloc(NI + 1, sizeof *row))) die("out of memory");
        if (N == room) {
            if (room > INT_MAX / 2) die("too many rows");
            room = room ? 2 * room : 256;
            X = realloc(X, (size_t)room * NI * sizeof *X); Y = realloc(Y, room * sizeof *Y);
            if (!X || !Y) die("out of memory");
        }
        double label = 0; parse(line, row, NI + 1, &label);
        for (n = 0; n < NI; n++) if (!(row[n] - row[n] == 0)) die("feature is not a finite number");   /* NaN or inf */
        memcpy(X + (size_t)N * NI, row, NI * sizeof *X);
        if (need_labels) {
            if (label < 0 || label > 65534 || label != (int)label) die("labels must be integers in 0..65534");
            Y[N] = (int)label;
        }
        N++;
    }
    if (path) fclose(f);                                      /* memory is reclaimed at exit; no free() needed */
    if (!N) die("no examples");
}

/* Accuracy and mean cross-entropy of the current model over the loaded data (no learning). */
static void report(const char *tag) {
    int i, ok = 0; double loss = 0;
    for (i = 0; i < N; i++) { ok += forward(X + (size_t)i * NI) == Y[i]; loss += lse - z[Y[i]]; }   /* -log p_y */
    if (!isfinite(loss)) die("numeric overflow");
    printf("%s loss %.4f  accuracy %d/%d = %.1f%%\n", tag, loss / N, ok, N, 100.0 * ok / N);
}

/* ---- voice front-end verb (pilot): the benchmark's 144-value MLP vector from the shared log-mel matrix ---- */
#define NC   12                     /* DCT-II coefficients c1..c12 of each frame (c0 dropped)   */
#define L    48                     /* energy-centred crop, frames                            */
#define NSEG 12                     /* segments of L / NSEG = 4 frames, averaged -> NSEG * NC values */
static void usage(void);
static int feat_main(int argc, char **argv) {   /* feat [LABEL] < clip -> one data row on stdout */
    int t, s, c, b, d, start = 0; float *e, emin = INFINITY, bs = -INFINITY;
    if (argc > 3) usage();
    if (argc > 2) integer(argv[2], 65534);                     /* validate LABEL as uai32's train would; printed verbatim */
    alloc_fe(); logmel();
    if (!(e = calloc(2 * T, sizeof *e))) die("out of memory");  /* e[0..T-1] smoothed, e[T..2T-1] raw mean log energy */
    for (t = 0; t < T; t++) { float a = 0; for (b = 0; b < NB; b++) a += lm[t * NB + b]; e[T + t] = a / NB; }
    for (t = 0; t < T; t++) {                                  /* 5-frame box smoothing, zero padded at the ends */
        for (d = -2; d <= 2; d++) if (t + d >= 0 && t + d < T) e[t] += e[T + t + d] * 0.2f;
        if (e[t] < emin) emin = e[t];
    }
    for (c = 0; c + L <= T; c++) {                             /* the L-frame window with the most energy above the minimum (first on a tie) */
        float a = 0;
        for (t = c; t < c + L; t++) a += e[t] - emin;
        if (a > bs) { bs = a; start = c; }
    }
    for (s = 0; s < NSEG; s++) for (c = 1; c <= NC; c++) {     /* DCT-II c1..c12 of each frame, mean over the segment's frames */
        float a = 0;
        for (t = start + s * (L / NSEG); t < start + (s + 1) * (L / NSEG); t++)
            for (b = 0; b < NB; b++) a += lm[t * NB + b] * cosf(PI * c * (b + 0.5f) / NB) * sqrtf(2.0f / NB);
        printf("%.5g ", a / (L / NSEG));
    }
    printf("%s\n", argc > 2 ? argv[2] : "");
    return 0;
}

static void usage(void) {
    die("usage:\n  netapp train DATA MODEL [HIDDEN=16] [EPOCHS=50] [RATE=0.05] [SEED=1 (integer)]\n"
        "  netapp test DATA MODEL\n  netapp predict MODEL < rows   (class, probabilities, logit margin)\n"
        "  netapp feat [LABEL] < clip     (raw 16 kHz 16-bit mono PCM, 1 s -> 144 features [+ LABEL])");
}

int main(int argc, char **argv) {
    int i, j, e;
    if (argc > 1 && !strcmp(argv[1], "feat")) return feat_main(argc, argv);
    if (argc < 3) usage();
    if (!strcmp(argv[1], "predict")) {                         /* ---- inference from stdin ---- */
        if (!load(argv[2])) die("cannot open model file");
        read_data(0, 0);
        for (i = 0; i < N; i++) {
            int best = forward(X + (size_t)i * NI); float second = -INFINITY;
            for (j = 0; j < NO; j++) if (j != best && z[j] > second) second = z[j];
            printf("%d", best);
            for (j = 0; j < NO; j++) printf(" %.6f", out[j]);
            printf(" %.6f\n", z[best] - second);                 /* logit margin: best minus runner-up */
        }
        return 0;
    }
    if (argc < 4) usage();
    if (!strcmp(argv[1], "test")) {                            /* ---- evaluate a saved model ---- */
        if (!load(argv[3])) die("cannot open model file");
        read_data(argv[2], 1);
        for (i = 0; i < N; i++) if (Y[i] >= NO) die("label outside the model's classes");
        report("test");
        return 0;
    }
    if (strcmp(argv[1], "train")) usage();                     /* ---- train (fresh or continued) ---- */
    int hidden = argc > 4 ? integer(argv[4], 65535) : 16, epochs = argc > 5 ? integer(argv[5], INT_MAX - 1u) : 50;
    float lr = argc > 6 ? rate(argv[6]) : 0.05f;
    rng = argc > 7 ? integer(argv[7], 4294967295u) : 1; if (!rng) rng = 1;
    int resumed = load(argv[3]);
    read_data(argv[2], 1);
    if (!resumed) {
        NH = hidden; NO = 0;
        for (i = 0; i < N; i++) if (Y[i] >= NO) NO = Y[i] + 1;
        if (NI > 65535 || NH > 65535 || NO > 65535) die("bad size");
        alloc();
        for (j = 0; j < NI; j++) {                             /* feature normalisation: shift by the mean, scale by the range */
            float lo = X[j], hi = X[j]; double s = 0;
            for (i = 0; i < N; i++) { float v = X[(size_t)i * NI + j]; s += v; if (v < lo) lo = v; if (v > hi) hi = v; }
            float range = hi - lo;                             /* finite inputs can still overflow here (3e38 - -3e38) */
            if (!(range <= FLT_MAX)) die("feature range overflows float");
            mean[j] = s / N; scale[j] = range > 0 ? 1 / range : 0;
        }
        for (i = 0; i < NH * (NI + 1); i++) W1[i] = (i + 1) % (NI + 1) ? frand() * sqrtf(6.0f / NI) : 0;  /* He-uniform, zero bias */
        for (i = 0; i < NO * (NH + 1); i++) W2[i] = (i + 1) % (NH + 1) ? frand() * sqrtf(6.0f / NH) : 0;
        printf("new model: %d inputs, %d hidden, %d classes, %d parameters\n", NI, NH, NO, nparams());
    } else {
        for (i = 0; i < N; i++) if (Y[i] >= NO) die("label outside the model's classes");
        printf("continuing: %d inputs, %d hidden, %d classes\n", NI, NH, NO);
    }
    int *idx = calloc(N, sizeof *idx); if (!idx) die("out of memory");
    for (i = 0; i < N; i++) idx[i] = i;
    for (e = 1; e <= epochs; e++) {
        for (i = N - 1; i > 0; i--) { frand(); j = rng % (i + 1); int t = idx[i]; idx[i] = idx[j]; idx[j] = t; }  /* shuffle */
        for (i = 0; i < N; i++) learn(X + (size_t)idx[i] * NI, Y[idx[i]], lr);
        printf("epoch %d/%d  ", e, epochs); report("train");
    }
    save(argv[3]);
    return 0;
}
