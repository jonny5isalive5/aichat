#!/usr/bin/env python3
"""record.py -- prompter and recorder for the enrolled-speaker, same-microphone pilot (python3 -I, numpy + stdlib only).

The label manifest is written ONCE (`init`) with every prompt of every phase in a fixed, seeded, randomised order and an
opaque 12-hex-digit id per item; its SHA-256 is written next to it (SEALED.sha256) and run_pilot.py refuses a manifest
whose hash changed.  Clips are named by id only: nothing the recogniser or the person running it sees carries a label.

    record.py init   MANIFEST --speaker ID --seed N --commands w1,w2,w3,w4 --confusables a,b,... --unrelated x,y,...
                     [--enrol 5] [--dev 10] [--test 30] [--dev-neg 100] [--test-neg 300] [--device NAME]
    record.py record MANIFEST PHASE [--backend auto|sounddevice|arecord|sox|manual] [--device NAME] [--auto] [--gap S]
    record.py import MANIFEST --from DIR          hand-recorded or stand-in captures DIR/<id>.wav -> centred raw clips
    record.py status MANIFEST                     progress per phase
    record.py centre IN.wav OUT.raw               the centring step alone (what import and record do to every capture)

Phases (per speaker; separate days if at all possible): enrol = 5 x 4 commands (the 4th command is recorded now but held
back by run_pilot.py until the fourth-command step); dev = 10 x 4 commands + DEV_NEG own-voice negatives; test = 30 x 4
commands + TEST_NEG own-voice negatives.  Negatives are the pre-registered confusables (3 per command, written in the
manifest before any recording) and unrelated words, spread as evenly as the counts allow.  Each phase's prompt order is a
seeded permutation of positives and negatives, interleaved.  The script resumes: items whose clip exists with the sha256
noted in recordings.json are skipped.

Capture = 1.5 s (24,000 samples) at 16 kHz mono 16-bit.  DISCLOSED HOST-SIDE SEGMENTATION, the only one in the pilot: the
host finds the energy centre of the utterance in the 1.5 s capture (midpoint of the frames whose 10 ms energy is within
25 dB of the peak frame) and writes the 1.0 s window centred on it as raw signed 16-bit little-endian PCM, zero-padded
only if the window would leave the capture.  Nothing else is done to the audio: no gain change, trimming, filtering or
noise suppression.  The centre sample, the active region and the capture peak are logged per clip in recordings.json.

Backends: 'sounddevice' (python module) if importable, else 'arecord' (ALSA), else 'sox'/'rec'; otherwise 'manual' prints
exact instructions for recording 1.5 s WAV files by hand into DIR/<id>.wav and importing them with `import`.
"""
import sys, os, json, time, hashlib, argparse, subprocess, shutil, wave, io, tempfile, struct
import numpy as np

SR = 16000; CAP_S = 1.5; CLIP_S = 1.0; CAP_N = int(SR * CAP_S); CLIP_N = int(SR * CLIP_S)
FRAME = 160                                   # 10 ms energy frames for the centring step
ACTIVE_DB = 25.0                              # a frame is 'active' when within this many dB of the peak frame
FORMAT = 'uai32-voice pilot manifest v1'
PHASES = ['enrol', 'dev', 'test']

# ---------------------------------------------------------------- manifest ----------------------------------------------------------------
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 16), b''): h.update(chunk)
    return h.hexdigest()

def sha256_bytes(b): return hashlib.sha256(b).hexdigest()

def canonical(obj): return json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()

