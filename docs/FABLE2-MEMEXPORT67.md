# Fable II MemExport67 — raw physical/virtual address classification

The real MemExport66 report confirmed 297 generated translation units,
8,436 atomic calls wrapped and 38 memory intrinsic calls wrapped. It also
reported **78,160 `REX_RAW_ADDR` references not individually classified**.
These are **references**, not 78,160 proven writes and not 78,160 fixes.

MemExport67 scans the original verified private C++ to partition the raw address
references into disjoint, non-overlapping categories:

- Raw address inside the first argument of an atomic write candidate;
- Atomic argument whose role is not known;
- Memory intrinsic possible destination vs possible source vs other argument;
- Simple direct `*reinterpret_cast<T*>(REX_RAW_ADDR(...))` assignment vs read;
- Opaque or syntactically unparsed references.

Only the **basic syntax forms** above are recognized. In particular, an unknown
alias passed to a function, pointer arithmetic, DMA, cache operations, JIT and
raw stores in unknown syntactic forms remain unproven. Neither an "atomic" nor
a "destination" candidate proves that a store was actually executed.

A sanity check demands all categories sum to the counted references, and the
optional known source SHA-256 and expected 78,160 occurrences match the
provenance established by MemExport65/66. If not, the report is refused.

Run directly from the private original ZIP without extracting the 297 files:

```sh
python3 scripts/classify_memexport67_raw_addresses.py \
  --archive '/sdcard/Download/Fable2-Cpp-Real-Gerado-PRIVADO-24.zip' \
  --report build/memexport67-private-report.json \
  --expected-raw-references 78160 \
  --expected-source-sha256 4a666a2488f5e9e55f9c3f3f5bee18bb3d3ffcedba870daacb8cb8699cc3bd9d
cat build/memexport67-private-report.json
```

Alternatively the workflow `build-fable-memexport67-private.yml` reads the ZIP
from the private `guest-input-26` release and uploads **only sanitized JSON**
back to that private release. The GitHub Actions public logs contain no C++ or
private file paths.

**NO production authorization:** global writer coverage is not proven; no
MemExport GPU-to-guest memory commits may be enabled using this report. The
five unimplemented MemExport vertex shaders are still outstanding; diagnostic
cache coverage remains 583/588.
