# Fable II MemExport65 — pointer and atomic classification

This is a **diagnostic** improvement based on actual examples from the private Fable II generated C++:

- `static_cast<int64_t>(ctx.r31.u64 * static_cast<uint64_t>(112))` is numeric math, **not** a guest-memory access.
- `__sync_bool_compare_and_swap(reinterpret_cast<uint32_t*>(REX_RAW_ADDR(ea)), ...)` is a **conditional atomic writer** to a guest-memory address.

MemExport65 classifies numeric casts, pointer casts, direct dereference assignment
candidates, atomic read/write/fence forms, REX_RAW_ADDR occurrences, and common
memory intrinsic destination operands. Calls and cast operands can overlap in the
counts — do not sum them as distinct stores. Any unknown access remains unverified.

Run locally without extracting or publicly uploading private C++:

```sh
python3 scripts/classify_memexport65_guest_access.py \
  --archive '/sdcard/Download/Fable2-Cpp-Real-Gerado-PRIVADO-24.zip' \
  --report build/memexport65-private-report.json
cat build/memexport65-private-report.json
```

The report contains aggregate counts and the source set SHA256 **only**, not source
fragments, file paths or code addresses. The tool uses the stage-63 validated
private ZIP reader; it does not modify the ZIP or the generated code.

**No MemExport writes may be enabled using this report.** The stage-61 barrier is
not installed at every PPC/native writer, and the five MemExport shaders have
not been functionally validated with the full Vulkan + guest-memory path.
