# Fable II Android — Integração 04: shaders próprios + plugin Plume

**Estado:** componentes de compilação gráfica integrados no código; **não há APK jogável** nem binários ARM64 compilados nesta entrega.

## Código novo

1. `scripts/generate_fable_shaders.py`: gera a imagem de análise da XEX de **Fable II** (quando possível) e invoca XenosRecomp para gerar `shader_cache.cpp`, HLSL e relatório local de proveniência SHA-256. Não usa os caches de shaders de Burnout. Se o `default.xex` usar compressão não suportada pelo utilitário do Xerenge, aceita `--guest-image` já obtido legitimamente.
2. `port/gpu/CMakeLists.txt`: monta um alvo Vulkan `librexgpu-plume.so` a partir dos **arquivos reais do renderer Xerenge** (`plume_renderer/`), ligados a um cache de shaders produzido para Fable II. Também gera metadados dos HLSLs com o gerador *host* (`shader_source_info_gen`) ao compilar cruzado para Android. Dependências: código-fonte ReXGlue Android, Plume, XenosRecomp, etcpak e libadrenotools.
3. `scripts/build_fable_gpu.sh`: compila somente o plugin ARM64, usando Android NDK, SDK ReXGlue e o cache de shaders. Recusa cache não gerado para Fable II ou adulterado.
4. `scripts/setup_gpu_dependencies.sh`: baixa forks do SDK, Plume e XenosRecomp para a pasta ignorada `build/deps/` (não atualiza nem apaga clones existentes).
5. `scripts/gpu_log_report.py`: analisa logs `plume:` do dispositivo e resume shader misses, pipelines rejeitados, erros Vulkan etc., permitindo priorizar os próximos consertos de GPU.
6. `scripts/prepare_android_target.py`: Android usa `rexglue_setup_target(fable_2)` **sem tentar instalar o plugin desconhecido via SDK**; plugin separado é construído por `port/gpu`. Desktop mantém `GPU_PLUGINS xenos`.
7. `scripts/check_native_libs.py`: bloqueia empacotamento quando `SDL_main` não estiver exportado pelo runtime/jogo Android.
8. `Fable2LauncherActivity.java`: agora exige também `librexgpu-plume.so` antes de abrir o jogo.

## Por que não é um port pronto

- O Xerenge Plume usa processamento gráfico adaptado a Burnout. O código-fonte é reutilizável, mas os caminhos de EDRAM, formatos de render target, pipelines e shaders construídos em tempo de execução precisam de correções para Fable II.
- Nem todo shader de Fable II é necessariamente recuperável pela varredura estática do XEX. Shaders gerados/modificados em tempo de execução continuam sem tradução sem captura/receita própria do Fable.
- O fork `himdo/rexglue-sdk` não contém a entrada `SDL_main` para Android que o fork `shipa-2/rexglue-xerenge` fornece. Mesmo com a interface pública de GPU igual, o SDK e o código recompilado devem ser compatibilizados e compilados conjuntamente.
- Sem `default.xex` legalmente obtido, Android NDK, toolchain host e compilação/testes reais, não é possível comprovar que as libs carregam ou que o jogo exibe gráficos.

## Uso recomendado — Linux PC ou runner privado com Android NDK

```sh
# Fonte Android e checkout dos forks; sem conteúdo do jogo:
bash scripts/setup_gpu_dependencies.sh

# Instalar CMake, Ninja, clang e compilar ferramentas host:
cmake -S external/Xerenge/tools/cxx -B build/deps/xerenge-tools -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/deps/xerenge-tools --target dump_xex_image
cmake -S build/deps/XenosRecomp-xerenge -B build/deps/xenos-build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/deps/xenos-build --target XenosRecomp

# Seu dump legítimo de Fable II permanece FORA do repositório:
python3 scripts/generate_fable_shaders.py \
  --game-xex /CAMINHO/PRIVADO/Fable2/default.xex \
  --xex-dumper build/deps/xerenge-tools/dump_xex_image \
  --translator build/deps/xenos-build/XenosRecomp/XenosRecomp \
  --header build/deps/XenosRecomp-xerenge/XenosRecomp/shader_common.h

# Com um SDK compatível compilável para Android e com o NDK instalado:
export ANDROID_NDK_HOME=/CAMINHO/Android/sdk/ndk/VERSAO
export REXSDK_DIR="$PWD/build/deps/rexglue-xerenge"
export PLUME_ROOT="$PWD/build/deps/plume-xerenge"
export XENOS_RECOMP_ROOT="$PWD/build/deps/XenosRecomp-xerenge"
bash scripts/build_fable_gpu.sh
```

Caso o `default.xex` não seja suportado pelo `dump_xex_image`, o gerador falhará explicitamente em vez de criar shaders falsos. O caminho alternativo `--guest-image ...` recebe um arquivo PE de convidado previamente extraído da sua cópia legal do jogo.

Após ter um binário real e logs de Fable II:

```sh
python3 scripts/gpu_log_report.py ~/fable2-gpu.log --output gpu-report.json
```

## Limitações e licenças

O plugin é derivado de Xerenge, **GPL-3.0-or-later**; preserve autoria e obrigações da licença ao distribuir código/binários. ReXGlue e outros componentes têm licenças próprias. Nenhuma ISO, XEX, dados do jogo ou shader cache comercial está neste ZIP ou no GitHub. Todas as operações de geração são locais.
