"""Tiling surface textures for the course materials (Scripts/apply_floating_islands.py imports them).

    python Art/Blender/surface_textures.py        (numpy + Pillow; the bpy venv has both)

Writes Art/Textures/:
  T_Sand_Color.png   1 m of bunker sand, 1024 px: loose grains in clumps, cream / tan / a few dark and white grains
  T_Sand_Normal.png  its bumps (linear RGB normal map, z up)
  T_Turf.png         mown grass: fine blade streaks, greyscale around 0.8 (a brightness multiplier)
  T_RoughTurf.png    long grass: coarser, clumpier streaks
  T_Macro.png        smooth large-scale noise the materials sample at several sizes for patchy colour
Every texture wraps seamlessly: the noise is made in frequency space, so it is periodic by construction.
"""
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / 'Textures'
rng = np.random.default_rng(7)


def spectral(n, low, high, aniso=(1.0, 1.0), power=1.0, seed=0):
    """Periodic noise with energy between wavelengths n/low and n/high pixels, stretched by aniso (x, y)."""
    r = np.random.default_rng(seed)
    fx = np.fft.fftfreq(n)[None, :] * n / aniso[0]
    fy = np.fft.fftfreq(n)[:, None] * n / aniso[1]
    f = np.sqrt(fx ** 2 + fy ** 2)
    band = np.exp(-((np.log(np.maximum(f, 1e-6)) - np.log(np.sqrt(low * high))) / np.log(high / low) * 2) ** 2)
    band[0, 0] = 0
    spectrum = band / np.maximum(f, 1) ** power * np.exp(2j * np.pi * r.random((n, n)))
    out = np.real(np.fft.ifft2(spectrum))
    return (out - out.mean()) / (out.std() + 1e-9)


def save_grey(name, value):
    Image.fromarray((np.clip(value, 0, 1) * 255).astype(np.uint8)).save(OUT / f'{name}.png')


def sand():
    n = 1024  # 1 m: ~1 mm a pixel
    clumps = spectral(n, 20, 80, seed=1)            # 1-5 cm lumps and hollows
    ripples = spectral(n, 4, 12, seed=2)            # footprints / broad unevenness
    grains = spectral(n, 250, 500, seed=3)          # single grains
    grit = spectral(n, 90, 250, seed=4)
    height = 0.55 * clumps + 0.35 * ripples + 0.28 * grit + 0.18 * grains
    # Lumps are rounder on top than in the hollows between them.
    height = np.tanh(height * 0.9)

    light = np.array([0.93, 0.85, 0.70])
    tan = np.array([0.80, 0.69, 0.53])
    dark = np.array([0.46, 0.39, 0.31])
    white = np.array([0.98, 0.96, 0.90])
    mix = np.clip(0.5 + 0.35 * spectral(n, 30, 120, seed=5) + 0.25 * grains, 0, 1)[..., None]
    colour = tan * (1 - mix) + light * mix
    specks = rng.random((n, n))
    colour = np.where((specks < 0.018)[..., None], dark, colour)
    colour = np.where((specks > 0.975)[..., None], white, colour)
    # Hollows read darker (self-shadowed), crests lighter.
    colour = colour * (0.82 + 0.2 * np.clip(0.5 + 0.5 * height, 0, 1))[..., None]
    Image.fromarray((np.clip(colour, 0, 1) ** (1 / 1.0) * 255).astype(np.uint8)).save(OUT / 'T_Sand_Color.png')

    # Normal map from the height (wrap-around gradients keep it tiling).
    strength = 3.0
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * strength
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * strength
    normal = np.stack([-dx, dy, np.ones_like(dx)], -1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    Image.fromarray(((normal * 0.5 + 0.5) * 255).astype(np.uint8)).save(OUT / 'T_Sand_Normal.png')


def turf():
    n = 512  # 1 m of mown grass
    blades = spectral(n, 60, 200, aniso=(1.0, 5.0), seed=11)   # thin streaks along the mowing direction
    tufts = spectral(n, 12, 40, seed=12)
    save_grey('T_Turf', 0.8 + 0.09 * blades + 0.06 * tufts)

    long_blades = spectral(n, 25, 90, aniso=(1.0, 3.5), seed=13)
    clumps = spectral(n, 5, 18, seed=14)
    save_grey('T_RoughTurf', 0.76 + 0.12 * long_blades + 0.1 * clumps)


def macro():
    n = 512
    value = 0.5 + 0.2 * spectral(n, 2, 6, seed=21) + 0.1 * spectral(n, 6, 16, seed=22)
    save_grey('T_Macro', value)


def ball_dimples():
    """Golf ball dimples: a hex-packed grid of shallow round cups (tiles 8 across, 4 down on the ball's UVs)."""
    w, h = 256, 222  # one hex period: 8 dimples across, 4 rows of pairs down (32 px apart)
    a = w / 8
    y, x = np.mgrid[0:h, 0:w].astype(float)
    height = np.zeros((h, w))
    for oy, ox in ((0.0, 0.0), (a * 3 ** 0.5 / 2, a / 2)):
        # distance to the nearest lattice point of this sub-grid (wrapping)
        dy = (y - oy) % (a * 3 ** 0.5)
        dy = np.minimum(dy, a * 3 ** 0.5 - dy)
        dx = (x - ox) % a
        dx = np.minimum(dx, a - dx)
        r = np.sqrt(dx ** 2 + dy ** 2) / (a * 0.46)
        height = np.minimum(height, np.where(r < 1, -(1 - r ** 2), 0.0))
    dxh = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 6
    dyh = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 6
    normal = np.stack([-dxh, dyh, np.ones_like(dxh)], -1)
    normal /= np.linalg.norm(normal, axis=-1, keepdims=True)
    Image.fromarray(((normal * 0.5 + 0.5) * 255).astype(np.uint8)).save(OUT / 'T_BallDimples.png')


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    ball_dimples()
    sand()
    turf()
    macro()
    print('SURFACE TEXTURES written to', OUT)
