# Patch 32 — ImGui Android

O log de 23/10/2026 falhou em `rex/ui/style.h:18` por ausência do include `imgui.h` no comando do compilador do alvo `fable_2`. O script detecta o cabeçalho na cópia privada do SDK e adiciona o diretório ao CMAKE_CXX_FLAGS da build Android, sem alterar o repositório upstream ou publicar dados do jogo.

## Termux

```bash
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-correcao-imgui-32.zip -d .
python3 scripts/enable_imgui_android_32.py
python3 -m unittest discover -s tests -p 'test_imgui_android_32.py' -v
bash -n scripts/build_android_native.sh
git add scripts/build_android_native.sh scripts/enable_imgui_android_32.py tests/test_imgui_android_32.py INSTRUCOES-32.md
git commit -m 'Corrigir include ImGui no Android ARM64'
git push origin main
gh workflow run build-fable2-arm64-26.yml --repo NanaveONE/Fteste -f release_tag=guest-input-26
```

Se `imgui.h` estiver realmente ausente do SDK, a build interrompe com mensagem explícita. Outros erros de linkagem/headers só poderão ser confirmados em nova compilação.
