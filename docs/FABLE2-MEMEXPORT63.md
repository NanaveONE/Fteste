# MemExport63: private generated guest memory audit

This stage inventories potential memory access sites in private generated Fable II C++.
It does not modify private generated sources, prove full write coverage, install a
stop-the-world barrier, or enable MemExport guest commits.

Run locally, **without uploading proprietary C++ or its detailed output**:

```bash
python3 scripts/audit_memexport63_guest_writes.py \
  --source-dir build/Fable-2-Recomp/generated/default \
  --report build/memexport63-private-audit.json
```

Or pass `--archive /path/to/private-generated-cpp.zip`. The JSON contains only
counts, sizes, and a source-set digest, never original C++ or filenames.
A zero count is not proof that writes are absent. This is a first step toward
locating the direct PPC memory paths for future synchronization work.

**Production gate remains closed: 583/588 shaders, no certified global exclusion.**
