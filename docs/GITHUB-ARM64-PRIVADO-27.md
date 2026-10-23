# Fable II ARM64 — workflow com entrada e saída privadas

Aplique este ZIP na raiz do Fteste. Ele substitui o workflow 26, baixando `default.xex` e o ZIP C++ da release `guest-input-26` no repositório **privado** `NanaveONE/Fable2-Arquivos-Privados`. Nunca publica esses arquivos no Fteste.

## Permissão necessária

O secret `FABLE2_PRIVATE_TOKEN` deve ser um token fine-grained limitado ao repositório `Fable2-Arquivos-Privados`, com **Contents: Read and write**. A permissão `Read-only` basta para baixar, mas **não permite enviar `libfable2.so` à release privada**. Edite a permissão do token no GitHub e, se gerar novo valor, atualize o secret com `gh secret set FABLE2_PRIVATE_TOKEN --repo NanaveONE/Fteste`. Nunca cole o token no chat.

## Aplicação no Termux

```bash
cd ~/Fteste
unzip -o ~/storage/downloads/Fteste-GitHub-Privado-ARM64-27.zip -d .
git add .github/workflows/build-fable2-arm64-26.yml docs/GITHUB-ARM64-PRIVADO-27.md
git commit -m "Usar release privada para compilar Fable II ARM64"
git push origin main
```

## Executar

```bash
gh workflow run build-fable2-arm64-26.yml --repo NanaveONE/Fteste -f release_tag=guest-input-26
gh run list --repo NanaveONE/Fteste --workflow build-fable2-arm64-26.yml --limit 3
```

Se o build passar, o `libfable2.so` será enviado à **release privada**, e não a um artifact público. Não significa que o jogo já seja jogável.

**Observação:** logs de workflows públicos são visíveis. O script não imprime conteúdos de arquivos privados deliberadamente, mas revise mensagens de falha. Esta correção não substitui a integração 25.
