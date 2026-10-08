/* vfe.c -- voice front-end for uAI-32: one second of 16 kHz 16-bit mono PCM -> NT*NB log band energies,
 * printed as one uai32 data row.  Same style and build flags as uai32.c; C99, no tables in the executable.
 *
 *   vfe [-n] [FILE|-] [LABEL]     FILE is raw little-endian 16-bit PCM or a WAV file (default: stdin, also "-");
 *                                 prints NT*NB numbers, then LABEL if given, on one line.
 *
 * Two front-ends, chosen when compiling (exactly one is built in):
 *   -DFE_BIQUAD  NB second-order IIR band-pass filters (RBJ biquads, transposed direct form II) with mel-spaced
 *                centres and bandwidth = half the spacing of the neighbouring centres; energy per 16 ms frame.
 *                No FFT.  Uses sinf (coefficients) + logf/expf (mel scale, log energy).
 *   -DFE_FFT     256-point radix-2 complex FFT (real input, imaginary part zero), sin^2 (Hann) window,
 *                NB triangular mel filters evaluated bin by bin from the band edges.  Uses sinf/cosf (window
 *                and twiddles, computed once at start-up) + logf/expf.  [default when neither is defined]
 *
 * Framing (both): 16 ms frames (FL = 256 samples), 8 ms hop (HOP = 128) -> NF = 124 frames per second.
 * Band energies are scaled so that a full-scale sine at a band centre gives 1.0, floored at FLOOR (-70 dB) and
 * logged; the 124 frames are pooled into NT segments by averaging the log energies, giving NT*NB features.
 * -n subtracts each band's mean over the NT segments (per-utterance mean normalisation: removes microphone
 * gain and fixed colouring).  Input shorter than one second is zero-padded; longer input is truncated.
 * WAV: the chunks are walked to "data"; "fmt " must say 1 channel, 16000 Hz, 16 bits (else error).
 *
 * Build (standalone):  cc <uai32 CFLAGS> -DFE_FFT vfe.c -o vfe <uai32 LDFLAGS> -lm
 * Bench:               cc ... -DBENCH=200 vfe.c ...   then  ./vfe_bench FILE   (ms per second of audio)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ==== VFE BEGIN ==== */
#if !defined(FE_BIQUAD) && !defined(FE_FFT)
#define FE_FFT
#endif
#ifndef NB
#define NB 16                          /* bands                                           */
#endif
#ifndef NT
#define NT 12                          /* time segments (pooled frames)                   */
#endif
#define FS 16000                       /* sample rate                                     */
#define NS FS                          /* samples analysed: one second                    */
#define FL 256                         /* frame length: 16 ms                             */
#define HOP 128                        /* frame hop: 8 ms                                 */
#define NF ((NS - FL) / HOP + 1)       /* frames per second: 124                          */
#define FLO 100.f                      /* lowest band edge, Hz                            */
#define FHI 7000.f                     /* highest band edge, Hz                           */
#define FLOOR 1e-7f                    /* energy floor (-70 dB re full scale)             */
#define PI 3.14159265f

static void die(const char *m);
static short pcm[NS];                  /* one second of samples                           */
static float band[NF][NB];             /* per-frame band energies (full-scale sine = 1)   */
static float feat[NT * NB], edge[NB + 2];

static unsigned rd(FILE *f, int n) {   /* n-byte little-endian unsigned integer           */
    unsigned v = 0; int i, c;
    for (i = 0; i < n; i++) { if ((c = getc(f)) < 0) die("truncated audio"); v |= (unsigned)c << 8 * i; }
    return v;
}
static int s16(unsigned v) { v &= 0xFFFF; return (int)v - (int)((v & 0x8000) << 1); }

static void read_pcm(FILE *f) {        /* raw 16-bit LE PCM, or a WAV container around it */
    int i = 0, lo, hi; unsigned a = rd(f, 4);
    if (a == 0x46464952u) {            /* "RIFF": walk the chunks to "data"               */
        rd(f, 8);                      /* file size, "WAVE"                               */
        for (;;) {
            unsigned id = rd(f, 4), n = rd(f, 4);
            if (id == 0x61746164u) break;                                  /* "data" */
            if (id == 0x20746d66u) {                                       /* "fmt " */
                unsigned ch = (rd(f, 2), rd(f, 2)), sr = rd(f, 4); rd(f, 6);
                if (ch != 1 || sr != FS || rd(f, 2) != 16) die("need 16 kHz 16-bit mono");
                n -= 16;
            }
            for (n += n & 1; n; n--) rd(f, 1);                             /* chunks are padded to even */
        }
    } else { pcm[0] = s16(a); pcm[1] = s16(a >> 16); i = 2; }
    for (; i < NS && (lo = getc(f)) >= 0 && (hi = getc(f)) >= 0; i++) pcm[i] = s16(lo | hi << 8);
}

static float mel(float f) { return 1127 * logf(1 + f / 700); }
static void edges(void) {              /* NB+2 edges equally spaced on the mel scale from FLO to FHI */
    int i; float lo = mel(FLO), d = (mel(FHI) - lo) / (NB + 1);
    for (i = 0; i < NB + 2; i++) edge[i] = 700 * (expf((lo + d * i) / 1127) - 1);
}

#ifdef FE_BIQUAD
/* Band b: RBJ constant-peak-gain band-pass, centre edge[b+1], bandwidth (edge[b+2]-edge[b])/2, so
 * alpha = sin(w0)/(2Q) = sin(w0)*bw/(2 fc).  Each sample's y^2 goes to the two 256-sample frames containing it. */
