# Geração privada de C++ do Fable II (integração 23)

A biblioteca `libfable2.so` só pode ser compilada depois de traduzir o `default.xex` do **mesmo Fable II** existente em `external/Fable-2-Recomp`. Esta etapa isola a geração de código do Android NDK e do renderer Plume.

## Pré-requisitos

- Linux x86_64 (por exemplo, computador Linux x86_64; **Termux Android ARM64 não consegue rodar o artifact Linux x86_64 nativamente**).
- `git submodule update --init --recursive` executado em Fteste; precisamos do submódulo `external/Fable-2-Recomp`.
- O ZIP `fable2-rexglue-codegen-linux-x86_64.zip` extraído com **todos** os arquivos (`rexglue`, `librexruntime.so`, `codegen-report.json`).
- `default.xex` original de uma edição GOTY suportada, num local privado. Não copie ISO nem XEX para GitHub.
- Espaço para arquivos C++ gerados (potencialmente vários GB temporários).

## Exemplo (somente no Linux x86_64)

```bash
cd ~/Fteste
git submodule update --init --recursive
mkdir -p build/tools/fable2-codegen-linux
unzip -o ~/Downloads/fable2-rexglue-codegen-linux-x86_64.zip -d build/tools/fable2-codegen-linux
chmod +x build/tools/fable2-codegen-linux/rexglue

python3 scripts/generate_fable2_cpp_private.py \
  --tool "$PWD/build/tools/fable2-codegen-linux/rexglue" \
  --xex "$HOME/private-fable2/default.xex" --check

python3 scripts/generate_fable2_cpp_private.py \
  --tool "$PWD/build/tools/fable2-codegen-linux/rexglue" \
  --xex "$HOME/private-fable2/default.xex"
```

O script usa `external/Fable-2-Recomp/fable_2_manifest.toml` e `fable2_switch_tables.toml`, valida a edição do XEX contra o catálogo upstream e somente então cria `build/fable2-guest-codegen-private/`.

No sucesso, procure `build/fable2-guest-codegen-private/codegen-summary.json` e o relatório privado `codegen.log`. Em caso de falha, não compartilhe o diretório gerado nem o jogo; envie somente um trecho saneado do erro após remover dados privados. A pasta `build/` está no `.gitignore` do Fteste.

**Não gere nem empacote código do jogo num workflow público.** O próximo passo será adaptar/compilar o C++ com um ReXGlue SDK Android ABI-compatível para produzir `libfable2.so`. Os 16 shaders ainda pendentes e o Vulkan/EDRAM continuam bloqueios para gameplay.
