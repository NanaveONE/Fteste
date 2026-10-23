# MemExport 47 — escrita CPU validada (não GPU Vulkan)

Este pacote faz *escritas reais* em um span de memória fornecido pelo chamador,
com validação de índice, intervalo e formato, e coleta intervalos alterados.
Por segurança só aceita bytes já codificados exatamente no formato do stream,
sem swap de componentes, sem formato numérico alternativo, sem endianness.

**Ainda falta implementar:** tradução eA/eM no XenosRecomp, formato/endianness Xenos,
memória convidada real, barreiras GPU-CPU, storage buffers e fallback compute
Vulkan, bindings e sincronização de caches. Continua 583/588 shaders; APK ainda
não é jogável. NÃO vincule esta escrita CPU a um draw Vulkan sem barreiras.

## Termux

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-MemExport-47.zip -d .
clang++ -std=c++20 -Wall -Wextra -Werror -pedantic \
  tests/test_fable_memexport_writer_47.cpp -o /tmp/test-fable47
/tmp/test-fable47

git add port/gpu/fable_memexport_writer_47.h \
  tests/test_fable_memexport_writer_47.cpp \
  .github/workflows/test-fable-memexport47.yml INSTRUCOES-47.md
git commit -m 'MemExport47: validar escrita CPU e intervalos alterados'
git push origin main
```

Workflow de teste sem dados privados do jogo. Não altere o `libfable2.so`.
