# MemExport62 — instrumentação de caminhos reais do ReXGlue

Esta etapa instrumenta, no checkout fixado `3452b5ae...`, dois arquivos reais
`src/system/xthread.cpp` e `src/system/xmemory.cpp`. A instrumentação registra
o período de execução direta do guest em `XThread::Execute()` e as chamadas
de escrita por `Memory::Zero`, `Fill` e `Copy`. O patch usa âncoras exatas e
é aplicado apenas ao clone de compilação em `build/deps/rexglue-xerenge`.

O código observa contagens atômicas, concorrência, e volume de bytes escritos
pelos métodos instrumentados. Não altera os valores em memória, não suspende
threads, não bloqueia operações GPU e não habilita nenhum dos cinco shaders.

**Importante:** o host e o guest compilado podem modificar memória por acessos
diretos ao `virtual_membase`, `TranslatePhysical`, por DMA/Vulkan, áudio e outros
produtores que não passam por esses métodos. Mesmo que os contadores registrem
zero, a implementação retorna sempre `globally_exclusive_verified=false` e
`EveryMemoryWriterIsInstrumented()=false`. MemExport55/60/61 continua fechado.

Esta instrumentação é preparatória para identificar pontos adicionais e
integrar uma safepoint/barreira global real. `XThread::Suspend()` isolado não
comprova parada de todos os acessos. O SDK deve ser compilado e testado no
Android ARM64 após o patch; os testes sintéticos não comprovam renderização.

A integração privada deve permanecer privada. Não distribuir shaders ou
binários derivados do jogo pelo repositório público.
