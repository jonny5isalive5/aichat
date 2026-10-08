"""Regenerate every reported draw with the benchmark's own seeded logic (fewshot.split, numpy default_rng(seed)),
verify each against the '_split' arrays stored in the results/*.npz files, and write manifests/draws.json (stored gzip-compressed in the repository as draws.json.gz) with the
exact file names.  Added during preservation (2026-10-08); not part of the original run.
usage: python3 -I regen_draws.py --meta cache/meta.json [--results results/] --out manifests/draws.json
   or: python3 -I regen_draws.py --wav data_raw/wav ...      (rebuilds the file list exactly like features.build_cache)
Only meta.json (file names, words, speaker hashes) is needed: the split never looks at the audio."""
import sys, os, json, glob, argparse, hashlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fewshot as fs
ap = argparse.ArgumentParser(); ap.add_argument('--meta'); ap.add_argument('--wav'); ap.add_argument('--results'); ap.add_argument('--out', required=True); a = ap.parse_args()
if a.meta: meta = json.load(open(a.meta))
else:
    files = sorted(glob.glob(os.path.join(a.wav, '*', '*.wav')))
    meta = {'files': [os.path.relpath(f, a.wav) for f in files], 'words': [f.split(os.sep)[-2] for f in files], 'speakers': [os.path.basename(f).split('_')[0] for f in files]}
class D: pass
data = D(); data.words = np.array(meta['words']); data.spk = np.array(meta['speakers']); data.files = meta['files']
filelist_sha = hashlib.sha256('\n'.join(data.files).encode()).hexdigest()
R = a.results
groups = [  # name, cmds, seeds, n_enrol, shuffle, result file(s) holding the same split, note
    ('full_yes_no_stop_test', ('yes', 'no', 'stop'), range(1, 21), 5, False, ['full_yes_no_stop_test.npz', 'templates_yes_no_stop_test.npz'], 'main result, 20 test draws'),
    ('full_yes_no_stop_dev', ('yes', 'no', 'stop'), range(101, 111), 5, False, ['full_yes_no_stop_dev.npz', 'templates_yes_no_stop_dev.npz'], 'separate dev draws used only to freeze the fixed thresholds'),
    ('full_up_down_go_test', ('up', 'down', 'go'), range(1, 21), 5, False, ['full_up_down_go_test.npz', 'templates_up_down_go_test.npz'], 'main result, 20 test draws'),
    ('full_up_down_go_dev', ('up', 'down', 'go'), range(101, 111), 5, False, ['full_up_down_go_dev.npz', 'templates_up_down_go_dev.npz'], 'separate dev draws used only to freeze the fixed thresholds'),
    ('full_yes_no_stop_go_test', ('yes', 'no', 'stop', 'go'), range(1, 11), 5, False, ['full_yes_no_stop_go_test.npz'], '4-command result, 10 test draws'),
    ('full_yes_no_stop_go_dev', ('yes', 'no', 'stop', 'go'), range(101, 106), 5, False, ['full_yes_no_stop_go_dev.npz'], '4-command dev draws for the fixed thresholds'),
    ('control_shuffled_yes_no_stop', ('yes', 'no', 'stop'), range(1, 11), 5, True, ['control_shuffled_yes_no_stop.npz'], 'same recordings as full_yes_no_stop_test seeds 1-10; enrolment labels permuted by numpy default_rng(seed+999).permutation'),
    ('enrol10_yes_no_stop_test', ('yes', 'no', 'stop'), range(1, 11), 10, False, ['enrol10_yes_no_stop_test.npz'], 'enrolment-size sweep (templates only)'),
    ('enrol20_yes_no_stop_test', ('yes', 'no', 'stop'), range(1, 11), 20, False, ['enrol20_yes_no_stop_test.npz', 'enrol20mlp_yes_no_stop_test.npz'], 'enrolment-size sweep; enrol20mlp (all methods, 8x augmentation) used the identical split'),
    ('enrol50_yes_no_stop_test', ('yes', 'no', 'stop'), range(1, 11), 50, False, ['enrol50_yes_no_stop_test.npz'], 'enrolment-size sweep (templates only)'),
    ('pilot_yes_no_stop', ('yes', 'no', 'stop'), range(901, 906), 5, False, [], 'hyper-parameter selection only (pilot*.py, diag*.py); never used for reported numbers; no .npz was saved'),
]
same_as = {'control_untrained (results/control_untrained.txt)': 'full_yes_no_stop_test seeds 1-10 (n_enrol 5, unshuffled)',
           'uint8_dtw_check (results/uint8_dtw_check.txt)': 'full_yes_no_stop_test seeds 1-10 (n_enrol 5, unshuffled)',
           'enrol20mlp_yes_no_stop_test.npz': 'enrol20_yes_no_stop_test (identical split; verified)'}
