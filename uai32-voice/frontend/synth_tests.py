#!/usr/bin/env python3
"""synth_tests.py DIR -- synthetic-signal correctness tests for vfe (biquad + fft), standalone and merged.
Writes test audio to DIR/tests, runs the binaries, compares against a float64 numpy reference of the same
formulas, checks tones light the right bands, silence gives the floor, WAV parsing, pooling, -n, labels,
and finally trains a uai32 model end to end on synthetic tone classes through the merged binaries."""
import sys, os, struct, subprocess, math, shutil
import numpy as np

D = sys.argv[1]; TD = os.path.join(D, 'tests'); shutil.rmtree(TD, ignore_errors=True); os.makedirs(TD)
FS = 16000; NS = 16000; FL = 256; HOP = 128; NF = (NS - FL) // HOP + 1; NB = 16; NT = 12
FLO = 100.0; FHI = 7000.0; FLOOR = 1e-7
def mel(f): return 1127 * np.log(1 + f / 700)
lo = mel(FLO); dm = (mel(FHI) - lo) / (NB + 1)
edge = 700 * (np.exp((lo + dm * np.arange(NB + 2)) / 1127) - 1); centre = edge[1:NB + 1]
BIN = {'biquad': ([os.path.join(D, 'vfe_biquad')], [os.path.join(D, 'uai32_biquad'), 'feat']),
       'fft':    ([os.path.join(D, 'vfe_fft')],    [os.path.join(D, 'uai32_fft'), 'feat'])}
fails = []
def check(cond, msg):
    print(('ok   ' if cond else 'FAIL ') + msg)
    if not cond: fails.append(msg)

