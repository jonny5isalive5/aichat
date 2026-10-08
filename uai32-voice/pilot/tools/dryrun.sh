#!/bin/sh
# dryrun.sh ZIP SCRATCH -- exercise the whole pilot kit end to end on speaker-INDEPENDENT stand-in clips from mini_speech_commands.zip
# (untrusted data; SCRATCH must not exist; everything runs with python3 -I), then write pilot/DRYRUN.md and copy the small
# artifacts into pilot/dryrun/.  The numbers it produces only prove that the pipeline runs; they are not pilot results.
#   1. tools/standin_captures.py: sealed manifest + 580 stand-in 1.5 s captures (enrol speakers excluded from dev/test)
#   2. record.py import/status/record(manual)/centre, the seal tamper check and backend error paths on a second manifest
#   3. run_pilot.py all (dev: P1 + freeze; test: P2 x2, P3, P4, controls, report), then the one-shot refusal
#   4. measure.sh --pilot on the states it produced
set -eu
ZIP=$1; S=$2; P=$(cd "$(dirname "$0")/.." && pwd); D=$P/dryrun
[ ! -e "$S" ] || { echo "dryrun.sh: $S exists; give a new, empty scratch path" >&2; exit 1; }
mkdir -p "$S"; S=$(cd "$S" && pwd); SEED=7; RSEED=1; T0=$(date +%s)
log() { printf '%s\n' "$*" | tee -a "$S/dryrun.log"; }
log "# dryrun.sh $(date -u +%Y-%m-%dT%H:%M:%SZ): zip sha256 $(sha256sum "$ZIP" | cut -c1-16)..., scratch $S, seeds standin $SEED / run $RSEED"
# ---- 1. stand-in manifest and captures ----
python3 -I "$P/tools/standin_captures.py" "$ZIP" "$S/data" $SEED | tee -a "$S/dryrun.log"
# ---- 2. the recorder's paths that need no microphone ----
{
  echo "## record.py status (before import)"; python3 -I "$P/record.py" status "$S/data/manifest.json"
  echo "## record.py import (host-side centring of every stand-in capture; QA warnings are expected on crowd-sourced clips)"
  python3 -I "$P/record.py" import "$S/data/manifest.json" --from "$S/data/incoming" | tail -1
  echo "## record.py status (after import)"; python3 -I "$P/record.py" status "$S/data/manifest.json"
  echo "## record.py centre on one stand-in capture"; w=$(ls "$S/data/incoming"/*.wav | head -1); python3 -I "$P/record.py" centre "$w" "$S/one.raw"; wc -c < "$S/one.raw"
  echo "## record.py init of a second, pre-registered manifest (the real pilot's shape) and the manual-recording instructions"
  python3 -I "$P/record.py" init "$S/rec-smoke/manifest.json" --speaker spk01 --seed 11 --commands stop,go,left,right \
      --confusables top,shop,stock,no,so,goat,lift,let,laughed,write,light,ride \
      --unrelated apple,window,seven,coffee,river,paper,yellow,music,table,garden,pencil,orange,summer,bottle,jacket,silver,candle,button,ladder,rocket \
      --device "none (dry run)" --notes "dry run: init and manual instructions only"
  python3 -I "$P/record.py" record "$S/rec-smoke/manifest.json" enrol --backend manual | head -9; echo "     ... (20 prompts)"
  echo "## error paths (each must refuse)"
  python3 -I "$P/record.py" record "$S/rec-smoke/manifest.json" enrol --backend arecord 2>&1 | tail -1 || true
  python3 -I "$P/record.py" record "$S/rec-smoke/manifest.json" enrol --backend sox 2>&1 | tail -1 || true
  python3 -I "$P/record.py" record "$S/rec-smoke/manifest.json" bogus 2>&1 | tail -1 || true
  python3 -I "$P/record.py" init "$S/rec-smoke/manifest.json" --speaker x --seed 1 --commands a,b,c,d 2>&1 | tail -1 || true
  python3 -I "$P/record.py" init "$S/rec-smoke/m2.json" --speaker x --seed 1 --commands a,b,c 2>&1 | tail -1 || true
  cp "$S/rec-smoke/manifest.json" "$S/rec-smoke/manifest.bak"
  python3 -I -c 'import json,sys; p=sys.argv[1]; m=json.load(open(p)); m["items"][0]["label"]=2; json.dump(m, open(p,"w"))' "$S/rec-smoke/manifest.json"
  python3 -I "$P/record.py" status "$S/rec-smoke/manifest.json" 2>&1 | tail -1 || true
  mv "$S/rec-smoke/manifest.bak" "$S/rec-smoke/manifest.json"
} > "$S/kit_checks.log" 2>&1
cat "$S/kit_checks.log" | tee -a "$S/dryrun.log" >/dev/null
# ---- 3. the runner ----
T1=$(date +%s); python3 -I "$P/run_pilot.py" all "$S/data/manifest.json" "$S/run" --seed $RSEED > "$S/run_all.log" 2>&1; T2=$(date +%s)
log "run_pilot.py all: $((T2 - T1)) s (log: run_all.log)"
{ echo "## one-shot rule: a second test stage on the same directory must be refused"
  python3 -I "$P/run_pilot.py" test "$S/data/manifest.json" "$S/run" --seed $RSEED 2>&1 | tail -1 || true
  echo "## recipe change after the freeze must be refused"
  python3 -I "$P/run_pilot.py" test "$S/data/manifest.json" "$S/run" --seed 2 --force-rerun 2>&1 | tail -1 || true
} >> "$S/kit_checks.log" 2>&1
# ---- 4. fresh measurements on the tested states ----
sh "$P/measure.sh" --pilot "$S/run" "$S/data/manifest.json" > "$S/measure_pilot.log" 2>&1; log "measure.sh --pilot done"
# ---- 5. DRYRUN.md and the small artifacts ----
rm -rf "$D"; mkdir -p "$D/measurements"
cp "$S/data/SEALED.sha256" "$S/data/standin_sources.txt" "$S/run/thresholds.json" "$S/run/summary.json" "$S/run/log.txt" "$S/run/TEST_RUNS.json" \
   "$S/run"/dev_det_*.csv "$S/run/stateA.dtw" "$S/run/stateB.dtw" "$S/run/modelA.bin" "$S/run/modelB.bin" "$S/run/strace_dtw.log" "$S/run/strace_net.log" "$S/run_all.log" "$S/kit_checks.log" "$D/"
cp "$S/run/measurements/sizes.txt" "$S/run/measurements/rss.txt" "$D/measurements/"
gzip -9 -n -c "$S/data/manifest.json" > "$D/manifest.json.gz"; gzip -9 -n -c "$S/data/recordings.json" > "$D/recordings.json.gz"
awk -F, 'NR==1 || $1=="dev" || $1=="P2" || $1=="P4" || $1=="untrained"' "$S/run/decisions.csv" | gzip -9 -n > "$D/decisions_core.csv.gz"
sha256sum "$S/run/decisions.csv" | sed 's|  .*|  decisions.csv (full, not copied: dev, P2, P2_rerun, P4, untrained, 5 constrained, 20 unconstrained)|' > "$D/decisions_full.sha256"
T3=$(date +%s)
{
  echo '# DRY RUN of the pilot kit on speaker-INDEPENDENT stand-in clips'
  echo
  echo '> **THESE ARE NOT PILOT RESULTS.**  Every clip below comes from Google mini_speech_commands: the "enrolled speaker" is'
  echo '> 20 different crowd-sourced speakers, and every dev/test clip is from a speaker absent from enrolment, through unknown'
  echo '> microphones.  The "own-voice confusables" are the words up/down and the "unrelated" words are left/right, chosen only'
  echo '> so that every stratum of the report is exercised.  The numbers prove that record.py, run_pilot.py and measure.sh run'
  echo '> end to end, refuse what they must refuse, and produce the report in the pre-registered shape.  They say nothing about'
  echo '> an enrolled speaker on one microphone, which is what the pilot will measure.  Do not quote them as pilot results.'
  echo
  echo "Produced by \`tools/dryrun.sh\` on $(date -u +%Y-%m-%dT%H:%M:%SZ) in $((T3 - T0)) s (run_pilot.py all: $((T2 - T1)) s) on $(uname -m), $(cc --version | head -1), $(python3 -c 'import sys,numpy; print("Python %d.%d.%d, numpy %s" % (*sys.version_info[:3], numpy.__version__))')."
  echo
  echo '## Exact commands'
  echo
  echo '```sh'
  echo "cd uai32-voice/pilot && ./build.sh && sha256sum -c SHA256SUMS       # dtwapp c3cc4fc9..., netapp 4e575f75..."
  echo "tools/dryrun.sh /path/mini_speech_commands.zip /scratch/pilot-dryrun   # zip sha256 $(sha256sum "$ZIP" | cut -c1-64)"
  echo '# which runs, in order:'
  echo "python3 -I tools/standin_captures.py ZIP /scratch/pilot-dryrun/data $SEED            # sealed manifest + 580 stand-in 1.5 s captures"
  echo 'python3 -I record.py import /scratch/pilot-dryrun/data/manifest.json --from /scratch/pilot-dryrun/data/incoming'
  echo "python3 -I run_pilot.py all /scratch/pilot-dryrun/data/manifest.json /scratch/pilot-dryrun/run --seed $RSEED"
  echo './measure.sh --pilot /scratch/pilot-dryrun/run /scratch/pilot-dryrun/data/manifest.json'
  echo '```'
  echo
  echo 'Everything is seeded: a repeat gives byte-identical clips, states, models and decisions (the SHA-256 values below); only the'
  echo 'manifest creation timestamp, hence its seal, and the freeze timestamp in thresholds.json differ between repeats.'
  echo 'Stand-in data: `dryrun/standin_sources.txt` lists every clip (id, phase, word, zip member, offset of the 1 s clip inside the'
  echo '1.5 s capture, SHA-256 of the member); `dryrun/manifest.json.gz` + `SEALED.sha256` is the sealed manifest,'
  echo '`dryrun/recordings.json.gz` the per-clip centring log (centre sample, active region, peak, QA warnings).'
  echo
  echo '## What the dry run exercised'
  echo
  echo '- `record.py`: `init` (a second, realistically pre-registered manifest: 4 commands, 12 confusables, 20 unrelated words),'
  echo '  `status`, `import` of 580 hand-style WAV captures with the host-side centring and QA warnings, `centre`, the `manual`'
  echo '  backend instructions, the refusals (missing arecord/sox when forced, unknown phase, existing manifest, 3 commands,'
  echo '  edited manifest against its seal).  NOT exercised: the live `sounddevice`, `arecord` and `sox` capture paths (no'
  echo '  audio device, module or tool in this container; see FAILURES.md).'
  echo '- `run_pilot.py`: `dev` (P1, dev scoring, DET CSVs, freeze), `test` (P2 twice with features re-extracted, P3, P4,'
  echo '  untrained / 5 constrained / 20 unconstrained permutation controls, strace, report), then the one-shot refusal and'
  echo '  the changed-recipe refusal.'
  echo '- `measure.sh --pilot`: bytes of exactly the tested states and peak RSS of every verb.'
  echo
  echo '```'
  cat "$S/kit_checks.log"
  echo '```'
  echo
  echo '## The report run_pilot.py wrote (dryrun/.. holds the inputs it cites)'
  echo
  sed "s|$S/run/|OUTDIR/|g; s|$S/|SCRATCH/|g; s|$P/|PILOT/|g; s|^# Pilot results|# [DRY RUN, speaker-independent stand-ins] Pilot results|" "$S/run/RESULTS.md"
  echo
  echo '## Fresh measurements (`measure.sh --pilot`, dryrun/measurements/)'
  echo
  echo '```'; cat "$S/run/measurements/sizes.txt"; echo; cat "$S/run/measurements/rss.txt"; echo '```'
  echo
  echo '## Run log of run_pilot.py (dryrun/run_all.log)'
  echo
  echo '```'; sed "s|$S/run/|OUTDIR/|g; s|$S/|SCRATCH/|g" "$S/run_all.log"; echo '```'
  echo
  echo '## Artifacts copied to dryrun/ (SHA-256 in dryrun/SHA256SUMS)'
  echo
  echo 'States and models (`stateA.dtw` 14,663, `stateB.dtw` 19,548, `modelA.bin` 5,936, `modelB.bin` 5,970 bytes), `thresholds.json`,'
  echo '`summary.json`, the four dev DET curves, `decisions_core.csv.gz` (dev, P2, P4 and the untrained control; P2_rerun is'
  echo 'byte-identical to P2 and the 25 permutation controls are only in the full decisions.csv, whose hash is in `decisions_full.sha256`),'
  echo 'the strace logs, `log.txt`, `run_all.log`, `kit_checks.log`, `measurements/`.  The 580 clips (18.6 MB) and the training-row'
  echo 'caches are not copied: `standin_sources.txt` + the zip + the seeds regenerate them exactly.'
} > "$P/DRYRUN.md"
(cd "$D" && sha256sum $(ls -p | grep -v / | grep -v SHA256SUMS) measurements/* > SHA256SUMS)
log "wrote $P/DRYRUN.md and $D/ ($(du -sk "$D" | cut -f1) KB); total $((T3 - T0)) s"
