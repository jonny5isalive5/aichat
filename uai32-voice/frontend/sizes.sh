#!/bin/sh
# sizes.sh ELF... -- per-section byte sizes of ELF files with section headers (decimal)
for f in "$@"; do
  printf '%-18s' "$f"
  readelf -S -W "$f" | grep -E '^\s*\[ *[0-9]+\] \.' | while read -r line; do
    set -- $(echo "$line" | sed 's/^.*\] //'); printf '%s=%d ' "$1" "0x$5"
  done; echo
done
