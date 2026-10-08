/* dtwapp.c -- Sentovara uAI-32 voice pilot, arm 1: enrolled-speaker command recogniser by dynamic time warping
 * (DTW) against uint8 templates.  One C99 file in the uai32.c style, built with the uai32 flags.
 *
 *   dtwapp enrol STATE LABEL < clip    append one template of the clip under LABEL (integer 0..15); STATE is created if absent
 *   dtwapp score STATE < clip          print one line:  best_label best_dist runnerup_dist margin
 *   dtwapp info  STATE                 print what the state holds and the format / capacity facts
 *
 * clip: raw signed 16-bit little-endian mono PCM at 16,000 Hz, one second = 16,000 samples; shorter input is zero-padded
 * at the end, longer input is truncated (the 128 samples after the last frame, 15,872..15,999, are never read).  WAV
 * files, empty input and an odd number of bytes are refused.  Isolated utterances only: the host centres the word.
 *
 * Features (the few-shot benchmark's DTW recipe, see FRONTEND.md): the 61 x 16 log-mel matrix of the shared front-end,
 * then per band mean/variance normalisation over the 61 frames, v = (x - mean) / (std + 1e-3), std = sqrt(mean((x - mean)^2)).
 * Template = the 61 x 16 normalised frames quantised to uint8: byte = clamp(round_half_even(v / 0.05), -127, 128) + 127,
 * value = (byte - 127) * 0.05, i.e. step 0.05 in normalised units, range -6.35 .. +6.40 (exactly the benchmark's check).
 * Distance = DTW with steps (1,0), (0,1), (1,1), Euclidean local cost over the 16 bands, total path cost / 122
 * (= query frames + template frames); the query is the float32 frames, the template is dequantised on the fly.
 * score: per label the minimum distance over its templates; best = the label with the smallest minimum (the lowest label
 * on a tie), runner-up = the smallest minimum among the other labels (inf when only one label is enrolled),
 * margin = runner-up - best (larger = more confident; a rejection threshold is applied by the host).
 *
 * STATE file (all little-endian):
 *   u16 magic 0xA1D7, u16 T = 61, u16 NB = 16, u16 N = number of templates            (8-byte header)
 *   then N records of 977 bytes: u8 label (0..15), u8 template[61 * 16] (frame 0 bands 0..15, frame 1, ...).
 *   size = 8 + 977 * N bytes; N = 20 (the pilot capacity of 4 commands x 5 examples) is 19,548 bytes; N <= 65535.
 *   Any other size, magic, T, NB, or a label byte >= 16 is refused.  enrol appends one record and rewrites the count,
 *   nothing else is ever rewritten, so the file is checked by formula like a uai32 model.  It is not crash-atomic: an
 *   enrol interrupted half-way leaves a file the size check refuses; delete it and enrol again.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <errno.h>

static void die(const char *m) { fprintf(stderr, "dtwapp: %s\n", m); exit(1); }

static unsigned integer(const char *s, unsigned max) {        /* as uai32.c */
    char *e; unsigned long v; errno = 0; v = strtoul(s, &e, 10);
    if (*s < '0' || *s > '9' || *e || errno || v > max) die("invalid integer argument");
    return (unsigned)v;
}

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

#define NL    16                    /* labels 0..NL-1                                         */
#define TB    (T * NB)              /* template values: 976                                   */
#define REC   (1 + TB)              /* record bytes: label + template = 977                   */
#define MAGIC 0xA1D7
#define STEP  0.05f                 /* quantisation step in normalised units                  */
#define OFF   127                   /* byte = q + OFF, q in -127..128                          */
static float *D;                    /* DTW cost row, T + 1 cells                              */
static unsigned char *rec;          /* one state record (label byte + template)               */

static void cmvn(void) {            /* per band mean / variance normalisation of lm over the T frames */
    int b, t;
    for (b = 0; b < NB; b++) {
        float m = 0, v = 0;
        for (t = 0; t < T; t++) m += lm[t * NB + b];
        m /= T;
        for (t = 0; t < T; t++) v += (lm[t * NB + b] - m) * (lm[t * NB + b] - m);
        v = sqrtf(v / T) + 1e-3f;
        for (t = 0; t < T; t++) lm[t * NB + b] = (lm[t * NB + b] - m) / v;
    }
}

static void quantise(void) {        /* lm -> rec[1..TB] as uint8 (round half to even, like numpy) */
    int i;
    for (i = 0; i < TB; i++) {
        long q = lrintf(lm[i] / STEP);
        rec[1 + i] = (unsigned char)((q < -OFF ? -OFF : q > OFF + 1 ? OFF + 1 : q) + OFF);
    }
}

