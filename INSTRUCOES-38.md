# Fteste - correção 38: validação de SDL_main

O log do build `39951160228` mostrou que o linker concluiu a criação de `libfable2.so`, e a checagem de alinhamento de 16 KiB passou. O bloqueio seguinte foi a verificação de exportação de `SDL_main`. O verificador antigo usava `llvm-readelf | grep -q` em shell com `set -o pipefail`, que pode falhar devido a SIGPIPE mesmo quando o símbolo existe.

A correção troca essa checagem por um script Python que consome todo o output de `llvm-readelf` e só aceita um símbolo `SDL_main` **definido**, `FUNC`, `GLOBAL`, `DEFAULT`, na tabela dinâmica. Se o símbolo realmente estiver faltando, a verificação falha de forma explicativa; **não desativa a segurança do build**. Não toca em `default.xex`, fontes recompiladas, patches da GPU ou no SDK.

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-correcao-SDL-main-38.zip -d .
python3 scripts/enable_fable2_sdl_export_38.py
python3 -m unittest discover -s tests -p 'test_sdl_export_38.py' -v
bash -n scripts/build_android_native.sh
git add -f scripts/build_android_native.sh scripts/check_fable2_sdl_export_38.py scripts/enable_fable2_sdl_export_38.py tests/test_sdl_export_38.py INSTRUCOES-38.md
git commit -m 'Corrigir verificacao SDL_main sem SIGPIPE'
git push origin main
gh workflow run build-fable2-arm64-26.yml --repo NanaveONE/Fteste --ref main -f release_tag=guest-input-26
```

Se o `SDL_main` estiver realmente ausente, o build deverá mostrar uma lista de símbolos relacionados. Essa evidência permitirá corrigir a exportação real, em vez de publicar uma `.so` inadequada. Após sucesso completo, `libfable2.so` será enviado à release **privada** como previsto no workflow. A biblioteca isolada não torna o jogo executável sem renderer Vulkan/Plume e empacotamento.
