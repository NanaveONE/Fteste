# Fable II MemExport60 — adaptador de memória física ReXGlue

Esta etapa inclui `port/gpu/fable_memexport_rex60.h`, uma implementação do
contrato `memexport55::PhysicalMemoryHost` que utiliza diretamente
`rex::memory::Memory::GetPhysicalHeap()`, `QueryRangeAccess()` e
`TranslatePhysical()` da revisão **3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b**.

- Rejeita offsets fora dos 512 MiB de memória física e todas as páginas sem
  permissão de escrita; não confunde endereços virtuais 0xA/0xC/0xE com offsets físicos.
- Antes de qualquer escrita, exige um `CertifiedGuestWorld` explicitamente
  instalado, validado para essa revisão, e a garantia de que **todos os
  executores guest e produtores de memória** estão realmente parados.
- Notifica o coordenador de invalidade/dirty cache antes de liberar as threads.
- Herdando o MemExport55, a transação valida sobreposição, journal, fence,
  visibilidade, modo de bytes e todos os endereços ANTES do primeiro memcpy.

**Não há um `CertifiedGuestWorld` concreto no ReXGlue atual.** `XThread::Suspend`
individual ou um mutex no renderer NÃO suspendem todos os writers. Portanto,
o adaptador não é automaticamente instalado em `PlumeDrawContext` e as
escritas MemExport permanecem desativadas na execução real. Esta etapa não
aprova os shaders ausentes, não substitui 583/588 por 588/588 nem produz APK.

O teste `tests/test_memexport60.cpp` usa um header mock para testar segurança,
não equivale a teste contra um runtime Android real. Na etapa seguinte, um
coordenador do ReXGlue deve fornecer uma barreira cooperativa real para
threads do jogo, codegen/JIT, host writers e invalidadores da GPU; depois
uma build Android deve testar o header contra o SDK exato e confirmar a
ordenação Vulkan/CPU e o endianness dos shaders.

```sh
c++ -std=c++20 -Wall -Wextra -Werror -Itests/stubs \
  tests/test_memexport60.cpp -o /tmp/test_memexport60
/tmp/test_memexport60
```
