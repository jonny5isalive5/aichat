"""select_clips.py ZIP OUTDIR [SEED] -- pick the pilot validation clips from mini_speech_commands.zip (untrusted data).
OUTDIR must not exist.  Writes OUTDIR/raw/<role>_<word>_<file>.raw (raw signed 16-bit LE mono PCM at 16 kHz, native
length, no padding) and OUTDIR/clips.txt: role word zipname samples sha256(raw).  Deterministic for a given SEED.
Commands yes/no/stop/go (labels 0..3): 5 enrolment + 10 query clips each, query speakers absent from enrolment, as in the
benchmark's split; unfamiliar words up/down/left/right: 5 clips each.  Run with python3 -I from outside OUTDIR."""
import sys, os, re, io, wave, zipfile, hashlib
import numpy as np
zpath, out = sys.argv[1], sys.argv[2]; seed = int(sys.argv[3]) if len(sys.argv) > 3 else 1
CMDS = ['yes', 'no', 'stop', 'go']; NEG = ['up', 'down', 'left', 'right']; N_ENROL, N_QUERY, N_NEG = 5, 10, 5
os.makedirs(os.path.join(out, 'raw'))                      # fails if OUTDIR exists: a fresh directory every time
z = zipfile.ZipFile(zpath); pat = re.compile(r'^mini_speech_commands/([a-z]+)/([0-9a-f]+)_nohash_([0-9]+)\.wav$')
by_word = {}
for info in z.infolist():
    m = pat.match(info.filename)
    if m and not info.is_dir(): by_word.setdefault(m.group(1), []).append((info.filename, m.group(2)))
rng = np.random.default_rng(seed); picks = []
for lab, w in enumerate(CMDS):
    files = sorted(by_word[w]); idx = rng.choice(len(files), N_ENROL, replace=False)
    enrol = [files[i] for i in idx]; spk = {s for _, s in enrol}
    rest = [f for f in files if f[1] not in spk]; idx = rng.choice(len(rest), N_QUERY, replace=False)
    picks += [('enrol', w, lab, f) for f in enrol] + [('query', w, lab, rest[i]) for i in idx]
for w in NEG:
    files = sorted(by_word[w]); idx = rng.choice(len(files), N_NEG, replace=False)
    picks += [('neg', w, -1, files[i]) for i in idx]
with open(os.path.join(out, 'clips.txt'), 'w') as man:
    man.write('# role word label zipname samples sha256_of_raw_pcm   (seed %d)\n' % seed)
    for role, w, lab, (name, spk) in picks:
        wv = wave.open(io.BytesIO(z.read(name)))
        if (wv.getframerate(), wv.getnchannels(), wv.getsampwidth()) != (16000, 1, 2): sys.exit('unexpected format: ' + name)
        pcm = wv.readframes(wv.getnframes())
        fn = '%s_%s_%s.raw' % (role, w, os.path.basename(name)[:-4])
        open(os.path.join(out, 'raw', fn), 'wb').write(pcm)
        man.write('%s %s %d %s %d %s\n' % (role, w, lab, name, len(pcm) // 2, hashlib.sha256(pcm).hexdigest()))
print('wrote', len(picks), 'clips to', out)
