#!/bin/sh
# validate.sh CLIPDIR BENCHCODE WORKDIR -- end-to-end validation of pilot/dtwapp and pilot/netapp on the pilot clips.
#   CLIPDIR   output of tools/select_clips.py (clips.txt + raw/), untrusted data
#   BENCHCODE the few-shot benchmark's code directory (features.py, feats2.py, dtw.c): the reference implementation
#   WORKDIR   scratch directory for intermediate files (created)
# Writes small logs and the real state/model files into pilot/validation/.  The frozen release binary (UAI32, default
# ../../uai32/uai32) is only executed, never modified, to prove that netapp's train is unchanged.  Run build.sh first.
set -eu
P=$(cd "$(dirname "$0")" && pwd); CLIPS=$1; BENCH=$2; W=$3; V=$P/validation
UAI32=${UAI32:-$P/../../uai32/uai32}
mkdir -p "$W/fe_Os" "$W/fe_O0" "$W/feat" "$W/rev" "$V"
log() { printf '%s\n' "$*" | tee -a "$V/validate.log"; }
: > "$V/validate.log"; : > "$V/errors.log"
log "# validate.sh $(date -u +%Y-%m-%dT%H:%M:%SZ); dtwapp $(sha256sum "$P/dtwapp" | cut -c1-16)..., netapp $(sha256sum "$P/netapp" | cut -c1-16)..."
# ---- 1. the benchmark's reference on the same clips ----
cc -O2 -shared -fPIC -o "$W/libdtw.so" "$BENCH/dtw.c" -lm
python3 -I "$P/tools/reference.py" "$CLIPS" "$BENCH" "$W/libdtw.so" "$W/ref" | tee -a "$V/validate.log"
# ---- 2. the shared front-end block alone, -Os and -O0 ----
"$P/tools/fe_harness.sh" "$P/dtwapp.c" "$W/fe_test"
for n in $(cat "$W/ref/names.txt"); do
  "$W/fe_test" < "$CLIPS/raw/$n.raw" > "$W/fe_Os/$n.txt"; "$W/fe_test.O0" < "$CLIPS/raw/$n.raw" > "$W/fe_O0/$n.txt"
done
# ---- 3. dtwapp: enrol the 20 enrolment clips in manifest order, then score every query ----
rm -f "$V/pilot.state"; : > "$V/dtwapp_scores.txt"
grep -v '^#' "$CLIPS/clips.txt" | awk '$1=="enrol"' | while read -r role word lab zipname samples sha; do
  "$P/dtwapp" enrol "$V/pilot.state" "$lab" < "$CLIPS/raw/${role}_${word}_$(basename "$zipname" .wav).raw"
done
grep -v '^#' "$CLIPS/clips.txt" | awk '$1!="enrol"' | while read -r role word lab zipname samples sha; do   # all 20 templates are in place
  n="${role}_${word}_$(basename "$zipname" .wav)"
  printf '%s %s\n' "$n" "$("$P/dtwapp" score "$V/pilot.state" < "$CLIPS/raw/$n.raw")" >> "$V/dtwapp_scores.txt"
done
"$P/dtwapp" info "$V/pilot.state" | tee "$V/dtwapp_info.txt" | sed 's/^/dtwapp info: /' >> "$V/validate.log"
# ---- 4. netapp feat on every clip; data files for train/test/predict ----
: > "$V/train4.txt"; : > "$V/test4.txt"; : > "$V/queries.txt"; : > "$V/train5.txt"
grep -v '^#' "$CLIPS/clips.txt" | while read -r role word lab zipname samples sha; do
  n="${role}_${word}_$(basename "$zipname" .wav)"
  case $role in
    enrol) "$P/netapp" feat "$lab" < "$CLIPS/raw/$n.raw" > "$W/feat/$n.txt"; cat "$W/feat/$n.txt" >> "$V/train4.txt"
           python3 -I "$P/tools/reverse_pcm.py" "$CLIPS/raw/$n.raw" "$W/rev/$n.raw"; "$P/netapp" feat 4 < "$W/rev/$n.raw" >> "$W/rev/rows.txt" ;;
    query) "$P/netapp" feat "$lab" < "$CLIPS/raw/$n.raw" > "$W/feat/$n.txt"; cat "$W/feat/$n.txt" >> "$V/test4.txt"; cat "$W/feat/$n.txt" >> "$V/queries.txt" ;;
    neg)   "$P/netapp" feat < "$CLIPS/raw/$n.raw" > "$W/feat/$n.txt"; cat "$W/feat/$n.txt" >> "$V/queries.txt" ;;
  esac
done
cat "$V/train4.txt" "$W/rev/rows.txt" > "$V/train5.txt"     # + 20 time-reversed enrolment clips as the synthetic 'unknown' class 4
log "data rows: train4 $(wc -l < "$V/train4.txt") (4 commands x 5), train5 $(wc -l < "$V/train5.txt") (+20 reversed clips, label 4), test4 $(wc -l < "$V/test4.txt"), queries $(wc -l < "$V/queries.txt") (40 in-vocabulary + 20 unfamiliar)"
# ---- 5. netapp train/test/predict, and the frozen uai32 on the same files (train must be byte-identical) ----
for k in 4 5; do
  rm -f "$V/model$k.bin" "$W/model${k}_uai32.bin"
  "$P/netapp" train "$V/train$k.txt" "$V/model$k.bin" 16 300 0.01 1 > "$V/netapp_train$k.log"
  "$UAI32"   train "$V/train$k.txt" "$W/model${k}_uai32.bin" 16 300 0.01 1 > "$W/uai32_train$k.log"
  cmp "$V/model$k.bin" "$W/model${k}_uai32.bin" && log "model$k.bin: $(wc -c < "$V/model$k.bin") bytes, byte-identical to the frozen uai32's model from the same command ($(head -1 "$V/netapp_train$k.log"); $(tail -1 "$V/netapp_train$k.log"))"
  log "netapp test  model$k (40 in-vocabulary queries, speaker-independent): $("$P/netapp" test "$V/test4.txt" "$V/model$k.bin")"
  log "uai32  test  model$k: $("$UAI32" test "$V/test4.txt" "$V/model$k.bin")"
  "$P/netapp" predict "$V/model$k.bin" < "$V/queries.txt" > "$V/netapp_predict$k.txt"
  "$UAI32"   predict "$V/model$k.bin" < "$V/queries.txt" > "$W/uai32_predict$k.txt"
