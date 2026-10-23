# Fable II ARM64 - GitHub Actions (26)

O workflow usa a integracao 25, ainda necessaria no branch main. O workflow nao foi executado; compilacao e compatibilidade nao estao confirmadas.

1. Aplique a correcao 25 e rode `python3 scripts/enable_fable2_private_arm64.py` antes de commitar os arquivos publicos do patch 25.
2. Aplique o ZIP 26 e envie `.github/workflows/build-fable2-arm64-26.yml` e este documento ao GitHub.
3. Crie uma GitHub Release com uma tag a sua escolha (por exemplo `guest-input-26`) e adicione exatamente dois arquivos: `Fable2-Cpp-Real-Gerado-PRIVADO-24.zip` e `default.xex`.
4. Actions > Fable II ARM64 - compilar guest real > Run workflow > informe a tag da release.
5. Confira o job. Se passar, baixe `fable2-android-arm64-guest-26` em Artifacts.

**ATENCAO:** em repositorio publico, os arquivos da Release ficam publicamente acessiveis. O XEX e o codigo C++ derivado do jogo podem estar sujeitos a direitos autorais. A escolha de publicar esses arquivos e sua responsabilidade; a opcao mais segura e manter as entradas em repositorio privado. Remover uma release depois nao garante remocao de copias feitas por terceiros.

A saida `libfable2.so` tambem e derivada do jogo. Publica-la em artefato publico pode ter o mesmo problema. O workflow **nao gera APK jogavel** e nao resolve shaders/Plume. Se falhar, envie apenas o log para analise, sem anexar os arquivos comerciais.
