# Memgate73 — compilação ARM64 privada real (ReXGlue + Plume72)

This stage is a **private-only build and ELF ABI integration probe**. It does
not implement the five missing MemExport shaders or authorize physical RAM
commits. It uses the genuine Memgate71 guest from the verified private release,
rebuilds the pinned ReXGlue runtime with 71/72 hooks, then builds the actual
Plume72 GPU with 583/588 diagnostic Fable II shaders.

## Run

```sh
gh workflow run build-fable-memgate73-arm64-private.yml \
  --repo NanaveONE/Fteste \
  -f release_tag=guest-input-26 \
  -f xenos_run_id=39971826822
```

Set the existing `FABLE2_PRIVATE_TOKEN` repository secret. The private release
must already have `libfable2-Memgate71-DIAGNOSTICO.so`,
`libfable2_memgate71.so`, the two `.sbk` banks and
`Fable2-MemExport-DIAGNOSTICO-43.zip`. The translator artifact is downloaded
from an existing *public* XenosRecomp Linux+DXC workflow run.

If successful, the workflow uploads only
`Fable2-Memgate73-ARM64-DIAGNOSTICO-PRIVADO.zip` to the **private** release,
containing `lib/arm64-v8a/` with the guest, runtime, GPU, one shared Memgate71
DSO, libc++ and any required non-system runtime dependency. A sanitized
`diagnostic/memgate73.json` contains actual ELF SHA256, PT_LOAD alignments,
DT_NEEDED, verified C ABI symbols and compile-hook evidence. Private source,
shader contents and compiler logs remain under `build/` on the runner.

On build failure, private logs are uploaded to a separate private ZIP (when
an access token is available), without emitting proprietary source excerpts
into public CI logs. The normal production `libfable2.so` release asset is
**never** overwritten.

## What is actually checked

- ReXGlue pinned commit `3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b`;
- Memgate72 SDK writer/map hook report and verified Plume72 source overlay;
- exact incomplete 583/588 shader probe identity; all five known hashes missing;
- real AArch64 ELF64, 16 KiB PT_LOAD alignment and dependency closure;
- all three guest/runtime/GPU DSOs depend on the same Memgate71 **SONAME**;
- runtime build's own gate and the guest-provided gate export the required ABI;
- GPU plugin entrypoints and SDL entrypoint;
- ReXGlue C++ imports (ABI59) resolved within the private staged bundle.

**Not checked or certified:** cross-thread GPU device execution completion,
Vulkan queue fence ordering, all device DMA/mapping paths, all direct guest
stores, game output, frames/rendering, saves or audio. Importing one SONAME is
not proof of synchronization. MemExport commits stay prohibited. An APK is
not generated and shaders remain 583/588.

## Memgate73: diagnóstico do erro de contagem no Probe56

O workflow de compilação anterior falhou no Probe56 com
`Private cache does not contain exactly 583 entries`, antes de compilar o
runtime/Plume. A etapa de reconciliação registra **somente metadados** em
`cache-reconcile.json`, preservados dentro de
`Fable2-Memgate73-LOGS-PRIVADO.zip` na release privada quando a compilação falha.

- 583 entradas: mantém a compilação gerada e executa o validador Probe56 original.
- **588 entradas, exatamente os 583 anteriores + cinco VS com os hashes
  MemExport conhecidos**: verifica SHA256 de cada contêiner SBK extraído,
  a assinatura dos dois bancos e a integridade zstd/SMOL-V do cache privado 43.
  Somente após as verificações, reutiliza o **cache de diagnóstico original de
  583 shaders**, armazenando o resultado novo no `build/` ignorado.
- Qualquer outra contagem, shader diferente, banco adulterado, formato inválido
  ou falta dos cinco VS: **bloqueia**, sem alteração do cache nem aprovação.

Não trata os cinco shaders adicionais como executáveis corretos, não modifica
código de memória GPU e não libera commits MemExport na RAM. Caso a contagem
permaneça inesperada, consulte **somente** o JSON privado e informe
`generated_entry_count` e `status`; não publique C++/SPIR-V/HLSL dos shaders.
