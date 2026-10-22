# Construindo primeiro o runtime nativo ARM64, não um launcher vazio

No GitHub do Fteste, o novo workflow manual **Compilar ReXGlue Android ARM64 (sem dados do jogo)** tenta produzir `librexruntime.so` com a NDK 27.2 e testa ELF AArch64. Isso é diferente do workflow `port-layout.yml`, que só examina fontes e testes.

## Ordem técnica real

1. **ReXGlue runtime**: `build_rexglue_android_sdk.sh` com o mesmo `REXSDK_DIR` usado em todos os CMake; a cópia contém os ajustes de áudio de Fable II.
2. **Host codegen/XenosRecomp**: `build_host_tools.sh` (Linux x86_64); resultados usados em `FABLE2_CODEGEN_TOOL`, `FABLE2_SHADER_TRANSLATOR`, `FABLE2_XEX_DUMPER`.
3. **Código do Fable II**: `build_android_native.sh` com arquivos privados `default.xex`, `data/`, NDK e SDK únicos. Não adivinhar se o gerador do Xerenge produz toda a API necessária — erros de C++ serão corrigidos a partir desta fase.
4. **Shaders estáticos**: `generate_fable_shaders.py` analisa o executável de Fable II; usar somente saída específica do título.
5. **Plugin Plume**: `build_fable_gpu.sh` com shader cache de Fable II e overlays `plume_draw.cpp` e `plume_graphics_system.cpp`; não usar a cache Burnout.
6. **Shader runtime offline**: depois de inicializar e capturar shaders, `compile_fable_runtime_shaders.py` e recompilar Plume.
7. **Vulkan/EDRAM**: só declarar formatos e resolves compatíveis após logs reais de draw/resolve/frame. Sem trace, mudanças arbitrárias podem tornar a renderização ainda mais incorreta.
8. **Instalador**: somente empacotar após NDK, Fable C++ e Plume realmente linkados. Testar os recursos do jogo num aparelho depois disso.

A compilação da biblioteca livre é necessária, mas insuficiente para um APK jogável.
