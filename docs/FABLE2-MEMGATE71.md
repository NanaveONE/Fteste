# Fable II Memgate71 — actual *shared* diagnostic synchronization

This is an opt-in experimental implementation, not a completed MemExport fix.
MemExport70 compiled the private 297 guest translation units with observation
of 8,436 atomic and 38 memory-intrinsic call sites. Those observers were per-
DSO and had no cross-library synchronization.

Memgate71 provides **libfable2_memgate71.so** with a stable C ABI and one
thread-nesting-aware, process-wide cooperative reader/writer gate (a drain
request excludes all *participating* writers until released). The shared
`.so`, not duplicated header-only state, owns the mutex and TLS nesting. It
is linked into the diagnostic guest, optional runtime and optional GPU builds.

The real participating paths when the diagnostic options are ON are:

- ReXGlue `XThread::Execute` entire guest execution interval;
- ReXGlue `Memory::{Zero, Fill, Copy}` function scopes;
- All MemExport70-instrumented guest atomic/memory-intrinsic calls (nested
  inside a guest executor where applicable);
- A Plume C entrypoint pair for *explicit* GPU-producer registration. Plume
  does NOT automatically call these at every GPU work submission yet.

**No** guest RAM commits are permitted. A successful diagnostic drain is not
proof that kernel/JIT, DMA, GPU device queues, audio, mapping invalidation,
shader memory formats or guest caches are covered. The C API deliberately
returns `memexport_commit_permitted=0` and `all_writers_certified=0` always.
The five MemExport shaders are still not validated (583/588).

### Run host tests

```sh
python3 -m unittest discover -s tests -p 'test_memgate71.py' -v
python3 -m unittest discover -s tests -p 'test_memexport70.py' -v
```

Host tests compile a real shared gate plus two independent client shared
libraries and verify that they agree on counters, guest writer acquisition,
nested scopes, exclusivity, timeout, and strict rejection of GPU commits.

### Android diagnostic guest build (private input)

```sh
gh workflow run build-fable2-arm64-26.yml --repo NanaveONE/Fteste \
  -f release_tag=guest-input-26 \
  -f memexport70_diagnostic=true -f memgate71_diagnostic=true
```

With both flags true, the workflow must link the original game guest's
diagnostic `.so` and `libfable2_memgate71.so`, upload both to the **private**
release, and keep proprietary sources/compiler logs outside public artifacts.
Neither library replaces the production release asset.

### Runtime and GPU builds

For a separately built pinned ReXGlue runtime, set
`FABLE2_MEMGATE71_DIAGNOSTIC=1` while running
`scripts/build_rexglue_android_sdk.sh`; it will install the ReXGlue writer
scopes and link its runtime to the same SONAME. The pinned source checkout is
verified before modification. A GPU diagnostic build can set the same flag
and provide `FABLE2_MEMGATE71_LIB=/absolute/path/libfable2_memgate71.so`.
**Distribute exactly one copy of the shared gate DSO with the same ABI and
content**; do not bundle separate gate instances or treat explicit Plume
registration as full renderer coverage.

### Remaining required work

1. Instrument all kernel/JIT direct writes, async producers, DMA and address
   mapping paths, and prove complete enrollment before requesting a commit.
2. Connect Plume's actual queue and GPU callback lifetimes to the writer gate,
   plus Vulkan queue/device ownership and completion fences.
3. Validate shader byte/word lane formats, endian conversion, write masks,
   physical RAM visibility, cache invalidation, and EDRAM interactions.
4. Verify the real Android ARM64 ABI in all three DSOs and execute game tests.

No part of Memgate71 changes guest RAM or lifts the MemExport55/60/61 safety
checks. Never upload private C++ ZIP, XEX, samples or private build logs to the
public Fteste repository.