def to_i16(x): return np.clip(np.round(np.asarray(x) * 32768), -32768, 32767).astype('<i2')
def write_raw(name, s): p = os.path.join(TD, name + '.raw'); s.tofile(p); return p
def write_wav(name, s, extra_chunk=False, channels=1, rate=FS, bits=16):
    data = s.tobytes()
    fmt = struct.pack('<HHIIHH', 1, channels, rate, rate * channels * bits // 8, channels * bits // 8, bits)
    body = b'WAVE' + b'fmt ' + struct.pack('<I', len(fmt)) + fmt
    if extra_chunk:
        pay = b'INFOISFT' + struct.pack('<I', 5) + b'vfe!!'          # 17 bytes: odd, so a pad byte follows
        body += b'LIST' + struct.pack('<I', len(pay)) + pay + b'\0'
    body += b'data' + struct.pack('<I', len(data)) + data
    p = os.path.join(TD, name + '.wav'); open(p, 'wb').write(b'RIFF' + struct.pack('<I', len(body)) + body); return p

def ref(s, variant, norm=False):
    x = np.zeros(NS); n = min(len(s), NS); x[:n] = s[:n] / 32768.0
    band = np.zeros((NF, NB))
    if variant == 'biquad':
        xl = x.tolist()
        for b in range(NB):
            fc = edge[b + 1]; w0 = 2 * math.pi * fc / FS; cs = math.cos(w0)
            alpha = math.sin(w0) * (edge[b + 2] - edge[b]) / (4 * fc); a0 = 1 + alpha
            b0 = alpha / a0; a1 = -2 * cs / a0; a2 = (1 - alpha) / a0; s1 = s2 = 0.0; yy = [0.0] * NS
            for i in range(NS):
                xi = xl[i]; y = b0 * xi + s1; s1 = s2 - a1 * y; s2 = -b0 * xi - a2 * y; yy[i] = y * y
            blk = (np.array(yy) * (2.0 / FL)).reshape(NS // HOP, HOP).sum(1)
            band[:, b] = blk[:NF] + blk[1:NF + 1]
    else:
        n_ = np.arange(FL); win = np.sin(np.pi * n_ / FL) ** 2 * (4.0 / FL)
        fj = FS * np.arange(FL // 2 + 1) / FL; W = np.zeros((NB, FL // 2 + 1))
        for b in range(NB):
            w = np.minimum((fj - edge[b]) / (edge[b + 1] - edge[b]), (edge[b + 2] - fj) / (edge[b + 2] - edge[b + 1]))
            W[b] = np.where(w > 0, w, 0)
        for k in range(NF):
            P = np.abs(np.fft.rfft(x[k * HOP:k * HOP + FL] * win)) ** 2; band[k] = W @ P
    feat = np.zeros((NT, NB))
    for t in range(NT):
        k0 = t * NF // NT; k1 = (t + 1) * NF // NT; feat[t] = np.log(band[k0:k1] + FLOOR).mean(0)
    if norm: feat -= feat.mean(0)
    return feat.ravel()

def run(cmd, inp=None):
    r = subprocess.run(cmd, input=inp, capture_output=True); return r.returncode, r.stdout.decode(), r.stderr.decode()
def feats(cmd, inp=None):
    rc, out, err = run(cmd, inp)
    if rc: raise SystemExit('command failed: %s: %s' % (cmd, err))
    toks = out.split(); return np.array([float(t) for t in toks]), toks, out

def compare(name, variant, s, extra=(), norm=False):
    """C standalone vs numpy reference (tiered tolerance), merged vs standalone (exact text)."""
    r = ref(s, variant, norm); sa, ma = BIN[variant]; p = write_raw(name + '_' + variant, s)
    flags = ['-n'] if norm else []
    c, toks, out = feats(sa + flags + [p]); _, mtoks, mout = feats(ma + flags + [p])
    check(out == mout, '%s/%s: merged `feat` output identical to standalone' % (name, variant))
    check(len(c) == NT * NB, '%s/%s: %d features' % (name, variant, NT * NB))
    hi = r > math.log(100 * FLOOR)                     # bands well above the floor: tight; near floor: loose
    d = np.abs(c - r); dh = d[hi].max() if hi.any() else 0; dl = d[~hi].max() if (~hi).any() else 0
    check(dh < 0.02 and dl < 0.5, '%s/%s: vs numpy reference  max|diff| above floor %.4f (n=%d), near floor %.4f (n=%d)'
          % (name, variant, dh, hi.sum(), dl, (~hi).sum()))
    return c.reshape(NT, NB), r.reshape(NT, NB)

def biquad_gain(f, b):                                 # analytic |H| of band b at frequency f
    fc = edge[b + 1]; w0 = 2 * math.pi * fc / FS; alpha = math.sin(w0) * (edge[b + 2] - edge[b]) / (4 * fc); a0 = 1 + alpha
    b0 = alpha / a0; a1 = -2 * math.cos(w0) / a0; a2 = (1 - alpha) / a0; z = np.exp(-1j * 2 * math.pi * f / FS)
    return abs(b0 * (1 - z ** 2) / (1 + a1 * z + a2 * z ** 2))
def tri_weight(f, b):
    return max(0.0, min((f - edge[b]) / (edge[b + 1] - edge[b]), (edge[b + 2] - f) / (edge[b + 2] - edge[b + 1])))

t = np.arange(NS) / FS
print('band centres (Hz):', ' '.join('%.0f' % c for c in centre))
print('band edges   (Hz):', ' '.join('%.0f' % c for c in edge))

# 1. silence -> every feature is exactly the floor
sil = to_i16(np.zeros(NS))
for v in BIN:
    c, r = compare('silence', v, sil)
    _, toks, _ = feats(BIN[v][0] + [os.path.join(TD, 'silence_%s.raw' % v)])
    check(all(tk == '-16.118' for tk in toks), 'silence/%s: all %d features == ln(1e-7) = -16.118' % (v, len(toks)))

# 2. tones at every band centre, amplitude 0.5 -> argmax band = that band; level ~ ln(A^2) = -1.386
print('\nper-band log energy (last segment) for a 0.5-amplitude tone at each band centre; peak marked *')
for v in BIN:
    print('--', v)
    print('      ' + ''.join('%7d' % b for b in range(NB)))
    ok_arg = True; peaks = []
    for b in range(NB):
        s = to_i16(0.5 * np.sin(2 * np.pi * centre[b] * t))
        c, r = compare('tone_c%02d' % b, v, s)
        last = c[NT - 1]; am = int(np.argmax(last)); ok_arg &= am == b; peaks.append(last[am])
        print('%5.0f ' % centre[b] + ''.join(('%6.2f' % x) + ('*' if i == am else ' ') for i, x in enumerate(last)))
    check(ok_arg, '%s: argmax band == tone band for all %d centre tones' % (v, NB))
    tol = 0.05 if v == 'biquad' else 0.6
    check(max(abs(p - math.log(0.25)) for p in peaks) < tol,
          '%s: peak level within %.2f nat of ln(A^2) = %.3f (measured %.3f..%.3f)' % (v, tol, math.log(0.25), min(peaks), max(peaks)))

# 3. tones at arbitrary frequencies -> argmax band == analytic argmax
for f in (440.0, 1000.0, 3000.0):
    s = to_i16(0.3 * np.sin(2 * np.pi * f * t))
    for v in BIN:
        c, r = compare('tone_%d' % int(f), v, s); am = int(np.argmax(c[NT - 1]))
        gains = [biquad_gain(f, b) for b in range(NB)] if v == 'biquad' else [tri_weight(f, b) for b in range(NB)]
        exp_b = int(np.argmax(gains))
        check(am == exp_b, 'tone %4.0f Hz/%s: argmax band %d == analytic band %d (centre %.0f Hz)' % (f, v, am, exp_b, centre[exp_b]))

# 4. onset at 0.55 s -> segments 0..5 exactly floor, 7..11 steady
s = to_i16(np.where(t >= 0.55, 0.5 * np.sin(2 * np.pi * 1000 * t), 0))
for v in BIN:
    c, r = compare('onset', v, s); b = int(np.argmax(c[NT - 1]))
    check(np.all(c[:6] == -16.118), 'onset/%s: segments 0..5 all at the floor' % v)
    check(np.ptp(c[7:, b]) < 0.05 and c[7:, b].mean() > -2, 'onset/%s: segments 7..11 steady in band %d (%.3f..%.3f)' % (v, b, c[7:, b].min(), c[7:, b].max()))

# 5. white noise at -20 dBFS -> every band above the floor
rng = np.random.default_rng(1); noise = to_i16(np.clip(rng.normal(0, 0.1, NS), -1, 1))
for v in BIN:
    c, r = compare('noise', v, noise)
    check(c.min() > -12, 'noise/%s: all bands above floor (min %.2f, max %.2f)' % (v, c.min(), c.max()))
    print('noise/%s band means: %s' % (v, ' '.join('%.1f' % x for x in c.mean(0))))

# 6. short input (0.5 s) is zero-padded; 7. long input (2 s) is truncated to the first second
tone1k = 0.5 * np.sin(2 * np.pi * 1000 * t); s_short = to_i16(tone1k[:8000])
s_long = to_i16(np.concatenate([tone1k, 0.5 * np.sin(2 * np.pi * 3000 * t)]))
for v in BIN:
    c, r = compare('short', v, s_short)
    check(np.all(c[7:] == -16.118) and c[:6].max() > -2, 'short/%s: second half at floor, first half lit' % v)
    _, _, o1 = feats(BIN[v][0] + [write_raw('tone1k_' + v, to_i16(tone1k))])
    _, _, o2 = feats(BIN[v][0] + [write_raw('long_' + v, s_long)])
    check(o1 == o2, 'long/%s: 2 s input gives the same row as its first second' % v)
    # 8. WAV container, WAV with an extra odd-length chunk, bad formats
    w1 = write_wav('tone1k', to_i16(tone1k)); w2 = write_wav('tone1k_list', to_i16(tone1k), extra_chunk=True)
    _, _, ow1 = feats(BIN[v][0] + [w1]); _, _, ow2 = feats(BIN[v][0] + [w2])
    check(ow1 == o1 and ow2 == o1, 'wav/%s: WAV and WAV+LIST chunk give the same row as raw' % v)
    _, _, ostdin = feats(BIN[v][0], open(w1, 'rb').read())
    check(ostdin == o1, 'wav/%s: same row from stdin' % v)
    for bad, kw in (('stereo', dict(channels=2)), ('8k', dict(rate=8000)), ('8bit', dict(bits=8))):
        rc, out, err = run(BIN[v][0] + [write_wav('bad_' + bad, to_i16(tone1k), **kw)])
        check(rc != 0 and 'need 16 kHz 16-bit mono' in err, 'wav/%s: %s WAV refused (%s)' % (v, bad, err.strip()))
    rc, out, err = run(BIN[v][0] + [os.path.join(TD, 'nonexistent.wav')])
    check(rc != 0 and 'cannot open' in err, 'io/%s: missing file refused (%s)' % (v, err.strip()))
    # 9. -n: per-band mean over segments is zero; matches reference
    c, r = compare('noise_norm', v, noise, norm=True)
    check(np.abs(c.mean(0)).max() < 2e-3, '-n/%s: per-band means over time |.| < 0.002 (max %.4f)' % (v, np.abs(c.mean(0)).max()))
    # 10. label appended; "-" means stdin
    _, toks, _ = feats(BIN[v][0] + [w1, '2']); check(len(toks) == NT * NB + 1 and toks[-1] == '2', 'label/%s: FILE LABEL -> %d tokens, last "2"' % (v, len(toks)))
    _, toks, _ = feats(BIN[v][0] + ['-n', '-', '3'], open(w1, 'rb').read()); check(len(toks) == NT * NB + 1 and toks[-1] == '3', 'label/%s: -n - LABEL from stdin' % v)

# 11. end to end through the merged binaries: 4 synthetic "commands" (tone pairs with noise, random gain, onset)
print('\nend-to-end: 4 classes x 20 train / 10 test through `uai32_X feat` -> `uai32_X train/test`')
classes = [(300, 2200), (600, 1500), (900, 3500), (1800, 2600)]
def utter(cls, rng):
    f1, f2 = classes[cls]; a = rng.uniform(0.1, 0.5); on = rng.uniform(0.05, 0.4); dur = rng.uniform(0.3, 0.5)
    env = ((t >= on) & (t < on + dur)).astype(float)
    x = a * env * (np.sin(2 * np.pi * f1 * t) + 0.5 * np.sin(2 * np.pi * f2 * t)) / 1.5 + rng.normal(0, 0.01, NS)
    return to_i16(np.clip(x, -1, 1))
for v in BIN:
    rng = np.random.default_rng(7); exe = BIN[v][1][0]
    for split, n in (('train', 20), ('test', 10)):
        rows = []
        for cls in range(4):
            for i in range(n):
                p = write_wav('e2e_%s_%d_%d' % (split, cls, i), utter(cls, rng))
                rows.append(feats([exe, 'feat', '-n', p, str(cls)])[2])
        open(os.path.join(TD, 'e2e_%s_%s.txt' % (v, split)), 'w').write(''.join(rows))
    model = os.path.join(TD, 'e2e_%s.model' % v)
    rc, out, err = run([exe, 'train', os.path.join(TD, 'e2e_%s_train.txt' % v), model, '16', '40', '0.05', '1'])
    check(rc == 0, 'e2e/%s: train ok: %s' % (v, out.splitlines()[0] + ' ... ' + out.splitlines()[-1]))
    rc, out, err = run([exe, 'test', os.path.join(TD, 'e2e_%s_test.txt' % v), model])
    acc = float(out.split('=')[-1].strip().rstrip('%')); check(rc == 0 and acc >= 90, 'e2e/%s (>=90%% required): %s (model %d bytes, exe %d bytes, combined %d)' % (
        v, out.strip(), os.path.getsize(model), os.path.getsize(exe), os.path.getsize(model) + os.path.getsize(exe)))

print('\n%d checks failed' % len(fails) if fails else '\nALL CHECKS PASSED')
sys.exit(1 if fails else 0)
