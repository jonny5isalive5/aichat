#!/bin/sh
# verify.sh -- evidence that uAI-32 meets every requirement of the Sentovara challenge.
# Every check prints PASS or FAIL with the numbers behind it; the exit status is non-zero if any check fails.
# Needs: sh, make, a C compiler, awk, cmp.  Runs in a few seconds (MNIST is measured separately, see measure.sh).
set -u
cd "$(dirname "$0")"
LIMIT=32768; W=work; FAIL=0
mkdir -p $W; cd $W && rm -f iris0.model iris.model iris_again.model spirals.model rings.model scrambled.model copy.model *.txt *.out; cd ..
size() { wc -c < "$1" | tr -d ' '; }
acc()  { ./uai32 test "$1" "$2" | awk -F'= ' '{print $2+0}'; }   # held-out accuracy in percent
check() { if [ "$1" -eq 1 ]; then echo "PASS  $2"; else echo "FAIL  $2"; FAIL=1; fi; }
ge() { awk "BEGIN{exit !($1 >= $2)}"; }   # float compare: ge A B

echo "== 0. build from source"
make -s uai32 || { echo "FAIL  build"; exit 1; }
EXE=$(size uai32)
check $((EXE <= LIMIT)) "executable is $EXE bytes (limit $LIMIT)"

echo "== 1. it learns: the same program, before and after training (iris, 4-8-3)"
./uai32 train data/iris_train.txt $W/iris0.model 8 0 0.05 1 > /dev/null   # 0 epochs = random initial weights, saved
./uai32 train data/iris_train.txt $W/iris.model  8 60 0.05 1 > $W/iris_train.out
A0=$(acc data/iris_test.txt $W/iris0.model); A1=$(acc data/iris_test.txt $W/iris.model)
check $(ge "$A1" 90 && ge "$A1" "$A0 + 20" && echo 1 || echo 0) "held-out accuracy went from $A0% (untrained) to $A1% (after 60 epochs)"
L1=$(sed -n '2p' $W/iris_train.out | awk '{print $5}'); L2=$(tail -1 $W/iris_train.out | awk '{print $5}')   # "epoch 1/60  train loss L ..." 
check $(ge "$L1" "$L2 * 2" && echo 1 || echo 0) "training loss fell from $L1 (epoch 1) to $L2 (epoch 60)"

echo "== 2. it alters internal state: the saved weights change"
if cmp -s $W/iris0.model $W/iris.model; then check 0 "model bytes changed"; else check 1 "model file changed (same size: $(size $W/iris0.model) -> $(size $W/iris.model) bytes)"; fi

echo "== 3. it generalises: accuracy on examples never seen in training"
./uai32 train data/spirals_train.txt $W/spirals.model 32 500 0.05 1 > /dev/null
./uai32 train data/rings_train.txt   $W/rings.model   16 200 0.05 1 > /dev/null
S=$(acc data/spirals_test.txt $W/spirals.model); R=$(acc data/rings_test.txt $W/rings.model)
check $(ge "$A1" 90 && echo 1 || echo 0) "iris:    $A1% on 30 unseen flowers"
check $(ge "$S" 95 && echo 1 || echo 0)  "spirals: $S% on 300 unseen points (curved boundary, 2 classes)"
check $(ge "$R" 95 && echo 1 || echo 0)  "rings:   $R% on 300 unseen points (3 concentric classes)"
# Control: destroy the relationship between features and labels; the model must then fail on the test set.
awk '{ $NF = ($NF + NR) % 2; print }' data/spirals_train.txt > $W/spirals_scrambled.txt
./uai32 train $W/spirals_scrambled.txt $W/scrambled.model 32 500 0.05 1 > /dev/null
C=$(acc data/spirals_test.txt $W/scrambled.model)
check $(ge 65 "$C" && echo 1 || echo 0) "control: trained on scrambled labels it scores $C% (chance is 50%), so the skill comes from the data"

echo "== 4. it saves, reloads and keeps inferring"
cp $W/spirals.model $W/copy.model
./uai32 predict $W/spirals.model < data/spirals_test.txt > $W/p1.out
./uai32 predict $W/copy.model    < data/spirals_test.txt > $W/p2.out
awk '{print $NF}' data/spirals_test.txt > $W/labels.txt
P=$(awk 'NR==FNR{l[FNR]=$1; next} l[FNR]==$1{c++} END{printf "%.1f", 100*c/FNR}' $W/labels.txt $W/p1.out)
check $(cmp -s $W/p1.out $W/p2.out && echo 1 || echo 0) "a fresh process reading a copy of the model file gives identical predictions ($(wc -l < $W/p1.out) rows)"
check $(ge "$P" 95 && echo 1 || echo 0) "those predictions are $P% correct on the unseen rows"

echo "== 5. training can continue from the saved state"
./uai32 train data/spirals_train.txt $W/spirals.model 0 100 0.01 > $W/cont.out    # file exists -> loads and continues
S2=$(acc data/spirals_test.txt $W/spirals.model)
check $(grep -q '^continuing' $W/cont.out && ge "$S2" 95 && echo 1 || echo 0) "reloaded, trained 100 more epochs at a lower rate: $S2% held-out"

echo "== 6. reproducible: same data and seed give a byte-identical model"
./uai32 train data/iris_train.txt $W/iris_again.model 8 60 0.05 1 > /dev/null
check $(cmp -s $W/iris.model $W/iris_again.model && echo 1 || echo 0) "two training runs with seed 1 produce the same bytes"

echo "== 7. size: executable + saved learned state must be <= $LIMIT bytes"
for n in iris spirals rings; do
    s=$(size $W/$n.model); c=$((EXE + s))
    check $((c <= LIMIT)) "$n: $EXE + $s = $c bytes ($((LIMIT - c)) spare)"
done
[ -f $W/mnist14.model ] && { s=$(size $W/mnist14.model); c=$((EXE + s)); check $((c <= LIMIT)) "mnist14: $EXE + $s = $c bytes ($((LIMIT - c)) spare)"; }

[ $FAIL -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit $FAIL
