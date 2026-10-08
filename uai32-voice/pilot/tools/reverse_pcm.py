"""reverse_pcm.py IN.raw OUT.raw -- time-reverse a raw 16-bit PCM clip (one of the benchmark's synthetic 'unknown' kinds)."""
import sys, numpy as np
np.fromfile(sys.argv[1], '<i2')[::-1].tofile(sys.argv[2])