def make_manifest(speaker, seed, commands, confusables, unrelated, enrol=5, dev=10, test=30, dev_neg=100, test_neg=300, device='', notes=''):
    """The sealed label manifest: every item of every phase with an opaque id, in the seeded prompt order."""
    commands = list(commands); confusables = list(confusables); unrelated = list(unrelated)
    if len(commands) != 4: raise SystemExit('exactly 4 commands: three enrolled first and the fourth held back')
    if len(set(commands + confusables + unrelated)) != len(commands) + len(confusables) + len(unrelated): raise SystemExit('a word appears twice')
    if not confusables and (dev_neg or test_neg): raise SystemExit('pre-register the confusables before recording')
    rng = np.random.default_rng([int(seed), 0x5EA1])
    counts = {'enrol': (enrol, 0), 'dev': (dev, dev_neg), 'test': (test, test_neg)}
    items = []
    for pi, phase in enumerate(PHASES):
        per_cmd, n_neg = counts[phase]
        lst = [dict(phase=phase, kind='command', label=c, word=w, stratum='command') for c, w in enumerate(commands) for _ in range(per_cmd)]
        # negatives: 60% confusables / 40% unrelated (rounded), each list cycled so every word is used as evenly as possible
        n_conf = int(round(0.6 * n_neg)) if unrelated else n_neg; n_unrel = n_neg - n_conf
        for j in range(n_conf): lst.append(dict(phase=phase, kind='negative', label=-1, word=confusables[j % len(confusables)], stratum='confusable'))
        for j in range(n_unrel): lst.append(dict(phase=phase, kind='negative', label=-1, word=unrelated[j % len(unrelated)], stratum='unrelated'))
        order = rng.permutation(len(lst))
        for pos, k in enumerate(order):
            it = dict(lst[k]); it['order'] = pos; items.append(it)
    ids = set()
    for it in items:                                   # opaque ids: random, assigned in prompt order, unique
        while True:
            i = ''.join('%02x' % b for b in rng.integers(0, 256, 6))
            if i not in ids: ids.add(i); break
        it['id'] = i; it['file'] = 'clips/%s.raw' % i
    man = dict(format=FORMAT, speaker=speaker, seed=int(seed), created=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               device=device, notes=notes, sample_rate=SR, capture_seconds=CAP_S, clip_seconds=CLIP_S,
               commands=commands, held_back_command=3, confusables=confusables, unrelated=unrelated,
               counts={p: dict(per_command=counts[p][0], negatives=counts[p][1]) for p in PHASES}, items=items)
    return man

def load_manifest(path, verify=True):
    man = json.load(open(path))
    if man.get('format') != FORMAT: raise SystemExit('not a pilot manifest: ' + path)
    if verify:
        seal = os.path.join(os.path.dirname(os.path.abspath(path)), 'SEALED.sha256')
        if not os.path.exists(seal): raise SystemExit('missing ' + seal + ' (the manifest was not sealed by `record.py init`)')
        want = open(seal).read().split()[0]
        got = sha256_bytes(canonical(man))
        if want != got: raise SystemExit('manifest hash %s does not match SEALED.sha256 %s: the label manifest was edited after sealing' % (got[:16], want[:16]))
    return man

def write_json_atomic(path, obj):
    d = os.path.dirname(os.path.abspath(path)); fd, tmp = tempfile.mkstemp(dir=d, prefix='.tmp', suffix='.json')
    with os.fdopen(fd, 'w') as f: json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)

def rec_path(manifest_path): return os.path.join(os.path.dirname(os.path.abspath(manifest_path)), 'recordings.json')
def clip_dir(manifest_path): return os.path.join(os.path.dirname(os.path.abspath(manifest_path)), 'clips')

def load_recordings(manifest_path):
    p = rec_path(manifest_path)
    return json.load(open(p)) if os.path.exists(p) else {}

def is_done(manifest_path, rec, it):
    """recorded = an entry in recordings.json AND the clip exists with that sha256 (so a deleted clip is re-recorded)."""
    r = rec.get(it['id']); f = os.path.join(os.path.dirname(os.path.abspath(manifest_path)), it['file'])
    return bool(r) and os.path.exists(f) and os.path.getsize(f) == 2 * CLIP_N and sha256_file(f) == r['sha256']

# ---------------------------------------------------------------- centring ----------------------------------------------------------------
def analyse(x):
    """x int16 capture -> dict(centre, first, last frame, active_ms, peak_dbfs, edge warning).  The one host-side segmentation step."""
    x = np.asarray(x, np.int16); n = len(x) // FRAME
    if n < 1: return None
    fr = (x[:n * FRAME].astype(np.float32) / 32768.0).reshape(n, FRAME)
    e = 10 * np.log10((fr ** 2).mean(1) + 1e-10)                      # frame energy in dB
    act = np.where(e >= e.max() - ACTIVE_DB)[0]
    first, last = int(act[0]), int(act[-1])
    centre = int(round((first + last + 1) * FRAME / 2))
    peak = float(np.abs(x).max()) / 32768.0
    return dict(centre_sample=centre, active_first_ms=first * 10, active_last_ms=(last + 1) * 10, active_ms=(last - first + 1) * 10,
                peak_dbfs=round(20 * np.log10(peak + 1e-9), 1), floor_db=round(float(np.percentile(e, 20)), 1), peak_db=round(float(e.max()), 1),
                edge=(first * FRAME < 0.05 * SR) or ((last + 1) * FRAME > len(x) - 0.05 * SR))

