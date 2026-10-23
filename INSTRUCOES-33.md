# Correção 33 — diagnósticos Windows no Android

Os cabeçalhos opcionais de instrumentação Windows incluídos diretamente por `src/main.cpp` ficam desativados **somente no Android**. O `fable2_state_probe.h` permanece incluído porque `fable_2_app.h` depende de suas funções. O código recompilado do jogo não é removido. O script altera exclusivamente `build/fable2-android-worktree/src/main.cpp`.

O workflow precisa chamar o script **depois de preparar o worktree e antes do CMake**; execute a inserção automática fornecida na conversa. Isto não garante que outros headers do projeto estejam portados.
