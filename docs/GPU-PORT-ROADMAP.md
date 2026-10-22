# Fable II Vulkan integration: exact unfinished boundary

Upstream references:

- Fable II: `external/Fable-2-Recomp/CMakeLists.txt`, `src/main.cpp`, `fable_2_manifest.toml`
- Xerenge: `external/Xerenge/rexglue/CMakeLists.txt`,
  `rexglue/src/plume_renderer/`, `scripts/build-android-apk.sh`

The two projects share the ReXGlue concept, NOT a plug-compatible complete
renderer. The current Fable application uses `rexglue_setup_target(fable_2
GPU_PLUGINS xenos)` and SDK GPU services. Xerenge's `rexgpu-plume` renderer
is a separate `.so` and contains title-specific draw processing, translated
shader caches and texture-format conversion. Loading the stock Xerenge
`librexgpu-plume.so` is NOT proof it supports Fable II.

Work required BEFORE a playable Android release:

1. Build a **matching** ReXGlue runtime for Android ARM64, and host-side
   ReXGlue codegen for the same SDK ABI. Xerenge's fork may diverge from the
   Fable II ReXGlue SDK; resolve differences rather than relabeling libraries.
2. Generate Fable II guest translation code from a compatible, legally owned
   `default.xex` via Fable's manifest; never upload game assets to GitHub.
3. Compile Fable II translated C++ and the game host into `libfable2.so`,
   exporting the native app entrypoint expected by SDL3.
4. Implement the graphics-system backend for Fable's Xenos calls: shader
   translation/cache (vertex/pixel), vertex layouts, EDRAM resolve, blending,
   texture formats, descriptors, render states, draw/present synchronization.
   The **Burnout** shader cache is not a valid replacement.
5. Negotiate the device's actual Vulkan version, extensions, memory features,
   color formats and supported texture compression at runtime. The manifest
   feature flag is NOT a substitute.
6. Implement Fable's input, audio, saving, and lifecycle handling; import game
   contents into a valid sandbox (the launcher is an initial implementation).
7. Only after the above: compile the 4 native ELF libraries, package via
   `scripts/package_android_apk.sh`, install, and test a real scene on device.

The helper scripts intentionally refuse to package a placeholder game without
native libraries. They do NOT verify game rendering or performance.

## Licensing and assets

Xerenge is published under GPL-3.0-or-later; Fable-2-Recomp identifies MIT.
Review all dependency notices before distribution. Redistribution of
proprietary Fable II binaries and assets is out of scope.

## Integração 04 — plugin separado e cache de Fable II

Foi adicionado `port/gpu/CMakeLists.txt` para construir o plugin Plume dos arquivos do Xerenge usando *cache de shaders do Fable II* gerado por `scripts/generate_fable_shaders.py`. Isso permite avançar na tradução gráfica sem embutir o código de Burnout no executável do jogo. **Não** prova compatibilidade de renderização.

O `dump_xex_image` usado pelo Xerenge atualmente só reconhece XEX com compressão BASIC; se a edição do Fable II utilizar outro formato, a etapa de extração pode falhar. O script aceita imagem já decodificada por um método legítimo como alternativa.

A próxima verificação deve ocorrer com GPU plugin e jogo compilados com **a mesma revisão do SDK**. Executar e ler `gpu_log_report.py` mostrará os shaders e comandos que precisam de suporte adicional. Também é necessário confirmar `SDL_main`, memória convidada, e validação de EDRAM, texturas e estados do Fable II.
