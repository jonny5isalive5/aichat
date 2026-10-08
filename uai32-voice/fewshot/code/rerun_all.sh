#!/bin/sh
# Every reported run, in the order of code/lane1.sh and code/lane2.sh, with paths relative to this directory's
# parent (added during preservation, 2026-10-08; lane1.sh/lane2.sh are the verbatim originals with scratch-space
# paths).  Prerequisites: data_raw/wav and cache/ built as in README.md; bin/uai32 and bin/libdtw.so present.
# Runs sequentially (about 25 minutes on one core; the original ran lane1 and lane2 as two parallel processes).
set -eu
cd "$(dirname "$0")/.."
mkdir -p results work
R=results; W=work; P="python3 -I code/run_main.py"
# lane 1
$P yes,no,stop 1-20      $R/full_yes_no_stop_test.npz            > $W/full_t1_test.log 2>&1
$P yes,no,stop 101-110   $R/full_yes_no_stop_dev.npz             > $W/full_t1_dev.log 2>&1
$P yes,no,stop 1-10      $R/control_shuffled_yes_no_stop.npz --shuffle_labels > $W/control_t1.log 2>&1
$P yes,no,stop,go 1-10   $R/full_yes_no_stop_go_test.npz         > $W/full_4cmd_test.log 2>&1
$P yes,no,stop,go 101-105 $R/full_yes_no_stop_go_dev.npz         > $W/full_4cmd_dev.log 2>&1
# lane 2
$P up,down,go 1-20       $R/full_up_down_go_test.npz             > $W/full_t2_test.log 2>&1
$P up,down,go 101-110    $R/full_up_down_go_dev.npz              > $W/full_t2_dev.log 2>&1
for n in 10 20 50; do $P yes,no,stop 1-10 $R/enrol${n}_yes_no_stop_test.npz --n_enrol $n --mlp none > $W/enrol${n}_t1.log 2>&1; done
$P yes,no,stop 1-10      $R/enrol20mlp_yes_no_stop_test.npz --n_enrol 20 --aug 8 > $W/enrol20mlp_t1.log 2>&1
# controls and checks that print to results/
python3 -I code/control_untrained.py > $R/control_untrained.txt
python3 -I code/check_uint8_dtw.py   > $R/uint8_dtw_check.txt
# tables
python3 -I code/summarize.py > /dev/null          # writes results/summary.txt and results/summary.json
python3 -I code/analyze_negsets.py > $R/negsets.txt
echo "rerun complete"