done
# ---- 6. every input validation path must fail with a non-zero exit ----
expect_fail() {   # expect_fail DESC STDIN CMD...
  desc=$1; in=$2; shift 2; set +e; out=$("$@" < "$in" 2>&1); rc=$?; set -e
  if [ $rc -eq 0 ]; then log "UNEXPECTED SUCCESS: $desc"; exit 1; fi
  printf 'expected failure, exit %d: %s -> %s\n' $rc "$desc" "$(printf '%s' "$out" | head -1)" >> "$V/errors.log"
}
clip=$(ls "$CLIPS"/raw/enrol_yes_*.raw | head -1)
python3 -I -c "import wave,sys; w=wave.open(sys.argv[2],'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(open(sys.argv[1],'rb').read())" "$clip" "$W/one.wav"
head -c -1 "$V/pilot.state" > "$W/trunc.state"; cp "$V/pilot.state" "$W/magic.state"; printf '\000' | dd of="$W/magic.state" bs=1 seek=0 conv=notrunc 2>/dev/null
cp "$V/pilot.state" "$W/badlabel.state"; printf '\020' | dd of="$W/badlabel.state" bs=1 seek=8 conv=notrunc 2>/dev/null
printf '\327\241\074\000\020\000\000\000' > "$W/geom.state"; printf '\327\241\075\000\020\000\000\000' > "$W/empty.state"
printf 'ab' > "$W/one_sample.raw"; printf 'abc' > "$W/odd.raw"
expect_fail "enrol label 16"            "$clip" "$P/dtwapp" enrol "$W/x.state" 16
expect_fail "enrol label -1"            "$clip" "$P/dtwapp" enrol "$W/x.state" -1
expect_fail "enrol label abc"           "$clip" "$P/dtwapp" enrol "$W/x.state" abc
expect_fail "enrol label 1.5"           "$clip" "$P/dtwapp" enrol "$W/x.state" 1.5
expect_fail "enrol without label"       "$clip" "$P/dtwapp" enrol "$W/x.state"
expect_fail "unknown verb"              "$clip" "$P/dtwapp" frobnicate "$W/x.state"
expect_fail "empty clip (enrol)"        /dev/null "$P/dtwapp" enrol "$W/x.state" 0
expect_fail "empty clip (score)"        /dev/null "$P/dtwapp" score "$V/pilot.state"
expect_fail "odd byte count, 3 bytes"   "$W/odd.raw" "$P/dtwapp" score "$V/pilot.state"
expect_fail "WAV instead of raw PCM"    "$W/one.wav" "$P/dtwapp" score "$V/pilot.state"
expect_fail "truncated state (1 byte short)" "$clip" "$P/dtwapp" score "$W/trunc.state"
expect_fail "truncated state (info)"    /dev/null "$P/dtwapp" info "$W/trunc.state"
expect_fail "truncated state (enrol)"   "$clip" "$P/dtwapp" enrol "$W/trunc.state" 0
expect_fail "wrong magic"               "$clip" "$P/dtwapp" score "$W/magic.state"
expect_fail "label byte 16 in a record" "$clip" "$P/dtwapp" score "$W/badlabel.state"
expect_fail "state with T=60 geometry"  "$clip" "$P/dtwapp" score "$W/geom.state"
expect_fail "score with zero templates" "$clip" "$P/dtwapp" score "$W/empty.state"
expect_fail "missing state (score)"     "$clip" "$P/dtwapp" score "$W/does_not_exist.state"
expect_fail "missing state (info)"      /dev/null "$P/dtwapp" info "$W/does_not_exist.state"
expect_fail "netapp feat label abc"     "$clip" "$P/netapp" feat abc
expect_fail "netapp feat label 65535"   "$clip" "$P/netapp" feat 65535
expect_fail "netapp feat too many args" "$clip" "$P/netapp" feat 1 2
expect_fail "netapp feat empty clip"    /dev/null "$P/netapp" feat
expect_fail "netapp feat WAV"           "$W/one.wav" "$P/netapp" feat
expect_fail "netapp feat odd bytes"     "$W/odd.raw" "$P/netapp" feat
expect_fail "netapp predict missing model" "$V/queries.txt" "$P/netapp" predict "$W/does_not_exist.bin"
expect_fail "netapp predict on a dtwapp state file" "$V/queries.txt" "$P/netapp" predict "$V/pilot.state"
expect_fail "dtwapp score on a netapp model" "$clip" "$P/dtwapp" score "$V/model4.bin"
# the one-sample clip is valid input (zero-padded), and an empty state (header only) accepts enrolments:
"$P/dtwapp" enrol "$W/empty.state" 3 < "$W/one_sample.raw" && log "one-sample clip accepted and padded (exit 0); $("$P/dtwapp" info "$W/empty.state" | head -1)"
log "input validation: $(wc -l < "$V/errors.log") error paths all exited non-zero (errors.log)"
# ---- 7. comparisons ----
python3 -I "$P/tools/compare.py" "$W/ref" "$W" "$V" | tee -a "$V/validate.log"
log "# validate.sh done"
