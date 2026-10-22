# Fable II Android — Integração 07: estado de rasterização e diagnóstico de shaders

**Status:** foi feita uma alteração concreta no código do renderizador Plume usado para
Fable II; **não foi compilado nem testado gameplay no Android**, pois os arquivos
privados do jogo e o Android SDK/NDK não estão disponíveis neste ambiente.

## Correções e integrações

1. `scripts/prepare_fable_plume.py` copia `plume_draw.cpp` do Xerenge para
   `build/fable2-plume-overlay/`, preservando o submódulo original. Aplica duas
   alterações verificadas no fonte do Xerenge, com âncoras exatas, falhando
   caso o upstream mude. Grava manifesto com hash SHA-256 da origem e do resultado.
2. **Culling (faces):** o Xerenge/Burnout mantém o culling desligado, a menos que
   `XERENGE_CULL` seja definido. Na compilação específica de Fable II,
   `FABLE2_PLUME_PORT=1` ativa o estado de culling informado pelo Xbox 360;
   `FABLE2_DISABLE_GUEST_CULL=1` reverte o comportamento para depuração.
   **Não há prova ainda de que a orientação de faces corresponda a todos os
   materiais, reflexos e passagens gráficas de Fable II.**
3. **Shaders ausentes:** o Xerenge apenas imprime as primeiras oito falhas de
   pipeline. Agora, no port Fable, cada combinação inédita de hashes de VS/PS
   ausente é registrada uma única vez, limitada a 1.024 combinações para evitar
   inundar o log. A linha tem marcador `FABLE2_MISSING_PIPELINE`.
   Nenhum shader falso/fallback é fabricado. O draw continua sendo rejeitado
   quando faltam seus shaders genuínos.
4. `port/gpu/CMakeLists.txt` passa a compilar a cópia adaptada em lugar do arquivo
   original, sem trocar os outros arquivos do Plume nem os do jogo Burnout.
5. `scripts/build_fable_gpu.sh` chama o preparador antes de configurar o CMake.
6. `scripts/gpu_log_report.py` extrai hashes VS/PS ausentes, combinações de
   pipelines perdidas e estatísticas de cobertura de shaders do log real.
7. GitHub Actions tenta aplicar o patch sobre o submódulo real e confere os
   novos pontos de integração, sem precisar de dados comerciais do jogo.

## Validações desta sessão

- Código do Xerenge no submódulo `4916754f727d1be1353ec5e12e1df2190fc7569d`:
  ambos os trechos de patch aparecem exatamente uma vez e os includes para
  `std::set`/`std::mutex` já existem.
- `python -m unittest discover -s tests -q`: **57 testes passaram**.
- `bash -n scripts/*.sh`: OK.
- C++ sintético com os dois blocos exatos do patch: compilado via
  `clang++ -std=c++20 -fsyntax-only`, tanto com quanto sem `FABLE2_PLUME_PORT`.
  Isto é validação de sintaxe, **não compilação do renderizador completo**.
- `cmake -S port/gpu ...`: bloqueou por `Missing required -DREXSDK_DIR=...`, como
  esperado neste ambiente sem SDK Android.

## Compilação real e próximos bloqueios

O pipeline já preparado permite, **em Linux com Android SDK/NDK e uma cópia
pessoal compatível de Fable II**, executar:

```bash
cd Fteste
git submodule update --init --recursive
bash scripts/setup_gpu_dependencies.sh
bash scripts/build_host_tools.sh
# Configurar ANDROID_HOME, ANDROID_NDK_HOME, REXSDK_DIR, FABLE2_GAME_ROOT,
# FABLE2_CODEGEN_TOOL, FABLE2_XEX_DUMPER, FABLE2_SHADER_TRANSLATOR,
# PLUME_ROOT, XENOS_RECOMP_ROOT, REXRUNTIME_LIB conforme instruções da fase 06.
bash scripts/attempt_playable_build.sh --check
bash scripts/attempt_playable_build.sh --build
```

Após uma execução real em aparelho, extrair o log via
`scripts/device_smoke_test.sh` e executar
`python scripts/gpu_log_report.py <caminho-do-log>`.
O resultado dos shaders ausentes pode orientar geração de shaders dinâmicos de
Fable II, correções de EDRAM/resolve, formatos e pipeline, entre outras.

**Bloqueadores:** conteúdo original do jogo indisponível neste ambiente;
SDK/NDK ausentes; geração de shaders dinâmicos ainda não implementada para
Fable; compatibilidade real dos comandos gráficos/EDRAM ainda desconhecida;
necessário executar e depurar num telefone real. Nenhum APK jogável é alegado.
