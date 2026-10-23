# Fteste — correção 37: ligação F5 Lua no Android ARM64

## O que o log provou

No job iniciado em 2026-10-23 10:42 UTC (commit `00cc4329`), o compilador
finalizou os objetos C++ e falhou ao ligar `libfable2.so`, na etapa 1006/1007.
`ld.lld` reportou exclusivamente estes três símbolos ausentes:

- `fable2::textappend::rdable2`
- `fable2::textappend::load_be`
- `fable2::textappend::host_addr`

Eles são chamados pelo diagnóstico opcional `LuaBind_RunScript_82806168` em
`src/core/fable2_f5_lua.h`. No Android, patch 33 já exclui o cabeçalho
`fable2_text_append.h`, que contém as definições inline dessas funções.
O diagnóstico usa a tecla F5 do Windows; ele não é necessário para a execução
básica do jogo e não deve substituir o dispatcher recompilado no Android.

## Solução

O patch 37 envolve **apenas** a inclusão de `fable2_f5_lua.h` em `main.cpp`
com `#if !defined(__ANDROID__)`. O recurso F5, o hook e as suas dependências
continuam intactos no Windows. No Android, o código gerado genuíno do jogo
fica responsável por `LuaBind_RunScript_82806168`.

O script verifica se o patch 33 já está aplicado e se o uso de `poll_f5()`
no controlador de teclado está protegido por `_WIN32`. Nada é alterado nos
297 arquivos C++ recompilados, no submódulo original ou nos arquivos
privados do jogo.

## Termux

1. Baixe `Fteste-correcao-linkagem-F5-37.zip` para Downloads.
2. Execute:

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-correcao-linkagem-F5-37.zip -d .
python3 scripts/enable_fable2_android_f5_lua_37.py
python3 -m unittest discover -s tests -p 'test_fable2_android_f5_lua_37.py' -v
python3 -m py_compile scripts/fix_fable2_android_f5_lua_37.py
bash -n scripts/build_android_native.sh
git add scripts/build_android_native.sh \
        scripts/fix_fable2_android_f5_lua_37.py \
        scripts/enable_fable2_android_f5_lua_37.py \
        tests/test_fable2_android_f5_lua_37.py \
        INSTRUCOES-37.md
git commit -m 'Isolar diagnostico F5 Lua no Android e corrigir linkagem'
git push origin main
gh workflow run build-fable2-arm64-26.yml --repo NanaveONE/Fteste -f release_tag=guest-input-26
```

O script de integração é idempotente. **Atenção:** o ZIP não contém o XEX nem
código recompilado privado; jamais envie esses arquivos para o repositório público.

## Verificação

Os testes locais verificam aplicação única, falhas de segurança e pré-processamento
C++ dos includes Android/Windows. A linkagem real Android, validação ARM64/16 KiB
e exportação `SDL_main` dependem da próxima execução GitHub Actions.
A existência de `libfable2.so` não comprova o funcionamento do jogo: o renderer
Vulkan/Plume e os shaders para Fable II ainda precisam de trabalho.
