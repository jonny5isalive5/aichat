#!/bin/sh
# measure.sh -- byte sizes (executables, state at capacity, totals against 32,768) and peak RSS / time of every verb of both
# applications, plus two references for the glibc floor: the frozen uai32 and an empty C program built with the same flags.
#
#   measure.sh CLIPDIR WORKDIR                      validation mode: the files validate.sh wrote (validation/pilot.state, model4/5.bin,
#                                                   train4/5.txt, test4.txt, queries.txt); writes pilot/measurements/{sizes,rss}.txt
#                                                   (or $MEASURE_OUT/{sizes,rss}.txt when that variable is set)
#   measure.sh --pilot RUNDIR MANIFEST [WORKDIR]    pilot mode: the files run_pilot.py wrote in RUNDIR (stateA/B.dtw, modelA/B.bin,
#                                                   trainsets/A_rows.txt, B_rows.txt, enrol_rows_B.txt, features/*.txt) and the first
#                                                   enrolment clip of MANIFEST; writes RUNDIR/measurements/{sizes,rss}.txt so the pilot
#                                                   report quotes fresh numbers for exactly the states it tested
# Peak RSS is ru_maxrss of the child (tools/maxrss.py, the counter GNU time prints), 3 runs each; see SIZES.md section 4 for why it is
# glibc-dominated and what the application working set is.
set -eu
P=$(cd "$(dirname "$0")" && pwd); UAI32=${UAI32:-$P/../../uai32/uai32}
if [ "${1:-}" = "--pilot" ]; then
  R=$(cd "$2" && pwd); MAN=$3; W=${4:-$R/measure_work}; M=$R/measurements; mkdir -p "$M" "$W"
  clip=$R/clips_first_enrol.raw
  python3 -I -c 'import json,sys,os; m=json.load(open(sys.argv[1])); it=min((i for i in m["items"] if i["phase"]=="enrol"), key=lambda i:i["order"]); sys.stdout.write(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), it["file"]))' "$MAN" > "$W/clip.path"
  cp "$(cat "$W/clip.path")" "$clip"
  STATE=$R/stateB.dtw; STATE_A=$R/stateA.dtw; M4=$R/modelA.bin; M5=$R/modelB.bin; TR4=$R/trainsets/A_rows.txt; TR5=$R/trainsets/B_rows.txt; TEST=$R/enrol_rows_B.txt
  cat "$R"/features/*.txt > "$W/queries.txt"; QUERIES=$W/queries.txt
  EPOCHS=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1]))["recipe"]["epochs"])' "$R/thresholds.json")
  label4="model A: 3 commands + unknown, NO=4"; label5="model B: 4 commands + unknown, NO=5, declared capacity"; strip="s|$R/||g; s|$W/||g"; MODE=pilot
else
  CLIPS=$1; W=$2; V=$P/validation; M=${MEASURE_OUT:-$P/measurements}; mkdir -p "$M" "$W"; R=$V   # MEASURE_OUT= another directory
  clip=$(ls "$CLIPS"/raw/query_yes_*.raw | head -1)
  STATE=$V/pilot.state; STATE_A=; M4=$V/model4.bin; M5=$V/model5.bin; TR4=$V/train4.txt; TR5=$V/train5.txt; TEST=$V/test4.txt; QUERIES=$V/queries.txt; EPOCHS=300
  label4="144-16-4 (NO=4)"; label5="144-16-5 (NO=5, class 4 = synthetic unknown)"; strip="s|$P/||g; s|$W/||g"; MODE=validation
fi
{
  echo "# measure.sh $(date -u +%Y-%m-%dT%H:%M:%SZ), $(uname -m), $(cc --version | head -1), mode $MODE"
  echo "# wc -c of every file that counts"
  wc -c "$P/dtwapp" "$P/dtwapp.elf" "$P/netapp" "$P/netapp.elf" ${STATE_A:+"$STATE_A"} "$STATE" "$M4" "$M5" "$UAI32" | sed "s|$P/||; $strip"
  d=$(wc -c < "$P/dtwapp"); n=$(wc -c < "$P/netapp"); s=$(wc -c < "$STATE"); m4=$(wc -c < "$M4"); m5=$(wc -c < "$M5")
  N=$(( (s - 8) / 977 ))
  echo "# formulas"
  echo "dtw state = 8 + 977 * N: N = $N -> $((8 + 977 * N)) (real file: $s)"
  echo "model = 8 + 8*NI + 2*(NH*(NI+1) + NO*(NH+1)): NI=144 NH=16 NO=4 -> $((8 + 8*144 + 2*(16*145 + 4*17))) (real file, $label4: $m4); NO=5 -> $((8 + 8*144 + 2*(16*145 + 5*17))) (real file, $label5: $m5)"
  echo "# totals against 32768"
  echo "dtwapp + state($N) = $d + $s = $((d + s)); spare $((32768 - d - s))"
  echo "netapp + model($label4) = $n + $m4 = $((n + m4)); spare $((32768 - n - m4))"
  echo "netapp + model($label5) = $n + $m5 = $((n + m5)); spare $((32768 - n - m5))"
  if [ -n "$STATE_A" ]; then echo "retained for retraining the network (host side, disclosed, not in the model): enrolment rows $(wc -c < "$TEST") bytes as feat text, $(( $(wc -l < "$TEST") * 144 * 4 )) as float32"; fi
  echo "# sections (readelf -S on the .elf twins)"
  for p in dtwapp netapp; do printf '%s: ' $p; readelf -SW "$P/$p.elf" | awk '$2 ~ /^\./ {printf "%s=%d ", $2, strtonum("0x" $6)}' 2>/dev/null || readelf -SW "$P/$p.elf" | awk '$2 ~ /^\./ {printf "%s=0x%s ", $2, $6}'; echo; done
  echo "# libc/libm imports (nm -D --undefined-only)"
  for p in dtwapp netapp; do printf '%s: ' $p; nm -D --undefined-only "$P/$p.elf" | awk '{print $2}' | sed 's/@.*//' | tr '\n' ' '; echo; done
  echo "# sha256"
  sha256sum "$P/dtwapp" "$P/netapp" ${STATE_A:+"$STATE_A"} "$STATE" "$M4" "$M5" | sed "s|$P/||; $strip"
} > "$M/sizes.txt"
cat "$M/sizes.txt"
# ---- peak RSS and time per verb, 3 runs each (ru_maxrss of the child) ----
printf 'int main(void){return 0;}' > "$W/nop.c"
cc -std=c99 -Os -fno-pie -fno-plt -fno-asynchronous-unwind-tables -fno-stack-protector "$W/nop.c" -o "$W/nop" -s -no-pie -Wl,--gc-sections -Wl,-z,now -Wl,--build-id=none -Wl,-z,norelro -Wl,-z,noseparate-code -Wl,--hash-style=gnu -Wl,-z,max-page-size=4096 -Wl,--no-eh-frame-hdr -Wl,-z,nosectionheader
rss() { python3 -I "$P/tools/maxrss.py" "$@" 2>>"$M/rss.txt" >/dev/null; }
{ echo "# measure.sh $(date -u +%Y-%m-%dT%H:%M:%SZ): ru_maxrss (kB) of each child process via wait4, 3 runs each; cpu = user+system; clip = $(basename "$clip")"; } > "$M/rss.txt"
for i in 1 2 3; do
  rss "$W/nop"                                                       < /dev/null
  rss "$UAI32" predict "$M4"                                         < "$QUERIES"
  rss "$P/dtwapp" info "$STATE"                                      < /dev/null
  rss "$P/dtwapp" score "$STATE"                                     < "$clip"
  cp "$STATE" "$W/enrol.state"; rss "$P/dtwapp" enrol "$W/enrol.state" 0 < "$clip"
  rss "$P/netapp" feat 0                                             < "$clip"
  rm -f "$W/m4.bin"; rss "$P/netapp" train "$TR4" "$W/m4.bin" 16 "$EPOCHS" 0.01 1 < /dev/null
  rm -f "$W/m5.bin"; rss "$P/netapp" train "$TR5" "$W/m5.bin" 16 "$EPOCHS" 0.01 1 < /dev/null
  rss "$P/netapp" test "$TEST" "$M5"                                 < /dev/null
  rss "$P/netapp" predict "$M5"                                      < "$QUERIES"
  "$P/netapp" feat < "$clip" > "$W/one_row.txt"; rss "$P/netapp" predict "$M5" < "$W/one_row.txt"
done
sed "s|$P/||g; $strip" "$M/rss.txt" > "$M/rss.tmp" && mv "$M/rss.tmp" "$M/rss.txt"
cat "$M/rss.txt"
