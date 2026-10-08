"""Small log-mel front end, written so it can be re-implemented in C in ~150 lines.

Recipe (fixed constants):
  SR=16000, clip zero-padded/cropped to 16000 samples (1 s)
  pre-emphasis y[n] = x[n] - 0.97*x[n-1]
  frames: N=512 (32 ms), hop=256 (16 ms), periodic Hann window -> T=61 frames
  power spectrum of 512-pt FFT (257 bins)
  NB=16 triangular mel filters, 100..7600 Hz (HTK mel), unit peak
  logmel = ln(E + 1e-3)   (E in units of the full-scale-normalised waveform)
Normalisation / pooling variants are applied on top of the 61x16 log-mel matrix:
  norm 'cmn'  : subtract per-band mean over the 61 frames
  norm 'peak' : subtract the global max, floor at -12 (nat-log units ~ -52 dB)
  pool 'grid' : frames 0..59 -> 12 segments x 5 frames, mean   -> 192 values
  pool 'center': energy-centred crop of 48 frames -> 12 x 4 frames -> 192 values
  pool 'vad'  : active region (smoothed energy > max-5.0) stretched to 12 segments -> 192 values
"""
import numpy as np, wave, os, glob, json

SR = 16000; NFFT = 512; HOP = 256; NB = 16; T = 1 + (SR - NFFT) // HOP   # 61
FMIN, FMAX = 100.0, 7600.0; EPS = 1e-3; NSEG = 12

def mel(f): return 2595.0 * np.log10(1.0 + f / 700.0)
def imel(m): return 700.0 * (10.0 ** (m / 2595.0) - 1.0)

def mel_filterbank():
    edges = imel(np.linspace(mel(FMIN), mel(FMAX), NB + 2))
    bins = np.floor((NFFT + 1) * edges / SR).astype(int)
    fb = np.zeros((NB, NFFT // 2 + 1), np.float32)
    for b in range(NB):
        lo, c, hi = bins[b], bins[b + 1], bins[b + 2]
        for k in range(lo, c): fb[b, k] = (k - lo) / max(c - lo, 1)
        for k in range(c, hi): fb[b, k] = (hi - k) / max(hi - c, 1)
    return fb

FB = mel_filterbank()
WIN = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(NFFT) / NFFT)).astype(np.float32)

def read_wav(path):
    w = wave.open(path, 'rb')
    assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2
    x = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2')
    w.close()
    out = np.zeros(SR, np.int16); n = min(len(x), SR); out[:n] = x[:n]
    return out

def logmel(wavs):
    """wavs: (B, 16000) int16 or float -> (B, 61, 16) float32 log-mel."""
    x = np.asarray(wavs, np.float32)
    if wavs.dtype == np.int16: x = x / 32768.0
    x = x.reshape(-1, SR)
    y = x.copy(); y[:, 1:] -= 0.97 * x[:, :-1]
    idx = np.arange(T)[:, None] * HOP + np.arange(NFFT)[None, :]
    fr = y[:, idx] * WIN                                   # (B, T, NFFT)
    ps = np.abs(np.fft.rfft(fr, axis=-1)) ** 2             # (B, T, 257)
    E = ps @ FB.T                                          # (B, T, NB)
    return np.log(E + EPS).astype(np.float32)

def normalise(lm, mode):
    if mode == 'cmn':  return lm - lm.mean(axis=1, keepdims=True)
    if mode == 'peak': return np.maximum(lm - lm.max(axis=(1, 2), keepdims=True), -12.0)
    if mode == 'none': return lm
    raise ValueError(mode)

def frame_energy(lm):   # (B,T,NB) -> (B,T) smoothed (5-frame box) mean log energy
    e = lm.mean(axis=2)
    k = np.ones(5, np.float32) / 5
    return np.stack([np.convolve(r, k, mode='same') for r in e])

def active_region(lm, drop=5.0):
    """Start/end frame of the region where smoothed energy > max - drop (nat-log units)."""
    e = frame_energy(lm); B = e.shape[0]
    s = np.zeros(B, int); t = np.full(B, T, int)
    for b in range(B):
        on = np.where(e[b] > e[b].max() - drop)[0]
        s[b], t[b] = on[0], on[-1] + 1
    return s, t

def pool(lm, mode):
    """(B,T,NB) -> (B, NSEG*NB) fixed vector."""
    B = lm.shape[0]
    if mode == 'grid':
        return lm[:, :60].reshape(B, NSEG, 5, NB).mean(axis=2).reshape(B, -1)
    if mode == 'center':
        e = frame_energy(lm); L = 48
        out = np.zeros((B, L, NB), np.float32)
        for b in range(B):
            # centre of a 48-frame window that maximises enclosed energy (box filter)
            c = np.convolve(e[b] - e[b].min(), np.ones(L), mode='valid').argmax()   # start of best window
            seg = lm[b, c:c + L]; out[b, :len(seg)] = seg
            if len(seg) < L: out[b, len(seg):] = lm[b].min()
        return out.reshape(B, NSEG, 4, NB).mean(axis=2).reshape(B, -1)
    if mode == 'vad':
        s, t = active_region(lm)
        out = np.zeros((B, NSEG, NB), np.float32)
        for b in range(B):
            a, z = s[b], max(t[b], s[b] + NSEG)
            z = min(z, T); a = max(0, min(a, z - 2))
            seg = lm[b, a:z]; n = len(seg)
            bounds = np.linspace(0, n, NSEG + 1)
            for i in range(NSEG):
                lo, hi = int(np.floor(bounds[i])), int(np.ceil(bounds[i + 1]))
                out[b, i] = seg[lo:max(hi, lo + 1)].mean(axis=0)
        return out.reshape(B, -1)
    raise ValueError(mode)

def build_cache(wavdir, outdir):
    files = sorted(glob.glob(os.path.join(wavdir, '*', '*.wav')))
    words = [f.split(os.sep)[-2] for f in files]
    spk = [os.path.basename(f).split('_')[0] for f in files]
    W = np.stack([read_wav(f) for f in files])
    LM = np.concatenate([logmel(W[i:i + 500]) for i in range(0, len(W), 500)])
    np.save(os.path.join(outdir, 'waves.npy'), W)
    np.save(os.path.join(outdir, 'logmel.npy'), LM)
    json.dump({'files': [os.path.relpath(f, wavdir) for f in files], 'words': words, 'speakers': spk},
              open(os.path.join(outdir, 'meta.json'), 'w'))
    print('cached', W.shape, LM.shape, 'words', sorted(set(words)))

if __name__ == '__main__':
    import sys
    build_cache(sys.argv[1], sys.argv[2])
