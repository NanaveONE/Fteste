# Correção 31: timer_queue.cpp / Android NDK r27c

O NDK r27c não fornece `std::jthread` e `std::stop_token` neste build.
A correção converte a thread da fila de temporizadores em `std::thread`,
com sinal atômico de parada, wakeup via `QueueTimer` e `join()` explícito.

Após extrair na raiz de Fteste, edite o workflow
`.github/workflows/build-fable2-arm64-26.yml` e acrescente ao passo
**Corrigir float from_chars do ReXGlue para Android NDK** (depois do comando
que aplica a correção de float):

```bash
python3 scripts/fix_rexglue_android_threads_31.py --sdk build/deps/rexglue-xerenge
```

Não rode esta correção no SDK rastreado pelo Git: ela altera somente a cópia
`build/deps/rexglue-xerenge` clonada pelo workflow.

O resultado é uma correção de fonte ainda não validada por build Android completo.