def names(idx): return [data.files[i] for i in np.asarray(idx)]
def by_cmd(idx, lab, cmds): return {c: names(np.asarray(idx)[np.asarray(lab) == i]) for i, c in enumerate(cmds)}
def by_word(idx, w): return {x: names(np.asarray(idx)[np.asarray(w) == x]) for x in sorted(set(map(str, w)))}
out = {'_doc': 'Every draw regenerated with fewshot.split(data, cmds, seed, n_enrol) (numpy default_rng(seed); enrolment = n_enrol recordings per command drawn without replacement from all 1000; dev/test positives = 100 per command and dev/test negatives = 200 per non-command word, all from speakers that contributed no enrolment recording, dev and test disjoint).  File names are relative to the extracted wav tree (mini_speech_commands/<word>/<speaker>_nohash_<n>.wav).  Enrolment lists keep the drawn order (index = class label order within the command).  dev_pos is scored by run_main.py but not used by any reported number.',
       'file_list_sha256': filelist_sha, 'n_files': len(data.files), 'same_split_as': same_as, 'groups': {}}
allok = True
for name, cmds, seeds, n_enrol, shuffle, files, note in groups:
    g = {'cmds': list(cmds), 'seeds': list(seeds), 'n_enrol': n_enrol, 'shuffle_labels': shuffle, 'result_files': files, 'note': note, 'verified_against_npz': {}, 'draws': {}}
    stored = {}
    if R:
        for f in files:
            p = os.path.join(R, f)
            if os.path.exists(p): stored[f] = np.load(p, allow_pickle=True)['results'][0]['_split']
            else: g['verified_against_npz'][f] = 'file not found'
    for seed in seeds:
        sp = fs.split(data, cmds, seed, n_enrol=n_enrol)
        if shuffle: sp['enrol_lab'] = np.random.default_rng(seed + 999).permutation(sp['enrol_lab'])
        d = {'enrol': by_cmd(sp['enrol_idx'], sp['enrol_lab'], cmds), 'test_pos': by_cmd(sp['test_pos'], sp['test_lab'], cmds), 'dev_pos': by_cmd(sp['dev_pos'], sp['dev_lab'], cmds),
             'dev_neg': by_word(sp['dev_neg'], sp['dev_negw']), 'test_neg': by_word(sp['test_neg'], sp['test_negw'])}
        if shuffle: d['enrol_files_in_draw_order'] = names(sp['enrol_idx']); d['enrol_labels_after_shuffle'] = [int(x) for x in sp['enrol_lab']]
        g['draws'][str(seed)] = d
        for f, st in stored.items():
            s = st[seed]; ok = all(np.array_equal(np.asarray(sp[k]), np.asarray(s[k])) for k in ['enrol_idx', 'enrol_lab', 'dev_pos', 'dev_lab', 'test_pos', 'test_lab', 'dev_neg', 'dev_negw', 'test_neg', 'test_negw'])
            g['verified_against_npz'].setdefault(f, True); g['verified_against_npz'][f] = g['verified_against_npz'][f] and ok
            if not ok: allok = False; print('MISMATCH', name, f, seed)
    print('%-32s %d draws  verified: %s' % (name, len(g['draws']), g['verified_against_npz'] or 'no npz for this group'))
    out['groups'][name] = g
# compact but line-per-draw JSON
with open(a.out, 'w') as f:
    f.write('{\n'); f.write('"_doc": %s,\n"file_list_sha256": %s,\n"n_files": %d,\n"same_split_as": %s,\n"groups": {\n' % (json.dumps(out['_doc']), json.dumps(filelist_sha), out['n_files'], json.dumps(same_as, indent=1)))
    gi = list(out['groups'].items())
    for n, (name, g) in enumerate(gi):
        f.write('%s: {\n' % json.dumps(name))
        for k in ['cmds', 'seeds', 'n_enrol', 'shuffle_labels', 'result_files', 'note', 'verified_against_npz']: f.write('%s: %s,\n' % (json.dumps(k), json.dumps(g[k])))
        f.write('"draws": {\n'); di = list(g['draws'].items())
        for m, (seed, d) in enumerate(di): f.write('%s: %s%s\n' % (json.dumps(seed), json.dumps(d, separators=(',', ':')), ',' if m < len(di) - 1 else ''))
        f.write('}}%s\n' % (',' if n < len(gi) - 1 else ''))
    f.write('}}\n')
json.load(open(a.out)); print('wrote', a.out, os.path.getsize(a.out), 'bytes; all stored splits reproduced exactly:', allok)
