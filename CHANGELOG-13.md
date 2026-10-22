# Fteste — Correção 13: erro de importação da Integração 12

## Erro exato confirmado nos logs do GitHub Actions

Arquivo: `logs_107980850568.zip`, job `check-sources` do workflow
`Fable II Android - Verificar integracao`, em 22/10/2026.

```
ImportError: cannot import name 'audit_cache' from 'scripts.validate_xenosrecomp_cache'
Ran 90 tests in 9.050s
FAILED (errors=1)
```

A Integração 12 substituiu o validador usado pela Integração 11 e retirou três
funções públicas importadas por `tests/test_xenosrecomp_cache_validation.py`:
`audit_cache`, `extract_cpp_cache` e `inspect_spirv`.

## Alterações

- **Restaurada** a API `audit_cache`, `extract_cpp_cache` e `inspect_spirv` sem
  retirar `inspect_cpp` nem `zstd_decode` da Integração 12.
- Os testes antigos usam **SPIR-V bruto sintético**, enquanto os caches reais
  do XenosRecomp usam **SMOL-V** dentro do zstd. O validador diferencia os dois
  formatos explicitamente, sem declarar SMOL-V como SPIR-V já validado.
- `audit_cache` para SMOL-V encaminha ao validador real `inspect_cpp` e devolve
  também os campos do relatório exigidos pelos testes antigos.
- O modo SPIR-V sintético continua a rejeitar estrutura inválida, entradas
  ausentes/duplicadas ou bytes excedentes.
- Um novo teste de regressão `tests/test_cache_api_compat_13.py` cobre as APIs
  preservadas e previne a mesma falha de importação.

## Validação local

- 7 testes anteriores da Integração 11 foram executados com sucesso.
- 6 testes adicionais da Integração 13 foram executados com sucesso.
- Teste com cache **real privado** do Fable II: 259/588 shaders (sem adaptação)
  ou 572/588 (com correção de textura 1D), com `INCOMPLETE` para ambos quando
  exigida cobertura de 100%. Os 16 shaders não convertidos continuam pendentes.
- Não foi construído nenhum APK, nem corrigido o código C++ do compilador
  para os 16 shaders remanescentes.

## Aplicação (Termux)

```sh
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-correcao-CI-13.zip -d .
python -m unittest discover -s tests -v
git add scripts/validate_xenosrecomp_cache.py tests/test_cache_api_compat_13.py CHANGELOG-13.md
git commit -m 'Corrigir compatibilidade do validador XenosRecomp no CI'
git push origin main
```

O ZIP contém apenas fonte e testes; não comite `default.xex`, `.sbk`,
`shader_cache.cpp` real nem outras cópias de conteúdo do jogo.