def centre_clip(x):
    """int16 capture of any length -> (int16 clip of exactly CLIP_N samples centred on the energy centre, analysis dict, start sample)."""
    x = np.asarray(x, np.int16); a = analyse(x)
    if a is None: raise SystemExit('capture too short to analyse')
    start = a['centre_sample'] - CLIP_N // 2
    out = np.zeros(CLIP_N, np.int16)
    lo, hi = max(start, 0), min(start + CLIP_N, len(x))
    if hi > lo: out[lo - start:hi - start] = x[lo:hi]
    a['window_start_sample'] = int(start); a['padded_samples'] = int(CLIP_N - max(hi - lo, 0))
    return out, a, start

def qa_warnings(a):
    w = []
    if a['peak_dbfs'] < -30: w.append('very quiet (peak %.0f dBFS): speak closer or raise the gain' % a['peak_dbfs'])
    if a['peak_dbfs'] > -0.5: w.append('clipped (peak %.1f dBFS): lower the gain' % a['peak_dbfs'])
    if a['peak_db'] - a['floor_db'] < 15: w.append('low signal-to-floor (%.0f dB): noisy room or no speech' % (a['peak_db'] - a['floor_db']))
    if a['active_ms'] > 1000: w.append('active region %d ms is longer than the 1 s window: say it shorter' % a['active_ms'])
    if a['edge']: w.append('utterance touches the capture edge: wait for the beep, then speak')
    if a['padded_samples']: w.append('window left the capture, %d samples zero-padded' % a['padded_samples'])
    return w

# ---------------------------------------------------------------- audio i/o ----------------------------------------------------------------
def read_wav(path):
    w = wave.open(path, 'rb')
    if (w.getframerate(), w.getnchannels(), w.getsampwidth()) != (SR, 1, 2):
        raise SystemExit('%s: need %d Hz mono 16-bit WAV, got %d Hz %d ch %d bytes/sample' % (path, SR, w.getframerate(), w.getnchannels(), w.getsampwidth()))
    x = np.frombuffer(w.readframes(w.getnframes()), '<i2'); w.close()
    return x

