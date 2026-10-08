"""Frame-feature variants on top of the cached 61x16 log-mel, plus score calibrations."""
import numpy as np, features as F
NC = 12
DCT = np.array([[np.cos(np.pi * c * (b + 0.5) / F.NB) for b in range(F.NB)] for c in range(F.NB)], np.float32) * np.sqrt(2.0 / F.NB)

def frames(LM, feat):
    """LM (B,61,16) raw log-mel -> (B,61,D) normalised frame features."""
    if feat.startswith('mfcc'):
        X = LM @ DCT.T; X = X[:, :, 1:NC + 1]                     # drop c0, keep c1..c12
    elif feat.startswith('lmclamp'):
        X = np.maximum(LM - LM.max(axis=(1, 2), keepdims=True), -7.0)
    else:
        X = LM
    if feat.endswith('cmn'):  X = X - X.mean(axis=1, keepdims=True)
    if feat.endswith('cmvn'): X = (X - X.mean(axis=1, keepdims=True)) / (X.std(axis=1, keepdims=True) + 1e-3)
    return X.astype(np.float32)

def energy(LM): return F.frame_energy(LM)

def pool_center(X, e, L=48, nseg=12):
    B, T, D = X.shape; out = np.zeros((B, L, D), np.float32)
    for b in range(B):
        c = np.convolve(e[b] - e[b].min(), np.ones(L), mode='valid').argmax()
        seg = X[b, c:c + L]; out[b, :len(seg)] = seg
    return out.reshape(B, nseg, L // nseg, D).mean(axis=2).reshape(B, -1)

def pool_grid(X, nseg=12):
    B, T, D = X.shape; return X[:, :60].reshape(B, nseg, 5, D).mean(axis=2).reshape(B, -1)

def calibrate(dcls, dall, kind):
    """dcls (n,k) per-class distances (lower = closer); dall (n,m) distances to all templates.  Returns pred, score."""
    srt = np.sort(dcls, 1); pred = dcls.argmin(1)
    if kind == 'min':    return pred, -srt[:, 0]
    if kind == 'margin': return pred, srt[:, 1] - srt[:, 0]
    if kind == 'ratio':  return pred, srt[:, 1] / (srt[:, 0] + 1e-9)
    if kind == 'tnorm':  return pred, (dall.mean(1) - srt[:, 0]) / (dall.std(1) + 1e-9)
    raise ValueError(kind)