static void analyse(void) {
    int b, i;
    for (b = 0; b < NB; b++) {
        float fc = edge[b + 1], w0 = 2 * PI * fc / FS, h = sinf(w0 / 2), cs = 1 - 2 * h * h;   /* cs = cos w0 */
        float alpha = sinf(w0) * (edge[b + 2] - edge[b]) / (4 * fc), a0 = 1 + alpha;
        float b0 = alpha / a0, a1 = -2 * cs / a0, a2 = (1 - alpha) / a0, s1 = 0, s2 = 0;
        for (i = 0; i < NS; i++) {
            float x = pcm[i] * (1.f / 32768), y = b0 * x + s1, yy = y * y * (2.f / FL); int k = i / HOP;
            s1 = s2 - a1 * y; s2 = -b0 * x - a2 * y;
            if (k < NF) band[k][b] += yy;
            if (k) band[k - 1][b] += yy;
        }
    }
}
#else
static float re[FL], im[FL], win[FL], twr[FL / 2], twi[FL / 2];
static void fft(void) {                /* in-place radix-2 decimation-in-time, length FL  */
    int i, j, k, h;
    for (i = 1, j = 0; i < FL; i++) {  /* bit-reversal permutation                        */
        for (k = FL >> 1; j & k; k >>= 1) j ^= k;
        j ^= k;
        if (i < j) { float t = re[i]; re[i] = re[j]; re[j] = t; t = im[i]; im[i] = im[j]; im[j] = t; }
    }
    for (h = 1; h < FL; h <<= 1)
        for (j = 0; j < h; j++) {
            float wr = twr[j * (FL / 2 / h)], wi = twi[j * (FL / 2 / h)];
            for (i = j; i < FL; i += 2 * h) {
                float tr = wr * re[i + h] - wi * im[i + h], ti = wr * im[i + h] + wi * re[i + h];
                re[i + h] = re[i] - tr; im[i + h] = im[i] - ti; re[i] += tr; im[i] += ti;
            }
        }
}
static void analyse(void) {
    int k, n, b, j;
    for (n = 0; n < FL; n++) { float s = sinf(PI * n / FL); win[n] = s * s * (4.f / FL / 32768); }  /* Hann, |X| = A for a full-scale sine */
    for (j = 0; j < FL / 2; j++) { twr[j] = cosf(2 * PI * j / FL); twi[j] = -sinf(2 * PI * j / FL); }
    for (k = 0; k < NF; k++) {
        for (n = 0; n < FL; n++) { re[n] = pcm[k * HOP + n] * win[n]; im[n] = 0; }
        fft();
        for (j = 0; j <= FL / 2; j++) {
            float f = (float)FS * j / FL, p = re[j] * re[j] + im[j] * im[j];
            for (b = 0; b < NB; b++) {                                         /* triangle on edge[b..b+2] */
                float w = (f - edge[b]) / (edge[b + 1] - edge[b]), v = (edge[b + 2] - f) / (edge[b + 2] - edge[b + 1]);
                if (v < w) w = v;
                if (w > 0) band[k][b] += w * p;
            }
        }
    }
}
#endif

static void pool(int norm) {           /* log, pool NF frames into NT segments, optional per-band mean removal */
    int t, b, k;
    for (t = 0; t < NT; t++) {
        int k0 = t * NF / NT, k1 = (t + 1) * NF / NT;
        for (b = 0; b < NB; b++) {
            float s = 0;
            for (k = k0; k < k1; k++) s += logf(band[k][b] + FLOOR);
            feat[t * NB + b] = s / (k1 - k0);
        }
    }
    if (norm) for (b = 0; b < NB; b++) {
        float m = 0;
        for (t = 0; t < NT; t++) m += feat[t * NB + b] / NT;
        for (t = 0; t < NT; t++) feat[t * NB + b] -= m;
    }
}

static int feat_main(int argc, char **argv) {   /* [-n] [FILE|-] [LABEL] -> one data row on stdout */
    int norm = 0, i; FILE *f = stdin;
    if (argc > 0 && !strcmp(argv[0], "-n")) { norm = 1; argc--; argv++; }
    if (argc > 0 && strcmp(argv[0], "-") && !(f = fopen(argv[0], "rb"))) die("cannot open audio file");
    read_pcm(f); edges(); analyse(); pool(norm);
    for (i = 0; i < NT * NB; i++) printf("%.3f ", feat[i]);
    if (argc > 1) printf("%s", argv[1]);
    printf("\n");
    return 0;
}
/* ==== VFE END ==== */

#ifndef VFE_EMBED
static void die(const char *m) { fprintf(stderr, "vfe: %s\n", m); exit(1); }
#ifdef BENCH
#include <time.h>
int main(int argc, char **argv) {      /* bench: repeat the whole analysis BENCH times on FILE */
    struct timespec t0, t1; int r; double s; FILE *f;
    if (argc < 2 || !(f = fopen(argv[1], "rb"))) die("bench: cannot open FILE");
    read_pcm(f);
    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (r = 0; r < BENCH; r++) { memset(band, 0, sizeof band); edges(); analyse(); pool(1); }
    clock_gettime(CLOCK_MONOTONIC, &t1);
    s = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) * 1e-9;
    printf("%d runs: %.3f ms per second of audio (check %g)\n", BENCH, 1e3 * s / BENCH, feat[NB + 3]);
    return 0;
}
#else
int main(int argc, char **argv) { return feat_main(argc - 1, argv + 1); }
#endif
#endif
