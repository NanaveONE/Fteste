# Correção 39 — ReXGlue Android ARM64: alinhamento de 16 KB e SDK fixo

O pacote `rexglue-android-arm64-runtime-only (1).zip` contém um `librexruntime.so`
ARM64 real, mas os seus segmentos PT_LOAD têm p_align = 4096 bytes. Portanto,
a validação antiga passou porque **não testava alinhamento**. A `libc++_shared.so`
recebida já tem alinhamento de 16384 bytes.

## O que muda

- O workflow de runtime fixa o SDK em `3452b5ae307b5f71468cc8b9f18e7d7e0d4c245b`,
  a mesma revisão da compilação Fable II existente.
- O CMake passa a usar `ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON` e
  `-Wl,-z,max-page-size=16384` durante a **nova** compilação do motor.
- O build verifica a revisão do SDK de entrada para evitar uma mistura acidental.
- `scripts/check_android_16k_alignment.py` passa a verificar **ambas** as libs
  antes de fazer upload. Se permanecerem 4 KB, o workflow falha corretamente.

## Termux: aplicar e recompilar o motor (sem recompilar o jogo)

```sh
cd ~/Fteste
git pull --ff-only
unzip -o ~/storage/downloads/Fteste-runtime-16k-39.zip -d .
python3 scripts/enable_rexglue_runtime_16k_39.py
python3 -m unittest discover -s tests -p 'test_rexglue_runtime_16k_39.py' -v
bash -n scripts/build_rexglue_android_sdk.sh
git add .github/workflows/build-android-runtime.yml scripts/build_rexglue_android_sdk.sh
git add -f scripts/enable_rexglue_runtime_16k_39.py tests/test_rexglue_runtime_16k_39.py INSTRUCOES-39.md
git commit -m "Fixar SDK e alinhar ReXGlue ARM64 a 16 KB"
git push origin main
gh workflow run build-android-runtime.yml --repo NanaveONE/Fteste --ref main
```

Quando o workflow finalizar com sucesso:

```sh
gh run list --repo NanaveONE/Fteste --workflow build-android-runtime.yml --limit 3
gh run download --repo NanaveONE/Fteste --name rexglue-android-arm64-runtime-only --dir ~/storage/downloads/Fable2/rexruntime-16k
```

Não sobrescreva o `libfable2.so` de 242 MB. O APK só deve ser montado após
validar as dependências nativas e compilar `librexgpu-plume.so` usando o mesmo SDK.

**Limites:** alinhamento ELF e revisão do SDK não provam ABI dinâmica, Vulkan,
GPU Xenos/EDRAM, shaders ou gameplay. São testes necessários, não suficientes.