static float dtw(void) {            /* normalised DTW distance between lm (query) and the template in rec */
    int i, j, k;
    D[0] = 0;
    for (j = 1; j <= T; j++) D[j] = INFINITY;
    for (i = 1; i <= T; i++) {
        float diag = D[0];                                             /* D[i-1][0]                 */
        D[0] = INFINITY;                                               /* D[i][0]                   */
        for (j = 1; j <= T; j++) {
            float c = 0, up = D[j], best = up < D[j - 1] ? up : D[j - 1];
            if (diag < best) best = diag;
            for (k = 0; k < NB; k++) {
                float d = lm[(i - 1) * NB + k] - (rec[1 + (j - 1) * NB + k] - OFF) * STEP;
                c += d * d;
            }
            D[j] = sqrtf(c) + best; diag = up;
        }
    }
    return D[T] / (2 * T);
}

/* ---- state file ---- */
static void put16(unsigned v, FILE *f) { putc(v & 255, f); putc(v >> 8 & 255, f); }
static int  get16(FILE *f) { int lo = getc(f), hi = getc(f); if (hi < 0) die("truncated state file"); return lo | hi << 8; }

static FILE *state(const char *path, int create, int *n) {   /* open and validate STATE; create an empty one if allowed */
    FILE *f = fopen(path, create ? "r+b" : "rb");
    if (!f) {
        if (!create || errno != ENOENT) die("cannot open state file");
        if (!(f = fopen(path, "w+b"))) die("cannot create state file");
        put16(MAGIC, f); put16(T, f); put16(NB, f); put16(0, f);
        if (fflush(f)) die("cannot write state file");
        rewind(f);
    }
    if (get16(f) != MAGIC) die("not a dtwapp state file");
    if (get16(f) != T || get16(f) != NB) die("state file frame geometry differs from this build");
    *n = get16(f);
    if (fseek(f, 0, SEEK_END) || ftell(f) != 8L + (long)REC * *n || fseek(f, 8, SEEK_SET)) die("wrong state file size");
    return f;
}

static void usage(void) {
    die("usage:\n  dtwapp enrol STATE LABEL < clip   (LABEL 0..15)\n  dtwapp score STATE < clip\n  dtwapp info STATE\n"
        "  clip: raw 16 kHz signed 16-bit little-endian mono PCM, 1 s (16,000 samples)");
}

int main(int argc, char **argv) {
    int i, n, count[NL] = {0};
    if (argc < 3) usage();
    if (!(D = calloc(T + 1 + (REC + 3) / 4, sizeof *D))) die("out of memory");   /* DTW row, then the record */
    rec = (unsigned char *)(D + T + 1);
    if (!strcmp(argv[1], "info")) {                            /* ---- facts about a state file ---- */
        FILE *f = state(argv[2], 0, &n);
        for (i = 0; i < n; i++) {
            if (fread(rec, 1, REC, f) != REC) die("truncated state file");
            if (rec[0] >= NL) die("invalid label in state file");
            count[rec[0]]++;
        }
        printf("templates %d, file bytes %ld = 8 + %d * %d, per label:", n, 8L + (long)REC * n, REC, n);
        for (i = 0; i < NL; i++) if (count[i]) printf(" %d:%d", i, count[i]);
        printf("\ntemplate: %d frames x %d bands uint8, step %g, range %g..%g, %d bytes with its label\n",
               T, NB, STEP, -OFF * STEP, (OFF + 1) * STEP, REC);
        printf("capacity: labels 0..%d, up to 65535 templates; pilot capacity 4 x 5 = 20 templates = %ld bytes\n", NL - 1, 8L + 20L * REC);
        return 0;
    }
    if (!strcmp(argv[1], "score")) {                           /* ---- recognise the clip on stdin ---- */
        float cmin[NL], best, run; int lab = 0;
        alloc_fe(); logmel(); cmvn();
        FILE *f = state(argv[2], 0, &n);
        if (!n) die("no templates enrolled");
        for (i = 0; i < NL; i++) cmin[i] = INFINITY;
        for (i = 0; i < n; i++) {
            float d;
            if (fread(rec, 1, REC, f) != REC) die("truncated state file");
            if (rec[0] >= NL) die("invalid label in state file");
            d = dtw();
            if (d < cmin[rec[0]]) cmin[rec[0]] = d;
        }
        for (i = 1; i < NL; i++) if (cmin[i] < cmin[lab]) lab = i;
        best = cmin[lab]; cmin[lab] = INFINITY; run = cmin[0];
        for (i = 1; i < NL; i++) if (cmin[i] < run) run = cmin[i];
        printf("%d %.6f %.6f %.6f\n", lab, best, run, run - best);
        return 0;
    }
    if (strcmp(argv[1], "enrol") || argc < 4) usage();         /* ---- add one template ---- */
    rec[0] = (unsigned char)integer(argv[3], NL - 1);
    alloc_fe(); logmel(); cmvn(); quantise();
    FILE *f = state(argv[2], 1, &n);
    if (n >= 65535) die("state file full");
    if (fseek(f, 0, SEEK_END) || fwrite(rec, 1, REC, f) != REC || fseek(f, 6, SEEK_SET)) die("cannot write state file");
    put16(n + 1, f);
    if (fclose(f)) die("cannot write state file");
    return 0;
}
