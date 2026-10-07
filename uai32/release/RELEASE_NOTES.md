# Sentovara µAI-32 — public release draft

Prepared 7 October 2026. **Review only: no release tag or GitHub release has been published.**

## Claim

An executable that can train and run a neural classifier, plus its complete saved MNIST learned state,
fits in **30,656 bytes**: **9,188 + 21,468**, leaving **2,112 bytes** under the **32,768-byte** limit.
The identified executable/model pair scores **9,781/10,000 = 97.81%**, with printed loss **0.0766**,
on the standard MNIST test set after 2×2 average pooling and rounding to 14×14 pixels.

## Scope

The claim concerns the exact on-disk artifacts at [`3e924e600ef6b65eff9f00668cb283b259930049`](https://github.com/jonny5isalive5/aichat/commit/3e924e600ef6b65eff9f00668cb283b259930049),
from [PR #2](https://github.com/jonny5isalive5/aichat/pull/2), on x86-64 Linux. Count the full executable and one full model file.
Host libc, libm and the dynamic loader are excluded, as are RAM, the OS, build/verification tools,
datasets, documentation and packaging metadata. The release ZIP itself is not a 32 KiB download.

## Evidence

The preserved focused audit reports **PASS**, **28/28 mandatory verification checks**, **18 regression
groups**, **222 recorded subprocess invocations**, sanitizer coverage and byte-identical reproduction
of the executable, all four trained models and the checksum manifest. The normalization overflow and
distribution publication-failure probes passed their controls. See [the evidence index](EVIDENCE.md)
for the original archive, exact hashes, logs, methods and limits of this evidence.

## Known limits

- One hidden layer with ReLU, softmax and SGD; no language-model or general-intelligence claim.
- No claim of being the world's smallest AI, of bare-metal deployment, or of a 32 KiB memory limit.
- MNIST is a public benchmark, not an established never-consulted development holdout. The audit did
  not prove the absence of historical tuning against the test set. Iris has one train/test duplicate.
- Saved weights use bfloat16; continuation reloads rounded weights and reseeds shuffling rather than
  exactly resuming interrupted float32 training. Other libm/CPU/toolchain environments can differ.
- Size flags disable stack protection, PIE, control-flow protection and RELRO; the binary also omits
  section headers. This is a research demonstration, not a hardened production deployment claim.
- The audit checks finite state, formats, numerical faults and failure paths, but is not a formal proof,
  an exhaustive security assessment or a certification for asbestos work or safety-critical decisions.

## Reproduction

Follow [REPRODUCE.md](REPRODUCE.md): pin the SHA; validate committed checksums; obtain and validate
the pinned MNIST archives; rebuild; train into scratch; run every regression and all mandatory checks.
The exact-build section identifies the recorded compiler, linker and libc packages. Keep raw logs and
exit codes. Run optional distribution regeneration only in a disposable second copy, then compare
the executable, models and manifest against the frozen originals.

## Disprove us

Attack the accounting, inspect dependencies, find leakage, reproduce failures or build a smaller
comparable program. [CHALLENGE.md](CHALLENGE.md) gives comparison rules and a counterexample template.
Open an issue with enough evidence for someone else to repeat your result.

## Changes in this release overlay

Only the README, Apache-2.0 license/notice, release documentation, provenance metadata and copies of
the original evidence are added or edited. Core model code, tests, size accounting, dataset files,
executable, learned models and `dist/SHA256SUMS` retain their audited bytes and Git modes.
Original source snapshots, including the earlier README, remain in the unchanged audit archive.

## Publication handoff

Review this documentation overlay separately from PR #2. Approve merging, the final release name/tag
and publication only after reviewing the package and current heads. The tag for a future release must
identify its actual commit; keep `3e924e600ef6b65eff9f00668cb283b259930049` explicit as the audited implementation.
Any subsequent code/artifact change needs fresh evidence before the claim is carried forward.
Apache-2.0 is the owner's selected project license; datasets retain the terms in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
