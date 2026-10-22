# Correção 14 — GitHub Actions Android ARM64

## Falha reproduzida nos logs `logs_107992912881.zip`

O job `android-runtime` falhou em `android-actions/setup-android@v3`, **antes de
compilar o ReXGlue**, porque a ação usou sua lista padrão de pacotes
`tools platform-tools` e o `sdkmanager` respondeu:

```
Warning: Failed to find package 'tools'
Error: sdkmanager failed with exit code 1
```

## Alterações

- `.github/workflows/build-android-runtime.yml`: define explicitamente
  `packages: platform-tools` para deixar de solicitar o pacote obsoleto `tools`.
  Mantém instalação separada de `ndk;27.2.12479018` e
  `platforms;android-35`.
- `tests/test_android_runtime_sdk_setup_14.py`: regressões sem dependências
  adicionais para impedir o retorno do pacote `tools` e conferir que a versão
  do NDK instalada coincide com a exportada ao compilador.

## Validação

Os testes Python e a sintaxe YAML da correção foram validados localmente.
**Não houve nova execução no runner do GitHub Actions nesta etapa.** Somente
um novo workflow permitirá verificar a instalação NDK e revelar eventuais
falhas seguintes do build C++ ARM64.

## Aplicar

```sh
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-correcao-Android-SDK-14.zip -d .
python3 -m unittest discover -s tests -v
git add .github/workflows/build-android-runtime.yml tests/test_android_runtime_sdk_setup_14.py CHANGELOG-14.md
git commit -m "Corrigir pacote Android SDK legado no CI ARM64"
git push origin main
```

Depois, executar manualmente o workflow **Compilar ReXGlue Android ARM64
(sem dados do jogo)**. Este workflow compila somente o runtime livre, não o
Fable II inteiro nem o APK jogável.
