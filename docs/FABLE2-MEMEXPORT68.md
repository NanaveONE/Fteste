# Fable II MemExport68 — opaque REX_RAW_ADDR context hints

The private MemExport67 scan found **69,724 opaque usages** out of 78,160 `REX_RAW_ADDR` references across 297 generated C++ sources. This script categorizes those usages by conservative lexical helper-name hints without publishing private C++.

The result is a *hint inventory*, **not** proof of memory writes or synchronization. All MemExport physical RAM commits remain disabled. No C++ code is rewritten; original game ZIP is untouched.

Run locally:

```sh
python3 scripts/classify_memexport68_opaque_helpers.py \
  --archive '/sdcard/Download/Fable2-Cpp-Real-Gerado-PRIVADO-24.zip' \
  --report build/memexport68-private-report.json \
  --expected-source-sha256 4a666a2488f5e9e55f9c3f3f5bee18bb3d3ffcedba870daacb8cb8699cc3bd9d \
  --expected-raw-references 78160 --expected-opaque-references 69724
cat build/memexport68-private-report.json
```

No counts should be interpreted as independent errors. The next implementation decision requires understanding actual access semantics in the generator and certifying *every* possible guest/host writer, including DMA and physical-memory mapping changes.
