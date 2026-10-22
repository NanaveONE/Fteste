# Fteste — Integração 20: ISO do próprio Fable II

## Fable-2-Recomp é o mesmo jogo

**Fable-2-Recomp (`himdo/Fable-2-Recomp`) é a base do MESMO Fable II (Xbox 360) que estamos portando para Android.** Não substituir por código de Burnout Revenge ou outro jogo.

Esta integração reutiliza o sistema de arquivos GDFX, a disposição de arquivos e o catálogo de versões do **Fable-2-Recomp**, acrescentando extração de ISO à instalação Android do Fteste. Não contém arquivos comerciais.

### Android

- `port/android/java/com/nanaveone/fable2/Fable2IsoExtractor.java` — leitor GDFX independente do .NET, portado do formato de `tools/x360extract/lib/Gdfx.cs` de Fable-2-Recomp. Usa `FileChannel` da ISO selecionada por SAF; não duplica a ISO de vários GB.
- `port/android/java/com/nanaveone/fable2/Fable2IsoInstaller.java` — instala **somente** `default.xex` e `data/`; valida SHA-256 e edição GOTY *antes* de extrair `data/`, usando `Fable2GameCompatibility` que já acompanha Fteste; extração em `game.pending` e atualização atômica de `game/` com backup.
- `scripts/enable_fable_iso_install.py` — altera com verificação o `Fable2LauncherActivity.java` existente: botão `Selecionar ISO original do Fable II`; preserva o importador de pasta original e o teste de bibliotecas nativas antes de iniciar o jogo. Rodar após extrair este ZIP.

### Extrator upstream sem adaptações

- `scripts/extract_fable_iso_upstream.py` — usa **diretamente** o CLI .NET 8 original `tools/x360extract/` contido no submódulo `external/Fable-2-Recomp` em Linux/Windows. Divide a extração em duas fases: `default.xex` → verificação do catálogo → `data/`. Não sobrescreve destino existente.

### Validação

- `tests/java/Fable2IsoExtractorTest.java` e `tests/java/com/nanaveone/fable2/Fable2IsoInstallerTest.java`: fixture ISO GDFX sintética, diretório que atravessa dois setores, leitura cruzando fronteira de varredura de 4 MiB, XEX, `data`, exclusão de conteúdo de sistema e rejeição de assinaturas/caminhos/extents inválidos.
- `tests/test_fable_iso_android_20.py`: compilação Java de leitor e instalador (simulações mínimas de API Android), patch idempotente com recusa de layout inesperado e catálogo sintético.
- 7 testes Python, 10 verificações do leitor Java e instalação transacional completa em ISO/SAF sintéticos executados localmente.

**Não validado ainda:** extração de uma ISO real no dispositivo Android, a compilação completa do APK, tradução dos 16 shaders restantes, Vulkan/EDRAM e gameplay. O instalador é genuíno, não é um motor gráfico.

## Aplicar

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-ISO-Fable2-Android-20.zip -d .
python3 scripts/enable_fable_iso_install.py
python3 scripts/enable_fable_iso_install.py --check
python3 -m unittest discover -s tests -v

git add port/android/java/com/nanaveone/fable2/Fable2IsoExtractor.java \
  port/android/java/com/nanaveone/fable2/Fable2IsoInstaller.java \
  port/android/java/com/nanaveone/fable2/Fable2LauncherActivity.java \
  scripts/enable_fable_iso_install.py scripts/extract_fable_iso_upstream.py \
  tests/test_fable_iso_android_20.py tests/java/ \
  CHANGELOG-20.md docs/FABLE2-ISO-INTEGRATION-20.md \
  docs/FABLE2-UPSTREAM-LICENSE-20.txt

git commit -m "Integrar ISO original Fable II no instalador Android"
git push origin main
```

## Extrair no Linux opcionalmente

Necessário .NET 8 SDK e `git submodule update --init --recursive` para o repositório Fable-2-Recomp. Nunca execute isso em GitHub Actions público com arquivos do jogo.

```bash
python3 scripts/extract_fable_iso_upstream.py \
  --iso /caminho/privado/Fable2-GOTY.iso \
  --output /caminho/privado/Fable2-extraido
```

## Créditos e licença

Formato e fluxo de extração baseados no projeto **himdo/Fable-2-Recomp** (`tools/x360extract`), licença MIT. A licença e atribuição upstream são reproduzidas em `docs/FABLE2-UPSTREAM-LICENSE-20.txt`.
