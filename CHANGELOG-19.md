# Integração 19 — Gerador de código Linux para a próxima etapa Fable II Android

## Objetivo

Gerar o executável **real** ReXGlue `rexglue` para Linux x86_64, usado como
`FABLE2_CODEGEN_TOOL` no build Android do Fable II.

## Como executar

1. Copie os arquivos deste ZIP para a raiz de `NanaveONE/Fteste`.
2. Execute `python -m unittest discover -s tests -v`.
3. Faça commit e push dos três arquivos.
4. Abra GitHub Actions > **Compilar ReXGlue codegen Linux (sem arquivos de jogo)** > Run workflow.
5. Baixe o artefato `fable2-rexglue-codegen-linux-x86_64`.

### Comandos de commit

```sh
git add .github/workflows/build-fable-codegen-host.yml scripts/package_fable_codegen_host.py tests/test_codegen_host_packaging_19.py CHANGELOG-19.md
git commit -m "Preparar codegen ReXGlue Linux para Fable II Android"
git push origin main
```

## O que está validado e o que não está

- O workflow usa o target upstream `rexglue` no preset Linux AMD64/Release.
- O empacotador só aceita ELF64 x86_64 e faz fechamento das dependências
  locais do SDK com verificação de `ldd` e smoke test `--version`.
- O executável pode ser compilado pelo GitHub Actions **sem nenhum arquivo do jogo**.
- **A compilação completa ainda precisa passar no GitHub Actions.** Não confunda
  testes de scripts com compilação do target `rexglue`.
- O seu XEX GOTY EUA/Europa é um perfil reconhecido pelo projeto, mas para
  compilar o jogo de verdade ainda é necessária a árvore comercial completa
  `data/` em ambiente PRIVADO, além do codegen, NDK e shaders completos.
- Nunca coloque `default.xex`, `.sbk`, pasta `data/`, fontes recompiladas
  derivadas do jogo ou cache compilado dos shaders no repositório público.
