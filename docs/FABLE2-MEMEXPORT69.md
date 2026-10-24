# Fable II MemExport69 — structural inspection of opaque REX_RAW_ADDR expressions

MemExport68 produced 69,724 `unknown_expression` hints. That **does not** mean
69,724 guest writes. The name-based lexing simply recognized no registered
helper families in the real generated C++.

MemExport69 groups the same opaque occurrences by nearby syntax: unknown
call arguments, pointer casts, returns, assignment expressions, pointer
arithmetic, postfix accesses, unary expressions, and a remaining unknown group.
The disjoint classification must reconcile to stage 67's opaque count and does
not leak source text or identifiers in the JSON.

```bash
python3 scripts/inspect_memexport69_opaque_shapes.py \
  --archive '/sdcard/Download/Fable2-Cpp-Real-Gerado-PRIVADO-24.zip' \
  --report build/memexport69-private-report.json \
  --expected-raw-references 78160 \
  --expected-opaque-references 69724 \
  --expected-source-sha256 4a666a2488f5e9e55f9c3f3f5bee18bb3d3ffcedba870daacb8cb8699cc3bd9d
cat build/memexport69-private-report.json
```

If context group totals are still uninformative, optional snippets can be
written **locally only** with `--private-examples build/memexport69-private-examples.txt`.
Those lines are game-derived content; **never upload them to the public repo,
CI logs or release**. The default JSON contains only aggregate counts.

This is an audit. It does NOT rewrite guest sources or implement stop-the-world,
DMA coordination, cache coherency, or Vulkan MemExport guest RAM commits. Shader
coverage remains 583/588 until those elements are functionally validated.
