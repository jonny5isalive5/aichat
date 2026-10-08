"""Dataset manifest statistics for the few-shot benchmark (added during preservation, 2026-10-08; not part of the
original run).  Reads the extracted wav tree and prints: per-word counts, WAV format check, clip-length statistics,
speaker-hash statistics, and whether any speaker has >= n recordings of every word of the tested command sets.
usage: python3 -I dataset_stats.py WAVDIR [--zip mini_speech_commands.zip]
WAVDIR is the directory produced by extract_zip.py (WAVDIR/<word>/<speaker>_nohash_<n>.wav)."""
import sys, os, glob, wave, hashlib, argparse, itertools, collections, zipfile
ap = argparse.ArgumentParser(); ap.add_argument('wavdir'); ap.add_argument('--zip'); a = ap.parse_args()
files = sorted(glob.glob(os.path.join(a.wavdir, '*', '*.wav')))       # same order as features.build_cache -> cache/meta.json
rel = [os.path.relpath(f, a.wavdir) for f in files]
words = [r.split(os.sep)[0] for r in rel]; spk = [os.path.basename(r).split('_')[0] for r in rel]
print('files: %d   sha256 of the newline-joined sorted relative file list: %s' % (len(files), hashlib.sha256('\n'.join(rel).encode()).hexdigest()))
if a.zip:
    h = hashlib.sha256(); s = 0
    with open(a.zip, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''): h.update(blk); s += len(blk)
    z = zipfile.ZipFile(a.zip); names = z.namelist()
    print('zip: %s  size %d bytes  sha256 %s  entries %d  wav entries %d  non-wav entries %d' % (os.path.basename(a.zip), s, h.hexdigest(), len(names), sum(n.endswith('.wav') for n in names), sum(not n.endswith('.wav') for n in names)))
    print('zip README.md (verbatim):'); print(z.read('mini_speech_commands/README.md').decode('utf-8', 'replace'))
cnt = collections.Counter(words); print('per-word counts:', dict(sorted(cnt.items())))
fmt = collections.Counter(); lens = []
for f in files:
    w = wave.open(f, 'rb'); fmt[(w.getframerate(), w.getnchannels(), w.getsampwidth())] += 1; lens.append(w.getnframes()); w.close()
print('wav formats (rate, channels, bytes/sample) -> count:', dict(fmt))
short = sum(l < 16000 for l in lens); exact = sum(l == 16000 for l in lens); longer = sum(l > 16000 for l in lens)
print('clip length (samples): min %d  max %d;  shorter than 16000: %d  exactly 16000: %d  longer: %d' % (min(lens), max(lens), short, exact, longer))
by_word_short = collections.Counter(w for w, l in zip(words, lens) if l < 16000); print('shorter-than-1s clips per word:', dict(sorted(by_word_short.items())))
hist = collections.Counter(min(l // 1600, 9) for l in lens); print('length histogram (0.1 s bins, last bin = 0.9-1.0 s):', {'%.1f-%.1f s' % (k / 10, (k + 1) / 10): v for k, v in sorted(hist.items())})
# speakers
S = set(spk); print('distinct speaker hashes: %d' % len(S))
per_word_spk = {w: len({s for s, ww in zip(spk, words) if ww == w}) for w in sorted(cnt)}; print('distinct speakers per word:', per_word_spk)
rec_per_spk = collections.Counter(spk); v = sorted(rec_per_spk.values())
print('recordings per speaker (all words): min %d  median %d  mean %.2f  max %d;  speakers with 1 recording: %d' % (v[0], v[len(v) // 2], sum(v) / len(v), v[-1], sum(x == 1 for x in v)))
sw = collections.Counter(zip(spk, words)); mx = max(sw.values()); print('max recordings of one word by one speaker: %d' % mx)
print('speakers with >= n recordings of a given word (any word):', {n: len({s for (s, w), c in sw.items() if c >= n}) for n in (1, 2, 3, 4, 5)})
def spk_with(cmds, n): return sorted({s for s in S if all(sw[(s, w)] >= n for w in cmds)})
for cmds in [('yes', 'no', 'stop'), ('up', 'down', 'go'), ('yes', 'no', 'stop', 'go')]:
    print('command set %s: speakers with >= n recordings of EVERY word: ' % '/'.join(cmds) + ', '.join('n=%d: %d' % (n, len(spk_with(cmds, n))) for n in (1, 2, 3, 4, 5)))
allw = sorted(cnt); best = max(((len(spk_with(t, 5)), t) for t in itertools.combinations(allw, 3)))
print('over all %d word triples, the largest number of speakers with >= 5 recordings of every word is %d (triple %s)' % (len(list(itertools.combinations(allw, 3))), best[0], '/'.join(best[1])))
best3 = max(((min(sw[(s, w)] for w in t), s, t) for t in itertools.combinations(allw, 3) for s in S))
print('the largest min-count over any (speaker, triple) is %d (speaker %s, triple %s)' % (best3[0], best3[1], '/'.join(best3[2])))
