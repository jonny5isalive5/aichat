# The pilot front-end, exactly

Both pilot applications (`dtwapp.c`, `netapp.c`) contain one textually identical block of C
(`/* ==== FRONT-END BEGIN ... END ==== */`, 82 lines; `build.sh` refuses to build if the two copies differ)
that turns one clip into the 61 x 16 log-mel matrix of the few-shot benchmark.  Each arm then derives its
own input from that matrix, exactly as the benchmark did from its cached log-mel (`features.py`,
`feats2.py`, `fewshot.pooled_vectors`, `fewshot.dtw_frames`).

## Which recipe, and why

The pilot uses the **benchmark recipe** (reports/fewshot-accuracy.md; scratch `voice-fewshot-accuracy/code/`
`features.py`, `feats2.py`, `frontend.c`), not the recipe of the front-end byte study (`vfe.c`: 256-point FFT,
16 ms / 8 ms framing, 100-7000 Hz, floor 1e-7, 124 frames pooled into 12 segments = 192 features).  Reason:
every accuracy and rejection number in the benchmark was produced with the former, so pilot numbers are
comparable to it, and it turned out to be implementable just as compactly (dtwapp is 7,416 bytes complete;
the block adds 2,312 bytes to uai32 in netapp, versus 2,224 for vfe.c's FFT variant, see SIZES.md).  The
only departures from the Python reference are numerical (float32 FFT in C versus numpy's float32 pocketfft,
`cosf`/`sinf` versus float64 tables): measured max |difference| 1.3e-4 in log-mel units, mean 7e-7, on all
80 validation clips (`validation/validate.log`).

## Input

- Raw signed 16-bit little-endian mono PCM at 16,000 Hz, read from **stdin**.  No header; a WAV file is
  refused (the "RIFF" tag is detected), as are an empty clip and an odd byte count.
- One second = 16,000 samples.  Shorter input is zero-padded at the end; longer input is truncated: the 61
  frames cover samples 0..15,871, so samples 15,872..15,999 (and anything after) are never read, exactly
  as in `features.py`, where no frame uses them either.
- Isolated utterances only: the host centres the word.  No segmentation, onset detection or gain control.
- Samples are read frame by frame (a 513-sample buffer slides by 256), so the whole second is never held.

## Steps (identical in both apps)

1. **Scaling**: x[n] = pcm[n] / 32768 (exact in float32).
2. **Pre-emphasis**: y[n] = x[n] - 0.97 x[n-1], with x[-1] = 0.
3. **Framing**: 61 frames of 512 samples (32 ms) every 256 samples (16 ms); frame t covers y[256t .. 256t+511].
4. **Window**: periodic Hann, w[n] = 0.5 - 0.5 cos(2 pi n / 512), n = 0..511.
5. **Spectrum**: 512-point complex radix-2 decimation-in-time FFT of the windowed frame (imaginary input 0);
   power P[k] = Re^2 + Im^2 for k = 0..256.
6. **Mel filters**: 18 edges equally spaced on the HTK mel scale between 100 Hz and 7,600 Hz,
   mel(f) = 2595 log10(1 + f/700), mapped to FFT bins by floor(513 f / 16000).  The C code uses the
   equivalent form ln(1 + f/700) (the constant 2595/ln 10 cancels in the linear spacing) and gets the same
   18 bins as numpy: 3 6 11 16 22 28 36 44 54 66 79 94 111 131 153 179 209 243 (verified on every clip; the
   closest edge to a bin boundary is 0.0096 bins away).  Filter b is a triangle rising linearly from
   bin[b] (weight 0) to bin[b+1] (weight 1) and falling to bin[b+2] (weight 0), i.e.
   w = (k - bin[b]) / (bin[b+1] - bin[b]) for k < bin[b+1], else (bin[b+2] - k) / (bin[b+2] - bin[b+1]);
   E[t][b] = sum_k w P[k] over bin[b] <= k < bin[b+2].
7. **Log**: lm[t][b] = ln(E[t][b] + 1e-3).  Digital silence gives exactly ln(1e-3) = -6.9078 everywhere.

Constants in the source: SR 16000, FN 512, HOP 256, T 61, NB 16, PI 3.14159265f.

## Arm 1, dtwapp: DTW frames and uint8 templates

- **Normalisation** (`feats2.frames(LM, 'logmel_cmvn')`): per band b over the 61 frames,
  v[t][b] = (lm[t][b] - mean_b) / (std_b + 1e-3), std_b = sqrt(mean((lm - mean_b)^2)) (population std).
- **Quantisation** (the benchmark's `check_uint8_dtw.py`): q = clamp(round_half_even(v / 0.05), -127, 128),
  stored as byte q + 127 (0..255); dequantised value (byte - 127) * 0.05.  Step 0.05, range -6.35..+6.40.
  `lrintf` gives round-half-even like `np.round`; the 20 x 976 template bytes written by dtwapp are
  identical to numpy's on the validation clips (19,520/19,520).
- **Distance** (the benchmark's `dtw.c`): D[0][0] = 0, D[i][0] = D[0][j] = inf; D[i][j] = c(i,j) +
  min(D[i-1][j], D[i][j-1], D[i-1][j-1]) with c = Euclidean distance between query frame i (float32) and
  dequantised template frame j over the 16 bands; result D[61][61] / 122.  Computed in one row of 62 floats.
- **Decision**: per label the minimum over its templates; best = smallest (lowest label on a tie), runner-up =
  smallest among the other labels; printed `best_label best_dist runnerup_dist margin`, margin = runner-up - best.
  Validation: 60/60 decisions and all distances within 2e-6 of the benchmark DTW on uint8 templates, and
  60/60 decisions (distances within 0.0098) of it on float32 templates.

## Arm 2, netapp feat: the 144-value vector

(`fewshot.pooled_vectors(LM)` with its defaults: `mfcc_raw`, 12 coefficients, `center` pooling)

- **Energy**: e[t] = mean over the 16 bands of lm[t][b]; smoothed with a 5-frame box, zero-padded at the
  ends (`np.convolve(..., 'same')`): es[t] = sum of 0.2 e[t+d] for d = -2..2 that exist.
- **Crop**: start c in 0..13 maximising sum over the 48 frames c..c+47 of (es[t] - min es); first maximum.
- **DCT-II** of each frame: C[t][c] = sqrt(2/16) sum_b lm[t][b] cos(pi c (b + 0.5) / 16), c = 1..12 (c0 dropped).
- **Pooling**: 12 segments of 4 frames from the crop; value[s * 12 + (c - 1)] = mean over the segment's 4
  frames of C[t][c].  144 values, printed with `%.5g` (as the benchmark wrote its rows), then the label if given.
- Validation: max |difference| from the benchmark vectors 5.1e-4, mean 9e-6, on all 80 clips; no crop-start
  disagreement (a clip with a different crop would differ by ~1); 70.8% of the printed `%.5g` tokens are
  character-identical to the benchmark's rows, the rest differ in the fifth significant digit.

## Working set of the block

One `calloc` of 2,275 floats = 9,100 bytes: sample buffer 513 shorts (1,026 bytes, padded to 1,028),
re and im 2 x 2,048, lm 3,904, 18 bin numbers 72.  Plus six scalars/pointers in .bss and a few locals.
`tools/fe_harness.sh` compiles the block alone (with -Os and -O0; both give bit-identical output) for the
comparison with `features.py`.
