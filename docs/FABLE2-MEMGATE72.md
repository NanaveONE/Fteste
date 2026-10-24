# Fable II Memgate72 — real PM4 write sites, host mappings, async producer scopes

This is a **diagnostic-only** incremental extension to verified Memgate71 and
MemExport70. It does not enable the five missing MemExport shaders or GPU
physical-RAM commits. **No all-writer certification is claimed.**

## Newly enrolled known sites

`patch_rex_memgate72_sdk.py` works **only** on the pinned private build clone
of ReXGlue at `3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b` after Memgate71:

- Direct host physical stores from the GPU's `REG_TO_MEM`, `MEM_WRITE`,
  `COND_WRITE`, event write and register scratch/writeback paths.
- The `EVENT_WRITE_ZPD` packet handler, which also writes a structured sample
  counter through a pointer.
- System heap allocation/free, mapped MMIO registration and GPU-written-range
  notifications. These paths are **not** complete DMA/mapping coverage.

`apply_fable_plume72.py` builds a **new** checked Plume overlay layer from
MemExport61's original output (`build/fable2-plume-overlay-61`), leaving all
old overlays and upstream Xerenge files untouched. It enrolls actual guest
physical-memory writes in `Pm4WritePhysical` and `WriteReadPointerWriteback`,
PM4 execution, resolve request/encoding, and the CPU work performed by the
video and present worker threads **after** their request mutexes are released.

This stage also restores **strict historical CI** for Plume52, 53, and 55.
`scripts/normalize_fable_plume_build.py` recognizes only the exact MemExport61
and Memgate71/72 build suffixes, removes them **in memory** for older checks,
and rejects any incomplete or modified suffix. It does not rewrite old layers.

The shared Memgate71 DSO remains the *same* `libfable2_memgate71.so` linked
by all opted-in libraries. A CPU-side Vulkan submit/encode scope does NOT keep
all participating writers stopped until Vulkan device completion. DMA engines,
asynchronous queue callbacks, mmap aliases, device fences, physical-memory
cache invalidation, race-free ownership and actual MemExport SPIR-V shaders
must be audited and implemented before granting any commit.

## Run tests

```sh
python3 -m unittest discover -s tests -p 'test_memgate72.py' -v
python3 -m unittest discover -s tests -p 'test_memgate71.py' -v
bash -n scripts/build_rexglue_android_sdk.sh
bash -n scripts/build_fable_gpu.sh
```

## Build diagnostic runtime and GPU in private worktree

```sh
export FABLE2_MEMGATE71_DIAGNOSTIC=1
bash scripts/build_rexglue_android_sdk.sh
# GPU build requires the previously generated PRIVATE shader cache and matching
# SDK/Plume/XenosRecomp checkout and the exact shared gate DSO:
export FABLE2_MEMGATE71_LIB="$PWD/build/rexglue-android-arm64/libfable2_memgate71.so"
bash scripts/build_fable_gpu.sh
```

The existing `build-fable2-arm64-26.yml` guest test covers the guest .so only.
It does **not** compile the private Vulkan GPU plugin or all runtime/DMA paths.
This patch therefore ships public source/synthetic tests, not a claim that a
playable Android build is available. The private shader cache remains 583/588.