def write_wav(path, x):
    w = wave.open(path, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(np.asarray(x, '<i2').tobytes()); w.close()

def pick_backend(name):
    if name != 'auto': return name
    try:
        import sounddevice  # noqa: F401
        return 'sounddevice'
    except Exception: pass
    if shutil.which('arecord'): return 'arecord'
    if shutil.which('rec') or shutil.which('sox'): return 'sox'
    return 'manual'

def capture(backend, device):
    """Record CAP_N samples; returns int16 array."""
    if backend == 'sounddevice':
        import sounddevice as sd
        x = sd.rec(CAP_N, samplerate=SR, channels=1, dtype='int16', device=device or None); sd.wait()
        return x.reshape(-1)[:CAP_N]
    if backend == 'arecord':
        cmd = ['arecord', '-q', '-f', 'S16_LE', '-r', str(SR), '-c', '1', '-t', 'raw', '-s', str(CAP_N)] + (['-D', device] if device else []) + ['-']
    elif backend == 'sox':
        exe = 'rec' if shutil.which('rec') else 'sox'
        cmd = [exe, '-q'] + ([] if exe == 'rec' else ['-d']) + ['-r', str(SR), '-c', '1', '-b', '16', '-e', 'signed-integer', '-t', 'raw', '-', 'trim', '0', str(CAP_S)]
        if device and exe == 'rec': os.environ['AUDIODEV'] = device
    else:
        raise SystemExit('no capture backend')
    try: p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    except FileNotFoundError: raise SystemExit('%s is not installed: use --backend auto (picks what exists) or manual' % cmd[0])
    if p.returncode: raise SystemExit('%s failed: %s' % (cmd[0], p.stderr.decode(errors='replace').strip()))
    x = np.frombuffer(p.stdout[:2 * CAP_N], '<i2')
    if len(x) < CAP_N // 2: raise SystemExit('%s returned only %d samples' % (cmd[0], len(x)))
    return x

def manual_instructions(manifest_path, man, todo):
    d = os.path.dirname(os.path.abspath(manifest_path)); inc = os.path.join(d, 'incoming')
    print('No capture backend (python module sounddevice, arecord, sox/rec) is available.  Record by hand:')
    print('  1. For each id below, record ONE 1.5 s WAV: 16,000 Hz, mono, 16-bit PCM, named incoming/<id>.wav under %s' % d)
    print('     e.g.  arecord -f S16_LE -r 16000 -c 1 -d 2 incoming/<id>.wav   (any length >= 1.5 s is accepted; only the')
    print('     first 1.5 s is used).  Same microphone, same room, same distance, AGC/noise suppression OFF for every clip.')
    print('  2. Prompt yourself in EXACTLY this order and say only the word shown, once, after a beep or count-in:')
    for it in todo: print('     %s  %s' % (it['id'], it['word'].upper()))
    print('  3. Then run:  python3 -I record.py import %s --from %s' % (manifest_path, inc))
    print('     which centres each capture into clips/<id>.raw and logs it in recordings.json (see --help).')
    os.makedirs(inc, exist_ok=True)
    with open(os.path.join(inc, 'PROMPTS_%s.txt' % todo[0]['phase']), 'w') as f:
        for it in todo: f.write('%s %s\n' % (it['id'], it['word']))
    print('  (the id/word list was also written to incoming/PROMPTS_%s.txt; it contains labels, keep it out of the clips directory)' % todo[0]['phase'])

# ---------------------------------------------------------------- commands ----------------------------------------------------------------
def cmd_init(a):
    if os.path.exists(a.manifest): raise SystemExit('%s exists; a sealed manifest is never overwritten (choose another directory)' % a.manifest)
    man = make_manifest(a.speaker, a.seed, a.commands.split(','), [w for w in a.confusables.split(',') if w], [w for w in a.unrelated.split(',') if w],
                        a.enrol, a.dev, a.test, a.dev_neg, a.test_neg, a.device, a.notes)
    d = os.path.dirname(os.path.abspath(a.manifest)); os.makedirs(os.path.join(d, 'clips'), exist_ok=True)
    with open(a.manifest, 'w') as f: json.dump(man, f, indent=1, sort_keys=True)
    h = sha256_bytes(canonical(man))
    open(os.path.join(d, 'SEALED.sha256'), 'w').write('%s  manifest.json (canonical JSON, sorted keys, no spaces) sealed %s\n' % (h, man['created']))
    n = {p: sum(it['phase'] == p for it in man['items']) for p in PHASES}
    print('sealed manifest %s: speaker %s, seed %d, %d items (%s); sha256 %s' % (a.manifest, a.speaker, a.seed, len(man['items']),
          ', '.join('%s %d' % kv for kv in n.items()), h))
    print('commands %s (the 4th, %r, is held back until the fourth-command step); confusables %s; unrelated %s' % (man['commands'], man['commands'][3], man['confusables'], man['unrelated']))

def record_item(manifest_path, man, rec, it, x, backend, source=''):
    clip, a, start = centre_clip(x)
    d = os.path.dirname(os.path.abspath(manifest_path)); f = os.path.join(d, it['file']); os.makedirs(os.path.dirname(f), exist_ok=True)
    clip.astype('<i2').tofile(f)
    entry = dict(sha256=sha256_file(f), bytes=2 * CLIP_N, capture_samples=int(len(x)), capture_sha256=sha256_bytes(np.asarray(x, '<i2').tobytes()),
                 backend=backend, source=source, recorded=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), retakes=rec.get(it['id'], {}).get('retakes', -1) + 1, **a)
    rec[it['id']] = entry; write_json_atomic(rec_path(manifest_path), rec)
    return entry

def cmd_record(a):
    man = load_manifest(a.manifest); rec = load_recordings(a.manifest)
    if a.phase not in PHASES: raise SystemExit('PHASE is one of ' + ', '.join(PHASES))
    items = sorted([it for it in man['items'] if it['phase'] == a.phase], key=lambda it: it['order'])
    todo = [it for it in items if not is_done(a.manifest, rec, it)]
    print('phase %s: %d items, %d recorded, %d to do' % (a.phase, len(items), len(items) - len(todo), len(todo)))
    if not todo: return
    backend = pick_backend(a.backend); print('backend:', backend, ('device ' + a.device) if a.device else '')
    if backend == 'manual': manual_instructions(a.manifest, man, todo); return
    print('Same microphone, same room, same distance as every other session; AGC and noise suppression OFF.')
    print('For each prompt: wait for REC, say the word once, naturally.  Enter = keep, r = retake, q = quit (resume later).')
    for n, it in enumerate(todo):
        while True:
            print('\n[%s %d/%d]  say:   %s' % (a.phase, it['order'] + 1, len(items), it['word'].upper()))
            time.sleep(a.gap); sys.stdout.write('\a  REC\n'); sys.stdout.flush()
            x = capture(backend, a.device)
            e = record_item(a.manifest, man, rec, it, x, backend)
            w = qa_warnings(e)
            print('  centre %.2f s, active %d ms, peak %.0f dBFS, floor %.0f dB%s' % (e['centre_sample'] / SR, e['active_ms'], e['peak_dbfs'], e['floor_db'],
                  ('; WARNING: ' + '; '.join(w)) if w else ''))
            if a.auto:
                if w and e['retakes'] < 2: continue
                break
            k = input('  Enter = keep, r = retake, q = quit: ').strip().lower()
            if k == 'q': print('stopped; run the same command again to resume'); return
            if k != 'r': break
    print('phase %s complete: %d/%d recorded' % (a.phase, sum(is_done(a.manifest, rec, it) for it in items), len(items)))

