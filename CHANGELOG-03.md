# Integração Android 03 — Fable II / Xerenge

**Resumo:** alterações reais no ponto de entrada ReXGlue, armazenamento Android,
controle SDL3, CMake e verificação de ABI nativa. Não é um APK funcional.

## Alterações introduzidas

1. `scripts/prepare_android_target.py` passou a criar uma cópia local com
   alterações também em `src/core/fable_2_app.h` e `src/main.cpp`, além de
   `CMakeLists.txt`. O submódulo Fable II original não é alterado.
2. A cópia Android usa o nome de backend `plume` no runtime; o desktop continua
   usando `xenos`. Isso **não** converte o Plume do Burnout para Fable II.
3. No Android, `FABLE2_GAME_ROOT` e `FABLE2_USER_ROOT` apontam os dados,
   saves e cache para armazenamento gravável fornecido pela Activity Java.
4. Dois probes de diagnóstico Win32 foram isolados do código Android.
5. Controles móveis com multitouch, sticks e botões Xbox via JNI e joystick
   virtual SDL3 (`fable2_touch.cpp` + `Fable2TouchControls.java`).
6. Pré-verificação de ELF ARM64, `DT_NEEDED`, símbolos de plugin ReXGlue e
   incompatibilidades públicas entre os dois SDKs.
7. `scripts/build_android_native.sh` declara a invocação NDK para fontes
   recompiladas de uma cópia legal do jogo, sem colocar dados no GitHub.

## Validações realizadas

- 20 testes unitários Python passaram localmente.
- Verificação de sintaxe shell e Python passou.
- AndroidManifest e arquivos Java/C++ verificados por inspeção; **não** houve
  compilação Android com SDK/NDK, nem teste de execução.

## Bloqueadores concretos ainda existentes

- A base SDK Android do Xerenge é uma fork diferente do SDK usado por
  Fable-2-Recomp. É necessário harmonizar as APIs, binários e codegen.
- O renderizador `librexgpu-plume.so` do Xerenge usa shaders, caches,
  render-state e vários caminhos de GPU específicos de Burnout Revenge.
  O simples nome `plume` não o torna compatível com Fable II.
- Recompilar o `default.xex` compatível exige extração de uma cópia legítima
  e um executável de codegen do **host**, compatível com o runtime escolhido.
- A adaptação deve passar por compilações e testes reais no aparelho;
  Vulkan anunciado no AndroidManifest não assegura suporte de driver.

## Publicar no GitHub via Termux

Baixe o ZIP completo da integração 03 e execute:

```bash
cd ~/Fteste
git pull
unzip -o ~/storage/downloads/Fteste-Fable2-Android-integracao-03.zip -d .
python -m unittest discover -s tests -v
git add .github .gitignore CHANGELOG-03.md port scripts tests
git commit -m "Fable II Android: runtime, GPU bridge e controles SDL3"
git push
```

Os dados comerciais (`default.xex`, `data/`, ISO) não devem ir ao GitHub.
