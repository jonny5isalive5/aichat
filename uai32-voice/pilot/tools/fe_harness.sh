#!/bin/sh
# fe_harness.sh SRC.c OUT -- compile the shared front-end block of SRC.c (dtwapp.c or netapp.c) with a test main that
# prints the NB+2 filter bin edges and the 61 x 16 log-mel matrix of the clip on stdin at full float precision (%.9g),
# so the block can be checked against the benchmark's features.py.  Built with -O0 and -Os to show both agree.
set -eu
SRC=$1; OUT=$2; TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
{
  printf '#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <math.h>\n'
  awk '/==== FRONT-END BEGIN/{p=1} p{print} /==== FRONT-END END/{p=0}' "$SRC"
  printf 'static void die(const char *m) { fprintf(stderr, "fe: %%s\\n", m); exit(1); }\n'
  printf 'int main(void) { int i; alloc_fe(); logmel(); for (i = 0; i < NB + 2; i++) printf("%%d ", bin[i]); printf("\\n");\n'
  printf '  for (i = 0; i < T * NB; i++) printf("%%.9g%%c", lm[i], i %% NB == NB - 1 ? 10 : 32);\n  return 0;\n}\n'
} > "$TMP/fe.c"
cc -std=c99 -Os -Wall -Wextra -pedantic -ffp-contract=off -fno-math-errno "$TMP/fe.c" -o "$OUT" -lm
cc -std=c99 -O0 -Wall -Wextra -pedantic -ffp-contract=off -fno-math-errno "$TMP/fe.c" -o "$OUT.O0" -lm
