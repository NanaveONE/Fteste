# Fable II MemExport66 — instrument call sites in private generated guest C++

Diagnostic instrumentation only. It is **not** a fix for the remaining five
MemExport shaders. The true renderer and host memory barriers are **not** certified.

The stage-65 private audit found 8,436 guest-memory atomic write candidates,
and 38 memory-intrinsic calls. This transformer uses the **same** stage-65
scanner, rejects unknown atomic destinations, nested calls and unbalanced calls,
and wraps validated sites with `fable2::memexport66::ObserveWrite`. The original
atomic operation is evaluated once inside a lambda. Its return value (including
CAS success/failure), side effects and ordering are preserved in synthetic tests.

The observer counts active guest write calls, but **does not block CPU threads**.
It is not the stage-61 world gate, and cannot serve as a coverage proof. Direct
stores, DMA, invalidation and uninstrumented host writers remain outstanding.

## Private local use

The input is your **unmodified** private ZIP; the output is ignored in `build/`.
No generated code is committed or uploaded to the public repository.

```sh
cd ~/Fteste
python3 scripts/instrument_memexport66_guest_writes.py \
  --archive /sdcard/Download/Fable2-Cpp-Real-Gerado-PRIVADO-24.zip \
  --output-dir build/fable2-memexport66-private \
  --report build/memexport66-report.json \
  --expected-atomics 8436 --expected-intrinsics 38 \
  --expected-source-sha256 4a666a2488f5e9e55f9c3f3f5bee18bb3d3ffcedba870daacb8cb8699cc3bd9d
cat build/memexport66-report.json
```

If the input ZIP differs, the expected input SHA-256 / call counts **must not**
be relaxed without reviewing the corresponding original stage-65 inventory.

The transformed files are in `build/fable2-memexport66-private/` and include a
private-header copy. This patch intentionally does **not** replace the verified
`generated/default` sources automatically: doing so without a matching private
Android build and validation could give a false sense of runtime safety.

## Remaining requirements

- Verify transform against actual 297 generated translation units and compile
  all transformed files with the matching Android NDK, not just synthetic smoke.
- Prove all direct PPC writes, guest CPU, kernel, async producers, DMA and memory
  mappings are covered by a shared guest-wide synchronization mechanism.
- Integrate a real Vulkan fence + format/address/endianness correct MemExport
  commit, without deadlocks or torn writes.
- Only then promote the five experimental shaders from 583/588 to 588/588.

### Private CI validation of the actual 297 files

Once pushed, launch the optional private workflow:

```sh
gh workflow run build-fable-memexport66-private.yml \
  --repo NanaveONE/Fteste -f release_tag=guest-input-26
```

This downloads the private ZIP only in the private job workspace, verifies
8,436/38 call counts and the stage-65 source hash, and uploads ONLY the
sanitized `Fable2-MemExport66-RELATORIO-PRIVADO.json` to the private release.
No generated C++ is uploaded as a GitHub Actions artifact. The workflow does
**not** compile all transformed C++ for Android or enable MemExport commits.
