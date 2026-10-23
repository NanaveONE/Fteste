# Fteste 25 — Compilação privada do Fable II C++ para ARM64

Esta mudança prepara uma compilação **real**, local e verificável de `libfable2.so` a partir do ZIP privado `Fable2-Cpp-Real-Gerado-PRIVADO-24.zip`. Não inclui códigos ou arquivos comerciais do jogo.

## Correções

- Importador com lista permitida de entradas do ZIP, bloqueio de caminhos perigosos, validação SHA-256 do `default.xex`, hash do manifesto, revisão exata do Fable-2-Recomp, 297 traduções listadas em `sources.cmake` e consistência das contagens de bytes.
- Verifica revisão **3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b** do SDK Android/ReXGlue contra a revisão com que o Codegen gerou os arquivos, evitando misturar bibliotecas/cabeçalhos com procedências diferentes.
- Todos os arquivos do jogo e fontes geradas permanecem em `build/`, ignorado pelo Git; os originais `external/Fable-2-Recomp` e `FABLE2_GAME_ROOT` não são modificados.
- `generated/rexglue.cmake` é modificado **somente na cópia de build**. Com `FABLE2_PRIVATE_CPP_IMPORTED=ON`, não executa Codegen Linux ou Android durante cross-build. Preserva o comportamento original quando essa opção está OFF.
- `scripts/build_android_native.sh` aceita `FABLE2_PRIVATE_CPP_ZIP` e deixa de exigir a pasta `data/` para **compilar**, mas ainda exige a `default.xex` correta para validar proveniência.
- Passa `-DFABLE2_CODEGEN_TOOL=` ao CMake para não tentar configurar `IMPORTED_LOCATION` em um alias não importado; `REXGLUE_CODEGEN` preserva o caminho do host no modo sem ZIP.
- Liga Android NDK com alinhamento mínimo PT_LOAD de 16 KB e valida o `.so` ARM64 e o símbolo SDL_main antes de aceitar a etapa como concluída.

## Limites

- Os testes locais confirmaram a importação dos **297 arquivos C++ reais** e a execução idempotente do importador, sem Android NDK presente. Os testes de regressão incluídos no pacote usam fontes sintéticas.
- **Ainda não compilou `libfable2.so`**. Um ambiente Linux x86-64 com SDK/NDK é obrigatório para essa etapa e erros de C++/linkagem podem surgir.
- O `libfable2.so` depende de runtime, plugin GPU Plume e shaders; um `.so` compilado não comprova que o jogo inicia ou está jogável.
- NUNCA envie o ZIP privado de C++/XEX, `build/`, shaders, dados `data/` ou símbolos extraídos ao GitHub público/artefatos de Actions.
