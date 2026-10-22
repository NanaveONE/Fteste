# Integração 09 — ReXGlue Android, áudio e shaders de execução

## O que esta atualização altera no código de verdade

- `scripts/port_fable_audio_sdk.py` modifica **uma cópia descartável do SDK Xerenge em `build/deps/`**, adicionando fallback silencioso temporizado do Fable II (48 kHz, blocos de 256 amostras) quando SDL3 não abre áudio. Preserva `DiscardPendingFrames()` e a saída SDL3 original. Fonte de referência: `himdo/rexglue-sdk` (BSD-3-Clause). O header do fallback está em `port/sdk/fable_clocked_audio_sink.h`.
- `scripts/build_rexglue_android_sdk.sh` tenta compilar **a biblioteca ARM64 real `librexruntime.so`** do mesmo checkout `REXSDK_DIR` que o host Fable II e o plugin Plume. Não compila jogo, só o runtime livre.
- `.github/workflows/build-android-runtime.yml` permite pedir **manualmente** no GitHub Actions a compilação do runtime ARM64, sem upload ou acesso a `default.xex`.
- `scripts/prepare_fable_plume.py` gera a cópia Fable do `plume_graphics_system.cpp` além da cópia `plume_draw.cpp`. Com `FABLE2_DUMP_UCODE=1`, registra microcódigo original e declarações para wrappers em `${FABLE2_USER_ROOT}/shader-captures/ucode-dump/` em vez do caminho relativo `generated/ucode-dump/`. O app Android disponibiliza uma opção para ativar isso. **Não equivale a shaders prontos em tempo real.**
- `scripts/compile_fable_runtime_shaders.py` executa as ferramentas host reais `rehost_runtime_shader`, `wrap_runtime_vertex_shader`, `wrap_runtime_pixel_shader`, `XenosRecomp` e `prepare_aux_shader_cache --suffix Bootstrap`, reconstruindo offline shaders que só aparecem em execução.
- `scripts/merge_fable_shader_sources.py` junta as fontes HLSL de shaders estáticos e dinâmicos sem colisões de hash e alimenta a tabela única `shader_source_info_gen` do Plume.
- `port/gpu/CMakeLists.txt` inclui a fonte adaptada do renderizador, e pode ligar o cache dinâmico Bootstrap ao cache estático do Fable II.
- `scripts/build_host_tools.sh` recompila também os utilitários de wrappers e localiza o gerador ReXGlue Release dentro da árvore Ninja Multi-Config em vez de adivinhar seu caminho.
- `scripts/attempt_playable_build.sh` compila o runtime SDK ARM64 se necessário e recusa misturar caches de shaders de XEXs diferentes.

## Status honesto (22/10/2026)

**Não foi possível compilar Fable II ARM64, executar a GPU no Android ou produzir APK jogável neste ambiente.** Este pacote contém fonte e um pipeline de build concreto, porém ainda existem incompatibilidades desconhecidas entre o código recompilado e o SDK, EDRAM/resolves e Vulkan. Não são resolvidas por mais testes de Python.

Validações: 74 testes locais, 1 ignorado pela indisponibilidade dos submódulos; sintaxe dos scripts Bash; C++ real do fallback de áudio compilado e executado em Linux; compilação C++ sintética dos trechos de capture/culling. Os pontos de patch foram verificados nos códigos upstream via GitHub. Nenhum `.so` ARM64 ou APK foi produzido.

## Primeira compilação que NÃO precisa dos arquivos do jogo

Depois de aplicar o ZIP no GitHub, entre em **Actions → Compilar ReXGlue Android ARM64 (sem dados do jogo) → Run workflow**. O artefato, se o build passar, será `rexglue-android-arm64-runtime-only` com o `librexruntime.so`. Isso NÃO é um APK de Fable II.

Para Linux local:

```sh
bash scripts/setup_gpu_dependencies.sh
bash scripts/build_rexglue_android_sdk.sh
```

Configure `ANDROID_NDK_HOME` para um NDK válido. O patch da SDK só altera uma cópia sob `build/`; nunca modifica os submódulos originais.

## Teste de shaders dinâmicos (depois de o jogo inicializar)

O processo que falta é circular por necessidade: sem uma execução inicial **não há capturas dos shaders gerados em tempo real**. Em um APK futuro com jogo compilado, marque **"Diagnóstico: capturar shaders do Fable II"** no launcher e carregue cenas. Transfira a pasta privada `${FABLE2_USER_ROOT}/shader-captures/ucode-dump/` para seu computador (somente arquivos de cópia própria; não publicar).

Em Linux, após obter `guest-image.bin` e compilar as ferramentas de `scripts/build_host_tools.sh`:

```sh
python3 scripts/compile_fable_runtime_shaders.py \
  --capture-dir /pasta/privada/ucode-dump \
  --guest-image build/fable2-shaders/xenos-scan/guest-image.bin \
  --translator "$FABLE2_SHADER_TRANSLATOR" \
  --header "$FABLE2_SHADER_HEADER" \
  --rehost "$FABLE2_SHADER_REHOST" \
  --wrap-vs "$FABLE2_SHADER_WRAP_VS" \
  --wrap-ps "$FABLE2_SHADER_WRAP_PS" \
  --rename "$FABLE2_SHADER_RENAME" \
  --output build/fable2-runtime-shaders
```

Depois execute `scripts/attempt_playable_build.sh --build`. O script valida que o novo cache pertence à mesma imagem de código do cache estático e o integra ao Plume. A tradução e novo build offline **não fornecem JIT automático** nem corrigem por si mesmos EDRAM, blending ou hardware Vulkan.

## Bloqueios ainda reais

1. **Código recompilado**: necessita `default.xex` e `data/` de uma edição legalmente própria e compatível, host codegen, NDK e eventuais mudanças no C++ a partir dos erros de compilação.
2. **ABI/runtime**: escolher o fork Xerenge como SDK único remove a divergência binária deliberadamente; o fallback de áudio do Fable II foi portado. Outras modificações específicas do Fable II no SDK original **não foram inteiramente reconciliadas** e podem exigir código adicional. O build real deve revelar quais.
3. **Renderização**: shaders dinâmicos exigem captura com jogo iniciando; formatos EDRAM, resolves, blend e sincronização específicos do Fable II continuam sem evidência para correções confiáveis.
4. **Android real**: áudio, saves, memória e gameplay só poderão ser validados com o aplicativo funcional em um aparelho. Nenhum teste de menu falso é apresentado como progresso do jogo.

As origens mantêm suas licenças. Nunca publicar `default.xex`, `data/`, código recompiled derivado nem caches de shaders de jogo comercial em repositório público.
