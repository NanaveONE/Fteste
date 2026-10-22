# Fable II Android — Integração 06: tentativa de build e catálogo de versões

**Status:** não existe APK jogável produzido/verificado nesta fase. O ambiente de
trabalho não possui um `default.xex` compatível, arquivos `data/`, SDK/NDK
Android nem um telefone conectado para testes de gameplay.

## Implementações novas

1. `scripts/build_host_tools.sh` compila, em Linux x86_64, os programas host
   de que a etapa Android realmente depende: Xerenge `dump_xex_image`,
   XenosRecomp e ReXGlue `rexglue` codegen. Corrige o comando errado da fase
   anterior: o alvo **CMake** chama-se `xerenge_tool_dump_xex`, embora o
   executável produzido se chame `dump_xex_image`.
2. `scripts/playable_preflight.py` verifica as ferramentas, fontes e caminhos
   privados essenciais **antes** de rodar recompilação ou tradução de shaders.
   Confere se o `default.xex` tem assinatura XEX2 e hash/tamanho de uma edição
   listada como `compatible: true` no catálogo **do próprio Fable-2-Recomp**,
   `constants/game_versions.json`. Verifica presença de arquivos exigidos e
   ausência dos arquivos explicitamente rejeitados pelo perfil.
3. `scripts/attempt_playable_build.sh --build` conecta as etapas reais:
   preflight, shader scan local, recompilação ARM64, plugin Vulkan do Xerenge,
   inspeção de bibliotecas ELF, empacotamento e assinatura Android.
   **Não cria nenhuma biblioteca fictícia.** Se falhar, o APK não é gerado.
4. A ferramenta compara o SHA-256 do cache de shaders local com o mesmo
   `default.xex` antes de reutilizar a cache, para não misturar edições.
5. `scripts/device_smoke_test.sh` abre o launcher por ADB e coleta logs nativos
   e Java após a tentativa de iniciar o jogo; não apaga os arquivos privados.
   Inspecionar/redigir logs antes de compartilhar.
6. CI expandida para executar os testes e confirmar que o preflight bloqueia
   builds sem arquivos privados; não faz upload de dados do Fable II.

## Testes executados

- `python -m unittest discover -s tests -v`: **49 testes passaram**.
- `bash -n scripts/*.sh`: sem erros de sintaxe.
- `cmake -S port/gpu -B build/cmake-preflight -G Ninja`: configuração parou
  corretamente em `Missing required -DREXSDK_DIR=...` (não havia SDK Android).
- `bash scripts/attempt_playable_build.sh --check`: **BLOCKED** como esperado:
  faltam arquivos do jogo, NDK, código-fonte dos submódulos no ambiente local,
  toolchain ReXGlue e shader translator. Isto **não é** compilação do jogo.

## Usar no computador Linux / GitHub local

```bash
cd ~/Fteste
git submodule update --init --recursive
bash scripts/setup_gpu_dependencies.sh
bash scripts/build_host_tools.sh
# Exportar os caminhos impressos por build_host_tools.sh, ANDROID_HOME,
# ANDROID_NDK_HOME, REXSDK_DIR, PLUME_ROOT, XENOS_RECOMP_ROOT,
# FABLE2_GAME_ROOT=/caminho/privado/para/default.xex+data/
bash scripts/attempt_playable_build.sh --check
bash scripts/attempt_playable_build.sh --build
```

O `--build` também precisa que `REXRUNTIME_LIB` identifique exatamente a
`librexruntime.so` ARM64 do mesmo SDK e que quaisquer libs não carregadas
por `DT_NEEDED` sejam selecionadas por `FABLE2_EXTRA_LIBS`. Exemplos e
variáveis estão em `--help`/documentação do script.

## Ainda impede gameplay real

- Não há XEX/dados privados para geração do código; o catálogo aceita somente
  as versões já verificadas pelo projeto Fable-2-Recomp.
- Não há NDK/SDK Android instalado neste ambiente para compilar o executável.
- O Plume do Xerenge não possui validação de shaders dinâmicos e comandos
  gráficos/EDRAM específicos de Fable II. Passar a build não seria prova de
  renderização/controles/audio/saves corretos.
- Testes reais no aparelho e correções baseadas no log do jogo continuam
  obrigatórios. Nenhum APK jogável foi criado nesta fase.
