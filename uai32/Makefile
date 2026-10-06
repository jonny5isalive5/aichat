# Sentovara uAI-32 -- build, measure, verify.
#   make            build ./uai32 with the size-reducing flags
#   make measure    print the byte sizes that the challenge counts
#   make verify     run the full evidence script (builds first)
#   make dist       copy the measured deliverable (executable + trained models + checksums) into dist/
#   make clean
CC      ?= cc
PROG    := uai32
# Generic flags: optimise for size, drop everything that is not code.
CFLAGS  ?= -std=c99 -Os -Wall -Wextra -pedantic -U_FORTIFY_SOURCE -fno-asynchronous-unwind-tables \
           -fno-stack-protector -fno-ident -fno-pie -fno-plt -fcf-protection=none -fno-math-errno \
           -ffunction-sections -fdata-sections
LDFLAGS ?= -s -no-pie -Wl,--gc-sections -Wl,-z,now -lm
# GNU ld only: these remove page-alignment padding and metadata that costs bytes on disk.
ifeq ($(shell uname -s),Linux)
LDFLAGS += -Wl,--build-id=none -Wl,-z,norelro -Wl,-z,noseparate-code -Wl,--hash-style=gnu \
           -Wl,-z,max-page-size=4096 -Wl,--no-eh-frame-hdr
endif

$(PROG): uai32.c shrink.py
	$(CC) $(CFLAGS) $< -o $@ $(LDFLAGS)
	@python3 shrink.py $@ || echo "note: python3 not found, section headers kept (about 1.9 KB)"

measure: $(PROG)
	@./measure.sh

verify: $(PROG)
	@./verify.sh

dist: $(PROG)
	@./measure.sh > /dev/null
	@rm -rf dist && mkdir dist && cp $(PROG) dist/
	@for n in iris spirals rings mnist14; do [ -f work/$$n.model ] && cp work/$$n.model dist/; done; true
	@cd dist && sha256sum $(PROG) *.model > SHA256SUMS && cat SHA256SUMS && wc -c $(PROG) *.model

clean:
	rm -rf $(PROG) work dist

.PHONY: measure verify dist clean