def cmd_import(a):
    man = load_manifest(a.manifest); rec = load_recordings(a.manifest); n = 0; miss = []
    for it in sorted(man['items'], key=lambda it: (PHASES.index(it['phase']), it['order'])):
        if is_done(a.manifest, rec, it): continue
        src = os.path.join(a.src, it['id'] + '.wav')
        if not os.path.exists(src): miss.append(it); continue
        x = read_wav(src)[:CAP_N]
        e = record_item(a.manifest, man, rec, it, x, 'import', source=os.path.relpath(src, os.path.dirname(os.path.abspath(a.manifest))))
        w = qa_warnings(e); n += 1
        if w and not a.quiet: print('%s %s: WARNING %s' % (it['id'], it['phase'], '; '.join(w)))
    print('imported %d captures; %d items still without a capture%s' % (n, len(miss), (': ' + ' '.join(it['id'] for it in miss[:10]) + (' ...' if len(miss) > 10 else '')) if miss else ''))

def cmd_status(a):
    man = load_manifest(a.manifest); rec = load_recordings(a.manifest)
    for p in PHASES:
        items = [it for it in man['items'] if it['phase'] == p]; done = [it for it in items if is_done(a.manifest, rec, it)]
        warn = sum(bool(qa_warnings(rec[it['id']])) for it in done)
        print('%-6s %3d/%3d recorded (%d positives, %d negatives), %d with QA warnings' % (p, len(done), len(items), sum(it['kind'] == 'command' for it in done),
              sum(it['kind'] == 'negative' for it in done), warn))
    print('speaker %s, seed %d, commands %s, held back: %s' % (man['speaker'], man['seed'], man['commands'], man['commands'][man['held_back_command']]))

def cmd_centre(a):
    x = read_wav(a.wav)[:CAP_N]; clip, e, start = centre_clip(x); clip.astype('<i2').tofile(a.out)
    print(json.dumps(e)); w = qa_warnings(e)
    if w: print('WARNING: ' + '; '.join(w))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter); sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('init'); p.add_argument('manifest'); p.add_argument('--speaker', required=True); p.add_argument('--seed', type=int, required=True)
    p.add_argument('--commands', required=True, help='4 comma-separated words; the 4th is held back'); p.add_argument('--confusables', default='', help='pre-registered, 3 per command')
    p.add_argument('--unrelated', default=''); p.add_argument('--enrol', type=int, default=5); p.add_argument('--dev', type=int, default=10); p.add_argument('--test', type=int, default=30)
    p.add_argument('--dev-neg', type=int, default=100); p.add_argument('--test-neg', type=int, default=300); p.add_argument('--device', default=''); p.add_argument('--notes', default='')
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser('record'); p.add_argument('manifest'); p.add_argument('phase'); p.add_argument('--backend', default='auto'); p.add_argument('--device', default='')
    p.add_argument('--auto', action='store_true', help='no keypress between prompts; retake automatically (twice at most) on a QA warning'); p.add_argument('--gap', type=float, default=1.0)
    p.set_defaults(fn=cmd_record)
    p = sub.add_parser('import'); p.add_argument('manifest'); p.add_argument('--from', dest='src', required=True); p.add_argument('--quiet', action='store_true'); p.set_defaults(fn=cmd_import)
    p = sub.add_parser('status'); p.add_argument('manifest'); p.set_defaults(fn=cmd_status)
    p = sub.add_parser('centre'); p.add_argument('wav'); p.add_argument('out'); p.set_defaults(fn=cmd_centre)
    a = ap.parse_args(); a.fn(a)

if __name__ == '__main__': main()
