# Fable II Android — Correção 16: threads do ReXGlue no NDK 27

Data: 22/10/2026

## Falha reproduzida nos logs do GitHub Actions

Workflow `Compilar ReXGlue Android ARM64`, execução `108004037582`, chegou
à tarefa **487 de 678**. O erro foi em
`build/deps/rexglue-xerenge/src/core/timer_queue.cpp`:

```
error: no type named 'stop_token' in namespace 'std'
error: no member named 'jthread' in namespace 'std'
error: no member named 'request_stop' in 'std::thread'
```

O NDK r27 (`android-31`, clang++/libc++) deste workflow não expõe as APIs
`std::jthread` e `std::stop_token`. A correção 15 para `float from_chars`
funcionou; o erro anterior **não aparece** nesta execução.

## Correção implementada

`scripts/patch_android_timer_thread.py` modifica **somente a cópia do SDK**
`build/deps/rexglue-xerenge/src/core/timer_queue.cpp` antes do CMake:

- Android: substitui `std::jthread` por `std::thread`, e `std::stop_token`
  por `std::atomic<bool> stop_requested_{false}`.
- Ao destruir `TimerQueue`, publica `stop_requested_ = true`, mantém o
  mecanismo original de **acordar o worker enfileirando um WaitItem** e
  faz `join()` para terminar os callbacks antes de liberar memória.
- Mantém integralmente o caminho `std::jthread/stop_token` original nas
  compilações não Android por blocos `#if defined(__ANDROID__)`.
- Atualiza o tipo do identificador para `std::thread::id` (compatível com
  `std::jthread::id` no desktop).
- Falha explicitamente se algum dos oito pontos do upstream mudou.
- É idempotente e inclui o modo `--check` para validar cada bloco antes do build.

`scripts/build_rexglue_android_sdk.sh` aplica e verifica esse patch **após**
a correção 15 e **antes** de configurar o CMake. A edição não afeta o
submódulo original, arquivos do jogo, Vulkan nem o renderizador Plume.

## Validação local

Seis testes de regressão passam, inclusive compilação e execução de programa
C++ com a lógica de criação/acordar/parar/join de threads nas duas variantes
(host desktop e host com `-D__ANDROID__`). Os oito âncoras textuais foram
conferidos no código público atual do fork `shipa-2/rexglue-xerenge`.

**A compilação ARM64 real ainda não foi repetida.** O teste com
`-D__ANDROID__` em Linux valida apenas o C++ condicionado, não o runtime
Android NDK. Um próximo erro de compilação poderá surgir após a etapa 487.

## Instalação no Fteste/Termux

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-correcao-ReXGlue-ARM64-16.zip -d .
python -m unittest discover -s tests -v
bash -n scripts/build_rexglue_android_sdk.sh
git add scripts/patch_android_timer_thread.py \
        scripts/build_rexglue_android_sdk.sh \
        tests/test_android_timer_thread_16.py CHANGELOG-16.md
git commit -m 'Corrigir timer_queue jthread no ReXGlue Android NDK'
git push origin main
```

Depois rode novamente o workflow manual `build-android-runtime.yml`.
Esse workflow compila apenas o `librexruntime.so` de código open-source;
**não é um APK Fable II** e não testa EDRAM, shaders ou gameplay.
