# Fable II MemExport70 — compile the *actual* private guest writer instrumentation

MemExport66 transformed 297 C++ translation units and wrapped 8,436 atomic
calls and 38 memory intrinsics. Previously, that transformed code was **not used
in the Android `libfable2.so` build**; its report established only source-code
rewrite coverage.

MemExport70 adds an explicitly opted-in **diagnostic-only** build path:

- After private generated C++ import and strict ZIP/XEX/SDK provenance checks,
  verify every imported source is byte-for-byte equal to the private ZIP.
- Reuse the tested MemExport66 transformer on *all* generated source units,
  requiring 297 sources, 8,436 atomic calls and 38 memory intrinsics.
- Install all transformed sources as a complete generated/default directory
  before CMake, with a rollback path for ordinary file-system errors.
- Preserve original `sources.cmake` and the imported-codegen stamp. Reject
  stale or partially instrumented builds and refuse source drift.
- Save a sanitized JSON report in ignored `build/`. The binary is compiled as
  a diagnostic guest **only**, never approved as `libfable2.so` production.

Run from private GitHub Actions (`FABLE2_PRIVATE_TOKEN` required):

```sh
gh workflow run build-fable2-arm64-26.yml \
  --repo NanaveONE/Fteste \
  -f release_tag=guest-input-26 \
  -f memexport70_diagnostic=true
```

The same diagnostic run also classifies remaining raw-address contexts with
MemExport69 and saves aggregate counts plus a few PRIVATE example lines.
Neither is uploaded to public Actions artifacts.

Success produces only the separately named PRIVATE release asset
`libfable2-MemExport70-DIAGNOSTICO.so` and JSON
`Fable2-MemExport70-RELATORIO-PRIVADO.json`, alongside the private context
report `Fable2-MemExport70-CONTEXTOS-PRIVADO.json` and private source
samples `Fable2-MemExport70-AMOSTRAS-PRIVADAS.txt`. Normal builds with the option OFF
continue using original generated C++ and the original `libfable2.so` output.

**NOT proof of complete synchronization.** Only observer counters exist in
MemExport66, confined to their linked library. No cross-library guest-RAM lock,
DMA exclusion, writer-cooperation certification or SPIR-V MemExport store
validation exists. The five pending shaders remain blocked at 583/588.

The original proprietary C++ ZIP, XEX, transformed sources and any compiler
logs must never be uploaded to the public repository/Actions artifacts. The
workflow writes diagnostic logs only to the separate private release.
