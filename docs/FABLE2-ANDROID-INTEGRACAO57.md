# Fable II — integração ARM64 de diagnóstico 57 (NÃO É APK)

A compilação GPU Probe56 gerou `Fable2-Plume-ARM64-Probe56-PRIVADO.zip`,
com 583 de 588 shaders. Cinco vertex shaders MemExport continuam sem execução
comprovada de escrita/sincronização de RAM física. **Não habilite esse cache
incompleto no APK de produção.**

Esta etapa agrega bibliotecas privadas e verifica o *empacotamento ELF*:

- `libfable2.so` (recompilação do código do jogo, na release privada);
- `librexgpu-plume.so` (GPU Probe56, na mesma release privada);
- `librexruntime.so` e `libc++_shared.so` (compiladas com Android NDK 27.2.12479018);
- outras dependências `DT_NEEDED` que forem efetivamente necessárias.

O estágio usa o `stage_android_libs.py` existente para conferir símbolos de GPU,
`SDL_main`, arquitetura ARM64, dependências transitivas e bibliotecas proibidas.
Depois verifica alinhamento de todos os segmentos PT_LOAD em 16 KB. Não
executa o jogo nem prova a compatibilidade da ABI C++ entre builds separados.

A `Fable2Activity` passa `--gpu_plugin=plume` ao ReXGlue, pois o SDK escolhe
`xenos` por padrão. No Android, o carregador do SDK usa o diretório da biblioteca
`librexruntime.so` para localizar `librexgpu-plume.so` no `nativeLibraryDir` do APK,
com `android:extractNativeLibs="true"` já definido pelo projeto. Isso só será
exercitado depois que o APK estiver autorizado e compilado.

## Iniciar no GitHub Actions

Depois de aplicar o patch público ao repositório:

```sh
gh workflow run build-fable2-arm64-integrate57-private.yml \
  --repo NanaveONE/Fteste -f release_tag=guest-input-26
```

O workflow precisa do secret `FABLE2_PRIVATE_TOKEN` autorizado a ler/escrever a
release `guest-input-26` de `NanaveONE/Fable2-Arquivos-Privados`, contendo
`libfable2.so` e `Fable2-Plume-ARM64-Probe56-PRIVADO.zip`. Nenhum arquivo de jogo
é copiado para artefatos públicos. O ZIP privado de saída é
`Fable2-ARM64-Integracao57-PRIVADO.zip` e contém as bibliotecas ARM64 verificadas
em `lib/arm64-v8a/`, relatório `diagnostic/integracao57.json` e o aviso de
limitação. Falhas privadas são salvas em `Fable2-Integracao57-LOGS-PRIVADO.zip`.

## Permanecem pendentes

1. Implementação Xenos MemExport dos cinco vertex shaders, cobrindo formato,
   endereço físico, coerência com memória do guest e exclusão global de CPU;
2. validação 588/588 com SPIR-V e execução Vulkan real;
3. confirmação de ABI entre guest, runtime e plugin no aparelho Android;
4. APK instalável com carregamento SDL/Vulkan, áudio, controle e gameplay testados.

Essa etapa não altera o gate 588/588 de produção.
