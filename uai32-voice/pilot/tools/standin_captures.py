#!/usr/bin/env python3
"""standin_captures.py ZIP OUTDIR SEED [--pilot-dir P] -- DRY-RUN ONLY: build a pilot manifest in record.py's format and stand-in
1.5 s "captures" from mini_speech_commands.zip (untrusted data; run with python3 -I from outside OUTDIR; OUTDIR must not exist).

The stand-in speaker is NOT one person: enrolment clips come from randomly chosen speakers, dev/test clips from speakers
absent from enrolment (speaker-independent, as the benchmark), so everything scored from this manifest only shows that the
kit runs.  Commands yes/no/stop/go (go held back), stand-in "confusables" up/down and "unrelated" left/right -- the strata
are placeholders for the pilot's pre-registered own-voice lists, not confusables of these words.
Each 1 s zip clip is placed at a seeded random offset (0-0.5 s) inside a 1.5 s capture of digital silence and written as
OUTDIR/incoming/<id>.wav, so `record.py import` exercises the host-side centring exactly as it would on real captures.
Writes OUTDIR/manifest.json + SEALED.sha256 (via record.make_manifest) and OUTDIR/standin_sources.txt (id, zip member,
offset, sha256 of the zip member's PCM) for reproducibility."""
import sys, os, re, io, wave, zipfile, hashlib, json, argparse, time
import numpy as np
ap = argparse.ArgumentParser(); ap.add_argument('zip'); ap.add_argument('out'); ap.add_argument('seed', type=int)
ap.add_argument('--pilot-dir', default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
a = ap.parse_args()
sys.path.insert(0, a.pilot_dir); import record                      # the real manifest code, so the format cannot drift
CMDS = ['yes', 'no', 'stop', 'go']; CONF = ['up', 'down']; UNREL = ['left', 'right']
os.makedirs(os.path.join(a.out, 'incoming'))                        # fails if OUTDIR exists: a fresh directory every time
man = record.make_manifest('standin-speaker-independent', a.seed, CMDS, CONF, UNREL, device='none: stand-in clips from mini_speech_commands.zip',
                           notes='DRY RUN: speaker-independent stand-in clips; proves the pipeline runs, not a pilot result')
with open(os.path.join(a.out, 'manifest.json'), 'w') as f: json.dump(man, f, indent=1, sort_keys=True)
h = record.sha256_bytes(record.canonical(man))
open(os.path.join(a.out, 'SEALED.sha256'), 'w').write('%s  manifest.json (canonical JSON, sorted keys, no spaces) sealed %s\n' % (h, man['created']))
z = zipfile.ZipFile(a.zip); pat = re.compile(r'^mini_speech_commands/([a-z]+)/([0-9a-f]+)_nohash_([0-9]+)\.wav$'); by_word = {}
for info in z.infolist():
    m = pat.match(info.filename)
    if m and not info.is_dir(): by_word.setdefault(m.group(1), []).append((info.filename, m.group(2)))
rng = np.random.default_rng([a.seed, 0x57A9])
need = {}
for it in man['items']: need.setdefault((it['phase'], it['word']), []).append(it)
# enrolment files first; their speakers are excluded from every other phase and word
enrol_spk = set(); chosen = {}
for w in CMDS:
    files = sorted(by_word[w]); idx = rng.choice(len(files), len(need[('enrol', w)]), replace=False)
    chosen[('enrol', w)] = [files[i] for i in idx]; enrol_spk |= {files[i][1] for i in idx}
for (phase, w), items in sorted(need.items()):
    if phase == 'enrol': continue
    used = {f for lst in chosen.values() for f in lst}
    pool = [f for f in sorted(by_word[w]) if f[1] not in enrol_spk and f not in used]
    idx = rng.choice(len(pool), len(items), replace=False); chosen[(phase, w)] = [pool[i] for i in idx]
with open(os.path.join(a.out, 'standin_sources.txt'), 'w') as src:
    src.write('# id phase word zip_member offset_samples sha256_of_member_pcm   (seed %d, zip sha256 %s)\n' % (a.seed, record.sha256_file(a.zip)))
    for (phase, w), items in sorted(need.items()):
        for it, (name, spk) in zip(sorted(items, key=lambda it: it['order']), chosen[(phase, w)]):
            wv = wave.open(io.BytesIO(z.read(name)))
            if (wv.getframerate(), wv.getnchannels(), wv.getsampwidth()) != (16000, 1, 2): sys.exit('unexpected format: ' + name)
            pcm = wv.readframes(wv.getnframes()); x = np.frombuffer(pcm, '<i2')[:record.SR]
            off = int(rng.integers(0, record.CAP_N - len(x) + 1)); cap = np.zeros(record.CAP_N, np.int16); cap[off:off + len(x)] = x
            record.write_wav(os.path.join(a.out, 'incoming', it['id'] + '.wav'), cap)
            src.write('%s %s %s %s %d %s\n' % (it['id'], phase, w, name, off, hashlib.sha256(pcm).hexdigest()))
print('stand-in captures: %d WAVs in %s/incoming from %d enrolment speakers (excluded elsewhere); manifest sealed %s' % (len(man['items']), a.out, len(enrol_spk), h[:16]))
